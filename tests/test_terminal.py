"""The real terminal with prompt_toolkit: keys come from a pipe, output goes nowhere."""
import asyncio

import pytest

pytest.importorskip("prompt_toolkit")

from prompt_toolkit.formatted_text import ANSI, to_formatted_text  # noqa: E402
from prompt_toolkit.input import create_pipe_input  # noqa: E402
from prompt_toolkit.output import DummyOutput  # noqa: E402

from hallux.machine import Key  # noqa: E402
from hallux.statusbar import StatusBar  # noqa: E402
from hallux.terminal import Terminal, zero_width  # noqa: E402

CTRL_SHIFT_DEL = "\x1b[3;6~"


def test_zero_width_marks_everything_but_colors():
    prompt = "\x1b]0;user@hallux: ~\x07\x1b[1;35mcow\x1b[0m\x1b[K> "
    assert zero_width(prompt) == "\x01\x1b]0;user@hallux: ~\x07\x02\x1b[1;35mcow\x1b[0m\x01\x1b[K\x02> "
    visible = "".join(text for style, text, *_ in to_formatted_text(ANSI(zero_width(prompt)))
                      if "ZeroWidthEscape" not in style)
    assert visible == "cow> "


def with_terminal(script, bar=None, cuts=None):
    """Run `script(terminal, type_keys)` against a terminal fed from a pipe.

    The real hard exit never returns (os._exit); here it's only recorded in `cuts`.
    """
    cuts = [] if cuts is None else cuts

    async def main():
        with create_pipe_input() as pipe:
            terminal = Terminal(bar, input=pipe, output=DummyOutput(),
                                power_cut=lambda: cuts.append("cut"))
            return await script(terminal, pipe.send_text)
    return asyncio.run(asyncio.wait_for(main(), 10))


def typed(keys, default="", cuts=None):
    """What read_line returns when these keys are typed."""
    async def script(terminal, type_keys):
        type_keys(keys)
        return await terminal.read_line("\x1b[35m$\x1b[0m ", default)
    return with_terminal(script, cuts=cuts)


def test_lines():
    assert typed("ls -la\r") == "ls -la"
    assert typed("\r", default="restored") == "restored"


def test_keys_that_end_the_line_go_to_the_ai():
    assert typed("rm -rf /tmp/x\x03") == Key("C-c", "rm -rf /tmp/x", 13, keep_line=False)
    assert typed("sleep 9\x1a") == Key("C-z", "sleep 9", 7, keep_line=False)
    assert typed("\x04") == Key("C-d", "", 0, keep_line=False)       # Ctrl-D on an empty line


def test_keys_that_work_in_place_go_to_the_ai():
    assert typed("cat /et\t") == Key("Tab", "cat /et", 7)
    assert typed("ls -l\x0c") == Key("C-l", "ls -l", 5)
    assert typed("\x12") == Key("C-r", "", 0)
    assert typed("vim \x1b.") == Key("M-.", "vim ", 4)
    assert typed("\x1bOP") == Key("F1", "", 0)


def test_line_editing_stays_local():
    assert typed("ab\x1b[D\x04\r") == "a"                 # Ctrl-D with text deletes a character
    assert typed("hello world\x17\x17there\r") == "there"  # Ctrl-W deletes words
    assert typed("x\x01y\x05z\r") == "yxz"                # Ctrl-A and Ctrl-E move


def test_ctrl_shift_del_pulls_the_plug():
    cuts = []
    typed("half a line" + CTRL_SHIFT_DEL + "\r", cuts=cuts)
    assert cuts == ["cut"]


def test_three_ctrl_c_within_a_second_pull_the_plug():
    async def script(terminal, type_keys):
        for _ in range(3):
            type_keys("\x03")
            await terminal.read_line("$ ")
    cuts = []
    with_terminal(script, cuts=cuts)
    assert cuts == ["cut"]


def test_ctrl_c_presses_too_far_apart_are_just_keys():
    async def script(terminal, type_keys):
        keys = []
        for pause in (0, 0, 1.1):                      # the third press comes too late
            await asyncio.sleep(pause)
            type_keys("\x03")
            keys.append(await terminal.read_line("$ "))
        return keys
    cuts = []
    assert all(key.name == "C-c" for key in with_terminal(script, cuts=cuts))
    assert cuts == []


def test_keys_typed_while_the_ai_works_wait_for_the_next_prompt():
    async def script(terminal, type_keys):
        interrupts = []
        async with terminal.busy(lambda: interrupts.append("stop")):
            type_keys("ls -l")                         # type-ahead: not echoed, not lost
            await asyncio.sleep(0.2)
            type_keys("\x03")                          # Ctrl-C stops the AI
            await asyncio.sleep(0.2)
        type_keys("a\r")
        return interrupts, await terminal.read_line("$ ")
    assert with_terminal(script) == (["stop"], "ls -la")


def test_ctrl_shift_del_works_while_the_ai_works():
    async def script(terminal, type_keys):
        async with terminal.busy(lambda: None):
            type_keys(CTRL_SHIFT_DEL)
            await asyncio.sleep(0.2)
    cuts = []
    with_terminal(script, cuts=cuts)
    assert cuts == ["cut"]


def test_the_ai_sees_a_screen_one_row_shorter_with_the_bar():
    async def script(terminal, type_keys):
        return terminal.size()
    assert with_terminal(script) == (80, 40)                                    # DummyOutput
    assert with_terminal(script, bar=StatusBar("claude-opus-5-5", "low")) == (80, 39)


def test_the_prompt_and_block_mode_share_the_keyboard(tmp_path):
    """Everything typed at once: a command line, then editing in nano, then Ctrl-D."""
    from test_machine import FakeModel, screen

    from hallux.config import Hardware
    from hallux.machine import Machine

    (tmp_path / "notes.txt").write_text("hi\n")
    model = FakeModel(
        screen(""),
        '<screen>\n  GNU nano 7.2   notes.txt\n</screen><prompt></prompt>'
        '<form keys="C-x" keymap="nano"><editor id="text" top="2" file="notes.txt"/></form>',
        screen("", prompt="$ "),
        screen("logout\n", prompt="", tail="<halt/>"))

    async def script(terminal, type_keys):
        machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)
        type_keys("nano notes.txt\r" "x\x18" "\x04")
        await machine.run()

    with_terminal(script, bar=StatusBar("claude-opus-5-5", "low"))
    boot, nano, ctrl_x, ctrl_d = model.sessions[0]
    assert nano.endswith(">nano notes.txt</input>")
    assert ctrl_x.startswith('<action key="C-x"') and ">xhi\n</field>" in ctrl_x
    assert ctrl_d.startswith('<key name="C-d" ')


def test_the_prompt_never_erases_the_status_bar():
    """prompt_toolkit erases below the cursor before drawing; the bar comes back in the same write."""
    import io

    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.output.vt100 import Vt100_Output

    screen = io.StringIO()
    whole = Vt100_Output(screen, lambda: Size(rows=30, columns=100), term="xterm-256color")

    async def script(terminal, type_keys):
        terminal.pinned = Size(rows=30, columns=100)   # as start() does on a real terminal
        type_keys("ls\r")
        return await terminal.read_line("$ ")

    async def main():
        with create_pipe_input() as pipe:
            terminal = Terminal(StatusBar("claude-opus-5-5", "low"), input=pipe, output=whole)
            return await script(terminal, pipe.send_text)

    assert asyncio.run(asyncio.wait_for(main(), 10)) == "ls"
    written = screen.getvalue()
    erases = [m.start() for m in __import__("re").finditer(r"\x1b\[J", written)]
    assert erases, "prompt_toolkit erased below the cursor"
    for at in erases:                                  # each erase is followed by the bar
        assert written[at:].startswith("\x1b[J\x1b7\x1b[1;29r\x1b[30;1H")
