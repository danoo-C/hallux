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

A migration (docs/hpm/migrations.md, section 4) waits on the tab as in the terminal: Enter
lets the AI start, Enter migrates after its plan, Enter accepts after the checks; q cancels,
r rolls back, l looks at the staged files first. The tab counts as typing then too.
"""
from __future__ import annotations

import textwrap
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
from hallux.hpm.running import (
    ASKING, CHECKED, DONE, FAILED, LET, LISTING, MIGRATING, MIGRATION, PLAN, PLANNING, WRITING,
    Entry, Seen,
)
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
                 back: Callable[[], None], migration_go: Callable[[], None] = lambda: None,
                 migration_cancel: Callable[[], None] = lambda: None,
                 refresh: Callable[[], None] = lambda: None,
                 unfetched: Callable[[], dict] = dict,
                 store_notes: Callable[[], list] = list) -> None:
        self.watch, self.catalog, self.installed = watch, catalog, installed
        self.plan_install, self.plan_remove = plan_install, plan_remove
        self.go, self.stop, self.back = go, stop, back
        self.migration_go, self.migration_cancel = migration_go, migration_cancel
        self.refresh, self.unfetched, self.store_notes = refresh, unfetched, store_notes
        self.refreshing = False                          # R: read the list again once it lands
        self.looking = False                             # l: the staged files, at the checks
        self.scrolled = 0                                # ↑ ↓ on a migration's screens
        self.view = STORE
        self.word = ""                                   # the filter's word
        self.row: Buffer | None = None                   # the filter's row, while it is open
        self.choices: dict[str, Choice] = {}             # by name: their ticks stay
        self.entries: list[Entry] = []
        self.model: Checkboxes | None = None
        self.questions: Conflicts | None = None          # the plan's, in ASKING
        self.asked_plan = None                           # the plan they belong to, and
                                                         # how often it was asked
        self.old_lines: dict[str, str] = {}              # "memory:<name>": replace or keep
        self.problem: str | None = None                  # the store couldn't be read
        self.top = 0
        self.lines_drawn = 0
        self.rows_at = 2
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
        return self.row is not None or self.watch().state in (ASKING, MIGRATING, MIGRATION)

    def hint(self) -> str:
        state = self.watch().state
        if self.row is not None:
            return "type a word · Enter keep it · Esc leave the row"
        if self.model is not None and self.model.viewing is not None:
            return "↑ ↓ scroll · Esc back"
        if state == PLANNING:
            return "working it out… · Esc stop"
        if state == MIGRATING:
            return "the AI works · Esc cancels this migration once it is done"
        if state == MIGRATION:
            phase = self.watch().phase
            if phase == CHECKED:
                return ("↑ ↓ scroll · l back to the checks" if self.looking else
                        "Enter accept · r roll back · l look first · ↑ ↓ scroll")
            return ("Enter migrate · q cancel · ↑ ↓ scroll" if phase == PLAN
                    else "Enter let the AI · q leave it out")
        if state == ASKING:
            keys = ["o s k f r m on a row", "O overwrite all", "S skip all"] if self._has_questions() else []
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
        state = self.watch().state
        if state == MIGRATION:
            return "cancel"
        return "stop" if state in (PLANNING, WRITING, MIGRATING) else "close"

    def leave(self) -> bool:
        state = self.watch().state
        if self.row is not None:
            self._close_row()
        elif self.model is not None and self.model.viewing is not None:
            self.model.viewing = None
        elif state in (PLANNING, WRITING, MIGRATING):
            self.stop()
        elif state == MIGRATION:
            self.looking = False
            self.migration_cancel()
        elif state == ASKING and self.watch().landed:
            self.host.say("a migration has landed: its data is in the new format, so Enter "
                          "installs the new version now")
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
            old = kept.get(entry.shown)
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
            self.choices[entry.shown] = Choice(
                entry.shown, entry.manifest, ticked=old.ticked if old else False, extras=extras,
                labels=entry.labels, note=" · ".join(notes), bad=bool(entry.problems),
                card=list(entry.card), review=list(entry.review))
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
            out.append(self.choices[entry.shown])
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
        asked = (seen.plan, seen.asked)
        if self.questions is not None and (seen.state != ASKING or self.asked_plan != asked):
            self.questions, self.asked_plan = None, None
        if seen.state == ASKING and self.questions is None:
            self.questions = Conflicts(seen.plan.grouped())
            self.asked_plan = asked
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
        if self.refreshing and seen.state in (LISTING, FAILED):
            self.refreshing = False
            self._read(fresh=True)
        if seen.state == PLANNING:
            if seen.merging:
                return [[("bold", " The AI is merging the memory files…")]]
            if seen.doing == "refresh":
                return [[("bold", " Downloading the stores' indexes and their packages…")]]
            what = "removing" if seen.doing == "remove" else "installing"
            return [[("bold", f" Working out what {what} would write…")]]
        if seen.state == MIGRATING:
            return [[("bold", f" {seen.busy}")], [],
                    [(NOTE, " Nothing in the world changes until you accept.")]]
        if seen.state == MIGRATION:
            lines = self._migration(seen)
            self.scrolled = max(0, min(self.scrolled, len(lines) - 3))
            return lines[self.scrolled:]
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
        stores = sorted({e.where for e in self.entries} | set(self.unfetched()) | {"local"},
                        key=lambda where: (where != "local", where))
        count = len(self.entries)
        head = f" {' + '.join(stores)} · {count} package{'s' * (count != 1)}"
        refresh = " · R refresh" if len(stores) > 1 else ""
        view = f" · {self.view}" if self.view != STORE else ""
        found = f" · “{self.word}”" if self.word else ""
        keys = f"+ - all · u updates · i installed · / find{refresh}"
        first = head + view + found + f"    installed here: {here}"
        if len(first) + 4 + len(keys) < self._width():
            lines = [[("bold", head + view + found),
                      (NOTE, f"    installed here: {here}    {keys}")], []]
        else:                                            # too narrow: the keys go below
            lines = [[("bold", head + view + found), (NOTE, f"    installed here: {here}")],
                     [(NOTE, f" {keys}")], []]
        for where, count in sorted(self.unfetched().items()):
            lines.insert(1, [(NOTE, f" {where}: {count} package{'s' * (count != 1)} not "
                                    f"downloaded yet · R downloads them")])
        for note in self.store_notes():
            lines.insert(1, [(WARNED, f" {note}")])
        if not self.entries and self.unfetched():
            return lines
        if not self.entries:
            return lines + [[(NOTE, " The store has no packages yet: hpm publish puts one there, "
                                    "from your terminal.")]]
        if not self.model.choices:
            return lines + [[(NOTE, " Nothing here in this view.")]]
        self.model.summary_width = max(12, min(40, self._width() - 62))
        self.rows_at = len(lines)                        # where the rows start, for the scroll
        for i, row in enumerate(self.model.rows()):
            mark = [("reverse", "▸")] if i == self.model.cursor else [("", " ")]
            lines.append(mark + [("", " ")] + _styled(row))
        lines += [_styled(line) for line in self.model.tail()]
        return lines

    def _wrapped(self, style: str, text: str) -> list[list]:
        """A line of a migration's screens, folded at the tab's width: a check or a note of
        the AI's can be long, and nothing of it may be cut off."""
        indent = " " * (len(text) - len(text.lstrip()) + 2)
        folded = textwrap.wrap(text, max(30, self._width() - 2), subsequent_indent=indent,
                               break_on_hyphens=False) or [""]
        return [[(style, " " + line)] for line in folded]

    def _migration(self, seen: Seen) -> list[list]:
        item, m = seen.item, seen.migration
        lines = [row for line in seen.said for row in self._wrapped(NOTE, line)]
        lines += [[]] if seen.said else []
        if seen.phase == LET:
            pending = item.incoming if seen.incoming else item.migrate
            start, end = pending.notes[0].old, pending.notes[-1].new
            what = f"{item.name}'s data" + (" coming in" if seen.incoming else "")
            lines += self._wrapped("bold", f"{what} is in format {start}; {item.name} "
                                           f"{item.release.version} needs {end}.")
            lines += self._wrapped("", "The AI migrates it first, into a staging folder: "
                                       "nothing in the world changes until you accept.")
            lines += self._wrapped(NOTE, f"Its notes: {', '.join(n.name for n in pending.notes)}; "
                                         f"for each, a plan and a migration, each a session of "
                                         f"the AI at most at the cap of hpm's config.toml.")
            lines += [[]] + self._wrapped(NOTE, f"Enter lets the AI start · q leaves {item.name} "
                                                f"out, and nothing of it is written")
            return lines
        if seen.phase == PLAN:
            for i, line in enumerate(m.plan_lines()):
                lines += self._wrapped("bold" if i == 0 else "", line)
            return lines + [[], [(NOTE, " Enter migrate · q cancel (nothing changes)")]]
        if self.looking:
            return lines + [row for line in m.look_lines() for row in self._wrapped("", line)] + [
                [], [(NOTE, " l back to the checks")]]
        for i, line in enumerate(m.checked_lines()):
            style = "bold" if i == 0 else LOUD if line.lstrip().startswith("✗") else ""
            lines += self._wrapped(style, line)
        return lines + [[], [(NOTE, " Enter accept (the old paths go, the backup stays) · "
                                    "r roll back · l look first")]]

    def _asking(self, seen: Seen) -> list[list]:
        plan = seen.plan
        lines = [row for line in seen.said for row in self._wrapped(NOTE, line)]
        lines += [[]] if seen.said else []
        for item in plan.items:
            if item.blocked:
                lines += self._wrapped(LOUD, f"✗ {item.name}: {item.blocked}")
                continue
            if item.skip:
                lines += self._wrapped(NOTE, f"– {item.name}: {item.skip}")
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
            if item.migrate:
                lines.append([(WARNED, f"   its data migrates {item.migrate.notes[0].old} → "
                                       f"{item.migrate.notes[-1].new} first, with the AI")])
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
        for path, text in seen.merged.items():
            body = text.splitlines()
            lines += [[], [("bold", f" merged by the AI: {path}")]]
            lines += [[("", "   " + line)] for line in body[:12]]
            if len(body) > 12:
                lines.append([(NOTE, f"   … and {len(body) - 12} more lines")])
        for path, why in seen.unmerged.items():
            lines += [[], [(WARNED, f" {path} can't be merged ({why}): it is skipped")]]
        if plan.migrations():
            lines += [[], [(NOTE, " Enter goes on to the migrations; Esc goes back, and nothing "
                                  "is written.")]]
        elif seen.landed:
            lines += [[], [(NOTE, " Enter writes it (its data is migrated already).")]]
        else:
            lines += [[], [(NOTE, " Enter writes it; Esc goes back, and nothing is written.")]]
        return lines

    def _progress(self, seen: Seen) -> list[list]:
        lines = [row for line in seen.said for row in self._wrapped(NOTE, line)]
        lines += [[]] if seen.said else []
        lines += [[("bold", " Removing…" if seen.doing == "remove" else " Installing…")]] \
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
                lines += self._wrapped(NOTE, f"backup: {seen.outcome.backup} (hpm rollback in "
                                             f"your terminal, once the world is stopped)")
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
            row = self.rows_at + self.model.cursor
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
        migration = Condition(lambda: self.watch().state == MIGRATION)
        migrating = Condition(lambda: self.watch().state == MIGRATING)
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
        kb.add("R", filter=listing)(to(self._refresh))
        kb.add("enter", filter=listing)(to(self._install))
        kb.add("up", filter=viewing)(to(lambda: self.model._scroll(-1)))
        kb.add("down", filter=viewing)(to(lambda: self.model._scroll(1)))

        for key, answer in (("o", "overwrite"), ("s", "skip"), ("k", "both"), ("f", "fail"),
                            ("r", "remove"), ("m", "merge")):
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
        kb.add("enter", filter=migration)(to(self._migration_go))
        kb.add("q", filter=migration)(to(lambda: self._migration_key("q")))
        kb.add("r", filter=migration)(to(lambda: self._migration_key("r")))
        kb.add("l", filter=migration)(to(lambda: self._migration_key("l")))
        kb.add("up", filter=migration)(to(lambda: self._scroll_migration(-1)))
        kb.add("down", filter=migration)(to(lambda: self._scroll_migration(1)))
        kb.add(Keys.Any, filter=migration)(lambda event: None)
        kb.add(Keys.Any, filter=migrating)(lambda event: None)

        kb.add(Keys.Any, filter=in_row)(lambda event: self._type(event.data))
        kb.add("backspace", filter=in_row)(to(self._erase))
        kb.add("enter", filter=in_row)(to(self._close_row))
        return kb

    def _migration_go(self) -> None:
        if self.looking:
            return
        self.scrolled = 0
        self.migration_go()

    def _scroll_migration(self, by: int) -> None:
        self.scrolled = max(0, self.scrolled + by)

    def _migration_key(self, key: str) -> None:
        """q at the start and at the plan, r and l at the checks."""
        phase = self.watch().phase
        if key == "l" and phase == CHECKED:
            self.looking, self.scrolled = not self.looking, 0
        elif (key == "q" and phase in (LET, PLAN)) or (key == "r" and phase == CHECKED):
            self.looking, self.scrolled = False, 0
            self.migration_cancel()

    def _refresh(self) -> None:
        self.refreshing = True
        self.refresh()

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
        name = choice.name.rsplit("/", 1)[-1]             # danika/kittystory: kittystory
        if name not in self.installed():
            self.host.say(f"{name} isn't installed here")
            return
        self.plan_remove(name)

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
