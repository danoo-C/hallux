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
from pathlib import Path
from typing import AsyncIterator, Callable, NoReturn

from prompt_toolkit import PromptSession
from prompt_toolkit.application import get_app
from prompt_toolkit.data_structures import Size
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import create_input
from prompt_toolkit.input.typeahead import store_typeahead
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import create_output
from prompt_toolkit.output.vt100 import Vt100_Output

from hallux import statusbar
from hallux.blockmode import POWER_CUT_KEY, BlockMode
from hallux.machine import Key
from hallux.protocol import Action, Form
from hallux.statusbar import StatusBar

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


class Terminal:
    def __init__(self, bar: StatusBar | None = None, input=None, output=None,
                 power_cut: Callable[[], None] | None = None) -> None:
        self.bar = bar                                   # None: no status bar
        self.status_bar = bar is not None
        self.real_tty = input is None and output is None and sys.stdin.isatty()
        self.input = input or create_input()
        self.output = output or create_output()          # the whole screen (block mode)
        self.saved_tty = _tty_settings() if self.real_tty else None
        self.on_power_cut = power_cut or self._pull_the_plug
        self.ctrl_c_times: deque[float] = deque(maxlen=CTRL_C_PRESSES)
        self.interrupt: Callable[[], None] | None = None     # stops the AI's current turn
        self.pinned: Size | None = None                  # the screen size the bar is pinned for
        self.raw = contextlib.ExitStack()                # raw mode for the whole session

        self.session: PromptSession = PromptSession(
            history=InMemoryHistory(), key_bindings=self._prompt_keys(), input=self.input,
            output=self._prompt_output())
        self.session.app.after_render += lambda _: self._check_size()
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

    async def read_line(self, prompt: str, default: str = "") -> str | Key:
        self.session.app.erase_when_done = False
        return await self.session.prompt_async(ANSI(zero_width(prompt)), default=default)

    def write(self, text: str) -> None:
        if self.bar:
            text = statusbar.strip_layout_codes(text)    # the bar's rows are hallux's business
        self._write(text)
        self._draw_bar()                                 # `clear` erases it; bring it back

    def size(self) -> tuple[int, int]:
        size = self.output.get_size()
        return size.columns, size.rows - (1 if self.bar else 0)

    def _prompt_keys(self) -> KeyBindings:
        keys = KeyBindings()
        for key, (name, echo) in LINE_ENDING.items():
            keys.add(key, eager=True)(self._line_ending(name, echo))
        empty = Condition(lambda: get_app().current_buffer.text == "")
        keys.add("c-d", filter=empty, eager=True)(self._line_ending("C-d", ""))
        for key, name in IN_PLACE.items():
            keys.add(*key, eager=True)(self._in_place(name))
        keys.add(POWER_CUT_KEY, eager=True)(lambda event: self.power_cut())
        return keys

    def _line_ending(self, name: str, echo: str) -> Callable:
        def handle(event) -> None:
            if name == "C-c":
                self.count_ctrl_c()
            buf = event.app.current_buffer
            line, cursor = buf.text, buf.cursor_position
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
                    for press in self.input.read_keys():
                        if press.key == POWER_CUT_KEY:
                            self.power_cut()
                        elif press.key == Keys.ControlC:
                            self.count_ctrl_c()
                            interrupt()
                        elif press.key != Keys.CPRResponse:
                            typed.append(press)          # type-ahead for the next prompt
                watching.enter_context(self.input.attach(read))
            try:
                yield
            finally:
                animation.cancel()
                self.interrupt = None
                store_typeahead(self.input, typed)
                if self.bar:
                    self.bar.update(busy=False)
                    self._refresh()

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
        else:
            self._draw_bar()

    # ---------------------------------------------------------------- block mode

    async def show_form(self, screen: str, form: Form) -> None:
        if self.pinned and not self.block.active:        # the full-screen app has its own bar
            self._write("\x1b7\x1b[r\x1b8")
        await self.block.show(screen, form)

    async def next_action(self) -> Action:
        return await self.block.next_action()

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
        if not self.pinned or self.block.active:
            return ""
        size = self.output.get_size()
        return statusbar.draw(self.bar, size.rows, size.columns)

    def _check_size(self) -> None:
        """After a resize: move the bar to the new bottom row and re-pin the region."""
        if not self.pinned or self.block.active:
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
