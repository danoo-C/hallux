"""The real terminal with prompt_toolkit: keys come from a pipe, output goes nowhere."""
import asyncio

import pytest

pytest.importorskip("prompt_toolkit")

from prompt_toolkit.formatted_text import ANSI, to_formatted_text  # noqa: E402
from prompt_toolkit.input import create_pipe_input  # noqa: E402
from prompt_toolkit.output import DummyOutput  # noqa: E402

from hallux.machine import Interrupted, Key  # noqa: E402
from hallux.protocol import plain  # noqa: E402
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


def on_screen(read, keys):
    """What a real terminal would be sent while `keys` are typed at a prompt, and the line."""
    import io

    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.output.vt100 import Vt100_Output

    screen = io.StringIO()
    output = Vt100_Output(screen, lambda: Size(rows=30, columns=100), term="xterm-256color")

    async def main():
        with create_pipe_input() as pipe:
            terminal = Terminal(None, input=pipe, output=output)
            pipe.send_text(keys)
            return await getattr(terminal, read)("Password: ")
    line = asyncio.run(asyncio.wait_for(main(), 10))
    return plain(screen.getvalue()), line


def test_a_password_is_read_without_showing_it():
    shown, line = on_screen("read_line", "hunter2\r")
    assert line == "hunter2" and "Password: hunter2" in shown          # a normal line
    shown, line = on_screen("read_secret", "hunter2\r")
    assert line == "hunter2" and "Password:" in shown
    assert shown.replace("Password:", "").strip() == ""                # and nothing else


def test_a_password_is_not_recalled():
    async def script(terminal, type_keys):
        type_keys("ls\r")
        await terminal.read_line("$ ")
        type_keys("hunter2\r")
        await terminal.read_secret("Password: ")
        type_keys("\x1b[A\r")                          # ↑ at a password prompt: nothing
        secret = await terminal.read_secret("Password: ")
        type_keys("\x1b[A\r")                          # ↑ at the shell: the last command
        return secret, await terminal.read_line("$ ")
    assert with_terminal(script) == ("", "ls")


def secret(keys):
    async def script(terminal, type_keys):
        type_keys(keys)
        return await terminal.read_secret("Password: ")
    return with_terminal(script)


def test_keys_at_a_password_prompt_carry_no_text():
    assert secret("hunter2\x03") == Key("C-c", "", 0, keep_line=False)
    assert secret("hunter2\x1a") == Key("C-z", "", 0, keep_line=False)
    assert secret("\x04") == Key("C-d", "", 0, keep_line=False)
    assert secret("hun\tter\x12\x1bOP2\r") == "hunter2"   # Tab, Ctrl-R and F1 do nothing here


def test_ctrl_shift_del_pulls_the_plug():
    cuts = []
    typed("half a line" + CTRL_SHIFT_DEL + "\r", cuts=cuts)
    assert cuts == ["cut"]


def test_the_addons_are_stopped_before_the_plug_is_pulled():
    def cut(cuts, before):
        async def main():
            with create_pipe_input() as pipe:
                terminal = Terminal(None, input=pipe, output=DummyOutput(),
                                    power_cut=lambda: cuts.append("cut"), before_power_cut=before)
                pipe.send_text(CTRL_SHIFT_DEL + "\r")
                await terminal.read_line("$ ")
        asyncio.run(asyncio.wait_for(main(), 10))
        return cuts

    order = []
    assert cut(order, lambda: order.append("addons stopped")) == ["addons stopped", "cut"]

    def broken():
        raise RuntimeError("the hooks themselves failed")
    assert cut([], broken) == ["cut"]                  # nothing keeps the plug in


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


def test_retract_erases_the_rows_a_text_took():
    import io

    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.output.vt100 import Vt100_Output

    screen = io.StringIO()
    output = Vt100_Output(screen, lambda: Size(rows=30, columns=10), term="xterm")

    async def main():
        with create_pipe_input() as pipe:
            terminal = Terminal(None, input=pipe, output=output)
            written = []
            terminal._write = written.append
            terminal.retract("0123456789012\nab\n")   # 2 rows (wrapped) + 1 row, cursor below
            terminal.retract("\x1b[31mno newline!")   # 11 visible characters: 2 rows
            terminal.retract("0123456789")             # exactly one row
            return written
    assert asyncio.run(main()) == ["\x1b[3A\r\x1b[J", "\x1b[1A\r\x1b[J", "\r\x1b[J"]


# ---------------------------------------------------------------- interrupted from outside

async def typed_in(terminal, text, session=None):
    """Wait until the prompt that is being read holds this text."""
    app = (session or terminal.session).app
    for _ in range(500):
        if app.is_running and app.current_buffer.text == text:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"the prompt never held {text!r}")


def test_an_interrupt_ends_the_prompt_and_hands_back_what_was_typed():
    async def script(terminal, type_keys):
        reading = asyncio.create_task(terminal.read_line("$ "))
        type_keys("ls -l")
        await typed_in(terminal, "ls -l")
        assert terminal.interrupt_prompt() is True
        first = await reading
        reading = asyncio.create_task(terminal.read_line("$ ", "echo hello"))
        type_keys("\x1b[D\x1b[D")                         # two to the left
        await typed_in(terminal, "echo hello")
        await asyncio.sleep(0.05)
        assert terminal.interrupt_prompt() is True
        return first, await reading

    first, second = with_terminal(script)
    assert first == Interrupted("ls -l", 5)
    assert second.line == "echo hello" and second.cursor in (8, 10)   # the keys may still be on the way


def test_an_interrupt_with_nothing_being_read_does_nothing():
    async def script(terminal, type_keys):
        nothing_read = terminal.interrupt_prompt()
        reading = asyncio.create_task(terminal.read_line("$ "))
        type_keys("ls")
        await typed_in(terminal, "ls")
        twice = terminal.interrupt_prompt(), terminal.interrupt_prompt()   # the second finds nothing
        interrupted = await reading
        async with terminal.busy(lambda: None):
            while_busy = terminal.interrupt_prompt()
        type_keys("\r")
        return nothing_read, twice, interrupted, while_busy, await terminal.read_line("$ ", "ls")

    assert with_terminal(script) == (False, (True, False), Interrupted("ls", 2), False, "ls")


def test_an_interrupt_leaves_a_password_prompt_alone():
    async def script(terminal, type_keys):
        reading = asyncio.create_task(terminal.read_secret("Password: "))
        type_keys("hunter2")
        await typed_in(terminal, "hunter2", terminal.secrets)
        assert terminal.interrupt_prompt() is False
        await asyncio.sleep(0.05)
        assert not reading.done()                                      # still asking
        type_keys("\r")
        return await reading

    assert with_terminal(script) == "hunter2"


def test_keys_that_arrive_after_an_interrupt_wait_for_the_next_prompt():
    async def script(terminal, type_keys):
        reading = asyncio.create_task(terminal.read_line("$ "))
        type_keys("ls")
        await typed_in(terminal, "ls")
        assert terminal.interrupt_prompt() is True
        type_keys(" -l\r")                                            # typed in the same moment
        interrupted = await reading
        return interrupted, await terminal.read_line("$ ", interrupted.line)

    assert with_terminal(script) == (Interrupted("ls", 2), "ls -l")    # nothing is lost


def test_an_interrupt_after_enter_changes_nothing():
    async def script(terminal, type_keys):
        reading = asyncio.create_task(terminal.read_line("$ "))
        type_keys("pwd")
        await typed_in(terminal, "pwd")
        terminal.session.app.exit(result="pwd")                        # what Enter does
        return terminal.interrupt_prompt(), await reading              # in the same moment

    assert with_terminal(script) == (False, "pwd")                     # the line wins


def test_an_addons_event_interrupts_the_real_prompt(tmp_path):
    """The whole path with the real terminal: a line half typed, an event from another thread,
    the AI's answer, and the line back at the prompt to be finished."""
    import threading

    from test_machine import FakeModel, result, screen

    from hallux import addons
    from hallux.config import Hardware
    from hallux.machine import Machine

    hub = addons.Events()
    bell = addons.Addon("bell", "A bell.", "the manual", {}, has_events=True)
    model = FakeModel([lambda: hub.listen("bell")] + result(screen("", prompt="$ ")),
                      screen("ding\n", prompt="$ "),
                      screen("logout\n", prompt="", tail="<halt/>"))

    async def script(terminal, type_keys):
        machine = Machine(tmp_path, Hardware(), terminal, client_factory=model, addons=[bell],
                          events=hub)
        running = asyncio.create_task(machine.run())
        type_keys("echo hel")
        await typed_in(terminal, "echo hel")
        threading.Thread(target=hub.emit, args=("bell", {"ring": 1})).start()
        await typed_in(terminal, "echo hel")                           # gone, and back again
        while len(model.sessions[0]) < 2:
            await asyncio.sleep(0.01)
        await typed_in(terminal, "echo hel")
        type_keys("lo\r")
        await running

    with_terminal(script, bar=StatusBar("claude-opus-5-5", "low"))
    boot, events, typed = model.sessions[0]
    assert events.startswith("<events ") and '<event addon="bell">{"ring": 1}</event>' in events
    assert typed.endswith(">echo hello</input>")                       # nothing typed was lost


def test_a_program_goes_on_when_its_action_isnt_sent(tmp_path):
    """The real terminal, block mode and the machine: over the boot's cap an action stays
    here, typing goes on, and once the cap is raised the next action brings all of it."""
    from test_machine import FakeModel, result, screen

    from hallux.config import Hardware
    from hallux.machine import Machine

    (tmp_path / "notes.txt").write_text("hi\n")
    model = FakeModel(
        result(screen(""), total=0.004),
        result('<screen>\n  GNU nano 7.2   notes.txt\n</screen><prompt></prompt>'
               '<form keys="C-o C-x" keymap="nano"><editor id="text" top="2" file="notes.txt"/>'
               '</form>', total=0.02),                                  # over one cent
        result(screen("", prompt="$ "), total=0.03),
        result(screen("logout\n", prompt="", tail="<halt/>"), total=0.04))

    async def script(terminal, type_keys):
        machine = Machine(tmp_path, Hardware(max_budget_usd=0.01), terminal, client_factory=model)
        running = asyncio.ensure_future(machine.run())
        type_keys("nano notes.txt\r" "x\x0f" "y")      # ^O is held back; "y" is typed after it
        await asyncio.sleep(0.5)
        held = len(model.sessions[0]), terminal.block.field_text("text"), dict(machine.notes)
        assert machine.change("max_budget_usd", "1") is None
        type_keys("z\x18")                             # ^X: this one goes
        await asyncio.sleep(0.5)
        type_keys("\x04")
        await running
        return held

    held = with_terminal(script, bar=StatusBar("claude-opus-5-5", "low"))
    assert held == (2, "xyhi\n", {"max_budget_usd": "budget used: $0.01 per boot"})
    boot, nano, ctrl_x, ctrl_d = model.sessions[0]     # ^O never reached the AI
    assert ctrl_x.startswith('<action key="C-x"') and ">xyzhi\n</field>" in ctrl_x
    assert 'unchanged="yes"' not in ctrl_x             # the text in full: the AI hasn't seen it

