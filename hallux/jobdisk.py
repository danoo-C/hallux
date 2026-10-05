"""A job's view of the disk: one folder of the machine, behind a second fence.

The job of an addon agent (docs/addon-agents.md, section 5) sees one folder. It reads all of
it, creates files there, and changes only the files it was given. What it writes goes into
private copies in <root>/.hallux/jobs/<pid>/, a place the machine can't see. Nobody else
sees them, and the real folder stays as it was, until the job ends well and they land.

A JobDisk has the methods of Disk that a job needs, with the same names and the same
answers, so a job's file tools and an addon function's disk handle work on it as they are.
It is used from two threads, the event loop's and an addon function's, and holds what two
threads could trip over: the copies, the counts, and whether it is closed. So every method
takes its one lock.
"""
from __future__ import annotations

import errno
import hashlib
import os
import posixpath
import re
import shutil
import threading
from pathlib import Path
from typing import Sequence

from hallux.disk import EDIT_LIMIT, Disk, replace_once, write_whole

JOBS = "jobs"                                 # in the hidden folder: a folder of copies per job
GIVEN_MAX = 8                                 # files a job may be given to change
FILES_MAX = 16                                # files it may write, the given ones it changed too
BYTES_MAX = 1024 * 1024                       # and what they may hold together
# Files in these are behaviour for the main agent, so no job works in them: every home's
# .bashrc is handed to it at each boot, and /usr/local/bin holds the machine's programs.
HOMES = ("/", "/home", "/root")               # refused themselves, and a folder directly in /home
SYSTEM = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/boot")     # refused with all that is in them
# A name the job makes up: letters, digits, . - and _, and no dot in front, so no .bashrc.
NEW_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")


def refusal(code: int, path: str | None = None) -> OSError:
    """What a JobDisk raises: an errno, as Disk does, and the path of the machine it is about."""
    return OSError(code, os.strerror(code), path)


def sweep(disk: Disk) -> list[str]:
    """Delete the copies of every job, and return the names of their folders, for the log.
    For when Hallux starts: whatever is there then was left by a crash or the hard exit."""
    jobs = disk.hidden / JOBS
    left = sorted(entry.name for entry in jobs.iterdir()) if jobs.is_dir() else []
    for name in left:
        if (jobs / name).is_dir() and not (jobs / name).is_symlink():
            shutil.rmtree(jobs / name)
        else:
            (jobs / name).unlink()
    return left


class JobDisk:
    def __init__(self, disk: Disk, folder: str, edit: Sequence[str] = (), pid: int = 0):
        """Check the folder and the files a job is given. Raises a refusal, with the path."""
        self.disk, self.pid = disk, pid
        self.folder = disk.virtual(folder)            # where a path without a / in front starts
        self.real_folder = self._jailed(folder)       # as it really is, behind every link
        if not self.real_folder.exists():
            raise refusal(errno.ENOENT, self.folder)
        if not self.real_folder.is_dir():
            raise refusal(errno.ENOTDIR, self.folder)
        inside_root = self.real_folder.relative_to(disk.root).as_posix()
        where = "/" if inside_root == "." else f"/{inside_root}"
        if (where in HOMES or posixpath.dirname(where) == "/home"
                or any(where == folder or where.startswith(f"{folder}/") for folder in SYSTEM)):
            raise refusal(errno.EACCES, self.folder)

        self.inside = Disk(self.real_folder)          # the folder's real files, behind its fence
        self.copy_root = disk.hidden / JOBS / str(pid)
        self.copies = Disk(self.copy_root)            # the job's own versions; made when written
        self._sizes: dict[str, int] = {}              # the copies: place in the folder -> bytes
        self._given: dict[str, str] = {}              # place -> what the file held at the start
        self.edit: list[str] = []                     # the given files, as paths of the machine
        self._closed = False
        self._lock = threading.RLock()
        if len(edit) > GIVEN_MAX:
            raise refusal(errno.E2BIG)
        for path in edit:
            self._give(path)

    def _jailed(self, path: str) -> Path:
        """The real place of a path of the machine. What the jail refuses names the path."""
        try:
            return self.disk.real(path)
        except OSError as e:
            raise refusal(e.errno, self.disk.virtual(path)) from None

    def _give(self, path: str) -> None:
        """One file the job may change. It is remembered as it is now, to tell at the landing
        whether someone else changed it meanwhile."""
        real, virtual = self._jailed(path), self.disk.virtual(path)
        if not real.exists():
            raise refusal(errno.ENOENT, virtual)
        if real.is_dir():
            raise refusal(errno.EISDIR, virtual)
        if not real.is_file() or self.real_folder not in real.parents:
            raise refusal(errno.EACCES, virtual)      # no regular file, or outside the folder
        place = real.relative_to(self.real_folder).as_posix()
        if place in self._given:                      # twice, also under a link's second name
            raise refusal(errno.EINVAL, virtual)
        if real.stat().st_size > BYTES_MAX:           # the job could never write it back
            raise refusal(errno.EFBIG, virtual)
        self._given[place] = hashlib.sha256(real.read_bytes()).hexdigest()
        self.edit.append(virtual)

    # ------------------------------------------------------------------ the fence

    def _place(self, path: str) -> str:
        """Where in the job's folder a path of the machine leads, or a refusal. The folder is
        the job's working directory, and never changes. The path goes through the jail as
        always; what it really leads to has to lie inside the folder. That refuses a .. that
        leaves the folder, a path elsewhere, and a link in the folder that points out of it."""
        if self._closed:
            raise refusal(errno.ESTALE)
        virtual = self._virtual(path)
        real = self._jailed(virtual)
        if real != self.real_folder and self.real_folder not in real.parents:
            raise refusal(errno.EACCES, virtual)
        return real.relative_to(self.real_folder).as_posix()      # "." is the folder itself

    def _virtual(self, path: str) -> str:
        return "/" + posixpath.normpath(posixpath.join(self.folder, path)).lstrip("/")

    # ------------------------------------------------------------------ reading

    def list_dir(self, path: str = ".") -> list[dict]:
        with self._lock:
            place = self._place(path)
            entries = {entry["name"]: entry for entry in self.inside.list_dir(place)}
            here = "" if place == "." else place
            for copy in self._sizes:                  # as the job wrote them, and what it created
                if posixpath.dirname(copy) == here:
                    mine = self.copies.stat(copy)
                    entries[mine["name"]] = entries.get(mine["name"], mine) | {
                        "size": mine["size"], "mtime": mine["mtime"]}
            return [entries[name] for name in sorted(entries)]

    def read_file(self, path: str, offset: int = 0) -> dict:
        with self._lock:
            place = self._place(path)
            return self._holder(place).read_file(place, offset)

    def read_text(self, path: str, limit: int = EDIT_LIMIT) -> str:
        with self._lock:
            place = self._place(path)
            return self._holder(place).read_text(place, limit)

    def _holder(self, place: str) -> Disk:
        """Who has the job's version of a file: its copies, or the folder itself."""
        return self.copies if place in self._sizes else self.inside

    # ------------------------------------------------------------------ writing

    def write_file(self, path: str, content: str, append: bool = False) -> dict:
        """As Disk.write_file, into the job's copy. There is no `parents`: a job can't create
        a folder."""
        with self._lock:
            place = self._place(path)
            data = content.encode("utf-8")
            before = self._mine(place)
            if append and before:                     # it starts from the real text
                data = before + data
            self._store(place, data)
            return {"ok": True, "size": len(data)}

    def edit_file(self, path: str, old: str, new: str) -> dict:
        with self._lock:
            place = self._place(path)
            before = self._mine(place)
            if before is None:
                raise refusal(errno.ENOENT, self._virtual(place))
            self._store(place, replace_once(before.decode("utf-8"), old, new).encode("utf-8"))
            return {"ok": True}

    def _mine(self, place: str) -> bytes | None:
        """What the job's version of this file holds: its copy, or the real file if that was
        given and isn't changed yet. None for a name that is free and may be taken. A refusal
        for all else: a file that wasn't given, a folder, a name no job may make."""
        if place in self._sizes:
            return self.copies.real(place).read_bytes()
        real, virtual = self.inside.real(place), self._virtual(place)
        if place in self._given:                      # gone meanwhile: the landing finds that out
            return real.read_bytes() if real.is_file() else b""
        if real.is_dir():
            raise refusal(errno.EISDIR, virtual)
        if real.exists() or real.is_symlink():        # it exists, and the job wasn't given it
            raise refusal(errno.EACCES, virtual)
        if not real.parent.is_dir():                  # a job can't create a folder
            raise refusal(errno.ENOENT, virtual)
        if not NEW_NAME.fullmatch(real.name):
            raise refusal(errno.EACCES, virtual)
        return None

    def _store(self, place: str, data: bytes) -> None:
        """Write the job's copy of a file, whole, if its limits allow."""
        files = len(self._sizes) + (place not in self._sizes)
        held = sum(size for other, size in self._sizes.items() if other != place) + len(data)
        if files > FILES_MAX or held > BYTES_MAX:
            raise refusal(errno.EDQUOT, self._virtual(place))
        copy = self.copies.real(place)                # under the path it has in the folder
        copy.parent.mkdir(parents=True, exist_ok=True)
        write_whole(copy, data)
        self._sizes[place] = len(data)

    # ------------------------------------------------------------------ when the job is over

    def close(self) -> None:
        """Make the disk dead: every later call raises ESTALE. An addon function can't be
        stopped, so one that outlives its job must not read or write through its handle."""
        with self._lock:
            self._closed = True

    def drop(self) -> None:
        """Delete the job's copies."""
        with self._lock:
            shutil.rmtree(self.copy_root, ignore_errors=True)
            self._sizes = {}
