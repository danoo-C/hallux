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


def hooked_session(script, bar=None):
    """Like session(), with hallux's status bar and the hard exit and Ctrl-C hooks."""
    calls = []

    def ctrl_c(waiting):
        calls.append(("ctrl-c", waiting))
        return waiting                                 # while the AI thinks: it interrupts

    async def main():
        with create_pipe_input() as pipe:
            block = BlockMode(input=pipe, output=DummyOutput(), bar=bar,
                              power_cut=lambda: calls.append("cut"), ctrl_c=ctrl_c)
            try:
                return await script(block, pipe.send_text), calls
            finally:
                await block.end()
    return asyncio.run(asyncio.wait_for(main(), 10))


def test_the_hard_exit_works_even_while_the_ai_thinks():
    async def script(block, keys):
        await block.show("", Form((EDITOR,), keys=("C-x",)))
        keys("\x1b[3;6~")                              # Ctrl+Shift+Del
        await asyncio.sleep(0.2)
        keys(CTRL["X"])
        await next_action(block)                       # now the AI is thinking
        keys("\x1b[3;6~")
        await asyncio.sleep(0.2)

    _, calls = hooked_session(script)
    assert calls == ["cut", "cut"]


def test_ctrl_c_is_an_action_or_interrupts_the_ai():
    async def script(block, keys):
        await block.show("", Form((EDITOR,), keys=()))
        keys("\x03")
        first = await next_action(block)               # at rest: an action for the AI
        keys("\x03")                                   # while it thinks: an interrupt
        await asyncio.sleep(0.2)
        await block.show("", Form((Field("editor", "text"),), keys=()))
        keys("\x03")
        return first, await next_action(block)

    (first, third), calls = hooked_session(script)
    assert first.key == third.key == "C-c"
    assert calls == [("ctrl-c", False), ("ctrl-c", True), ("ctrl-c", False)]


def test_block_mode_has_the_status_bar_below_the_screen():
    from hallux.statusbar import StatusBar
    pager = Field("pager", "man", text="\n".join(f"line {i}" for i in range(100)))

    async def script(block, keys):
        await block.show("", Form((pager,), keys=("q",)))
        keys("Gq")                                     # jump to the end, then act
        return await next_action(block)

    action, _ = hooked_session(script, bar=StatusBar("claude-opus-5-5", "low"))
    assert action.key == "q" and action.fields[0].cursor[0] == 100    # G: the last line


# ---------------------------------------------------------------- fitting the screen

from hallux.blockmode import fit_screen  # noqa: E402


def test_a_screen_drawn_too_tall_still_shows_its_bottom_lines():
    """The live bug: 31 rows drawn for a 29-row screen hid nano's help lines."""
    lines = ["TITLE"] + [""] * 27 + ["[ New File ]", "^G Help  ^O Write Out", "^X Exit"]
    editor = Field("editor", "text", top=3, height=24).with_defaults()
    screen, tops = fit_screen(lines, [], 29, [editor])
    assert len(screen) == 29 and screen[0] == "TITLE"
    assert screen[-3:] == ["[ New File ]", "^G Help  ^O Write Out", "^X Exit"]
    assert tops == {"text": 3}                         # rows 27-28 went, nothing above moved


def test_fields_move_up_with_their_text():
    lines = ["TITLE", "", ""] + ["body"] * 3 + ["", "", "Save modified buffer? "]
    answer = Field("line", "yn", top=9, left=23).with_defaults()      # beside the question
    screen, tops = fit_screen(lines, [], 7, [answer])
    assert screen[tops["yn"] - 1] == "Save modified buffer? "


def test_the_footer_is_pinned_to_the_bottom():
    footer = ["[ New File ]", "^G Help", "^X Exit"]
    editor = Field("editor", "text", top=3, height=0).with_defaults()
    answer = Field("line", "yn", top=-3, left=23).with_defaults()
    screen, tops = fit_screen(["TITLE"], footer, 10, [editor, answer])
    assert screen == ["TITLE"] + [""] * 6 + footer
    assert tops == {"text": 3, "yn": 8}                # -3: third row from the bottom


def test_colored_rows_are_not_blank_and_the_footer_always_wins():
    bar = "\x1b[48;5;205m" + " " * 20 + "\x1b[0m"      # a colored bar made of spaces
    screen, _ = fit_screen(["a", bar, "b", "c"], ["KEYS"], 3, [])
    assert screen == ["a", bar, "KEYS"]                # cut short; the keys survive


def test_block_mode_lays_out_a_footer():
    footer_form = Form((Field("editor", "text", top=2, height=0, text="hi\n"),), keys=("C-x",),
                       footer="[ New File ]\n^X Exit\n")

    async def script(block, keys):
        await block.show("TITLE\n", footer_form)
        keys(CTRL["X"])
        return await next_action(block)

    assert session(script).key == "C-x"
