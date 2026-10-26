""".hpm files: a package's folder in one file (docs/hpm/hpm.md, section 3; the plan's
decision 2 and step 1).

The folder:

    hpm.toml              the manifest
    CHANGELOG.md          what changed, newest first
    files/root/...        files under / of a world:  files/root/usr/local/bin/kittystory
    files/home/...        files under the user's home: files/home/.kittystory/packs/x.pack
    migrations/*.md       notes for the AI when the data format changes

An archive is that folder as a gzipped tar. pack() makes the same bytes from the same files:
the names in a fixed order (hpm.toml first, so read_manifest finds it at once), the files'
times kept, and nothing of the machine that packed it (owners, modes, the gzip header's
time). unpack() trusts nothing in a file: it reads every entry's header and refuses the
whole file, before writing anything, if one breaks a rule. It never calls tarfile's own
extract, so the rules hold on every Python from 3.11 on.
"""
from __future__ import annotations

import contextlib
import gzip
import hashlib
import os
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from hallux.hpm.manifest import MANIFEST_MAX, Manifest, ManifestError, check_path

MANIFEST = "hpm.toml"
CHANGELOG = "CHANGELOG.md"
REVIEW = "review.md"                      # the AI's review of the card, made at publish
FILES, MIGRATIONS = "files", "migrations"
ROOTS = {"root": "/", "home": "~/"}       # files/<this>/... is the machine path <that>...
TOP = {MANIFEST, CHANGELOG, REVIEW, FILES, MIGRATIONS}
FILES_MAX = 10_000                        # files in one package
BYTES_MAX = 200 * 1024 * 1024             # what they hold together, unpacked
NAME_MAX = 1024                           # characters of one name in the archive
PIECE = 1024 * 1024


class ArchiveError(ValueError):
    """A package that can't be packed, or a file that isn't a package hpm will unpack."""


# ---------------------------------------------------------------------- names

def to_machine(member: str) -> str:
    """The machine path of a name under files/: "files/home/.kittystory/x" -> "~/.kittystory/x".
    ValueError for a name that isn't a package's file."""
    parts = member.split("/")
    if len(parts) < 3 or parts[0] != FILES or parts[1] not in ROOTS:
        raise ValueError(f"{member[:80]!r} isn't under files/root/ or files/home/")
    return check_path(ROOTS[parts[1]] + "/".join(parts[2:]))


def to_member(path: str) -> str:
    """The name in a package of a machine path: "/usr/local/bin/x" -> "files/root/usr/local/bin/x"."""
    check_path(path)
    if path.startswith("~/"):
        return f"{FILES}/home/{path[2:]}"
    return f"{FILES}/root/{path[1:]}"


def _member_problem(name: str, is_dir: bool) -> str | None:
    """Why a name can't be in a package, or None."""
    shown = repr(name[:80])
    if not name or len(name) > NAME_MAX:
        return f"a name of {len(name)} characters"
    if name.startswith("/") or "\\" in name or (len(name) > 1 and name[1] == ":"):
        return f"{shown} is an absolute name"
    parts = name.rstrip("/").split("/") if is_dir else name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return f"{shown} has an empty name, . or .. in it"
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        return f"{shown} has a control character in it"
    top = parts[0]
    if top not in TOP:
        return f"{shown} is no part of a package ({', '.join(sorted(TOP))})"
    if top in (MANIFEST, CHANGELOG, REVIEW):
        return f"{shown} must be a file" if is_dir or len(parts) > 1 else None
    if top == MIGRATIONS:
        if is_dir:
            return None if len(parts) == 1 else f"{shown}: migrations/ holds no folders"
        if len(parts) != 2 or not parts[1].endswith(".md"):
            return f"{shown}: migrations/ holds only .md notes"
        return None
    # files/
    if len(parts) == 1 or (is_dir and len(parts) == 2 and parts[1] in ROOTS):
        return None if is_dir else f"{shown} must be a folder"
    if parts[1] not in ROOTS:
        return f"{shown}: files/ holds only root/ and home/"
    if is_dir:
        return None
    try:
        to_machine(name)
    except ValueError as e:
        return str(e)
    return None


# ---------------------------------------------------------------------- packing

def pack(folder: Path | str, out: Path | str) -> Path:
    """Pack a package's folder into one .hpm file at `out`. The manifest is checked first,
    and every file must be one a package may hold: anything else, a link or a device
    included, is refused with every reason at once. The file appears whole or not at all."""
    folder, out = Path(folder), Path(out)
    entries = _gather(folder)
    data = (folder / MANIFEST).read_bytes()
    try:
        Manifest.load(data)
    except ManifestError as e:
        raise ArchiveError(f"{folder / MANIFEST}: {e}") from None
    out.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=f".{out.name}.", suffix=".part", dir=out.parent)
    try:
        with os.fdopen(handle, "wb") as raw, \
                gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped, \
                tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for name, real in entries:
                found = real.stat()
                info = tarfile.TarInfo(name)
                info.size, info.mtime, info.mode = found.st_size, int(found.st_mtime), 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                with real.open("rb") as reader:
                    tar.addfile(info, reader)
        os.replace(temp, out)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise
    return out


def _gather(folder: Path) -> list[tuple[str, Path]]:
    """The files to pack, by their names in the package: hpm.toml first, the rest sorted."""
    if not (folder / MANIFEST).is_file():
        raise ArchiveError(f"{folder} has no {MANIFEST}")
    problems: list[str] = []
    files: list[tuple[str, Path]] = []
    total = 0
    for real in sorted(folder.rglob("*")):
        name = real.relative_to(folder).as_posix()
        mode = real.lstat().st_mode
        if stat.S_ISDIR(mode):
            if problem := _member_problem(name + "/", is_dir=True):
                problems.append(problem)
            continue
        if not stat.S_ISREG(mode):
            problems.append(f"{name!r} is a link or a special file; a package holds plain files")
            continue
        if problem := _member_problem(name, is_dir=False):
            problems.append(problem)
            continue
        files.append((name, real))
        total += real.stat().st_size
    if len(files) > FILES_MAX:
        problems.append(f"{len(files)} files, more than {FILES_MAX}")
    if total > BYTES_MAX:
        problems.append(f"{total} bytes, more than {BYTES_MAX // (1024 * 1024)} MB")
    if problems:
        raise ArchiveError(_told(folder, problems))
    files.sort(key=lambda entry: (entry[0] != MANIFEST, entry[0]))
    return files


def _told(where: object, problems: list[str]) -> str:
    many = "1 problem" if len(problems) == 1 else f"{len(problems)} problems"
    text = f"{where}: {many}: " + "; ".join(problems[:20])
    return text + (f"; and {len(problems) - 20} more" if len(problems) > 20 else "")


# ---------------------------------------------------------------------- unpacking

def unpack(file: Path | str, into: Path | str) -> Manifest:
    """Unpack a .hpm file into `into`, a folder that doesn't exist yet or is empty. Every
    entry is checked before anything is written: plain files and folders only, names inside
    the package's layout, at most FILES_MAX files and BYTES_MAX bytes, a good manifest. A
    file that breaks one is refused as a whole, with what was wrong, and if writing fails on
    the way the folder is taken away again. Returns the manifest."""
    file, into = Path(file), Path(into)
    members, manifest = _checked_members(file)
    made = not into.exists()
    if not made and (not into.is_dir() or any(into.iterdir())):
        raise ArchiveError(f"{into} must be a new or empty folder")
    into.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(file, mode="r:gz") as tar:
            for count, info in enumerate(tar):
                if count >= len(members) or not _same(info, members[count]):
                    raise ArchiveError(f"{file} changed while it was unpacked")
                target = into.joinpath(*PurePosixPath(info.name).parts)
                if info.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                reader = tar.extractfile(info)
                with reader, target.open("xb") as writer:   # "x": never over anything
                    left = info.size
                    while piece := reader.read(min(PIECE, left)):
                        writer.write(piece)
                        left -= len(piece)
                    if left:
                        raise ArchiveError(f"{file}: {info.name} ends early")
                os.utime(target, (info.mtime, info.mtime))
    except BaseException:
        if made:
            shutil.rmtree(into, ignore_errors=True)
        else:                                     # it was empty: it is empty again
            for child in into.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
        raise
    return manifest


def _same(info: tarfile.TarInfo, checked: tarfile.TarInfo) -> bool:
    return (info.name, info.type, info.size) == (checked.name, checked.type, checked.size)


def _checked_members(file: Path) -> tuple[list[tarfile.TarInfo], Manifest]:
    """Every entry's header, checked, and the manifest; or ArchiveError with all problems."""
    problems: list[str] = []
    members: list[tarfile.TarInfo] = []
    names: set[str] = set()
    manifest_data: bytes | None = None
    files = total = 0
    try:
        with tarfile.open(file, mode="r:gz") as tar:
            for info in tar:
                name = info.name
                if info.isdir():
                    if problem := _member_problem(name.rstrip("/") + "/", is_dir=True):
                        problems.append(problem)
                elif not info.isreg():
                    problems.append(f"{name[:80]!r} is a link or a special file")
                elif problem := _member_problem(name, is_dir=False):
                    problems.append(problem)
                else:
                    files += 1
                    total += info.size
                    if name == MANIFEST:
                        if info.size > MANIFEST_MAX:
                            problems.append(f"its {MANIFEST} is bigger than "
                                            f"{MANIFEST_MAX // 1024} KB")
                            manifest_data = b""
                        else:
                            manifest_data = tar.extractfile(info).read()
                key = name.rstrip("/")
                if key in names:
                    problems.append(f"{name[:80]!r} is in it twice")
                names.add(key)
                members.append(info)
                if files > FILES_MAX:
                    problems.append(f"more than {FILES_MAX} files")
                    break
                if total > BYTES_MAX:
                    problems.append(f"more than {BYTES_MAX // (1024 * 1024)} MB unpacked")
                    break
    except (tarfile.TarError, OSError, EOFError, gzip.BadGzipFile) as e:
        raise ArchiveError(f"{file}: not a package hpm can read ({type(e).__name__}: {e})") \
            from None
    manifest = None
    if manifest_data is None:
        problems.append(f"no {MANIFEST} in it")
    elif manifest_data:
        try:
            manifest = Manifest.load(manifest_data)
        except ManifestError as e:
            problems.append(str(e))
    if problems:
        raise ArchiveError(_told(file, problems))
    return members, manifest


def read_manifest(file: Path | str) -> Manifest:
    """The manifest of a .hpm file, read without unpacking the rest: pack() puts it first."""
    file = Path(file)
    try:
        with tarfile.open(file, mode="r:gz") as tar:
            for info in tar:
                if info.name == MANIFEST and info.isreg():
                    if info.size > MANIFEST_MAX:
                        raise ArchiveError(f"{file}: its {MANIFEST} is too big")
                    return Manifest.load(tar.extractfile(info).read())
    except (tarfile.TarError, OSError, EOFError, gzip.BadGzipFile) as e:
        raise ArchiveError(f"{file}: not a package hpm can read ({type(e).__name__}: {e})") \
            from None
    except ManifestError as e:
        raise ArchiveError(f"{file}: {e}") from None
    raise ArchiveError(f"{file}: no {MANIFEST} in it")


def package_files(folder: Path | str) -> dict[str, Path]:
    """The files of an unpacked package, by their machine paths: "~/.kittystory/x": its file."""
    folder = Path(folder)
    found: dict[str, Path] = {}
    base = folder / FILES
    for root in ROOTS:
        top = base / root
        if not top.is_dir():
            continue
        for real in sorted(top.rglob("*")):
            if real.is_file() and not real.is_symlink():
                found[to_machine(real.relative_to(folder).as_posix())] = real
    return found


def sha256(file: Path | str) -> str:
    """The file's fingerprint, as "sha256:<hex>"."""
    digest = hashlib.sha256()
    with Path(file).open("rb") as reader:
        for piece in iter(lambda: reader.read(PIECE), b""):
            digest.update(piece)
    return "sha256:" + digest.hexdigest()


def listing(file: Path | str) -> dict[str, tuple[int, str]]:
    """Every file of a .hpm file, by its name in the package: (size, "sha256:<hex>"). Read
    from the archive itself, nothing unpacked; publish compares a world's files with it."""
    file = Path(file)
    found: dict[str, tuple[int, str]] = {}
    try:
        with tarfile.open(file, mode="r:gz") as tar:
            for info in tar:
                if not info.isreg():
                    continue
                digest = hashlib.sha256()
                reader = tar.extractfile(info)
                for piece in iter(lambda: reader.read(PIECE), b""):
                    digest.update(piece)
                found[info.name] = (info.size, "sha256:" + digest.hexdigest())
    except (tarfile.TarError, OSError, EOFError, gzip.BadGzipFile) as e:
        raise ArchiveError(f"{file}: not a package hpm can read ({type(e).__name__}: {e})") \
            from None
    return found


def read_member(file: Path | str, name: str, limit: int = 1024 * 1024) -> bytes | None:
    """One small file of a .hpm file, such as its CHANGELOG.md; None if it has none."""
    file = Path(file)
    try:
        with tarfile.open(file, mode="r:gz") as tar:
            for info in tar:
                if info.name == name and info.isreg():
                    if info.size > limit:
                        raise ArchiveError(f"{file}: {name} is bigger than {limit} bytes")
                    return tar.extractfile(info).read()
    except (tarfile.TarError, OSError, EOFError, gzip.BadGzipFile) as e:
        raise ArchiveError(f"{file}: not a package hpm can read ({type(e).__name__}: {e})") \
            from None
    return None
