"""The Details tab of hallux's own panel: one job and what it has been doing, or one idle
agent and what it is.

It shows the row that is picked in the Agents tab, which the host keeps for both tabs. It
is given the same two functions, watch() and kill(pid), and reads watch() anew at every
redraw: a job's lines appear as they happen. The view stays at the newest line unless the
user scrolls up. What is shown here was cleaned and cut when hallux.agents kept it; the tab
only draws it.
"""
from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass
from typing import Callable

from prompt_toolkit.application import get_app
from prompt_toolkit.data_structures import Point
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from hallux.agents import Declared, Seen, Watched
from hallux.panel import Tab
from hallux.panel_tabs.agents import NO_AGENT, Asking, Row, cost, cut, picked, ready, rows
from hallux.statusbar import GRAY, clock, tokens

RESULT = "→"                                  # the kind of a line that holds a tool's answer
KIND_MIN, KIND_MAX = 6, 12                    # columns of a line's kind: "status", a tool's name
WHEEL = 3                                     # lines the wheel scrolls
NOTE = f"fg:{GRAY}"


@dataclass
class Drawn:
    head: list[tuple[str, str]]               # two lines, which stay: (style, text)
    body: list[tuple[str, str]]               # the lines that scroll, oldest first


def draw(row: Row | None, width: int = 80) -> Drawn:
    """The whole tab as text, for the row that is picked."""
    if row is None:
        return Drawn([("", ""), ("", "")], [])
    return _job(row.job, width) if row.job is not None else _agent(row.agent, width)


def _job(seen: Seen, width: int) -> Drawn:
    its = seen.row
    # "waiting in check": the call's name. Its file is in the lines below.
    state = its["state"] + (f" in {its['tool'].split(' ')[0]}" if "tool" in its else "")
    facts = [str(its["pid"]), its["addon"], its["agent"], state, clock(its["seconds"]),
             f"{tokens(its['tokens'])} tok"]
    if "cost_usd" in its:
        facts.append(cost(its))
    may = (f"may change: {', '.join(os.path.basename(path) for path in seen.edit)}"
           if seen.edit else "creates files only")
    head = [("bold", cut(" " + " · ".join(facts), width - 1)),
            (NOTE, cut(f" folder {its['folder']} · {may}", width - 1))]
    kinds = [line.kind for line in seen.activity if line.kind != RESULT]
    kind_width = min(KIND_MAX, max([KIND_MIN, *(len(kind) for kind in kinds)]))
    indent = 1 + 5 + 2 + kind_width + 2                  # " 0:02  status  "
    room = max(10, width - 1 - indent)
    body: list[tuple[str, str]] = []
    for line in seen.activity:
        if line.kind == RESULT:                          # under the call it answers
            first, style = " " * indent + f"{RESULT} ", NOTE
            text = textwrap.wrap(line.text, room - 2)
        else:
            first = f" {clock(line.at):>5}  {cut(line.kind, kind_width):<{kind_width}}  "
            style, text = "", textwrap.wrap(line.text, room)
        text = text or [""]
        body.append((style, first + text[0]))
        body += [(style, " " * len(first) + more) for more in text[1:]]
    return Drawn(head, body)


def _agent(agent: Declared, width: int) -> Drawn:
    asks = f"asks for effort {agent.asks}" if agent.asks else "asks for no effort"
    gets = f"gets {agent.model}" + (f", effort {agent.effort}" if agent.effort else ", no effort")
    head = [("bold", cut(f" {agent.addon} · {agent.name} · idle · {ready(agent)}", width - 1)),
            (NOTE, cut(f" {asks} · {gets}", width - 1))]
    tools = ", ".join(agent.tools) or "none of its addon's"
    body = [("", f" tools: {tools}"), ("", ""), (NOTE, " instructions")]
    for paragraph in agent.prompt.splitlines():
        body += [("", f" {line}") for line in textwrap.wrap(paragraph, max(10, width - 2)) or [""]]
    return Drawn(head, body)


class DetailsTab(Asking, Tab):
    title = "Details"
    esc = "back"                                         # Esc goes back to the Agents tab

    def __init__(self, watch: Callable[[], Watched], kill: Callable[[int], None]) -> None:
        self.watch, self.kill = watch, kill
        self.top: int | None = None                      # the first line in view; None: the
        self.cursor = Point(0, 0)                        # view follows the newest line
        self.body = Window(FormattedTextControl(self._body, focusable=True,
                                                get_cursor_position=lambda: self.cursor),
                           always_hide_cursor=True)
        self.container = HSplit([Window(height=1),
                                 Window(FormattedTextControl(self._head), height=2),
                                 Window(height=1), self.body])
        self.bindings = self._bindings()

    # ---------------------------------------------------------------- what the host asks

    @property
    def typing(self) -> bool:
        return self.asking is not None

    def hint(self) -> str:
        if self.asking is not None:
            return self.question()
        return "← → other agent · ↑ ↓ scroll · k kill"

    def disabled(self) -> str | None:
        return None if self.watch().agents else NO_AGENT

    def leave(self) -> bool:
        if self.asking is not None:
            self.asking = None
        else:
            self.host.show("Agents")                     # the panel stays open
        return True

    def shown(self) -> None:
        self.top, self.asking = None, None

    # ---------------------------------------------------------------- drawing

    def _current(self) -> Row | None:
        """The row that is picked; the first one, when nothing is."""
        listed = rows(self.watch())
        return listed[picked(listed, self.host.pick)] if listed else None

    def _drawn(self) -> Drawn:
        return draw(self._current(), get_app().output.get_size().columns)

    def _head(self) -> list:
        lines = self._drawn().head
        return [part for style, text in lines for part in ((style, text), ("", "\n"))][:-1]

    def _body(self) -> list:
        lines = self._drawn().body
        width = get_app().output.get_size().columns
        if self.top is None:                             # the window scrolls to its cursor:
            self.cursor = Point(0, max(0, len(lines) - 1))       # the newest line
        else:
            self.top = max(0, min(self.top, len(lines) - 1))
            self.body.vertical_scroll = self.top
            self.cursor = Point(0, self.top)
        parts = [part for style, text in lines           # the wheel works on the whole row
                 for part in ((style, f"{text:<{width - 1}}", self._wheel), ("", "\n"))]
        return parts[:-1]

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
        free = self.bind_question(kb)
        kb.add("up", filter=free)(lambda event: self._scroll(-1))
        kb.add("down", filter=free)(lambda event: self._scroll(1))
        kb.add("pageup", filter=free)(lambda event: self._scroll(1 - self._height()))
        kb.add("pagedown", filter=free)(lambda event: self._scroll(self._height() - 1))
        kb.add("left", filter=free)(lambda event: self._other(-1))
        kb.add("right", filter=free)(lambda event: self._other(1))
        kb.add("k", filter=free)(lambda event: self.ask(self._current()))
        return kb

    def _scroll(self, by: int) -> None:
        """Move the view. At the bottom it follows the newest line again."""
        last = max(0, len(self._drawn().body) - self._height())      # the top, at the bottom
        top = max(0, (last if self.top is None else self.top) + by)
        self.top = None if top >= last else top

    def _other(self, by: int) -> None:
        """The row before or after, in the Agents tab's order."""
        listed = rows(self.watch())
        if listed:
            at = max(0, min(len(listed) - 1, picked(listed, self.host.pick) + by))
            self.host.pick, self.top = listed[at].key, None
