"""The machine loop, driven by a scripted keyboard and a fake model."""
import asyncio
import contextlib
import logging
import sys

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent, ToolUseBlock

from hallux import config
from hallux.addons import Events
from hallux.config import Hardware
from hallux.machine import SYSTEM_PROMPT, Interrupted, Key, Machine
from hallux.protocol import Action, FieldState


def result(text, *, error=False, total=0.001, tools=(), chunks=0):
    """A model turn: optional tool calls, the text streamed in pieces of `chunks` characters
    (0: not streamed), then the result (the SDK reports a running total)."""
    streamed = []
    if chunks:
        event = lambda e: StreamEvent(uuid="u", session_id="s", event=e)   # noqa: E731
        streamed = [event({"type": "content_block_start", "index": 0,
                           "content_block": {"type": "text", "text": ""}})]
        streamed += [event({"type": "content_block_delta", "index": 0,
                            "delta": {"type": "text_delta", "text": text[i:i + chunks]}})
                     for i in range(0, len(text), chunks)]
    message = ResultMessage(subtype="error_during_execution" if error else "success",
                            duration_ms=1500, duration_api_ms=1, is_error=error, num_turns=1,
                            session_id="s", result=text, total_cost_usd=total)
    calls = [AssistantMessage(content=[ToolUseBlock(id=str(i), name=f"mcp__hallux__{name}",
                                                    input=args)], model="m")
             for i, (name, args) in enumerate(tools)]
    return calls + streamed + [message]


class FakeModel:
    """Hands out scripted results, one per message, across as many sessions as it's asked for."""

    def __init__(self, *results):
        self.results = [r if isinstance(r, list) else result(r) for r in results]
        self.interrupts = 0
        self.sessions = []                   # the messages each session received
        self.options = []
        self.switches = []                   # set_model: (the model, messages sent before it)
        self.refuses = {}                    # a model name: why the session won't switch to it

    def __call__(self, options):
        self.options.append(options)
        self.sessions.append([])
        return FakeClient(self)


class FakeClient:
    def __init__(self, model):
        self.model = model

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def query(self, message):
        self.model.sessions[-1].append(message)

    async def receive_response(self):
        for message in self.model.results.pop(0):
            if callable(message):            # something that happens while the AI works
                message()
            else:
                yield message

    async def interrupt(self):
        self.model.interrupts += 1

    async def set_model(self, model):
        self.model.switches.append((model, len(self.model.sessions[-1])))
        if model in self.model.refuses:
            raise Exception(self.model.refuses[model])      # the SDK raises nothing finer


class Typing:
    """A scripted key: the user is in the middle of this line, and stays there until the
    prompt is interrupted from outside. `meanwhile` happens while they type; the prompt
    refuses the first `not_up_yet` interrupts, as one that is still being drawn does."""

    def __init__(self, text, meanwhile=lambda: None, not_up_yet=0):
        self.text, self.meanwhile, self.not_up_yet = text, meanwhile, not_up_yet


class FakeTerminal:
    """Types the scripted keys; records what was shown."""

    status_bar = False

    def __init__(self, *keys, ctrl_c_while_busy=()):
        self.keys = list(keys)
        self.screen = ""
        self.prompts = []                    # (prompt, restored line) per read
        self.secret_prompts = []             # the prompts that were read with echo off
        self.statuses = []                   # every set_status call
        self.activities = []                 # what each busy period was about
        self.ctrl_c_while_busy = list(ctrl_c_while_busy)   # per busy period: press Ctrl-C?

    async def start(self):
        pass

    def stop(self):
        pass

    @contextlib.asynccontextmanager
    async def busy(self, interrupt, activity="thinking…"):
        self.activities.append(activity)
        if self.ctrl_c_while_busy and self.ctrl_c_while_busy.pop(0):
            interrupt()
        yield

    def set_status(self, **changes):
        self.statuses.append(changes)

    def next_key(self):
        """The next scripted key. What is callable among the keys happens on the way, while
        the terminal waits: a change in hallux's own panel, say."""
        while callable(self.keys[0]) and not isinstance(self.keys[0], type):
            self.keys.pop(0)()
        return self.keys.pop(0)

    async def read_line(self, prompt, default=""):
        self.prompts.append((prompt, default))
        key = self.next_key()
        if isinstance(key, type) and issubclass(key, BaseException):
            raise key
        if isinstance(key, Typing):
            self.typing, self.interrupted = key, asyncio.Event()
            key.meanwhile()
            await asyncio.wait_for(self.interrupted.wait(), 5)     # nobody came: the test fails
            self.typing = None
            return Interrupted(default + key.text, len(default + key.text))
        return key

    typing = None                            # the Typing that waits at the prompt now

    def interrupt_prompt(self):
        if self.typing is None or self.interrupted.is_set():
            return False
        if self.typing.not_up_yet:
            self.typing.not_up_yet -= 1
            return False
        self.interrupted.set()
        return True

    async def read_secret(self, prompt):
        self.secret_prompts.append(prompt)
        return await self.read_line(prompt)

    streams = False

    def write(self, text):
        self.screen += text
        self.writes = getattr(self, "writes", []) + [text]

    def retract(self, text):
        self.retracted = getattr(self, "retracted", []) + [text]
        self.screen = self.screen.removesuffix(text)

    def size(self):
        return 100, 30

    # block mode: forms are recorded, actions come from the same script as the keys
    forms = None
    ended = 0
    texts = None

    async def show_form(self, screen, form, patch=None):
        self.forms = (self.forms or []) + [(screen, form)]
        self.patches = getattr(self, "patches", []) + [patch]
        self.texts = {f.id: f.text for f in form.fields if f.text is not None} | (self.texts or {})

    async def next_action(self):
        key = self.next_key()
        if isinstance(key, type) and issubclass(key, BaseException):
            raise key
        return key

    kept = None                              # the ticks keep_form was called with
    ticks = None                             # the ticks set_tick gave the program on screen

    def keep_form(self, tick=None):
        self.kept = (self.kept or []) + [tick]

    def set_tick(self, seconds):
        self.ticks = (self.ticks or []) + [seconds]

    async def end_form(self):
        if self.forms and self.ended < len(self.forms):
            self.ended = len(self.forms)

    def field_text(self, id):
        return self.texts[id]

    def field_saved(self, id):
        pass


def screen(text, prompt="user@hallux:~$ ", tail=""):
    return f"<screen>\n{text}</screen><prompt>{prompt}</prompt>{tail}"


def run(tmp_path, model, terminal, hardware=Hardware()):
    machine = Machine(tmp_path, hardware, terminal, client_factory=model)
    asyncio.run(machine.run())
    return machine


def test_boot_input_and_halt(tmp_path):
    model = FakeModel(screen("Debian GNU/Linux 12 hallux tty1\n"),
                      screen("fib.py  notes.md\n"),
                      screen("logout\n", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("ls", EOFError)
    run(tmp_path, model, terminal)
    assert terminal.screen == "Debian GNU/Linux 12 hallux tty1\nfib.py  notes.md\nlogout\n"
    assert terminal.prompts == [("user@hallux:~$ ", ""), ("user@hallux:~$ ", "")]
    boot, ls, eof = model.sessions[0]
    assert boot.startswith('<boot first="yes" cwd="/" time="') and 'cols="100" rows="30"' in boot
    assert boot.endswith("></boot>")
    assert ls.startswith("<input ") and ls.endswith(">ls</input>")
    assert eof.startswith('<key name="C-d" ') and eof.endswith("></key>")


def test_reboot_starts_a_fresh_session(tmp_path):
    model = FakeModel(screen("boot 1\n"),
                      screen("rebooting\n", prompt="", tail="<reboot/>"),
                      screen("boot 2\n"),
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("reboot", "poweroff")
    machine = run(tmp_path, model, terminal)
    assert len(model.sessions) == 2
    assert model.sessions[1][0].startswith("<boot ")
    assert terminal.screen == "boot 1\nrebooting\nboot 2\n"
    assert machine.disk.cwd == "/"


def test_the_prompt_comes_from_the_ai(tmp_path):
    model = FakeModel(screen("", prompt="user@hallux:~$ "),
                      screen("hallux: prompt saved to ~/.bashrc\n", prompt="␛[35mcow daysi moo>␛[0m "),
                      screen("Python 3.11.2\n", prompt=">>> "),
                      result("broken reply without a prompt"),       # keeps ">>> "
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal('hallux i want my prompt to be "cow daysi moo> "', "python3", "x", "exit")
    run(tmp_path, model, terminal)
    assert [p for p, _ in terminal.prompts] == [
        "user@hallux:~$ ", "\x1b[35mcow daysi moo>\x1b[0m ", ">>> ", ">>> "]


def test_keys_go_to_the_ai(tmp_path):
    model = FakeModel(screen(""),
                      screen("", tail=""),                          # Ctrl-C at the prompt
                      screen("␛[H␛[2J"),                             # Ctrl-L
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal(KeyboardInterrupt, Key("C-l", "ls -l"), EOFError)
    run(tmp_path, model, terminal)
    _, ctrl_c, ctrl_l, _ = model.sessions[0]
    assert ctrl_c.startswith('<key name="C-c" cursor="0" ') and ctrl_c.endswith("></key>")
    assert ctrl_l.startswith('<key name="C-l" cursor="0" ') and ctrl_l.endswith(">ls -l</key>")
    assert terminal.screen == "\x1b[H\x1b[2J"
    assert terminal.prompts[2] == ("user@hallux:~$ ", "ls -l")      # the typed line comes back


def ask(text, name="user", new=False):
    """A reply that asks for a password."""
    attrs = f'secret="{name}"' + (' new="yes"' if new else "")
    return f"<screen>\n</screen><prompt {attrs}>{text}</prompt>"


def test_a_password_stays_on_this_computer(tmp_path, caplog):
    """sudo, passwd, sudo again: the AI hears whether a password is right, never the password."""
    caplog.set_level("INFO", logger="hallux")
    model = FakeModel(screen(""),
                      ask("[sudo] password for user: "),             # sudo true
                      screen(""),                                    # none set: anything goes
                      ask("New password: ", new=True),               # passwd
                      ask("Retype new password: ", new=True),
                      screen("passwd: password updated successfully\n"),
                      ask("[sudo] password for user: "),             # sudo true
                      ask("[sudo] password for user: "),             # wrong: asked again
                      screen(""),
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("sudo true", "hunter2", "passwd", "s3cret", "s3cret",
                            "sudo true", "hunter2", "s3cret", EOFError)
    run(tmp_path, model, terminal)
    _, _, unset, _, first, saved, _, wrong, right, _ = model.sessions[0]
    assert unset.startswith('<input secret="user" match="unset" ') and unset.endswith("></input>")
    assert first.startswith('<input secret="user" new="first" ')
    assert saved.startswith('<input secret="user" new="saved" ')
    assert wrong.startswith('<input secret="user" match="no" ')
    assert right.startswith('<input secret="user" match="yes" ')
    assert terminal.secret_prompts == ["[sudo] password for user: ", "New password: ",
                                       "Retype new password: ", "[sudo] password for user: ",
                                       "[sudo] password for user: "]
    seen = "".join(model.sessions[0]) + caplog.text + (tmp_path / ".hallux/passwords.json").read_text()
    assert "sudo true" in seen and "hunter2" not in seen and "s3cret" not in seen


def test_only_enter_at_a_password_prompt_is_reported(tmp_path):
    model = FakeModel(screen(""), ask("Password: ", "root"), screen("su: Authentication failure\n"),
                      screen("", prompt="", tail="<halt/>"))
    run(tmp_path, model, FakeTerminal("su", "", EOFError))
    assert model.sessions[0][2].startswith('<input secret="root" match="unset" empty="yes" ')


def test_a_key_at_a_password_prompt_names_it_and_drops_a_half_set_password(tmp_path):
    model = FakeModel(screen(""),
                      ask("New password: ", new=True), ask("Retype new password: ", new=True),
                      screen(""),                                    # Ctrl-C: back to the shell
                      ask("New password: ", new=True), screen(""),
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("passwd", "abc", Key("C-c", "", keep_line=False), "passwd", "abc", EOFError)
    run(tmp_path, model, terminal)
    _, _, first, ctrl_c, _, again, eof = model.sessions[0]
    assert ctrl_c.startswith('<key name="C-c" cursor="0" secret="user" ') and ctrl_c.endswith("></key>")
    assert first.startswith('<input secret="user" new="first" ')
    assert again.startswith('<input secret="user" new="first" ')    # not taken for the retype
    assert "secret" not in eof                                       # the shell prompt again
    assert not (tmp_path / ".hallux" / "passwords.json").exists()


def test_a_failed_answer_leaves_the_password_prompt_hidden(tmp_path, capsys):
    model = FakeModel(screen(""), ask("Password: "),
                      result("overloaded", error=True),              # the prompt stays as it was
                      screen(""), screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("su", "hunter2", "hunter2", EOFError)
    run(tmp_path, model, terminal)
    assert terminal.secret_prompts == ["Password: ", "Password: "]
    assert "hunter2" not in "".join(model.sessions[0])


def test_cwd_travels_in_every_envelope(tmp_path):
    (tmp_path / "home" / "user").mkdir(parents=True)
    model = FakeModel(screen(""), screen(""), screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("cd", "exit")
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)

    async def boot_then_cd():
        read_line = terminal.read_line

        async def typing(prompt, default=""):
            line = await read_line(prompt, default)
            if line == "cd":
                machine.disk.chdir("/home/user")                    # what the chdir tool does
            return line
        terminal.read_line = typing
        await machine.run()

    asyncio.run(boot_then_cd())
    assert 'cwd="/"' in model.sessions[0][0]
    assert 'cwd="/home/user"' in model.sessions[0][2]


def test_model_errors(tmp_path, capsys):
    model = FakeModel(screen(""),
                      result("overloaded", error=True),             # a command fails: go on
                      result("still down", error=True))             # Ctrl-D fails: halt anyway
    terminal = FakeTerminal("ls", EOFError)
    run(tmp_path, model, terminal)
    assert "hallux: the model failed (overloaded)" in capsys.readouterr().err
    assert terminal.prompts == [("user@hallux:~$ ", ""), ("user@hallux:~$ ", "")]


def test_failed_boot_exits(tmp_path, capsys):
    with pytest.raises(SystemExit):
        run(tmp_path, FakeModel(result("invalid api key", error=True)), FakeTerminal())
    assert "invalid api key" in capsys.readouterr().err


def test_options(tmp_path):
    model = FakeModel(screen("", prompt="", tail="<halt/>"))
    run(tmp_path, model, FakeTerminal(), Hardware(model="claude-haiku-4-5", effort="high"))
    options = model.options[0]
    assert options.system_prompt == SYSTEM_PROMPT and "REPLY FORMAT" in SYSTEM_PROMPT
    assert options.model == "claude-haiku-4-5" and options.effort is None
    assert options.tools == [] and options.permission_mode == "dontAsk"
    assert options.strict_mcp_config and options.setting_sources == []
    assert list(options.mcp_servers) == ["hallux"]
    assert "mcp__hallux__read_file" in options.allowed_tools
    assert all(name.startswith("mcp__hallux__") for name in options.allowed_tools)


# --- the words of the prompt: a test holds what it says, not what the AI does with it ----------

def rule_of(section, start):
    """The rule of the prompt that starts with these words, on one line."""
    return " ".join(section[section.index(f"- {start}"):].split("\n- ")[0].split())


def test_the_prompt_puts_a_request_before_a_card_and_a_rule_before_a_request():
    programs = SYSTEM_PROMPT.split("\nPROGRAMS\n")[1].split("\nADDONS\n")[0]
    assert programs.index("- Programs invented with hallux") < programs.index("- A card says")
    rule = rule_of(programs, "A card says what its program does when it isn't asked otherwise")
    for part in ("its numbers and habits are defaults",
                 "in its arguments or typed into it, comes before them",
                 "one request changes nothing for the next run",
                 "A rule still comes before a request."):
        assert part in rule
    assert rule.endswith("Where a card says how its program does something, that comes before "
                         "what this prompt says about programs in general, never before REPLY "
                         "FORMAT and THE DISK IS REAL.")


def test_the_prompt_says_where_a_change_made_with_hallux_goes():
    command = SYSTEM_PROMPT.split("\nTHE hallux COMMAND\n")[1]
    assert ("go into ~/.bashrc, a change to an invented program into its card, and everything "
            "else into the Rules section of memory.") in " ".join(command.split())
    assert command.index("- Only a hallux command typed") < command.index("- A change to how")
    line = rule_of(command, "A change to how an invented program behaves goes into its card.")
    for part in ('("never more than a minute") goes into the Rules.',
                 "When it isn't clear which is meant, it goes into the card.",
                 "The confirming line says where the change went."):
        assert part in line


NANO = ('<screen>\n  GNU nano 7.2   hello.txt\n</screen><prompt></prompt>'
        '<form keys="C-o C-x" focus="text" keymap="nano">'
        '<editor id="text" top="3" left="1" height="20" file="hello.txt"/></form>')


def test_block_mode_nano_session(tmp_path):
    (tmp_path / "home" / "user").mkdir(parents=True)
    (tmp_path / "home" / "user" / "hello.txt").write_text("hi\n")
    model = FakeModel(screen(""),
                      NANO,
                      '<screen>\n  File Name to Write: </screen><prompt></prompt>'
                      '<form keys="C-c"><editor id="text"/><line id="name" top="23" left="21">'
                      'hello.txt</line></form>',
                      '<screen>\n  GNU nano 7.2   hello.txt\n</screen><prompt></prompt>'
                      '<form keys="C-o C-x"><editor id="text"/></form>',
                      screen("", prompt="user@hallux:~$ "),
                      screen("", prompt="", tail="<halt/>"))
    edited = FieldState("text", "hi\nthere\n", (2, 6), modified=True, changed=True)
    terminal = FakeTerminal(
        "nano hello.txt",
        Action("C-o", "text", (edited,)),
        Action("Enter", "name", (FieldState("text", edited.text, (2, 6), True, False),
                                 FieldState("name", "hello.txt", (1, 10), False, False))),
        Action("C-x", "text", (FieldState("text", edited.text, (2, 6), False, False),)),
        EOFError)
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)

    async def cd_home_then_run():
        read_line = terminal.read_line

        async def typing(prompt, default=""):
            machine.disk.chdir("/home/user")             # what the AI's boot does
            return await read_line(prompt, default)
        terminal.read_line = typing
        await machine.run()

    asyncio.run(cd_home_then_run())
    first_screen, first_form = terminal.forms[0]
    assert first_screen == "  GNU nano 7.2   hello.txt\n"
    assert first_form.fields[0].text == "hi\n"           # loaded from the disk, not the AI
    assert first_form.keymap == "nano" and first_form.keys == ("C-o", "C-x")
    kept = terminal.forms[1][1].fields[0]                  # <editor id="text"/> after ^O
    assert (kept.top, kept.left, kept.height, kept.text) == (3, 1, 20, None)   # same place,
    assert kept.file == "hello.txt"                        # same file, the user's text kept
    _, _, ctrl_o, enter, ctrl_x, _ = model.sessions[0]
    assert ctrl_o.startswith('<action key="C-o" focus="text" ')
    assert '<field id="text" cursor="2:6" modified="yes">hi\nthere\n</field>' in ctrl_o
    assert '<field id="text" cursor="2:6" modified="yes" unchanged="yes"></field>' in enter
    assert ctrl_x.startswith('<action key="C-x" ')
    assert terminal.ended == 3                            # the shell screen came back
    assert terminal.prompts[-1][0] == "user@hallux:~$ "   # and the shell's prompt with it


def test_block_mode_survives_a_model_failure(tmp_path, capsys):
    model = FakeModel(screen(""), NANO, result("overloaded", error=True),
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("nano hello.txt", Action("C-x", "text", ()), EOFError)
    run(tmp_path, model, terminal)
    assert terminal.ended == 1                            # thrown out of the form, not stuck
    assert terminal.prompts[-1][0] == "user@hallux:~$ "
    assert "overloaded" in capsys.readouterr().err


def test_a_click_reports_where_it_landed(tmp_path):
    model = FakeModel(screen(""), NANO, screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("nano x", Action("click", "text", (), row=24, col=3))
    run(tmp_path, model, terminal)
    click = model.sessions[0][2]
    assert click.startswith('<action key="click" focus="text" row="24" col="3" ')


def test_keys_and_the_line_that_comes_back(tmp_path):
    model = FakeModel(screen(""),
                      screen("") + "<edit>cat /etc/</edit>",       # Tab: the AI completes
                      screen(""),                                   # Ctrl-C drops the line
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal(Key("Tab", "cat /et", cursor=7),
                            Key("C-c", "rm -rf", cursor=6, keep_line=False), "exit")
    run(tmp_path, model, terminal)
    _, tab, ctrl_c, _ = model.sessions[0]
    assert tab.startswith('<key name="Tab" cursor="7" ') and tab.endswith(">cat /et</key>")
    assert [default for _, default in terminal.prompts] == ["", "cat /etc/", ""]


def test_ctrl_c_while_the_ai_works_interrupts_it(tmp_path):
    model = FakeModel(screen(""),
                      screen("half an answer"),                     # cut off, never shown
                      screen("^C\n"),
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("sleep 100", "exit", ctrl_c_while_busy=[False, True])
    run(tmp_path, model, terminal)
    _, sleep, ctrl_c, _ = model.sessions[0]
    assert model.interrupts == 1
    assert ctrl_c.startswith('<key name="C-c" interrupted="yes" ') and ctrl_c.endswith("></key>")
    assert "half an answer" not in terminal.screen and "^C\n" in terminal.screen


def test_the_status_bar_follows_the_work(tmp_path):
    model = FakeModel(result(screen(""), total=0.07),
                      result(screen("hallux\n"), total=0.09,
                             tools=[("read_file", {"path": "/etc/hostname"}),
                                    ("memory_edit", {"old": "", "new": "x"})]),
                      result(screen("", prompt="", tail="<halt/>"), total=0.1))
    terminal = FakeTerminal("cat /etc/hostname", "exit")
    machine = run(tmp_path, model, terminal)
    assert terminal.activities == ["booting…", "thinking…", "thinking…"]
    assert {"activity": "reading /etc/hostname", "tools": 1} in terminal.statuses
    assert {"activity": "remembering…", "tools": 2} in terminal.statuses
    costs = [s["cost"] for s in terminal.statuses if "cost" in s]
    assert costs == pytest.approx([0.07, 0.09, 0.1])            # a running total, not a sum
    assert machine.spent == pytest.approx(0.1)


def test_model_errors_go_to_the_status_bar(tmp_path, capsys):
    model = FakeModel(screen(""), result("overloaded", error=True),
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("ls", "exit")
    terminal.status_bar = True
    run(tmp_path, model, terminal)
    assert {"error": "overloaded"} in terminal.statuses
    assert capsys.readouterr().err == ""                        # nothing scribbled on screen



def test_a_first_boot_gets_an_empty_directory_tree(tmp_path):
    model = FakeModel(screen("", tail="<cwd>/home/user</cwd>"), screen("", prompt="", tail="<halt/>"))
    machine = run(tmp_path, model, FakeTerminal("exit"))
    boot = model.sessions[0][0]
    assert boot.startswith('<boot first="yes" ') and "<memory>" not in boot
    for folder in ("etc", "home/user", "root", "tmp", "var/log", "usr/local/bin"):
        assert (tmp_path / folder).is_dir()
    assert 'cwd="/home/user"' in model.sessions[0][1]         # <cwd> moved the shell


def test_a_boot_brings_the_memory_and_the_defining_files(tmp_path):
    (tmp_path / ".hallux").mkdir()
    (tmp_path / ".hallux" / "memory.md").write_text("# hallux memory\n## Machine\n- Debian 12\n")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "hostname").write_text("kitty\n")
    (tmp_path / "home" / "user").mkdir(parents=True)
    (tmp_path / "home" / "user" / ".bashrc").write_text('PS1="moo> "\n')
    (tmp_path / "etc" / "big").write_text("x" * 100_000)             # not a boot file anyway
    model = FakeModel(screen("", prompt="moo> "), screen("", prompt="", tail="<halt/>"))
    run(tmp_path, model, FakeTerminal("exit"))
    boot = model.sessions[0][0]
    assert boot.startswith('<boot first="no" ')
    assert "<memory>\n# hallux memory\n## Machine\n- Debian 12\n</memory>" in boot
    assert '<file path="/etc/hostname">kitty\n</file>' in boot
    assert '<file path="/home/user/.bashrc">PS1="moo> "\n</file>' in boot
    assert "xxxx" not in boot and not (tmp_path / "tmp").exists()      # no skeleton either


def test_a_bad_cwd_is_ignored(tmp_path):
    model = FakeModel(screen("", tail="<cwd>/nope</cwd>"), screen("", prompt="", tail="<halt/>"))
    machine = run(tmp_path, model, FakeTerminal("exit"))
    assert 'cwd="/"' in model.sessions[0][1]



def test_answers_stream_onto_the_screen(tmp_path):
    ls = "\n".join(f"file{i}.txt" for i in range(20)) + "\n"
    model = FakeModel(result(screen("booting\n"), chunks=5),
                      result(screen(ls), chunks=7),
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("ls", "exit")
    terminal.streams = True
    run(tmp_path, model, terminal)
    assert terminal.screen == "booting\n" + ls                  # everything, exactly once
    assert len(terminal.writes) > 10                             # ... in many small pieces
    assert {"activity": "writing…"} in terminal.statuses


def test_a_streamed_full_screen_program_is_taken_back(tmp_path):
    """If the AI puts the form after the screen, the chrome streamed into the shell is erased."""
    nano_last = ("<screen>\n  GNU nano 7.2\n</screen><prompt></prompt>"
                 '<form keys="C-x"><editor id="text" top="2"/></form>')
    nano_first = ('<form keys="C-x"><editor id="text" top="2"/></form>'
                  "<screen>\n  GNU nano 7.2\n</screen><prompt></prompt>")
    for reply, retracted in ((nano_last, ["  GNU nano 7.2\n"]), (nano_first, [])):
        model = FakeModel(screen(""), result(reply, chunks=4), screen("", prompt="", tail="<halt/>"))
        terminal = FakeTerminal("nano x", Action("C-x", "text", ()), "exit")
        terminal.streams = True
        run(tmp_path, model, terminal)
        assert getattr(terminal, "retracted", []) == retracted
        assert "GNU nano" not in terminal.screen                 # it went to the form instead
        assert terminal.forms[0][0] == "  GNU nano 7.2\n"


def test_nothing_streams_under_a_form(tmp_path):
    model = FakeModel(screen(""), NANO,
                      result("<screen>\n  still nano\n</screen><prompt></prompt>"
                             '<form keys="C-x"><editor id="text"/></form>', chunks=3),
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("nano hello.txt", Action("C-o", "text", ()), Action("C-x", "text", ()),
                            "exit")
    terminal.streams = True
    run(tmp_path, model, terminal)
    assert "still nano" not in terminal.screen and not getattr(terminal, "retracted", [])



def test_claude_code_keeps_no_transcript_unless_asked(tmp_path):
    for hardware, flags in ((Hardware(), {"no-session-persistence": None}),
                            (Hardware(keep_transcripts=True), {})):
        model = FakeModel(screen("", prompt="", tail="<halt/>"))
        run(tmp_path, model, FakeTerminal(), hardware)
        assert model.options[0].extra_args == flags and model.options[0].cli_path is None


def test_os_sandbox_runs_claude_code_through_the_wrapper(tmp_path, monkeypatch):
    import hallux.sandbox
    monkeypatch.setattr(hallux.sandbox, "wrapper", lambda folder: folder / "claude-in-bwrap")
    model = FakeModel(screen("", prompt="", tail="<halt/>"))
    run(tmp_path, model, FakeTerminal(), Hardware(os_sandbox=True))
    assert model.options[0].cli_path == tmp_path / ".hallux" / "claude-in-bwrap"


TOP = ('<form raw="yes" tick="3"><footer>\nq quit\n</footer></form>'
       '<screen>\ntop - 01:02:03 up 3 days\n</screen><prompt></prompt>')


def test_raw_mode_sends_keys_and_ticks(tmp_path):
    model = FakeModel(screen(""), TOP, TOP, TOP, screen("", prompt="$ "), screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("top", Action("tick", None), Action("keys", None, events=("<key>Down</key>",)),
                            Action("keys", None, events=("<text>q</text>",)), "exit")
    terminal.streams = True
    run(tmp_path, model, terminal)
    _, top, tick, down, q, _ = model.sessions[0]
    assert tick.startswith("<tick ") and tick.endswith("></tick>")
    assert down.startswith("<keys ") and down.endswith("><key>Down</key></keys>")
    assert q.endswith("><text>q</text></keys>")
    assert terminal.forms[0][1].raw and terminal.forms[0][1].tick == 3
    assert "top - 01:02:03" not in terminal.screen          # never streamed into the shell
    assert "updating…" in terminal.activities


def test_ticks_pause_when_their_budget_is_spent(tmp_path):
    model = FakeModel(screen(""), TOP, result(TOP, total=0.2), result(TOP, total=0.4),
                      screen("", prompt="$ "), screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("top", Action("tick", None), Action("tick", None),
                            Action("keys", None, events=("<text>q</text>",)), "exit")
    run(tmp_path, model, terminal, Hardware(tick_budget_usd=0.3))
    ticks = [form.tick for _, form in terminal.forms]
    assert ticks == [3, 3, 0]                               # $0.40 spent on ticks: paused
    assert {"note": "live updates paused: tick budget used"} in terminal.statuses
    assert {"note": None} in terminal.statuses              # cleared when top exits



def test_a_patch_reaches_the_screen(tmp_path):
    patch_reply = ('<form keys="C-x"><editor id="text"/></form><patch>\n'
                   '<rows from="-3">[ Wrote 1 line ]</rows>\n</patch><prompt></prompt>')
    model = FakeModel(screen(""), NANO, patch_reply, screen("", prompt="$ "),
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("nano hello.txt", Action("C-o", "text", ()), Action("C-x", "text", ()), "exit")
    run(tmp_path, model, terminal)
    assert terminal.patches == [None, ((-3, ("[ Wrote 1 line ]",)),)]
    assert terminal.forms[1][1].fields[0].top == 3           # the editor kept its place


# --- settings that change while the machine runs: what hallux's own panel calls -----------------

HALT = screen("", prompt="", tail="<halt/>")
KEY = {"x": Action("keys", None, events=("<text>x</text>",)),
       "q": Action("keys", None, events=("<text>q</text>",))}
EVENTS_USED, EVENTS_OFF = "events paused: budget used", "events are off: event_budget_usd is 0"
TICKS_USED = "live updates paused: tick budget used"


def notes_of(terminal):
    return [status["note"] for status in terminal.statuses if "note" in status]


def kinds(model):
    return [message[1:].split(" ")[0] for message in model.sessions[0]]


def idle(tmp_path, hardware=Hardware(), **more):
    """A machine that isn't switched on: what the panel calls needs no boot."""
    terminal = FakeTerminal()
    return Machine(tmp_path, hardware, terminal, client_factory=FakeModel(), **more), terminal


def test_a_raised_event_budget_lets_events_through_again(tmp_path):
    hub = Events()

    def raise_it():
        hub.emit("bell", {"ring": "unheard"})                # paused: it is dropped
        assert machine.change("event_budget_usd", "$1") is None
        hub.emit("bell", {"ring": "heard"})

    model = FakeModel([lambda: hub.listen("bell"), lambda: hub.emit("bell", {"ring": "first"})]
                      + result(screen("boot\n"), total=0.01),
                      result(screen("ding\n"), total=0.31),            # $0.30: the budget is used
                      result(screen("ding again\n"), total=0.32),
                      result(HALT, total=0.33))
    terminal = FakeTerminal(Typing("ls", meanwhile=raise_it), "exit")
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model, events=hub)
    asyncio.run(asyncio.wait_for(machine.run(), 20))
    assert kinds(model) == ["boot", "events", "events", "input"]       # and no new session
    assert '{"ring": "heard"}' in model.sessions[0][2] and "unheard" not in model.sessions[0][2]
    assert notes_of(terminal) == [EVENTS_USED, None]
    assert machine.hardware.event_budget_usd == 1.0 and len(model.sessions) == 1


def test_a_lowered_event_budget_pauses_at_once(tmp_path):
    machine, terminal = idle(tmp_path)
    machine.events.listen("bell")
    machine.event_spent = 0.2
    assert machine.change("event_budget_usd", "0.1") is None
    assert machine.events.paused and notes_of(terminal) == [EVENTS_USED]
    assert machine.view().paused == {"event_budget_usd"}
    machine.events.emit("bell", {"ring": 1})
    assert machine.events.pending() == 0                     # dropped, as when it runs out
    assert machine.change("event_budget_usd", "0") is None   # still paused, for another reason
    assert notes_of(terminal) == [EVENTS_USED, EVENTS_OFF]
    assert machine.change("event_budget_usd", "0.5") is None
    assert not machine.events.paused and notes_of(terminal)[-1] is None
    assert machine.view().paused == frozenset()


def test_a_new_tick_budget_counts_for_the_next_screen(tmp_path):
    model = FakeModel(result(screen(""), total=0.01), result(TOP, total=0.02),
                      [lambda: machine.change("tick_budget_usd", "0.1")]       # under the tick
                      + result(TOP, total=0.22),
                      [lambda: machine.change("tick_budget_usd", "$1")] + result(TOP, total=0.23),
                      result(screen("", prompt="$ "), total=0.24), result(HALT, total=0.25))
    terminal = FakeTerminal("top", Action("tick", None), KEY["x"], KEY["q"], "exit")
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)
    asyncio.run(machine.run())
    assert [form.tick for _, form in terminal.forms] == [3, 0, 3]
    assert notes_of(terminal) == [TICKS_USED, None]


def test_a_note_goes_only_when_its_own_reason_does(tmp_path):
    hub = Events()
    model = FakeModel([lambda: hub.listen("bell")] + result(screen("boot\n"), total=0.01),
                      result(TOP, total=0.02), result(TOP, total=0.32),          # a tick for $0.30
                      result(screen("", prompt="$ "), total=0.33), result(HALT, total=0.34))
    terminal = FakeTerminal("top", Action("tick", None), KEY["q"], "exit")
    hardware = Hardware(event_budget_usd=0)
    asyncio.run(Machine(tmp_path, hardware, terminal, client_factory=model, events=hub).run())
    assert notes_of(terminal) == [EVENTS_OFF, f"{EVENTS_OFF} · {TICKS_USED}", EVENTS_OFF]


def test_a_new_boot_starts_without_the_last_boots_pause(tmp_path):
    hub = Events()
    model = FakeModel([lambda: hub.listen("bell")] + result(screen("boot 1\n")),
                      screen("", prompt="", tail="<reboot/>"), screen("boot 2\n"), HALT)
    terminal = FakeTerminal("reboot", "poweroff")
    hardware = Hardware(event_budget_usd=0)
    machine = Machine(tmp_path, hardware, terminal, client_factory=model, events=hub)
    asyncio.run(machine.run())
    assert notes_of(terminal) == [EVENTS_OFF, None]          # nobody listens in the second boot
    assert machine.view().paused == frozenset()


def test_a_new_effort_runs_from_the_next_boot(tmp_path):
    seen = []

    def set_it():
        assert machine.change("effort", "high") is None
        seen.append((machine.hardware.effort, machine.running.effort,
                     machine.view().running.effort))

    model = FakeModel(screen("boot 1\n"),
                      [set_it] + result(screen("", prompt="", tail="<reboot/>")),
                      screen("boot 2\n"), HALT)
    terminal = FakeTerminal("reboot", "poweroff")
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)
    asyncio.run(machine.run())
    assert seen == [("high", "low", "low")]                  # set, but this boot keeps its own
    assert [options.effort for options in model.options] == ["low", "high"]
    assert [status for status in terminal.statuses if "effort" in status] == [
        {"model": "claude-opus-5-5", "effort": "low"},       # the bar shows what runs,
        {"model": "claude-opus-5-5", "effort": "high"}]      # and changes with the boot
    assert machine.running == machine.hardware


def test_the_bar_shows_no_effort_on_a_model_without_efforts(tmp_path):
    terminal = FakeTerminal()
    run(tmp_path, FakeModel(HALT), terminal, Hardware(model="claude-haiku-4-5", effort="high"))
    assert terminal.statuses[0] == {"model": "claude-haiku-4-5", "effort": None}


def test_a_wrong_value_changes_nothing(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="hallux")
    machine, terminal = idle(tmp_path)
    assert machine.change("tick_budget_usd", "-1") == "must be a number, 0 or more"
    assert machine.change("max_budget_usd", "0") == "must be a positive number"
    assert machine.change("effort", "turbo") == (
        "must be one of low, medium, high, xhigh, max, not 'turbo'")
    assert machine.change("status_bar", "off") == "is set when Hallux starts: edit config.toml"
    assert machine.hardware == Hardware() and machine.unsaved == {}
    assert "config" not in caplog.text and terminal.statuses == []


def test_the_same_value_is_no_change(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="hallux")
    machine, _ = idle(tmp_path, Hardware(model="claude-sonnet-5-5"), from_flags=["model"])
    assert machine.change("model", " claude-sonnet-5-5 ") is None      # Enter on a row as it was
    assert machine.change("tick_budget_usd", "$0.25") is None
    assert machine.change("max_budget_usd", "") is None
    assert machine.unsaved == {} and machine.from_flags == {"model"}   # still the flag's
    assert machine.view().unsaved == frozenset() and "config" not in caplog.text


def test_a_change_is_unsaved_and_logged_and_no_longer_the_flags(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="hallux")
    machine, _ = idle(tmp_path, Hardware(model="claude-sonnet-5-5", effort="high"),
                      from_flags=["model", "effort"])
    assert machine.view().from_flags == {"model", "effort"}
    assert machine.change("model", "claude-haiku-4-5") is None
    assert machine.change("tick_budget_usd", "1.25") is None
    assert machine.hardware == Hardware("claude-haiku-4-5", "high", tick_budget_usd=1.25)
    assert machine.unsaved == {"model": "claude-haiku-4-5", "tick_budget_usd": 1.25}
    assert machine.from_flags == {"effort"}
    assert "config: model claude-sonnet-5-5 -> claude-haiku-4-5" in caplog.text
    assert "config: tick_budget_usd 0.25 -> 1.25" in caplog.text


def test_save_writes_what_was_changed_and_nothing_else(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="hallux")
    machine, _ = idle(tmp_path, Hardware(model="claude-sonnet-5-5"), from_flags=["model"])
    machine.change("tick_budget_usd", "1.25")
    machine.change("effort", "high")
    assert machine.save() is None
    written = (tmp_path / ".hallux" / "config.toml").read_text()
    assert written == 'tick_budget_usd = 1.25\neffort = "high"\n'      # not the flag's model
    assert machine.unsaved == {} and "config saved: tick_budget_usd, effort" in caplog.text
    assert config.load(tmp_path, model="claude-sonnet-5-5") == machine.hardware
    assert machine.save() is None and caplog.text.count("config saved") == 1


def test_save_keeps_the_changes_when_it_cant_write(tmp_path):
    machine, _ = idle(tmp_path)
    (tmp_path / ".hallux").mkdir(exist_ok=True)
    (tmp_path / ".hallux" / "config.toml").write_text('effort = "turbo"\n')    # broken by now
    machine.change("tick_budget_usd", "1.25")
    assert machine.save() == ("config.toml: effort must be one of low, medium, high, xhigh, max, "
                              "not 'turbo'. Nothing saved.")
    assert machine.unsaved == {"tick_budget_usd": 1.25}
    (tmp_path / ".hallux" / "config.toml").write_text('effort = "max"\n')      # mended
    assert machine.save() is None and machine.unsaved == {}
    assert config.load(tmp_path) == Hardware(effort="max", tick_budget_usd=1.25)


def test_the_view_is_what_the_panel_shows(tmp_path):
    hardware = Hardware(max_budget_usd=2.0)
    machine, _ = idle(tmp_path, hardware, from_flags=["effort"])
    assert machine.view() == config.View(
        hardware=hardware, running=hardware, spent_boot=0.0, spent_since_refill=0.0,
        spent_ticks=None, spent_events=0.0, paused=frozenset(),
        from_flags=frozenset({"effort"}), unsaved=frozenset(),
        path=tmp_path.resolve() / ".hallux" / "config.toml")
    machine.change("fallback_model", "claude-haiku-4-5")
    view = machine.view()
    assert view.hardware.fallback_model == "claude-haiku-4-5" and view.running == hardware
    assert view.unsaved == {"fallback_model"}


def test_refill_starts_every_budget_anew(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="hallux")
    hub = Events()
    seen = {}

    def refill():
        seen["before"], seen["total"] = machine.view(), machine.spent
        seen["said"] = machine.refill()
        seen["after"], seen["total after"] = machine.view(), machine.spent
        hub.emit("bell", {"ring": "after"})

    model = FakeModel([lambda: hub.listen("bell"), lambda: hub.emit("bell", {"ring": "first"})]
                      + result(screen("boot\n"), total=0.01),
                      result(screen("ding\n"), total=0.31),            # the event: $0.30, used up
                      result(TOP, total=0.32),                         # Ctrl-L brings a program
                      result(TOP, total=0.62),                         # a tick: $0.30, used up
                      [refill] + result(TOP, total=0.63),
                      result(screen("", prompt="$ "), total=0.64),
                      result(screen("ding again\n"), total=0.65),
                      result(HALT, total=0.66))
    terminal = FakeTerminal(Key("C-l", ""), Action("tick", None), KEY["x"], KEY["q"], "exit")
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model, events=hub)
    asyncio.run(asyncio.wait_for(machine.run(), 20))

    before, after = seen["before"], seen["after"]
    assert before.paused == {"event_budget_usd", "tick_budget_usd"}
    assert (before.spent_events, before.spent_ticks) == pytest.approx((0.30, 0.30))
    assert seen["said"] == "budgets refilled"
    assert after.paused == frozenset() and (after.spent_events, after.spent_ticks) == (0.0, 0.0)
    assert after.spent_boot == before.spent_boot == pytest.approx(0.62)
    assert seen["total after"] == seen["total"] == pytest.approx(0.62)     # the bar's total stays
    assert after.unsaved == frozenset()                                    # a refill is no setting
    assert "budgets refilled: events $0.30, ticks $0.30" in caplog.text

    assert kinds(model) == ["boot", "events", "key", "tick", "keys", "keys", "events", "input"]
    assert '{"ring": "after"}' in model.sessions[0][6]                     # events arrive again
    assert [form.tick for _, form in terminal.forms] == [3, 0, 3]          # the next screen ticks
    assert notes_of(terminal) == [EVENTS_USED, f"{EVENTS_USED} · {TICKS_USED}", TICKS_USED,
                                  None]



# --- the budget per boot: hallux checks it itself, before a message goes to the AI -------------

P = "user@hallux:~$ "
CENT_USED = "budget used: $0.01 per boot · raise it: ctrl+f12"      # the panel's key
A_CENT = Hardware(max_budget_usd=0.01)


def test_the_session_gets_no_cap(tmp_path):
    model = FakeModel(HALT)
    run(tmp_path, model, FakeTerminal(), Hardware(max_budget_usd=2.0))
    assert model.options[0].max_budget_usd is None


@pytest.mark.parametrize("cap", [None, 1.0])
def test_without_a_cap_or_under_it_nothing_is_held_back(tmp_path, cap):
    model = FakeModel(result(screen("boot\n"), total=0.5), result(screen("one\n"), total=0.9),
                      result(HALT, total=0.95))
    terminal = FakeTerminal("echo one", "exit")
    machine = run(tmp_path, model, terminal, Hardware(max_budget_usd=cap))
    assert kinds(model) == ["boot", "input", "input"] and notes_of(terminal) == []
    assert terminal.prompts == [(P, ""), (P, "")] and terminal.screen == "boot\none\n"
    assert machine.view().paused == frozenset()


def test_over_its_cap_a_line_waits_until_the_cap_is_raised(tmp_path):
    model = FakeModel(result(screen("boot\n"), total=0.004),
                      result(screen("one\n"), total=0.012),              # over one cent
                      result(screen("two\n"), total=0.02), result(HALT, total=0.03))
    terminal = FakeTerminal("echo one", "echo two",                      # the second is held back
                            lambda: machine.change("max_budget_usd", "$1"),
                            "echo two", "exit")
    machine = Machine(tmp_path, A_CENT, terminal, client_factory=model)
    asyncio.run(machine.run())
    assert kinds(model) == ["boot", "input", "input", "input"]           # "echo two" went once
    assert [">echo two</input>" in message for message in model.sessions[0]] == [0, 0, 1, 0]
    assert terminal.prompts == [(P, ""), (P, ""), (P, "echo two"), (P, "")]   # the line is back
    assert notes_of(terminal) == [CENT_USED, None]
    assert terminal.screen == "boot\none\ntwo\n"


def test_over_its_cap_keys_arent_sent_and_ctrl_d_halts(tmp_path, caplog):
    from hallux.addons import Addon
    caplog.set_level(logging.INFO, logger="hallux")
    stopped = []
    lamp = Addon("lamp", "A lamp.", "It has no functions.", {}, stop=lambda: stopped.append(1))
    model = FakeModel(result(screen("boot\n"), total=0.02))              # the boot is over the cap
    terminal = FakeTerminal(Key("Tab", "ec", 2), Key("C-c", "ec", 2, keep_line=False), EOFError)
    machine = Machine(tmp_path, A_CENT, terminal, client_factory=model, addons=[lamp])
    asyncio.run(machine.run())                                           # Ctrl-D: it halts
    assert kinds(model) == ["boot"]                                      # nothing was sent
    assert terminal.prompts == [(P, ""), (P, "ec"), (P, "")]             # Tab keeps the line
    assert stopped == [1] and "halt: Ctrl-D, and the budget is used" in caplog.text
    assert notes_of(terminal) == [CENT_USED]                             # said once


def test_over_its_cap_a_password_is_neither_sent_nor_checked(tmp_path):
    model = FakeModel(result(ask("New password: ", new=True), total=0.02))
    terminal = FakeTerminal("hunter2", EOFError)
    machine = Machine(tmp_path, A_CENT, terminal, client_factory=model)
    asyncio.run(machine.run())
    assert kinds(model) == ["boot"]
    assert terminal.secret_prompts == ["New password: "] * 2             # it is asked again,
    assert terminal.prompts == [("New password: ", "")] * 2              # empty
    assert machine.passwords.pending is None                             # the store is as it was
    assert not (tmp_path / ".hallux" / "passwords.json").exists()


def test_a_message_that_is_under_way_is_finished_over_the_cap(tmp_path):
    model = FakeModel(result(screen("boot\n"), total=0.004),
                      result(screen("half an answer"), total=0.02),      # cut off, and over
                      result(screen("^C\n"), total=0.03))
    terminal = FakeTerminal("sleep 100", EOFError, ctrl_c_while_busy=[False, True])
    run(tmp_path, model, terminal, A_CENT)
    assert kinds(model) == ["boot", "input", "key"]                      # Ctrl-C's own message
    assert 'name="C-c" interrupted="yes"' in model.sessions[0][2]

    model = FakeModel(result(screen("boot\n"), total=0.004), result(NANO, total=0.02),
                      result(screen("", prompt="$ "), total=0.03))
    terminal = FakeTerminal("nano hello.txt", EOFError, EOFError)        # the full-screen app dies
    run(tmp_path, model, terminal, A_CENT)
    assert kinds(model) == ["boot", "input", "key"] and terminal.kept is None


def test_events_wait_for_the_cap_too(tmp_path):
    hub = Events()

    def raise_it():
        hub.emit("bell", {"ring": "unheard"})                # over the cap: it is dropped
        assert machine.change("max_budget_usd", "1") is None
        hub.emit("bell", {"ring": "heard"})

    model = FakeModel([lambda: hub.listen("bell")] + result(screen("boot\n"), total=0.02),
                      result(screen("ding\n"), total=0.03), result(HALT, total=0.04))
    terminal = FakeTerminal(Typing("ls", meanwhile=raise_it), "exit")
    machine = Machine(tmp_path, A_CENT, terminal, client_factory=model, events=hub)
    asyncio.run(asyncio.wait_for(machine.run(), 20))
    assert kinds(model) == ["boot", "events", "input"]
    assert '{"ring": "heard"}' in model.sessions[0][1] and "unheard" not in model.sessions[0][1]
    assert notes_of(terminal) == [CENT_USED, None]


def test_over_its_cap_a_program_stays_and_its_action_isnt_sent(tmp_path):
    model = FakeModel(result(screen("boot\n"), total=0.004), result(NANO, total=0.02),
                      result(screen("", prompt="$ "), total=0.03), result(HALT, total=0.04))
    terminal = FakeTerminal("nano hello.txt", Action("C-o", "text", ()),         # held back
                            lambda: machine.change("max_budget_usd", ""),        # no cap any more
                            Action("C-x", "text", ()), "exit")
    machine = Machine(tmp_path, A_CENT, terminal, client_factory=model)
    asyncio.run(machine.run())
    assert kinds(model) == ["boot", "input", "action", "input"]
    assert model.sessions[0][2].startswith('<action key="C-x"')         # C-o never went
    assert terminal.kept == [0] and len(terminal.forms) == 1            # nothing was shown again
    assert notes_of(terminal) == [CENT_USED, None]


def test_over_its_cap_a_program_doesnt_tick(tmp_path):
    model = FakeModel(result(screen("boot\n"), total=0.004), result(TOP, total=0.006),
                      result(TOP, total=0.02),                           # the tick: over the cap
                      result(screen("", prompt="$ "), total=0.03), result(HALT, total=0.04))
    terminal = FakeTerminal("top", Action("tick", None), Action("tick", None), KEY["x"],
                            lambda: machine.change("max_budget_usd", "1"), KEY["q"], "exit")
    machine = Machine(tmp_path, A_CENT, terminal, client_factory=model)
    asyncio.run(machine.run())
    assert kinds(model) == ["boot", "input", "tick", "keys", "input"]   # one tick, and then q
    assert model.sessions[0][3].endswith("<text>q</text></keys>")
    assert [form.tick for _, form in terminal.forms] == [3, 0]          # it came up without ticks
    assert terminal.kept == [0, 0] and notes_of(terminal) == [CENT_USED, None]


def test_raising_the_cap_takes_only_its_own_note_away(tmp_path):
    hub = Events()
    model = FakeModel([lambda: hub.listen("bell")] + result(screen("boot\n"), total=0.02),
                      result(HALT, total=0.03))
    terminal = FakeTerminal(lambda: machine.change("max_budget_usd", ""), "exit")
    hardware = Hardware(max_budget_usd=0.01, event_budget_usd=0)
    machine = Machine(tmp_path, hardware, terminal, client_factory=model, events=hub)
    asyncio.run(machine.run())
    assert notes_of(terminal) == [EVENTS_OFF, f"{EVENTS_OFF} · {CENT_USED}", EVENTS_OFF]
    assert kinds(model) == ["boot", "input"]


def test_a_refill_lets_the_boot_spend_its_cap_once_more(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="hallux")
    seen = {}

    def refill():
        seen["before"] = machine.view()
        machine.refill()
        seen["after"] = machine.view()

    model = FakeModel(result(screen("boot\n"), total=0.04), result(screen("a\n"), total=0.12),
                      result(screen("b\n"), total=0.15), result(screen("c\n"), total=0.23))
    terminal = FakeTerminal("a", "b", refill, "b", "c", "d", EOFError)
    machine = Machine(tmp_path, Hardware(max_budget_usd=0.10), terminal, client_factory=model)
    asyncio.run(machine.run())
    used = "budget used: $0.10 per boot · raise it: ctrl+f12"
    assert kinds(model) == ["boot", "input", "input", "input"]          # a, b and c; d never
    assert terminal.prompts == [(P, ""), (P, ""), (P, "b"), (P, ""), (P, ""), (P, "d")]
    assert notes_of(terminal) == [used, None, used]                     # $0.11 more: used again
    before, after = seen["before"], seen["after"]
    assert before.paused == {"max_budget_usd"} and after.paused == frozenset()
    assert (before.spent_boot, before.spent_since_refill) == pytest.approx((0.12, 0.12))
    assert (after.spent_boot, after.spent_since_refill) == pytest.approx((0.12, 0.0))
    costs = [status["cost"] for status in terminal.statuses if "cost" in status]
    assert costs == pytest.approx([0.04, 0.12, 0.15, 0.23])             # each answer's own cost
    assert "budgets refilled: events $0.00, ticks $0.00, boot $0.12" in caplog.text


def test_a_reboot_starts_the_count_at_zero(tmp_path):
    reboot = screen("", prompt="", tail="<reboot/>")
    model = FakeModel(result(screen("boot 1\n"), total=0.04), result(reboot, total=0.12),
                      result(screen("boot 2\n"), total=0.04), result(screen("ok\n"), total=0.05),
                      result(HALT, total=0.06))
    terminal = FakeTerminal("reboot", "ls", "exit")
    machine = run(tmp_path, model, terminal, Hardware(max_budget_usd=0.10))
    assert [len(session) for session in model.sessions] == [2, 3] and notes_of(terminal) == []
    assert machine.spent == pytest.approx(0.18)

    model = FakeModel(result(screen("boot 1\n"), total=0.04), result(reboot, total=0.08),
                      result(screen("boot 2\n"), total=0.12))            # over, counted from zero
    terminal = FakeTerminal(lambda: machine.refill(), "reboot", EOFError)
    machine = Machine(tmp_path, Hardware(max_budget_usd=0.10), terminal, client_factory=model)
    asyncio.run(machine.run())
    assert [len(session) for session in model.sessions] == [2, 1]
    assert notes_of(terminal) == ["budget used: $0.10 per boot · raise it: ctrl+f12"]
    assert machine.view().spent_since_refill == machine.view().spent_boot == pytest.approx(0.12)


# --- switching the model: from the next answer, in the session that runs ----------------------

OPUS, SONNET, HAIKU = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"


def on_the_bar(terminal):
    """Every model and effort the bar was given, in order."""
    return [(status["model"], status["effort"]) for status in terminal.statuses
            if "model" in status]


def test_a_new_model_answers_the_next_line(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="hallux")
    seen = []

    def set_it():
        assert machine.change("model", SONNET) is None
        seen.append((list(model.switches), machine.running.model, on_the_bar(terminal),
                     machine.view().running.model, machine.view().hardware.model))

    model = FakeModel(screen("boot\n"), screen("one\n"), screen("two\n"), screen("three\n"), HALT)
    terminal = FakeTerminal("one", set_it, "two", "three", "exit")
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)
    asyncio.run(machine.run())
    # set, and not switched yet: the session and the bar are on the old model
    assert seen == [([], OPUS, [(OPUS, "low")], OPUS, SONNET)]
    # with the next line it is switched once, before that line goes out, and never again
    assert model.switches == [(SONNET, 2)] and len(model.sessions[0]) == 5
    assert on_the_bar(terminal) == [(OPUS, "low"), (SONNET, "low")]
    assert machine.running.model == SONNET and len(model.sessions) == 1     # the same session
    assert "model: claude-opus-5-5 -> claude-sonnet-5-5" in caplog.text
    assert notes_of(terminal) == []


def test_a_model_changed_back_is_no_switch(tmp_path):
    def back_and_forth():
        machine.change("model", SONNET)
        machine.change("model", OPUS)

    model = FakeModel(screen("boot\n"), screen("one\n"), HALT)
    terminal = FakeTerminal(back_and_forth, "one", "exit")
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)
    asyncio.run(machine.run())
    assert model.switches == [] and on_the_bar(terminal) == [(OPUS, "low")]


def test_a_switch_that_fails_is_noted_and_tried_again(tmp_path, capsys, caplog):
    refused = "model not switched: Model 'claude-banana-9' not found"
    model = FakeModel(screen("boot\n"), screen("one\n"), screen("two\n"), screen("three\n"), HALT)
    model.refuses["claude-banana-9"] = "Model 'claude-banana-9' not found"
    seen = []
    look = lambda: seen.append((dict(machine.notes), machine.running.model))     # noqa: E731
    terminal = FakeTerminal(lambda: machine.change("model", "claude-banana-9"), "one", look,
                            "two", lambda: machine.change("model", SONNET), "three", look, "exit")
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)
    asyncio.run(machine.run())
    assert kinds(model) == ["boot", "input", "input", "input", "input"]     # every line went out
    assert terminal.screen == "boot\none\ntwo\nthree\n"
    assert seen == [({"model": refused}, OPUS),             # after the answer: still there
                    ({}, SONNET)]                           # a switch worked: gone at once
    assert model.switches == [("claude-banana-9", 1), ("claude-banana-9", 2), (SONNET, 3)]
    assert notes_of(terminal) == [refused, None]            # said once; gone when one works
    assert on_the_bar(terminal) == [(OPUS, "low"), (SONNET, "low")]
    assert capsys.readouterr().err.count(f"hallux: {refused}\n") == 1
    assert caplog.text.count("model not switched") == 1


def test_the_note_of_a_failed_switch_goes_with_its_model(tmp_path):
    model = FakeModel(screen("boot\n"), screen("one\n"), screen("two\n"), HALT)
    model.refuses["claude-banana-9"] = "Model 'claude-banana-9' not found"
    terminal = FakeTerminal(lambda: machine.change("model", "claude-banana-9"), "one",
                            lambda: machine.change("model", OPUS), "two", "exit")
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)
    asyncio.run(machine.run())
    assert notes_of(terminal) == ["model not switched: Model 'claude-banana-9' not found", None]
    assert model.switches == [("claude-banana-9", 1)]       # back on the one that runs: no switch


def test_after_a_reboot_the_new_model_runs_and_nothing_waits(tmp_path):
    reboot = [lambda: machine.change("model", SONNET)] + result(
        screen("", prompt="", tail="<reboot/>"))            # set while the last answer is written
    model = FakeModel(screen("boot 1\n"), reboot, screen("boot 2\n"), screen("one\n"), HALT)
    terminal = FakeTerminal("reboot", "one", "exit")
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)
    asyncio.run(machine.run())
    assert [options.model for options in model.options] == [OPUS, SONNET]
    assert model.switches == [] and on_the_bar(terminal) == [(OPUS, "low"), (SONNET, "low")]


def test_the_effort_on_the_bar_is_the_one_the_session_got(tmp_path):
    """Haiku runs without an effort. A session that started with one has it again on the next
    model; one that started on Haiku was given none, and has none after a switch either."""
    def run_through(first, *later):
        model = FakeModel(*[screen("ok\n")] * (len(later) + 1), HALT)
        keys = [key for name in later for key in (lambda name=name: machine.change("model", name),
                                                  "ls")]
        terminal = FakeTerminal(*keys, "exit")
        machine = Machine(tmp_path, Hardware(model=first, effort="high"), terminal,
                          client_factory=model)
        asyncio.run(machine.run())
        return on_the_bar(terminal), machine.view()

    bar, view = run_through(SONNET, HAIKU, OPUS)
    assert bar == [(SONNET, "high"), (HAIKU, None), (OPUS, "high")]
    bar, view = run_through(HAIKU, SONNET)
    assert bar == [(HAIKU, None), (SONNET, None)]
    assert view.hardware.effort == "high" and view.running.model_effort is None



# --- a program whose ticks a budget stopped ticks again when the budget allows it -------------

def test_a_paused_program_ticks_again_when_the_tick_budget_is_raised(tmp_path):
    model = FakeModel(result(screen(""), total=0.01), result(TOP, total=0.02),
                      result(TOP, total=0.32),                           # a tick for $0.30
                      result(screen("", prompt="$ "), total=0.33), result(HALT, total=0.34))
    terminal = FakeTerminal("top", Action("tick", None),
                            lambda: machine.change("tick_budget_usd", "1"), KEY["q"], "exit")
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model)
    asyncio.run(machine.run())
    assert [form.tick for _, form in terminal.forms] == [3, 0]           # paused on the screen
    assert terminal.ticks == [3]                         # the tick the program asked for
    assert notes_of(terminal) == [TICKS_USED, None]


def test_a_program_ticks_again_when_the_cap_that_stopped_it_is_raised(tmp_path):
    model = FakeModel(result(screen("boot\n"), total=0.004), result(TOP, total=0.02),   # over
                      result(screen("", prompt="$ "), total=0.03), result(HALT, total=0.04))
    terminal = FakeTerminal("top", lambda: machine.change("max_budget_usd", ""), KEY["q"], "exit")
    machine = Machine(tmp_path, A_CENT, terminal, client_factory=model)
    asyncio.run(machine.run())
    assert [form.tick for _, form in terminal.forms] == [0] and terminal.ticks == [3]
    assert notes_of(terminal) == [CENT_USED, None]


def test_a_cap_lowered_under_a_ticking_program_stops_its_ticks_until_it_is_raised(tmp_path):
    model = FakeModel(result(screen("boot\n"), total=0.004), result(TOP, total=0.006),
                      result(screen("", prompt="$ "), total=0.007), result(HALT, total=0.008))
    terminal = FakeTerminal("top", lambda: machine.change("max_budget_usd", "0.005"),
                            Action("tick", None),                        # held back: no ticks
                            lambda: machine.change("max_budget_usd", "1"), KEY["q"], "exit")
    machine = Machine(tmp_path, A_CENT, terminal, client_factory=model)
    asyncio.run(machine.run())
    assert [form.tick for _, form in terminal.forms] == [3]
    assert terminal.kept == [0] and terminal.ticks == [3]
    assert kinds(model) == ["boot", "input", "keys", "input"]            # the tick never went


def test_with_both_budgets_used_up_ticks_wait_for_both(tmp_path):
    cap_used = "budget used: $0.30 per boot · raise it: ctrl+f12"

    def play(*in_the_panel):
        model = FakeModel(result(screen(""), total=0.01), result(TOP, total=0.02),
                          result(TOP, total=0.32),                       # the tick uses up both
                          result(screen("", prompt="$ "), total=0.33), result(HALT, total=0.34))
        terminal = FakeTerminal("top", Action("tick", None), *in_the_panel, KEY["q"], "exit")
        nonlocal machine
        machine = Machine(tmp_path, Hardware(max_budget_usd=0.30), terminal, client_factory=model)
        asyncio.run(machine.run())
        return terminal

    machine = None
    seen = []
    terminal = play(lambda: machine.change("tick_budget_usd", "1"),
                    lambda: seen.append((machine.terminal.ticks, dict(machine.notes))),
                    lambda: machine.change("max_budget_usd", "1"))
    assert seen == [(None, {"max_budget_usd": cap_used})]     # one raised: no ticks, its note stays
    assert terminal.ticks == [3]                              # both raised: it ticks again
    assert notes_of(terminal) == [cap_used, f"{cap_used} · {TICKS_USED}", cap_used, None]

    terminal = play(lambda: machine.refill())                 # the button does both at once
    assert terminal.ticks == [3]
    assert notes_of(terminal) == [cap_used, f"{cap_used} · {TICKS_USED}", TICKS_USED, None]


def test_a_program_that_asked_for_no_tick_gets_none(tmp_path):
    model = FakeModel(result(screen("boot\n"), total=0.004), result(NANO, total=0.02),
                      result(screen("", prompt="$ "), total=0.03), result(HALT, total=0.04))
    terminal = FakeTerminal("nano hello.txt", lambda: machine.change("max_budget_usd", ""),
                            Action("C-x", "text", ()), "exit")
    machine = Machine(tmp_path, A_CENT, terminal, client_factory=model)
    asyncio.run(machine.run())
    assert terminal.ticks is None

def test_an_answers_cost_is_on_the_bar_before_the_answer_ends(tmp_path):
    """The end of an answer may wait for the panel, and the panel shows what was spent."""
    class Watching(FakeTerminal):
        costs_at_the_end = ()

        @contextlib.asynccontextmanager
        async def busy(self, interrupt, activity="thinking…"):
            try:
                yield
            finally:
                costs = [status["cost"] for status in self.statuses if "cost" in status]
                self.costs_at_the_end += (costs[-1] if costs else None,)

    model = FakeModel(result(screen("boot\n"), total=0.07), result(screen("ok\n"), total=0.09),
                      result(HALT, total=0.1))
    terminal = Watching("ls", "exit")
    machine = run(tmp_path, model, terminal)
    assert terminal.costs_at_the_end == pytest.approx((0.07, 0.09, 0.1))
    assert machine.spent == pytest.approx(0.1) and machine.last_turn_cost == pytest.approx(0.01)

def test_the_app_tells_the_machine_which_settings_came_from_flags(tmp_path, monkeypatch):
    from hallux import app, machine, terminal
    given = {}

    class Recorded:
        view = change = save = refill = staticmethod(lambda *args: None)

        def __init__(self, root, hardware, terminal, **more):
            given.update(more, hardware=hardware, machine=self)

        async def run(self):
            pass

    class Keyboard:
        power_cut = count_ctrl_c = staticmethod(lambda: None)

        def __init__(self, bar, **more):
            given["bar"] = bar

        def set_panel(self, panel):
            given["panel"] = panel

    class Tty:
        isatty, write, flush = (lambda self: True), (lambda self, text: None), (lambda self: None)

    (tmp_path / ".hallux").mkdir()
    (tmp_path / ".hallux" / "config.toml").write_text('addons = []\neffort = "max"\n')
    monkeypatch.setattr(machine, "Machine", Recorded)
    monkeypatch.setattr(terminal, "Terminal", Keyboard)
    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(sys, "stdout", Tty())
    monkeypatch.setattr(sys, "argv", ["hallux", str(tmp_path), "--model", "claude-sonnet-5-5"])
    try:
        app.main()
    finally:
        for handler in list(app.log.handlers):               # main() logs into the world's folder
            app.log.removeHandler(handler)
            handler.close()
    assert given["from_flags"] == {"model"}                  # the effort is the file's
    assert given["hardware"] == Hardware("claude-sonnet-5-5", "max", addons=())
    panel = given["panel"]                                   # and the terminal gets the panel:
    assert [tab.title for tab in panel.tabs] == ["Config"]   # one tab, around the machine,
    assert panel.tabs[0].view is Recorded.view and panel.bar is given["bar"]
    assert panel.power_cut is Keyboard.power_cut and panel.ctrl_c is Keyboard.count_ctrl_c
