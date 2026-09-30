import asyncio

import pytest

pytest.importorskip("prompt_toolkit")

from prompt_toolkit.formatted_text import ANSI, to_formatted_text  # noqa: E402
from prompt_toolkit.input import create_pipe_input  # noqa: E402
from prompt_toolkit.output import DummyOutput  # noqa: E402

from hallux.machine import Key  # noqa: E402
from hallux.terminal import Terminal, zero_width  # noqa: E402


def test_zero_width_marks_everything_but_colors():
    prompt = "\x1b]0;user@hallux: ~\x07\x1b[1;35mcow\x1b[0m\x1b[K> "
    assert zero_width(prompt) == "\x01\x1b]0;user@hallux: ~\x07\x02\x1b[1;35mcow\x1b[0m\x01\x1b[K\x02> "
    visible = "".join(text for style, text, *_ in to_formatted_text(ANSI(zero_width(prompt)))
                      if "ZeroWidthEscape" not in style)
    assert visible == "cow> "


def typed(keys, default=""):
    """What read_line returns when these keys are typed."""
    async def read():
        with create_pipe_input() as pipe:
            terminal = Terminal(input=pipe, output=DummyOutput())
            pipe.send_text(keys)
            return await terminal.read_line("\x1b[35m$\x1b[0m ", default)
    return asyncio.run(read())


def test_lines():
    assert typed("ls -la\r") == "ls -la"
    assert typed("\r", default="restored") == "restored"


def test_screen_keys_go_to_the_ai():
    assert typed("ls -l\x0c") == Key("C-l", "ls -l")                     # Ctrl-L


def test_ctrl_c_and_ctrl_d():
    with pytest.raises(KeyboardInterrupt):
        typed("half a line\x03")
    with pytest.raises(EOFError):
        typed("\x04")


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

    async def main():
        with create_pipe_input() as pipe:
            terminal = Terminal(input=pipe, output=DummyOutput())
            machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)
            pipe.send_text("nano notes.txt\r" "x\x18" "\x04")
            await asyncio.wait_for(machine.run(), 10)

    asyncio.run(main())
    boot, nano, ctrl_x, eof = model.sessions[0]
    assert nano.endswith(">nano notes.txt</input>")
    assert ctrl_x.startswith('<action key="C-x"') and ">xhi\n</field>" in ctrl_x
    assert eof.startswith("<eof ")
