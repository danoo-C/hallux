"""The Packages tab of hallux's own panel: hpm in the world you are in (docs/hpm/hpm.md,
sections 6a and 10; the plan's step 5).

The store's packages with checkboxes, their extras folding open under them; Enter works out
what would be written, the conflicts are asked on the same tab, and the write runs in a
thread with its progress. The tab is given the functions of the machine's Installs
(hallux/hpm/running.py), as the Files tab is given those of Imports, and reads watch() anew
at every redraw. Its rows and their keys are the terminal's (hallux/hpm/screens.py), so a
package ticks and its conflicts are answered the same way in both.

Its key is g (Packa_g_es): p is the Files tab's path row. No key of its own is a tab's
letter (a d f g c) while the list is shown; while a plan's questions are asked the tab
counts as typing, so o s k f r are its answers there.
"""
from __future__ import annotations

from typing import Callable

from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import ConditionalContainer, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from hallux.hpm.engine import KEEP, REPLACE
from hallux.hpm.running import ASKING, DONE, FAILED, LISTING, PLANNING, WRITING, Entry, Seen
from hallux.hpm.screens import Checkboxes, Choice, Conflicts
from hallux.panel import Tab
from hallux.statusbar import GRAY, RED, YELLOW_NOTE

NOTE, LOUD, WARNED = f"fg:{GRAY}", f"fg:{RED}", f"fg:{YELLOW_NOTE}"
STORE, UPDATES, HERE = "the store", "updates", "installed here"
STYLES = {"class:title": "bold", "class:dim": NOTE, "class:loud": f"{LOUD} bold",
          "class:bad": LOUD, "class:cursor": "reverse", "class:ok": "", "class:keys": NOTE}


def _styled(row: list) -> list:
    """The terminal screens' rows, in the panel's colors."""
    return [(STYLES.get(style, style), text) for style, text in row]


class PackagesTab(Tab):
    title = "Packages"
    key = "g"

    def __init__(self, watch: Callable[[], Seen], catalog: Callable[..., list[Entry]],
                 installed: Callable[[], dict], plan_install: Callable, plan_remove: Callable,
                 go: Callable[[dict], None], stop: Callable[[], None],
                 back: Callable[[], None]) -> None:
        self.watch, self.catalog, self.installed = watch, catalog, installed
        self.plan_install, self.plan_remove = plan_install, plan_remove
        self.go, self.stop, self.back = go, stop, back
        self.view = STORE
        self.word = ""                                   # the filter's word
        self.row: Buffer | None = None                   # the filter's row, while it is open
        self.choices: dict[str, Choice] = {}             # by name: their ticks stay
        self.entries: list[Entry] = []
        self.model: Checkboxes | None = None
        self.questions: Conflicts | None = None          # the plan's, in ASKING
        self.asked_plan = None                           # the plan they belong to
        self.old_lines: dict[str, str] = {}              # "memory:<name>": replace or keep
        self.problem: str | None = None                  # the store couldn't be read
        self.top = 0
        self.lines_drawn = 0
        self.body = Window(FormattedTextControl(self._text, focusable=True,
                                                get_cursor_position=self._cursor),
                           always_hide_cursor=True, wrap_lines=False)
        self.container = HSplit([
            Window(height=1),
            ConditionalContainer(Window(FormattedTextControl(self._row_text), height=1),
                                 Condition(lambda: self.row is not None)),
            self.body])
        self.bindings = self._bindings()

    # ---------------------------------------------------------------- what the host asks

    @property
    def typing(self) -> bool:
        return self.row is not None or self.watch().state == ASKING

    def hint(self) -> str:
        state = self.watch().state
        if self.row is not None:
            return "type a word · Enter keep it · Esc leave the row"
        if self.model is not None and self.model.viewing is not None:
            return "↑ ↓ scroll · Esc back"
        if state == PLANNING:
            return "working it out… · Esc stop"
        if state == ASKING:
            keys = ["o s k f r on a row", "O overwrite all", "S skip all"] if self._has_questions() else []
            if self.old_lines:
                keys.append("y n the old memory line")
            return " · ".join(keys + ["Enter go on", "Esc back"])
        if state == WRITING:
            return "Esc stops between two packages"
        if state in (DONE, FAILED):
            return "Enter back to the list"
        return "space tick · → extras · v card · r remove · Enter install"

    @property
    def esc(self) -> str:
        """What Esc does here, for the panel's foot."""
        if self.model is not None and self.model.viewing is not None:
            return "back"
        return "stop" if self.watch().state in (PLANNING, WRITING) else "close"

    def leave(self) -> bool:
        state = self.watch().state
        if self.row is not None:
            self._close_row()
        elif self.model is not None and self.model.viewing is not None:
            self.model.viewing = None
        elif state in (PLANNING, WRITING):
            self.stop()
        elif state == ASKING:
            self._back()                                 # the questions: back to the list
        else:
            if state in (DONE, FAILED):
                self._back()                             # seen: the list, the next time
            return False                                 # and the panel closes
        return True

    def wants_first(self) -> bool:
        """The panel opens here while a write runs, and until its outcome was seen."""
        return self.watch().state in (WRITING, DONE)

    def shown(self) -> None:
        self.top = 0
        if self.watch().state == LISTING:
            self._read(fresh=True)

    # ---------------------------------------------------------------- the list

    def _read(self, fresh: bool = False) -> None:
        """The catalog, and the choices made from it. Ticks stay for packages still there."""
        try:
            self.entries = self.catalog(fresh)
            self.problem = None
        except Exception as e:                           # an HpmError: the store is wrong
            self.entries, self.problem = [], str(e)
        record = self.installed() if self.entries else {}
        kept = self.choices
        self.choices = {}
        for entry in self.entries:
            old = kept.get(entry.name)
            notes = []
            if entry.installed:
                notes.append(f"installed {entry.installed} ↑" if entry.newer else "installed ✓")
            notes += [p.replace("which this world doesn't get (its config's addons)",
                                "the world doesn't get").replace(", which Hallux doesn't have", "")
                      + " ✗" for p in entry.problems]
            if entry.manifest.is_bundle:
                notes.append(f"bundle of {len(entry.manifest.bundle)}")
            extras = old.extras if old else (
                {k: k in record.get(entry.name, {}).get("extras", []) for k in entry.manifest.extras}
                if entry.installed else {})
            self.choices[entry.name] = Choice(
                entry.name, entry.manifest, ticked=old.ticked if old else False, extras=extras,
                labels=entry.labels, note=" · ".join(notes), bad=bool(entry.problems),
                card=list(entry.card))
        self._rebuild()

    def _visible(self) -> list[Choice]:
        out = []
        for entry in self.entries:
            if self.view == UPDATES and not entry.newer:
                continue
            if self.view == HERE and not entry.installed:
                continue
            word = self.word.lower()
            if word and word not in entry.name.lower() and word not in entry.manifest.summary.lower():
                continue
            out.append(self.choices[entry.name])
        return out

    def _rebuild(self) -> None:
        cursor = self.model.cursor if self.model else 0
        self.model = Checkboxes(self._visible(), title=" ")
        if len(self.model.choices) == 1:
            self.model.choices[0].open = True
        self.model.cursor = min(cursor, max(0, len(self.model.entries()) - 1))

    def _width(self) -> int:
        try:
            return get_app().output.get_size().columns
        except Exception:
            return 80

    # ---------------------------------------------------------------- drawing

    def _text(self) -> list:
        seen = self.watch()
        if self.questions is not None and (seen.state != ASKING or seen.plan is not self.asked_plan):
            self.questions, self.asked_plan = None, None
        if seen.state == ASKING and self.questions is None:
            self.questions = Conflicts(seen.plan.grouped())
            self.asked_plan = seen.plan
            self.old_lines = {f"memory:{i.name}": REPLACE for i in seen.plan.memory_questions()}
        lines = self._lines(seen)
        self.lines_drawn = len(lines)
        out: list = []
        for line in lines:
            out += line + [("", "\n")]
        return out[:-1]

    def _lines(self, seen: Seen) -> list[list]:
        if self.model is None:
            self._read()
        if seen.state == PLANNING:
            what = "removing" if seen.doing == "remove" else "installing"
            return [[("bold", f" Working out what {what} would write…")]]
        if seen.state == ASKING:
            return self._asking(seen)
        if seen.state in (WRITING, DONE):
            return self._progress(seen)
        if seen.state == FAILED:
            return [[(LOUD, f" {seen.error}")], [], [(NOTE, " Nothing more was written.")]]
        if self.model.viewing is not None:
            return [[("", " " + line)] for line in self.model.viewing[self.model.view_top:]]
        return self._listing()

    def _listing(self) -> list[list]:
        if self.problem:
            return [[(LOUD, f" The store can't be read: {self.problem}")]]
        here = sum(1 for e in self.entries if e.installed)
        head = f" local · {len(self.entries)} package{'s' * (len(self.entries) != 1)}"
        view = f" · {self.view}" if self.view != STORE else ""
        found = f" · “{self.word}”" if self.word else ""
        lines = [[("bold", head + view + found), (NOTE, f"    installed here: {here}    "
                                                         f"+ - all · u updates · i installed · / find")],
                 []]
        if not self.entries:
            return lines + [[(NOTE, " The store has no packages yet: hpm publish puts one there, "
                                    "from your terminal.")]]
        if not self.model.choices:
            return lines + [[(NOTE, " Nothing here in this view.")]]
        self.model.summary_width = max(12, min(40, self._width() - 62))
        for i, row in enumerate(self.model.rows()):
            mark = [("reverse", "▸")] if i == self.model.cursor else [("", " ")]
            lines.append(mark + [("", " ")] + _styled(row))
        lines += [_styled(line) for line in self.model.tail()]
        return lines

    def _asking(self, seen: Seen) -> list[list]:
        plan = seen.plan
        lines = []
        for item in plan.items:
            if item.blocked:
                lines.append([(LOUD, f" ✗ {item.name}: {item.blocked}")])
                continue
            if seen.doing == "remove":
                gone = sum(1 for a in item.actions if a.op == "remove")
                lines.append([("bold", f" remove {item.name} {item.was}"),
                              ("", f": {gone} file{'s' * (gone != 1)}; its data stays")])
                continue
            new = sum(1 for a in item.actions if a.op == "write" and a.mark == "new")
            replaced = sum(1 for a in item.actions if a.op == "write" and a.mark != "new")
            asked = sum(1 for a in item.actions if a.op == "ask")
            parts = [f"{new} new"] + [f"{replaced} replaced"] * bool(replaced) + \
                    [f"{asked} asked below"] * bool(asked)
            was = f" (installed {item.was})" if item.was else ""
            lines.append([("bold", f" {item.name} {item.release.version}{was}"),
                          ("", ": " + " · ".join(parts))])
        for note in plan.notes:
            lines.append([(WARNED, f" note: {note}")])
        for name, path, why in plan.loud:
            lines.append([(LOUD, f" !! {name}: {path + ': ' if path else ''}{why}")])
        for item in plan.memory_questions():
            answer = self.old_lines.get(f"memory:{item.name}", REPLACE)
            lines += [[], [("", f" The machine's memory has its own line about {item.name}:")],
                      [(NOTE, f"   {item.old_line}")],
                      [("", "   y replace it with hpm's  " if answer == REPLACE else "   y replace  "),
                       ("bold" if answer == REPLACE else NOTE, "[replace]" if answer == REPLACE else ""),
                       ("", " · n keep it "), ("bold" if answer == KEEP else NOTE,
                                               "[keep]" if answer == KEEP else "")]]
        if self._has_questions():
            lines += [[], [("bold", " " + self.questions.title)]]
            for i, row in enumerate(self.questions.rows()):
                mark = [("reverse", "▸")] if i == self.questions.cursor else [("", " ")]
                lines.append(mark + [("", " ")] + _styled(row))
            lines += [_styled(line) for line in self.questions.tail()]
        lines += [[], [(NOTE, " Enter writes it; Esc goes back, and nothing is written.")]]
        return lines

    def _progress(self, seen: Seen) -> list[list]:
        lines = [[("bold", " Removing…" if seen.doing == "remove" else " Installing…")]] \
            if seen.state == WRITING else []
        for done in seen.progress:
            sign = {"failed": "✗", "skipped": "–"}.get(done.status, "✓")
            style = LOUD if done.status == "failed" else NOTE if done.status == "skipped" else ""
            why = f": {done.why}" if done.why else ""
            version = f" {done.version}" if done.version else ""
            lines.append([(style, f" {sign} {done.name}{version} {done.status}{why}")])
        if seen.state == DONE and seen.outcome is not None:
            lines += [[], [("bold", " " + seen.outcome.summary())]]
            if seen.outcome.backup:
                lines.append([(NOTE, f" backup: {seen.outcome.backup} (hpm rollback in your "
                                     f"terminal, once the world is stopped)")])
            if seen.outcome.notes:
                lines.append([(NOTE, " The machine is told with your next line.")])
        return lines

    def _row_text(self) -> list:
        if self.row is None:
            return []
        return [("bold", " find: "), ("underline", self.row.text), ("reverse", " ")]

    def _cursor(self) -> Point:
        """Where the list scrolls to: the row the cursor is on, inside what is drawn."""
        seen, row = self.watch(), 0
        if seen.state == LISTING and self.model is not None and self.model.viewing is None \
                and self.model.choices and not self.problem:
            row = 2 + self.model.cursor
        elif seen.state == ASKING and self._has_questions():
            row = self.lines_drawn - len(self.questions.rows()) - 4 + self.questions.cursor
        return Point(0, max(0, min(row, self.lines_drawn - 1)))

    def _has_questions(self) -> bool:
        return self.questions is not None and bool(self.questions.questions)

    # ---------------------------------------------------------------- keys

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()
        listing = Condition(lambda: self.watch().state == LISTING and self.row is None
                            and (self.model is None or self.model.viewing is None))
        viewing = Condition(lambda: self.model is not None and self.model.viewing is not None)
        asking = Condition(lambda: self.watch().state == ASKING)
        ended = Condition(lambda: self.watch().state in (DONE, FAILED))
        in_row = Condition(lambda: self.row is not None)

        def to(handler):
            return lambda event: handler()

        def model(method: str):
            return lambda event: getattr(self.model, method)()

        kb.add("up", filter=listing)(model("up"))
        kb.add("down", filter=listing)(model("down"))
        kb.add(" ", filter=listing)(model("toggle"))
        kb.add("right", filter=listing)(model("open"))
        kb.add("left", filter=listing)(model("close"))
        kb.add("+", filter=listing)(model("all"))
        kb.add("-", filter=listing)(model("none"))
        kb.add("v", filter=listing)(model("show_card"))
        kb.add("u", filter=listing)(to(lambda: self._switch(UPDATES)))
        kb.add("i", filter=listing)(to(lambda: self._switch(HERE)))
        kb.add("/", filter=listing)(to(self._open_row))
        kb.add("r", filter=listing)(to(self._remove))
        kb.add("enter", filter=listing)(to(self._install))
        kb.add("up", filter=viewing)(to(lambda: self.model._scroll(-1)))
        kb.add("down", filter=viewing)(to(lambda: self.model._scroll(1)))

        for key, answer in (("o", "overwrite"), ("s", "skip"), ("k", "both"), ("f", "fail"),
                            ("r", "remove")):
            kb.add(key, filter=asking)(lambda event, answer=answer: self._answer(answer))
        kb.add("O", filter=asking)(to(lambda: self._answer_all("overwrite")))
        kb.add("S", filter=asking)(to(lambda: self._answer_all("skip")))
        kb.add("up", filter=asking)(to(lambda: self.questions and self.questions.up()))
        kb.add("down", filter=asking)(to(lambda: self.questions and self.questions.down()))
        kb.add("y", filter=asking)(to(lambda: self._old_lines(REPLACE)))
        kb.add("n", filter=asking)(to(lambda: self._old_lines(KEEP)))
        kb.add("enter", filter=asking)(to(self._go))
        kb.add(Keys.Any, filter=asking)(lambda event: None)  # nothing else, while asked
        kb.add("enter", filter=ended)(to(self._back))

        kb.add(Keys.Any, filter=in_row)(lambda event: self._type(event.data))
        kb.add("backspace", filter=in_row)(to(self._erase))
        kb.add("enter", filter=in_row)(to(self._close_row))
        return kb

    def _switch(self, view: str) -> None:
        self.view = STORE if self.view == view else view
        self._rebuild()

    def _install(self) -> None:
        wants = self.model.result() if self.model else []
        if not wants:
            self.host.say("tick a package first, with space")
            return
        self.plan_install(wants)

    def _remove(self) -> None:
        if not self.model or not self.model.choices:
            return
        choice, _ = self.model.here()
        if choice.name not in self.installed():
            self.host.say(f"{choice.name} isn't installed here")
            return
        self.plan_remove(choice.name)

    def _answer(self, answer: str) -> None:
        if self._has_questions():
            self.questions.answer(answer)

    def _answer_all(self, answer: str) -> None:
        if self._has_questions():
            self.questions.answer_all(answer)

    def _old_lines(self, answer: str) -> None:
        for key in self.old_lines:
            self.old_lines[key] = answer

    def _go(self) -> None:
        answers = dict(self.questions.result()) if self._has_questions() else {}
        answers |= self.old_lines
        self.go(answers)

    def _back(self) -> None:
        self.back()
        self.questions, self.asked_plan, self.old_lines = None, None, {}
        self._read()

    def _open_row(self) -> None:
        self.row = Buffer()
        self.row.text = self.word

    def _close_row(self) -> None:
        if self.row is not None:
            self.word = self.row.text.strip()
            self.row = None
            self._rebuild()

    def _type(self, text: str) -> None:
        if text and text.isprintable():
            self.row.insert_text(text)

    def _erase(self) -> None:
        self.row.delete_before_cursor(1)
