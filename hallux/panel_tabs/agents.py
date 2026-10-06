"""The Agents tab of hallux's own panel: the jobs of the addons' agents, and the agents that
are idle.

The tab knows nothing of the machine. It is given two functions: watch() says what to show
(hallux.agents.Jobs.watch) and kill(pid) ends a job. It reads watch() anew at every redraw,
so a row changes when its job reports, and the times count while the terminal's beat draws.

What it shares with the Details tab is here too: the rows in their order, which of them is
picked, and the question before a kill.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from prompt_toolkit.application import get_app
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, ScrollOffsets, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from hallux.agents import ENDED, Declared, Seen, Watched
from hallux.panel import Tab
from hallux.statusbar import GRAY, clock, spent, tokens

NO_AGENT = "no attached addon has an agent"   # why both tabs can't be chosen on such a machine
BUSY = "already running"                      # why_not of an agent whose job runs: it isn't idle
HEADS = ("PID", "ADDON", "AGENT", "STATE", "TIME", "TOKENS", "COST", "STATUS")
NAME_MAX = 12                                 # columns of an addon's or an agent's name
NOTE, CURRENT = f"fg:{GRAY}", "reverse"

Part = tuple[str, str, object]                # a style, a text, and the row a click on it picks


@dataclass(frozen=True)
class Row:
    """A row of the list: a job, or an agent that is idle."""
    key: object                               # what the panel's pick holds for it: a job's
    job: Seen | None = None                   # pid, or an idle agent's addon
    agent: Declared | None = None

    @property
    def runs(self) -> bool:
        return self.job is not None and self.job.row["state"] not in ENDED


def rows(watched: Watched, idle: bool = True) -> list[Row]:
    """The rows in their order: the jobs that run, then the ones that have ended, the newest
    on top in each, then the agents that are idle."""
    listed = [Row(seen.row["pid"], job=seen) for seen in watched.jobs]
    if idle:
        listed += [Row(agent.addon, agent=agent) for agent in watched.agents
                   if agent.why_not != BUSY]
    return listed


def picked(listed: list[Row], pick: object) -> int:
    """Where the picked row is. The first one, when the pick is none of them."""
    return next((at for at, row in enumerate(listed) if row.key == pick), 0)


def ready(agent: Declared) -> str:
    """What an idle agent's row says: that it could start, or why it can't."""
    if agent.why_not:
        return f"can't start: {agent.why_not}"
    return "ready" + (f" · effort {agent.effort}" if agent.effort else "")


def cost(row: dict) -> str:
    """A job's dollars: known once it has ended, and its worker has said what it cost."""
    if "cost_usd" not in row:
        return "·"
    return "?" if row["cost_usd"] == "unknown" else spent(row["cost_usd"])


def cut(text: str, width: int) -> str:
    return text if len(text) <= width else text[:max(0, width - 1)] + "…"


@dataclass
class State:
    """Where the user is in the tab."""
    hide_idle: bool = False                   # `i` hides the idle agents
    asking: int | None = None                 # the pid of the job a kill is asked for


@dataclass
class Drawn:
    head: list[Part]                          # the columns' names, which stay
    rows: list[list[Part]]                    # the part that scrolls, line by line
    under: list[Part]                         # the line under the list, which stays
    cursor: Point                             # in the rows: the line to keep in view


def draw(watched: Watched, state: State, pick: object, width: int = 80) -> Drawn:
    """The whole tab as text, from what watch() says and where the user is."""
    listed = rows(watched, not state.hide_idle)
    at = picked(listed, pick)
    names = [(row.job.row["addon"], row.job.row["agent"]) if row.job
             else (row.agent.addon, row.agent.name) for row in listed]
    addon_width = min(NAME_MAX, max([len(HEADS[1]), *(len(addon) for addon, _ in names)]))
    agent_width = min(NAME_MAX, max([len(HEADS[2]), *(len(agent) for _, agent in names)]))

    def line(pid: str, addon: str, agent: str, state_: str, time: str, tok: str, dollars: str,
             status: str) -> str:
        left = (f" {pid:>5}  {cut(addon, addon_width):<{addon_width}}  "
                f"{cut(agent, agent_width):<{agent_width}}  {state_:<7} {time:>5} {tok:>6} "
                f"{dollars:>7}  ")                       # close together: the status needs room
        return left + cut(status, max(0, width - 1 - len(left)))

    drawn: list[list[Part]] = []
    for here, ((addon, agent), row) in enumerate(zip(names, listed)):
        if row.job is not None:
            its = row.job.row
            text = line(str(its["pid"]), addon, agent, its["state"], clock(its["seconds"]),
                        tokens(its["tokens"]), cost(its),
                        its["status"] if row.job.ended is None else row.job.ended)
        else:
            text = line("·", addon, agent, "idle", "·", "·", "·", ready(row.agent))
        style = CURRENT if here == at else ""
        drawn.append([(style, f"{text:<{width - 1}}" if here == at else text, row.key)])
    running = sum(row.runs for row in listed)
    ended = sum(row.job is not None and not row.runs for row in listed)
    under = (f" {running} running · {ended} ended · jobs in this boot: "
             f"{spent(watched.spent_boot)}")
    return Drawn([("bold", line(*HEADS), None)], drawn, [(NOTE, under, None)], Point(0, at))


class Asking:
    """The question before a kill, which both tabs ask the same way. `k` on a job that runs
    asks `kill 30005? y/n` in the foot, as the tab's own hint. While it is asked the tab
    counts as typing, so the host takes no letter for itself. `y` kills. Any other typed key
    drops the question, and so do Esc, a click on another row, and the panel closing."""

    kill: Callable[[int], None]
    asking: int | None = None

    def ask(self, row: Row | None) -> None:
        if row is not None and row.runs:      # an ended job and an idle agent have nothing
            self.asking = row.key             # to kill

    def answer(self, yes: bool) -> None:
        pid, self.asking = self.asking, None
        if yes and pid is not None:
            try:
                self.kill(pid)
            except OSError:                   # it ended while the question stood
                pass

    def question(self) -> str:
        return f"kill {self.asking}? y/n"

    def bind_question(self, kb: KeyBindings) -> Condition:
        """Bind the question's keys. Returns the filter for the tab's other keys."""
        asked = Condition(lambda: self.asking is not None)
        kb.add("y", filter=asked)(lambda event: self.answer(True))
        kb.add(Keys.Any, filter=asked)(lambda event: self.answer(False))
        return ~asked


class AgentsTab(Asking, Tab):
    title = "Agents"

    def __init__(self, watch: Callable[[], Watched], kill: Callable[[int], None]) -> None:
        self.watch, self.kill = watch, kill
        self.state = State()
        self.cursor = Point(0, 0)
        rows_ = FormattedTextControl(self._rows, focusable=True,
                                     get_cursor_position=lambda: self.cursor)
        self.container = HSplit([                        # the names stay, the rows scroll
            Window(height=1),
            Window(FormattedTextControl(lambda: self._clickable(self._drawn().head)), height=1),
            Window(rows_, always_hide_cursor=True, dont_extend_height=True,
                   scroll_offsets=ScrollOffsets(top=1, bottom=1)),
            Window(height=1),
            Window(FormattedTextControl(lambda: self._clickable(self._drawn().under)), height=1),
            Window()])                                   # what is left of a tall window
        self.bindings = self._bindings()

    # ---------------------------------------------------------------- what the host asks

    @property
    def typing(self) -> bool:
        return self.asking is not None

    def hint(self) -> str:
        if self.asking is not None:
            return self.question()
        idle = "show" if self.state.hide_idle else "hide"
        return f"↑ ↓ pick · Enter details · k kill · i {idle} idle agents"

    def disabled(self) -> str | None:
        return None if self.watch().agents else NO_AGENT

    def wants_first(self) -> bool:
        """The panel opens here while a job runs."""
        return any(row.runs for row in rows(self.watch()))

    def leave(self) -> bool:
        if self.asking is None:
            return False
        self.asking = None
        return True

    def shown(self) -> None:
        self.state, self.asking = State(), None          # the idle agents are shown again

    # ---------------------------------------------------------------- drawing

    def _listed(self) -> list[Row]:
        return rows(self.watch(), not self.state.hide_idle)

    def _drawn(self) -> Drawn:
        width = get_app().output.get_size().columns
        return draw(self.watch(), self.state, self.host.pick, width)   # anew at every redraw

    def _rows(self) -> list:
        drawn = self._drawn()
        self.cursor = drawn.cursor
        lines = [self._clickable(line) for line in drawn.rows]
        return [part for line in lines for part in (*line, ("", "\n"))][:-1]

    def _clickable(self, line: list[Part]) -> list:
        return [(style, text) if key is None else (style, text, self._click(key))
                for style, text, key in line]

    def _click(self, key: object) -> Callable[[MouseEvent], None]:
        def handle(event: MouseEvent) -> None:
            if event.event_type != MouseEventType.MOUSE_UP:
                return
            if key != self.host.pick:                    # another row: the question is gone
                self.asking = None
            self.host.pick = key
        return handle

    # ---------------------------------------------------------------- keys

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()
        free = self.bind_question(kb)
        kb.add("up", filter=free)(lambda event: self._move(-1))
        kb.add("down", filter=free)(lambda event: self._move(1))
        kb.add("enter", filter=free)(lambda event: self._details())
        kb.add("k", filter=free)(lambda event: self.ask(self._current()))
        kb.add("i", filter=free)(lambda event: self._toggle_idle())
        return kb

    def _current(self) -> Row | None:
        listed = self._listed()
        return listed[picked(listed, self.host.pick)] if listed else None

    def _move(self, by: int) -> None:
        listed = self._listed()
        if listed:
            at = max(0, min(len(listed) - 1, picked(listed, self.host.pick) + by))
            self.host.pick = listed[at].key

    def _details(self) -> None:
        if (row := self._current()) is not None:
            self.host.pick = row.key                     # the first row, when nothing was picked
            self.host.show("Details")

    def _toggle_idle(self) -> None:
        self.state.hide_idle = not self.state.hide_idle
