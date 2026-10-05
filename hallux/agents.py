"""Addon agents: the jobs an addon's agent does in the background (docs/addon-agents.md).

Jobs is one for a run of Hallux. It holds the process table, takes each job from spawn to
its end, and makes the event of that end from facts: the pid, how it ended, the files that
landed. Nothing a job says reaches the main agent, except a status line of 80 clean
characters and the names of its files.

A job is run by a worker. Jobs is handed what makes one: a stand-in in the tests, and for
the real thing a Claude session of its own. It asks three things of a worker: run, stop,
and to report while it runs, which a worker does through the Job it was made for.
"""
from __future__ import annotations

import asyncio
import errno
import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol, Sequence

from hallux.addons import STATUS_MAX, Addon, Refused
from hallux.config import Hardware
from hallux.disk import Disk
from hallux.jobdisk import FolderGone, JobDisk
from hallux.protocol import CONTROL_PICTURES, SEQUENCE

log = logging.getLogger("hallux")

FIRST_PID = 30001                             # pids count up from here for as long as hallux runs
BRIEF_MAX = 2000                              # characters of a job's one message
TURNS = 60                                    # model turns per job: a backstop in code
TABLE_MAX = 32                                # rows of the main agent's table
KEPT_MAX = 32                                 # ended jobs kept for hallux's own panel
ACTIVITY_MAX = 200                            # lines of what a job has been doing
LINE_MAX = 500                                # characters of one such line
STOP_SECONDS = 5.0                            # for a stopped worker to come back with the cost
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
    kind: str                                 # status, a tool's name, end
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
    """What a machine has in place of a worker until it is given one that can run a job: its
    jobs fail at once, and say so."""

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

    def tool_ended(self) -> None:
        self.jobs.report(self, state="running")

    def tokens_so_far(self, tokens: int) -> None:
        self.jobs.report(self, tokens=tokens)

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
            row["cost_usd"] = "unknown" if self.cost_usd is None else self.cost_usd
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
        with self._lock:
            self._table.clear()
            self._events.clear()

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
               args: dict | None = None, tokens: int | None = None) -> None:
        """A worker says where its job is: inside a tool call, out of it, at so many tokens."""
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
