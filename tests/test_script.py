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
    assert ScriptTerminal(["ls"]).refresh() is None                           # and has no panel


def test_a_status_before_there_is_a_record_is_dropped():
    terminal = ScriptTerminal(["ls"])
    terminal.set_status(model="claude-opus-5-5", effort="low")       # the bar, as a boot starts
    assert terminal.records == []


def test_a_scripted_run_halts_at_its_cap(tmp_path, capsys):
    model = FakeModel(result(screen("boot\n", prompt="$ "), total=0.004),
                      result(screen("one\n", prompt="$ "), total=0.02))    # over one cent
    echoed = []
    terminal = ScriptTerminal(["echo one", "echo two", "echo three"], echo=echoed.append)
    hardware = Hardware(max_budget_usd=0.01)
    asyncio.run(Machine(tmp_path, hardware, terminal, client_factory=model).run())
    assert [r.typed for r in terminal.records] == ["(boot)", "echo one"]
    assert terminal.lines == ["echo two", "echo three"]                  # never typed,
    assert "".join(echoed) == "boot\n$ echo one\none\n"                  # and none glued on
    assert len(model.sessions[0]) == 2
    # once, and without the panel's key: a script has no keyboard to press it on
    assert capsys.readouterr().err.count("hallux: budget used: $0.01 per boot\n") == 1


def test_a_scripted_run_halts_at_its_cap_in_a_full_screen_program(tmp_path, capsys):
    nano = ('<screen>\n  GNU nano 7.2\n</screen><prompt></prompt>'
            '<form keys="C-x"><editor id="text" top="2"/></form>')
    model = FakeModel(result(screen("boot\n", prompt="$ "), total=0.004), result(nano, total=0.02))
    terminal = ScriptTerminal(["nano", "@action C-x", "ls"])
    hardware = Hardware(max_budget_usd=0.01)
    asyncio.run(Machine(tmp_path, hardware, terminal, client_factory=model).run())
    assert [r.typed for r in terminal.records] == ["(boot)", "nano"]
    assert "GNU nano 7.2" in terminal.records[1].output                  # its screen is recorded
    assert terminal.lines == ["@action C-x", "ls"] and len(model.sessions[0]) == 2
    assert capsys.readouterr().err.count("budget used") == 1


# --- the jobs of the addons' agents in a scripted run --------------------------------------

import pytest  # noqa: E402
from test_agents import MUSIC, StandIn  # noqa: E402
from test_machine import PLAYER, PLAYS, block, kinds, served  # noqa: E402,F401

from hallux import addons  # noqa: E402
from hallux.addons import Events  # noqa: E402
from hallux.script import JobsRun, run_script, summary  # noqa: E402

HALT = screen("", prompt="", tail="<halt/>")


def scripted(tmp_path, served, lines, answers, ends_after=None, hear=()):
    """Run these lines with run_script(). The AI calls the fake addon's compose while it
    answers the first line; the job's stand-in worker ends well `ends_after` seconds after
    it was made, or never. From its boot on the AI listens to the addons in `hear`.
    Returns what run_script returns, the transcript and the fake model."""
    def compose(spawn, request: str, folder: str) -> dict:
        """Have the composer write a song."""
        return {"pid": spawn(request, folder)}

    studio = addons.Addon("music", "A sound card.", "the manual", {"compose": compose},
                          has_events=True, agent=MUSIC.agent)
    gate, hub = asyncio.Event(), Events()

    async def the_ai_calls_compose():
        await served["music"]["compose"].handler({"request": "a song", "folder": "/tmp"})

    def worker(job):
        if ends_after is not None:
            asyncio.get_running_loop().call_later(ends_after, gate.set)
        return StandIn(job, (("wait", gate),))          # it costs $0.21 when it ends well

    first, *rest = answers
    model = FakeModel([lambda: [hub.listen(name) for name in hear]]
                      + result(screen("boot\n"), total=0.05),
                      [the_ai_calls_compose] + result(first, total=0.05),
                      *[result(answer, total=0.05) for answer in rest], result(HALT, total=0.05))
    echoed = []
    records, jobs = asyncio.run(asyncio.wait_for(run_script(
        tmp_path, Hardware(), lines, echoed.append, addons=[studio], events=hub,
        client_factory=model, worker_factory=worker), 20))
    return records, jobs, "".join(echoed), model


def test_wait_jobs_holds_a_script_until_the_job_ends_and_no_longer(tmp_path, served):
    records, jobs, transcript, model = scripted(
        tmp_path, served, ["compose", "@wait jobs 5", "ls"],
        [screen("[1] 30001\n"), screen("[1]+  Done\nnotes.md\n")], ends_after=0.3)
    assert [record.typed for record in records] == ["(boot)", "compose", "@wait jobs 5", "ls",
                                                    "@key C-d"]
    waited = records[2]
    assert 0.25 < waited.seconds < 2 and waited.output == ""        # not its five seconds
    assert "user@hallux:~$ [@wait jobs 5]\n" in transcript and "still running" not in transcript
    done = ('{"event": "job", "pid": 30001, "agent": "composer", "state": "done", "files": [], '
            '"seconds": 0}')
    assert model.sessions[0][2].startswith(block(("music", done)) + "<input ")    # the next line
    assert jobs == JobsRun(count=1, cost=0.21)
    assert [round(record.cost, 2) for record in records] == [0.05, 0, 0, 0, 0]   # in no line


def test_wait_jobs_gives_up_after_its_seconds_and_the_transcript_says_so(tmp_path, served):
    records, jobs, transcript, model = scripted(
        tmp_path, served, ["compose", "@wait jobs 0.2", "ls"],
        [screen("[1] 30001\n"), screen("notes.md\n")])              # the job never ends
    waited = records[2]
    assert 0.2 <= waited.seconds < 2
    assert waited.output == "[1 job still running after 0.2 s]\n" and waited.output in transcript
    assert model.sessions[0][2].startswith("<input ")               # nothing has ended
    assert jobs == JobsRun(count=1, cost=0.07)          # the halt killed it, and it is counted


def test_after_a_wait_a_listening_ai_hears_of_the_job_before_the_next_line(tmp_path, served):
    records, jobs, transcript, model = scripted(
        tmp_path, served, ["compose", "@wait jobs", "ls"],          # as long as it takes
        [screen("[1] 30001\n"), screen("[1]+  Done\n"), screen("notes.md\n")],
        ends_after=0.2, hear=["music"])
    assert kinds(model) == ["boot", "input", "events", "input", "key"]
    assert records[2].typed == "@wait jobs" and records[2].output == "[1]+  Done\n"
    assert model.sessions[0][3].startswith("<input ") and jobs.cost == 0.21


def test_a_wait_in_a_full_screen_program_wakes_it_when_the_job_has_ended(tmp_path, served):
    records, jobs, transcript, model = scripted(
        tmp_path, served, ["player", "@wait jobs 5", "@action q"],
        [PLAYER, PLAYS, screen("stopped\n")], ends_after=0.2, hear=["music"])
    assert kinds(model) == ["boot", "input", "events", "action", "key"]
    assert "playing night.score" in transcript and "[@wait jobs 5]\n" in transcript


@pytest.mark.parametrize("jobs, shown", [
    (JobsRun(), "5 round trips, 3s, $0.12"),            # no job: as it always was
    (JobsRun(1, 0.21), "5 round trips, 3s, $0.33 (1 job: $0.21)"),
    (JobsRun(2, 1.3), "5 round trips, 3s, $1.42 (2 jobs: $1.30)"),
    (JobsRun(1, 0.0), "5 round trips, 3s, $0.12 (1 job: $0.00)"),
])
def test_the_summary_counts_the_jobs_and_their_cost(jobs, shown):
    from hallux.script import Record
    records = [Record("(boot)", seconds=1.0, cost=0.05), Record("compose", cost=0.04),
               Record("@wait jobs 180", seconds=2.0), Record("ls", cost=0.03),
               Record("(reboot)", seconds=0.2), Record("@key C-d")]
    line = summary(records, Hardware(), jobs)
    assert line.startswith("opus 5.5 · low — boot 1.0s (0 tool calls), reboot 0.2s (0 tool calls)")
    assert line.endswith(f" — {shown}") and summary(records, Hardware()).endswith("$0.12")


# --- job control in a scripted run -----------------------------------------------------------

def test_a_scripted_run_keeps_no_screen_so_fg_has_the_program_drawn_again(tmp_path):
    """A transcript has no screen to keep. The AI is told so at its <resume>, and draws."""
    nano = ('<screen>\n  GNU nano 7.2\n</screen><prompt></prompt>'
            '<form keys="C-x"><editor id="text" top="2"/></form>')
    stopped = screen("\n[1]+  Stopped                 nano\n", tail='<suspend job="1"/>')
    model = FakeModel(screen("boot\n"), nano, stopped,
                      '<screen>\n</screen><prompt></prompt><resume job="1"/>', nano,
                      screen("", prompt="$ "), screen("logout\n", prompt="", tail="<halt/>"))
    terminal = run_lines(tmp_path, model, ["nano", "@action C-z", "fg", "@action C-x"])
    kinds = [message[1:].split(" ")[0] for message in model.sessions[0]]
    assert kinds == ["boot", "input", "action", "input", "gone", "action", "key"]
    assert [record.typed for record in terminal.records] == [
        "(boot)", "nano", "@action C-z", "fg", "@action C-x", "@key C-d"]
    assert "[1]+  Stopped" in terminal.records[2].output
    assert "GNU nano 7.2" in terminal.records[3].output                  # drawn again, under fg
