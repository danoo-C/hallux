"""Block mode with a real prompt_toolkit app: keys come from a pipe, output goes nowhere."""
import asyncio

import pytest

pytest.importorskip("prompt_toolkit")

from prompt_toolkit.input import create_pipe_input  # noqa: E402
from prompt_toolkit.output import DummyOutput  # noqa: E402

from hallux.blockmode import BlockMode, key_sequence  # noqa: E402
from hallux.protocol import Field, Form  # noqa: E402

CTRL = {"K": "\x0b", "O": "\x0f", "U": "\x15", "X": "\x18"}
EDITOR = Field("editor", "text", top=2, height=10, text="line one\nline two\n", file="/h.txt")


def session(script):
    """Run `script(block_mode, type_keys)` against a block mode fed from a pipe."""
    async def main():
        with create_pipe_input() as pipe:
            block = BlockMode(input=pipe, output=DummyOutput())
            try:
                return await script(block, pipe.send_text)
            finally:
                await block.end()
    return asyncio.run(asyncio.wait_for(main(), 10))


def next_action(block):
    return asyncio.wait_for(block.next_action(), 5)


def test_key_names():
    assert key_sequence("C-o") == ("c-o",) and key_sequence("C-\\") == ("c-\\",)
    assert key_sequence("M-u") == ("escape", "u") and key_sequence("F10") == ("f10",)
    assert key_sequence("PageUp") == ("pageup",) and key_sequence("q") == ("q",)
    assert key_sequence("Hyper-x") is None


def test_typing_is_local_and_an_action_key_reports_the_fields():
    async def script(block, keys):
        await block.show("  GNU nano 7.2   h.txt\n", Form((EDITOR,), keys=("C-o", "C-x"), keymap="nano"))
        keys("hello " + CTRL["K"] + CTRL["O"])       # type, ^K cuts the line, ^O acts
        return await next_action(block)

    action = session(script)
    assert action.key == "C-o" and action.focus == "text"
    (state,) = action.fields
    assert state.text == "line two\n" and state.cursor == (1, 1)
    assert state.modified and state.changed           # the AI never saw the file's text


def test_kept_fields_and_a_line_field():
    async def script(block, keys):
        await block.show("title\n", Form((EDITOR,), keys=("C-o",), keymap="nano"))
        keys("x" + CTRL["O"])
        first = await next_action(block)
        prompt_form = Form((Field("editor", "text", top=2, height=10),                 # keeps
                            Field("line", "name", top=12, left=21, width=30, text="h.txt")),
                           focus="name")
        await block.show("title\n\n\nFile Name to Write: \n", prompt_form)
        keys("2\r")                                    # Enter in a line field always acts
        return first, await next_action(block), block.field_text("text")

    first, enter, text = session(script)
    assert first.fields[0].text == text == "xline one\nline two\n"
    assert enter.key == "Enter" and enter.focus == "name"
    kept, name = enter.fields
    assert not kept.changed                            # the AI saw it with ^O already
    assert name.text == "h.txt2" and name.changed      # the cursor starts after a line's text


def test_letters_type_in_editors_but_act_in_pagers():
    async def script(block, keys):
        await block.show("", Form((EDITOR,), keys=("q", "C-x")))
        keys("q" + CTRL["X"])
        in_editor = await next_action(block)
        pages = "\n".join(f"line {i}" for i in range(200))
        await block.show("", Form((Field("pager", "man", text=pages),), keys=("q",)))
        keys(" q")                                     # space scrolls, q acts
        return in_editor, await next_action(block)

    in_editor, in_pager = session(script)
    assert in_editor.key == "C-x" and in_editor.fields[0].text.startswith("qline one")
    assert in_pager.key == "q" and in_pager.fields[0].cursor[0] > 1


def test_ctrl_c_always_reaches_the_ai():
    async def script(block, keys):
        await block.show("", Form((EDITOR,), keys=()))
        keys("\x03")
        return await next_action(block)

    assert session(script).key == "C-c"


def test_clicks_outside_the_fields_go_to_the_ai():
    async def script(block, keys):
        await block.show("title bar\n", Form((EDITOR,), keys=("C-x",)))
        keys("\x1b[<0;5;1M\x1b[<0;5;1m")               # press and release at row 1, column 5
        return await next_action(block)

    action = session(script)
    assert (action.key, action.row, action.col) == ("click", 1, 5)


def test_saving_resets_modified():
    async def script(block, keys):
        await block.show("", Form((EDITOR,), keys=("C-o",)))
        keys("x")
        await asyncio.sleep(0.2)
        block.field_saved("text")
        keys(CTRL["O"])
        return await next_action(block)

    assert not session(script).fields[0].modified


def test_bad_styles_and_languages_are_ignored():
    field = Field("editor", "text", text="print(1)\n", style="fg:#nothex bogus", lang="klingon")

    async def script(block, keys):
        await block.show("", Form((field,), keys=("C-x",)))
        keys(CTRL["X"])
        return await next_action(block)

    assert session(script).key == "C-x"


def test_a_pager_can_be_a_menu():
    menu = Field("pager", "menu", text="Install\nConfigure\nQuit\n")

    async def script(block, keys):
        await block.show("", Form((menu,), keys=("Enter",)))
        keys("\x1b[B\r")                               # Down, Enter
        return await next_action(block)

    action = session(script)
    assert action.key == "Enter" and action.fields[0].cursor == (2, 1)    # "Configure"


def test_enter_never_acts_in_an_editor():
    async def script(block, keys):
        await block.show("", Form((EDITOR,), keys=("Enter", "C-x")))
        keys("\r" + CTRL["X"])
        return await next_action(block)

    action = session(script)
    assert action.key == "C-x" and action.fields[0].text == "\nline one\nline two\n"


def test_keys_typed_while_the_ai_thinks_go_into_the_next_screen():
    async def script(block, keys):
        await block.show("", Form((EDITOR,), keys=("C-o", "C-x")))
        keys(CTRL["O"] + "abc" + CTRL["X"])            # "abc^X" typed before the AI answers
        first = await next_action(block)
        await asyncio.sleep(0.2)                       # the AI is thinking
        await block.show("", Form((Field("editor", "text"),), keys=("C-x",)))
        return first, await next_action(block)

    first, second = session(script)
    assert first.key == "C-o" and first.fields[0].text == EDITOR.text
    assert second.key == "C-x" and second.fields[0].text == "abc" + EDITOR.text
