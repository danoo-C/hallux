"""The scripted runner and the reboot check, with a fake model."""
import asyncio

from test_machine import FakeModel, result, screen

from hallux.config import Hardware
from hallux.machine import Machine
from hallux.script import (CHECKS, REBOOT_SCRIPT, SETUP, ScriptEnded, ScriptTerminal, plain,
                           reboot_report)


def run_lines(tmp_path, model, lines):
    terminal = ScriptTerminal(lines)
    try:
        asyncio.run(Machine(tmp_path, Hardware(), terminal, client_factory=model).run())
    except ScriptEnded:                                 # as run_script() does
        pass
    return terminal


def test_a_script_types_commands_and_keys(tmp_path):
    model = FakeModel(result(screen("Debian GNU/Linux 12\n"), total=0.05,
                             tools=[("memory_edit", {"old": "", "new": "x"})]),
                      result(screen("\x1b[34mfib.py\x1b[0m\n"), total=0.07),
                      screen("", tail=""),
                      screen("logout\n", prompt="", tail="<halt/>"))
    terminal = run_lines(tmp_path, model, ["# a comment", "ls --color", "@key C-c"])
    boot, ls, ctrl_c, eof = terminal.records
    assert (boot.typed, boot.output, boot.tools) == ("(boot)", "Debian GNU/Linux 12\n", ["remembering…"])
    assert (ls.typed, ls.output, ls.prompt) == ("ls --color", "fib.py\n", "user@hallux:~$ ")
    assert round(boot.cost, 2) == 0.05 and round(ls.cost, 2) == 0.02
    assert model.sessions[0][2].startswith('<key name="C-c" ')
    assert eof.typed == "@key C-d"                      # the script ran out: Ctrl-D halts


def test_a_script_types_a_password_without_showing_it(tmp_path):
    model = FakeModel(screen("", prompt="$ "),
                      '<screen>\n</screen><prompt secret="root">Password: </prompt>',
                      screen("", prompt="# "),
                      screen("logout\n", prompt="", tail="<halt/>"))
    echoed = []
    terminal = ScriptTerminal(["su", "hunter2"], echo=echoed.append)
    asyncio.run(Machine(tmp_path, Hardware(), terminal, client_factory=model).run())
    assert [r.typed for r in terminal.records] == ["(boot)", "su", "(password)", "@key C-d"]
    assert model.sessions[0][2].startswith('<input secret="root" match="unset" ')
    assert "".join(echoed) == "$ su\nPassword: \nlogout\n"       # the transcript: no password


def test_a_script_ends_even_if_the_machine_will_not_halt(tmp_path):
    model = FakeModel(*[screen(">>> ", prompt=">>> ")] * 10)
    terminal = run_lines(tmp_path, model, ["python3"])
    assert [r.typed for r in terminal.records].count("@key C-d") == 3


def test_the_reboot_check_passes_when_everything_survives(tmp_path):
    identity = {"hostname": "hallux", "uname -r": "6.1.0-25-amd64",
                "head -2 /etc/os-release": 'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"',
                "cat note.txt": "remember me", "cat nope.txt": "OOPS: cat: nope.txt: gone",
                "cowsay moo": "< moo >", "hallux": "1. every error message starts with OOPS:"}
    replies = [screen("booting\n", prompt="$ ")]
    replies += [screen("", prompt="check> ")] * len(SETUP)
    replies += [screen(identity[c] + "\n", prompt="check> ") for c, _ in CHECKS]
    replies += [screen("rebooting\n", prompt="", tail="<reboot/>"), screen("booting\n", prompt="check> ")]
    replies += [screen(identity[c] + "\n", prompt="check> ") for c, _ in CHECKS]
    replies += [screen("logout\n", prompt="", tail="<halt/>")]
    terminal = run_lines(tmp_path, FakeModel(*replies), REBOOT_SCRIPT)
    report, passed = reboot_report(terminal.records)
    assert passed, report
    assert [r.typed for r in terminal.records].count("(reboot)") == 1


def test_the_reboot_check_catches_drift(tmp_path):
    replies = [screen("", prompt="check> ")] * (1 + len(SETUP))          # boot and setup
    replies += [screen("hallux\n" if c == "hostname" else "OOPS\n", prompt="check> ") for c, _ in CHECKS]
    replies += [screen("", prompt="", tail="<reboot/>"), screen("", prompt="user@hallux:~$ ")]
    replies += [screen("kitty\n" if c == "hostname" else "OOPS\n", prompt="user@hallux:~$ ")
                for c, _ in CHECKS]
    replies += [screen("", prompt="", tail="<halt/>")]
    terminal = run_lines(tmp_path, FakeModel(*replies), REBOOT_SCRIPT)
    report, passed = reboot_report(terminal.records)
    assert not passed
    assert "FAILED    hostname" in report and "after:  kitty" in report
    assert "FAILED    the prompt survives" in report


def test_plain_drops_colors():
    assert plain("\x1b[1;32muser\x1b[0m\r\n\x1b]0;title\x07x") == "user\nx"



def test_a_new_machine_arrives_in_one_answer(tmp_path):
    """First boot: the memory and the key files come with the boot screen, no tool calls."""
    first_boot = (screen("Debian GNU/Linux 12\n", tail="<cwd>/home/user</cwd>")
                  + "<memory>\n# hallux memory\n## Machine\n- Debian 12\n</memory>"
                  + '<file path="/etc/hostname">hallux\n</file>'
                  + '<file path="/home/user/.bashrc">PS1="$ "\n</file>')
    later = screen("", tail='<memory>\nwiped\n</memory><file path="note.txt" append="yes">b\n</file>')
    terminal = run_lines(tmp_path, FakeModel(first_boot, later, screen("", prompt="", tail="<halt/>")),
                         ["echo b >> note.txt"])
    assert (tmp_path / ".hallux" / "memory.md").read_text() == "# hallux memory\n## Machine\n- Debian 12\n"
    assert (tmp_path / "etc" / "hostname").read_text() == "hallux\n"
    assert (tmp_path / "home" / "user" / ".bashrc").read_text() == 'PS1="$ "\n'
    assert (tmp_path / "home" / "user" / "note.txt").read_text() == "b\n"   # relative to the cwd
    assert terminal.records[0].tools == []                       # the boot needed no tools



def test_the_reboot_check_fails_if_the_machine_never_rebooted(tmp_path):
    """Live: `reboot` without sudo was refused, and the "after" checks ran in the same boot."""
    replies = [screen("", prompt="check> ")] * (1 + len(SETUP))
    replies += [screen("OOPS\n", prompt="check> ")] * len(CHECKS)
    replies += [screen("Call to Reboot failed: Interactive authentication required.\n",
                       prompt="check> ")]
    replies += [screen("OOPS\n", prompt="check> ")] * len(CHECKS)
    replies += [screen("", prompt="", tail="<halt/>")]
    terminal = run_lines(tmp_path, FakeModel(*replies), REBOOT_SCRIPT)
    report, passed = reboot_report(terminal.records)
    assert not passed and "FAILED    the machine rebooted" in report


def test_a_script_cant_be_interrupted():
    assert ScriptTerminal(["ls"]).interrupt_prompt() is False                 # a script gets no events
