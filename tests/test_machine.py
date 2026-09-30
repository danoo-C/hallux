"""The machine loop, driven by a scripted keyboard and a fake model."""
import asyncio

import pytest
from claude_agent_sdk import ResultMessage

from hallux.config import Hardware
from hallux.machine import SYSTEM_PROMPT, Key, Machine
from hallux.protocol import Action, FieldState


def result(text, *, error=False):
    return ResultMessage(subtype="error_during_execution" if error else "success",
                         duration_ms=1, duration_api_ms=1, is_error=error, num_turns=1,
                         session_id="s", result=text, total_cost_usd=0.001)


class FakeModel:
    """Hands out scripted results, one per message, across as many sessions as it's asked for."""

    def __init__(self, *results):
        self.results = [r if isinstance(r, ResultMessage) else result(r) for r in results]
        self.sessions = []                   # the messages each session received
        self.options = []

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
        yield self.model.results.pop(0)

    async def interrupt(self):
        pass


class FakeTerminal:
    """Types the scripted keys; records what was shown."""

    def __init__(self, *keys):
        self.keys = list(keys)
        self.screen = ""
        self.prompts = []                    # (prompt, restored line) per read

    async def read_line(self, prompt, default=""):
        self.prompts.append((prompt, default))
        key = self.keys.pop(0)
        if isinstance(key, type) and issubclass(key, BaseException):
            raise key
        return key

    def write(self, text):
        self.screen += text

    def size(self):
        return 100, 30

    # block mode: forms are recorded, actions come from the same script as the keys
    forms = None
    ended = 0
    texts = None

    async def show_form(self, screen, form):
        self.forms = (self.forms or []) + [(screen, form)]
        self.texts = {f.id: f.text for f in form.fields if f.text is not None} | (self.texts or {})

    async def next_action(self):
        key = self.keys.pop(0)
        if isinstance(key, type) and issubclass(key, BaseException):
            raise key
        return key

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
    assert boot.startswith('<boot cwd="/" time="') and 'cols="100" rows="30"' in boot
    assert boot.endswith("></boot>")
    assert ls.startswith("<input ") and ls.endswith(">ls</input>")
    assert eof.startswith("<eof ")


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
                      screen("broken reply without a prompt"),       # keeps ">>> "
                      screen("", prompt="", tail="<halt/>"))
    model.results[3] = result("broken reply without a prompt")
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
    _, sigint, ctrl_l, _ = model.sessions[0]
    assert sigint.startswith("<signal ") and sigint.endswith(">SIGINT</signal>")
    assert ctrl_l.startswith('<key name="C-l" ') and ctrl_l.endswith(">ls -l</key>")
    assert terminal.screen == "\x1b[H\x1b[2J"
    assert terminal.prompts[2] == ("user@hallux:~$ ", "ls -l")      # the typed line comes back


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
