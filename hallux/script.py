"""Driving the machine from a script instead of a keyboard: tests, benchmarks, the reboot check.

A script has one entry per line:

    ls -la          a command: typed, then Enter (at a password prompt: the password)
    @key C-c        a key for the machine (C-c, Tab, C-l, ...)
    @action C-x     an action key in a full-screen program (block mode)
    @wait jobs 180  go on when no addon agent's job runs, or after that many seconds
    # a comment     skipped

When the script runs out, Ctrl-D is sent until the machine halts. The transcript is what
the screen would show, without colors.
"""
from __future__ import annotations

import asyncio
import contextlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Callable, Sequence

from hallux.addons import Addon, Events
from hallux.config import Hardware
from hallux.machine import Interrupted, Key, Machine
from hallux.protocol import Action, Form, plain
from hallux.statusbar import short_model

LINE_ENDING_KEYS = ("C-c", "C-d", "C-z", "C-\\")
WAIT = re.compile(r"@wait jobs(?:\s+(\d+(?:\.\d+)?))?\s*")     # the seconds can be left out
WAIT_STEP = 0.05                                        # how often a wait looks at the jobs


@dataclass
class Record:
    """One round trip: what was typed, at which prompt, and what came back."""
    typed: str
    prompt: str = ""
    output: str = ""
    seconds: float = 0.0
    cost: float = 0.0
    tools: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class JobsRun:
    """The addon agents' jobs of a scripted run, for its summary: how many were started, and
    what they cost together. Their cost is in no Record: a job belongs to no line."""
    count: int = 0
    cost: float = 0.0


class ScriptEnded(Exception):
    """The script ran out and the machine wouldn't halt."""


class ScriptTerminal:
    """A terminal whose keyboard is a script. Implements hallux.machine.Terminal."""

    status_bar = False
    streams = False                                     # a transcript gains nothing from it
    attended = False                                    # nobody can raise a budget: the machine
                                                        # halts where it would hold a line back

    def __init__(self, lines: list[str], echo: Callable[[str], None] = lambda text: None,
                 cols: int = 100, rows: int = 30) -> None:
        self.lines = [line for line in lines if line.strip() and not line.lstrip().startswith("#")]
        self.echo, self.cols, self.rows = echo, cols, rows
        self.records: list[Record] = []
        self.spent = 0.0
        self.eofs = 0
        self.jobs_running: Callable[[], int] = lambda: 0    # run_script() says how to ask

    def _new_record(self, typed: str, prompt: str = "") -> None:
        self.records.append(Record(typed=typed, prompt=prompt))

    async def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    async def read_line(self, prompt: str, default: str = "") -> str | Key | Interrupted:
        if self._waits():
            await self._wait_for_jobs(prompt)
            return Interrupted(default, len(default))   # the machine looks for what ended:
        return self._next(prompt, default)              # it may go out before the next line

    def _waits(self) -> bool:
        return bool(self.lines) and WAIT.fullmatch(self.lines[0].strip()) is not None

    async def _wait_for_jobs(self, prompt: str = "") -> None:
        """`@wait jobs 180`: the script goes on when no job runs, or after that many seconds.
        Without it a script would run out while a job works, the machine would halt, and the
        job would be killed. Without the seconds it waits as long as the jobs run, which
        their own timeout bounds."""
        line = self.lines.pop(0).strip()
        seconds = WAIT.fullmatch(line).group(1)
        self.echo(plain(prompt) + f"[{line}]\n")
        self._new_record(line, prompt)
        started = time.monotonic()
        while self.jobs_running() and (seconds is None
                                       or time.monotonic() - started < float(seconds)):
            await asyncio.sleep(WAIT_STEP)
        self.records[-1].seconds += time.monotonic() - started
        if left := self.jobs_running():
            self.write(f"[{left} job{'s' * (left > 1)} still running after {seconds} s]\n")

    def interrupt_prompt(self) -> bool:
        return False                                    # a script gets no events

    async def read_secret(self, prompt: str) -> str | Key:
        return self._next(prompt, secret=True)          # the next line is the password

    def _next(self, prompt: str, default: str = "", secret: bool = False) -> str | Key:
        if not self.lines:
            self.eofs += 1
            if self.eofs > 3:
                raise ScriptEnded
            self._new_record("@key C-d", prompt)
            return Key("C-d", "", keep_line=False)
        line = self.lines.pop(0)
        shown = f"[{line}]" if line.startswith("@") else "" if secret else line
        self.echo(plain(prompt) + shown + "\n")
        if line.startswith("@key "):
            self._new_record(line, prompt)
            name = line[5:].strip()
            return Key(name, default, len(default), keep_line=name not in LINE_ENDING_KEYS)
        self._new_record("(password)" if secret else line, prompt)   # not in the transcript
        return default + line

    def write(self, text: str) -> None:
        text = plain(text)
        if not self.records:
            self._new_record("(boot)")
        self.records[-1].output += text
        self.echo(text)

    def retract(self, text: str) -> None:
        pass

    def size(self) -> tuple[int, int]:
        return self.cols, self.rows

    @contextlib.asynccontextmanager
    async def busy(self, interrupt: Callable[[], None],
                   activity: str = "thinking…") -> AsyncIterator[None]:
        if activity == "booting…":
            self._new_record("(reboot)" if self.records else "(boot)")
        started = time.monotonic()
        try:
            yield
        finally:
            self.records[-1].seconds += time.monotonic() - started

    def set_status(self, **changes: object) -> None:
        if not self.records:                            # the bar is set as a boot starts,
            return                                      # before there is anything to record
        record = self.records[-1]
        if "activity" in changes and "tools" in changes:
            record.tools.append(str(changes["activity"]))
        if "cost" in changes:
            record.cost += float(changes["cost"]) - self.spent
            self.spent = float(changes["cost"])
        if changes.get("error"):
            record.error = str(changes["error"])

    # block mode: the screen is recorded, actions come from the script
    async def show_form(self, screen: str, form: Form, patch=None) -> None:
        if patch:
            screen = "".join(f"[rows from {first}]\n" + "\n".join(rows) + "\n" for first, rows in patch)
        footer = f"\n{form.footer}" if form.footer else ""
        fields = ", ".join(f"<{f.kind} {f.id}>" for f in form.fields)
        self.write(f"{screen}{footer}\n[full screen: {fields}; keys {' '.join(form.keys)}]\n")

    async def next_action(self) -> Action:
        if self._waits():
            await self._wait_for_jobs()
            return Action(key="wake", focus=None)       # the machine looks for what ended
        if self.lines and self.lines[0].startswith("@action "):
            line = self.lines.pop(0)
            self._new_record(line)
            return Action(key=line[8:].strip(), focus=None)
        raise EOFError("the script has no action for this screen")

    def keep_form(self, tick: float | None = None) -> None:
        pass

    def set_tick(self, seconds: float) -> None:
        pass

    def wake_form(self) -> bool:
        return False                                    # a script's program waits for nobody

    async def end_form(self) -> None:
        pass

    def field_text(self, id: str) -> str:
        raise ValueError(f"no field {id!r}: scripts can't type into fields")

    def field_saved(self, id: str) -> None:
        pass


async def run_script(root: Path, hardware: Hardware, lines: list[str],
                     echo: Callable[[str], None] = lambda text: None,
                     addons: Sequence[Addon] = (), events: Events | None = None,
                     **more: object) -> tuple[list[Record], JobsRun]:
    """Run the script on a machine of its own. Returns the records, and the jobs' numbers
    beside them. `more` is the machine's: the tests hand in a pretend model."""
    terminal = ScriptTerminal(lines, echo)
    machine = Machine(root, hardware, terminal, addons=addons, events=events, **more)
    terminal.jobs_running = lambda: len(machine.jobs.running())
    try:
        await machine.run()
    except ScriptEnded:
        pass
    return terminal.records, JobsRun(machine.jobs.started, machine.jobs.spent)


def summary(records: list[Record], hardware: Hardware, jobs: JobsRun = JobsRun()) -> str:
    boots = [r for r in records if r.typed in ("(boot)", "(reboot)")]
    parts = [f"{r.typed[1:-1]} {r.seconds:.1f}s ({len(r.tools)} tool calls)" for r in boots]
    trips = [r for r in records if not r.typed.startswith("@wait")]      # a wait is none
    total = sum(r.seconds for r in records)
    cost = sum(r.cost for r in records) + jobs.cost     # the main session's, and the jobs'
    of_jobs = f" ({jobs.count} job{'s' * (jobs.count > 1)}: ${jobs.cost:.2f})" * bool(jobs.count)
    return (f"{short_model(hardware.model)} · {hardware.model_effort or 'default'} — "
            + ", ".join(parts) + f" — {len(trips)} round trips, {total:.0f}s, "
            f"${cost:.2f}{of_jobs}")


# ---------------------------------------------------------------- the reboot check

SETUP = ['hallux my prompt is "check> "',
         "hallux every error message starts with OOPS:",
         "hallux user can use sudo without a password",    # a prompt would eat the next line
         "echo remember me > note.txt",
         "sudo apt install -y cowsay"]
# (command, what must hold): "same" output before and after the reboot, the error "rule"
# still applies, or the installed program still "works".
CHECKS = [("hostname", "same"), ("uname -r", "same"), ("head -2 /etc/os-release", "same"),
          ("cat note.txt", "same"), ("cat nope.txt", "rule"), ("cowsay moo", "works"),
          ("hallux", "rule")]
REBOOT_SCRIPT = SETUP + [c for c, _ in CHECKS] + ["sudo reboot"] + [c for c, _ in CHECKS] + ["exit"]


def reboot_report(records: list[Record]) -> tuple[str, bool]:
    """Compare every check before and after the reboot. Returns the report and "all passed"."""
    runs = {}
    for record in records:
        runs.setdefault(record.typed, []).append(record)
    rebooted = "(reboot)" in runs                      # a plain `reboot` can be refused, faithfully
    lines, passed = [f"  {'ok' if rebooted else 'FAILED':9} the machine rebooted"], rebooted
    for command, kind in CHECKS:
        found = runs.get(command, [])
        if len(found) < 2:
            lines.append(f"  MISSING   {command}")
            passed = False
            continue
        before, after = found[0].output.strip(), found[1].output.strip()
        if kind == "same":
            ok = before == after
        elif kind == "rule":
            ok = "OOPS" in before and "OOPS" in after
        else:
            ok = all("not found" not in text and "No such" not in text for text in (before, after))
        passed &= ok
        lines.append(f"  {'ok' if ok else 'FAILED':9} {command}")
        if not ok or kind == "same":
            shown = before.splitlines()[:1] or [""]
            lines.append(f"            before: {shown[0][:70]}")
            if before != after:
                lines.append(f"            after:  {(after.splitlines()[:1] or [''])[0][:70]}")
    prompts = [plain(r.prompt) for r in runs.get(CHECKS[0][0], [])[:2]]   # before, after
    same_prompt = prompts == ["check> ", "check> "]
    passed &= same_prompt
    lines.append(f"  {'ok' if same_prompt else 'FAILED':9} the prompt survives: "
                 + " / ".join(repr(p) for p in prompts))
    return "\n".join(lines), passed
