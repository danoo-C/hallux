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


@pytest.mark.parametrize("keymap", ["emacs", "nano", "vi"])
def test_ctrl_z_always_reaches_the_ai_with_the_fields(keymap):
    """Job control: the AI suspends the program, also one whose form doesn't list the key."""
    async def script(block, keys):
        await block.show("", Form((EDITOR,), keys=("C-x",), keymap=keymap))
        keys("typed \x1a")
        return await next_action(block)

    action = session(script)
    assert action.key == "C-z" and action.focus == "text"
    (state,) = action.fields
    assert state.text == "typed line one\nline two\n" and state.changed


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


# ---------------------------------------------------------------- raw mode

TOP = Form((), raw=True, tick=0)


def test_raw_mode_sends_every_key_and_batches_what_was_typed_meanwhile():
    async def script(block, keys):
        await block.show("top\n", TOP)
        keys("j")
        first = await next_action(block)
        keys("jk\x1b[A\r")                             # typed while the AI is answering
        await asyncio.sleep(0.3)
        await block.show("top\n", TOP)                 # ... goes out with the next screen
        return first, await next_action(block)

    first, batch = session(script)
    assert (first.key, first.events) == ("keys", ("<text>j</text>",))
    assert batch.events == ("<text>jk</text>", "<key>Up</key>", "<key>Enter</key>")


def test_raw_mode_key_names():
    expected = {"\x1b": "Escape", "\x1bOQ": "F2", "\x1b[5~": "PageUp", "\x7f": "Backspace",
                "\t": "Tab", "\x0c": "C-l", "\x1b[1;5A": "C-Up", "\x1b[3~": "Delete"}

    async def script(block, keys):
        names = {}
        for sequence in expected:
            await block.show("x\n", TOP)
            keys(sequence)
            names[sequence] = (await next_action(block)).events
        return names

    assert session(script) == {seq: (f"<key>{name}</key>",) for seq, name in expected.items()}


def test_raw_mode_ticks_when_idle():
    async def script(block, keys):
        await block.show("top - 01:02:03\n", Form((), raw=True, tick=1.0))
        started = asyncio.get_running_loop().time()
        action = await next_action(block)
        return action.key, asyncio.get_running_loop().time() - started

    key, waited = session(script)
    assert key == "tick" and 0.9 < waited < 2


def test_raw_mode_clicks_and_the_wheel_anywhere_on_screen():
    async def script(block, keys):
        events = []
        for sgr in ("\x1b[<0;70;30M\x1b[<0;70;30m", "\x1b[<65;3;4M"):
            await block.show("one short line\n", TOP)
            keys(sgr)
            events += (await next_action(block)).events
        return events

    assert session(script) == ['<mouse button="left" row="30" col="70"/>',
                               '<mouse button="wheel-down" row="4" col="3"/>']


def test_raw_mode_ctrl_c_is_a_key_and_still_counts_for_the_hard_exit():
    async def script(block, keys):
        await block.show("top\n", TOP)
        keys("\x03")
        return await next_action(block)

    action, calls = hooked_session(script)
    assert action.events == ("<key>C-c</key>",) and calls == [("ctrl-c", False)]


# ---------------------------------------------------------------- partial redraws

NANO_SCREEN = "  GNU nano 7.2   notes.txt\n"
NANO_FOOTER = "[ New File ]\n^G Help  ^O Write Out\n^X Exit  ^R Read File\n"


def test_a_patch_changes_only_its_rows():
    form = Form((Field("editor", "text", top=3, height=0, text="hi\n"),
                 Field("line", "yn", top=-3, left=23, text="")), keys=("C-x",), footer=NANO_FOOTER)

    async def script(block, keys):
        await block.show(NANO_SCREEN, form)
        before = list(block.composed), dict(block.field_tops)
        kept = Form((Field("editor", "text", top=3, height=0),               # as resolve() gives
                     Field("line", "yn", top=-3, left=23)), keys=("C-x",))
        await block.show("", kept, patch=((-3, ("Save modified buffer?",)), (2, ("row two",))))
        return before, list(block.composed), dict(block.field_tops)

    (before, tops_before), after, tops_after = session(script)
    rows = len(before)                                  # the DummyOutput screen, minus nothing
    assert len(after) == rows and after[0] == before[0] == "  GNU nano 7.2   notes.txt"
    assert after[1] == "row two" and after[-3] == "Save modified buffer?"
    assert after[-2:] == before[-2:] == ["^G Help  ^O Write Out", "^X Exit  ^R Read File"]
    assert tops_after == tops_before                    # the fields didn't move


def test_a_patch_can_bring_a_new_footer_and_survives_a_resize():
    from hallux.blockmode import BlockMode as Block
    block = Block()
    block.composed, block.footer_rows = ["title", "", "", "", "old status", "old keys"], 2
    body = block._patched(6, ["new status", "new keys"], ((1, ("new title",)),))
    assert body == ["new title", "", "", "", "new status", "new keys"]
    block.composed, block.footer_rows = body, 2
    bigger = block._patched(8, None, ((-1, ("^X Exit",)),))
    assert bigger == ["new title", "", "", "", "", "", "new status", "^X Exit"]   # footer stays down


def test_a_patch_before_any_screen_starts_from_blank_rows():
    async def script(block, keys):
        await block.show("", Form((), raw=True), patch=((1, ("score: 0",)),))
        return list(block.composed)

    composed = session(script)
    assert composed[0] == "score: 0" and set(composed[1:]) == {""}


def test_an_action_that_isnt_sent_leaves_the_form_to_type_in():
    async def script(block, keys):
        await block.show("", Form((EDITOR,), keys=("C-o", "C-x")))
        keys("a" + CTRL["O"] + "b")                    # "b" is typed while the action is away
        first = await next_action(block)
        await asyncio.sleep(0.2)
        block.keep_form()                              # the AI never got it: on with the form
        keys("c" + CTRL["X"])
        return first, await next_action(block)

    first, second = session(script)
    assert first.key == "C-o" and first.fields[0].text == "a" + EDITOR.text
    assert second.key == "C-x" and second.fields[0].text == "abc" + EDITOR.text


def test_an_action_that_isnt_sent_reports_its_fields_again():
    async def script(block, keys):
        await block.show("", Form((Field("editor", "text", text="seen\n"),), keys=("C-o", "C-x")))
        keys("a" + CTRL["O"])
        first = await next_action(block)
        block.keep_form()
        keys(CTRL["O"])                                # the same text, and the AI hasn't seen it
        second = await next_action(block)
        await block.show("", Form((Field("editor", "text"),), keys=("C-o", "C-x")))   # now it has
        keys(CTRL["X"])
        return first, second, await next_action(block)

    first, second, third = session(script)
    assert first.fields[0].text == second.fields[0].text == third.fields[0].text == "aseen\n"
    assert first.fields[0].changed and second.fields[0].changed       # in full, once more
    assert not third.fields[0].changed                                # an answer came: it is seen


def test_keep_form_can_stop_a_programs_ticks():
    async def script(block, keys):
        await block.show("top - 01:02:03\n", Form((), raw=True, tick=0.2))
        tick = await next_action(block)                # nothing was pressed: a tick
        keys("jk")                                     # pressed while the tick is away
        await asyncio.sleep(0.1)
        block.keep_form(tick=0)                        # the tick isn't sent, and no other comes
        batch = await next_action(block)               # what was pressed is an action, at once
        block.keep_form(tick=0)                        # and that one isn't sent either
        waiting = asyncio.ensure_future(block.next_action())
        await asyncio.sleep(0.6)
        still_waiting = not waiting.done()
        keys("q")
        return tick.key, batch.events, still_waiting, (await asyncio.wait_for(waiting, 5)).events

    assert session(script) == ("tick", ("<text>jk</text>",), True, ("<text>q</text>",))


def test_a_tick_that_isnt_sent_takes_nothing_back():
    """What an earlier action reported is with the AI, whatever happens to a later tick."""
    def menu(text):
        return Form((Field("pager", "list", text=text),), raw=True, tick=0.2)

    async def script(block, keys):
        await block.show("", menu("one\n"))
        keys("j")
        first = await next_action(block)               # this one goes to the AI,
        await block.show("", menu("two\n"))            # which answers with a new list
        tick = await next_action(block)
        block.keep_form(tick=0)                        # the tick stays here
        keys("k")
        return first, tick.key, await next_action(block)

    first, tick, second = session(script)
    assert tick == "tick" and second.events == ("<text>k</text>",)
    assert second.fields[0].text == "two\n" and not second.fields[0].changed   # the AI wrote it


# --- a wake from outside: a job's end, for a program that has no fields --------------------

def test_a_wake_ends_the_wait_of_a_program_without_fields():
    async def script(block, keys):
        await block.show("player\n", TOP)
        waiting = asyncio.ensure_future(block.next_action())
        await asyncio.sleep(0.1)
        said = block.wake()
        return said, await asyncio.wait_for(waiting, 5), block.waiting

    said, action, with_the_ai = session(script)
    assert said is True and (action.key, action.focus, action.fields, action.events) == (
        "wake", None, (), ())
    assert with_the_ai                                  # as after any action


def test_a_program_with_fields_isnt_woken_and_keeps_what_was_typed():
    async def script(block, keys):
        await block.show("  GNU nano 7.2   h.txt\n", Form((EDITOR,), keys=("C-o",), keymap="nano"))
        waiting = asyncio.ensure_future(block.next_action())
        keys("typed ")
        await asyncio.sleep(0.2)
        said = block.wake()
        await asyncio.sleep(0.2)
        still_waiting = not waiting.done()
        keys("more " + CTRL["O"])
        return said, still_waiting, await asyncio.wait_for(waiting, 5), block.actions.empty()

    said, still_waiting, action, nothing_else = session(script)
    assert said is False and still_waiting and nothing_else
    assert action.key == "C-o" and action.fields[0].text == "typed more line one\nline two\n"


def test_a_program_isnt_woken_while_an_action_is_with_the_ai():
    async def script(block, keys):
        await block.show("top\n", TOP)
        keys("j")
        first = await next_action(block)               # with the AI now
        said = block.wake()
        await block.show("top\n", TOP)                 # its answer
        waiting = asyncio.ensure_future(block.next_action())
        await asyncio.sleep(0.2)
        nothing_came = not waiting.done()              # no wake was put behind the answer
        then = block.wake()                            # the machine looks again, and it works
        return first.key, said, nothing_came, then, (await asyncio.wait_for(waiting, 5)).key

    assert session(script) == ("keys", False, True, True, "wake")


def test_keys_typed_during_the_answer_to_a_wake_go_to_the_next_screen():
    async def script(block, keys):
        await block.show("player\n", TOP)
        block.wake()
        woken = await next_action(block)
        keys("jk")                                     # typed while the AI answers the wake
        await asyncio.sleep(0.3)
        await block.show("player\n", TOP)
        return woken.key, (await next_action(block)).events

    assert session(script) == ("wake", ("<text>jk</text>",))


def test_a_wake_that_isnt_sent_gives_the_keyboard_back():
    async def script(block, keys):
        await block.show("player\n", TOP)
        block.wake()
        woken = await next_action(block)
        keys("j")
        await asyncio.sleep(0.3)
        block.keep_form()                              # the machine had nothing to send
        return woken.key, (await next_action(block)).events

    assert session(script) == ("wake", ("<text>j</text>",))


def test_a_wake_and_a_tick_that_fall_together_are_one_action():
    ticking = Form((), raw=True, tick=0.2)

    async def script(block, keys):
        await block.show("top\n", ticking)
        tick = await next_action(block)                # the time is up: a tick, with the AI now,
        behind_it = block.wake()                       # and a wake right behind it isn't taken
        await block.show("top\n", ticking)
        block.wake()                                   # a wake first, and the tick's time passes
        await asyncio.sleep(0.4)                       # before anybody waits
        first = await next_action(block)
        return tick.key, behind_it, first.key, block.actions.empty()

    assert session(script) == ("tick", False, "wake", True)


# --- a form that is put aside and put back --------------------------------------------------

NANO_FORM = Form((EDITOR,), keys=("C-o", "C-z"), keymap="nano")
PLAYER = Form((), raw=True, footer="q quit")


def test_a_suspended_editor_comes_back_with_its_text_its_cursor_and_its_focus():
    async def script(block, keys):
        await block.show("  GNU nano 7.2   h.txt\n", NANO_FORM)
        keys("hello \x1b[B")                           # typed, and one line down
        await asyncio.sleep(0.2)
        buffer = block.areas["text"].buffer
        before = block.field_text("text"), buffer.cursor_position, block._focused().id
        await block.suspend(1)
        aside = block.active, list(block.suspended)
        back = await block.resume(1)
        after = block.field_text("text"), buffer.cursor_position, block._focused().id
        same_field = block.areas["text"].buffer is buffer
        keys(CTRL["O"])                                # the AI never saw what was typed
        return before, aside, back, after, same_field, await next_action(block), block.suspended

    before, aside, back, after, same_field, action, left = session(script)
    assert before == ("hello line one\nline two\n", 21, "text") == after
    assert aside == (False, [1]) and back is True and same_field and left == {}
    (state,) = action.fields
    assert action.key == "C-o" and state.text == before[0] and state.cursor == (2, 7)
    assert state.changed and state.modified


def test_a_resume_over_a_program_that_is_on_screen_takes_its_place():
    """Job control: a <resume> without a <suspend> of what is on screen ends that program."""
    async def script(block, keys):
        await block.show("  GNU nano 7.2   h.txt\n", NANO_FORM)
        keys("hello ")
        await asyncio.sleep(0.2)
        await block.suspend(1)
        await block.show("player\n", PLAYER)           # another program, without fields
        back = await block.resume(1)                   # and the editor over it
        on_screen = block.form.raw, list(block.areas), block._focused().id, block.composed[0]
        keys("x" + CTRL["O"])                          # typed into the editor, at its cursor
        return back, on_screen, await next_action(block), list(block.suspended)

    back, on_screen, action, left = session(script)
    assert back is True and left == []
    assert on_screen[:3] == (False, ["text"], "text") and on_screen[3].startswith("  GNU nano 7.2")
    assert action.key == "C-o" and action.fields[0].text == "hello xline one\nline two\n"


def test_the_field_that_had_the_focus_has_it_again():
    """Not the one the form names, and not the first one: the one the user was in."""
    save_as = Form((Field("editor", "text", top=2, height=8, text="line one\n"),
                    Field("line", "name", top=12, left=21, width=30, text="h.txt")),
                   keys=("C-o",), focus="text")

    async def script(block, keys):
        await block.show("title\n\n\n\n\n\n\n\n\n\n\nFile Name to Write: \n", save_as)
        block.app.layout.focus(block.areas["name"])    # as a click into that field does
        keys("2")
        await asyncio.sleep(0.2)
        before = block._focused().id, block.field_text("name")
        await block.suspend(1)
        await block.resume(1)
        after = block._focused().id
        keys("3\r")                                    # Enter in a line field acts
        return before, after, await next_action(block)

    before, after, action = session(script)
    assert before == ("name", "h.txt2") and after == "name"
    assert (action.key, action.focus) == ("Enter", "name")
    assert [state.text for state in action.fields] == ["line one\n", "h.txt23"]


def test_what_the_ai_has_seen_and_what_was_saved_come_back_too():
    async def script(block, keys):
        await block.show("  GNU nano 7.2   h.txt\n", NANO_FORM)
        keys("x" + CTRL["O"])
        await next_action(block)                       # the AI sees the text, and saves it
        block.field_saved("text")
        await block.show("  GNU nano 7.2   h.txt\n", Form((Field("editor", "text", top=2, height=10),),
                                                         keys=("C-o", "C-z"), keymap="nano"))
        await block.suspend(1)
        await block.resume(1)
        keys(CTRL["O"])
        unchanged = (await next_action(block)).fields[0]
        await block.show("", block.form)
        keys("y" + CTRL["O"])
        return unchanged, (await next_action(block)).fields[0]

    unchanged, typed = session(script)
    assert (unchanged.text, unchanged.changed, unchanged.modified) == (
        "xline one\nline two\n", False, False)         # the AI saw it, and it is saved
    assert (typed.text, typed.changed, typed.modified) == ("xyline one\nline two\n", True, True)


def test_a_vi_program_comes_back_in_the_mode_it_was_in():
    """A form that is put back is shown in a new app, and a new app starts in insert mode.
    Tried on 2026-10-05: normal mode before, insert mode after, and `x` typed an x."""
    from prompt_toolkit.key_binding.vi_state import InputMode
    vi = Form((EDITOR,), keys=("C-o",), keymap="vi")

    async def script(block, keys):
        await block.show("h.txt\n", vi)
        keys("\x1b")                                   # Esc: normal mode
        await asyncio.sleep(0.7)                       # it waits, to tell Esc from an arrow
        before = block.app.vi_state.input_mode
        await block.suspend(1)
        await block.resume(1)
        after = block.app.vi_state.input_mode
        keys("x")                                      # deletes a character there
        await asyncio.sleep(0.2)
        normal = block.field_text("text")
        keys("ihi \x1b")                               # and a form suspended while inserting
        await asyncio.sleep(0.7)
        keys("a")                                      # is in insert mode again
        await asyncio.sleep(0.2)
        await block.suspend(2)
        await block.resume(2)
        inserting = block.app.vi_state.input_mode
        keys("Z")
        await asyncio.sleep(0.2)
        return before, after, normal, inserting, block.field_text("text")

    before, after, normal, inserting, typed = session(script)
    assert before == after == InputMode.NAVIGATION and normal == "ine one\nline two\n"
    assert inserting == InputMode.INSERT and "Z" in typed


def test_what_was_typed_before_a_suspend_can_be_undone_after_the_resume():
    async def script(block, keys):
        await block.show("  GNU nano 7.2   h.txt\n", NANO_FORM)
        keys("alpha ")
        await asyncio.sleep(0.2)
        keys("beta ")
        await asyncio.sleep(0.2)
        typed = block.field_text("text")
        await block.suspend(1)
        await block.resume(1)
        keys("\x1bu" * 6)                              # M-u, nano's undo, a few times
        await asyncio.sleep(0.4)
        return typed, block.field_text("text")

    typed, undone = session(script)
    assert typed == "alpha beta line one\nline two\n"
    assert "beta" not in undone and len(undone) < len(typed) - 4     # its history came with it
    assert undone.endswith("line one\nline two\n")


def test_a_resumed_program_ticks_again():
    async def script(block, keys):
        await block.show("top - 01:02:03\n", Form((), raw=True, tick=0.2))
        await block.suspend(1)
        await block.resume(1)
        started = asyncio.get_running_loop().time()
        action = await next_action(block)
        return block.form.tick, action.key, asyncio.get_running_loop().time() - started

    tick, key, waited = session(script)
    assert tick == 0.2 and key == "tick" and 0.15 < waited < 1.5


def test_two_programs_under_two_names_come_back_each_as_itself():
    async def script(block, keys):
        await block.show("  GNU nano 7.2   h.txt\n", NANO_FORM)
        keys("mine ")
        await asyncio.sleep(0.2)
        await block.suspend(1)
        await block.show("player\ncomposing…\n", PLAYER)
        await block.suspend(2)
        names = list(block.suspended)
        await block.resume(1)
        editor = on_screen(block)[0], block.field_text("text"), block.form.keymap, block.form.raw
        await block.resume(2)                          # in place of what is on screen
        player = on_screen(block)[:2], on_screen(block)[-1], block.form.raw, block.areas
        keys("j")
        return names, editor, player, (await next_action(block)).events, list(block.suspended)

    names, editor, player, events, left = session(script)
    assert names == [1, 2] and left == []
    assert editor == ("  GNU nano 7.2   h.txt", "mine line one\nline two\n", "nano", False)
    assert player == (["player", "composing…"], "q quit", True, {})
    assert events == ("<text>j</text>",)               # and it has the keyboard, as itself


def test_resuming_a_name_that_isnt_kept_does_nothing():
    async def script(block, keys):
        nothing = await block.resume(7), block.active
        await block.show("player\n", PLAYER)
        await block.suspend(1)
        other = await block.resume(2), block.active, list(block.suspended)
        await block.suspend(1)                         # with nothing on screen: nothing to keep
        return nothing, other, list(block.suspended)

    assert session(script) == ((False, False), (False, False, [1]), [1])


def test_a_forgotten_form_is_gone_and_only_eight_are_kept():
    async def script(block, keys):
        for name in range(1, 10):                      # nine: the first one goes
            await block.show(f"program {name}\n", PLAYER)
            await block.suspend(name)
        nine = list(block.suspended)
        await block.show("program 3 again\n", PLAYER)
        await block.suspend(3)                         # a name given again is the newest
        again = list(block.suspended)
        block.forget(5)
        block.forget(42)                               # no such name: nothing happens
        one_gone = list(block.suspended), await block.resume(5), await block.resume(1)
        await block.resume(3)
        shown = on_screen(block)[0]
        block.forget()                                 # and all of them, at the end of a boot
        return nine, again, one_gone, shown, list(block.suspended)

    nine, again, one_gone, shown, none = session(script)
    assert nine == [2, 3, 4, 5, 6, 7, 8, 9] and again == [2, 4, 5, 6, 7, 8, 9, 3]
    assert one_gone == ([2, 4, 6, 7, 8, 9, 3], False, False)
    assert shown == "program 3 again" and none == []


def test_a_form_resumed_on_a_smaller_window_is_fitted_and_keeps_its_footer_at_the_bottom():
    from prompt_toolkit.data_structures import Size
    from test_panel import Screen

    async def main():
        with create_pipe_input() as pipe:
            block = BlockMode(input=pipe, output=Screen(24, 80))
            try:
                await block.show("player\ncomposing…\n\n\n\n\n\n\n\nlast line\n", PLAYER)
                tall = on_screen(block)
                await block.suspend(1)
                block.output.size = Size(12, 60)       # the window shrank meanwhile
                await block.resume(1)
                return tall, on_screen(block)
            finally:
                await block.end()

    tall, small = asyncio.run(asyncio.wait_for(main(), 10))
    assert len(tall) == 24 and tall[:2] == ["player", "composing…"] and tall[-1] == "q quit"
    assert len(small) == 12 and small[:2] == ["player", "composing…"] and small[-1] == "q quit"
    assert "last line" in small                        # blank rows went, not the text


def test_keys_typed_before_a_suspend_wait_for_the_shell_and_after_a_resume_go_to_the_form():
    from prompt_toolkit.input.typeahead import get_typeahead

    async def main():
        with create_pipe_input() as pipe:
            block = BlockMode(input=pipe, output=DummyOutput())
            try:
                await block.show("  GNU nano 7.2   h.txt\n", NANO_FORM)
                pipe.send_text("\x1a")                 # Ctrl-Z: an action, with the AI now
                await next_action(block)
                pipe.send_text("ls")                   # typed while the AI answers it
                await asyncio.sleep(0.3)
                await block.suspend(1)                 # its answer: put the program aside
                for_the_shell = [press.data for press in get_typeahead(pipe)]
                await block.resume(1)
                pipe.send_text("typed ")
                await asyncio.sleep(0.3)
                return for_the_shell, block.field_text("text")
            finally:
                await block.end()

    for_the_shell, text = asyncio.run(asyncio.wait_for(main(), 10))
    assert for_the_shell == ["l", "s"] and text == "typed line one\nline two\n"


# --- hallux's own panel as a layer over a full-screen program ------------------------------

CTRL_F12, ESC, DOWN, CTRL_SHIFT_DEL = "\x1b[24;5~", "\x1b", "\x1b[B", "\x1b[3;6~"


def with_panel(script, bar=None, rows=24, cuts=None):
    """Run `script(block, keys, panel, settings)`: block mode on a pipe that was handed a real
    panel. Its Config tab is around fakes, and `settings.calls` is what they were asked."""
    from test_panel import Screen
    from test_panel_config import Machine as Settings

    from hallux.panel import Panel
    cuts = [] if cuts is None else cuts

    async def main():
        with create_pipe_input() as pipe:
            settings = Settings()
            block = BlockMode(input=pipe, output=Screen(rows, 80), bar=bar,
                              power_cut=lambda: cuts.append("cut"))
            block.panel = Panel([settings.tab()], power_cut=block.power_cut)
            try:
                return await script(block, pipe.send_text, block.panel, settings)
            finally:
                await block.end()
    return asyncio.run(asyncio.wait_for(main(), 15))


def on_screen(block):
    """What block mode's app drew last, row by row."""
    screen, size = block.app.renderer._last_screen, block.app.output.get_size()
    return ["".join(screen.data_buffer[y][x].char for x in range(size.columns)).rstrip()
            for y in range(size.rows)]


def to_row(stop):
    from test_panel_config import to
    return to(stop)


def test_the_panel_opens_over_a_program_and_leaves_it_as_it_was():
    async def script(block, keys, panel, settings):
        await block.show("  GNU nano 7.2\n", Form((EDITOR,), keys=("C-o", "C-x"), keymap="nano"))
        keys("ab" + CTRL_F12)
        await asyncio.sleep(0.3)
        opened = block.layered, panel.is_open, on_screen(block)[0].split()
        keys(to_row("tick_budget_usd") + "\r" + "1.25\r")       # typed into the panel
        await asyncio.sleep(0.2)
        keys(ESC)
        await asyncio.sleep(0.3)
        closed = block.layered, panel.is_open, on_screen(block)[0].strip()
        keys("c")
        await asyncio.sleep(0.2)
        return opened, closed, block.field_text("text"), block.actions.empty()

    opened, closed, text, nothing_sent = with_panel(script)
    assert opened == (True, True, ["Hallux", "[", "Config", "]"])
    assert closed == (False, False, "GNU nano 7.2")             # the program's screen is back
    assert text == "abc" + EDITOR.text                          # from before, and the last key
    assert nothing_sent                                         # none of it went to the AI


def test_keys_in_one_burst_go_where_they_belong():
    """Typed in one go: text, Ctrl+F12, keys for the panel, Ctrl+F12, text, an action key."""
    async def script(block, keys, panel, settings):
        await block.show("", Form((EDITOR,), keys=("C-o", "C-x")))
        keys("ab" + CTRL_F12 + to_row("tick_budget_usd") + "\r1.25\r" + CTRL_F12 + "c" + CTRL["X"])
        return await next_action(block), settings.calls

    action, calls = with_panel(script)
    assert calls == [("change", "tick_budget_usd", "1.25")]
    assert action.key == "C-x" and action.fields[0].text == "abc" + EDITOR.text


def test_typing_in_the_panel_is_plain_typing_over_vi_keys():
    from prompt_toolkit.enums import EditingMode
    from prompt_toolkit.key_binding.vi_state import InputMode

    async def script(block, keys, panel, settings):
        await block.show("", Form((EDITOR,), keys=("C-x",), keymap="vi"))
        keys(ESC)                                      # vi's normal mode
        await asyncio.sleep(0.7)
        before = block.app.editing_mode, block.app.vi_state.input_mode
        keys(CTRL_F12)
        await asyncio.sleep(0.3)
        keys(to_row("model") + "\r" + "dd-x-claude:wq" + "\r")     # all of them vi commands
        await asyncio.sleep(0.2)
        during = block.app.editing_mode
        keys(ESC)
        await asyncio.sleep(0.3)
        after = block.app.editing_mode, block.app.vi_state.input_mode
        keys("x")                                      # normal mode again: x deletes a letter
        await asyncio.sleep(0.2)
        return before, during, after, block.field_text("text"), settings.calls

    before, during, after, text, calls = with_panel(script)
    assert before == after == (EditingMode.VI, InputMode.NAVIGATION)
    assert during == EditingMode.EMACS
    assert calls == [("change", "model", "dd-x-claude:wq")]        # the name arrived whole
    assert text == EDITOR.text[1:]


def test_no_key_of_the_panel_reaches_a_raw_program():
    async def script(block, keys, panel, settings):
        await block.show("top\n", TOP)
        keys(CTRL_F12 + "jk" + DOWN + "\r")
        await asyncio.sleep(0.3)
        during = block.layered, block.actions.empty()
        keys(CTRL_F12)
        await asyncio.sleep(0.2)
        keys("q")
        return during, (await next_action(block)).events, block.actions.empty()

    during, events, no_more = with_panel(script)
    assert during == (True, True)                      # and Ctrl+F12 itself never goes
    assert events == ("<text>q</text>",) and no_more


def test_without_a_panel_the_key_does_nothing_and_still_isnt_the_ais():
    async def script(block, keys):
        await block.show("top\n", TOP)
        keys(CTRL_F12 + "q")
        return (await next_action(block)).events, block.layered

    assert session(script) == (("<text>q</text>",), False)


def test_the_panel_opens_while_the_ai_is_busy_with_the_screen():
    async def script(block, keys, panel, settings):
        await block.show("", Form((EDITOR,), keys=("C-o", "C-x")))
        keys(CTRL["O"] + "ab")                         # "ab" is typed while the AI thinks
        first = await next_action(block)
        await asyncio.sleep(0.2)
        keys(CTRL_F12 + to_row("tick_budget_usd") + "\r2\r")
        await asyncio.sleep(0.3)
        during = block.layered, list(settings.calls), block.field_text("text")
        keys(ESC)                                      # a key of its own: the panel gets it too
        await asyncio.sleep(0.3)
        closed = block.layered
        keys("c")                                      # the AI still thinks: held again
        await asyncio.sleep(0.2)
        waiting = closed, block.field_text("text")
        await block.show("", Form((Field("editor", "text"),), keys=("C-x",)))   # its next screen
        keys(CTRL["X"])
        return first.key, during, waiting, (await next_action(block)).fields[0].text

    first, during, waiting, text = with_panel(script)
    assert first == "C-o"
    assert during == (True, [("change", "tick_budget_usd", "2")], EDITOR.text)   # at once
    assert waiting == (False, EDITOR.text)             # closed; nothing got into the field
    assert text == "abc" + EDITOR.text                 # what was held went to the next screen


def test_a_tick_waits_for_the_panel_and_the_clock_starts_again():
    async def script(block, keys, panel, settings):
        await block.show("top\n", Form((), raw=True, tick=0.3))
        waiting = asyncio.ensure_future(block.next_action())
        await asyncio.sleep(0.1)
        keys(CTRL_F12)
        await asyncio.sleep(0.9)                       # three ticks long
        no_tick = not waiting.done()
        started = asyncio.get_running_loop().time()
        keys(CTRL_F12)
        action = await asyncio.wait_for(waiting, 5)
        return no_tick, action.key, asyncio.get_running_loop().time() - started

    no_tick, key, waited = with_panel(script)
    assert no_tick and key == "tick" and 0.25 < waited < 1.0


def test_a_wake_waits_for_the_panel_to_close():
    async def script(block, keys, panel, settings):
        await block.show("player\n", Form((), raw=True))
        waiting = asyncio.ensure_future(block.next_action())
        await asyncio.sleep(0.1)
        keys(CTRL_F12)
        await asyncio.sleep(0.3)
        said = block.wake()                            # yes: it will come
        await asyncio.sleep(0.3)
        held_back = not waiting.done()
        keys(CTRL_F12)                                 # the panel closes
        action = await asyncio.wait_for(waiting, 5)
        return said, held_back, action.key, block.actions.empty()

    assert with_panel(script) == (True, True, "wake", True)


def test_a_wake_that_waited_for_the_panel_goes_with_the_program():
    async def script(block, keys, panel, settings):
        await block.show("player\n", Form((), raw=True))
        keys(CTRL_F12)
        await asyncio.sleep(0.3)
        said = block.wake()
        await block.end()                              # the program ends under the panel
        return said, block.actions.empty(), block.wake_asked

    assert with_panel(script) == (True, True, False)


def test_the_panel_opens_over_a_resumed_program_as_over_any_other():
    async def script(block, keys, panel, settings):
        await block.show("player\ncomposing…\n", Form((), raw=True))
        await block.suspend(1)
        await block.resume(1)
        keys(CTRL_F12)
        await asyncio.sleep(0.3)
        over = block.layered, on_screen(block)[0]
        keys(ESC)
        await asyncio.sleep(0.3)
        return over, block.layered, on_screen(block)[:2]

    over, still, under = with_panel(script)
    assert over[0] is True and over[1].endswith("[ Config ]")
    assert still is False and under == ["player", "composing…"]


def test_set_tick_starts_a_wait_that_had_no_tick():
    async def script(block, keys):
        await block.show("top\n", Form((), raw=True, tick=0))
        waiting = asyncio.ensure_future(block.next_action())
        await asyncio.sleep(0.4)
        no_tick = not waiting.done()
        started = asyncio.get_running_loop().time()
        block.set_tick(0.2)
        action = await asyncio.wait_for(waiting, 5)
        return no_tick, action.key, asyncio.get_running_loop().time() - started, block.form.tick

    no_tick, key, waited, tick = session(script)
    assert no_tick and key == "tick" and 0.15 < waited < 1.0 and tick == 0.2


def test_a_click_in_the_panel_doesnt_reach_the_program():
    click = "\x1b[<0;40;20M\x1b[<0;40;20m"             # in the empty part of both

    async def script(block, keys, panel, settings):
        await block.show("title bar\n", Form((EDITOR,), keys=("C-x",)))
        keys(CTRL_F12)
        await asyncio.sleep(0.3)
        keys(click)
        await asyncio.sleep(0.2)
        under_the_panel = block.actions.empty()
        keys(CTRL_F12)
        await asyncio.sleep(0.2)
        keys(click)
        return under_the_panel, (await next_action(block)).key

    assert with_panel(script) == (True, "click")


def test_the_bar_stays_under_the_panel():
    from hallux.statusbar import StatusBar
    bar = StatusBar("claude-opus-5-5", "low")

    async def script(block, keys, panel, settings):
        await block.show("the program\n", Form((EDITOR,), keys=("C-x",)))
        keys(CTRL_F12)
        await asyncio.sleep(0.3)
        return on_screen(block)

    rows = with_panel(script, bar=bar, rows=12)
    assert rows[0].split() == ["Hallux", "[", "Config", "]"]
    assert "↑ ↓ move" in rows[-2] and "the program" not in "".join(rows)   # the foot, above
    assert rows[-1].startswith(" • ") and "opus 5.5 · low" in rows[-1]     # block mode's own row


def test_the_panel_closes_when_the_app_ends_under_it():
    async def script(block, keys, panel, settings):
        await block.show("top\n", TOP)
        nothing_open = asyncio.ensure_future(block.panel_gone())
        await asyncio.sleep(0.05)
        keys(CTRL_F12)
        await asyncio.sleep(0.3)
        waiting = asyncio.ensure_future(block.panel_gone())
        await asyncio.sleep(0.1)
        opened = block.layered, waiting.done(), nothing_open.done()
        block.app.exit()                               # the full-screen app dies
        await asyncio.wait_for(waiting, 2)
        return opened, block.layered, panel.is_open

    assert with_panel(script) == ((True, False, True), False, False)


def test_the_hard_exit_works_in_the_panel_over_a_program():
    async def script(block, keys, panel, settings):
        await block.show("top\n", TOP)
        keys(CTRL_F12 + CTRL_SHIFT_DEL)
        await asyncio.sleep(0.3)
        return block.layered

    cuts = []
    assert with_panel(script, cuts=cuts) is True and cuts == ["cut"]
