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
