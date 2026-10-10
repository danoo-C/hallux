"""The Config tab of hallux's own panel, in a real panel on a pipe. The four functions it is
given are fakes that note their calls."""
import asyncio
import dataclasses
from dataclasses import fields
from pathlib import Path

import pytest

pytest.importorskip("prompt_toolkit")

from test_panel import ESC, StandIn, click, drawn, session  # noqa: E402

from hallux import config  # noqa: E402
from hallux.config import Hardware, View  # noqa: E402
from hallux.panel import Panel  # noqa: E402
from hallux.panel_tabs.config import (  # noqa: E402
    AGENTS, BUTTONS, LABEL_WIDTH, LABELS, ConfigTab, State, draw, stops,
)

UP, DOWN, LEFT, RIGHT, HOME, END = "\x1b[A", "\x1b[B", "\x1b[D", "\x1b[C", "\x1b[H", "\x1b[F"
BACKSPACE, DELETE, ENTER, CTRL_U = "\x7f", "\x1b[3~", "\r", "\x15"


class Machine:
    """What stands in for the machine: a view, and the three things the tab can ask for."""

    agents = False                           # the machine has an addon with an agent

    def __init__(self, hardware=Hardware(), **view):
        self.hardware, self.calls, self.reasons = hardware, [], {}
        self.shown = dict(running=hardware, spent_boot=0.0, spent_since_refill=None,
                          spent_ticks=None, spent_events=0.0, paused=frozenset(),
                          from_flags=frozenset(), unsaved=set(),
                          path=Path("/home/user/world/.hallux/config.toml")) | view
        self.save_says = None

    def view(self):
        shown = dict(self.shown, unsaved=frozenset(self.shown["unsaved"]))
        if shown["spent_since_refill"] is None:
            shown["spent_since_refill"] = shown["spent_boot"]
        return View(hardware=self.hardware, **shown)

    def change(self, name, text):
        self.calls.append(("change", name, text))
        if name in self.reasons:
            return self.reasons[name]
        try:
            value = config.typed(name, text)
        except ValueError as e:
            return str(e)
        self.hardware = dataclasses.replace(self.hardware, **{name: value})
        self.shown["unsaved"].add(name)

    def save(self):
        self.calls.append(("save",))
        return self.save_says

    def refill(self):
        self.calls.append(("refill",))
        return "budgets refilled"

    def tab(self):
        return ConfigTab(self.view, self.change, self.save, self.refill, agents=self.agents)


class MachineWithAnAgent(Machine):
    agents = True


def text(machine, state=None):
    """The whole tab as text, as draw() gives it."""
    result = draw(machine.view(), state or State(), machine.agents)
    return "\n".join("".join(part[1] for part in line) for line in (*result.rows, result.buttons))


def to(stop, start=None, agents=False):
    """The keys that move to this row or button: from the first row, or from `start`."""
    order = stops(agents)
    steps = order.index(stop) - (order.index(start) if start else 0)
    return (DOWN if steps > 0 else UP) * abs(steps)


def on(machine, script, extra=(), **size):
    """Show a panel with the Config tab of this machine and run the script on it."""
    panel = Panel([*extra, machine.tab()])
    return session(panel, lambda press: script(press, panel), **size)


def test_every_setting_has_a_row():
    assert set(LABELS) == {f.name for f in fields(Hardware)}
    assert stops(agents=True) == [name for name in LABELS if config.WHEN[name] == "now"] + [
        name for name in LABELS if config.WHEN[name] == "reboot"] + list(BUTTONS)
    assert stops() == [stop for stop in stops(agents=True) if stop not in AGENTS]
    assert len(stops()) == 9                                # six rows that change, three buttons
    assert len(stops(agents=True)) == 15                    # and the six of the addon agents


def test_no_label_runs_into_its_value():
    """Tried in the check of 2026-10-05: "Agent effort, at most" and "Budget for all jobs" did."""
    assert max(len(label) for label in LABELS.values()) < LABEL_WIDTH
    shown = text(MachineWithAnAgent())
    assert all(f"    {label:<{LABEL_WIDTH}}" in shown for label in LABELS.values())


def test_the_agents_rows_are_hidden_until_the_tab_is_told():
    hidden, told = text(Machine()), text(MachineWithAnAgent())
    assert not any(LABELS[name] in hidden for name in AGENTS)
    assert all(LABELS[name] in told for name in AGENTS)
    without = [line for line in told.splitlines()
               if not line.strip().startswith(tuple(LABELS[name] for name in AGENTS))]
    assert "\n".join(without) == hidden                     # nothing else differs but those rows

    async def script(press, panel):
        await press(to("event_budget_usd") + DOWN + ENTER)  # the row after it, on this machine
        return panel.tab.state.open

    assert on(Machine(), script) == "effort"                # the arrow keys pass over the six
    assert on(MachineWithAnAgent(), script) == "agent_model"


def test_the_agents_rows_as_they_are_shown():
    machine = MachineWithAnAgent(Hardware(agent_model="claude-haiku-4-5", agent_max_effort="xhigh",
                                          agent_max_running=3, agent_job_budget_usd=0.125,
                                          agent_budget_usd=4, agent_timeout_seconds=90.5))
    assert text(MachineWithAnAgent()).split("\n\n")[1] == """\
  Changes now
    Model              claude-opus-5-5
    Budget per boot    none                spent in this boot: ~$0.00
    Tick budget        $0.25
    Event budget       $0.25               spent since you typed: ~$0.00
    Agent model        same as Model
    Max agent effort   high
    Agents at once     2
    Budget per job     $2.00
    Budget, all jobs   $4.00               spent since you typed: ~$0.00
    Time per job       600s"""
    shown = {line[4:23].strip(): line[23:].strip() for line in text(machine).splitlines()}
    assert [shown[LABELS[name]] for name in AGENTS] == [
        "claude-haiku-4-5", "xhigh", "3", "$0.125",
        "$4.00               spent since you typed: ~$0.00", "90.5s"]


def test_the_budget_for_all_jobs_shows_what_was_spent_since_it_was_filled():
    machine = MachineWithAnAgent(spent_jobs=0.3)

    async def script(press, panel):
        before = drawn(panel)
        machine.shown["spent_jobs"] = 0.61                  # a job ends while the panel is open
        await press(DOWN)
        return before, drawn(panel)

    before, after = on(machine, script)
    assert any(line.rstrip().endswith("Budget, all jobs   $4.00               "
                                      "spent since you typed: ~$0.30") for line in before)
    assert any("spent since you typed: ~$0.61" in line for line in after)
    assert "spent since you typed: ~$0.30" not in text(Machine(spent_jobs=0.3))   # no agent, no row


def test_what_was_spent_has_the_tilde_and_a_limit_has_none():
    """What was spent is what the tokens would cost at list prices, like the bar's cost. A
    limit is a number the user typed."""
    machine = MachineWithAnAgent(Hardware(max_budget_usd=2.0), spent_boot=1.42, spent_ticks=0.05,
                                 spent_events=0.1, spent_jobs=0.3)
    shown = text(machine)
    rows = {line[4:23].strip(): line[23:].rstrip() for line in shown.splitlines()}
    for label, limit, spent in (("Budget per boot", "$2.00", "spent in this boot: ~$1.42"),
                                ("Tick budget", "$0.25", "spent by this program: ~$0.05"),
                                ("Event budget", "$0.25", "spent since you typed: ~$0.10"),
                                ("Budget, all jobs", "$4.00", "spent since you typed: ~$0.30")):
        assert rows[label].startswith(f"{limit} ") and rows[label].endswith(spent)
    assert rows["Budget per job"] == "$2.00" and shown.count("~$") == 4
    machine.shown["spent_since_refill"] = 0.1
    assert "spent since the refill: ~$0.10 · this boot: ~$1.42" in text(machine)


@pytest.mark.parametrize("has_agent", [True, False])
def test_the_panel_the_app_builds_shows_the_six_rows_only_with_an_agent(tmp_path, monkeypatch,
                                                                       has_agent):
    """app.py tells the tab whether one of the attached addons has an agent."""
    import sys

    from test_addons import agented, fake

    from hallux import addons, app, machine, terminal
    from hallux.agents import Jobs
    from hallux.disk import Disk
    given = {}

    class Recorded(Machine):                                # this file's stand-in, made as
        def __init__(self, root, hardware, terminal, **more):    # the app makes a machine
            super().__init__(hardware)
            self.jobs = Jobs(Disk(root), lambda: hardware, addons=more["addons"])

        async def run(self):
            pass

    class Keyboard:
        power_cut = count_ctrl_c = staticmethod(lambda: None)

        def __init__(self, bar, **more):
            pass

        def set_panel(self, panel):
            given["panel"] = panel

    class Tty:
        isatty, write, flush = (lambda self: True), (lambda self, text: None), (lambda self: None)

    folder = tmp_path / "addons"
    folder.mkdir()
    (folder / "music.py").write_text(agented() if has_agent else fake())
    (tmp_path / "world").mkdir()
    monkeypatch.setattr(app, "ADDONS_FOLDER", folder)
    monkeypatch.setattr(machine, "Machine", Recorded)
    monkeypatch.setattr(terminal, "Terminal", Keyboard)
    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(sys, "stdout", Tty())
    monkeypatch.setattr(sys, "argv", ["hallux", str(tmp_path / "world")])
    try:
        app.main()
    finally:
        for handler in list(app.log.handlers):              # main() logs into the world's folder
            app.log.removeHandler(handler)
            handler.close()
        for name in [name for name in sys.modules if name.startswith(addons.MODULE_PREFIX)]:
            del sys.modules[name]
    panel = given["panel"]
    tab = panel.tabs[-1]                                    # Config, behind Agents and Details
    assert [(other.title, other.disabled() is None) for other in panel.tabs[:2]] == [
        ("Agents", has_agent), ("Details", has_agent)]      # grey without an agent

    async def script(press):
        before = "\n".join(drawn(panel))
        if has_agent:
            await press(to("agent_max_running", agents=True) + ENTER + "3" + ENTER)
        return before, "\n".join(drawn(panel))

    before, after = session(panel, script)
    assert tab.agents is has_agent
    assert all((LABELS[name] in before) is has_agent for name in AGENTS)
    if has_agent:                                           # and one of them can be changed
        assert "Agents at once     2" in before and "Agents at once     3" in after
        assert tab.view().hardware.agent_max_running == 3


@pytest.mark.parametrize("name, opens_with, how, offered", [
    ("agent_model", "", "type a name, or ↑ ↓ pick",
     ["› none", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"]),
    ("agent_max_effort", "high", "↑ ↓ pick", ["low", "medium", "› high", "xhigh", "max"]),
    ("agent_max_running", "2", "type a whole number", []),
    ("agent_job_budget_usd", "2.00", "type the dollars", []),
    ("agent_budget_usd", "4.00", "type the dollars", []),
    ("agent_timeout_seconds", "600", "type the seconds", []),
])
def test_each_agents_row_opens_with_its_own_hint_and_list(name, opens_with, how, offered):
    machine = MachineWithAnAgent()

    async def script(press, panel):
        await press(to(name, agents=True) + ENTER)
        return panel.tab.state.typed.text, drawn(panel)[-1], text(machine, panel.tab.state)

    line, foot, shown = on(machine, script)
    assert line == opens_with and foot == f" {how} · Enter take · Esc leave it as it was"
    listed = [row.strip() for row in shown.split(LABELS[name])[1].split("\n\n")[0].splitlines()[1:]]
    assert [row for row in listed if row.lstrip("› ") in config.EFFORTS + config.MODELS + ("none",)
            ] == offered


def test_an_agents_number_is_typed_and_its_effort_is_picked():
    machine = MachineWithAnAgent()

    async def script(press, panel):
        await press(to("agent_max_running", agents=True) + ENTER + "3" + ENTER)
        await press(to("agent_timeout_seconds", "agent_max_running", agents=True) + ENTER
                    + "90s" + ENTER)
        await press(to("agent_max_effort", "agent_timeout_seconds", agents=True) + ENTER)
        await press("max")                                  # nothing is typed into this row
        await press(DOWN + ENTER)
        await press(to("agent_model", "agent_max_effort", agents=True) + ENTER + DOWN + ENTER)
        return text(machine)

    shown = on(machine, script)
    assert machine.calls == [("change", "agent_max_running", "3"),
                             ("change", "agent_timeout_seconds", "90s"),
                             ("change", "agent_max_effort", "xhigh"),         # the next of the five
                             ("change", "agent_model", "claude-opus-5-5")]    # the one after none
    assert machine.hardware == Hardware(agent_max_running=3, agent_timeout_seconds=90.0,
                                        agent_max_effort="xhigh", agent_model="claude-opus-5-5")
    assert "Time per job       90s" in shown and "Agent model        claude-opus-5-5" in shown
    assert shown.endswith("4 changes not saved")


def test_the_agent_model_row_says_what_a_wrong_name_does():
    machine = MachineWithAnAgent()

    async def script(press, panel):
        await press(to("agent_model", agents=True) + ENTER)
        return text(machine, panel.tab.state)

    offered = on(machine, script)
    assert "a wrong name fails every job" in offered
    assert "ends Hallux" not in offered                     # that is the Model row's warning


def test_a_budget_that_cant_hold_with_the_other_is_refused_in_its_row():
    machine = MachineWithAnAgent()
    machine.reasons["agent_job_budget_usd"] = "is over the budget for all jobs"

    async def script(press, panel):
        await press(to("agent_job_budget_usd", agents=True) + ENTER + "3" + ENTER)
        return panel.tab.typing, drawn(panel)

    still_open, screen = on(machine, script)
    assert still_open and machine.hardware == Hardware()
    [row] = [line for line in screen if line.lstrip().startswith("Budget per job")]
    assert row.endswith("3                   is over the budget for all jobs")
    assert len(row) <= 80                                   # all of it, on a window of 80


def test_the_text_of_the_tab():
    machine = Machine(Hardware(max_budget_usd=2.0, effort="high", addons=("music", "window")),
                      running=Hardware(max_budget_usd=2.0), spent_boot=1.42, spent_ticks=0.25,
                      paused=frozenset({"tick_budget_usd"}), unsaved={"effort", "max_budget_usd"})
    assert text(machine) == """
  world/.hallux/config.toml

  Changes now
    Model              claude-opus-5-5
    Budget per boot    $2.00               spent in this boot: ~$1.42
    Tick budget        $0.25               spent by this program: ~$0.25 (paused)
    Event budget       $0.25               spent since you typed: ~$0.00

  Changes at the machine's next reboot
    Effort             high                running now: low
    Fallback model     none

  Set when Hallux starts (edit config.toml)
    Status bar         on
    Addons             music, window
    Transcripts        off
    OS sandbox         off

    [ Refill budgets ]   [ Save ]   [ Close ]      2 changes not saved"""


def test_values_and_notes_as_the_rows_show_them():
    machine = Machine(Hardware(model="claude-sonnet-5-5", effort="max",
                               fallback_model="claude-haiku-4-5", tick_budget_usd=0.125,
                               event_budget_usd=0, status_bar=False, keep_transcripts=True,
                               os_sandbox=True, addons=()),
                      running=Hardware(model="claude-haiku-4-5", effort="max"), spent_events=0.1,
                      paused=frozenset({"event_budget_usd", "max_budget_usd"}),
                      from_flags=frozenset({"model", "effort"}), unsaved={"effort"})
    shown = {line[4:23].strip(): line[23:].strip() for line in text(machine).splitlines()}
    assert shown["Model"] == ("claude-sonnet-5-5   running now: claude-haiku-4-5 · "
                              "from --model, for this run")
    assert shown["Effort"] == "max                 running now: none · from --effort, for this run"
    assert shown["Budget per boot"] == "none                spent in this boot: ~$0.00 (paused)"
    assert shown["Tick budget"] == "$0.125"                 # no program on screen: no note
    assert shown["Event budget"] == "$0.00               spent since you typed: ~$0.10 (paused)"
    assert shown["Fallback model"] == "claude-haiku-4-5"
    assert (shown["Status bar"], shown["Addons"], shown["Transcripts"], shown["OS sandbox"]) == (
        "off", "none", "on", "on")
    assert text(machine).endswith("[ Close ]      1 change not saved")
    assert "all that loaded" in text(Machine()) and "not saved" not in text(Machine())


def test_the_budget_per_boot_has_both_numbers_after_a_refill():
    machine = Machine(Hardware(max_budget_usd=2.0), spent_boot=1.52)
    assert "spent in this boot: ~$1.52" in text(machine)
    machine.shown["spent_since_refill"] = 0.10
    assert "spent since the refill: ~$0.10 · this boot: ~$1.52" in text(machine)
    assert "spent in this boot" not in text(machine)


def test_a_setting_is_drawn_in_the_group_of_its_when(monkeypatch):
    before = text(Machine()).split("\n\n")
    assert "Changes now" in before[1] and "Tick budget" in before[1]
    assert stops()[:4] == ["model", "max_budget_usd", "tick_budget_usd", "event_budget_usd"]
    monkeypatch.setitem(config.WHEN, "tick_budget_usd", "reboot")
    after = text(Machine()).split("\n\n")
    assert "Tick budget" in after[2] and "Tick budget" not in after[1]
    assert stops()[:4] == ["model", "max_budget_usd", "event_budget_usd", "tick_budget_usd"]


def test_change_a_number_save_and_close():
    """The step's "Done when": the tick budget is changed, Save is pressed, Esc closes."""
    machine = Machine()

    async def script(press, panel):
        opened_on = panel.tab.title
        await press(to("tick_budget_usd") + ENTER)
        open_row = panel.tab.typing, panel.tab.state.typed.text
        await press("1.25" + ENTER)                         # typed over the value that was there
        closed_row = panel.tab.typing, text(machine)
        await press(to("Save", "tick_budget_usd") + ENTER)
        said = drawn(panel)
        await press(ESC, wait=0.2)
        return opened_on, open_row, closed_row, said, panel.is_open

    opened_on, open_row, (typing, changed), said, still_open = on(machine, script)
    assert opened_on == "Config" and open_row == (True, "0.25")
    assert not typing and "Tick budget        $1.25" in changed
    assert machine.calls == [("change", "tick_budget_usd", "1.25"), ("save",)]
    assert any(line.endswith("[ Close ]      saved") for line in said) and not still_open


def test_a_stand_in_tab_is_in_the_row_and_can_be_chosen():
    machine = Machine()

    async def script(press, panel):
        first = panel.tab.title, drawn(panel)[0].split("Hallux")[1].strip()
        await press("j")
        return first, panel.tab.title, drawn(panel)[1]

    first, title, body = on(machine, script, extra=[StandIn("Jobs")])
    assert first == ("Config", "Jobs   [ Config ]") and (title, body) == ("Jobs", "this is Jobs")


def test_a_refused_value_stays_in_its_open_row():
    machine = Machine()
    machine.reasons["tick_budget_usd"] = "must be a number, 0 or more"

    async def script(press, panel):
        await press(to("tick_budget_usd") + ENTER + "abc" + ENTER)
        refused = panel.tab.typing, text(machine, panel.tab.state), drawn(panel)[-1]
        await press(ESC, wait=0)
        await asyncio.sleep(0.2)                            # within a fifth of a second
        return refused, (panel.tab.typing, panel.is_open, text(machine, panel.tab.state))

    (open_row, shown, foot), (typing, is_open, after) = on(machine, script)
    assert open_row
    assert "Tick budget        abc                 must be a number, 0 or more" in shown
    assert foot == " type the dollars · Enter take · Esc leave it as it was"
    assert (typing, is_open) == (False, True)               # Esc left the row, not the panel
    assert "Tick budget        $0.25" in after and "must be" not in after
    assert machine.calls == [("change", "tick_budget_usd", "abc")]      # and wasn't asked again


def test_effort_is_picked_from_its_five_values():
    machine = Machine()

    async def script(press, panel):
        await press(to("effort") + ENTER)
        offered = text(machine, panel.tab.state)
        await press("xhigh")                                # nothing is typed into this row
        await press(DOWN + ENTER)
        return offered, drawn(panel)[-1]

    offered, foot = on(machine, script)
    assert "\n".join(line.strip() for line in offered.splitlines()
                     if line.strip() in ("› low", "medium", "high", "xhigh", "max")) == (
        "› low\nmedium\nhigh\nxhigh\nmax")
    assert machine.calls == [("change", "effort", "medium")]            # the next of the five
    assert foot == " ↑ ↓ move · Enter change · Esc close"


def test_a_model_is_picked_from_the_list_or_typed():
    machine = Machine(running=Hardware(model="claude-opus-4-8"))

    async def script(press, panel):
        await press(to("model") + ENTER)
        offered = text(machine, panel.tab.state)
        await press(DOWN + ENTER)                           # picked: the next in the list
        await press(ENTER + "banana-1" + ENTER)             # typed, and "a" doesn't choose a tab
        await press(ENTER + LEFT + BACKSPACE + "2" + ENTER)     # an arrow keeps what is there
        return offered, panel.tab.title

    offered, title = on(machine, script, extra=[StandIn("Agents"), StandIn("Details")])
    listed = [line.strip() for line in offered.splitlines()
              if line.strip().startswith(("›", "claude"))]
    assert listed == ["› claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5",
                      "claude-opus-4-8"]                    # the three, and the one that runs
    assert "a wrong name is refused; saved, it ends Hallux at the next boot" in offered
    assert machine.calls == [("change", "model", "claude-sonnet-5-5"),
                             ("change", "model", "banana-1"), ("change", "model", "banana21")]
    assert title == "Config"


def test_the_fallback_models_list_starts_with_none():
    machine = Machine(Hardware(fallback_model="claude-haiku-4-5"))

    async def script(press, panel):
        await press(to("fallback_model") + ENTER + UP + UP + UP)
        offered = text(machine, panel.tab.state)
        await press(ENTER)
        return offered

    offered = on(machine, script)
    assert "› none\n" in offered and "a wrong name" not in offered
    assert machine.calls == [("change", "fallback_model", "")]
    assert machine.hardware.fallback_model is None


def test_an_empty_budget_per_boot_is_no_cap():
    machine = Machine(Hardware(max_budget_usd=2.0))

    async def script(press, panel):
        await press(to("max_budget_usd") + ENTER)
        foot = drawn(panel)[-1]
        await press(BACKSPACE + ENTER)                      # the value was selected: all of it goes
        return foot

    assert on(machine, script) == (" type the dollars, or nothing for no cap · Enter take · "
                                   "Esc leave it as it was")
    assert machine.calls == [("change", "max_budget_usd", "")]
    assert "Budget per boot    none" in text(machine)


def test_the_keys_of_an_open_row():
    machine = Machine(Hardware(fallback_model="abc"))
    typed = {"x": "x",                                      # typed over what was selected
             LEFT + "x": "abxc", HOME + "x": "xabc",        # an arrow keeps it
             HOME + RIGHT + DELETE: "ac", LEFT + LEFT + "\x0b": "a",        # Ctrl-K
             LEFT + CTRL_U + "\x05" + "x": "cx",            # Ctrl-U, Ctrl-E
             "\x01x" + END + "y": "xabcy",                  # Ctrl-A
             "\x1b[200~pasted\x1b[201~": "pasted",          # from the clipboard
             DELETE: "", "\x08": "",                        # the selection goes
             "é ü": "é ü"}

    async def script(press, panel):
        for keys in typed:                                  # each on a row that says "abc"
            await press(to("fallback_model") + ENTER + keys + ENTER)
            machine.hardware = Hardware(fallback_model="abc")
            panel.tab.shown()

    on(machine, script)
    assert [call[2] for call in machine.calls] == list(typed.values())


def test_save_says_saved_or_why_not():
    machine = Machine(unsaved={"effort"})

    async def script(press, panel):
        await press(to("Save") + ENTER)
        saved = text(machine, panel.tab.state), panel.tab.state.failed
        machine.save_says = "config.toml: can't change effort safely. Edit the file. Nothing saved."
        await press(ENTER)
        refused = text(machine, panel.tab.state), panel.tab.state.failed
        await press(UP)                                     # moving on, the answer goes
        return saved, refused, text(machine, panel.tab.state)

    saved, refused, moved = on(machine, script)
    assert saved[0].endswith("[ Close ]      saved") and not saved[1]
    assert refused[0].endswith("[ Close ]      " + machine.save_says) and refused[1]
    assert moved.endswith("[ Close ]      1 change not saved")
    assert machine.calls == [("save",), ("save",)]


def test_refill_budgets_asks_nothing_and_saves_nothing():
    machine = Machine(unsaved={"effort"})

    async def script(press, panel):
        await press(to("Refill budgets") + ENTER)
        said = text(machine, panel.tab.state)
        await press(RIGHT)                                  # → to Save, ← back
        on_save = drawn(panel)[-1]
        await press(LEFT)
        return said, on_save, panel.tab.state.at

    said, on_save, at = on(machine, script)
    assert said.endswith("[ Close ]      budgets refilled")
    assert machine.calls == [("refill",)] and machine.view().unsaved == {"effort"}
    assert on_save == " ↑ ↓ move · Enter press · Esc close"
    assert stops()[at] == "Refill budgets"


def test_the_close_button_closes_the_panel():
    machine = Machine()

    async def script(press, panel):
        await press(to("Close") + DOWN + DOWN)              # the last stop: further down is no stop
        at = stops()[panel.tab.state.at]
        await press(ENTER)
        await asyncio.wait_for(panel.wait_closed(), 1)
        return at

    assert on(machine, script) == "Close" and machine.calls == []


def test_tab_and_shift_tab_go_round():
    machine = Machine()

    async def script(press, panel):
        await press("\x1b[Z")                               # Shift+Tab from the first: the last
        back = stops()[panel.tab.state.at]
        await press("\t\t")
        return back, stops()[panel.tab.state.at], drawn(panel)

    back, forth, rows = on(machine, script)
    assert (back, forth) == ("Close", stops()[1])


def test_a_click_opens_a_row_presses_a_button_and_picks_from_a_list():
    machine = Machine()

    async def script(press, panel):
        row = next(y for y, line in enumerate(drawn(panel)) if "Event budget" in line)
        await press(click(row, 10))
        opened = panel.tab.state.open
        row = next(y for y, line in enumerate(drawn(panel)) if "Effort" in line)
        await press(click(row, 30))                         # another row: the first is left
        effort = panel.tab.state.open
        row = next(y for y, line in enumerate(drawn(panel)) if line.strip() == "xhigh")
        await press(click(row, 26))
        picked = panel.tab.state.open
        row, line = next((y, line) for y, line in enumerate(drawn(panel)) if "[ Save ]" in line)
        await press(click(row, line.index("Save")))
        return opened, effort, picked, text(machine, panel.tab.state)

    opened, effort, picked, after = on(machine, script)
    assert (opened, effort, picked) == ("event_budget_usd", "effort", None)
    assert machine.calls == [("change", "effort", "xhigh"), ("save",)]
    assert after.endswith("[ Close ]      saved")


def test_a_row_that_doesnt_change_takes_no_click():
    machine = Machine()

    async def script(press, panel):
        row = next(y for y, line in enumerate(drawn(panel)) if "Status bar" in line)
        await press(click(row, 10))
        return panel.tab.state.open, panel.tab.state.at

    assert on(machine, script) == (None, 0)


def test_on_ten_rows_the_row_you_are_on_and_the_buttons_are_drawn():
    machine = Machine()

    async def script(press, panel):
        top = drawn(panel)
        await press(to("fallback_model"))
        low = drawn(panel)
        await press(ENTER)
        return top, low, drawn(panel)

    top, low, open_row = on(machine, script, rows=10)
    for rows, row in ((top, "Budget per boot"), (low, "Fallback model"), (open_row, "› none")):
        assert any(row in line for line in rows[1:-2]), row
        assert "[ Refill budgets ]   [ Save ]   [ Close ]" in rows[-2]      # they stay
        assert rows[-1].startswith((" ↑ ↓ move", " type a name"))
    assert not any("Budget per boot" in line for line in low)               # it scrolled away


def test_on_a_tall_window_the_buttons_follow_the_rows():
    machine = Machine()

    async def script(press, panel):
        return drawn(panel)

    rows = on(machine, script, rows=40)
    last_row = next(y for y, line in enumerate(rows) if "OS sandbox" in line)
    assert "[ Refill budgets ]" in rows[last_row + 2] and rows[last_row + 1] == ""
    assert rows[-1] == " ↑ ↓ move · Enter change · Esc close"       # the foot is at the bottom


def test_what_is_shown_is_read_at_every_redraw():
    machine = Machine(spent_events=0.0)

    async def script(press, panel):
        machine.shown["spent_events"] = 0.07                # the AI works while the panel is open
        panel.invalidate()
        await asyncio.sleep(0.05)
        return drawn(panel)

    assert any("spent since you typed: ~$0.07" in line for line in on(machine, script))


def test_opened_again_the_tab_starts_fresh():
    machine = Machine()
    tab = machine.tab()
    panel = Panel([tab])
    panel.open()
    tab.state.at = stops().index("effort")
    tab._enter()                                            # its row is open
    tab.state.answer = "saved"
    assert tab.typing and tab.leave() and not tab.leave()   # Esc leaves it, once
    tab._enter()
    panel.close()
    panel.open()
    assert not tab.typing and tab.state.at == 0 and tab.state.answer == ""
    assert machine.calls == []
