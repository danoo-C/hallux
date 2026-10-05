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
from hallux.panel_tabs.config import BUTTONS, LABELS, ConfigTab, State, draw, stops  # noqa: E402

UP, DOWN, LEFT, RIGHT, HOME, END = "\x1b[A", "\x1b[B", "\x1b[D", "\x1b[C", "\x1b[H", "\x1b[F"
BACKSPACE, DELETE, ENTER, CTRL_U = "\x7f", "\x1b[3~", "\r", "\x15"


class Machine:
    """What stands in for the machine: a view, and the three things the tab can ask for."""

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
        return ConfigTab(self.view, self.change, self.save, self.refill)


def text(machine, state=None):
    """The whole tab as text, as draw() gives it."""
    result = draw(machine.view(), state or State())
    return "\n".join("".join(part[1] for part in line) for line in (*result.rows, result.buttons))


def to(stop, start=None):
    """The keys that move to this row or button: from the first row, or from `start`."""
    steps = stops().index(stop) - (stops().index(start) if start else 0)
    return (DOWN if steps > 0 else UP) * abs(steps)


def on(machine, script, extra=(), **size):
    """Show a panel with the Config tab of this machine and run the script on it."""
    panel = Panel([*extra, machine.tab()])
    return session(panel, lambda press: script(press, panel), **size)


def test_every_setting_has_a_row():
    assert set(LABELS) == {f.name for f in fields(Hardware)}
    assert stops() == [name for name in LABELS if config.WHEN[name] in ("now", "reboot")
                       and config.WHEN[name] == "now"] + [
                           name for name in LABELS if config.WHEN[name] == "reboot"] + list(BUTTONS)
    assert len(stops()) == 9                                # six rows that change, three buttons


def test_the_text_of_the_tab():
    machine = Machine(Hardware(max_budget_usd=2.0, effort="high", addons=("music", "window")),
                      running=Hardware(max_budget_usd=2.0), spent_boot=1.42, spent_ticks=0.25,
                      paused=frozenset({"tick_budget_usd"}), unsaved={"effort", "max_budget_usd"})
    assert text(machine) == """
  world/.hallux/config.toml

  Changes now
    Budget per boot    $2.00               spent in this boot: $1.42
    Tick budget        $0.25               spent by this program: $0.25 (paused)
    Event budget       $0.25               spent since you typed: $0.00

  Changes at the machine's next reboot
    Model              claude-opus-5-5     
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
    assert shown["Budget per boot"] == "none                spent in this boot: $0.00 (paused)"
    assert shown["Tick budget"] == "$0.125"                 # no program on screen: no note
    assert shown["Event budget"] == "$0.00               spent since you typed: $0.10 (paused)"
    assert shown["Fallback model"] == "claude-haiku-4-5"
    assert (shown["Status bar"], shown["Addons"], shown["Transcripts"], shown["OS sandbox"]) == (
        "off", "none", "on", "on")
    assert text(machine).endswith("[ Close ]      1 change not saved")
    assert "all that loaded" in text(Machine()) and "not saved" not in text(Machine())


def test_the_budget_per_boot_has_both_numbers_after_a_refill():
    machine = Machine(Hardware(max_budget_usd=2.0), spent_boot=1.52)
    assert "spent in this boot: $1.52" in text(machine)
    machine.shown["spent_since_refill"] = 0.10
    assert "spent since the refill: $0.10 · this boot: $1.52" in text(machine)
    assert "spent in this boot" not in text(machine)


def test_a_setting_is_drawn_in_the_group_of_its_when(monkeypatch):
    before = text(Machine()).split("\n\n")
    assert "Changes now" in before[1] and "Effort" in before[2] and "Effort" not in before[1]
    monkeypatch.setitem(config.WHEN, "effort", "now")
    after = text(Machine()).split("\n\n")
    assert "Effort" in after[1] and "Effort" not in after[2]
    assert stops().index("effort") < stops().index("model")     # and the arrows follow


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
    assert "a wrong name ends Hallux at the next boot" in offered
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

    assert any("spent since you typed: $0.07" in line for line in on(machine, script))


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
