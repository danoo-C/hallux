"""Block mode: full-screen programs the way an IBM 3270 terminal ran them.

The AI draws the whole screen and declares editable fields on it. The terminal lets you
type, move and scroll inside the fields by itself, and only goes back to the AI when you
press one of the form's action keys or click outside the fields. Every character on screen
is the AI's, except what you type into its fields.
"""
from __future__ import annotations

import asyncio
import contextlib
import html
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Callable

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.document import Document
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.filters import Condition, vi_navigation_mode
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import DynamicKeyBindings, KeyBindings
from prompt_toolkit.key_binding.bindings.scroll import scroll_page_down, scroll_page_up
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import (
    ConditionalContainer, DynamicContainer, Float, FloatContainer, HSplit, Layout, Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.widgets import TextArea

from hallux.protocol import Action, Field, FieldState, Form, plain
from hallux.statusbar import StatusBar

if TYPE_CHECKING:
    from hallux.panel import Panel             # block mode is handed one; it never imports it

POWER_CUT_KEY = "c-s-delete"                   # the hard exit: Ctrl+Shift+Del
OPEN_KEY = "c-f12"                             # opens and closes hallux's own panel (hallux.panel)
ESCAPE_SECONDS = 0.05                          # in the panel: how long Esc waits to be told from
                                               # the start of an arrow key

SPECIAL_KEYS = {
    "Enter": "enter", "Escape": "escape", "Tab": "tab", "Backspace": "backspace",
    "Delete": "delete", "Insert": "insert", "Up": "up", "Down": "down", "Left": "left",
    "Right": "right", "Home": "home", "End": "end", "PageUp": "pageup", "PageDown": "pagedown",
    "Space": " ",
}


def key_sequence(name: str) -> tuple[str, ...] | None:
    """The prompt_toolkit keys for a key name from a form: "C-o", "M-u", "F1", "q", "PageUp"."""
    if name in SPECIAL_KEYS:
        return (SPECIAL_KEYS[name],)
    if re.fullmatch(r"C-[a-zA-Z@\\\]^_]", name):
        return ("c-" + name[2:].lower(),)
    if re.fullmatch(r"M-\S", name):                   # Alt/Meta: the terminal sends Escape first
        return ("escape", name[2:].lower())
    if re.fullmatch(r"F([1-9]|1[0-9]|2[0-4])", name):
        return (name.lower(),)
    if len(name) == 1 and name.isprintable():
        return (name,)
    return None


KEY_NAMES = {code: name for name, code in SPECIAL_KEYS.items() if name != "Space"}
KEY_NAMES |= {"c-m": "Enter", "c-i": "Tab", "c-h": "Backspace", "s-tab": "S-Tab"}
NOT_KEYS = {Keys.Vt100MouseEvent, Keys.CPRResponse, Keys.ScrollUp, Keys.ScrollDown,
            Keys.WindowsMouseEvent, Keys.Ignore}


def key_event(press) -> tuple[str, str] | None:
    """A key press as raw mode sends it: ("text", "j") or ("key", "C-Up"); None for non-keys."""
    if press.key in NOT_KEYS:
        return None
    if press.key == Keys.BracketedPaste:
        return "text", press.data
    code = press.key.value if isinstance(press.key, Keys) else press.key
    if len(code) == 1 and code.isprintable():
        return "text", code
    return "key", _key_name(code)


def _key_name(code: str) -> str:
    if code in KEY_NAMES:
        return KEY_NAMES[code]
    if re.fullmatch(r"f\d+", code):
        return code.upper()
    for prefix, name in (("c-s-", "C-S-"), ("c-", "C-"), ("s-", "S-")):
        if code.startswith(prefix):
            rest = code[len(prefix):]
            return name + KEY_NAMES.get(rest, rest)
    return code


def render_events(presses) -> tuple[str, ...]:
    """Key presses as events for the AI; typed text is joined: <text>jj</text><key>Up</key>."""
    events, text = [], ""
    for press in presses:
        event = key_event(press)
        if event is None:
            continue
        kind, value = event
        if kind == "text":
            text += value
            continue
        if text:
            events.append(f"<text>{html.escape(text, quote=False)}</text>")
            text = ""
        events.append(f"<key>{value}</key>")
    if text:
        events.append(f"<text>{html.escape(text, quote=False)}</text>")
    return tuple(events)


def _lexer(lang: str | None) -> PygmentsLexer | None:
    if not lang:
        return None
    try:
        from pygments.lexers import get_lexer_by_name
        return PygmentsLexer(type(get_lexer_by_name(lang)))
    except Exception:                                  # no pygments, or an unknown language
        return None


def _style(style: str) -> str:
    """The AI's style string if prompt_toolkit understands it, else nothing (never a crash)."""
    try:
        Style([("x", style)]).get_attrs_for_style_str("class:x")
        return style
    except Exception:
        return ""


SGR_RESET = re.compile(r"\x1b\[0?m")


def _blank(line: str) -> bool:
    """Nothing to see: only spaces (any other escape code, like a colored bar, counts)."""
    return not SGR_RESET.sub("", line).strip()


def _pad(line: str, columns: int) -> str:
    """A screen row padded with spaces to the screen's width (colors reset first)."""
    width = get_cwidth(plain(line))
    return line + "\x1b[0m" + " " * (columns - width) if width < columns else line


def fit_screen(lines: list[str], footer: list[str], rows: int,
               fields: list[Field]) -> tuple[list[str], dict[str, int]]:
    """Lay the AI's screen out on exactly `rows` rows. Returns the rows and each field's top.

    The footer is pinned to the bottom, so the AI never has to count rows. If the screen is
    still too tall (models miscount), blank rows that no field covers are dropped from the
    bottom up, and fields below them move up with the text they belong to. If that isn't
    enough, the screen is cut short: the footer, with its keys, always stays.
    """
    footer = footer[-rows:]
    room = rows - len(footer)
    covered = set()
    for f in fields:
        if f.top > 0:
            height = f.height or max(1, room - f.top + 1)
            covered.update(range(f.top, f.top + height))
    excess = len(lines) - room
    dropped = []
    for row in range(len(lines), 0, -1):
        if excess <= 0:
            break
        if row not in covered and _blank(lines[row - 1]):
            dropped.append(row)
            excess -= 1
    kept = [line for row, line in enumerate(lines, 1) if row not in dropped][:room]
    screen = kept + [""] * (room - len(kept)) + footer
    tops = {}
    for f in fields:
        if f.top < 0:                                  # counted from the bottom
            tops[f.id] = max(1, rows + f.top + 1)
        else:
            tops[f.id] = max(1, f.top - sum(1 for row in dropped if row < f.top))
    return screen, tops


class Background(FormattedTextControl):
    """The AI's screen behind the fields. Clicks on it go to the AI (in raw mode, the wheel too)."""

    def __init__(self, screen: str, on_click: Callable[[str, int, int], None], raw: bool = False):
        super().__init__(ANSI(screen), focusable=raw)  # in raw mode it holds the focus itself
        self.on_click, self.raw = on_click, raw

    def mouse_handler(self, mouse_event: MouseEvent):
        row, col = mouse_event.position.y + 1, mouse_event.position.x + 1
        if mouse_event.event_type == MouseEventType.MOUSE_UP:
            self.on_click("left", row, col)
            return None
        if self.raw and mouse_event.event_type in (MouseEventType.SCROLL_UP, MouseEventType.SCROLL_DOWN):
            self.on_click("wheel-up" if mouse_event.event_type == MouseEventType.SCROLL_UP
                          else "wheel-down", row, col)
            return None
        return NotImplemented


class BlockMode:
    def __init__(self, input=None, output=None, bar: StatusBar | None = None,
                 power_cut: Callable[[], None] = lambda: None,
                 ctrl_c: Callable[[bool], bool] = lambda waiting: False) -> None:
        self.input, self.output = input, output         # tests pass a pipe and a dummy
        self.bar = bar                                  # hallux's status bar, the bottom row
        self.power_cut = power_cut                      # the hard exit
        self.ctrl_c = ctrl_c                            # every Ctrl-C; True means "consumed"
        self.app: Application | None = None
        self.running: asyncio.Task | None = None
        self.form: Form | None = None
        self.areas: dict[str, TextArea] = {}
        self.kinds: dict[str, tuple] = {}             # what each area was built for
        self.seen: dict[str, str | None] = {}          # the text the AI has seen, per field
        self.seen_before: dict[str, str | None] | None = None   # ... before the action on its way
        self.baseline: dict[str, str] = {}             # the text when loaded, set or saved
        self.container = Window()
        self.background: Window | None = None          # the screen behind the fields
        self.composed: list[str] | None = None         # that screen, row by row, as shown
        self.footer_rows = 0                           # how many of its rows are the footer
        self.field_tops: dict[str, tuple[int, int]] = {}   # id: (top as given, row on screen)
        self.bindings = KeyBindings()
        self.waiting = False                           # an action is with the AI
        self.actions: asyncio.Queue[Action] = asyncio.Queue()
        self.held: list = []                           # keys typed while the AI thinks
        self.cut = ""                                  # nano's cut buffer
        self.panel: Panel | None = None                # hallux's own panel, once handed over
        self.layered = False                           # it is open, as a layer over the program
        self.layer_gone = asyncio.Event()              # ... and set when it isn't
        self.layer_gone.set()
        self.under: tuple = ()                         # what the program had before the layer
        self.clock = asyncio.Event()                   # set: the wait for a tick starts again

    @property
    def active(self) -> bool:
        return self.app is not None

    # ---------------------------------------------------------------- the AI's side

    async def show(self, screen: str, form: Form,
                   patch: tuple[tuple[int, tuple[str, ...]], ...] | None = None) -> None:
        """Show a form, or update the one on screen. Fields whose text is None keep theirs.
        With a patch, only those rows of the screen on display change."""
        form = replace(form, fields=tuple(f.with_defaults() for f in form.fields))
        self.form = form
        self.seen_before = None                         # the AI answered: it has seen the action
        self._build_areas(form)
        self.container = self._layout(screen, form, patch)
        self.bindings = self._key_bindings(form)
        if self.app is None:
            self.app = Application(
                layout=Layout(DynamicContainer(lambda: self.container)),
                key_bindings=DynamicKeyBindings(         # under the panel, the keys are its own
                    lambda: self.panel.bindings if self.layered else self.bindings),
                full_screen=True, mouse_support=True, input=self.input, output=self.output)
            self.running = asyncio.create_task(self.app.run_async(handle_sigint=False))
            self.running.add_done_callback(lambda task: self._close_panel())   # it died
            processor = self.app.key_processor         # keys typed while the AI thinks wait
            self.process_keys = processor.process_keys     # in the queue for the next screen,
            processor.process_keys = lambda: (             # unless they are typed into the panel
                self._hold_keys() if self.waiting and not self.layered else self.process_keys())
        self.app.editing_mode = EditingMode.VI if form.keymap == "vi" else EditingMode.EMACS
        if form.fields:
            focus = self.areas.get(form.focus or "") or next(
                (self.areas[f.id] for f in form.fields if f.kind != "pager"),
                self.areas[form.fields[0].id])
        else:
            focus = self.background
        self.app.layout.focus(focus)
        self.waiting = False
        await self._drawn()
        self._take_held_keys()

    def _take_held_keys(self) -> None:
        """The form takes keys again, and first what was typed while it waited."""
        if self.form.raw and self.held:                 # raw mode: what was typed meanwhile
            held, self.held = self.held, []             # goes to the AI as one batch
            self._send_events(held)
        else:
            self._release_keys()
            self.app.key_processor.process_keys()       # type-ahead goes into the form

    async def _drawn(self) -> None:
        """Wait until the new screen is on display: clicks only reach what has been drawn."""
        drawn = asyncio.get_running_loop().create_future()

        def after_render(_) -> None:
            if not drawn.done():
                drawn.set_result(None)

        self.app.after_render += after_render
        self.app.invalidate()
        try:
            await asyncio.wait({drawn, self.running}, timeout=2,
                               return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.app.after_render -= after_render

    async def next_action(self) -> Action:
        """Wait for an action key or a click; in raw mode with a tick, at most `tick` seconds,
        then return a tick. Raises EOFError if the full-screen app died."""
        getter = asyncio.ensure_future(self.actions.get())
        while True:                                     # once more whenever the clock restarts
            self.clock.clear()
            ticks = self.form is not None and self.form.raw and not self.layered
            tick = self.form.tick if ticks else 0       # under the panel a tick waits
            restart = asyncio.ensure_future(self.clock.wait())
            done, _ = await asyncio.wait({getter, self.running, restart}, timeout=tick or None,
                                         return_when=asyncio.FIRST_COMPLETED)
            restart.cancel()
            if getter in done:
                return getter.result()
            if self.running in done:
                getter.cancel()
                self.running.result()                  # re-raises whatever killed the app
                raise EOFError("block mode ended")
            if not done:                                # nothing happened: time for a tick
                getter.cancel()
                self.waiting = True                     # keys pressed now wait for the redraw
                return Action(key="tick", focus=None)

    def set_tick(self, seconds: float) -> None:
        """Give the program on screen this tick. A wait that is running starts again with it."""
        if self.form is not None:
            self.form = replace(self.form, tick=seconds)
            self.clock.set()

    def keep_form(self, tick: float | None = None) -> None:
        """The action that came back never reached the AI: the form stays as it is and takes
        keys again. What it reported of the fields counts as not seen, so the next action
        reports it once more. With a tick, that is the form's tick from now on."""
        if self.app is None or self.form is None:
            return
        if self.seen_before is not None:
            self.seen, self.seen_before = self.seen_before, None
        if tick is not None:
            self.form = replace(self.form, tick=tick)
        self.waiting = False
        self._take_held_keys()

    async def end(self) -> None:
        """Leave block mode: the shell screen comes back."""
        if self.app is None:
            return
        self._close_panel()                            # it can't stay open over nothing
        self._release_keys()                           # prompt_toolkit keeps unprocessed keys
        if self.app.is_running:                        # as type-ahead for the shell prompt
            self.app.exit()
        elif not self.running.done():
            self.running.cancel()
        try:
            await self.running
        except (asyncio.CancelledError, EOFError):
            pass
        self.app = self.running = self.form = None
        self.areas, self.kinds, self.seen, self.baseline = {}, {}, {}, {}
        self.seen_before = None
        self.composed, self.footer_rows, self.field_tops = None, 0, {}
        self.waiting = False

    def invalidate(self) -> None:
        if self.app is not None:
            self.app.invalidate()

    def field_text(self, id: str) -> str:
        if id not in self.areas:
            raise ValueError(f"no field {id!r} on the screen")
        return self.areas[id].text

    def field_saved(self, id: str) -> None:
        self.baseline[id] = self.field_text(id)

    # ---------------------------------------------------------------- hallux's own panel

    def open_panel(self) -> None:
        """Ctrl+F12: the panel as a layer over the program. The program's screen, its fields
        and their cursors stay under it, untouched. The keys and the focus are the panel's,
        and typing is plain typing, whatever the program's keys are: over vi keys in normal
        mode a model's name would run as commands."""
        if self.panel is None or self.layered or self.app is None or self.running.done():
            return
        app = self.app
        self.under = (app.layout.current_window, app.editing_mode, app.ttimeoutlen)
        self.layered = True
        self.layer_gone.clear()
        app.editing_mode, app.ttimeoutlen = EditingMode.EMACS, ESCAPE_SECONDS
        self.panel.on_close = self._close_panel        # Esc, Ctrl+F12 or its Close button
        self.panel.open()                              # takes the focus
        self.clock.set()                               # a tick that is due waits
        app.invalidate()

    def _close_panel(self) -> None:
        """The layer goes: the program has its keys, its focus and its way of editing again,
        in the mode it was in. Also when the full-screen app ends under the panel."""
        if not self.layered:
            return
        self.layered = False
        self.panel.on_close = None
        self.panel.close()                             # when it wasn't the panel that closed
        focus, editing_mode, ttimeoutlen = self.under
        if self.app is not None:
            self.app.editing_mode, self.app.ttimeoutlen = editing_mode, ttimeoutlen
            with contextlib.suppress(ValueError):      # the app has ended
                self.app.layout.focus(focus)
            self.app.invalidate()
        self.layer_gone.set()
        self.clock.set()                               # the program's clock starts again

    async def panel_gone(self) -> None:
        """Wait until the panel isn't open over the program: the end of an answer waits here."""
        await self.layer_gone.wait()

    # ---------------------------------------------------------------- building the screen

    def _build_areas(self, form: Form) -> None:
        areas = {}
        for f in form.fields:
            shape = (f.kind, f.style, f.lang)
            area = self.areas.get(f.id)
            if area is None or self.kinds.get(f.id) != shape:
                kept = area.text if area is not None else ""
                area = self._new_area(f)
                area.buffer.set_document(Document(kept, len(kept)), bypass_readonly=True)
                self.kinds[f.id] = shape
                self.seen.setdefault(f.id, kept)
                self.baseline.setdefault(f.id, kept)
            if f.text is not None:                      # new text from the AI or from a file
                start = len(f.text) if f.kind == "line" else 0     # type after a line's text
                area.buffer.set_document(Document(f.text, start), bypass_readonly=True)
                self.seen[f.id] = None if f.file else f.text   # the AI never saw file text
                self.baseline[f.id] = f.text
            if f.cursor is not None:
                doc = area.buffer.document
                row = min(f.cursor[0] - 1, doc.line_count - 1)
                col = min(f.cursor[1] - 1, len(doc.lines[row]))
                area.buffer.cursor_position = doc.translate_row_col_to_index(row, col)
            areas[f.id] = area
        self.areas = areas

    def _new_area(self, f: Field) -> TextArea:
        editable = Condition(lambda: not self.waiting)
        return TextArea(
            multiline=f.kind != "line",
            read_only=True if f.kind == "pager" else ~editable,
            wrap_lines=f.kind == "pager",
            lexer=_lexer(f.lang),
            style=_style(f.style),
            focus_on_click=True,
        )

    def _layout(self, screen: str, form: Form,
                patch: tuple[tuple[int, tuple[str, ...]], ...] | None = None) -> FloatContainer:
        size = lambda: get_app().output.get_size()                   # noqa: E731
        bar_rows = 1 if self.bar else 0
        rows = max(1, self._screen_size().rows - bar_rows)
        lines = screen.split("\n")
        footer = (form.footer or "").split("\n") if form.footer else []
        for part in (lines, footer):
            if part and part[-1] == "":                # the newline that ends the last row
                part.pop()
        if patch is None or self.composed is None and not patch:
            body, tops = fit_screen(lines, footer, rows, list(form.fields))
            self.footer_rows = len(footer)
        else:
            body = self._patched(rows, footer if form.footer else None, patch)
            tops = {f.id: self._row_of(f, rows) for f in form.fields}
        self.composed = body
        self.field_tops = {f.id: (f.top, tops[f.id]) for f in form.fields}
        footer_rows = self.footer_rows
        floats = []
        for f in form.fields:
            top = tops[f.id]
            width = f.width or (lambda f=f: max(1, size().columns - f.left + 1))
            height = f.height or (lambda top=top: max(1, rows - footer_rows - top + 1))
            floats.append(Float(content=self.areas[f.id], top=top - 1, left=f.left - 1,
                                width=width, height=height))
        columns = self._screen_size().columns              # padded to the full rectangle, so
        body = [_pad(line, columns) for line in body]      # a click anywhere maps exactly
        background = Window(Background("\n".join(body), self._click, raw=form.raw), wrap_lines=False)
        self.background = background
        if self.panel is not None:                         # the panel, over all of the program
            layer = ConditionalContainer(self.panel.container, Condition(lambda: self.layered))
            floats.append(Float(content=layer, top=0, bottom=0, left=0, right=0, z_index=9))
        screen_area = FloatContainer(content=background, floats=floats)
        if self.bar is None:
            return screen_area
        bar = FormattedTextControl(lambda: self.bar.fragments(size().columns))
        return HSplit([screen_area, Window(bar, height=1)])

    def _patched(self, rows: int, footer: list[str] | None,
                 patch: tuple[tuple[int, tuple[str, ...]], ...]) -> list[str]:
        """The screen on display with a patch applied: whole rows replaced, top or bottom
        counted. After a resize, the stored screen is fitted again first."""
        body = list(self.composed or [""] * rows)
        if len(body) != rows:
            cut = len(body) - self.footer_rows
            body, _ = fit_screen(body[:cut], body[cut:], rows, [])
        if footer is not None:                          # a new footer replaces the old one
            body = body[:rows - self.footer_rows] + [""] * self.footer_rows
            body = body[:rows - len(footer)] + footer[-rows:]
            self.footer_rows = len(footer)
        for first, block in patch:
            start = first if first > 0 else rows + first + 1
            for row, line in enumerate(block, start):
                if 1 <= row <= rows:
                    body[row - 1] = line
        return body

    def _row_of(self, field: Field, rows: int) -> int:
        """Where a field sits on a patched screen: where it was, if its top didn't change."""
        given, shown = self.field_tops.get(field.id, (None, None))
        if given == field.top and shown is not None:
            return shown
        return field.top if field.top > 0 else max(1, rows + field.top + 1)

    def _screen_size(self):
        output = self.app.output if self.app is not None else self.output
        if output is None:
            import shutil
            columns, rows = shutil.get_terminal_size()
            return type("Size", (), {"rows": rows, "columns": columns})
        return output.get_size()

    # ---------------------------------------------------------------- keys and clicks

    def _focused(self) -> Field | None:
        if self.app is None or self.form is None:
            return None
        for f in self.form.fields:
            if f.id in self.areas and self.app.layout.has_focus(self.areas[f.id]):
                return f
        return None

    def _key_bindings(self, form: Form) -> KeyBindings:
        kb = KeyBindings()
        if form.raw:                                    # every key goes to the AI
            # not eager: an eager catch-all would also swallow mouse events before the mouse
            # bindings see them (eager matches win over more specific ones)
            kb.add(Keys.Any)(lambda event: self._send_events(event.key_sequence))
            kb.add(Keys.BracketedPaste, eager=True)(lambda event: self._send_events(event.key_sequence))

            @kb.add("c-c", eager=True)
            def _ctrl_c(event) -> None:
                if not self.ctrl_c(False):
                    self._send_events(event.key_sequence)

            kb.add(POWER_CUT_KEY, eager=True)(lambda e: self.power_cut())
            kb.add(OPEN_KEY, eager=True)(lambda e: self.open_panel())     # never the AI's
            return kb
        kind = lambda k: Condition(lambda: (f := self._focused()) is not None and f.kind == k)  # noqa: E731
        editor, line, pager = kind("editor"), kind("line"), kind("pager")

        if form.keymap == "nano":
            self._nano_keys(kb, editor & Condition(lambda: not self.waiting))
        for keys, scroll in [((" ",), scroll_page_down), (("pagedown",), scroll_page_down),
                             (("b",), scroll_page_up), (("pageup",), scroll_page_up)]:
            kb.add(*keys, filter=pager)(scroll)
        kb.add("g", filter=pager)(lambda e: setattr(e.current_buffer, "cursor_position", 0))
        kb.add("G", filter=pager)(lambda e: setattr(e.current_buffer, "cursor_position",
                                                    len(e.current_buffer.text)))

        kb.add(POWER_CUT_KEY, eager=True)(lambda e: self.power_cut())
        kb.add(OPEN_KEY, eager=True)(lambda e: self.open_panel())
        kb.add("enter", filter=line, eager=True)(self._action("Enter"))       # 3270 Enter
        if "Enter" in form.keys:                         # a pager as a menu: the cursor's
            kb.add("enter", filter=pager, eager=True)(self._action("Enter"))  # line is the pick
        printable_ok = pager | vi_navigation_mode        # letters type text in editors
        for name in dict.fromkeys((*form.keys, "C-c")):  # Ctrl-C always reaches the AI
            keys = key_sequence(name)
            if keys is None or name == "Enter":          # Enter never acts in an editor
                continue
            printable = len(keys) == 1 and len(keys[0]) == 1
            kb.add(*keys, filter=printable_ok if printable else Condition(lambda: True),
                   eager=True)(self._action(name))
        return kb

    def _nano_keys(self, kb: KeyBindings, editor: Condition) -> None:
        @kb.add("c-k", filter=editor, eager=True)
        def _cut_line(event) -> None:
            buf = event.current_buffer
            doc = buf.document
            start = doc.translate_row_col_to_index(doc.cursor_position_row, 0)
            end = start + len(doc.current_line) + (doc.cursor_position_row < doc.line_count - 1)
            buf.save_to_undo_stack()
            self.cut = buf.text[start:end]
            buf.document = Document(buf.text[:start] + buf.text[end:], start)

        kb.add("c-u", filter=editor, eager=True)(lambda e: e.current_buffer.insert_text(self.cut))
        kb.add("c-y", filter=editor, eager=True)(scroll_page_up)
        kb.add("c-v", filter=editor, eager=True)(scroll_page_down)
        kb.add("escape", "u", filter=editor, eager=True)(lambda e: e.current_buffer.undo())
        kb.add("escape", "e", filter=editor, eager=True)(lambda e: e.current_buffer.redo())

    def _action(self, name: str) -> Callable:
        def handle(event) -> None:
            if name == "C-c" and self.ctrl_c(False):
                return
            self._send(Action(key=name, focus=getattr(self._focused(), "id", None)))
        return handle

    def _click(self, button: str, row: int, col: int) -> None:
        if self.form is not None and self.form.raw:
            self._send(Action(key="keys", focus=None,
                              events=(f'<mouse button="{button}" row="{row}" col="{col}"/>',)))
        elif button == "left":
            self._send(Action(key="click", focus=getattr(self._focused(), "id", None),
                              row=row, col=col))

    def _send_events(self, presses) -> None:
        if events := render_events(presses):
            self._send(Action(key="keys", focus=None, events=events))

    def _send(self, action: Action) -> None:
        if self.waiting or self.form is None:
            return
        self.waiting = True
        self.seen_before = dict(self.seen)
        states = []
        for f in self.form.fields:
            doc = self.areas[f.id].buffer.document
            text = doc.text
            states.append(FieldState(
                id=f.id, text=text,
                cursor=(doc.cursor_position_row + 1, doc.cursor_position_col + 1),
                modified=text != self.baseline.get(f.id),
                changed=text != self.seen.get(f.id)))
            self.seen[f.id] = text                     # the AI is about to see it
        self.actions.put_nowait(Action(action.key, action.focus, tuple(states), action.row,
                                       action.col, action.events))
        self._hold_keys()                              # keys typed right after the action key

    def _hold_keys(self) -> None:
        """While the AI thinks, keys wait for its next screen. Only the hard exit, the panel's
        key and Ctrl-C (which can interrupt the AI) are acted on right away."""
        queue = self.app.key_processor.input_queue
        while queue:
            press = queue.popleft()
            if press.key == POWER_CUT_KEY:
                self.power_cut()
            elif press.key == OPEN_KEY and self.panel is not None:
                self.open_panel()
                return self.process_keys()             # what was typed behind it is the panel's
            elif press.key == "c-c" and self.ctrl_c(True):
                continue
            else:
                self.held.append(press)

    def _release_keys(self) -> None:
        self.app.key_processor.input_queue.extendleft(reversed(self.held))
        self.held = []
