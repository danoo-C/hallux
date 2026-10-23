"""hpm's screens in your terminal (docs/hpm/hpm.md, sections 6, 6a and 7; the plan's step 4):
the checkboxes, the user, and the conflicts. Each is a small full-screen prompt_toolkit app
over a model that knows nothing of drawing, so the tests can drive the model by its methods
and the app by its keys.

None of them uses a letter that the panel's Packages tab couldn't (a d f c g choose tabs
there): "all" and "none" are + and -, as they will be in the tab.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from prompt_toolkit.application import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style

from hallux.hpm.engine import BOTH, FAIL, KEEP, OVERWRITE, REMOVE, SKIP, Action, Want
from hallux.hpm.manifest import Manifest

STYLE = Style.from_dict({
    "title": "bold", "dim": "fg:ansibrightblack", "loud": "fg:ansired bold",
    "cursor": "reverse", "ok": "fg:ansigreen", "bad": "fg:ansired", "keys": "fg:ansibrightblack",
})


# ---------------------------------------------------------------------- the frame

class Screen:
    """A list of rows with a cursor, and a foot with its keys."""

    title = ""
    foot = ""

    def __init__(self) -> None:
        self.cursor = 0
        self.done = False
        self.cancelled = False
        self.viewing: list[str] | None = None     # a text shown over the list (v), or None
        self.view_top = 0

    # what a screen says for itself
    def rows(self) -> list[StyleAndTextTuples]:
        raise NotImplementedError

    def head(self) -> list[StyleAndTextTuples]:
        return [[("class:title", self.title)], []] if self.title else []

    def tail(self) -> list[StyleAndTextTuples]:
        return []

    def bind(self, kb: KeyBindings) -> None:
        """The screen's own keys."""

    # moving
    def up(self) -> None:
        self.cursor = max(0, self.cursor - 1)

    def down(self) -> None:
        self.cursor = min(max(0, len(self.rows()) - 1), self.cursor + 1)

    def cancel(self) -> None:
        self.cancelled = self.done = True

    def accept(self) -> None:
        self.done = True

    # drawing
    def text(self) -> StyleAndTextTuples:
        if self.viewing is not None:
            lines: list[StyleAndTextTuples] = [[("", line)] for line in self.viewing[self.view_top:]]
        else:
            lines = list(self.head())
            for i, row in enumerate(self.rows()):
                lines.append([("class:cursor", "▸ ")] + row if i == self.cursor else [("", "  ")] + row)
            lines += self.tail()
        out: StyleAndTextTuples = []
        for line in lines:
            out += line + [("", "\n")]
        return out

    def keys(self) -> StyleAndTextTuples:
        """The foot, on a row of its own at the bottom, so a long list never hides it."""
        words = "↑↓ scroll · q or Esc back" if self.viewing is not None else self.foot
        return [("class:keys", "  " + words)]

    def cursor_point(self) -> Point:
        return Point(0, 0 if self.viewing is not None else len(self.head()) + self.cursor)

    def application(self, **io) -> Application:
        kb = KeyBindings()
        viewing = lambda: self.viewing is not None             # noqa: E731
        from prompt_toolkit.filters import Condition
        listing, reading = Condition(lambda: not viewing()), Condition(viewing)

        def key(*keys, filter=listing):
            def wrap(handler):
                kb.add(*keys, filter=filter)(lambda event: (handler(), self._maybe_exit(event)))
                return handler
            return wrap

        key("up")(self.up)
        key("down")(self.down)
        key("enter")(self.accept)
        key("q")(self.cancel)
        kb.add("escape", eager=True, filter=listing)(lambda e: (self.cancel(), self._maybe_exit(e)))
        kb.add("c-c")(lambda e: (self.cancel(), self._maybe_exit(e)))
        kb.add("up", filter=reading)(lambda e: self._scroll(-1))
        kb.add("down", filter=reading)(lambda e: self._scroll(1))
        kb.add("q", filter=reading)(lambda e: self._close_view())
        kb.add("escape", eager=True, filter=reading)(lambda e: self._close_view())
        self.bind_keys = key
        self.bind(kb)
        control = FormattedTextControl(self.text, get_cursor_position=self.cursor_point,
                                       focusable=True, show_cursor=False)
        foot = Window(FormattedTextControl(self.keys), height=1)
        return Application(layout=Layout(HSplit([Window(control, wrap_lines=False), foot])),
                           key_bindings=kb, style=STYLE, full_screen=True, **io)

    def _scroll(self, by: int) -> None:
        self.view_top = max(0, min(len(self.viewing or []) - 1, self.view_top + by))

    def _close_view(self) -> None:
        self.viewing = None

    def view(self, lines: list[str]) -> None:
        self.viewing, self.view_top = lines, 0

    def _maybe_exit(self, event) -> None:
        if self.done:
            event.app.exit()

    def run(self, **io):
        """Show the screen until Enter or q; then the result, or None if cancelled."""
        self.application(**io).run()
        return None if self.cancelled else self.result()

    def result(self):
        raise NotImplementedError


# ---------------------------------------------------------------------- the checkboxes

def _cut(text: str, width: int) -> str:
    return text if len(text) <= width else text[:width - 1] + "…"


@dataclass
class Choice:
    """One package on the checkbox screen."""
    name: str
    manifest: Manifest
    ticked: bool = True
    extras: dict[str, bool] = field(default_factory=dict)    # key: ticked
    labels: dict[str, str] = field(default_factory=dict)     # key: what the extra is
    open: bool = False
    note: str = ""                                           # "needs the web addon ✗", "installed 1.3"
    bad: bool = False                                        # the note says what's missing
    card: list[str] = field(default_factory=list)            # for v


class Checkboxes(Screen):
    """hpm.md, sections 6 and 6a: one row per package, its extras folding open under it."""

    foot = "space tick · → extras · + all · - none · v the card · Enter install · q cancel"

    def __init__(self, choices: list[Choice], title: str = "") -> None:
        super().__init__()
        self.choices = choices
        for choice in choices:
            if not choice.extras:
                choice.extras = {k: e.default for k, e in choice.manifest.extras.items()}
            choice.open = len(choices) == 1           # one package: its extras are shown
        if title:
            self.title = title
        elif len(choices) == 1:
            m = choices[0].manifest
            self.title = "  ·  ".join(x for x in (f"{m.name} {m.version}", m.summary,
                                                  f"by {m.author}" if m.author else "") if x)
        else:
            self.title = f"{len(choices)} packages"

    def entries(self) -> list[tuple[Choice, str | None]]:
        """The rows: each package, and under an open one its extras."""
        out = []
        for choice in self.choices:
            out.append((choice, None))
            if choice.open:
                out += [(choice, key) for key in choice.manifest.extras]
        return out

    def rows(self) -> list[StyleAndTextTuples]:
        rows = []
        for choice, key in self.entries():
            if key is None:
                box = "[x]" if choice.ticked else "[ ]"
                fold = ("▾ " if choice.open else "▸ ") if choice.manifest.extras else "  "
                more = ", ".join(k for k, on in choice.extras.items() if on) if not choice.open else ""
                summary = _cut(choice.manifest.summary or "", 40)
                row = [("", f"{box} {fold}{choice.name:<20} {summary:<40} "),
                       ("class:bad" if choice.bad else "class:dim", choice.note)]
                if more:
                    row.append(("class:dim", f"  ▸ {more}"))
                if choice.manifest.rules:
                    row.append(("class:loud", "  adds rules"))
                rows.append(row)
            else:
                extra = choice.manifest.extras[key]
                box = "[x]" if choice.extras[key] and choice.ticked else "[ ]"
                needs = f" · needs {', '.join(extra.needs)}" if extra.needs else ""
                rows.append([("", f"      {box} {key:<14} {_cut(choice.labels.get(key, ''), 34):<34}"),
                             ("class:dim", f" {extra.package}{needs}")])
        return rows

    def tail(self) -> list[StyleAndTextTuples]:
        if not self.choices:
            return []
        choice, _ = self.entries()[min(self.cursor, len(self.entries()) - 1)]
        out: list[StyleAndTextTuples] = []
        if choice.manifest.memory_line:
            out += [[], [("", "  This adds to the machine's memory:")],
                    [("class:dim", f"    {choice.manifest.memory_line}")]]
        if choice.manifest.rules:
            out += [[("class:loud", "  and rules, which change the whole machine:")]]
            out += [[("class:loud", f"    {rule}")] for rule in choice.manifest.rules]
        return out

    # the keys
    def bind(self, kb: KeyBindings) -> None:
        self.bind_keys(" ")(self.toggle)
        self.bind_keys("right")(self.open)
        self.bind_keys("left")(self.close)
        self.bind_keys("+")(self.all)
        self.bind_keys("-")(self.none)
        self.bind_keys("v")(self.show_card)

    def here(self) -> tuple[Choice, str | None]:
        return self.entries()[self.cursor]

    def toggle(self) -> None:
        choice, key = self.here()
        if key is None:
            choice.ticked = not choice.ticked
            return
        if choice.extras[key] and choice.ticked:
            self._untick(choice, key)
        else:
            choice.ticked = True                  # an extra wants its app
            self._tick(choice, key)

    def _tick(self, choice: Choice, key: str) -> None:
        choice.extras[key] = True                 # ticking characters ticks packs
        for need in choice.manifest.extras[key].needs:
            if not choice.extras.get(need):
                self._tick(choice, need)

    def _untick(self, choice: Choice, key: str) -> None:
        choice.extras[key] = False                # unticking packs unticks characters
        for other, extra in choice.manifest.extras.items():
            if key in extra.needs and choice.extras.get(other):
                self._untick(choice, other)

    def open(self) -> None:
        choice, _ = self.here()
        if choice.manifest.extras and not choice.open:
            choice.open = True

    def close(self) -> None:
        choice, key = self.here()
        if choice.open:
            choice.open = False
            self.cursor = [i for i, (c, k) in enumerate(self.entries()) if c is choice and k is None][0]

    def all(self) -> None:
        for choice in self.choices:
            choice.ticked = True

    def none(self) -> None:
        for choice in self.choices:
            choice.ticked = False

    def show_card(self) -> None:
        choice, _ = self.here()
        m = choice.manifest
        lines = [f"{m.name} {m.version}: what it puts into the machine's mind", ""]
        lines += ["The card:", ""] + (choice.card or ["(this package has no card)"])
        lines += ["", "The memory line:", f"  {m.memory_line or '(none)'}"]
        if m.rules:
            lines += ["", "Rules, which change the whole machine:"] + [f"  {r}" for r in m.rules]
        self.view(lines)

    def result(self) -> list[Want]:
        return [Want(c.name, extras=tuple(k for k, on in c.extras.items() if on))
                for c in self.choices if c.ticked]


# ---------------------------------------------------------------------- one of a list

class Pick(Screen):
    """One of a few: the world's user, when it has several."""

    foot = "↑↓ choose · Enter take it · q cancel"

    def __init__(self, title: str, options: list[str]) -> None:
        super().__init__()
        self.title, self.options = title, options

    def rows(self) -> list[StyleAndTextTuples]:
        return [[("", option)] for option in self.options]

    def result(self) -> str:
        return self.options[self.cursor]


# ---------------------------------------------------------------------- the conflicts

WORDS = {"foreign": "different, not hpm's", "changed": "you changed it",
         "in-the-way": "a folder or a link is there"}
KEYS = {"o": OVERWRITE, "s": SKIP, "k": BOTH, "f": FAIL, "r": REMOVE}   # k: keep both, or keep
SHOWN = {OVERWRITE: "[o]verwrite", SKIP: "[s]kip", BOTH: "[k]eep both", FAIL: "[f]ail it",
         REMOVE: "[r]emove", KEEP: "[k]eep"}


class Conflicts(Screen):
    """hpm.md, section 7: the plan's questions, grouped by package and folder."""

    foot = "o s k f r on a row · O overwrite all · S skip all · Enter go on · q cancel"

    def __init__(self, groups: dict[tuple[str, str], list[Action]]) -> None:
        super().__init__()
        self.groups = groups
        self.questions = [q for qs in groups.values() for q in qs]
        self.answers = {q.path: q.default for q in self.questions}
        many = len(self.questions)
        self.title = f"{many} file{'s are' if many != 1 else ' is'} in the way"

    def rows(self) -> list[StyleAndTextTuples]:
        rows = []
        for q in self.questions:
            name = q.path.rsplit("/", 1)[-1]
            words = WORDS.get(q.mark, q.mark)
            if q.mark == "changed" and REMOVE in q.choices:
                words = "you changed it; the new version doesn't have it"
            if q.owner:
                words += f" (it is {q.owner}'s)"
            choices = [(("class:title" if self.answers[q.path] == c else "class:dim"), SHOWN[c] + " ")
                       for c in q.choices]
            rows.append([("", f"{q.package:<18} {name:<28} {words:<34} ")] + choices)
        return rows

    def tail(self) -> list[StyleAndTextTuples]:
        if not self.questions:
            return []
        q = self.questions[self.cursor]
        return [[], [("class:dim", f"  {q.path}")]]

    def bind(self, kb: KeyBindings) -> None:
        for key, answer in KEYS.items():
            self.bind_keys(key)(lambda answer=answer: self.answer(answer))
        self.bind_keys("O")(lambda: self.answer_all(OVERWRITE))
        self.bind_keys("S")(lambda: self.answer_all(SKIP))

    def answer(self, answer: str) -> None:
        """The key on this row: o s f r, and k for keep both or keep, whichever it offers."""
        if not self.questions:
            return
        q = self.questions[self.cursor]
        if answer in (BOTH, KEEP):
            answer = BOTH if BOTH in q.choices else KEEP
        if answer in q.choices:
            self.answers[q.path] = answer
            self.down()

    def answer_all(self, answer: str) -> None:
        """O and S across every package: where a question can't take it (a folder in the
        way can't be overwritten), it keeps its answer; S keeps a changed file a new version
        dropped."""
        for q in self.questions:
            if answer in q.choices:
                self.answers[q.path] = answer
            elif answer == SKIP and KEEP in q.choices:
                self.answers[q.path] = KEEP

    def result(self) -> dict[str, str]:
        return dict(self.answers)
