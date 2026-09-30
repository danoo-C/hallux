"""Block mode: full-screen programs the way an IBM 3270 terminal ran them.

The AI draws the whole screen and declares editable fields on it. The terminal lets you
type, move and scroll inside the fields by itself, and only goes back to the AI when you
press one of the form's action keys or click outside the fields. Every character on screen
is the AI's, except what you type into its fields.
"""
from __future__ import annotations

import asyncio
import re
from typing import Callable

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.document import Document
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.filters import Condition, vi_navigation_mode
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import DynamicKeyBindings, KeyBindings
from prompt_toolkit.key_binding.bindings.scroll import scroll_page_down, scroll_page_up
from prompt_toolkit.layout import DynamicContainer, Float, FloatContainer, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from hallux.protocol import Action, Field, FieldState, Form

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


class Background(FormattedTextControl):
    """The AI's screen behind the fields. Clicks on it go to the AI."""

    def __init__(self, screen: str, on_click: Callable[[int, int], None]):
        super().__init__(ANSI(screen), focusable=False)
        self.on_click = on_click

    def mouse_handler(self, mouse_event: MouseEvent):
        if mouse_event.event_type == MouseEventType.MOUSE_UP:
            self.on_click(mouse_event.position.y + 1, mouse_event.position.x + 1)
            return None
        return NotImplemented


class BlockMode:
    def __init__(self, input=None, output=None) -> None:      # tests pass a pipe and a dummy
        self.input, self.output = input, output
        self.app: Application | None = None
        self.running: asyncio.Task | None = None
        self.form: Form | None = None
        self.areas: dict[str, TextArea] = {}
        self.kinds: dict[str, tuple] = {}             # what each area was built for
        self.seen: dict[str, str | None] = {}          # the text the AI has seen, per field
        self.baseline: dict[str, str] = {}             # the text when loaded, set or saved
        self.container = Window()
        self.bindings = KeyBindings()
        self.waiting = False                           # an action is with the AI
        self.actions: asyncio.Queue[Action] = asyncio.Queue()
        self.held: list = []                           # keys typed while the AI thinks
        self.cut = ""                                  # nano's cut buffer

    @property
    def active(self) -> bool:
        return self.app is not None

    # ---------------------------------------------------------------- the AI's side

    async def show(self, screen: str, form: Form) -> None:
        """Show a form, or update the one on screen. Fields whose text is None keep theirs."""
        self.form = form
        self._build_areas(form)
        self.container = self._layout(screen, form)
        self.bindings = self._key_bindings(form)
        if self.app is None:
            self.app = Application(
                layout=Layout(DynamicContainer(lambda: self.container)),
                key_bindings=DynamicKeyBindings(lambda: self.bindings),
                full_screen=True, mouse_support=True, input=self.input, output=self.output)
            self.running = asyncio.create_task(self.app.run_async(handle_sigint=False))
            processor = self.app.key_processor         # keys typed while the AI thinks wait
            process_keys = processor.process_keys      # in the queue for the next screen
            processor.process_keys = lambda: None if self.waiting else process_keys()
        self.app.editing_mode = EditingMode.VI if form.keymap == "vi" else EditingMode.EMACS
        focus = self.areas.get(form.focus or "") or next(
            (self.areas[f.id] for f in form.fields if f.kind != "pager"), self.areas[form.fields[0].id])
        self.app.layout.focus(focus)
        self.waiting = False
        await self._drawn()
        self._release_keys()
        self.app.key_processor.process_keys()           # type-ahead goes into the new form

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
        """Wait for an action key or a click. Raises EOFError if the full-screen app died."""
        getter = asyncio.ensure_future(self.actions.get())
        done, _ = await asyncio.wait({getter, self.running}, return_when=asyncio.FIRST_COMPLETED)
        if getter in done:
            return getter.result()
        getter.cancel()
        self.running.result()                          # re-raises whatever killed the app
        raise EOFError("block mode ended")

    async def end(self) -> None:
        """Leave block mode: the shell screen comes back."""
        if self.app is None:
            return
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
        self.waiting = False

    def field_text(self, id: str) -> str:
        if id not in self.areas:
            raise ValueError(f"no field {id!r} on the screen")
        return self.areas[id].text

    def field_saved(self, id: str) -> None:
        self.baseline[id] = self.field_text(id)

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

    def _layout(self, screen: str, form: Form) -> FloatContainer:
        size = lambda: get_app().output.get_size()                   # noqa: E731
        floats = []
        for f in form.fields:
            width = f.width or (lambda f=f: max(1, size().columns - f.left + 1))
            height = f.height or (lambda f=f: max(1, size().rows - f.top + 1))
            floats.append(Float(content=self.areas[f.id], top=f.top - 1, left=f.left - 1,
                                width=width, height=height))
        background = Window(Background(screen, self._click), wrap_lines=False)
        return FloatContainer(content=background, floats=floats)

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
            self._send(Action(key=name, focus=getattr(self._focused(), "id", None)))
        return handle

    def _click(self, row: int, col: int) -> None:
        self._send(Action(key="click", focus=getattr(self._focused(), "id", None), row=row, col=col))

    def _send(self, action: Action) -> None:
        if self.waiting or self.form is None:
            return
        self.waiting = True
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
        self.actions.put_nowait(Action(action.key, action.focus, tuple(states), action.row, action.col))
        queue = self.app.key_processor.input_queue    # keys typed right after the action key
        self.held, _ = list(queue), queue.clear()      # wait for the AI's next screen

    def _release_keys(self) -> None:
        self.app.key_processor.input_queue.extendleft(reversed(self.held))
        self.held = []
