"""The Config tab of hallux's own panel: the machine's settings, and how far its budgets are.

The tab knows nothing of the machine. It is given four functions: view() says what to show,
and change(name, text), save() and refill() do what the rows and the buttons ask for.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, ScrollOffsets, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from hallux import config
from hallux.config import EFFORTS, MODELS, View
from hallux.panel import Tab
from hallux.statusbar import GRAY, RED

LABELS = {                                    # every setting, in the order of its rows
    "model": "Model", "max_budget_usd": "Budget per boot", "tick_budget_usd": "Tick budget",
    "event_budget_usd": "Event budget", "effort": "Effort", "fallback_model": "Fallback model",
    "status_bar": "Status bar", "addons": "Addons", "keep_transcripts": "Transcripts",
    "os_sandbox": "OS sandbox",
}
GROUPS = {                                    # by when a change takes effect: config.WHEN
    "now": "Changes now", "reboot": "Changes at the machine's next reboot",
    "start": "Set when Hallux starts (edit config.toml)",
}
BUTTONS = ("Refill budgets", "Save", "Close")
BUDGETS = ("max_budget_usd", "tick_budget_usd", "event_budget_usd")
NAMES = ("model", "fallback_model")           # typed, with a list to pick from
INDENT, LABEL_WIDTH, VALUE_WIDTH = 4, 19, 18    # a model's name fits, with the cursor after it
NOTE, REFUSED, CURRENT = f"fg:{GRAY}", f"fg:{RED}", "reverse"
TYPED, SELECTED = "underline", "underline reverse"

Part = tuple[str, str, object]                # a style, a text, and what a click on it means


@dataclass
class State:
    """Where the user is in the tab."""
    at: int = 0                               # the stop the cursor is on: see stops()
    open: str | None = None                   # the setting whose row is open for a change
    typed: Buffer = field(default_factory=Buffer)    # the line of the open row
    selected: bool = False                    # all of it: the next thing typed takes its place
    refused: str | None = None                # why what was entered there wasn't taken
    answer: str = ""                          # what the last button said,
    failed: bool = False                      # and whether that was a refusal


@dataclass
class Drawn:
    rows: list[list[Part]]                    # the part that scrolls, line by line
    buttons: list[Part]                       # the line under it, which stays
    cursor: Point                             # in the rows: the line to keep in view


def stops() -> list[str]:
    """What the arrow keys move over, in order: the rows that change, then the buttons."""
    rows = [name for when in ("now", "reboot") for name in LABELS if config.WHEN[name] == when]
    return rows + list(BUTTONS)


def dollars(amount: float) -> str:
    """$0.25, and with all its digits where two aren't enough: $0.125."""
    text = f"{amount:.2f}"
    if float(text) != amount:
        text = f"{amount:.10f}".rstrip("0")
    return f"${text}"


def shown(name: str, value: object) -> str:
    """A setting's value as its row shows it."""
    if value is None:
        return "all that loaded" if name == "addons" else "none"
    if name in BUDGETS:
        return dollars(value)
    if name == "addons":
        return ", ".join(value) or "none"
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def entered(name: str, value: object) -> str:
    """The line a row opens with: its value as it would be typed. Nothing for none."""
    if value is None:
        return ""
    return dollars(value)[1:] if name in BUDGETS else str(value)


def choices(name: str, view: View) -> list[str]:
    """The list an open row offers to pick from. The other rows have none."""
    if name == "effort":
        return list(EFFORTS)
    if name not in NAMES:
        return []
    models = list(dict.fromkeys((*MODELS, view.running.model, view.hardware.model)))
    return ["none", *models] if name == "fallback_model" else models


def note(name: str, view: View) -> str:
    """What stands beside a row's value: what runs, what was spent, where the value is from."""
    hw, running, parts = view.hardware, view.running, []
    if name == "model" and running.model != hw.model:
        parts.append(f"running now: {running.model}")
    elif name == "effort" and running.model_effort != hw.effort:
        parts.append(f"running now: {running.model_effort or 'none'}")
    elif name == "max_budget_usd" and view.spent_since_refill != view.spent_boot:
        parts.append(f"spent since the refill: ${view.spent_since_refill:.2f} · "
                     f"this boot: ${view.spent_boot:.2f}")
    elif name == "max_budget_usd":
        parts.append(f"spent in this boot: ${view.spent_boot:.2f}")
    elif name == "tick_budget_usd" and view.spent_ticks is not None:
        parts.append(f"spent by this program: ${view.spent_ticks:.2f}")
    elif name == "event_budget_usd":
        parts.append(f"spent since you typed: ${view.spent_events:.2f}")
    if name in view.paused:
        parts.append(f"{parts.pop()} (paused)" if parts else "(paused)")
    if name in view.from_flags:
        parts.append(f"from --{name}, for this run")
    return " · ".join(parts)


def draw(view: View, state: State) -> Drawn:
    """The whole tab as text, from what the machine says and where the user is."""
    at = stops()[state.at]
    values = {name: shown(name, getattr(view.hardware, name)) for name in LABELS}
    width = max(VALUE_WIDTH, len(state.typed.text) + 1 if state.open else 0,
                *(len(values[name]) for name in LABELS if config.WHEN[name] != "start"))
    column = INDENT + LABEL_WIDTH                       # where the values start
    rows: list[list[Part]] = [[], [(NOTE, f"  {Path(*view.path.parts[-3:])}", None)]]
    cursor = Point(0, 0)
    for when, title in GROUPS.items():
        rows += [[], [("bold", f"  {title}", None)]]
        for name in (name for name in LABELS if config.WHEN[name] == when):
            label = f"{LABELS[name]:<{LABEL_WIDTH}}"
            if name != state.open:
                style = CURRENT if name == at else ""
                click = name if when != "start" else None
                rows.append([("", " " * INDENT, click), (style, label + values[name], click),
                             ("", " " * (width - len(values[name]) + 2), click),
                             (NOTE, note(name, view), click)])
                if name == at:
                    cursor = Point(0, len(rows) - 1)
                continue
            beside = ((REFUSED, state.refused) if state.refused
                      else (NOTE, _warning(name) or note(name, view)))
            line = state.typed.text
            rows.append([("", " " * INDENT, None), ("bold", label, None),
                         (SELECTED if state.selected else TYPED, line, None),
                         (TYPED, " " * (width - len(line)), None), ("", "  ", None),
                         (*beside, None)])
            cursor = Point(column + state.typed.cursor_position, len(rows) - 1)
            for choice in choices(name, view):
                is_it = entered(name, _meant(choice)) == state.typed.text
                rows.append([("", " " * (column - 2), None),
                             ("bold" if is_it else "", f"{'›' if is_it else ' '} {choice}",
                              ("pick", choice))])
    rows.append([])
    if at in BUTTONS and state.open is None:
        cursor = Point(0, len(rows) - 1)                # the end of the rows is in view
    buttons: list[Part] = [("", " " * INDENT, None)]
    for button in BUTTONS:
        style = CURRENT if button == at and state.open is None else ""
        buttons += [(style, f"[ {button} ]", button), ("", "   ", None)]
    if state.answer:
        buttons.append((REFUSED if state.failed else NOTE, f"   {state.answer}", None))
    elif view.unsaved:
        count = len(view.unsaved)
        buttons.append((NOTE, f"   {count} change{'s' * (count > 1)} not saved", None))
    return Drawn(rows, buttons, cursor)


def _warning(name: str) -> str:
    """A model name can't be checked here, so its open row says what a wrong one does."""
    if name != "model":
        return ""
    return ("a wrong name fails the next answer" if config.WHEN[name] == "now"
            else "a wrong name ends Hallux at the next boot")


def _meant(choice: str) -> str | None:
    return None if choice == "none" else choice


class ConfigTab(Tab):
    title = "Config"

    def __init__(self, view: Callable[[], View], change: Callable[[str, str], str | None],
                 save: Callable[[], str | None], refill: Callable[[], str]) -> None:
        self.view, self.change, self.save, self.refill = view, change, save, refill
        self.state = State()
        self.cursor = Point(0, 0)
        text_row = Condition(lambda: self.state.open not in (None, "effort"))
        rows = FormattedTextControl(self._rows, focusable=True,
                                    get_cursor_position=lambda: self.cursor)
        self.container = HSplit([                        # the rows scroll, the buttons stay
            Window(rows, always_hide_cursor=~text_row, dont_extend_height=True,
                   scroll_offsets=ScrollOffsets(top=1, bottom=lambda: 1 + len(self._choices()))),
            Window(FormattedTextControl(self._buttons), height=1),
            Window()])                                   # what is left of a tall window
        self.bindings = self._bindings(text_row)

    # ---------------------------------------------------------------- what the host asks

    @property
    def typing(self) -> bool:
        return self.state.open is not None

    def hint(self) -> str:
        name = self.state.open
        if name is None:
            press = "press" if stops()[self.state.at] in BUTTONS else "change"
            return f"↑ ↓ move · Enter {press}"
        how = ("↑ ↓ pick" if name == "effort"
               else "type a name, or ↑ ↓ pick" if name in NAMES
               else "type the dollars, or nothing for no cap" if name == "max_budget_usd"
               else "type the dollars")
        return f"{how} · Enter take · Esc leave it as it was"

    def leave(self) -> bool:
        if self.state.open is None:
            return False
        self.state.open = self.state.refused = None
        return True

    def shown(self) -> None:
        self.state = State()

    # ---------------------------------------------------------------- drawing

    def _rows(self) -> list:
        drawn = draw(self.view(), self.state)            # read anew at every redraw
        self.cursor = drawn.cursor
        lines = [self._clickable(line) for line in drawn.rows]
        return [part for line in lines for part in (*line, ("", "\n"))][:-1]

    def _buttons(self) -> list:
        return self._clickable(draw(self.view(), self.state).buttons)

    def _clickable(self, line: list[Part]) -> list:
        return [(style, text) if target is None else (style, text, self._click(target))
                for style, text, target in line]

    def _click(self, target: object) -> Callable[[MouseEvent], None]:
        def handle(event: MouseEvent) -> None:
            if event.event_type != MouseEventType.MOUSE_UP:
                return
            if isinstance(target, tuple):                # an entry of the open row's list
                self._pick(target[1])
                return self._take()
            self.leave()                                 # a row that was open is left as it was
            self.state.at = stops().index(target)
            self._enter()
        return handle

    # ---------------------------------------------------------------- keys

    def _bindings(self, text_row: Condition) -> KeyBindings:
        kb = KeyBindings()
        closed = Condition(lambda: self.state.open is None)
        on_button = closed & Condition(lambda: stops()[self.state.at] in BUTTONS)

        def to(handler: Callable[[], object]) -> Callable:
            return lambda event: handler()

        kb.add("up", filter=closed)(to(lambda: self._move(-1)))
        kb.add("down", filter=closed)(to(lambda: self._move(1)))
        kb.add("tab", filter=closed)(to(lambda: self._move(1, around=True)))
        kb.add("s-tab", filter=closed)(to(lambda: self._move(-1, around=True)))
        kb.add("left", filter=on_button)(to(lambda: self._move(-1)))
        kb.add("right", filter=on_button)(to(lambda: self._move(1)))
        kb.add("enter", filter=closed)(to(self._enter))
        kb.add("enter", filter=~closed)(to(self._take))
        kb.add("up", filter=~closed)(to(lambda: self._step(-1)))
        kb.add("down", filter=~closed)(to(lambda: self._step(1)))

        # An open row is one line of text. Its keys are bound here, one by one, so that it is
        # typed into the same way whatever editing keys the app around the panel has. The row
        # opens with its value selected: what is typed takes its place, an arrow keeps it.
        @kb.add(Keys.Any, filter=text_row)
        @kb.add(Keys.BracketedPaste, filter=text_row)
        def _type(event) -> None:
            if text := "".join(char for char in event.data if char.isprintable()):
                self._write(text)

        def edit(*keys: str, deletes: bool = False) -> Callable:
            def bind(change: Callable[[Buffer], object]) -> None:
                def handle(event) -> None:
                    if deletes and self.state.selected:
                        self._write("")
                    else:
                        change(self.state.typed)
                    self.state.selected = False
                for key in keys:
                    kb.add(key, filter=text_row)(handle)
            return bind

        edit("backspace", "c-h", deletes=True)(lambda line: line.delete_before_cursor())
        edit("delete", deletes=True)(lambda line: line.delete())
        edit("left")(lambda line: line.cursor_left())
        edit("right")(lambda line: line.cursor_right())
        edit("home", "c-a")(lambda line: setattr(line, "cursor_position", 0))
        edit("end", "c-e")(lambda line: setattr(line, "cursor_position", len(line.text)))
        edit("c-u")(lambda line: line.delete_before_cursor(line.cursor_position))
        edit("c-k")(lambda line: line.delete(len(line.text) - line.cursor_position))
        return kb

    def _write(self, text: str) -> None:
        """Type into the open row. What was selected goes."""
        if self.state.selected:
            self._line("", selected=False)
        self.state.typed.insert_text(text)

    def _line(self, text: str, selected: bool = True) -> None:
        """Put a whole line into the open row, the cursor at its end."""
        self.state.typed.set_document(Document(text, len(text)), bypass_readonly=True)
        self.state.selected, self.state.refused = selected, None

    def _move(self, by: int, around: bool = False) -> None:
        last = len(stops()) - 1
        to = self.state.at + by
        self.state.at = to % (last + 1) if around else max(0, min(last, to))
        self.state.answer = ""

    def _enter(self) -> None:
        """Enter or a click on the stop the cursor is on: open the row, or press the button."""
        state, target = self.state, stops()[self.state.at]
        state.answer, state.failed = "", False
        if target == "Close":
            self.host.close()
        elif target == "Save":
            reason = self.save()
            state.answer, state.failed = reason or "saved", reason is not None
        elif target == "Refill budgets":
            state.answer = self.refill()
        else:
            state.open = target
            self._line(entered(target, getattr(self.view().hardware, target)))

    def _choices(self) -> list[str]:
        return choices(self.state.open, self.view()) if self.state.open else []

    def _step(self, by: int) -> None:
        """In an open row with a list: the entry before or after the one that is entered."""
        offered = self._choices()
        if not offered:
            return
        lines = [entered(self.state.open, _meant(choice)) for choice in offered]
        here = lines.index(self.state.typed.text) if self.state.typed.text in lines else -1
        self._pick(offered[max(0, min(len(offered) - 1, here + by))])

    def _pick(self, choice: str) -> None:
        self._line(entered(self.state.open, _meant(choice)))

    def _take(self) -> None:
        """Enter in an open row: the machine takes the value, or says why not."""
        reason = self.change(self.state.open, self.state.typed.text)
        if reason is None:
            self.state.open = None
        self.state.refused = reason
