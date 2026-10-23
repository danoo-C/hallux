"""A world, seen by hpm: finding it, its user, and the files a manifest's patterns match
(docs/hpm/hpm.md, sections 5 and 6; the plan's decision 12 and steps 2 and 3).

Everything here reads the world through its Disk, so nothing outside the world's folder and
nothing in its /.hallux can be reached.
"""
from __future__ import annotations

import os
import posixpath
from dataclasses import dataclass
from pathlib import Path

from hallux.disk import HIDDEN_NAME, Disk
from hallux.hpm.manifest import Manifest, match

MANIFESTS = "/usr/local/share/hpm"      # a package's manifest, notes and changelog in a world


class HpmError(Exception):
    """What hpm tells the user and stops on. The message is the whole story."""


# ---------------------------------------------------------------------- finding the world

def find_world(start: Path | str | None = None, given: Path | str | None = None) -> Path:
    """The world to work on: `given` (--world), else the folder `start` (the one you're in)
    and its parents, to the first with a .hallux folder in it, the way git finds its
    repository. A folder without .hallux is no world; your home, or a folder above it, is
    never one (Hallux refuses them too)."""
    if given is not None:
        world = Path(given).expanduser().resolve()
        if not (world / HIDDEN_NAME).is_dir():
            raise HpmError(f"{world} is no Hallux world: it has no {HIDDEN_NAME} folder")
        return _not_home(world)
    here = Path(start if start is not None else os.getcwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / HIDDEN_NAME).is_dir() and not _is_home_or_above(folder):
            return folder
    raise HpmError(f"{here} is in no Hallux world (no folder above it has {HIDDEN_NAME}); "
                   f"name one with --world")


def _is_home_or_above(folder: Path) -> bool:
    home = Path.home().resolve()
    return folder == home or folder in home.parents


def _not_home(world: Path) -> Path:
    if _is_home_or_above(world):
        raise HpmError(f"{world} can't be a world: it is your home, or holds it")
    return world


# ---------------------------------------------------------------------- the world's user

def homes(disk: Disk) -> list[str]:
    """The homes `~` may stand for in this world, best first. From /etc/passwd: the users
    with a uid of 1000 or more and a home under /home. Without any there: the folders
    under /home that aren't empty, or if all are, every one. (Every world gets an empty
    /home/user when it is made, which then doesn't count beside a real home.)"""
    found: list[str] = []
    try:
        real = disk.real("/etc/passwd")
        text = real.read_text(encoding="utf-8", errors="replace") if real.is_file() else ""
    except OSError:
        text = ""
    for line in text.splitlines():
        fields = line.split(":")
        if len(fields) < 3 or not fields[0]:
            continue
        try:
            uid = int(fields[2])
        except ValueError:
            continue
        home = fields[5] if len(fields) > 5 and fields[5] else f"/home/{fields[0]}"
        home = posixpath.normpath(home)
        if 1000 <= uid < 65534 and home.startswith("/home/") and home.count("/") == 2 \
                and home not in found:
            found.append(home)
    if found:
        return found
    try:
        base = disk.real("/home")
        folders = sorted(p for p in base.iterdir() if p.is_dir() and not p.is_symlink())
    except OSError:
        return []
    full = [p for p in folders if any(p.iterdir())]
    return [f"/home/{p.name}" for p in (full or folders)]


def world_user(disk: Disk, user: str | None = None) -> str | None:
    """The home `~` stands for: the one home there is, or the home of `user` (--user).
    None if the world has no home at all. Several and no `user` is an HpmError that lists
    them, for the caller to ask or to tell."""
    found = homes(disk)
    if user is not None:
        for home in found:
            if posixpath.basename(home) == user:
                return home
        raise HpmError(f"this world has no user {user!r}; its users: "
                       f"{', '.join(posixpath.basename(h) for h in found) or 'none'}")
    if len(found) > 1:
        raise HpmError("this world has several users ("
                       + ", ".join(posixpath.basename(h) for h in found)
                       + "); say which with --user")
    return found[0] if found else None


# ---------------------------------------------------------------------- a package's files

@dataclass(frozen=True)
class Collected:
    """The files a manifest's patterns match in a world."""
    files: dict[str, tuple[str, Path]]        # machine path ("~/x" or "/x"): (kind, real file)
    empty: tuple[str, ...] = ()               # patterns that matched nothing
    links: tuple[str, ...] = ()               # machine paths of links a pattern reaches


def manifest_path(name: str) -> str:
    return f"{MANIFESTS}/{name}/hpm.toml"


def read_world_manifest(disk: Disk, name: str) -> tuple[Manifest, str] | None:
    """The manifest a world keeps for a package, and its text; None if it has none."""
    try:
        real = disk.real(manifest_path(name))
    except OSError:
        return None
    if not real.is_file():
        return None
    text = real.read_text(encoding="utf-8")
    return Manifest.load(text), text


def collect(disk: Disk, manifest: Manifest, home: str | None) -> Collected:
    """Every file of the world the manifest's patterns match, with its kind (the narrower
    kind, as Manifest.kind_of says). `home` is where `~` is; without one a `~` pattern
    matches nothing. A link is never collected: it is told, for the caller to refuse."""
    files: dict[str, tuple[str, Path]] = {}
    empty, links = [], set()
    for kind, pattern in manifest.patterns():
        found = _matching(disk, pattern, home, links)
        if not found:
            empty.append(pattern)
        for path, real in found.items():
            files.setdefault(path, (manifest.kind_of(path), real))
    return Collected(dict(sorted(files.items())), tuple(empty), tuple(sorted(links)))


def _matching(disk: Disk, pattern: str, home: str | None, links: set[str]) -> dict[str, Path]:
    tilde = pattern.startswith("~/")
    if tilde and home is None:
        return {}
    placed = (home + pattern[1:]) if tilde else pattern

    def machine(virtual: str) -> str:
        return "~" + virtual[len(home):] if tilde else virtual

    names = placed[1:].split("/")
    fixed = next((i for i, name in enumerate(names) if "*" in name), len(names))
    if fixed == len(names):                       # no wildcard: one file
        return _one(disk, placed, machine(placed), links)
    base = "/" + "/".join(names[:fixed])
    try:
        top = disk.real(base, follow=False)
    except OSError:                               # behind the fence, or under /.hallux
        return {}
    if top.is_symlink():
        links.add(machine(base))
        return {}
    if not top.is_dir():
        return {}
    found: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(top):     # never into a linked folder
        here = Path(dirpath)
        if here == disk.root:
            dirnames[:] = [d for d in dirnames if d != HIDDEN_NAME]
        dirnames.sort()
        for name in sorted(dirnames + filenames):
            real = here / name
            path = machine("/" + real.relative_to(disk.root).as_posix())
            if real.is_symlink():
                if match(pattern, path) or match(pattern, path + "/x"):
                    links.add(path)
                continue
            if name in filenames and real.is_file() and match(pattern, path):
                found[path] = real
    return found


def _one(disk: Disk, virtual: str, path: str, links: set[str]) -> dict[str, Path]:
    try:
        real = disk.real(virtual, follow=False)
    except OSError:
        return {}
    if real.is_symlink():
        links.add(path)
        return {}
    return {path: real} if real.is_file() else {}


# ---------------------------------------------------------------------- a running world

RUNNING = "running"                      # .hallux/running: {"pid": …, "start": …}


def _started(pid: int) -> int | None:
    """When a process started (field 22 of /proc/<pid>/stat, in clock ticks since the boot),
    or None if there is no such process."""
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    try:
        return int(text[text.rindex(")") + 2:].split()[19])   # the fields after the name
    except (ValueError, IndexError):
        return None


def mark_running(root: Path | str) -> dict:
    """Mark the world as running in this process: .hallux/running, with the process's number
    and start time. A mark left by a process that is gone is simply replaced."""
    from hallux.disk import write_whole
    import json
    hidden = Path(root) / HIDDEN_NAME
    hidden.mkdir(parents=True, exist_ok=True)
    mark = {"pid": os.getpid(), "start": _started(os.getpid())}
    write_whole(hidden / RUNNING, json.dumps(mark) + "\n")
    return mark


def unmark_running(root: Path | str, mark: dict) -> None:
    """Take this process's mark away, and only this process's."""
    path = Path(root) / HIDDEN_NAME / RUNNING
    if read_mark(root) == mark:
        path.unlink(missing_ok=True)


def read_mark(root: Path | str) -> dict | None:
    import json
    try:
        mark = json.loads((Path(root) / HIDDEN_NAME / RUNNING).read_text())
    except (OSError, ValueError):
        return None
    return mark if isinstance(mark, dict) and isinstance(mark.get("pid"), int) else None


def running(root: Path | str) -> int | None:
    """The number of the Hallux that runs the world, or None. A mark whose process is gone,
    or whose number another process got later (WSL starts low again after a restart), is
    no Hallux running."""
    mark = read_mark(root)
    if mark is None:
        return None
    started = _started(mark["pid"])
    if started is None or (mark.get("start") is not None and started != mark["start"]):
        return None
    return mark["pid"]


def refuse_running(root: Path | str) -> None:
    pid = running(root)
    if pid is not None:
        raise HpmError(f"this world is running (Hallux, process {pid}): use the Packages tab "
                       f"there (Ctrl+F12), or stop the world first")
