"""Files from the user's computer, dropped into the machine.

A terminal has no message for a drop. It pastes the path of what was dropped, as text
(docs/user-addition/drag-and-drop/). read_drop makes real paths of such a text, or says why
it isn't a drop.

Terminals quote in their own ways, and a Windows path is full of backslashes that are no
escapes. So the text is read in three ways, and what exists on this computer decides which
reading is the right one.

look works out what would be copied, where to, and what is in the way, and writes nothing:
the tree that the panel shows before a copy. A thing that was dropped goes into a directory
of the machine under its own name, and what is in a folder goes under that folder's place.
Every place is asked of the Disk, so none is outside the machine or in /.hallux.

carry_out copies. It goes over what was dropped once more and decides about each thing as
it is at that moment, by the same walk and the same marks as the tree. No file is ever
seen half-copied (disk.copy_whole), and none is replaced that the user wasn't asked about.

Imports is what the machine has of all this, and all that the panel's Files tab knows: one
list of what was dropped, one walk or one copy at a time, each in a thread of its own, and
what there is to show of them.
"""
from __future__ import annotations

import asyncio
import errno
import functools
import logging
import os
import posixpath
import re
import shlex
import socket
import stat
import subprocess
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterator, Sequence
from urllib.parse import unquote, urlsplit

from hallux.disk import Disk, copy_whole

LONGEST = 64 * 1024                           # bytes of a text that can still be a drop
SHOWN = 60                                    # characters of a text that a refusal repeats:
                                              # its last, where a path has its name
MOUNT = "/mnt"                                # where WSL has the Windows drives, as a rule
WSLPATH_SECONDS = 2.0
# What looks like a Windows path: two slashes of either kind in front, or a drive.
WINDOWS = re.compile(r"[\\/]{2}|[A-Za-z]:[\\/]")
# A file of a WSL distribution as Windows names it, \\wsl$\NAME\… and \\wsl.localhost\NAME\…,
# and as VS Code's terminal types it: with the slashes turned and the $ taken out, //wsl/NAME/…
SHARE = re.compile(r"[\\/]{2}wsl(?:\$|\.localhost)?[\\/](?P<name>[^\\/]+)(?P<rest>.*)",
                   re.IGNORECASE | re.DOTALL)
DRIVE = re.compile(r"(?P<letter>[A-Za-z]):[\\/](?P<rest>.*)", re.DOTALL)
# A piece of a pasted text: all between two quotes, or all up to the next space.
PIECE = re.compile(r""""([^"]*)"|'([^']*)'|(\S+)""")

FOLDER_MAX = 50                               # entries a folder lists in the tree
TREE_MAX = 2000                               # lines the tree keeps
TELL_SECONDS = 0.1                            # how often a walk says how far it has come
FOLDER, FILE, LINK, OTHER = "folder", "file", "link", "other"     # what a line of the tree is
MORE = "more"                                 # or what it stands for: the lines that were left out
# The marks of a line. What has one of these five is not copied, with all that is in it:
HERE, IN_THE_WAY, NO_PLACE, UNREADABLE, NOT_COPIED = (
    "is already here", "in the way", "can't go there", "can't be read", "not copied")
SKIPPED = (HERE, IN_THE_WAY, NO_PLACE, UNREADABLE, NOT_COPIED)
EXISTS = "exists"                             # a file is there already: the user is asked
LEADS = "→"                                   # a link in a dropped folder: "→ ../cat.png"
MEANWHILE = "appeared meanwhile"              # a file that is there, and the user wasn't asked
STOPPED, FULL = "stopped", "the disk is full"                     # why a copy ended early
FAILED_MAX = 50                               # failures a copy names; the rest it counts
# The states of the machine's Imports: nothing dropped, the tree is being worked out, it is
# there, the copy runs, the copy is over.
EMPTY, LOOKING, READY, COPYING, DONE = "empty", "looking", "ready", "copying", "done"
CHANGED_SECONDS = 0.1                         # how often a thread asks for the panel to be drawn
CLOSE_SECONDS = 2.0                           # how long Hallux waits at its end for a thread

Translate = Callable[[str], "str | None"]
log = logging.getLogger("hallux")


class NotADrop(ValueError):
    """The text names nothing that could be copied. The message says why, in words for the
    panel's foot."""


def from_windows(text: str) -> str | None:
    """A Windows path as WSL's own wslpath translates it: that knows a drive which is mounted
    somewhere else than /mnt. None when there is no wslpath, as outside WSL, when it refuses
    the path, and when it takes too long."""
    try:
        done = subprocess.run(
            ["wslpath", "-u", text], stdin=subprocess.DEVNULL, capture_output=True,
            timeout=WSLPATH_SECONDS, encoding="utf-8", errors="surrogateescape")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.rstrip("\n") or None


def read_drop(text: str, translate: Translate = from_windows) -> list[Path]:
    """The paths that a dropped text names, as they were dropped: not resolved, each one
    once, in their order. Raises NotADrop.

    The text is read in three ways, and the first in which every path exists is taken: as
    one path; cut at the spaces outside quotes, with a backslash as a character, as Windows
    Terminal and VS Code's terminal send it; and as a shell's words, as most other
    terminals do. `translate` makes a path of this computer of a Windows path that the
    rules here can't find, or None."""
    text = text.strip(" \r\n")
    if not text or "\0" in text or len(text.encode("utf-8", "surrogatepass")) > LONGEST:
        raise NotADrop("not a path")
    translate = functools.cache(translate)            # two readings may name the same path
    lost: list[str] = []                              # Windows paths nothing could translate
    for reading in (_whole, _quoted, _words):
        paths = _paths(reading(text), translate, lost)
        if paths:
            return paths
    if lost:                                          # the shortest: one path, not a whole paste
        raise NotADrop(f"can't be reached from here: {min(lost, key=len)}")
    shown = text if len(text) <= SHOWN else "…" + text[-(SHOWN - 1):]
    raise NotADrop(f"no such file or folder on this computer: {shown}")


# ---------------------------------------------------------------------- the three readings

def _whole(text: str) -> list[str]:
    """One path, whatever is in it. One pair of quotes around it is taken off."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    return [text]


def _quoted(text: str) -> list[str]:
    """Cut at the spaces outside "…" and '…', and after a quote that closes: two drops into
    VS Code's terminal arrive as '/a/Pictures''/a/hallux.hlx'. A backslash is a character.
    So is a quote in the middle of a word, as in O'Brien."""
    return [found[found.lastindex] for found in PIECE.finditer(text)]


def _words(text: str) -> list[str]:
    """As a shell cuts its words: quotes, and a backslash in front of a space."""
    try:
        return shlex.split(text)
    except ValueError:                                # a quote that never closes
        return []


# ---------------------------------------------------------------------- one path

def _paths(pieces: list[str], translate: Translate, lost: list[str]) -> list[Path]:
    """Every piece as a path that exists. Nothing if one of them doesn't: then the text
    wasn't meant to be read this way."""
    paths = []
    for piece in pieces:
        path = _locate(piece, translate, lost)
        if path is None:
            return []
        paths.append(Path(path))
    return list(dict.fromkeys(paths))


def _locate(written: str, translate: Translate, lost: list[str]) -> str | None:
    """The path of this computer that a piece of the text names, or None if nothing is
    there. A Windows path that nothing could translate is noted in `lost`."""
    if written.lower().startswith("file://"):
        written = _from_url(written)
    if WINDOWS.match(written) and not _exists(written):
        found = _translated(written, translate)
        if found is None:
            lost.append(written)
            return None
        written = found
    return written if _exists(written) else None


def _exists(path: str) -> bool:
    """Is something at this path? A link counts, also one that leads nowhere. A path that
    isn't absolute never does: a terminal pastes the whole path, and a bare word like `ls`
    must not be read as a file in Hallux's own directory."""
    return path.startswith("/") and os.path.lexists(path)


def _from_url(url: str) -> str:
    """The path in a file:// address. Nothing for a file of another computer."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    here = parts.netloc.lower() in ("", "localhost", socket.gethostname().lower())
    return unquote(parts.path) if here else ""


def _translated(written: str, translate: Translate) -> str | None:
    """A Windows path as a path of this computer, or None if nothing can translate it. By
    rule where there is one: a drop can hold hundreds of paths, and wslpath takes one at a
    call."""
    share, drive = SHARE.fullmatch(written), DRIVE.fullmatch(written)
    if share and share["name"].lower() == os.environ.get("WSL_DISTRO_NAME", "").lower():
        return share["rest"].replace("\\", "/") or "/"        # wslpath says the same of it
    if drive:
        guess = f"{MOUNT}/{drive['letter'].lower()}/" + drive["rest"].replace("\\", "/")
        if os.path.lexists(guess):
            return guess
    return translate(written)


# ---------------------------------------------------------------------- the tree

@dataclass(frozen=True)
class Line:
    """One line of the tree, as the panel draws it."""
    depth: int                        # 0 for a thing that was dropped itself
    name: str
    kind: str                         # FOLDER, FILE, LINK or OTHER; MORE for "… 6 more"
    size: int = 0                     # bytes: a file's, and of a folder all that is in it
    files: int = 0                    # of a folder: what is in it and is no folder, at any depth
    mark: str = ""                    # one of the marks, "→ " and where a link leads, or nothing


@dataclass(frozen=True)
class Counts:
    """How much was dropped, with all that is in the folders, also what the lines leave out."""
    folders: int = 0
    files: int = 0                    # everything that is no folder
    bytes: int = 0                    # what the files hold
    marks: dict[str, int] = field(default_factory=dict)      # how many have each mark;
                                                             # the links are under LEADS

    @property
    def to_copy(self) -> int:
        """How many of them have no mark that skips them: what a copy would at least try."""
        return self.folders + self.files - sum(self.marks.get(mark, 0) for mark in SKIPPED)


@dataclass(frozen=True)
class Tree:
    """What would be copied into a directory of the machine."""
    into: str                         # the destination, as the machine's path
    lines: tuple[Line, ...] = ()      # top to bottom
    counts: Counts = field(default_factory=Counts)
    refused: str | None = None        # why nothing of it can be copied at all
    stopped: bool = False             # the walk was stopped: there are no lines


@dataclass(frozen=True)
class _Entry:
    """One thing a walk comes to: a thing that was dropped, or one in a dropped folder."""
    source: Path                      # where it is on the user's computer
    where: str                        # its place, as the machine's path,
    place: Path | None                # and as the real one; None where the disk gives none
    depth: int
    name: str
    kind: str
    size: int                         # the bytes of a file
    mark: str                         # LEADS for a link that would be copied
    leads: str                        # and where that link leads, as it is written
    number: int                       # which one it is in its folder, from 0,
    of: int                           # and how many that folder has


@dataclass
class _Open:
    """A folder that a walk is inside of."""
    slot: int | None                  # where its line is in the tree, if it has one
    shown: bool                       # whether what is in it gets lines
    files: int = 0
    bytes: int = 0


def look(disk: Disk, sources: Sequence[Path], into: str,
         stop: threading.Event | None = None,
         tell: Callable[[Counts], None] | None = None) -> Tree:
    """The tree of what would be copied if `sources`, the paths of a drop, went into `into`,
    a directory of the machine. Nothing is written.

    It is made to run in a thread: it looks at `stop` between two entries and returns a tree
    that is `stopped`, and it calls `tell` with the counts so far, some times a second."""
    into = disk.virtual(into)
    refused = _refused(disk, sources, into)
    if refused is not None:
        return Tree(into, refused=refused)
    lines: list[Line] = []
    inside: list[_Open] = []                          # the folders the walk is in, outermost first
    folders = files = held = 0
    marks: dict[str, int] = {}
    told = time.monotonic()

    def add(line: Line) -> int | None:
        """Put a line into the tree, if the tree still takes one. Returns where it is."""
        if len(lines) < TREE_MAX:
            lines.append(line)
            return len(lines) - 1
        if len(lines) == TREE_MAX:
            lines.append(Line(0, "… and more", MORE))
        return None

    def leave(depth: int) -> None:
        """The walk is through with the folders at this depth and below: their lines get
        their sums, and so do the folders they are in."""
        while len(inside) > depth:
            done = inside.pop()
            if inside:
                inside[-1].files += done.files
                inside[-1].bytes += done.bytes
            if done.slot is not None:
                lines[done.slot] = replace(lines[done.slot], size=done.bytes, files=done.files)

    for entry in _walk(disk, sources, into):
        if stop is not None and stop.is_set():
            return Tree(into, counts=Counts(folders, files, held, dict(marks)), stopped=True)
        leave(entry.depth)
        folder = inside[-1] if inside else None       # the one it is in, if it is in one
        if entry.kind == FOLDER:
            folders += 1
        else:
            files, held = files + 1, held + entry.size
            if folder is not None:
                folder.files += 1
                folder.bytes += entry.size
        if entry.mark:
            marks[entry.mark] = marks.get(entry.mark, 0) + 1
        shown = folder is None or folder.shown and entry.number < FOLDER_MAX
        if folder is not None and folder.shown and entry.number == FOLDER_MAX:
            add(Line(entry.depth, f"… {entry.of - FOLDER_MAX} more", MORE))
        mark = f"{LEADS} {entry.leads}" if entry.mark == LEADS else entry.mark
        line = Line(entry.depth, entry.name, entry.kind, entry.size, 0, mark)
        slot = add(line) if shown else None
        if entry.kind == FOLDER:
            inside.append(_Open(slot, shown))
        if tell is not None and time.monotonic() - told >= TELL_SECONDS:
            told = time.monotonic()
            tell(Counts(folders, files, held, dict(marks)))
    leave(0)
    return Tree(into, tuple(lines), Counts(folders, files, held, marks))


def _refused(disk: Disk, sources: Sequence[Path], into: str) -> str | None:
    """Why nothing of a drop can go into this directory of the machine, or None."""
    try:
        folder = disk.real(into)
    except OSError:
        return None                                   # behind the fence: every line says so
    if not folder.is_dir():
        return f"the folder is gone: {into}"
    return _into_itself(sources, folder)


def _into_itself(sources: Sequence[Path], folder: Path) -> str | None:
    """The words for a source that is this real folder, or holds it. None if none does."""
    for source in sources:
        if _holds(source, folder):
            return f"would be copied into itself: {_name(source) or source}"
    return None


def _holds(source: Path, folder: Path) -> bool:
    """Is this real folder the source, or somewhere in it?"""
    real = Path(os.path.realpath(source))
    return real == folder or real in folder.parents


def _name(source: Path) -> str:
    """The name under which a dropped thing arrives: its own. A path that ends in .. has
    none, and then it is the name of what the path leads to. Only / has no name at all."""
    return source.name if source.name not in ("", "..") else Path(os.path.realpath(source)).name


def _walk(disk: Disk, sources: Sequence[Path], into: str) -> Iterator[_Entry]:
    """Everything that was dropped: each thing in front of what is in it, a folder's entries
    by name, as the tree lists them. A thing's mark is worked out when the walk comes to it,
    and not before: who makes a folder on the way finds what is in it marked as it is then.
    What is in a folder with a mark is left out, and no link is followed into a folder."""
    waiting = [(source, _name(source), into, 0, number, len(sources))
               for number, source in reversed(list(enumerate(sources)))]
    while waiting:
        source, name, above, depth, number, of = waiting.pop()
        where = posixpath.join(above, name)
        found = _seen(source, follow=depth == 0)      # what was dropped itself is followed
        kind = _kind(found)
        try:
            place = disk.place(where)
        except OSError:
            place = None
        mark, leads, names = _mark(source, kind, found, place), "", []
        try:
            if mark == LEADS:
                leads = os.readlink(source)
            elif kind == FOLDER and not mark:
                names = sorted(os.listdir(source))
        except OSError:
            mark = UNREADABLE
        size = found.st_size if found is not None and kind == FILE else 0
        yield _Entry(source, where, place, depth, name, kind, size, mark, leads, number, of)
        waiting += [(source / child, child, where, depth + 1, at, len(names))
                    for at, child in reversed(list(enumerate(names)))]


def _seen(path: Path, follow: bool) -> os.stat_result | None:
    """What is at a path, or None if nothing can be found out about it."""
    try:
        return os.stat(path) if follow else os.lstat(path)
    except OSError:
        return None


def _kind(found: os.stat_result | None) -> str:
    if found is None:
        return OTHER
    return (FOLDER if stat.S_ISDIR(found.st_mode) else FILE if stat.S_ISREG(found.st_mode)
            else LINK if stat.S_ISLNK(found.st_mode) else OTHER)


def _mark(source: Path, kind: str, found: os.stat_result | None, place: Path | None) -> str:
    """The mark of one thing: the first that fits. LEADS for a link that would be copied."""
    if place is None:
        return NO_PLACE
    there = _seen(place, follow=False)                # a link at the place is seen as a link
    if found is not None and there is not None and os.path.samestat(found, there):
        return HERE
    if kind == OTHER:                                 # a socket, a pipe, a device, a dead link
        return UNREADABLE if found is None else NOT_COPIED
    if there is not None and (kind == LINK or _kind(there) != kind):
        return IN_THE_WAY                             # also a link there, wherever it leads
    if kind == FILE and not os.access(source, os.R_OK):
        return UNREADABLE
    if kind == FILE and there is not None:
        return EXISTS
    return LEADS if kind == LINK else ""


# ---------------------------------------------------------------------- the copy

@dataclass(frozen=True)
class Result:
    """What a copy did."""
    into: str                         # the destination, as the machine's path
    files: int = 0                    # what was written: files and links,
    folders: int = 0                  # the folders that were made,
    bytes: int = 0                    # and what the files hold
    skipped: dict[str, int] = field(default_factory=dict)    # what wasn't copied, by its mark;
                                                             # MEANWHILE is one of them
    failed: tuple[tuple[str, str], ...] = ()      # up to FAILED_MAX: a path below `into`, and why
    more: int = 0                     # how many more failed
    ended: str | None = None          # why it stopped early
    names: tuple[str, ...] = ()       # the dropped names under which something was written, a
                                      # folder's with a / after it


def carry_out(disk: Disk, sources: Sequence[Path], into: str, overwrite: bool | None,
              stop: threading.Event | None = None,
              tell: Callable[[Counts], None] | None = None) -> Result:
    """Copy `sources`, the paths of a drop, into `into`, a directory of the machine.

    It doesn't copy from a tree: it goes over the sources again and decides about each thing
    as it is by then. What has a mark that skips is skipped. A file that exists is replaced
    if `overwrite` is True and skipped if it is False. None means that the user wasn't asked,
    because nothing existed when the tree was made: what exists by now is skipped, and counted
    as MEANWHILE.

    What goes wrong with one thing is that thing's: it is in `failed` with its reason, and
    the copy goes on. Three things end the whole copy, and what was written until then stays:
    `stop` is set, the disk is full, the destination is gone.

    `tell` gets how far the copy has come, after each thing and some times a second inside a
    big file: the folders, the files and the bytes it is through with, copied or not. They
    end at the counts of the tree."""
    into = disk.virtual(into)
    ended = _refused(disk, sources, into)
    if ended is not None:
        return Result(into, ended=ended)
    files = folders = held = more = 0
    skipped: dict[str, int] = {}
    failed: list[tuple[str, str]] = []
    names: dict[str, None] = {}                       # in the order they were dropped
    seen_folders = seen_files = seen_bytes = 0        # how far it is through, for `tell`
    told = time.monotonic()

    def wrote(count: int) -> None:
        """A piece of a file is written."""
        nonlocal seen_bytes, told
        seen_bytes += count
        if tell is not None and time.monotonic() - told >= TELL_SECONDS:
            told = time.monotonic()
            tell(Counts(seen_folders, seen_files, seen_bytes))

    for entry in _walk(disk, sources, into):
        if stop is not None and stop.is_set():
            ended = STOPPED
            break
        if entry.depth == 0:
            top = entry.name + "/" * (entry.kind == FOLDER)
        skip, before, made = _skip(entry.mark, overwrite), seen_bytes, False
        try:
            if skip is not None:
                skipped[skip] = skipped.get(skip, 0) + 1
            elif entry.kind == FOLDER:
                made = _make_folder(entry.place)
                folders += made
            elif entry.kind == LINK:
                os.symlink(entry.leads, entry.place)
                files, made = files + 1, True
            elif copy_whole(entry.source, entry.place, stop, wrote):
                files, held, made = files + 1, held + seen_bytes - before, True
            else:
                ended = STOPPED
                break
        except OSError as e:
            if e.errno in (errno.ENOSPC, errno.EDQUOT):
                ended = FULL
                break
            if _gone(disk, into):
                ended = f"the folder is gone: {into}"
                break
            if len(failed) < FAILED_MAX:
                failed.append((posixpath.relpath(entry.where, into),
                               e.strerror or type(e).__name__))
            else:
                more += 1
        if made:
            names.setdefault(top)
        if entry.kind == FOLDER:
            seen_folders += 1
        else:
            seen_files, seen_bytes = seen_files + 1, before + entry.size
        if tell is not None:
            tell(Counts(seen_folders, seen_files, seen_bytes))
    return Result(into, files, folders, held, skipped, tuple(failed), more, ended, tuple(names))


def _skip(mark: str, overwrite: bool | None) -> str | None:
    """Why a thing with this mark isn't copied, or None if it is."""
    if mark in SKIPPED:
        return mark
    if mark == EXISTS and not overwrite:
        return EXISTS if overwrite is False else MEANWHILE
    return None


def _make_folder(place: Path) -> bool:
    """Make a folder, unless one is there. Says whether it made one."""
    try:
        os.mkdir(place)
    except FileExistsError:
        if place.is_symlink() or not place.is_dir():  # something else took the name meanwhile
            raise
        return False
    return True


def _gone(disk: Disk, into: str) -> bool:
    """Is the destination no folder any more?"""
    try:
        return not disk.real(into).is_dir()
    except OSError:
        return False                                  # behind the fence, which every place says


# ---------------------------------------------------------------------- the machine's side

@dataclass(frozen=True)
class Seen:
    """Everything the Files tab shows, as it is at one moment. The tab may keep it."""
    state: str                        # EMPTY, LOOKING, READY, COPYING or DONE
    into: str                         # the destination; in EMPTY, where a drop would go now
    names: tuple[str, ...] = ()       # what was dropped, in its order
    lines: tuple[Line, ...] = ()      # the tree, in READY and COPYING
    counts: Counts = field(default_factory=Counts)      # of the tree; in LOOKING, so far
    refused: str | None = None        # in READY: why nothing of the tree can be copied
    through: Counts = field(default_factory=Counts)     # in COPYING: how far it is, of `counts`
    result: Result | None = None      # in DONE


class _Run:
    """A walk or a copy that runs in its thread."""

    def __init__(self) -> None:
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None


class Imports:
    """What was dropped into the machine, and what becomes of it.

    Everything is called in the event loop, as the panel calls it. A walk and a copy work in
    a thread of their own, so the panel stays alive, and so does an answer of the AI that
    runs. What they report from there is taken under a lock, and what they end with comes
    back into the loop. `changed` is called in the loop whenever a thread has changed what
    watch() returns; what the panel changes itself it draws itself.

    A daemon thread, not asyncio's pool, as for an addon's function: a copy that hangs on a
    drive that doesn't answer must not keep Hallux from quitting."""

    def __init__(self, disk: Disk, changed: Callable[[], None] | None = None) -> None:
        self.disk = disk
        self.changed = changed or (lambda: None)
        self._state = EMPTY
        self._sources: list[Path] = []                # what was dropped, in its order
        self._into = ""                               # where it goes: the shell's directory at
                                                      # the first drop of the list
        self._tree: Tree | None = None
        self._result: Result | None = None
        self._run: _Run | None = None                 # the walk or the copy that counts: the
                                                      # last one begun, unless it was dropped
        self._runs: list[_Run] = []                   # and every one whose thread may still live
        self._lock = threading.Lock()                 # for what a thread reports:
        self._through = Counts()                      # how far the walk or the copy has come,
        self._asked = 0.0                             # and when it last asked to be drawn

    # ------------------------------------------------------------------ what the tab is shown

    def watch(self) -> Seen:
        with self._lock:
            through = self._through
        if self._state == EMPTY:
            return Seen(EMPTY, self.disk.cwd)
        names = tuple(_name(source) or str(source) for source in self._sources)
        if self._state == LOOKING:
            return Seen(LOOKING, self._into, names, counts=through)
        if self._state == DONE:
            return Seen(DONE, self._into, names, result=self._result)
        tree = self._tree
        refused = tree.refused or (STOPPED if tree.stopped else None)
        return Seen(self._state, self._into, names, tree.lines, tree.counts, refused,
                    through if self._state == COPYING else Counts())

    # ------------------------------------------------------------------ what the tab asks for

    def reads(self, text: str) -> bool:
        """Is this text a drop at all?"""
        try:
            read_drop(text)
        except NotADrop:
            return False
        return True

    def drop(self, text: str) -> str | None:
        """Add what a dropped text names to the list, and work the tree out again. Returns
        None, or why nothing was added, in words for the panel's foot: then the list is as
        it was. The first drop of a list notes where the list goes: the shell's directory."""
        if self._state == COPYING:
            return "a copy is running"
        try:
            dropped = read_drop(text)
        except NotADrop as e:
            return str(e)
        fresh = self._state in (EMPTY, DONE)
        sources = [] if fresh else list(self._sources)
        into = self.disk.cwd if fresh else self._into
        for source in dropped:
            name = _name(source)
            if source in sources:
                return f"already in the list: {name}"
            if name in map(_name, sources):
                return f"two things named {name}"
            sources.append(source)
        try:
            said = _into_itself(dropped, self.disk.real(into))
        except OSError:
            said = None                               # behind the fence: the tree says so
        if said is not None:
            return said
        self._sources, self._into, self._state = sources, into, LOOKING
        self._begin(lambda run, tell: look(self.disk, tuple(sources), into, run.stop, tell),
                    self._looked, lambda why: Tree(into, refused=f"couldn't be looked at: {why}"))
        return None

    def start(self, overwrite: bool | None) -> None:
        """Copy what the tree shows. `overwrite` is carry_out's: True and False are the
        user's answer about the files that exist, None says that none did. Nothing happens
        unless the tree is there, isn't refused, and has something that would be copied."""
        tree = self._tree
        if (self._state != READY or tree.refused is not None or tree.stopped
                or not tree.counts.to_copy):
            return
        sources, into = tuple(self._sources), self._into
        self._state = COPYING

        def copy(run: _Run, tell: Callable[[Counts], None]) -> Result:
            result = carry_out(self.disk, sources, into, overwrite, run.stop, tell)
            log.info("import into %s: %d files, %d folders, %d bytes; %d skipped, %d failed%s",
                     result.into, result.files, result.folders, result.bytes,
                     sum(result.skipped.values()), len(result.failed) + result.more,
                     f"; {result.ended}" if result.ended else "")
            return result

        self._begin(copy, self._copied, lambda why: Result(into, ended=f"failed: {why}"))

    def stop(self) -> None:
        """Stop the walk or the copy that runs. What was copied stays."""
        if self._run is not None:
            self._run.stop.set()

    def clear(self) -> None:
        """Empty the list, or forget the result of the last copy. Not while a copy runs."""
        if self._state == COPYING:
            return
        self._drop_run()
        self._state = EMPTY                           # in which nothing reads what the list held

    def close(self) -> None:
        """Hallux ends: stop what runs, and wait until it has stopped. A thread that doesn't
        answer in time is left to itself. It is a daemon thread and ends with Hallux."""
        self._drop_run()                              # every other run was stopped when it
        for run in self._runs:                        # was replaced, or is through
            run.thread.join(CLOSE_SECONDS)
            if run.thread.is_alive():
                log.warning("an import didn't stop in %.0f seconds", CLOSE_SECONDS)
        self._runs = []

    # ------------------------------------------------------------------ the threads

    def _begin(self, work: Callable[[_Run, Callable[[Counts], None]], object],
               landed: Callable[[object], None], broken: Callable[[str], object]) -> None:
        """Do `work` in a thread of its own, in place of the walk that runs, if one does.
        What it returns goes to `landed`, in the loop, unless this run was replaced or
        dropped meanwhile: then it reaches nobody. If it raises, which is a mistake in here,
        the log has it, and `landed` gets what `broken` makes of the error's words: the tab
        says so, and doesn't wait for ever."""
        loop, run = asyncio.get_running_loop(), _Run()
        self._drop_run()

        def ask(function: Callable, *args: object) -> None:
            try:
                loop.call_soon_threadsafe(function, *args)
            except RuntimeError:                      # the loop is closed: Hallux is off
                pass

        def tell(counts: Counts) -> None:             # in the thread
            with self._lock:
                if run is not self._run:
                    return
                self._through = counts
                due = time.monotonic() - self._asked >= CHANGED_SECONDS
                if due:
                    self._asked = time.monotonic()
            if due:
                ask(self.changed)

        def land(outcome: object) -> None:            # in the loop
            if run is self._run:
                landed(outcome)
                self.changed()

        def body() -> None:                           # the thread
            try:
                outcome = work(run, tell)
            except Exception as e:
                log.exception("an import's thread failed")
                outcome = broken(f"{type(e).__name__}: {e}")
            ask(land, outcome)

        with self._lock:                              # its first report is drawn at once
            self._run, self._through, self._asked = run, Counts(), 0.0
        self._runs = [other for other in self._runs if other.thread.is_alive()] + [run]
        run.thread = threading.Thread(target=body, name="hallux-import", daemon=True)
        run.thread.start()

    def _drop_run(self) -> None:
        """Stop the walk or the copy that counts, and take no more of it."""
        with self._lock:
            run, self._run = self._run, None
        if run is not None:
            run.stop.set()

    def _looked(self, tree: Tree) -> None:
        self._tree, self._state = tree, READY

    def _copied(self, result: Result) -> None:
        self._result, self._state = result, DONE
