"""What a world remembers of hpm (docs/hpm/hpm.md, sections 8 and 9; the plan's decisions 4
to 6 and step 3): its record, its backups, and the lines hpm owns in its memory.

All of it is in the world's hidden folder, /.hallux, which the machine can't see and the
world's Disk refuses. So it is written here straight under `disk.hidden`, whole
(write_whole, copy_whole), and never through the Disk's file methods. The memory is the one
exception: its lines go through Disk.memory_edit, the Disk's own door into /.hallux.

    .hallux/hpm/installed.json             the record: every package, its files' fingerprints
    .hallux/hpm/backups/<time>-<name>/     one backup: backup.json and files/<path>
"""
from __future__ import annotations

import datetime
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from hallux.disk import Disk, copy_whole, write_whole
from hallux.hpm.world import HpmError

FOLDER = "hpm"
RECORD = "installed.json"
BACKUPS = "backups"
PROGRAMS = "## Invented programs"
RULES = "## Rules (from `hallux ...`)"


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def hpm_folder(disk: Disk) -> Path:
    return disk.hidden / FOLDER


# ---------------------------------------------------------------------- the record

def load(disk: Disk) -> dict:
    """The world's record: {name: entry}. An entry is
    {"version", "from", "installed", "data_format", "extras", "home", "files", "incomplete"},
    and "files" is {placed path: {"kind", "sha256"}}. A record that can't be read is an
    HpmError: hpm never guesses what a world has."""
    path = hpm_folder(disk) / RECORD
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HpmError(f"the world's record {path} can't be read ({e}); hpm won't guess what "
                       f"is installed. Put it right, or move it away to start over") from None
    if not isinstance(data, dict) or not all(isinstance(v, dict) and isinstance(v.get("files"), dict)
                                             for v in data.values()):
        raise HpmError(f"the world's record {path} isn't hpm's: it must map each package to "
                       f"its entry")
    return data


def save(disk: Disk, record: dict) -> None:
    folder = hpm_folder(disk)
    folder.mkdir(parents=True, exist_ok=True)
    write_whole(folder / RECORD, json.dumps(record, indent=1, sort_keys=True) + "\n")


def owner(record: dict, path: str, but: str | None = None) -> str | None:
    """The package whose record holds the placed path, other than `but`."""
    for name, entry in record.items():
        if name != but and path in entry["files"]:
            return name
    return None


# ---------------------------------------------------------------------- the memory

def _tag(name: str, version: str | None = None) -> str:
    return f"[hpm {name} {version}]" if version else f"[hpm {name} "


def _tagged(name: str) -> re.Pattern:
    return re.compile(rf"\[hpm {re.escape(name)} [^\]\s]+\]\s*$")


def _section(lines: list[str], title: str) -> tuple[int, int] | None:
    """Where a section is: the index of its title line, and of the line after its last."""
    starts = [i for i, line in enumerate(lines) if line.rstrip("\n").startswith(title.split(" (")[0])
              and line.startswith("## ")]
    if not starts:
        return None
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1                                  # the blank lines before the next title
    return start, end


def untagged_line(disk: Disk, name: str) -> str | None:
    """An untagged line about the program under "Invented programs", the kind the machine
    writes itself ("- kittystory (was lt-love…): split-screen chat…"); None if there is none."""
    lines = disk.memory_read()["text"].splitlines()
    where = _section([line + "\n" for line in lines], PROGRAMS)
    if where is None:
        return None
    about = re.compile(rf"^\s*(?:[-*]\s+|\d+\.\s+)?{re.escape(name)}(?![A-Za-z0-9-])")
    for line in lines[where[0] + 1:where[1]]:
        if about.match(line) and "[hpm " not in line:
            return line
    return None


def _change_memory(disk: Disk, change) -> None:
    text = disk.memory_read()["text"]
    new = change(text)
    if new != text:
        disk.memory_edit(text, new) if text else disk.memory_edit("", new)


def _put(text: str, title: str, name: str, lines_in: list[str], replace: str | None) -> str:
    """The text with the section's tagged lines of `name` replaced by `lines_in`, and the
    untagged line `replace` taken out; the section made at the end if it isn't there."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    tagged = _tagged(name)
    lines = [line for line in lines if not (tagged.search(line.rstrip("\n"))
                                            or (replace is not None and line.rstrip("\n") == replace))]
    if not lines_in:
        return "".join(lines)
    new = [line + "\n" for line in lines_in]
    where = _section(lines, title)
    if where is None:
        gap = "\n" if lines and lines[-1].strip() else ""
        return "".join(lines) + gap + title + "\n" + "".join(new)
    return "".join(lines[:where[1]] + new + lines[where[1]:])


def set_memory(disk: Disk, name: str, version: str, memory_line: str, rules: tuple[str, ...] = (),
               replace: str | None = None) -> None:
    """The package's lines in the machine's memory: its memory line under "Invented
    programs", its rules under "Rules", each ending in [hpm name version]. Lines of an older
    version are replaced; `replace` is an untagged line about the program to take out. The
    machine's own lines stay as they are."""
    tag = _tag(name, version)

    def change(text: str) -> str:
        line = [f"- {memory_line} {tag}"] if memory_line else []
        text = _put(text, PROGRAMS, name, line, replace)
        if rules:
            numbered = _numbered(text)
            text = _put(text, RULES, name,
                        [f"{numbered + i + 1}. {rule} {tag}" for i, rule in enumerate(rules)], None)
        return text

    _change_memory(disk, change)


def _numbered(text: str) -> int:
    lines = text.splitlines(keepends=True)
    where = _section(lines, RULES)
    if where is None:
        return 0
    return sum(1 for line in lines[where[0] + 1:where[1]] if re.match(r"\s*\d+\.", line))


def remove_memory(disk: Disk, name: str) -> None:
    """Every line hpm wrote for the package, in any section."""
    tagged = _tagged(name)

    def change(text: str) -> str:
        lines = text.splitlines(keepends=True)
        return "".join(line for line in lines if not tagged.search(line.rstrip("\n")))

    _change_memory(disk, change)


def restore_line(disk: Disk, line: str) -> None:
    """Put an untagged line back under "Invented programs", as a rollback does for the old
    line an install replaced."""
    def change(text: str) -> str:
        if line in text.splitlines():
            return text
        lines = text.splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        where = _section(lines, PROGRAMS)
        if where is None:
            gap = "\n" if lines and lines[-1].strip() else ""
            return "".join(lines) + gap + PROGRAMS + "\n" + line + "\n"
        return "".join(lines[:where[1]] + [line + "\n"] + lines[where[1]:])

    _change_memory(disk, change)


def memory_lines(disk: Disk, name: str) -> list[str]:
    tagged = _tagged(name)
    return [line for line in disk.memory_read()["text"].splitlines() if tagged.search(line)]


# ---------------------------------------------------------------------- backups

@dataclass(frozen=True)
class Backup:
    folder: Path
    data: dict                    # backup.json

    @property
    def name(self) -> str:
        return self.folder.name

    def holds(self, package: str) -> bool:
        return package in self.data["packages"] and package not in self.data.get("rolled_back", [])


def make_backup(disk: Disk, label: str, files: dict[str, str], entries: dict[str, dict | None],
                memory: dict[str, list[str]]) -> Backup:
    """A backup, before anything is written: a copy of each placed path in `files` that is
    there (by the package it is for), the record's entries of the packages as they were (None:
    not installed), and their lines in the memory. A path that isn't there is named, so that
    a rollback takes away what the write puts there."""
    base = hpm_folder(disk) / BACKUPS
    base.mkdir(parents=True, exist_ok=True)
    stamp = now().replace(":", "-")
    folder, count = base / f"{stamp}-{label}", 1
    while folder.exists():
        count += 1
        folder = base / f"{stamp}-{label}-{count}"
    folder.mkdir()
    listed = {}
    for path, package in sorted(files.items()):
        real = disk.root / path.lstrip("/")
        if real.is_file() and not real.is_symlink():
            target = folder / "files" / path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_whole(real, target)
            listed[path] = {"package": package, "was": "there"}
        else:
            listed[path] = {"package": package, "was": "missing"}
    data = {"made": now(), "packages": sorted(entries), "files": listed,
            "entries": entries, "memory": memory, "rolled_back": []}
    write_whole(folder / "backup.json", json.dumps(data, indent=1, sort_keys=True) + "\n")
    return Backup(folder, data)


def backups(disk: Disk) -> list[Backup]:
    """Every backup of the world, oldest first."""
    base = hpm_folder(disk) / BACKUPS
    if not base.is_dir():
        return []
    found = []
    for folder in sorted(base.iterdir()):
        try:
            data = json.loads((folder / "backup.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue                              # half made, when a write failed: not one
        found.append(Backup(folder, data))
    return sorted(found, key=lambda b: (b.data.get("made", ""), b.name))


def backups_size(disk: Disk) -> int:
    base = hpm_folder(disk) / BACKUPS
    return sum(p.stat().st_size for p in base.rglob("*") if p.is_file()) if base.is_dir() else 0


def mark_rolled_back(backup: Backup, package: str) -> None:
    backup.data.setdefault("rolled_back", []).append(package)
    write_whole(backup.folder / "backup.json", json.dumps(backup.data, indent=1, sort_keys=True) + "\n")


def clean_backups(disk: Disk) -> int:
    """Remove every backup. Returns how many there were."""
    found = backups(disk)
    shutil.rmtree(hpm_folder(disk) / BACKUPS, ignore_errors=True)
    return len(found)
