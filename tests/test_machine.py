"""The machine loop, driven by a scripted keyboard and a fake model."""
import asyncio
import contextlib

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent, ToolUseBlock

from hallux.config import Hardware
from hallux.machine import SYSTEM_PROMPT, Key, Machine
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
            yield message

    async def interrupt(self):
        self.model.interrupts += 1


class FakeTerminal:
    """Types the scripted keys; records what was shown."""

    status_bar = False

    def __init__(self, *keys, ctrl_c_while_busy=()):
        self.keys = list(keys)
        self.screen = ""
        self.prompts = []                    # (prompt, restored line) per read
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

    async def read_line(self, prompt, default=""):
        self.prompts.append((prompt, default))
        key = self.keys.pop(0)
        if isinstance(key, type) and issubclass(key, BaseException):
            raise key
        return key

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
