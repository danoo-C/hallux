"""Hallux's own panel, the host: a real prompt_toolkit app, keys from a pipe, stand-in tabs."""
import asyncio

import pytest

pytest.importorskip("prompt_toolkit")

from prompt_toolkit.data_structures import Size  # noqa: E402
from prompt_toolkit.filters import Condition  # noqa: E402
from prompt_toolkit.input import create_pipe_input  # noqa: E402
from prompt_toolkit.key_binding import KeyBindings  # noqa: E402
from prompt_toolkit.keys import Keys  # noqa: E402
from prompt_toolkit.layout import Window  # noqa: E402
from prompt_toolkit.layout.controls import FormattedTextControl  # noqa: E402
from prompt_toolkit.output import DummyOutput  # noqa: E402

from hallux import panel as panel_module  # noqa: E402
from hallux.blockmode import OPEN_KEY  # noqa: E402
from hallux.panel import Panel, Tab  # noqa: E402
from hallux.statusbar import DIM, StatusBar  # noqa: E402

ESC, CTRL_F12, CTRL_SHIFT_DEL, UP = "\x1b", "\x1b[24;5~", "\x1b[3;6~", "\x1b[A"


class Screen(DummyOutput):
    """An output that goes nowhere, of the size a test wants."""

    def __init__(self, rows=24, columns=80):
        self.size = Size(rows, columns)

    def get_size(self):
        return self.size


def drawn(panel):
    """What the panel's app drew last, row by row."""
    screen, size = panel.app.renderer._last_screen, panel.app.output.get_size()
    return ["".join(screen.data_buffer[y][x].char for x in range(size.columns)).rstrip()
            for y in range(size.rows)]


def style_at(panel, row, column):
    return panel.app.renderer._last_screen.data_buffer[row][column].style


def tab_row(panel):
    """The tabs as the first row of the screen shows them, without the name in front."""
    return drawn(panel)[0].removeprefix(" Hallux").strip()


def click(row, column):
    """The mouse pressed and let go on this row and column of the screen, counted from 0."""
    return f"\x1b[<0;{column + 1};{row + 1}M\x1b[<0;{column + 1};{row + 1}m"


def session(panel, script, rows=24, columns=80):
    """Show the panel on a pipe and run `script(press)`. `press` types keys and waits until
    the panel has taken them. Returns what the script returns; the panel is closed after."""
    async def main():
        with create_pipe_input() as pipe:
            showing = asyncio.ensure_future(panel.run(pipe, Screen(rows, columns)))
            await asyncio.sleep(0.1)

            async def press(keys, wait=0.06):
                pipe.send_text(keys)
                await asyncio.sleep(wait)

            try:
                return await script(press)
            finally:
                panel.close()
                await showing
    return asyncio.run(asyncio.wait_for(main(), 15))


class StandIn(Tab):
    """A tab that only notes what the host asks of it."""

    def __init__(self, title, reason=None, first=False):
        self.title, self.reason, self.first = title, reason, first
        self.container = Window(FormattedTextControl(f"this is {title}", focusable=True))
        self.typing = False                  # a row is open for typing
        self.open_rows = 0                   # what Esc has to leave before it closes the panel
        self.shows, self.got = 0, []
        self.bindings = KeyBindings()
        self.bindings.add("x")(lambda event: self.got.append("x"))
        self.bindings.add("escape", "u")(lambda event: self.got.append("M-u"))   # as editing keys
        self.bindings.add(Keys.Any, filter=Condition(lambda: self.typing))(
            lambda event: self.got.append(event.data))

    def hint(self):
        return f"x marks {self.title}"

    def disabled(self):
        return self.reason

    def wants_first(self):
        return self.first

    def leave(self):
        if not self.open_rows:
            return False
        self.open_rows -= 1
        return True

    def shown(self):
        self.shows += 1


def three(**details):
    return [StandIn("Agents"), StandIn("Details", **details), StandIn("Config")]


def test_the_key_that_opens_the_panel_is_ctrl_f12():
    assert OPEN_KEY == "c-f12" == Keys.ControlF12.value


def test_the_tab_row_has_every_title_and_brackets_on_the_shown_one():
    panel = Panel(three())

    async def script(press):
        return drawn(panel)

    rows = session(panel, script)
    assert rows[0].startswith(" Hallux   ") and len(rows[0]) == 79      # one column is left free
    assert rows[0].endswith("   Agents     Details   [ Config ]")
    assert rows[1] == "this is Config" and rows[-1] == " x marks Config · a d c tabs · Esc close"


def test_one_tab_has_a_tab_row_too():
    panel = Panel([StandIn("Config")])

    async def script(press):
        return drawn(panel)

    rows = session(panel, script)
    assert rows[0].split() == ["Hallux", "[", "Config", "]"]
    assert rows[-1] == " x marks Config · Esc close"            # no letters: there is one tab


def test_the_first_letter_of_a_title_is_its_key_and_is_underlined():
    panel = Panel(three())

    async def script(press):
        at = drawn(panel)[0].index("Agents")
        return [style_at(panel, 0, at + i) for i in range(2)]

    first, second = session(panel, script)
    assert "underline" in first and "underline" not in second


def test_a_letter_shows_its_tab_and_so_does_a_click_on_its_title():
    panel = Panel(three())
    agents, details, config = panel.tabs

    async def script(press):
        await press("a")
        by_letter = panel.tab, tab_row(panel), drawn(panel)[1]
        await press(click(0, drawn(panel)[0].index("Details") + 2))
        by_click = panel.tab, tab_row(panel), drawn(panel)[1]
        await press("c")
        return by_letter, by_click, panel.tab

    by_letter, by_click, last = session(panel, script)
    assert by_letter == (agents, "[ Agents ]   Details     Config", "this is Agents")
    assert by_click == (details, "Agents   [ Details ]   Config", "this is Details")
    assert last is config and (agents.shows, details.shows, config.shows) == (1, 1, 2)


def test_while_a_tab_is_typing_the_letters_are_its_own():
    panel = Panel(three())
    config = panel.tabs[2]

    async def script(press):
        config.typing = True
        await press("ad")
        typing = panel.tab, drawn(panel)[-1]
        await press(click(0, drawn(panel)[0].index("Agents")))         # a click always works
        return typing, panel.tab

    typing, after_click = session(panel, script)
    assert typing == (config, " x marks Config")            # no letters and no Esc in the foot
    assert config.got == ["a", "d"] and after_click is panel.tabs[0]


def test_a_disabled_tab_is_grey_and_says_why_it_cant_be_chosen():
    panel = Panel(three(reason="no attached addon has an agent"))
    config = panel.tabs[2]

    async def script(press):
        at = drawn(panel)[0].index("Details")
        grey = style_at(panel, 0, at + 3)
        await press("d")
        by_letter = panel.tab, drawn(panel)[-1]
        await press("x")                                    # the reason stays for a moment
        await press(click(0, at))
        return grey, by_letter, (panel.tab, drawn(panel)[-1])

    grey, by_letter, by_click = session(panel, script)
    assert f"fg:{DIM}" in grey
    assert by_letter == by_click == (config, " no attached addon has an agent")
    assert panel.tabs[1].shows == 0 and config.got == ["x"]


def test_the_reason_in_the_foot_goes_by_itself(monkeypatch):
    monkeypatch.setattr(panel_module, "MESSAGE_SECONDS", 0.2)
    panel = Panel(three(reason="not now"))

    async def script(press):
        await press("d")
        said = drawn(panel)[-1]
        await asyncio.sleep(0.4)
        return said, drawn(panel)[-1]

    assert session(panel, script) == (" not now", " x marks Config · a d c tabs · Esc close")


def test_a_tabs_keys_act_only_while_it_is_shown():
    panel = Panel(three())
    agents, _, config = panel.tabs

    async def script(press):
        await press("x")
        await press("a")
        await press("xx")

    session(panel, script)
    assert (config.got, agents.got) == (["x"], ["x", "x"])


def test_the_panel_opens_on_the_tab_that_wants_to_be_first_or_on_the_last():
    panel = Panel(three())
    assert panel.tab is panel.tabs[2] and not panel.is_open
    panel.tabs[0].first = panel.tabs[1].first = True
    panel.open()
    assert panel.tab is panel.tabs[0] and panel.is_open     # the first that asks
    panel.close()
    panel.tabs[0].first = panel.tabs[1].first = False
    panel.open()
    assert panel.tab is panel.tabs[2]                       # nobody asks: the last in the row


def test_opening_starts_fresh():
    panel = Panel(three(reason="not now"))
    panel.open()
    panel.show("Agents")
    panel.show("Details")
    assert panel.tab is panel.tabs[0] and panel.message == "not now"
    panel.close()
    panel.open()
    assert panel.tab is panel.tabs[2] and panel.message == ""


def test_two_tabs_with_the_same_first_letter_are_refused():
    with pytest.raises(ValueError, match="same letter: Config and Costs"):
        Panel([StandIn("Agents"), StandIn("Config"), StandIn("Costs")])


def test_esc_asks_the_tab_first():
    panel = Panel(three())
    config = panel.tabs[2]

    async def script(press):
        config.open_rows = 2
        await press(ESC, wait=0.2)
        await press(ESC, wait=0.2)
        still_open = panel.is_open, config.open_rows
        await press(ESC)
        await asyncio.wait_for(panel.wait_closed(), 1)
        return still_open

    assert session(panel, script) == (True, 0)              # twice the tab had something to leave
    assert not panel.is_open


def test_esc_and_ctrl_f12_close_and_the_wait_returns():
    for key in (ESC, CTRL_F12):
        panel = Panel(three())

        async def script(press):
            waiting = asyncio.ensure_future(panel.wait_closed())
            await asyncio.sleep(0.05)
            was_waiting = not waiting.done() and panel.is_open
            await press("a" + key, wait=0.2)                # from any tab
            await asyncio.wait_for(waiting, 1)
            return was_waiting

        assert session(panel, script) and not panel.is_open and panel.app is None

    panel = Panel(three())
    panel.tabs[2].typing, panel.tabs[2].open_rows = True, 1

    async def script(press):
        await press(CTRL_F12)                               # also out of a row that is open
        await asyncio.wait_for(panel.wait_closed(), 1)

    session(panel, script)
    assert not panel.is_open and panel.tabs[2].open_rows == 1


def test_closing_twice_closes_once():
    panel = Panel(three())

    async def script(press):
        await press(ESC + CTRL_F12 + ESC, wait=0.3)         # one right after the other
        await asyncio.wait_for(panel.wait_closed(), 1)

    session(panel, script)                                  # and no error from the app
    panel.close()
    assert not panel.is_open


def test_esc_is_quick_and_an_arrow_key_is_no_esc():
    """Esc is the first byte of an arrow key, and the first key of Alt+U, which the shown tab
    binds as editing keys do. It closes within a fifth of a second all the same."""
    panel = Panel(three())

    async def script(press):
        await press(UP, wait=0.3)
        after_arrow = panel.is_open
        await press(ESC, wait=0)
        await asyncio.wait_for(panel.wait_closed(), 0.2)
        return after_arrow

    assert session(panel, script) is True


def test_a_tab_can_show_another_tab_and_close_the_panel():
    panel = Panel(three())
    agents, details, _ = panel.tabs

    async def script(press):
        agents.host.show("Details")
        await asyncio.sleep(0.05)
        shown = panel.tab, drawn(panel)[1]
        details.host.close()
        await asyncio.wait_for(panel.wait_closed(), 1)
        return shown

    assert session(panel, script) == (details, "this is Details")
    assert agents.host is panel and panel.pick is None      # the one thing the tabs share
    with pytest.raises(ValueError, match="no tab 'Costs'"):
        panel.show("Costs")


def test_the_hard_exit_and_ctrl_c():
    cuts, presses = [], []
    panel = Panel(three(), power_cut=lambda: cuts.append("cut"),
                  ctrl_c=lambda: presses.append("C-c"))

    async def script(press):
        await press("\x03\x03")
        await press(CTRL_SHIFT_DEL)
        return panel.is_open

    assert session(panel, script) is True                   # Ctrl-C counts, and nothing else
    assert (cuts, presses) == (["cut"], ["C-c", "C-c"])


def test_the_foot_has_the_hint_of_the_shown_tab():
    panel = Panel(three())

    async def script(press):
        first = drawn(panel)[-1]
        await press("a")
        return first, drawn(panel)[-1]

    assert session(panel, script) == (" x marks Config · a d c tabs · Esc close",
                                      " x marks Agents · a d c tabs · Esc close")


def test_run_puts_the_bar_on_the_last_row_and_the_container_has_none():
    bar = StatusBar("claude-opus-5-5", "low")
    panel = Panel(three(), bar=bar)

    async def script(press):
        bar.update(note="events paused: budget used")
        panel.invalidate()                                  # the bar changed: draw again
        await asyncio.sleep(0.05)
        return drawn(panel)

    rows = session(panel, script, rows=10)
    assert rows[-2] == " x marks Config · a d c tabs · Esc close"
    assert rows[-1].startswith(" • events paused: budget used") and "opus 5.5" in rows[-1]
    assert len(panel.container.children) == 3               # the tab row, the tab, the foot
