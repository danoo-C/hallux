"""Addon agents: the jobs an addon's agent does in the background (docs/addon-agents.md).

Jobs is one for a run of Hallux. It holds the process table, takes each job from spawn to
its end, and makes the event of that end from facts: the pid, how it ended, the files that
landed. Nothing a job says reaches the main agent, except a status line of 80 clean
characters and the names of its files.

A job is run by a worker. Jobs is handed what makes one, and asks three things of it: run,
stop, and to report while it runs, which a worker does through the Job it was made for. The
real worker is Session, at the end of this file: a Claude session of its own for each job.
The tests have a stand-in that follows a script.
"""
from __future__ import annotations

import asyncio
import contextlib
import errno
import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Callable, Coroutine, Protocol, Sequence

from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, SdkMcpTool, StreamEvent,
    TextBlock, ToolUseBlock,
)

from hallux import config, sandbox
from hallux.addons import STATUS_MAX, Addon, Refused
from hallux.config import Hardware
from hallux.disk import Disk
from hallux.jobdisk import FolderGone, JobDisk
from hallux.protocol import CONTROL_PICTURES, SEQUENCE
from hallux.tools import SERVER, build_job_servers

log = logging.getLogger("hallux")
RULES = (files("hallux") / "agent.md").read_text(encoding="utf-8")     # for every worker

FIRST_PID = 30001                             # pids count up from here for as long as hallux runs
BRIEF_MAX = 2000                              # characters of a job's one message
TURNS = 60                                    # model turns per job: a backstop in code
TABLE_MAX = 32                                # rows of the main agent's table
KEPT_MAX = 32                                 # ended jobs kept for hallux's own panel
ACTIVITY_MAX = 200                            # lines of what a job has been doing
LINE_MAX = 500                                # characters of one such line
RESULT_SHOWN = 160                            # of a tool's result among them: about two lines
STOP_SECONDS = 5.0                            # for a stopped worker to come back with the cost
RESULT_SECONDS = 3.0                          # of those, for the result that follows an interrupt
BOOT_SECONDS = 5.0                            # for all of them together, at the end of a boot
ENDED = ("done", "failed", "killed")
ROUNDING = 1e-9                               # dollars added up aren't exact: 0.1 + 0.2
CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean(text: object, limit: int) -> str:
    """One line of printable text, cut at `limit`: no control characters, no escape codes, and
    none of the control pictures that the terminal turns into escape codes. A job's text is
    untrusted: it may repeat what a file told it."""
    plain = SEQUENCE.sub("", str(text).translate(CONTROL_PICTURES))     # ␛[31m goes as a whole
    return " ".join(CONTROLS.sub(" ", plain).split())[:limit]


@dataclass(frozen=True)
class Limits:
    """What a job may use. Read from the settings when it starts, and carried by it."""
    budget_usd: float                         # agent_job_budget_usd
    turns: int
    seconds: float                            # agent_timeout_seconds


@dataclass(frozen=True)
class Outcome:
    """How a worker's run ended."""
    ok: bool                                  # well: only then does the job's work land
    why: str | None = None                    # budget, turns, or how the session failed
    cost_usd: float | None = None             # None: it isn't known
    tokens: int | None = None                 # None: what was reported so far stands
    turns: int = 0
    last: str = ""                            # its last message: for the log, and nobody else


@dataclass
class JobEvent:
    """The end of a job, waiting for the main agent. Built by hallux, from facts."""
    addon: str
    data: dict
    had_turn: bool = False                    # it has had a message of its own; the machine's


@dataclass(frozen=True)
class Line:
    """One line of what a job has been doing, for hallux's own panel."""
    at: float                                 # seconds from the job's start
    kind: str                                 # status, a tool's name, → for what it answered,
                                              # says for what the model wrote, end
    text: str


class Worker(Protocol):
    """What runs one job."""

    async def run(self) -> Outcome:
        """Do the job, and come back with how it ended."""

    async def stop(self) -> None:
        """End now: run() comes back soon, and still says what the job cost."""


def _ended(state: str, why: str | None, landed: dict | None) -> str:
    """How a job ended, as a line for the panel: with the files that landed, or the reason."""
    if landed is None:
        return f"{state}: {why}"
    names = ", ".join(os.path.basename(path) for path in landed["files"]) or "nothing written"
    if "conflict" in landed:
        changed = ", ".join(os.path.basename(path) for path in landed["conflict"])
        return f"{state}: {names} ({changed} was changed meanwhile)"
    return f"{state}: {names}"


class NoWorker:
    """What a Jobs has in place of a worker when it is handed nothing that makes one: its jobs
    fail at once, and say so. A machine hands its Jobs the real one, Session."""

    def __init__(self, job: Job) -> None:
        self.job = job

    async def run(self) -> Outcome:
        return Outcome(ok=False, why="this hallux has no worker to run a job", cost_usd=0.0)

    async def stop(self) -> None:
        pass


class Job:
    """One job: its row in the table, and what its worker may do to it."""

    def __init__(self, jobs: Jobs, pid: int, addon: Addon, brief: str, disk: JobDisk,
                 limits: Limits, now: float) -> None:
        self.jobs, self.pid, self.addon, self.brief = jobs, pid, addon, brief
        self.disk, self.limits = disk, limits
        self.agent = addon.agent.name
        self.state = "running"                # or waiting, and then one of ENDED
        self.status = addon.agent.status or self.agent
        self.tool: str | None = None          # the tool call it is in, while it waits
        self.tokens, self.turns = 0, 0
        self.cost_usd: float | None = None
        self.why: str | None = None
        self.started = datetime.now().astimezone().isoformat(timespec="seconds")
        self.began, self.ended = now, None    # on the clock that counts its seconds
        self.settled = False                  # its worker has come back: its cost has arrived
        self.silent = False                   # its boot is over: no event for its end
        self.activity: deque[Line] = deque(maxlen=ACTIVITY_MAX)
        self.worker: Worker | None = None     # while it runs
        self.task: asyncio.Task | None = None
        self.stopper: asyncio.Task | None = None      # held here: a loop only holds a task weakly
        self.timer: asyncio.TimerHandle | None = None

    # What a worker reports. All of it is called in hallux's event loop.

    def set_status(self, text: object) -> str:
        """The one thing a job writes into its row. Returns the line as kept."""
        return self.jobs.set_status(self.pid, text)

    def tool_began(self, name: str, args: dict | None = None) -> None:
        """The job is inside a tool call. Of the arguments only a file of its own is shown."""
        self.jobs.report(self, state="waiting", tool=name, args=args or {})

    def tool_ended(self, result: str | None = None) -> None:
        """The call is over. With what it answered, for the panel: its result or its error."""
        self.jobs.report(self, state="running", result=result)

    def tokens_so_far(self, tokens: int) -> None:
        self.jobs.report(self, tokens=tokens)

    def says(self, text: str) -> None:
        """What the model wrote between two tool calls. For the panel, and nobody else."""
        self.jobs.said(self, text)

    # What the table shows.

    def seconds(self, now: float) -> int:
        return int((self.ended if self.ended is not None else now) - self.began)

    def row(self, now: float) -> dict:
        row: dict = {"pid": self.pid, "addon": self.addon.name, "agent": self.agent,
                     "state": self.state}
        if self.state == "waiting" and self.tool:
            row["tool"] = self.tool
        row |= {"started": self.started, "seconds": self.seconds(now), "tokens": self.tokens,
                "folder": self.disk.folder, "status": self.status}
        if self.why:
            row["why"] = self.why
        if self.settled:                      # a job's dollars are known when it has ended
            row["cost_usd"] = "unknown" if self.cost_usd is None else round(self.cost_usd, 4)
        return row


class Jobs:
    def __init__(self, disk: Disk, settings: Callable[[], Hardware],
                 make_worker: Callable[[Job], Worker] = NoWorker,
                 on_report: Callable[[], None] = lambda: None,
                 on_event: Callable[[], None] = lambda: None,
                 over_budget: Callable[[], bool] = lambda: False,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.disk = disk                      # the machine's: a job's folder is a path of it
        self.settings = settings              # as they are when they are asked for
        self.make_worker = make_worker
        self.on_report = on_report            # a job reported or ended: the bar, the panel
        self.on_event = on_event              # an event started to wait: the prompt
        self.over_budget = over_budget        # the machine's: has the boot used its budget
        self.clock = clock
        # The jobs' dollars, apart from the main session's. A job is in them when its worker
        # has come back; one whose cost isn't known counts with its full cap.
        self.spent = 0.0                      # since hallux started
        self.spent_boot = 0.0                 # by the jobs of this boot
        self.spent_since_refill = 0.0         # what counts for agent_budget_usd
        self.loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.RLock()        # spawn is called in an addon's own thread
        self._next = FIRST_PID
        self._live: dict[int, Job] = {}       # every job whose worker hasn't come back
        self._table: dict[int, Job] = {}      # what the main agent sees: those that run, and
                                              # those that ended and weren't seen yet
        self._events: list[JobEvent] = []     # oldest first; never dropped while the boot lasts
        self._finishing: set[asyncio.Task] = set()    # what goes on after a job's end
        self.kept: deque[Job] = deque(maxlen=KEPT_MAX)    # ended, for the panel: they stay

    def start(self) -> None:
        """Learn the event loop. To be called from inside it, when hallux starts to run."""
        self.loop = asyncio.get_running_loop()

    # ------------------------------------------------------------------ a job's start

    def spawn(self, addon: Addon, brief: str, folder: str, edit: Sequence[str] = ()) -> int:
        """Start a job of this addon's agent, and return its pid at once. Raises Refused.

        It is called in the addon's own thread. So it only checks, notes the row under a
        lock, and hands the start of the worker to hallux's event loop."""
        if self.loop is None:
            raise RuntimeError("Jobs.spawn() before Jobs.start(): no event loop to run a job in")
        if not isinstance(brief, str) or len(brief) > BRIEF_MAX:
            raise Refused("EMSGSIZE")
        with self._lock:
            if self.why_not(addon):           # a cap: the way a failed fork reads
                raise Refused("EAGAIN")
            pid = self._next
            try:                              # the folder and the files: the fenced disk checks
                disk = JobDisk(self.disk, folder, list(edit or ()), pid)
            except OSError as e:
                raise Refused(errno.errorcode.get(e.errno, "EIO"), e.filename) from None
            except ValueError:                # no path at all: a NUL in it, say
                raise Refused("EINVAL") from None
            hw = self.settings()
            limits = Limits(hw.agent_job_budget_usd, TURNS, hw.agent_timeout_seconds)
            job = Job(self, pid, addon, brief, disk, limits, self.clock())
            self._next += 1
            self._live[pid] = self._table[pid] = job
            self._trim()
        log.info("job %d: %s.%s started in %s", pid, addon.name, job.agent, disk.folder)
        self.loop.call_soon_threadsafe(self._start, job)
        return pid

    def _start(self, job: Job) -> None:
        """In the event loop: make the job's worker and let it run."""
        if job.settled:                       # killed before it started: no worker was made
            return
        job.worker = self.make_worker(job)
        job.timer = self.loop.call_later(job.limits.seconds, self._end, job, "timeout")
        job.task = self.loop.create_task(self._run(job))
        self.on_report()

    async def _run(self, job: Job) -> None:
        try:
            outcome = await job.worker.run()
        except asyncio.CancelledError:        # stopped the hard way: it never said what it cost
            outcome = Outcome(ok=False)
        except Exception as e:                # a worker that broke
            log.exception("job %d: its worker failed", job.pid)
            outcome = Outcome(ok=False, why=f"{type(e).__name__}: {e}")
        self._settle(job, outcome)

    # ------------------------------------------------------------------ a job's end

    def kill(self, pid: int) -> None:
        """End a job. ESRCH for a pid that isn't running: not there, or ended already. To be
        called in the event loop, as everything here but spawn."""
        with self._lock:
            job = self._table.get(pid)
            if job is None or job.state in ENDED:
                raise OSError(errno.ESRCH, os.strerror(errno.ESRCH))
        self._end(job, "kill")

    def _end(self, job: Job, why: str) -> None:
        """Kill a job: by kill, by its time, or because its boot is over. The row is marked at
        once and nothing of the job will land. Its worker is stopped, and what the job cost
        goes into the row when the worker has come back."""
        with self._lock:
            if job.state in ENDED:
                return
            self._close(job, "killed", why)
        if job.worker is None:                # it hadn't started: it cost nothing
            self._settle(job, Outcome(ok=False, cost_usd=0.0))
        else:
            job.stopper = self.loop.create_task(self._stop(job, job.worker))
        self._told_someone(job)

    async def _stop(self, job: Job, worker: Worker) -> None:
        try:
            await asyncio.wait_for(worker.stop(), STOP_SECONDS)
        except Exception:                     # it wouldn't stop, or broke: the task goes anyway
            log.warning("job %d: its worker didn't stop", job.pid, exc_info=True)
        if job.task is not None and not job.task.done():
            await asyncio.wait({job.task}, timeout=STOP_SECONDS)
            if not job.task.done():
                job.task.cancel()             # and its cost stays unknown

    def _settle(self, job: Job, outcome: Outcome) -> None:
        """The worker has come back. If the job wasn't killed meanwhile, this is its end; if
        it was, only what it cost is new. A job that was killed never lands."""
        with self._lock:
            if job.settled:
                return
            if job.timer is not None:
                job.timer.cancel()
            job.settled, job.turns, job.cost_usd = True, outcome.turns, outcome.cost_usd
            job.worker = None                 # a kept job doesn't keep its session
            if outcome.tokens is not None:
                job.tokens = outcome.tokens
            ended_here = job.state not in ENDED
            if ended_here:
                self._close(job, *self._ending(job, outcome))
            self._live.pop(job.pid, None)
            counted = job.limits.budget_usd if job.cost_usd is None else job.cost_usd
            self.spent += counted
            self.spent_boot += counted
            self.spent_since_refill += counted
            cost = "cost unknown" if job.cost_usd is None else f"${job.cost_usd:.4f}"
            log.info("job %d %s%s: %d turns, %ds, %d tokens, %s", job.pid, job.state,
                     f" ({job.why})" if job.why else "", job.turns, job.seconds(self.clock()),
                     job.tokens, cost)
            if outcome.last:                  # to the log, and nowhere else
                log.info("job %d said last: %s", job.pid, clean(outcome.last, LINE_MAX))
        if ended_here:
            self._told_someone(job)
        else:
            self.on_report()

    def _ending(self, job: Job, outcome: Outcome) -> tuple[str, str | None, dict | None]:
        """How a job ends whose worker came back by itself: the state, why, what landed."""
        if outcome.ok:
            try:
                return "done", None, job.disk.land()
            except FolderGone:
                return "failed", "folder", None
            except OSError as e:              # a write failed in the middle: the disk is full
                log.warning("job %d: its work didn't land: %s", job.pid, e)
                return "failed", "disk", None
        if outcome.why in ("budget", "turns"):
            return "killed", outcome.why, None
        return "failed", clean(outcome.why or "", STATUS_MAX) or "failed", None

    def _close(self, job: Job, state: str, why: str | None, landed: dict | None = None) -> None:
        """A job's end, as the table shows it from now on: the row, the event, the copies."""
        job.state, job.why, job.tool = state, why, None
        job.ended = self.clock()
        written = job.disk.written()
        job.disk.drop()                       # dead from here on, also for a handle out there
        self._line(job, "end", _ended(state, why, landed))
        self.kept.append(job)
        if job.silent:
            return
        data = {"event": "job", "pid": job.pid, "agent": job.agent, "state": state}
        data |= landed if landed is not None else {"why": why, "written": written}
        self._events.append(JobEvent(job.addon.name, data | {"seconds": job.seconds(job.ended)}))

    def _told_someone(self, job: Job) -> None:
        """After a job's end: the bar and the panel, and the prompt if an event waits now."""
        self.on_report()
        if not job.silent:
            self.on_event()

    async def end_boot(self) -> None:
        """The boot is over: every job is killed, with no event. Then the table and the list
        of events are empty. The pids go on, and so does what is kept for the panel."""
        with self._lock:
            live = list(self._live.values())
            for job in live:
                job.silent = True
        for job in live:
            self._end(job, "boot")
        tasks = [job.task for job in live if job.task is not None and not job.task.done()]
        if tasks:                             # a few seconds for what they cost
            _, late = await asyncio.wait(tasks, timeout=BOOT_SECONDS)
            for task in late:
                task.cancel()
            if late:
                await asyncio.wait(late, timeout=1)
        if self._finishing:                   # and for their sessions to be closed
            await asyncio.wait(set(self._finishing), timeout=BOOT_SECONDS)
        with self._lock:
            self._table.clear()
            self._events.clear()

    def finish_later(self, work: Coroutine) -> None:
        """Let something of a job's go on after the job has ended: the closing of its session,
        which takes a second or more. It is held here, since a loop holds a task only weakly,
        and the end of a boot waits for it."""
        task = self.loop.create_task(work)
        self._finishing.add(task)
        task.add_done_callback(self._finishing.discard)

    # ------------------------------------------------------------------ the caps

    def why_not(self, addon: Addon) -> str | None:
        """Why a job of this addon's agent can't start now, in words, or None if it can. It is
        the check spawn makes, without starting anything; the panel shows the words.

        The budget for all jobs is never passed: a job that runs, or was killed and hasn't
        said what it cost, counts with its full cap, and so does the one that asks."""
        hw = self.settings()
        with self._lock:
            if hw.agent_max_running == 0 or hw.agent_budget_usd == 0:
                return "agents are off"
            if any(job.addon.name == addon.name for job in self._live.values()):
                return "already running"      # one job of an addon's agent at a time
            if len(self._live) >= hw.agent_max_running:
                return "too many jobs"
            running = sum(job.limits.budget_usd for job in self._live.values())
            asked = self.spent_since_refill + running + hw.agent_job_budget_usd
            if asked > hw.agent_budget_usd + ROUNDING:
                return "jobs budget used"
        if self.over_budget():                # the boot's, jobs included
            return "boot budget used"
        return None

    def refill(self) -> None:
        """Somebody is at the keyboard: what the ended jobs cost counts from nothing again."""
        with self._lock:
            self.spent_since_refill = 0.0

    def new_boot(self) -> None:
        """A boot starts: it has spent nothing on jobs yet, and their budget is full."""
        with self._lock:
            self.spent_boot = self.spent_since_refill = 0.0

    # ------------------------------------------------------------------ what a worker reports

    def set_status(self, pid: int, text: object) -> str:
        """One line, cut at 80 characters and cleaned. Returns the line as kept, so a cut is
        never silent. Only the newest line is in the table."""
        kept = clean(text, STATUS_MAX)
        with self._lock:
            job = self._live.get(pid)
            if job is None or job.state in ENDED:
                raise OSError(errno.ESRCH, os.strerror(errno.ESRCH))
            job.status = kept
            self._line(job, "status", kept)
        self.on_report()
        return kept

    def report(self, job: Job, state: str | None = None, tool: str | None = None,
               args: dict | None = None, tokens: int | None = None,
               result: str | None = None) -> None:
        """A worker says where its job is: inside a tool call, out of it and with what answer,
        at so many tokens."""
        with self._lock:
            if job.state in ENDED:            # killed meanwhile: the row stays as it is
                return
            if tokens is not None:
                job.tokens = tokens
            if state == "waiting":
                # The first text argument that names a file of the job's own, and no other
                # argument: an argument is text the job chose.
                file = next((name for value in (args or {}).values()
                             if (name := job.disk.own(value))), None)
                job.state, job.tool = "waiting", clean(tool, STATUS_MAX)
                self._line(job, job.tool, file or "")
                if file:
                    job.tool = f"{job.tool} {file}"
            elif state == "running":
                job.state, job.tool = "running", None
                if result is not None:        # short: a whole file can come back from a read
                    self._line(job, "→", clean(result, RESULT_SHOWN))
        self.on_report()

    def said(self, job: Job, text: str) -> None:
        """What a job's model wrote, as a line for the panel. Nothing of it goes anywhere
        else: not into the row, and not into the event."""
        with self._lock:
            if job.state in ENDED or not text.strip():
                return
            self._line(job, "says", text)
        self.on_report()

    def _line(self, job: Job, kind: str, text: str) -> None:
        job.activity.append(Line(self.clock() - job.began, kind, clean(text, LINE_MAX)))

    # ------------------------------------------------------------------ what the main agent gets

    def table(self) -> list[dict]:
        """The rows, as dictionaries. A job that has ended leaves the table once it was read,
        like a process that was waited for."""
        with self._lock:
            now = self.clock()
            rows = [job.row(now) for job in self._table.values()]
            for pid in [pid for pid, job in self._table.items() if job.state in ENDED]:
                del self._table[pid]
            return rows

    def waiting(self) -> list[JobEvent]:
        """The events that wait, oldest first. They stay until they are told."""
        with self._lock:
            return list(self._events)

    def told(self, events: Sequence[JobEvent]) -> None:
        """These events have reached the main agent: their message went out and was answered.
        Their jobs leave the table: they were seen."""
        with self._lock:
            for event in events:
                if event in self._events:
                    self._events.remove(event)
                self._table.pop(event.data["pid"], None)

    def _trim(self) -> None:
        """At most TABLE_MAX rows: the oldest ended ones go first."""
        ended = [pid for pid, job in self._table.items() if job.state in ENDED]
        while len(self._table) > TABLE_MAX and ended:
            del self._table[ended.pop(0)]


# ---------------------------------------------------------------------- a job's real session

def shared_options(hw: Hardware, hidden: Path) -> dict:
    """What every Claude session of hallux gets, the machine's own and a job's: nothing of
    Claude Code's and nothing of yours, and the OS sandbox if it is set. `hidden` is the
    world's .hallux folder, where the sandbox's start script lives."""
    return {
        "strict_mcp_config": True,            # no MCP servers from your own Claude config
        "tools": [],                          # no built-in Bash/Read/Write/... at all
        "permission_mode": "dontAsk",         # anything that isn't allowed by name is denied
        "setting_sources": [],                # ignore your CLAUDE.md and settings
        "include_partial_messages": True,     # the stream: an answer as it's written, and a
                                              # job's tokens
        # hallux.log has everything; Claude Code needn't keep its own transcript, which
        # would also show hallux sessions in your `claude --resume` list
        "extra_args": {} if hw.keep_transcripts else {"no-session-persistence": None},
        "cli_path": sandbox.wrapper(hidden) if hw.os_sandbox else None,
    }


def rules(addon: Addon) -> str:
    """A job's system prompt: hallux's rules for every worker, then its addon's own."""
    ours = RULES.replace("{agent}", addon.agent.name).replace("{addon}", addon.name)
    return f"{ours.rstrip()}\n\n{addon.agent.prompt}"


def task(job: Job) -> str:
    """A job's one message: the brief, and under it what the job may change."""
    if job.disk.edit:
        may = (f"You may change these files: {', '.join(job.disk.edit)}. Every other file "
               f"that is there is read-only for you, and you can create new ones.")
    else:
        may = "You were given no file to change: you can only create new files."
    return f"{job.brief}\n\nYour folder is {job.disk.folder}. {may}"


def _tokens(usage: dict | None, written: bool = True) -> int:
    """What a model message read, cached input included, and with `written` what it wrote."""
    usage = usage or {}
    kinds = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    return sum(usage.get(kind) or 0 for kind in kinds + (("output_tokens",) if written else ()))


def _reason(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}" if str(error) else type(error).__name__


class Session:
    """The real worker: a Claude session of its own for one job, opened when the job starts
    and closed when it ends. It gets hallux's rules for a worker, its addon's prompt and the
    job's tools, and nothing else. `running` says which model the machine's own session
    really runs on, and `client_factory` makes the SDK's client, as for the machine."""

    def __init__(self, job: Job, running: Callable[[], str],
                 client_factory: Callable[..., ClaudeSDKClient] = ClaudeSDKClient) -> None:
        self.job, self.running, self.client_factory = job, running, client_factory
        self.tools: dict[str, SdkMcpTool] = {}        # the job's, by the names it calls them
        self.client: ClaudeSDKClient | None = None    # while its session is open
        self.opening: asyncio.Future | None = None
        self.patience: asyncio.Timeout | None = None  # how long its result may still take
        self.stopped = False                  # stop() was called
        self.over = False                     # run() has come back
        # The tokens: of the model messages that have ended, and of the one under way what it
        # read and what it wrote.
        self.before = self.read = self.written = 0
        self.said = ""                        # the last text the model wrote

    def options(self) -> ClaudeAgentOptions:
        job, hw, agent = self.job, self.job.jobs.settings(), self.job.addon.agent
        model = config.agent_model(hw, self.running())
        servers, self.tools = build_job_servers(job.addon, job.disk, job)
        return ClaudeAgentOptions(
            system_prompt=rules(job.addon),
            model=model,
            effort=config.agent_effort(hw, agent.effort, model),
            # No fallback model: a job fails before it runs on a model nobody chose for it.
            max_turns=job.limits.turns,
            max_budget_usd=job.limits.budget_usd,     # the SDK's own cap, for this session
            mcp_servers=servers,
            allowed_tools=list(self.tools),
            **shared_options(hw, job.jobs.disk.hidden),
        )

    async def run(self) -> Outcome:
        session = contextlib.AsyncExitStack()         # what was opened, to close at the end
        try:
            return await self._run(session)
        finally:
            if self.client is not None:       # closed in the background: nobody waits for it
                self.job.jobs.finish_later(self._close(session))
            self.over, self.client = True, None

    async def _run(self, session: contextlib.AsyncExitStack) -> Outcome:
        job = self.job
        if self.stopped:                      # before it began
            return Outcome(ok=False, cost_usd=0.0)
        try:
            self.opening = asyncio.ensure_future(
                session.enter_async_context(self.client_factory(options=self.options())))
            self.client = await self.opening
        except asyncio.CancelledError:
            if not self.stopped:              # not a stop: this task itself is being ended
                raise
            return Outcome(ok=False, cost_usd=0.0)    # nothing was asked of the model
        except Exception as e:
            log.warning("job %d: its session didn't open", job.pid, exc_info=True)
            return Outcome(ok=False, why=_reason(e), cost_usd=0.0)
        if self.stopped:                      # while it opened, too late to end the opening
            return Outcome(ok=False, cost_usd=0.0)
        try:
            async with asyncio.timeout(None) as self.patience:   # stop() sets how long
                await self.client.query(task(job))
                return self._outcome(await self._read())
        except Exception as e:
            if self.stopped and isinstance(e, TimeoutError):     # nothing followed the interrupt
                log.warning("job %d: no result came after it was stopped", job.pid)
                return Outcome(ok=False, tokens=self._so_far())
            log.warning("job %d: its session failed", job.pid, exc_info=True)     # Claude Code
            return Outcome(ok=False, why=_reason(e), tokens=self._so_far())       # died, say

    async def _read(self) -> ResultMessage | None:
        """Read the session to its result. Each tool call goes to the log with the pid in
        front, and so does what the model says, which the panel gets too. Whatever else the
        session sends is passed over: its thinking, its states, the rate limit."""
        job, result = self.job, None
        async for message in self.client.receive_response():
            if isinstance(message, StreamEvent):
                self._count(message.event)
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        log.info("job %d: tool %s %s", job.pid,
                                 block.name.removeprefix(f"mcp__{SERVER}__"), block.input)
                    elif isinstance(block, TextBlock) and block.text.strip():
                        log.info("job %d says: %s", job.pid, block.text)
                        self.said = block.text
                        job.says(block.text)
            elif isinstance(message, ResultMessage):
                result = message
        return result

    def _count(self, event: dict) -> None:
        """The tokens, from the stream: what a model message read when it starts, what it
        wrote when it ends. A message that is cut by a kill still counts with what it read.
        The usage on the session's own messages can't be added up: a model message arrives
        as several of them, each with the same numbers and the output of its first moment."""
        kind = event.get("type")
        if kind == "message_start":
            usage = (event.get("message") or {}).get("usage")
            self.before += self.read + self.written
            self.read, self.written = _tokens(usage, written=False), 0
        elif kind == "message_delta":
            self.written = (event.get("usage") or {}).get("output_tokens") or self.written
        else:
            return
        self.job.tokens_so_far(self._so_far())

    def _so_far(self) -> int:
        return self.before + self.read + self.written

    def _outcome(self, result: ResultMessage | None) -> Outcome:
        """How the job ended, from its session's result. Well is a success that carries no
        error: a call to the API that failed arrives as a success with the error flag set."""
        if result is None:
            return Outcome(ok=False, why="its session ended without a result",
                           tokens=self._so_far())
        # The larger number stands: after a kill or a used-up cap the result's own usage
        # lacks the last model message, or all of them.
        facts = {"cost_usd": result.total_cost_usd, "turns": result.num_turns,
                 "tokens": max(self._so_far(), _tokens(result.usage)),
                 "last": "" if result.result == self.said else result.result or ""}
        if result.subtype == "success" and not result.is_error:
            return Outcome(ok=True, **facts)
        why = {"error_max_turns": "turns", "error_max_budget_usd": "budget"}.get(result.subtype)
        if why is None:                       # worded as the machine words a model error
            why = "; ".join(result.errors or []) or result.result or result.subtype
            if result.api_error_status:
                why = f"{why} (HTTP {result.api_error_status})"
        return Outcome(ok=False, why=why, **facts)

    async def stop(self) -> None:
        """End now. An open session is interrupted, and run() reads on to the result that
        follows, which holds what the job cost. One that is still opening has nothing to
        interrupt: its opening is ended, and it cost nothing."""
        self.stopped = True
        if self.over:                         # it came back by itself meanwhile
            return
        if self.client is None:
            if self.opening is not None:
                self.opening.cancel()
            return
        self.patience.reschedule(asyncio.get_running_loop().time() + RESULT_SECONDS)
        await self.client.interrupt()

    async def _close(self, session: contextlib.AsyncExitStack) -> None:
        try:
            await session.aclose()
        except Exception:
            log.warning("job %d: its session didn't close cleanly", self.job.pid, exc_info=True)
