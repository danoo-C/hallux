"""The real terminal: keys in, the AI's text out, and hallux's own status bar.

prompt_toolkit handles the keyboard side of line editing (arrows, backspace, recalling
what you typed). Keys that mean something to the machine (Ctrl-C, Tab, Ctrl-L, F-keys...)
go to the AI together with the line being typed, and the AI decides what they do.

Hallux reads the keyboard all the time, also while the AI thinks: keys typed then wait for
the next prompt, Ctrl-C interrupts the AI, and Ctrl+Shift+Del (or Ctrl-C three times
within a second) pulls the plug: hallux quits at once, whatever the AI is doing.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import signal
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, Callable, NoReturn

from prompt_toolkit import PromptSession
from prompt_toolkit.application import get_app
from prompt_toolkit.data_structures import Size
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import DummyHistory, InMemoryHistory
from prompt_toolkit.input import create_input
from prompt_toolkit.input.typeahead import get_typeahead, store_typeahead
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.processors import Processor, Transformation, TransformationInput
from prompt_toolkit.output import create_output
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.utils import get_cwidth

from hallux import statusbar
from hallux.blockmode import OPEN_KEY, POWER_CUT_KEY, BlockMode
from hallux.machine import Interrupted, Key
from hallux.protocol import Action, Form, plain
from hallux.statusbar import StatusBar

if TYPE_CHECKING:
    from hallux.panel import Panel

log = logging.getLogger("hallux")

# Keys for the machine that end the line. The tty driver echoes them ("ls -la^C").
LINE_ENDING = {"c-c": ("C-c", "^C"), "c-z": ("C-z", "^Z"), "c-\\": ("C-\\", "^\\")}
# Keys for the machine that work in place: the AI answers and the line comes back.
IN_PLACE = {("tab",): "Tab", ("c-l",): "C-l", ("c-r",): "C-r", ("c-s",): "C-s",
            ("c-o",): "C-o", ("c-g",): "C-g", ("c-q",): "C-q", ("c-v",): "C-v",
            ("c-x",): "C-x", ("escape", "."): "M-.",
            **{(f"f{n}",): f"F{n}" for n in range(1, 13)}}
CTRL_C_PRESSES, CTRL_C_WINDOW = 3, 1.0          # this many Ctrl-C within a second: hard exit
RESTORE_TERMINAL = ("\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l"   # mouse reporting off
                    "\x1b[?2004l\x1b[?1049l"                        # paste mode, main screen
                    "\x1b[0m\x1b[?25h")                             # plain colors, cursor on

# Escape sequences other than colors (SGR): prompt_toolkit must print them as-is, zero-width.
NON_SGR_ESCAPE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-ln-z]")


def zero_width(prompt: str) -> str:
    """Mark non-color escapes (window titles, cursor moves) as zero-width for prompt_toolkit."""
    return NON_SGR_ESCAPE.sub(lambda m: f"\x01{m[0]}\x02", prompt)


@dataclass(frozen=True)
class _ToPanel:
    """What a prompt returns when Ctrl+F12 ended it: the line as it was typed so far."""
    line: str
    cursor: int = 0


class Terminal:
    def __init__(self, bar: StatusBar | None = None, input=None, output=None,
                 power_cut: Callable[[], None] | None = None,
                 before_power_cut: Callable[[], object] = lambda: None) -> None:
        self.bar = bar                                   # None: no status bar
        self.status_bar = bar is not None
        self.streams = True                              # show answers while they're written
        self.attended = True                             # somebody is at the keyboard
        self.real_tty = input is None and output is None and sys.stdin.isatty()
        self.input = input or create_input()
        self.output = output or create_output()          # the whole screen (block mode)
        self.saved_tty = _tty_settings() if self.real_tty else None
        self.on_power_cut = power_cut or self._pull_the_plug
        self.before_power_cut = before_power_cut         # the addons' stop() hooks
        self.ctrl_c_times: deque[float] = deque(maxlen=CTRL_C_PRESSES)
        self.interrupt: Callable[[], None] | None = None     # stops the AI's current turn
        self.pinned: Size | None = None                  # the screen size the bar is pinned for
        self.raw = contextlib.ExitStack()                # raw mode for the whole session
        self.panel: Panel | None = None                  # hallux's own panel, once handed over
        self.visit: asyncio.Task | None = None           # a visit that began while the AI works
        self.kept: list[str] | None = None               # during a visit: what was written
        self.over_prompt = False                         # the visit began at the shell prompt,
        self.event_waits = False                         # and an event asked the prompt to end

        prompt_output = self._prompt_output()
        self.session: PromptSession = PromptSession(
            history=InMemoryHistory(), key_bindings=self._prompt_keys(), input=self.input,
            output=prompt_output)
        # Passwords: nothing typed is shown, and nothing is kept for ↑ to bring back.
        self.secrets: PromptSession = PromptSession(
            history=DummyHistory(), key_bindings=self._prompt_keys(secret=True),
            input=self.input, output=prompt_output, input_processors=[_NoEcho()])
        for session in (self.session, self.secrets):
            session.app.after_render += lambda _: self._check_size()
        self.block = BlockMode(input=self.input, output=self.output, bar=bar,
                               power_cut=self.power_cut, ctrl_c=self._block_ctrl_c)

    # ---------------------------------------------------------------- start and stop

    async def start(self) -> None:
        # Raw mode from start to stop: no gap in which Ctrl-C would become a real SIGINT or a
        # key would be echoed into the machine's output. (prompt_toolkit's own switches nest.)
        self.raw.enter_context(self.input.raw_mode())
        if self.bar and self.real_tty:
            size = self.output.get_size()
            self._write(statusbar.install(size.rows))
            self.pinned = size
            self._draw_bar()
            with contextlib.suppress(NotImplementedError, RuntimeError, AttributeError):
                asyncio.get_running_loop().add_signal_handler(signal.SIGWINCH, self._check_size)

    def stop(self) -> None:
        self.raw.close()
        if self.pinned:
            self._write(statusbar.uninstall(self.output.get_size().rows))
            self.pinned = None
            with contextlib.suppress(NotImplementedError, RuntimeError, AttributeError, ValueError):
                asyncio.get_running_loop().remove_signal_handler(signal.SIGWINCH)

    # ---------------------------------------------------------------- the shell prompt

    async def read_line(self, prompt: str, default: str = "") -> str | Key | Interrupted:
        while True:
            self.session.app.erase_when_done = False
            line = await self.session.prompt_async(ANSI(zero_width(prompt)), default=default)
            if not isinstance(line, _ToPanel):
                return line
            self.over_prompt, self.event_waits = True, False
            try:
                await self._visit_from_prompt()
            finally:
                self.over_prompt = False
            if self.event_waits:                         # the read ends as the event would have
                return Interrupted(line.line, line.cursor)   # ended it, with what was typed
            default = line.line                          # read on from there

    def interrupt_prompt(self) -> bool:
        """End the shell prompt from outside, the way a key like Tab ends it from inside:
        read_line returns what was typed so far. Keys that arrive after it wait for the
        next prompt. False, and nothing happens, when no shell prompt is being read: while
        the AI answers, at a password prompt, in a full-screen program. Call it from the
        event loop. While the panel is open over the prompt the answer is yes, and the read
        ends when the panel closes."""
        if self.over_prompt:
            self.event_waits = True
            return True
        app = self.session.app
        if not app.is_running or app.future is None or app.future.done():
            return False
        buf = app.current_buffer
        app.erase_when_done = True                       # the AI redraws the prompt line
        app.exit(result=Interrupted(buf.text, buf.cursor_position))
        return True

    async def read_secret(self, prompt: str) -> str | Key:
        """Read a password, the way a tty with echo off does (sudo, passwd, ssh)."""
        while True:
            self.secrets.app.erase_when_done = False     # Ctrl+F12 before it erased the prompt
            line = await self.secrets.prompt_async(ANSI(zero_width(prompt)))
            if not isinstance(line, _ToPanel):
                return line
            await self._visit_from_prompt()              # and nothing typed is carried over

    def write(self, text: str) -> None:
        if self.kept is not None:                        # the panel covers the screen: it is
            self.kept.append(text)                       # printed when the visit is over
            return
        self._write(text)                                # already made safe by decode()
        self._draw_bar()                                 # `clear` erases it; bring it back

    def retract(self, text: str) -> None:
        """Erase text just written: move up over the rows it took and clear below."""
        size = self.output.get_size()
        cols = max(1, size.columns)
        *lines, last = plain(text).split("\n")
        up = sum(max(1, -(-get_cwidth(line) // cols)) for line in lines)
        up += max(1, -(-get_cwidth(last) // cols)) - 1
        self._write((f"\x1b[{up}A" if up else "") + "\r\x1b[J")   # stops at the region's top
        self._draw_bar()

    def size(self) -> tuple[int, int]:
        size = self.output.get_size()
        return size.columns, size.rows - (1 if self.bar else 0)

    def _prompt_keys(self, secret: bool = False) -> KeyBindings:
        """The keys for the machine. At a password prompt they carry no text, and the keys
        that work in place do nothing (Ctrl-R would show what's typed in its search line)."""
        keys = KeyBindings()
        for key, (name, echo) in LINE_ENDING.items():
            keys.add(key, eager=True)(self._line_ending(name, echo, secret))
        empty = Condition(lambda: get_app().current_buffer.text == "")
        keys.add("c-d", filter=empty, eager=True)(self._line_ending("C-d", "", secret))
        for key, name in IN_PLACE.items():
            keys.add(*key, eager=True)((lambda event: None) if secret else self._in_place(name))
        keys.add(POWER_CUT_KEY, eager=True)(lambda event: self.power_cut())
        keys.add(OPEN_KEY, eager=True)(self._to_panel(secret))
        return keys

    def _to_panel(self, secret: bool) -> Callable:
        """Ctrl+F12 at a prompt ends it the way Tab does, and the panel is visited. Without a
        panel the key does nothing."""
        def handle(event) -> None:
            if self.panel is None:
                return
            buf = event.app.current_buffer
            line, cursor = ("", 0) if secret else (buf.text, buf.cursor_position)
            event.app.erase_when_done = True             # the prompt is drawn again afterwards
            event.app.exit(result=_ToPanel(line, cursor))
        return handle

    def _line_ending(self, name: str, echo: str, secret: bool = False) -> Callable:
        def handle(event) -> None:
            if name == "C-c":
                self.count_ctrl_c()
            buf = event.app.current_buffer
            line, cursor = ("", 0) if secret else (buf.text, buf.cursor_position)
            buf.cursor_position = len(buf.text)
            buf.insert_text(echo)                        # shown, not sent: "ls -la^C"
            event.app.exit(result=Key(name, line, cursor, keep_line=False))
        return handle

    def _in_place(self, name: str) -> Callable:
        def handle(event) -> None:
            buf = event.app.current_buffer
            event.app.erase_when_done = True             # the AI redraws the prompt line
            event.app.exit(result=Key(name, buf.text, buf.cursor_position, keep_line=True))
        return handle

    def _prompt_output(self) -> Vt100_Output:
        """prompt_toolkit may not draw on the bar's row: tell it the screen is a row shorter."""
        if not (self.bar and isinstance(self.output, Vt100_Output)):
            return self.output
        whole = self.output

        def get_size() -> Size:
            size = whole.get_size()
            return Size(rows=max(1, size.rows - 1), columns=size.columns)
        return _BarKeepingOutput(whole.stdout, get_size, term=whole.term, bar=self._bar_codes)

    # ---------------------------------------------------------------- while the AI works

    @contextlib.asynccontextmanager
    async def busy(self, interrupt: Callable[[], None],
                   activity: str = "thinking…") -> AsyncIterator[None]:
        """The AI is working: animate the bar and keep reading the keyboard."""
        if self.bar:
            self.bar.update(busy=True, activity=activity, tools=0, error=None,
                            started=time.monotonic())
        self.interrupt = interrupt
        animation = asyncio.create_task(self._animate())
        typed: list = []
        with contextlib.ExitStack() as watching:
            if not self.block.active:                    # block mode reads its own keys
                def read() -> None:
                    presses = self.input.read_keys()
                    for at, press in enumerate(presses):
                        if press.key == POWER_CUT_KEY:
                            self.power_cut()
                        elif press.key == OPEN_KEY and self.panel and self.visit is None:
                            self.visit = asyncio.ensure_future(visit(presses[at + 1:]))
                            break                        # the keys after it are the panel's
                        elif press.key == Keys.ControlC:
                            self.count_ctrl_c()
                            interrupt()
                        elif press.key != Keys.CPRResponse:
                            typed.append(press)          # type-ahead for the next prompt

                async def visit(keys: list) -> None:
                    try:
                        typed.extend(await self.visit_panel(keys))
                    finally:
                        self.visit = None
                watching.enter_context(self.input.attach(read))
            try:
                yield
            finally:
                animation.cancel()
                if self.bar:                             # the bar stops when the answer ends,
                    self.bar.update(busy=False)          # not when the panel closes
                    self._refresh()
                # The answer isn't over until a visit to the panel is: the panel's app has
                # the keyboard, and it has to give it back to the reader above before that
                # reader lets go. All that follows an answer waits here with it.
                if self.visit is not None:
                    await self.visit
                await self.block.panel_gone()            # over a program the panel is a layer
                self.interrupt = None
                store_typeahead(self.input, typed)

    def set_status(self, **changes: object) -> None:
        if self.bar:
            self.bar.update(**changes)
            self._refresh()

    async def _animate(self) -> None:
        while True:
            await asyncio.sleep(statusbar.FRAME_SECONDS)
            self._refresh()

    def _refresh(self) -> None:
        if self.block.active:
            self.block.invalidate()
        elif self.kept is not None:                      # the bar is the panel's last row now
            self.panel.invalidate()
        else:
            self._draw_bar()

    # ---------------------------------------------------------------- hallux's own panel

    def set_panel(self, panel: Panel) -> None:
        """Hand the panel over. From now on Ctrl+F12 opens it: at a prompt, while the AI
        works, and over a full-screen program. A terminal that has none ignores the key."""
        self.panel = self.block.panel = panel

    async def _visit_from_prompt(self) -> None:
        """The visit after Ctrl+F12 ended a prompt. What was typed behind Ctrl+F12 is the
        panel's, and what was typed behind the key that closed it is for the prompt."""
        store_typeahead(self.input, await self.visit_panel(get_typeahead(self.input)))

    async def visit_panel(self, keys: list) -> list:
        """One visit to the panel, with `keys` typed into it first. It is over when this
        returns: the panel's app is gone, the shell's screen and the bar are back, and what
        was written meanwhile is printed. Returns the keys typed after the one that closed
        the panel."""
        # A prompt_toolkit app feeds itself the keys that are stored for the next prompt when
        # it starts. Those were typed for the shell, so they are taken out for the visit.
        earlier = get_typeahead(self.input)
        store_typeahead(self.input, keys)
        if self.pinned:                                  # the panel has the whole screen,
            self._write("\x1b7\x1b[r\x1b8")              # as a full-screen program has
        self.kept = []                                   # from here on write() doesn't print
        try:
            await self.panel.run(self.input, self.output)    # on the alternate screen
        finally:
            kept, self.kept = self.kept, None
            after = get_typeahead(self.input)
            store_typeahead(self.input, earlier)
            self._check_size()                           # the window may have another size now
            self._draw_bar()                             # pins the region again, before any text:
            for text in kept:                            # unpinned, the text would scroll the
                self.write(text)                         # bar's row away and end up on it
        return after

    # ---------------------------------------------------------------- block mode

    async def show_form(self, screen: str, form: Form, patch=None) -> None:
        if self.pinned and not self.block.active:        # the full-screen app has its own bar
            self._write("\x1b7\x1b[r\x1b8")
        await self.block.show(screen, form, patch)

    async def next_action(self) -> Action:
        return await self.block.next_action()

    def keep_form(self, tick: float | None = None) -> None:
        self.block.keep_form(tick)

    def set_tick(self, seconds: float) -> None:
        self.block.set_tick(seconds)

    async def end_form(self) -> None:
        if self.block.active:
            await self.block.end()
            self._draw_bar()                             # re-pins the scroll region

    def field_text(self, id: str) -> str:
        return self.block.field_text(id)

    def field_saved(self, id: str) -> None:
        self.block.field_saved(id)

    def _block_ctrl_c(self, waiting: bool) -> bool:
        self.count_ctrl_c()
        if waiting and self.interrupt:                   # the AI is busy with this screen
            self.interrupt()
            return True
        return False

    # ---------------------------------------------------------------- the hard exit

    def count_ctrl_c(self) -> None:
        now = time.monotonic()
        self.ctrl_c_times.append(now)
        if len(self.ctrl_c_times) == CTRL_C_PRESSES and now - self.ctrl_c_times[0] <= CTRL_C_WINDOW:
            self.power_cut()

    def power_cut(self) -> None:
        log.warning("power cut: hard exit by key")
        with contextlib.suppress(Exception):             # nothing may keep the plug in
            self.before_power_cut()
        self.on_power_cut()

    def _pull_the_plug(self) -> NoReturn:
        """Quit now: stop the model, give the terminal back as it was, exit."""
        _stop_children()
        with contextlib.suppress(Exception):
            sys.stdout.flush()
        if self.saved_tty is not None:
            with contextlib.suppress(Exception):
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.saved_tty)
        rows = self.output.get_size().rows
        restore = RESTORE_TERMINAL + (statusbar.uninstall(rows) if self.pinned else "")
        with contextlib.suppress(OSError):
            os.write(sys.stdout.fileno(), (restore + "\r\n").encode())
            os.write(sys.stderr.fileno(), b"hallux: power cut\r\n")
        os._exit(130)

    # ---------------------------------------------------------------- drawing the bar

    def _draw_bar(self) -> None:
        if codes := self._bar_codes():
            self._write(codes)

    def _bar_codes(self) -> str:
        if not self.pinned or self.block.active or self.kept is not None:
            return ""
        size = self.output.get_size()
        return statusbar.draw(self.bar, size.rows, size.columns)

    def _check_size(self) -> None:
        """After a resize: move the bar to the new bottom row and re-pin the region."""
        if not self.pinned or self.block.active or self.kept is not None:
            return
        size = self.output.get_size()
        if size != self.pinned:
            if size.rows > self.pinned.rows:             # the old bar row is now screen
                self._write(f"\x1b7\x1b[{self.pinned.rows};1H\x1b[0m\x1b[2K\x1b8")
            self.pinned = size
            self._draw_bar()

    def _write(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()


class _NoEcho(Processor):
    """Shows nothing of the typed line, and keeps the cursor where the prompt ends."""

    def apply_transformation(self, transformation_input: TransformationInput) -> Transformation:
        return Transformation([], source_to_display=lambda i: 0, display_to_source=lambda i: 0)


class _BarKeepingOutput(Vt100_Output):
    """prompt_toolkit's output for the shell prompt.

    Before it draws the prompt, prompt_toolkit erases everything below the cursor, and that
    reaches the bar's row too (a scroll region doesn't protect a row from erasing). So every
    erase repaints the bar in the same write: no flicker, and the bar is always there.
    """

    def __init__(self, stdout, get_size, term, bar: Callable[[], str]) -> None:
        super().__init__(stdout, get_size, term=term)
        self.bar = bar

    def erase_down(self) -> None:
        super().erase_down()
        self.write_raw(self.bar())

    def erase_screen(self) -> None:
        super().erase_screen()
        self.write_raw(self.bar())


def _tty_settings() -> list | None:
    try:
        import termios
        return termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        return None


def _stop_children() -> None:
    """Stop the Claude Code process the SDK started (Linux: found through /proc)."""
    me = f"PPid:\t{os.getpid()}\n"
    for status in Path("/proc").glob("[0-9]*/status"):
        with contextlib.suppress(OSError, ValueError):
            if me in status.read_text():
                os.kill(int(status.parent.name), signal.SIGTERM)
