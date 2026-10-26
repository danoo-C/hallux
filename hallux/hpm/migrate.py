"""Migrations: when an app changes how it stores its data (docs/hpm/migrations.md; the plan's
decisions 6 to 9 and step 7).

A package whose data_format is higher than the world's brings notes, migrations/<a>-to-<b>.md,
for the AI to follow. hpm reads two things out of a note, its "Old paths" line and its
"Checks" list; the rest is for the AI. One package's migration is, for each note in turn:

1. a plan: the AI reads the note and the files, writes nothing, and says what becomes what;
2. the migration: the AI writes the new files by their machine paths, and they land in a
   staging folder (the StagingDisk), never in the world. Files that move unchanged it copies
   with the copy tool: Hallux copies the bytes.

Then the checks (Hallux's own, then the note's, which the AI reports), and the user's
accept: the staged files land, the old paths go, and the record says the new format. All
of it after a backup, which the install that follows adds to: one rollback brings back the
old data and the old version together.

Data coming in, a data package in an older format than its app, is migrated the same way
in a temporary folder laid out as a world, with the app's notes, and installed from there.
"""
from __future__ import annotations

import dataclasses
import errno
import json
import os
import posixpath
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from hallux.disk import HIDDEN_NAME, Disk, copy_whole, write_whole
from hallux.hpm import ai
from hallux.hpm import record as rec
from hallux.hpm.archive import listing, read_member, sha256, to_member
from hallux.hpm.manifest import Manifest, check_path, check_pattern, match, place
from hallux.hpm.store import Release, Store
from hallux.hpm.world import MANIFESTS, HpmError

FOLDER = "migrations"
STAGING = "staging"                       # in .hallux/hpm: a folder per migration
NOTE_NAME = re.compile(r"([1-9][0-9]{0,3})-to-([1-9][0-9]{0,3})\.md")
NOTE_MAX = 64 * 1024
FILES_MAX = 10_000                        # what one migration may stage
BYTES_MAX = 512 * 1024 * 1024
SHOWN = 40                                # rows and files shown on one screen


# ---------------------------------------------------------------------- the notes

@dataclass(frozen=True)
class Note:
    """One migration note: from data format `old` to `new`."""
    name: str                             # "1-to-2.md"
    old: int
    new: int
    text: str
    old_paths: tuple[str, ...]            # machine paths or patterns: "~/.kittystory/chars/"
    checks: tuple[str, ...]


def read_note(name: str, text: str) -> Note:
    """A note, checked: its name says the formats, it has an "Old paths" line (its value may
    be "none") whose paths are machine paths, and its checks are a list. HpmError otherwise."""
    shown = f"{FOLDER}/{name}"
    found = NOTE_NAME.fullmatch(name)
    if not found:
        raise HpmError(f"{shown}: a note is named <from>-to-<to>.md, like 1-to-2.md")
    old, new = int(found[1]), int(found[2])
    if new <= old:
        raise HpmError(f"{shown} goes from format {old} to {new}: a migration only goes up")
    if len(text.encode("utf-8")) > NOTE_MAX:
        raise HpmError(f"{shown} is bigger than {NOTE_MAX // 1024} KB")
    line = re.search(r"^Old paths\b[^:\n]*:[ \t]*(.*)$", text, re.M | re.I)
    if line is None:
        raise HpmError(f"{shown} has no line 'Old paths…: ~/…', the paths that go once the "
                       f"user accepts (or 'Old paths: none'; docs/hpm/migrations.md, section 3)")
    value = line[1].strip()
    paths = [] if value.lower() in ("none", "-", "") else [
        p.strip("`") for p in re.split(r"[,\s]+", value) if p.strip("`")]
    for path in paths:
        problem = _old_path_problem(path)
        if problem:
            raise HpmError(f"{shown}: the old path {path!r} {problem}")
    return Note(name, old, new, text, tuple(paths), _checks(text))


def _old_path_problem(path: str) -> str | None:
    bare = {"": "/", "~": "~/"}.get(path.rstrip("/"), path.rstrip("/"))
    try:
        (check_pattern if "*" in bare else check_path)(bare)
    except ValueError as e:
        return str(e).replace(repr(bare[:60]), "").strip() or "isn't a machine path"
    names = bare.lstrip("~").strip("/").split("/")
    if not bare.startswith("~/") and len(names) < 2:
        return "is a whole top folder of the machine"
    if names[0] == HIDDEN_NAME or "*" in names[0]:
        return "isn't a place a package's data can be"
    return None


def _checks(text: str) -> tuple[str, ...]:
    """The list under a line "Checks:", up to the first line that isn't one of its items."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.fullmatch(r"\s*Checks:\s*", line)), None)
    if start is None:
        return ()
    out: list[str] = []
    for line in lines[start + 1:]:
        if re.match(r"\s*[-*]\s+", line):
            out.append(re.sub(r"^\s*[-*]\s+", "", line).strip())
        elif line.strip() and out and line.startswith(("  ", "\t")):
            out[-1] += " " + line.strip()             # an item that goes on to the next line
        elif line.strip() or out:
            break
    return tuple(out)


def release_notes(release: Release) -> list[Note]:
    """The notes a release carries."""
    out = []
    for member in sorted(listing(release.path)):
        if member.startswith(f"{FOLDER}/") and member.count("/") == 1:
            data = read_member(release.path, member) or b""
            out.append(read_note(member.split("/", 1)[1], data.decode("utf-8", "replace")))
    return out


def world_notes(disk: Disk, name: str) -> list[Note]:
    """The notes a world keeps for a package, in /usr/local/share/hpm/<name>/migrations/."""
    try:
        folder = disk.real(f"{MANIFESTS}/{name}/{FOLDER}")
    except OSError:
        return []
    if not folder.is_dir():
        return []
    return [read_note(p.name, p.read_text(encoding="utf-8", errors="replace"))
            for p in sorted(folder.iterdir()) if p.is_file() and not p.is_symlink()
            and p.suffix == ".md"]


def chain(notes: list[Note], start: int, end: int, what: str) -> list[Note]:
    """The notes that take data from format `start` to `end`, in order: from each format,
    the note that goes furthest without passing `end`. HpmError names the first missing one."""
    out, at = [], start
    while at < end:
        step = max((n for n in notes if n.old == at and n.new <= end), key=lambda n: n.new,
                   default=None)
        if step is None:
            raise HpmError(f"{what} has no migration from data format {at} "
                           f"({FOLDER}/{at}-to-{at + 1}.md), so data in format {at} can't "
                           f"come to {end}")
        out.append(step)
        at = step.new
    return out


# ---------------------------------------------------------------------- paths

def machine_of(path: str, home: str | None) -> str:
    """A placed path as a package names it: "/home/danika/.x" -> "~/.x"."""
    if home and path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


def placed(path: str, home: str | None) -> str:
    if path.startswith("~/"):
        if home is None:
            raise HpmError(f"{path}: this world has no user home for ~")
        return place(path, home)
    return path


def under(old: str, machine: str) -> bool:
    """Is a machine path one of an old path's files: the path, or in its folder?"""
    base = old.rstrip("/")
    if "*" in base:
        return match(base, machine) or match(base + "/**", machine)
    return machine == base or machine.startswith(base + "/")


def files_under(disk: Disk, paths, home: str | None) -> list[str]:
    """The placed paths of the files a world has under these old paths (no links, nothing
    under /.hallux)."""
    found: set[str] = set()
    for old in paths:
        bare = old.rstrip("/")
        fixed = bare.split("*")[0].rsplit("/", 1)[0] if "*" in bare else bare
        try:
            top = disk.real(placed(fixed or "/", home), follow=False)
        except (OSError, HpmError):
            continue
        if top.is_symlink():
            continue
        if top.is_file():
            candidates = [top]
        elif top.is_dir():
            candidates = []
            for dirpath, dirnames, filenames in os.walk(top):     # never into a linked folder
                if Path(dirpath) == disk.root:
                    dirnames[:] = [d for d in dirnames if d != HIDDEN_NAME]
                candidates += [Path(dirpath) / name for name in filenames]
        else:
            continue
        for real in candidates:
            if real.is_symlink() or not real.is_file():
                continue
            path = "/" + real.relative_to(disk.root).as_posix()
            if under(old, machine_of(path, home)):
                found.add(path)
    return sorted(found)


def data_files(disk: Disk, manifest: Manifest | None, home: str | None) -> list[str]:
    """The placed paths of the files a manifest's data patterns match in a world."""
    if manifest is None:
        return []
    from hallux.hpm.world import _matching
    out: set[str] = set()
    for pattern in manifest.files["data"]:
        for path in _matching(disk, pattern, home, set()):
            out.add(placed(path, home))
    return sorted(out)


# ---------------------------------------------------------------------- the staging disk

def _refused(code: int, path: str) -> OSError:
    return OSError(code, os.strerror(code), path)


class StagingDisk:
    """The disk a migration's AI works on: the world as it is, read-only, and a staging folder
    on top of it. A write goes into the folder under the world path it names
    (staging/<time>/home/<user>/.kittystory/characters/emma.toml), and only if `may_write`
    allows the path: the package's data paths. A read takes the staged file if there is one,
    and the world's otherwise. Nothing is ever removed. The world's Disk refuses all under
    /.hallux, where the folder is, so this is a disk of its own, as a job's JobDisk is.
    A path may start with ~/, the user's home, as the notes write them."""

    def __init__(self, disk: Disk, folder: Path, may_write: Callable[[str], bool],
                 home: str | None = None) -> None:
        self.disk, self.folder, self.may_write, self.home = disk, Path(folder), may_write, home
        self.folder.mkdir(parents=True, exist_ok=True)
        self.staged = Disk(self.folder)
        self.cwd = "/"
        self.sizes: dict[str, int] = {}               # world path: bytes staged
        self.copied: dict[str, str] = {}              # world path: the path it was copied from
        self.by: dict[str, int] = {}                  # world path: the note that wrote it last
        self.note = 0                                 # the note being followed

    def virtual(self, path: str) -> str:
        if self.home and (path == "~" or path.startswith("~/")):
            path = self.home + path[1:]
        return self.disk.virtual(path)

    def real(self, path: str) -> Path:
        """Where a staged file is."""
        return self.folder / self.virtual(path).lstrip("/")

    # reading
    def list_dir(self, path: str = ".") -> list[dict]:
        virtual = self.virtual(path)
        entries, found = {}, False
        try:
            entries = {e["name"]: e for e in self.disk.list_dir(virtual)}
            found = True
        except FileNotFoundError:
            pass
        try:
            for entry in self.staged.list_dir(virtual):
                entries[entry["name"]] = entries.get(entry["name"], entry) | {
                    "size": entry["size"], "mtime": entry["mtime"]}
                found = True
        except (FileNotFoundError, NotADirectoryError):
            pass
        if not found:
            raise _refused(errno.ENOENT, virtual)
        return [entries[name] for name in sorted(entries)]

    def stat(self, path: str) -> dict:
        virtual = self.virtual(path)
        if virtual in self.sizes or self.real(virtual).is_dir():
            return self.staged.stat(virtual)
        return self.disk.stat(virtual)

    def read_file(self, path: str, offset: int = 0) -> dict:
        virtual = self.virtual(path)
        holder = self.staged if virtual in self.sizes else self.disk
        return holder.read_file(virtual, offset)

    def read_text(self, path: str, limit: int | None = None) -> str:
        virtual = self.virtual(path)
        holder = self.staged if virtual in self.sizes else self.disk
        return holder.read_text(virtual) if limit is None else holder.read_text(virtual, limit)

    def find(self, path: str = ".", pattern: str = "*") -> dict:
        virtual = self.virtual(path)
        entries: dict[str, dict] = {}
        truncated, found = False, False
        for holder in (self.disk, self.staged):
            try:
                got = holder.find(virtual, pattern)
            except (FileNotFoundError, NotADirectoryError):
                continue
            found = True
            truncated |= got["truncated"]
            for entry in got["entries"]:
                entries.setdefault(entry["path"], entry)
        if not found:
            raise _refused(errno.ENOENT, virtual)
        return {"entries": [entries[p] for p in sorted(entries)], "truncated": truncated}

    # writing
    def _target(self, path: str, size: int) -> tuple[str, Path]:
        virtual = self.virtual(path)
        world = self.disk.place(virtual)              # refuses /.hallux, and links out of it
        if not self.may_write(virtual):
            raise _refused(errno.EACCES, virtual)
        if world.is_dir() and not world.is_symlink():
            raise _refused(errno.EISDIR, virtual)
        real = self.staged.place(virtual)
        if real.is_dir():
            raise _refused(errno.EISDIR, virtual)
        files = len(self.sizes) + (virtual not in self.sizes)
        held = sum(n for p, n in self.sizes.items() if p != virtual) + size
        if files > FILES_MAX or held > BYTES_MAX:
            raise _refused(errno.EDQUOT, virtual)
        real.parent.mkdir(parents=True, exist_ok=True)
        return virtual, real

    def write_file(self, path: str, content: str, append: bool = False,
                   parents: bool = True) -> dict:
        data = content.encode("utf-8")
        if append:
            data = self._bytes(path) + data
        virtual, real = self._target(path, len(data))
        write_whole(real, data)
        self._staged(virtual, len(data))
        self.copied.pop(virtual, None)
        return {"ok": True, "size": len(data)}

    def copy(self, source: str, target: str) -> dict:
        """Copy a file's bytes, the staged one or the world's, to a staged path."""
        origin = self._source(source)
        virtual, real = self._target(target, origin.stat().st_size)
        if origin == real:
            raise _refused(errno.EINVAL, virtual)
        copy_whole(origin, real)
        self._staged(virtual, real.stat().st_size)
        self.copied[virtual] = self.virtual(source)
        return {"ok": True, "size": self.sizes[virtual]}

    def _source(self, path: str) -> Path:
        virtual = self.virtual(path)
        if virtual in self.sizes:
            return self.real(virtual)
        real = self.disk.real(virtual)
        if real.is_dir():
            raise _refused(errno.EISDIR, virtual)
        if not real.is_file():
            raise _refused(errno.ENOENT, virtual)
        return real

    def _bytes(self, path: str) -> bytes:
        try:
            return self._source(path).read_bytes()
        except FileNotFoundError:
            return b""

    def _staged(self, virtual: str, size: int) -> None:
        self.sizes[virtual] = size
        self.by[virtual] = self.note

    # what it holds
    def files(self) -> list[str]:
        return sorted(self.sizes)

    def copy_problems(self) -> list[str]:
        """Each file made with copy that isn't its source byte for byte any more."""
        out = []
        for target, source in sorted(self.copied.items()):
            try:
                same = sha256(self.real(target)) == sha256(self._source(source))
            except OSError:
                same = False
            if not same:
                out.append(f"{target} isn't {source} byte for byte")
        return out

    def drop(self) -> None:
        shutil.rmtree(self.folder, ignore_errors=True)


# ---------------------------------------------------------------------- what the AI says

@dataclass(frozen=True)
class Row:
    """One line of a migration's plan: what becomes what."""
    what: str
    old: tuple[str, ...]
    new: tuple[str, ...]


@dataclass(frozen=True)
class Check:
    text: str
    held: bool
    why: str = ""
    by: str = "hallux"                    # or "the AI": one of the note's own checks


def last_json(text: str) -> dict | None:
    """The JSON object an answer ends with, in a fence or not."""
    for chunk in reversed(re.findall(r"```(?:json)?[ \t]*\n(.*?)\n[ \t]*```", text, re.S)):
        try:
            found = json.loads(chunk)
        except ValueError:
            continue
        if isinstance(found, dict):
            return found
    end = text.rfind("}")
    start = text.find("{")
    while 0 <= start < end:
        try:
            found = json.loads(text[start:end + 1])
        except ValueError:
            start = text.find("{", start + 1)
            continue
        return found if isinstance(found, dict) else None
    return None


def _strings(value: object) -> tuple[str, ...] | None:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return tuple(value)
    return None


# ---------------------------------------------------------------------- one package's migration

PLANNING, PLANNED, MIGRATED, ACCEPTED, CANCELLED = (
    "planning", "planned", "migrated", "accepted", "cancelled")


class Shared:
    """The backup of one update, made by its first migration, added to by the others and by
    the install after them."""

    def __init__(self) -> None:
        self.backup: rec.Backup | None = None


class Migration:
    """One package's data, from the format it is in to the one its package needs: its notes
    one after the other, staged, then the checks, then accept or cancel.

    For the world (`incoming` False): the world's own data, after a backup into `shared`;
    the staging folder is in /.hallux/hpm/staging/. For data coming in: a data package's
    files, laid out as a world in the plan's temporary folder, staged beside them."""

    def __init__(self, plan, item, store: Store, *, incoming: bool = False,
                 shared: Shared | None = None, client_factory=None) -> None:
        pending = item.incoming if incoming else item.migrate
        if pending is None:
            raise HpmError(f"{item.name} has no migration to run")
        self.plan, self.item, self.store = plan, item, store
        self.name, self.incoming = item.name, incoming
        self.notes: list[Note] = list(pending.notes)
        self.layout: Manifest = pending.layout        # whose data patterns the new files are
        self.home = plan.home
        self.world = plan.disk.root
        self.client_factory = client_factory
        self.settings = ai.settings(store)
        self.shared = shared or Shared()
        self.index = 0
        self.rows: list[Row] = []                     # the plan of the note being followed
        self.planned: list[Row] = []                  # the rows of every note so far
        self.ai_checks: list[Check] = []
        self.checks: list[Check] = []
        self.spent = 0.0
        self.state = PLANNING
        self.landed = self.removed = 0
        stamp = rec.now().replace(":", "-")
        if incoming:
            temp = Path(plan.temp.name)
            self.disk = Disk(self._lay_out(temp / f"{item.name}-world"))
            folder = temp / f"{item.name}-staging"
        else:
            self.disk = plan.disk
            folder = rec.hpm_folder(plan.disk) / STAGING / f"{stamp}-{item.name}"
            self._back_up()
        self.stage = StagingDisk(self.disk, folder, self.may_write, self.home)

    @property
    def start(self) -> int:
        return self.notes[0].old

    @property
    def end(self) -> int:
        return self.notes[-1].new

    @property
    def note(self) -> Note:
        return self.notes[self.index]

    def may_write(self, path: str) -> bool:
        """Only under the data paths of the new layout."""
        return self.layout.kind_of(machine_of(path, self.home)) == "data"

    # ------------------------------------------------------------------ the backup

    def _paths(self) -> list[str]:
        """Every file under the old and the new data paths, in the world as it is now."""
        old = [p for note in self.notes for p in note.old_paths]
        return sorted(set(files_under(self.disk, old, self.home))
                      | set(data_files(self.disk, self.layout, self.home))
                      | set(data_files(self.disk, self.item.manifest, self.home)))

    def _back_up(self) -> None:
        record = rec.load(self.disk)
        files = {path: self.name for path in self._paths()}
        entry = {self.name: record.get(self.name)}
        memory = {self.name: {"untagged": None}}
        if self.shared.backup is None:
            self.shared.backup = rec.make_backup(self.disk, self.name, files, entry, memory)
        else:
            rec.extend_backup(self.disk, self.shared.backup, files, entry, memory)

    def _lay_out(self, into: Path) -> Path:
        """The data package's files as a world: files/root/ at /, files/home/ at the home."""
        from hallux.hpm.assist import _as_world
        _as_world(Path(self.plan.temp.name) / self.item.name, into, self.home or "/home/user")
        return into

    # ------------------------------------------------------------------ the AI's two parts

    def _head(self) -> list[str]:
        note = self.note
        release = self.item.release
        lines = [f"The package is {self.name}" + (f" {release.version}" if release else "") + "."]
        if self.incoming:
            lines.append(f"Its files are coming into a world whose {self.item.manifest.for_app} "
                         f"keeps its data in format {self.end}; they are in format "
                         f"{self.start}. They are laid out here as a world of their own.")
        else:
            lines.append(f"The world's data is in format {self.start}; {self.name} needs "
                         f"{self.end}.")
        if len(self.notes) > 1:
            lines.append(f"This is note {self.index + 1} of {len(self.notes)}, "
                         f"{note.old} → {note.new}; what the notes before it wrote is "
                         f"staged, and you read it back as written.")
        lines += [f"~ is {self.home}." if self.home else "There is no user home here.", "",
                  f"The note, migrations/{note.name}:", "<<<", note.text.rstrip(), ">>>", ""]
        return lines

    def plan_rows(self) -> list[Row]:
        """The AI's plan for the note being followed: it reads, writes nothing, and says what
        becomes what. A plan hpm can't read is shown to the AI once more; then an HpmError."""
        lines = self._head() + [
            "Now the plan: read the note and the files it speaks of, write nothing, and say "
            "what you will do. End your answer with this JSON:",
            '{"rows": [{"what": "Emma", "old": ["~/.kittystory/chars/Emma/"], '
            '"new": ["~/.kittystory/characters/emma.toml", "~/.kittystory/memories/emma.md"]}]}',
            "One row for each thing the note moves (a character, a song…); \"new\" is every "
            "file you will write for it, by its path with ~/. A world with nothing to move has "
            "no rows."]
        job = ai.Job("migrate", "\n".join(lines), disk=self.stage, writes=False)
        rows: list[Row] = []

        def follow(answer: ai.Answer) -> str | None:
            nonlocal rows
            rows, problems = self._rows(answer.text)
            if not problems:
                return None
            return ("hpm couldn't take that plan: " + "; ".join(problems)
                    + ". Answer again, ending with the JSON.")

        answer = self._run(job, follow)
        rows, problems = self._rows(answer.text)
        if problems:
            raise HpmError(f"the AI's plan for {self.note.name} can't be used: "
                           + "; ".join(problems))
        self.rows, self.state = rows, PLANNED
        return rows

    def _rows(self, text: str) -> tuple[list[Row], list[str]]:
        found = last_json(text)
        if found is None or not isinstance(found.get("rows"), list):
            return [], ['the answer has no JSON object with "rows" at its end']
        rows, problems = [], []
        for i, row in enumerate(found["rows"]):
            what = row.get("what") if isinstance(row, dict) else None
            old = _strings(row.get("old", [])) if isinstance(row, dict) else None
            new = _strings(row.get("new", [])) if isinstance(row, dict) else None
            if not isinstance(what, str) or old is None or new is None:
                problems.append(f"row {i + 1} isn't {{\"what\": text, \"old\": [paths], "
                                f"\"new\": [paths]}}")
                continue
            for path in new:
                try:
                    if not self.may_write(placed(check_path(path), self.home)):
                        problems.append(f"{path} is outside {self.name}'s data paths "
                                        f"({', '.join(self.layout.files['data']) or 'none'})")
                except (ValueError, HpmError) as e:
                    problems.append(f"{path}: {e}")
            rows.append(Row(what, old, new))
        return rows, problems

    def migrate(self) -> list[Check]:
        """The AI follows the note into the staging folder, then reports the note's checks.
        After the last note, the checks of the whole migration; else the next note's plan
        is the next step."""
        note = self.note
        self.stage.note = self.index
        plan = json.dumps({"rows": [dataclasses.asdict(r) for r in self.rows]}, indent=1)
        lines = self._head() + [
            "The plan you made, which the user accepted:", plan, "",
            "Now migrate: write every file of the plan by its machine path. What you write "
            "lands in a staging folder, not in the world, until the user accepts; a file you "
            "wrote reads back as you wrote it. For a file that moves unchanged use copy: "
            "Hallux copies its bytes. You may write only under these data paths: "
            + (", ".join(self.layout.files["data"]) or "none") + ". You can't remove "
            "anything: the old paths go when the user accepts.",
            "", "Then go through the note's checks, each against what you wrote and the old "
            "files, and end your answer with this JSON:",
            '{"checks": [{"check": "the check, as the note says it", "held": true, '
            '"why": "3 of 3 folders"}]}']
        if not note.checks:
            lines.append('The note has no checks: end with {"checks": []}.')
        job = ai.Job("migrate", "\n".join(lines), disk=self.stage, may_write=self.may_write,
                     copy=True)

        def follow(answer: ai.Answer) -> str | None:
            found = last_json(answer.text)
            if found is not None and isinstance(found.get("checks"), list):
                return None
            return 'hpm found no JSON with "checks" at the end of your answer: answer again ' \
                   'with the checks, ending with the JSON. Write nothing more.'

        answer = self._run(job, follow)
        self.ai_checks += self._reported(answer.text, note)
        self.planned += self.rows
        self.index += 1
        if self.index < len(self.notes):
            self.state = PLANNING
            return []
        self.checks = self.check()
        self.state = MIGRATED
        return self.checks

    def _reported(self, text: str, note: Note) -> list[Check]:
        found = last_json(text) or {}
        said = found.get("checks") if isinstance(found.get("checks"), list) else []
        out, seen = [], set()
        for entry in said:
            if not isinstance(entry, dict) or not isinstance(entry.get("check"), str):
                continue
            seen.add(entry["check"].strip())
            out.append(Check(entry["check"].strip(), entry.get("held") is True,
                             str(entry.get("why", "")), "the AI"))
        for check in note.checks:
            if check.strip() not in seen and not any(check.strip() in s or s in check.strip()
                                                     for s in seen):
                out.append(Check(check, False, "the AI didn't report it", "the AI"))
        return out

    def _run(self, job: ai.Job, follow) -> ai.Answer:
        answer = ai.run_job(self.world, job, self.settings, self.client_factory, follow=follow)
        self.spent += answer.cost_usd
        if not answer.ok:
            raise HpmError(f"the AI's migration of {self.name} ({self.note.name}) didn't end "
                           f"well: {answer.why}")
        return answer

    # ------------------------------------------------------------------ the checks

    def check(self) -> list[Check]:
        """Hallux's own checks, then the AI's report of the note's."""
        out = []
        named = sorted({placed(p, self.home) for row in self.planned for p in row.new})
        missing = [machine_of(p, self.home) for p in named if p not in self.stage.sizes]
        out.append(Check("every file the plan named is staged", not missing,
                         f"missing: {', '.join(missing[:5])}" + (" …" if len(missing) > 5 else "")
                         if missing else f"{len(named)} of {len(named)}"))
        if not self.incoming:
            changed = self._changed_since_backup()
            out.append(Check("the world's old files are as they were at the backup", not changed,
                             f"changed since: {', '.join(changed[:5])}" if changed else ""))
        wrong = self.stage.copy_problems()
        copies = len(self.stage.copied)
        out.append(Check("every file made with copy is its source byte for byte", not wrong,
                         "; ".join(wrong[:3]) if wrong else f"{copies} of {copies}"))
        return out + self.ai_checks

    def _changed_since_backup(self) -> list[str]:
        backup = self.shared.backup
        if backup is None:
            return []
        listed = {p: info for p, info in backup.data["files"].items()
                  if info["package"] == self.name}
        out = []
        for path in self._paths():
            info = listed.get(path)
            if info is None or info["was"] != "there":
                out.append(machine_of(path, self.home))
            elif sha256(backup.folder / "files" / path.lstrip("/")) != sha256(
                    self.disk.root / path.lstrip("/")):
                out.append(machine_of(path, self.home))
        out += [machine_of(p, self.home) for p, info in listed.items()
                if info["was"] == "there" and not (self.disk.root / p.lstrip("/")).is_file()]
        return sorted(set(out))

    @property
    def held(self) -> bool:
        return all(c.held for c in self.checks)

    # ------------------------------------------------------------------ what is shown

    def landing(self) -> list[str]:
        """The staged files that land: not those under the old paths of a later note, which
        were a step on the way."""
        out = []
        for path in self.stage.files():
            later = [p for note in self.notes[self.stage.by[path] + 1:] for p in note.old_paths]
            if not any(under(p, machine_of(path, self.home)) for p in later):
                out.append(path)
        return out

    def old_files(self) -> tuple[list[str], list[str]]:
        """The files that go at accept, and those that stay because another package holds
        them."""
        record = rec.load(self.disk) if not self.incoming else {}
        lands = set(self.landing())
        old = [p for note in self.notes for p in note.old_paths]
        going, kept = [], []
        for path in files_under(self.disk, old, self.home):
            if path in lands:
                continue
            (kept if rec.owner(record, path, but=self.name) else going).append(path)
        return going, kept

    def plan_lines(self) -> list[str]:
        """The plan, as the terminal and the tab show it."""
        note = self.note
        lines = [f"{self.name} data {note.old} → {note.new}"
                 + (f" (note {self.index + 1} of {len(self.notes)})" if len(self.notes) > 1 else "")
                 + (" · the data coming in" if self.incoming else ""), ""]
        if not self.rows:
            lines.append("  nothing to move: only the format changes")
        paths = [p for row in self.rows for p in row.old + row.new]
        common = _common(paths)
        width = min(16, max((len(r.what) for r in self.rows), default=0))
        for row in self.rows[:SHOWN]:
            old = " · ".join(_short(p, common) for p in row.old) or "–"
            new = " · ".join(_short(p, common) for p in row.new) or "–"
            lines.append(f"  {row.what[:16]:<{width}}  {old} → {new}")
        if len(self.rows) > SHOWN:
            lines.append(f"  … and {len(self.rows) - SHOWN} more")
        if common:
            lines.append(f"  (in {common}/)")
        return lines

    def checked_lines(self) -> list[str]:
        written = len(self.stage.files()) - len(self.stage.copied)
        held = sum(1 for c in self.checks if c.held)
        sign = "✓" if self.held else "✗"
        lines = [f"{sign} {self.name}: {len(self.stage.files())} files staged ({written} written, "
                 f"{len(self.stage.copied)} copied) · {held} of {len(self.checks)} checks held"
                 + (f" · the AI's part ~${self.spent:.4f}" if self.spent else ""), ""]
        for check in self.checks:
            why = f": {check.why}" if check.why else ""
            lines.append(f"  {'✓' if check.held else '✗'} {check.text}{why}"
                         + ("  (the AI)" if check.by != "hallux" else ""))
        going, kept = self.old_files()
        if going:
            lines += ["", f"  accept removes {len(going)} old file(s): "
                          + ", ".join(sorted({_top(machine_of(p, self.home), self.notes)
                                              for p in going}))]
        if kept:
            lines.append(f"  {len(kept)} old file(s) stay: another package holds them")
        return lines

    def look_lines(self) -> list[str]:
        """The staged files, to look at before accepting."""
        lines = []
        for path in self.stage.files():
            size = self.stage.sizes[path]
            source = self.stage.copied.get(path)
            how = f"copy of {machine_of(source, self.home)}" if source else f"{size} bytes"
            lines.append(f"── {machine_of(path, self.home)}  ({how})")
            if source:
                continue
            try:
                text = self.stage.real(path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                lines.append("   (not text)")
                continue
            body = text.splitlines()
            lines += [f"   {line}" for line in body[:20]]
            if len(body) > 20:
                lines.append(f"   … and {len(body) - 20} more lines")
        return lines or ["nothing is staged"]

    # ------------------------------------------------------------------ accept, or not

    def accept(self) -> None:
        """Land the staged files, remove the old paths, and say the new format; then the
        package is walked again, for the install that follows. For data coming in, all of
        it happens in the temporary world, and the package is made again from it."""
        from hallux.hpm import engine
        if self.state != MIGRATED:
            raise HpmError(f"{self.name}'s migration isn't at its end: nothing to accept")
        lands = self.landing()
        going, _ = self.old_files()
        disk = self.disk
        if not self.incoming:                         # for the machine: where its data is now
            self.item.migrated = {
                "from": self.start, "to": self.end,
                "gone": sorted({_top(machine_of(p, self.home), self.notes) for p in going}),
                "into": sorted({posixpath.dirname(machine_of(p, self.home)) + "/" for p in lands})}
        if not self.incoming:                         # anything new under them, backed up too
            rec.extend_backup(disk, self.shared.backup, {p: self.name for p in lands + going},
                              {}, {})
        try:
            for path in lands:
                real = disk.place(path)
                engine._make_folders(disk, real)
                copy_whole(self.stage.real(path), real)
                self.landed += 1
            for path in going:
                disk.place(path).unlink(missing_ok=True)
                engine._remove_empty_folders(disk, path, self.home)
                self.removed += 1
        except OSError as e:
            raise HpmError(f"{self.name}'s migration stopped while it landed "
                           f"({e.strerror or e}): {self.landed} files landed. "
                           + ("" if self.incoming else f"hpm rollback {self.name} puts the "
                                                       f"backup back")) from None
        if self.incoming:
            folder, manifest = self._package_again()
            self.stage.drop()
            self.item.incoming = None
            engine.rewalk(self.plan, self.item, folder, manifest)
        else:
            record = rec.load(disk)
            entry = record.get(self.name)
            if entry is not None:
                for path in going:
                    entry["files"].pop(path, None)
                for path in lands:
                    kind = self.layout.kind_of(machine_of(path, self.home)) or "data"
                    entry["files"][path] = {"kind": kind, "sha256": sha256(disk.root / path.lstrip("/"))}
                entry["data_format"] = self.end
                rec.save(disk, record)
            self.stage.drop()
            self.item.migrate = None
            engine.rewalk(self.plan, self.item)
        self.state = ACCEPTED

    def _package_again(self) -> tuple[Path, Manifest]:
        """The data package made again from its migrated world: its files in the new layout,
        and its manifest with the app's data patterns added, in the new format."""
        source = Path(self.plan.temp.name) / self.item.name
        folder = Path(self.plan.temp.name) / f"{self.item.name}-migrated"
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir()
        for name in ("hpm.toml", "CHANGELOG.md", FOLDER):
            if (source / name).is_dir():
                shutil.copytree(source / name, folder / name)
            elif (source / name).is_file():
                shutil.copy2(source / name, folder / name)
        for dirpath, _, filenames in os.walk(self.disk.root):
            for filename in filenames:
                real = Path(dirpath) / filename
                path = "/" + real.relative_to(self.disk.root).as_posix()
                target = folder / to_member(machine_of(path, self.home))
                target.parent.mkdir(parents=True, exist_ok=True)
                copy_whole(real, target)
        manifest = self.item.manifest
        data = tuple(dict.fromkeys(manifest.files["data"] + self.layout.files["data"]))
        return folder, dataclasses.replace(manifest, data_format=self.end,
                                           files={**manifest.files, "data": data})

    def cancel(self) -> None:
        """Nothing lands: the staging folder goes, and so does the package's part of the
        backup. The world was never touched."""
        self.stage.drop()
        if not self.incoming and self.shared.backup is not None:
            rec.drop_from_backup(self.shared.backup, self.name)
            if not self.shared.backup.data["packages"]:
                self.shared.backup = None
        self.state = CANCELLED


def _common(paths: list[str]) -> str:
    """The folder all these paths are in, if it is deeper than ~ or /."""
    folders = [posixpath.dirname(p.rstrip("/")) for p in paths]
    try:
        common = posixpath.commonpath(folders) if folders else ""
    except ValueError:                            # some under ~/, some under /
        return ""
    return "" if common in ("", "/", "~") else common


def _short(path: str, common: str) -> str:
    return path[len(common) + 1:] if common and path.startswith(common + "/") else path


def _top(path: str, notes: list[Note]) -> str:
    """The old path a file is under, as the note names it."""
    for note in notes:
        for old in note.old_paths:
            if under(old, path):
                return old
    return path


# ---------------------------------------------------------------------- a note at publish

def write_note_job(name: str, old: int, new: int, release: Path, before: Manifest,
                   after: Manifest) -> ai.Job:
    """hpm publish, when the data moved: the AI writes the note from the last release (the
    old layout) and the world (the new one). It may write only that note."""
    target = f"{MANIFESTS}/{name}/{FOLDER}/{old}-to-{new}.md"
    text = "\n".join([
        f"The package is {name}. Its data moved since its last release, so its data format "
        f"goes from {old} to {new}.",
        "", f"Its data before (the last release's manifest): {list(before.files['data'])}",
        f"Its data now (the world's manifest): {list(after.files['data'])}", "",
        "The last release is readable with release_list_dir and release_read_file; the world "
        "with list_dir, read_file and find. The program's card is /usr/local/bin/" + name + ".",
        f"Write the note at {target}, and nothing else."])
    return ai.Job("write-migration", text, may_write=lambda path: path == target,
                  release=release)
