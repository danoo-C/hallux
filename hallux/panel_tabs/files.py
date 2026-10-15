"""The Files tab of hallux's own panel: files and folders dropped onto the terminal's window,
and their copy into the machine.

A terminal has no message for a drop: it pastes the path of what was dropped, or it types it
(docs/user-addition/drag-and-drop/). A paste reaches the tab from any tab, through the host
(Tab.paste). For a terminal that types the drop, as VS Code's does, the tab has a row for a
typed path: a quote, a slash or a backslash opens it, and so does `p`.

The tab knows nothing of the machine. It is given six functions, those of the machine's
Imports (hallux.importing): watch() says what to show, and drop(text), reads(text),
start(overwrite), stop() and clear() do what the keys ask for. It reads watch() anew at
every redraw, so the counts grow while a walk or a copy runs in its thread.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import ConditionalContainer, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from hallux.importing import (
    COPYING, DONE, EMPTY, EXISTS, FILE, FOLDER, LOOKING, MORE, READY, SKIPPED, STOPPED, Counts,
    Line, Result, Seen,
)
from hallux.panel import Tab
from hallux.panel_tabs.agents import cut
from hallux.statusbar import GRAY, RED, YELLOW_NOTE, size

TAKE_SECONDS = 0.3                            # a typed drop is taken when no key came for this long
OPENERS = ("'", '"', "/", "\\")               # what a typed drop starts with: it opens the path row
FILES_WIDTH, SIZE_WIDTH, MARK_MAX = 11, 8, 24     # columns of a tree's line: "1,400 files", "2.3 MB"
NAME_MIN = 12                                 # columns a name keeps, however narrow the window
WHEEL = 3                                     # lines the wheel scrolls
NOTE, REFUSED, WARNED = f"fg:{GRAY}", f"fg:{RED}", f"fg:{YELLOW_NOTE}"
TYPED, AT = "underline", "reverse"            # the path row's text, and its cursor

Fragments = list[tuple[str, str]]             # one line: (style, text) pairs


@dataclass
class Drawn:
    head: list[Fragments]                     # two lines, which stay
    body: list[Fragments]                     # the lines that scroll, top to bottom


def clean(text: str) -> str:
    """A name as it is shown: a character that isn't printable is a ?."""
    return "".join(char if char.isprintable() else "?" for char in text)


def plural(count: int, word: str) -> str:
    return f"{count:,} {word}{'s' * (count != 1)}"


def counted(counts: Counts) -> str:
    """2 folders · 14 files · 2.3 MB. No folders, no word for them."""
    parts = [plural(counts.folders, "folder")] if counts.folders else []
    return " · ".join([*parts, plural(counts.files, "file"), size(counts.bytes)])


def exist(count: int, what: str = "") -> str:
    """1 exists already, 3 files exist already."""
    return f"{plural(count, what) if what else f'{count:,}'} {'exists' if count == 1 else 'exist'} already"


def ending(text: str, width: int) -> str:
    """A path cut at its front: its end, where the name is, stays."""
    return text if len(text) <= width else "…" + text[-max(0, width - 1):]


def fitted(said: str, width: int) -> str:
    """A word for the foot, cut to its width. A long one keeps what comes before its colon,
    and the end of what follows: there a path has its name."""
    if len(said) <= width:
        return said
    head, colon, tail = said.partition(": ")
    if not colon or len(head) + len(colon) + NAME_MIN > width:
        return ending(said, width)
    return head + colon + ending(tail.removeprefix("…"), width - len(head) - len(colon))


def draw(seen: Seen, width: int = 80) -> Drawn:
    """The whole tab as text, from what watch() says."""
    room = max(NAME_MIN, width - 2)                      # one column in front, one left free
    into = clean(seen.into)
    if seen.state == EMPTY:
        return Drawn([[("bold", " Drop files or folders onto this window.")],
                      [(NOTE, " They are copied into " + ending(into, room - 21))]], [])
    if seen.state == DONE:
        return _done(seen.result, into, width)
    head = [[("bold", " into " + ending(into, room - 5))]]
    if seen.state == LOOKING:
        head.append([("", f" {counted(seen.counts)} · counting…")])
        return Drawn(head, [[("", " " + cut(clean(name), room))] for name in seen.names])
    if seen.state == COPYING:
        done, of = seen.through, seen.counts
        head.append([("", f" copying… {done.files:,} of {plural(of.files, 'file')} · "
                          f"{size(done.bytes)} of {size(of.bytes)}")])
    elif seen.refused is not None:                       # a refused tree has no lines
        head.append([(REFUSED, " " + cut(clean(seen.refused), room))])
    else:
        line = [("", " " + counted(seen.counts))]
        if exists := seen.counts.marks.get(EXISTS, 0):
            line.append((WARNED, f" · {exist(exists)}"))
        if skipped := sum(seen.counts.marks.get(mark, 0) for mark in SKIPPED):
            line.append((NOTE, f" · {skipped:,} can't be copied"))
        head.append(line)
    return Drawn(head, tree(seen.lines, width))


def tree(lines: tuple[Line, ...], width: int = 80) -> list[Fragments]:
    """The tree's lines: two spaces for each depth, the name, a / after a folder; on the
    right, in columns, a folder's number of files, the size, the mark."""
    marks = [len(line.mark) for line in lines if line.kind != MORE and line.mark]
    mark_width = min(MARK_MAX, max(marks, default=0))
    right = FILES_WIDTH + 2 + SIZE_WIDTH + (3 + mark_width if mark_width else 0)
    room = max(NAME_MIN, width - 1 - 1 - 2 - right)
    drawn: list[Fragments] = []
    for line in lines:
        name = "  " * line.depth + clean(line.name)
        if line.kind == MORE:                            # "… 6 more", "… and more"
            drawn.append([(NOTE, " " + cut(name, room))])
            continue
        name += "/" * (line.kind == FOLDER)
        files = plural(line.files, "file") if line.kind == FOLDER else ""
        held = size(line.size) if line.kind in (FOLDER, FILE) else ""
        parts = [("", f" {cut(name, room):<{room}}  {files:>{FILES_WIDTH}}  {held:>{SIZE_WIDTH}}")]
        if line.mark:
            style = WARNED if line.mark == EXISTS else NOTE if line.mark in SKIPPED else ""
            parts += [("", "   "), (style, cut(clean(line.mark), mark_width))]
        drawn.append(parts)
    return drawn


def _done(result: Result, into: str, width: int) -> Drawn:
    """After a copy: what was copied, and what wasn't, each with its reason."""
    room = max(NAME_MIN, width - 2)
    said = f"copied {plural(result.files, 'file')} ({size(result.bytes)}) into "
    style = "bold"
    if result.ended is not None:                         # stopped, the disk is full, a mistake
        said = f"{clean(result.ended)}: {said}"
        style = "bold" if result.ended == STOPPED else REFUSED
    first = (" " + said + ending(into, room - len(said)) if room - len(said) >= NAME_MIN
             else " " + cut(said + into, room))
    skipped, failed = sum(result.skipped.values()), len(result.failed) + result.more
    counts = [f"{skipped:,} skipped"] * bool(skipped) + [f"{failed:,} failed"] * bool(failed)
    head = [[(style, first)], [(NOTE, " " + (" · ".join(counts) or "nothing skipped"))]]
    if not counts and result.ended is None:
        return Drawn(head, [[(NOTE, " everything was copied")]])
    body: list[Fragments] = []
    for mark, count in result.skipped.items():
        body.append([("", f" {count:,} skipped: "),
                     (WARNED if mark == EXISTS else NOTE, clean(mark))])
    for path, why in result.failed:
        body.append([("", " " + cut(clean(path), room // 2)), ("", "  "),
                     (REFUSED, cut(clean(why), max(10, room - room // 2 - 2)))])
    if result.more:
        body.append([(NOTE, f" … {result.more:,} more failed")])
    return Drawn(head, body)


class FilesTab(Tab):
    title = "Files"

    def __init__(self, watch: Callable[[], Seen], drop: Callable[[str], str | None],
                 reads: Callable[[str], bool], start: Callable[[bool | None], None],
                 stop: Callable[[], None], clear: Callable[[], None]) -> None:
        self.watch, self.drop, self.reads = watch, drop, reads
        self.start, self.stop, self.clear = start, stop, clear
        self.top = 0                                     # the first line of the body in view
        self.cursor = Point(0, 0)
        self.asking = False                              # overwrite the files that exist?
        self.row: Buffer | None = None                   # the path row, while it is open
        self.burst = True                                # its keys came many at once, as a
        self.read = 0                                    # drop's do: characters in this read,
        self.counting: asyncio.Handle | None = None      # until the loop is through with it
        self.taking: asyncio.TimerHandle | None = None   # takes a typed drop without Enter
        self.result: Result | None = None                # the last result that was on the screen
        self.body = Window(FormattedTextControl(self._body, focusable=True,
                                                get_cursor_position=lambda: self.cursor),
                           always_hide_cursor=True)
        self.container = HSplit([
            Window(height=1),
            Window(FormattedTextControl(self._head), height=2),
            ConditionalContainer(Window(FormattedTextControl(self._row), height=1),
                                 Condition(lambda: self.row is not None)),
            Window(height=1), self.body])
        self.bindings = self._bindings()

    # ---------------------------------------------------------------- what the host asks

    @property
    def typing(self) -> bool:
        return self.asking or self.row is not None

    def hint(self) -> str:
        if self.asking:
            exists = self.watch().counts.marks.get(EXISTS, 0)
            return f"{exist(exists, 'file')}: o overwrite · s skip · Esc back"
        if self.row is not None:
            return "type or drop a path · Enter take · Esc leave the row"
        seen = self.watch()
        keys = ["↑ ↓ scroll"] if len(draw(seen, self._columns()).body) > self._height() else []
        if self._copies(seen):
            keys.append("Enter copy")
        if seen.state == COPYING:
            keys.append("s stop")
        else:
            keys += ["x clear"] * (seen.state != EMPTY) + ["p path"]
        return " · ".join(keys)

    def paste(self, text: str) -> bool:
        """A drop is taken from any tab. Another text only while this is the shown one: then
        the foot says why it is no drop."""
        if self.host.tab is not self and not self.reads(text):
            return False
        self._give(text)
        return True

    def wants_first(self) -> bool:
        """The panel opens here while a copy runs, and until its result was on the screen."""
        seen = self.watch()
        return seen.state == COPYING or seen.state == DONE and seen.result is not self.result

    def leave(self) -> bool:
        if self.asking:
            self.asking = False
        elif self.row is not None:
            self._close_row()
        else:
            return False
        return True

    def shown(self) -> None:
        self.top, self.asking = 0, False
        self._close_row()
        if (seen := self.watch()).state == DONE:
            self.result = seen.result

    # ---------------------------------------------------------------- drawing

    def _columns(self) -> int:
        return get_app().output.get_size().columns

    def _drawn(self) -> Drawn:
        seen = self.watch()                              # anew at every redraw
        if seen.state == DONE:
            self.result = seen.result                    # it is on the screen now
        return draw(seen, self._columns())

    def _head(self) -> list:
        lines = self._drawn().head
        return [part for line in lines for part in (*line, ("", "\n"))][:-1]

    def _body(self) -> list:
        lines, width = self._drawn().body, self._columns()
        self.top = max(0, min(self.top, len(lines) - 1))
        self.body.vertical_scroll = self.top
        self.cursor = Point(0, self.top)
        parts: list = []
        for line in lines:                               # the wheel works on the whole row
            parts += [(style, text, self._wheel) for style, text in line]
            parts += [("", " " * max(0, width - 1 - sum(len(text) for _, text in line)),
                       self._wheel), ("", "\n")]
        return parts[:-1]

    def _row(self) -> list:
        """path: and what was typed, with the cursor in it. A long text shows its end."""
        if self.row is None:
            return []
        text, at = self.row.text, self.row.cursor_position
        room = max(NAME_MIN, self._columns() - 1 - len(" path: ") - 1)
        start = max(0, at + 1 - room)
        shown, at = text[start:start + room], at - start
        return [("bold", " path: "), (TYPED, shown[:at]), (AT, shown[at:at + 1] or " "),
                (TYPED, shown[at + 1:])]

    def _wheel(self, event: MouseEvent) -> None:
        if event.event_type == MouseEventType.SCROLL_UP:
            self._scroll(-WHEEL)
        elif event.event_type == MouseEventType.SCROLL_DOWN:
            self._scroll(WHEEL)

    def _height(self) -> int:
        info = self.body.render_info
        return info.window_height if info is not None else 1

    # ---------------------------------------------------------------- keys

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()
        asked = Condition(lambda: self.asking)
        in_row = Condition(lambda: self.row is not None)
        free = ~asked & ~in_row

        def when(*states: str) -> Condition:
            return Condition(lambda: self.watch().state in states)

        def to(handler: Callable[[], object]) -> Callable:
            return lambda event: handler()

        kb.add("up", filter=~asked)(to(lambda: self._scroll(-1)))
        kb.add("down", filter=~asked)(to(lambda: self._scroll(1)))
        kb.add("pageup", filter=~asked)(to(lambda: self._scroll(1 - self._height())))
        kb.add("pagedown", filter=~asked)(to(lambda: self._scroll(self._height() - 1)))
        kb.add("enter", filter=free)(to(self._enter))
        kb.add("x", filter=free)(to(self.clear))             # it clears nothing while a copy runs
        kb.add("s", filter=free & when(COPYING))(to(self.stop))
        opens = free & ~when(COPYING)
        kb.add("p", filter=opens)(to(lambda: self._open("")))
        for first in OPENERS:
            kb.add(first, filter=opens)(lambda event, first=first: self._open(first))

        # The question, as the tab's own hint. While it is asked the tab counts as typing, so
        # the host takes no letter. Esc and any other key drop it.
        kb.add("o", filter=asked)(to(lambda: self._answer(True)))
        kb.add("s", filter=asked)(to(lambda: self._answer(False)))
        kb.add(Keys.Any, filter=asked)(to(lambda: self._answer(None)))

        # The path row is one line of text. Its keys are bound here one by one, as the Config
        # tab binds its open row, so no letter in a path chooses a tab or does anything else.
        @kb.add(Keys.Any, filter=in_row)
        def _type(event) -> None:
            if all(len(press.key) == 1 for press in event.key_sequence):     # a character
                if text := "".join(char for char in event.data if char.isprintable()):
                    self._write(text)

        @kb.add(Keys.BracketedPaste, filter=in_row)
        def _paste(event) -> None:
            lines = " ".join(event.data.splitlines())    # paths one to a line stay apart
            if text := "".join(char for char in lines if char.isprintable()):
                self._write(text)

        def edit(*keys: str) -> Callable:
            def bind(change: Callable[[Buffer], object]) -> None:
                def handle(event) -> None:
                    change(self.row)
                    self.burst = False                   # a hand edits: Enter takes it
                for key in keys:
                    kb.add(key, filter=in_row)(handle)
            return bind

        edit("backspace")(lambda line: line.delete_before_cursor())
        edit("delete")(lambda line: line.delete())
        edit("left")(lambda line: line.cursor_left())
        edit("right")(lambda line: line.cursor_right())
        edit("home", "c-a")(lambda line: setattr(line, "cursor_position", 0))
        edit("end", "c-e")(lambda line: setattr(line, "cursor_position", len(line.text)))
        edit("c-u")(lambda line: line.delete_before_cursor(line.cursor_position))
        kb.add("enter", filter=in_row)(to(self._take))
        return kb

    def _scroll(self, by: int) -> None:
        last = max(0, len(self._drawn().body) - self._height())     # the top, at the bottom
        self.top = max(0, min(last, self.top + by))

    def _copies(self, seen: Seen) -> bool:
        """Would Enter copy something?"""
        return seen.state == READY and seen.refused is None and seen.counts.to_copy > 0

    def _enter(self) -> None:
        """Copy. Asked first when a file exists already."""
        seen = self.watch()
        if not self._copies(seen):
            return
        if seen.counts.marks.get(EXISTS):
            self.asking = True
        else:
            self.start(None)                             # nothing to ask about

    def _answer(self, overwrite: bool | None) -> None:
        self.asking = False
        if overwrite is not None:
            self.start(overwrite)

    def _give(self, text: str) -> bool:
        """Give a text to drop(). What it says goes into the foot. True if it was taken."""
        said = self.drop(text)
        if said is not None:
            self.host.say(fitted(clean(said), max(NAME_MIN, self._columns() - 2)))
            return False
        self.top = 0                                     # a new tree, seen from its top
        return True

    # ---------------------------------------------------------------- the path row

    def _open(self, first: str) -> None:
        self.row, self.burst = Buffer(), True
        self._write(first)

    def _close_row(self) -> None:
        self.row = None
        if self.taking is not None:
            self.taking.cancel()
            self.taking = None

    def _write(self, text: str) -> None:
        """Type into the row. A terminal that types a drop sends it all at once, and the keys
        of one read are handled in one go. A character that came alone was typed by hand."""
        self.read += len(text)
        if self.counting is None:
            self.counting = asyncio.get_running_loop().call_soon(self._counted)
        self.row.insert_text(text)
        self._wait()

    def _counted(self) -> None:
        """The loop is through with the keys of one read."""
        if self.read == 1:
            self.burst = False
        self.read, self.counting = 0, None

    def _wait(self) -> None:
        """A key came to the row: wait anew for the pause after a typed drop."""
        if self.taking is not None:
            self.taking.cancel()
        self.taking = asyncio.get_running_loop().call_later(TAKE_SECONDS, self._by_itself)

    def _by_itself(self) -> None:
        """No key came for a while. A text whose keys came as one is a drop that was typed,
        and is taken without Enter if it reads as one. The row closes either way then, and
        what drop() said is in the foot. A text typed by hand waits for Enter."""
        self.taking = None
        if self.row is None or not self.burst or not self.reads(text := self.row.text):
            return
        self._close_row()
        self._give(text)
        get_app().invalidate()

    def _take(self) -> None:
        """Enter in the row: drop() gets the text, whatever it is. Taken, the row closes;
        refused, it stays with its text, and the foot says why."""
        if self._give(self.row.text):
            self._close_row()
