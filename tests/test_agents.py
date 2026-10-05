"""The jobs of addon agents, hallux/agents.py: the process table, a job's life from spawn to
its end, and the event of that end. No model: a job is run by a stand-in worker that follows
a script."""
import asyncio
import errno
import logging
import threading

import pytest

import hallux.agents
from hallux import addons
from hallux.agents import ACTIVITY_MAX, FIRST_PID, TURNS, Jobs, Outcome, clean
from hallux.config import Hardware
from hallux.disk import Disk

NEON = "BPM = 90\n# neon\nSONG:\n"
HERE = "/home/user/Music"
WELL = Outcome(ok=True, cost_usd=0.21, tokens=21340, turns=7, last="The song is written.")
MUSIC = addons.Addon("music", "A sound card.", "the manual", {}, agent=addons.Agent(
    "composer", "You compose one song.", {}, "high", "composing…"))
MAIL = addons.Addon("mail", "A mailbox.", "the manual", {}, agent=addons.Agent(
    "sorter", "You sort mail.", {}))
GUI = addons.Addon("gui", "A window.", "the manual", {}, agent=addons.Agent(
    "designer", "You design.", {}))
ROOMY = Hardware(agent_budget_usd=1000)                  # no budget in the way of a test
CHEAP = Outcome(ok=True, cost_usd=0.30, tokens=100, turns=1)


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "world"
    (root / "home" / "user" / "Music").mkdir(parents=True)
    (root / "home" / "user" / "Music" / "neon.score").write_text(NEON)
    (root / "tmp" / "work").mkdir(parents=True)
    (root / "etc").mkdir()
    (root / "etc" / "passwd").write_text("user:x:1000\n")
    return root


@pytest.fixture
def music(root):
    return root / "home" / "user" / "Music"


class StandIn:
    """A worker that follows a script, step by step:

        ("status", text)        set the job's status line
        ("tool", name, args)    a tool call begins       ("back",)   and ends
        ("tokens", count)       so many tokens so far
        ("write", path, text)   write a file through the job's disk
        ("wait", gate)          wait until the test opens the gate, or until it is stopped
        ("end", outcome)        come back with this
        ("raise", error)        break

    A script that runs out ends well. `stopped` is what it comes back with when it is stopped
    while it waits; None there means it doesn't come back at all. With `lingers`, it comes
    back only when that gate opens: its cost takes a while to arrive."""

    def __init__(self, job, script, stopped=Outcome(ok=False, cost_usd=0.07, tokens=900, turns=2),
                 lingers=None):
        self.job, self.script, self.when_stopped = job, list(script), stopped
        self.stop_asked, self.lingers = asyncio.Event(), lingers
        self.ran_in = None

    async def run(self):
        self.ran_in = threading.current_thread()
        for kind, *more in self.script:
            if kind == "status":
                self.job.set_status(*more)
            elif kind == "tool":
                self.job.tool_began(*more)
            elif kind == "back":
                self.job.tool_ended()
            elif kind == "tokens":
                self.job.tokens_so_far(*more)
            elif kind == "write":
                self.job.disk.write_file(*more)
            elif kind == "wait":
                opened = asyncio.ensure_future(more[0].wait())
                asked = asyncio.ensure_future(self.stop_asked.wait())
                await asyncio.wait({opened, asked}, return_when=asyncio.FIRST_COMPLETED)
                opened.cancel(), asked.cancel()
                if self.stop_asked.is_set():
                    if self.when_stopped is None:
                        await asyncio.sleep(3600)        # it never comes back by itself
                    if self.lingers is not None:
                        await self.lingers.wait()
                    return self.when_stopped
            elif kind == "end":
                return more[0]
            elif kind == "raise":
                raise more[0]
        return WELL

    async def stop(self):
        self.stop_asked.set()


class World:
    """A Jobs on a test world, with stand-in workers, inside a running event loop."""

    def __init__(self, root, hardware=ROOMY):
        self.disk, self.hardware = Disk(root), hardware
        self.scripts, self.workers, self.reports, self.arrivals = {}, [], 0, 0
        self.now = 100.0                                 # the clock: a test moves it
        self.boot_over = False                           # what the machine says of its budget
        self.jobs = Jobs(self.disk, lambda: self.hardware, self.make, on_report=self.reported,
                         on_event=self.arrived, over_budget=lambda: self.boot_over,
                         clock=lambda: self.now)
        self.jobs.start()

    def make(self, job):
        script, more = self.scripts.get(job.pid, ((), {}))
        self.workers.append(StandIn(job, script, **more))
        return self.workers[-1]

    def reported(self):
        self.reports += 1

    def arrived(self):
        self.arrivals += 1

    def spawn(self, *script, addon=MUSIC, brief="a dark techno song", folder=HERE, edit=(),
              **more):
        """Start a job whose worker will follow this script. Returns its pid."""
        self.scripts[self.jobs._next] = (script, more)
        return self.jobs.spawn(addon, brief, folder, edit)

    def tries(self, *script, addon=MUSIC, folder="/tmp/work", **more):
        """spawn(), or the code it was refused with."""
        try:
            return self.spawn(*script, addon=addon, folder=folder, **more)
        except addons.Refused as refusal:
            return refusal.code

    def row(self, pid):
        """The job's row, without reading the table: reading it lets an ended job go."""
        job = next(job for job in [*self.jobs._live.values(), *self.jobs._table.values(),
                                   *self.jobs.kept] if job.pid == pid)
        return job.row(self.now)

    def events(self):
        return [(event.addon, event.data) for event in self.jobs.waiting()]

    async def until(self, condition, seconds=5):
        deadline = asyncio.get_running_loop().time() + seconds
        while not condition():
            assert asyncio.get_running_loop().time() < deadline, "it never happened"
            await asyncio.sleep(0.005)

    async def ended(self, pid):
        """Wait until the job's worker has come back."""
        await self.until(lambda: pid not in self.jobs._live)
        return self.row(pid)


def run(root, scenario, hardware=ROOMY):
    async def main():
        return await scenario(World(root, hardware))
    return asyncio.run(asyncio.wait_for(main(), 20))


def refused(code, fn, *args, path=None):
    with pytest.raises(addons.Refused) as info:
        fn(*args)
    assert (info.value.code, info.value.path) == (code, path)


# ---------------------------------------------------------------- spawn

def test_spawn_returns_a_pid_at_once_and_the_worker_starts_after_it(root):
    async def scenario(world):
        first = world.spawn(("wait", asyncio.Event()))
        nothing_ran_yet = list(world.workers)            # the row is there, the worker isn't
        row = world.row(first)
        second = world.spawn(addon=MAIL, folder="/tmp/work")
        await world.until(lambda: len(world.workers) == 2)
        return first, second, nothing_ran_yet, row

    first, second, nothing_ran_yet, row = run(root, scenario)
    assert (first, second) == (FIRST_PID, FIRST_PID + 1) == (30001, 30002)
    assert nothing_ran_yet == []
    assert row["state"] == "running" and row["pid"] == 30001


def test_spawn_from_an_addons_thread_runs_the_worker_in_the_event_loop(root):
    async def scenario(world):
        pids = []
        thread = threading.Thread(target=lambda: pids.append(world.spawn()))
        thread.start()
        await asyncio.to_thread(thread.join)
        await world.ended(pids[0])
        return pids, world.workers[0].ran_in, threading.current_thread()

    pids, ran_in, loop_thread = run(root, scenario)
    assert pids == [30001] and ran_in is loop_thread


def test_a_refused_start_leaves_no_row(root):
    async def scenario(world):
        refused("EMSGSIZE", world.jobs.spawn, MUSIC, "x" * 2001, HERE)
        refused("EMSGSIZE", world.jobs.spawn, MUSIC, None, HERE)
        refused("EACCES", world.jobs.spawn, MUSIC, "a song", "/home/user", path="/home/user")
        refused("ENOENT", world.jobs.spawn, MUSIC, "a song", "/home/user/Videos",
                path="/home/user/Videos")
        refused("ENOENT", world.jobs.spawn, MUSIC, "a song", HERE, [f"{HERE}/nope.score"],
                path=f"{HERE}/nope.score")
        refused("EACCES", world.jobs.spawn, MUSIC, "a song", HERE, ["/etc/passwd"],
                path="/etc/passwd")
        refused("E2BIG", world.jobs.spawn, MUSIC, "a song", HERE, [f"{HERE}/neon.score"] * 9)
        refused("EINVAL", world.jobs.spawn, MUSIC, "a song", "/tmp/a\0b")     # no path at all
        table, workers = world.jobs.table(), list(world.workers)
        return table, workers, world.spawn(brief="x" * 2000)      # the limit itself is fine

    table, workers, pid = run(root, scenario)
    assert table == [] and workers == []
    assert pid == 30001                                  # a refusal used up no pid
    assert not (root / ".hallux").exists()               # and left no folder of copies


def test_a_relative_folder_starts_at_the_machines_working_directory(root):
    async def scenario(world):
        refused("ENOENT", world.jobs.spawn, MUSIC, "a song", "Music", path="/Music")
        world.disk.chdir("/home/user")
        pid = world.spawn(folder="Music", edit=["Music/neon.score"])
        world.disk.chdir("/etc")                         # the shell moves on; the job doesn't
        return world.row(pid)["folder"], world.jobs._live[pid].disk.edit

    assert run(root, scenario) == (HERE, [f"{HERE}/neon.score"])


def test_spawn_before_the_loop_is_known_is_loud(root):
    jobs = Jobs(Disk(root), Hardware, lambda job: None)
    with pytest.raises(RuntimeError, match=r"before Jobs\.start\(\)"):
        jobs.spawn(MUSIC, "a song", HERE)


# ---------------------------------------------------------------- the row

def test_the_row_starts_with_the_declarations_status_or_the_agents_name(root):
    async def scenario(world):
        gate = asyncio.Event()
        composing = world.spawn(("wait", gate), edit=[f"{HERE}/neon.score"])
        sorting = world.spawn(("wait", gate), addon=MAIL, folder="/tmp/work")
        rows = world.row(composing), world.row(sorting)
        gate.set()
        return rows

    composing, sorting = run(root, scenario)
    assert composing.pop("started").startswith("20") and len(sorting.pop("started")) == 25
    assert composing == {"pid": 30001, "addon": "music", "agent": "composer", "state": "running",
                         "seconds": 0, "tokens": 0, "folder": HERE, "status": "composing…"}
    assert sorting == {"pid": 30002, "addon": "mail", "agent": "sorter", "state": "running",
                       "seconds": 0, "tokens": 0, "folder": "/tmp/work", "status": "sorter"}


def test_a_job_carries_its_limits_from_the_settings_at_its_start(root):
    async def scenario(world):
        first = world.spawn(("wait", asyncio.Event()))
        world.hardware = Hardware(agent_job_budget_usd=0.25, agent_timeout_seconds=90,
                                  agent_budget_usd=1000)
        second = world.spawn(("wait", asyncio.Event()), addon=MAIL, folder="/tmp/work")
        await world.until(lambda: len(world.workers) == 2)
        return [worker.job.limits for worker in world.workers], (first, second)

    limits, _ = run(root, scenario)
    assert (limits[0].budget_usd, limits[0].turns, limits[0].seconds) == (1.0, TURNS, 600) == (
        1.0, 60, 600)
    assert (limits[1].budget_usd, limits[1].turns, limits[1].seconds) == (0.25, 60, 90)


def test_the_row_through_a_jobs_life(root):
    async def scenario(world):
        gates = [asyncio.Event() for _ in range(3)]
        pid = world.spawn(("wait", gates[0]), ("tokens", 1200), ("tool", "check", {"path": "x"}),
                          ("wait", gates[1]), ("back",), ("tokens", 3400), ("wait", gates[2]))
        seen = []
        for gate in gates:
            await asyncio.sleep(0.02)
            world.now += 10
            row = world.row(pid)
            seen.append((row["state"], row.get("tool"), row["seconds"], row["tokens"]))
            gate.set()
        row = await world.ended(pid)
        world.now += 100                                 # its seconds are fixed at the end
        return seen, row, world.row(pid)["seconds"]

    seen, row, later = run(root, scenario)
    assert seen == [("running", None, 10, 0), ("waiting", "check", 20, 1200),
                    ("running", None, 30, 3400)]
    assert (row["state"], row["seconds"], row["tokens"], row["cost_usd"]) == (
        "done", 30, 21340, 0.21)                         # the worker's own count at the end
    assert "tool" not in row and "why" not in row and later == 30


def test_tool_shows_a_files_name_only_for_one_of_the_jobs_own_files(root, music):
    (music / "beat.score").write_text("not given\n")

    async def scenario(world):
        calls = [("check", {"path": "neon.score"}),                  # a file it was given
                 ("check", {"path": f"{HERE}/neon.score", "loop": True}),
                 ("read_file", {"path": "beat.score"}),              # one that isn't its own
                 ("check", {"path": "/etc/passwd"}),                 # nor is this
                 ("write_file", {"path": "new.score", "content": "x"}),      # not yet written
                 ("check", {"note": "rm -rf /", "path": "new.score"}),       # written by now
                 ("remix", {"mood": "neon.score is great", "to": "neon.score"}),
                 ("set_status", {})]
        script, shown, gates = [], [], [asyncio.Event() for _ in calls]
        for (name, args), gate in zip(calls, gates):
            script += [("tool", name, args), ("wait", gate), ("back",)]
            if name == "write_file":
                script.append(("write", "new.score", "x"))
        pid = world.spawn(*script, edit=[f"{HERE}/neon.score"])
        for calls_begun, gate in enumerate(gates, 1):    # each call writes a line of activity
            await world.until(lambda: world.workers
                              and len(world.workers[0].job.activity) == calls_begun)
            shown.append(world.row(pid)["tool"])
            gate.set()
        return shown

    assert run(root, scenario) == [
        "check neon.score", "check neon.score", "read_file", "check", "write_file",
        "check new.score", "remix neon.score", "set_status"]     # no other argument, ever


def test_set_status_keeps_one_clean_line_and_says_what_it_kept(root):
    async def scenario(world):
        pid = world.spawn(("wait", asyncio.Event()))
        await world.until(lambda: world.workers)
        job = world.workers[0].job
        kept = [job.set_status("balancing the mix"),
                job.set_status("x" * 200),
                job.set_status("red ␛[31malert␛[0m and \x1b]0;title\x07 and \x1b[2Jcleared"),
                job.set_status("two\nlines\tand\ra tab ␇␈"),
                job.set_status(42)]
        return kept, world.row(pid)["status"]

    kept, status = run(root, scenario)
    assert kept == ["balancing the mix", "x" * 80, "red alert and and cleared",
                    "two lines and a tab", "42"]
    assert status == "42"                                # only the newest line is in the table


def test_clean_takes_out_what_a_terminal_would_act_on():
    assert clean("plain text, with ünïcödé and ♪", 80) == "plain text, with ünïcödé and ♪"
    assert clean("␛[38;5;218mpink␛[0m", 80) == "pink"   # the picture, and what it would become
    assert clean("\x1b[?1049h\x9b31m\x00\x7f ok", 80) == "31m ok"
    assert clean("   spaces   kept   single  ", 80) == "spaces kept single"
    assert clean("a" * 600, 500) == "a" * 500


# ---------------------------------------------------------------- how a job ends

def test_done_when_a_job_ends_well_its_file_lands_and_the_event_says_so(root, music):
    """The step's "Done when": a stand-in worker writes a score into a test world, ends, and the
    test reads the event: done, the file's path, and the file is in the folder."""
    async def scenario(world):
        pid = world.spawn(("status", "sketching the drums"),
                          ("write", "midnight-cello.score", "BPM = 60\nSONG:\n"))
        world.now += 48
        row = await world.ended(pid)
        return row, world.events(), world.arrivals

    row, events, arrivals = run(root, scenario)
    assert events == [("music", {"event": "job", "pid": 30001, "agent": "composer",
                                 "state": "done", "files": [f"{HERE}/midnight-cello.score"],
                                 "seconds": 48})]
    assert (music / "midnight-cello.score").read_text() == "BPM = 60\nSONG:\n"
    assert (row["state"], row["cost_usd"], row["status"]) == ("done", 0.21, "sketching the drums")
    assert arrivals == 1                                 # the function was called for it
    assert not list((root / ".hallux" / "jobs").iterdir())


def test_a_job_that_wrote_nothing_has_an_empty_list(root):
    async def scenario(world):
        await world.ended(world.spawn())
        return world.events()

    assert run(root, scenario)[0][1]["files"] == []      # the program can say so


def test_a_conflict_at_the_landing_is_in_the_event(root, music):
    async def scenario(world):
        gate = asyncio.Event()
        pid = world.spawn(("write", "neon.score", "the job's neon\n"), ("wait", gate),
                          edit=[f"{HERE}/neon.score"])
        await world.until(lambda: world.workers)
        (music / "neon.score").write_text("the user's edit\n")       # saved in nano meanwhile
        gate.set()
        await world.ended(pid)
        return world.events()

    [(_, event)] = run(root, scenario)
    assert event == {"event": "job", "pid": 30001, "agent": "composer", "state": "done",
                     "conflict": [f"{HERE}/neon.score"], "files": [f"{HERE}/neon.score.new"],
                     "seconds": 0}
    assert (music / "neon.score").read_text() == "the user's edit\n"
    assert (music / "neon.score.new").read_text() == "the job's neon\n"


def test_the_folder_deleted_while_the_job_ran(root, music):
    async def scenario(world):
        gate = asyncio.Event()
        pid = world.spawn(("write", "new.score", "x"), ("wait", gate))
        await world.until(lambda: world.workers and world.jobs._live[pid].disk.written())
        (music / "neon.score").unlink()
        music.rmdir()
        gate.set()
        return await world.ended(pid), world.events()

    row, [(_, event)] = run(root, scenario)
    assert (row["state"], row["why"], row["cost_usd"]) == ("failed", "folder", 0.21)
    assert event == {"event": "job", "pid": 30001, "agent": "composer", "state": "failed",
                     "why": "folder", "written": 1, "seconds": 0}
    assert not music.exists() and not list((root / ".hallux" / "jobs").iterdir())


def test_a_write_that_fails_in_the_middle_of_the_landing(root, music, monkeypatch, caplog):
    def full(target, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    async def scenario(world):
        pid = world.spawn(("write", "new.score", "x"), ("wait", gate := asyncio.Event()))
        await world.until(lambda: world.workers and world.jobs._live[pid].disk.written())
        monkeypatch.setattr(hallux.jobdisk, "write_whole", full)
        gate.set()
        return await world.ended(pid), world.events()

    row, [(_, event)] = run(root, scenario)
    assert (row["state"], row["why"]) == ("failed", "disk")
    assert (event["state"], event["why"], event["written"]) == ("failed", "disk", 1)
    assert "job 30001: its work didn't land" in caplog.text and not (music / "new.score").exists()


@pytest.mark.parametrize("outcome, state, why", [
    (Outcome(ok=False, why="API Error: 529 overloaded", cost_usd=0.03), "failed",
     "API Error: 529 overloaded"),
    (Outcome(ok=False), "failed", "failed"),             # it didn't say how
    (Outcome(ok=False, why="␛[31m" + "x" * 200), "failed", "x" * 80),     # cleaned and cut
    (Outcome(ok=False, why="budget", cost_usd=1.0), "killed", "budget"),
    (Outcome(ok=False, why="turns", cost_usd=0.4), "killed", "turns"),
])
def test_a_worker_that_doesnt_end_well_leaves_the_folder_as_it_was(root, music, outcome, state, why):
    async def scenario(world):
        pid = world.spawn(("write", "new.score", "x"), ("write", "neon.score", "changed"),
                          ("end", outcome), edit=[f"{HERE}/neon.score"])
        return await world.ended(pid), world.events()

    row, [(addon, event)] = run(root, scenario)
    assert (row["state"], row["why"]) == (state, why)
    assert addon == "music" and event == {"event": "job", "pid": 30001, "agent": "composer",
                                          "state": state, "why": why, "written": 2, "seconds": 0}
    assert (music / "neon.score").read_text() == NEON and not (music / "new.score").exists()
    assert not list((root / ".hallux" / "jobs").iterdir())      # the copies are dropped


def test_a_worker_that_breaks_is_a_failed_job(root, caplog):
    async def scenario(world):
        return await world.ended(world.spawn(("raise", RuntimeError("the session melted"))))

    row = run(root, scenario)
    assert (row["state"], row["why"], row["cost_usd"]) == (
        "failed", "RuntimeError: the session melted", "unknown")
    assert "job 30001: its worker failed" in caplog.text and "Traceback" in caplog.text


# ---------------------------------------------------------------- a kill

def test_kill_marks_the_row_at_once_and_the_cost_arrives_after_it(root, music):
    async def scenario(world):
        pid = world.spawn(("write", "new.score", "x"), ("wait", asyncio.Event()))
        await world.until(lambda: world.workers and world.jobs._live[pid].disk.written())
        world.now += 7
        world.jobs.kill(pid)
        at_once = world.row(pid), world.events(), pid in world.jobs._live
        after = await world.ended(pid)
        return at_once, after

    (row, events, still_counted), after = run(root, scenario)
    assert (row["state"], row["why"], row["seconds"]) == ("killed", "kill", 7)
    assert "cost_usd" not in row and still_counted       # until its cost arrives
    assert events == [("music", {"event": "job", "pid": 30001, "agent": "composer",
                                 "state": "killed", "why": "kill", "written": 1, "seconds": 7})]
    assert (after["state"], after["cost_usd"], after["tokens"]) == ("killed", 0.07, 900)
    assert not (music / "new.score").exists() and not list((root / ".hallux" / "jobs").iterdir())


def test_a_job_that_was_killed_never_lands_even_if_its_worker_comes_back_well(root, music):
    async def scenario(world):
        pid = world.spawn(("write", "new.score", "x"), ("wait", asyncio.Event()), stopped=WELL)
        await world.until(lambda: world.workers and world.jobs._live[pid].disk.written())
        world.jobs.kill(pid)
        return await world.ended(pid), world.events()

    row, events = run(root, scenario)
    assert (row["state"], row["why"], row["cost_usd"]) == ("killed", "kill", 0.21)
    assert len(events) == 1 and events[0][1]["state"] == "killed"        # one event, not two
    assert not (music / "new.score").exists()


def test_a_kill_before_the_worker_has_started(root):
    async def scenario(world):
        pid = world.spawn(("write", "new.score", "x"))
        world.jobs.kill(pid)                             # in the same breath as the spawn
        row = world.row(pid)
        await asyncio.sleep(0.05)                        # the start comes round, and finds it ended
        return row, world.workers, world.events(), pid in world.jobs._live

    row, workers, events, live = run(root, scenario)
    assert (row["state"], row["why"], row["cost_usd"]) == ("killed", "kill", 0.0)
    assert workers == [] and not live                    # no worker was made: it cost nothing
    assert events[0][1] == {"event": "job", "pid": 30001, "agent": "composer", "state": "killed",
                            "why": "kill", "written": 0, "seconds": 0}


def test_a_kill_of_what_isnt_running_is_esrch(root):
    async def scenario(world):
        pid = world.spawn()
        await world.ended(pid)
        codes = []
        for target in (pid, 30099, 1):                   # ended, never there, never ours
            with pytest.raises(OSError) as info:
                world.jobs.kill(target)
            codes.append(errno.errorcode[info.value.errno])
        return codes

    assert run(root, scenario) == ["ESRCH", "ESRCH", "ESRCH"]


def test_a_stop_that_gives_no_cost(root):
    async def scenario(world):
        pid = world.spawn(("wait", asyncio.Event()), stopped=Outcome(ok=False))
        await world.until(lambda: world.workers)
        world.jobs.kill(pid)
        return await world.ended(pid)

    row = run(root, scenario)
    assert (row["state"], row["cost_usd"]) == ("killed", "unknown")      # the row says so


def test_a_worker_that_never_comes_back_is_given_up_on(root, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="hallux")
    monkeypatch.setattr(hallux.agents, "STOP_SECONDS", 0.05)

    async def scenario(world):
        pid = world.spawn(("wait", asyncio.Event()), stopped=None)
        await world.until(lambda: world.workers)
        world.jobs.kill(pid)
        return await world.ended(pid)

    row = run(root, scenario)
    assert (row["state"], row["why"], row["cost_usd"]) == ("killed", "kill", "unknown")
    assert "job 30001 killed (kill)" in caplog.text and "cost unknown" in caplog.text


def test_the_timeout_kills_a_job(root, music):
    async def scenario(world):
        pid = world.spawn(("write", "new.score", "x"), ("wait", asyncio.Event()))
        return await world.ended(pid), world.events()

    row, [(_, event)] = run(root, scenario, Hardware(agent_timeout_seconds=0.05,
                                                     agent_budget_usd=1000))
    assert (row["state"], row["why"], row["cost_usd"]) == ("killed", "timeout", 0.07)
    assert (event["state"], event["why"], event["written"]) == ("killed", "timeout", 1)
    assert not (music / "new.score").exists()


def test_after_any_end_the_jobs_disk_handle_is_dead(root):
    async def scenario(world):
        gate, handles, codes = asyncio.Event(), [], []
        ends = [(), (("end", Outcome(ok=False, why="broke")),), (("wait", gate),)]
        for number, script in enumerate(ends):           # ended well, failed, killed
            pid = world.spawn(("write", f"song-{number}.score", "x"), *script)
            await world.until(lambda: world.workers and world.workers[-1].job.pid == pid)
            job = world.workers[-1].job
            handles.append(addons.DiskHandle(job.disk))  # what an addon function still holds
            if script and script[0][0] == "wait":
                await world.until(job.disk.written)
                world.jobs.kill(pid)
            await world.ended(pid)
        for number, handle in enumerate(handles):
            with pytest.raises(OSError) as stale:
                handle.read_text(f"song-{number}.score")
            codes.append(handle.refusal(stale.value))
        return codes, [world.row(FIRST_PID + number)["state"] for number in range(3)]

    assert run(root, scenario) == (["ESTALE", "ESTALE", "ESTALE"], ["done", "failed", "killed"])


def test_the_log_gets_one_line_for_each_end_and_the_last_message(root, caplog):
    caplog.set_level(logging.INFO, logger="hallux")

    async def scenario(world):
        world.now += 0
        pid = world.spawn(("tokens", 500))
        world.now += 48
        await world.ended(pid)

    run(root, scenario)
    assert "job 30001: music.composer started in /home/user/Music" in caplog.text
    assert "job 30001 done: 7 turns, 48s, 21340 tokens, $0.2100" in caplog.text
    assert "job 30001 said last: The song is written." in caplog.text


# ---------------------------------------------------------------- the events and the table

def test_the_events_come_out_oldest_first_and_stay_until_they_are_told(root):
    async def scenario(world):
        first, second = asyncio.Event(), asyncio.Event()
        a = world.spawn(("wait", first))
        b = world.spawn(("wait", second), addon=MAIL, folder="/tmp/work")
        second.set()
        await world.ended(b)
        one, arrivals_after_one = world.events(), world.arrivals
        first.set()
        await world.ended(a)
        both = world.jobs.waiting()
        both[0].had_turn = True                          # the machine's mark
        again = world.jobs.waiting()
        world.jobs.told(both[:1])
        return one, arrivals_after_one, both, again, world.jobs.waiting(), world.arrivals

    one, arrivals_after_one, both, again, left, arrivals = run(root, scenario)
    assert [addon for addon, _ in one] == ["mail"] and arrivals_after_one == 1
    assert [(event.addon, event.data["pid"]) for event in both] == [("mail", 30002), ("music", 30001)]
    assert [event.had_turn for event in again] == [True, False]      # the mark stays while it waits
    assert [event.data["pid"] for event in left] == [30001] and arrivals == 2


def test_an_ended_job_leaves_the_table_once_it_was_read(root):
    async def scenario(world):
        gate = asyncio.Event()
        ended = world.spawn()
        running = world.spawn(("wait", gate), addon=MAIL, folder="/tmp/work")
        await world.ended(ended)
        first, second = world.jobs.table(), world.jobs.table()
        gate.set()
        await world.ended(running)
        world.jobs.told(world.jobs.waiting())            # seen in an event: that counts too
        return first, second, world.jobs.table()

    first, second, third = run(root, scenario)
    assert [(row["pid"], row["state"]) for row in first] == [(30001, "done"), (30002, "running")]
    assert [(row["pid"], row["state"]) for row in second] == [(30002, "running")]
    assert third == []


def test_the_table_holds_thirty_two_rows_and_the_oldest_ended_go_first(root):
    async def scenario(world):
        for _ in range(33):
            await world.ended(world.spawn())
        gate = asyncio.Event()
        running = world.spawn(("wait", gate), addon=MAIL, folder="/tmp/work")
        rows = world.jobs.table()
        gate.set()
        await world.ended(running)
        return rows, len(world.jobs.waiting()), [job.pid for job in world.jobs.kept]

    rows, waiting, kept = run(root, scenario)
    assert len(rows) == 32
    assert [row["pid"] for row in rows] == list(range(30003, 30035))     # 30001 and 30002 went
    assert rows[-1]["state"] == "running"
    assert waiting == 34                                 # no event is dropped with its row
    assert kept == list(range(30003, 30035))             # the last 32 that ended, for the panel


def test_the_report_function_is_called_when_a_job_reports_or_ends(root):
    async def scenario(world):
        gates = [asyncio.Event() for _ in range(4)]
        pid = world.spawn(("wait", gates[0]), ("status", "one"), ("wait", gates[1]),
                          ("tool", "check", {}), ("wait", gates[2]), ("back",), ("wait", gates[3]))
        counts = []
        for gate in gates:
            await asyncio.sleep(0.02)
            counts.append(world.reports)
            gate.set()
        await world.ended(pid)
        return counts, world.reports

    counts, at_the_end = run(root, scenario)
    assert counts == sorted(set(counts)) and len(counts) == 4        # it grew with each report
    assert at_the_end > counts[-1]


# ---------------------------------------------------------------- the end of a boot

def test_the_end_of_a_boot_kills_every_job_without_an_event(root, music):
    async def scenario(world):
        landed = world.spawn(("write", "landed.score", "x"))
        await world.ended(landed)                        # its event never reached the main agent
        running = world.spawn(("write", "new.score", "x"), ("wait", asyncio.Event()))
        await world.until(lambda: world.jobs._live[running].disk.written())
        fresh = world.spawn(addon=MAIL, folder="/tmp/work")      # spawned, not started yet
        arrivals = world.arrivals
        await world.jobs.end_boot()
        after = (world.jobs.table(), world.jobs.waiting(), dict(world.jobs._live),
                 world.arrivals - arrivals)
        rows = [world.row(pid) for pid in (running, fresh)]
        return after, rows, world.spawn(), [job.pid for job in world.jobs.kept]

    (table, waiting, live, arrivals), rows, next_pid, kept = run(root, scenario)
    assert table == [] and waiting == [] and live == {} and arrivals == 0
    assert [(row["state"], row["why"]) for row in rows] == [("killed", "boot"), ("killed", "boot")]
    assert rows[0]["cost_usd"] == 0.07 and rows[1]["cost_usd"] == 0.0    # their costs were read
    assert next_pid == 30004                             # the pids go on: not 30001 again
    assert kept == [30001, 30002, 30003]                 # and so does what is kept for the panel
    assert (music / "landed.score").exists() and not (music / "new.score").exists()


def test_the_end_of_a_boot_doesnt_wait_long_for_a_cost(root, monkeypatch):
    monkeypatch.setattr(hallux.agents, "BOOT_SECONDS", 0.05)
    monkeypatch.setattr(hallux.agents, "STOP_SECONDS", 5)

    async def scenario(world):
        pid = world.spawn(("wait", asyncio.Event()), stopped=None)
        await world.until(lambda: world.workers)
        started = asyncio.get_running_loop().time()
        await world.jobs.end_boot()
        return asyncio.get_running_loop().time() - started, world.row(pid), world.jobs._live

    took, row, live = run(root, scenario)
    assert took < 2 and live == {} and (row["state"], row["cost_usd"]) == ("killed", "unknown")


# ---------------------------------------------------------------- for hallux's own panel

def test_a_jobs_activity_has_its_lines_in_order_each_with_its_time(root):
    async def scenario(world):
        gates = [asyncio.Event() for _ in range(3)]
        pid = world.spawn(("status", "sketching the drums"), ("wait", gates[0]),
                          ("write", "midnight.score", "x"),
                          ("tool", "check", {"path": "midnight.score"}), ("wait", gates[1]),
                          ("back",), ("status", "balancing the mix"), ("wait", gates[2]))
        for seconds, gate in zip((2, 9, 20), gates):
            await asyncio.sleep(0.02)
            world.now += seconds
            gate.set()
        await world.ended(pid)
        return [(round(line.at), line.kind, line.text) for line in world.jobs.kept[0].activity]

    assert run(root, scenario) == [(0, "status", "sketching the drums"),
                                   (2, "check", "midnight.score"),
                                   (11, "status", "balancing the mix"),
                                   (31, "end", "done: midnight.score")]


def test_the_activity_keeps_the_last_two_hundred_lines_and_they_are_clean(root):
    async def scenario(world):
        pid = world.spawn(*[("status", f"line {n}") for n in range(ACTIVITY_MAX)],
                          ("status", "red ␛[31malert"), ("end", Outcome(ok=False, why="broke")))
        await world.ended(pid)
        return [line.text for line in world.jobs.kept[0].activity]

    lines = run(root, scenario)
    assert len(lines) == ACTIVITY_MAX == 200
    assert lines[0] == "line 2"                          # the oldest went first
    assert lines[-2:] == ["red alert", "failed: broke"]


def test_an_ended_job_is_kept_after_the_table_dropped_it_and_after_a_reboot(root):
    async def scenario(world):
        await world.ended(world.spawn(("status", "done with it")))
        world.jobs.table()                               # the main agent has seen it
        await world.jobs.end_boot()                      # and the boot is over
        return world.jobs.table(), [(job.pid, job.state, job.status, len(job.activity))
                                    for job in world.jobs.kept]

    assert run(root, scenario) == ([], [(30001, "done", "done with it", 2)])


def test_the_line_for_a_jobs_end_says_what_landed_or_why_not(root, music):
    async def scenario(world):
        gate = asyncio.Event()
        await world.ended(world.spawn())
        await world.ended(world.spawn(("write", "a.score", "x"), ("write", "b.score", "y")))
        conflict = world.spawn(("write", "neon.score", "z"), ("wait", gate),
                               edit=[f"{HERE}/neon.score"])
        await world.until(lambda: len(world.workers) == 3 and world.workers[2].job.disk.written())
        (music / "neon.score").write_text("changed by the user\n")
        gate.set()
        await world.ended(conflict)
        killed = world.spawn(("wait", asyncio.Event()))
        await world.until(lambda: len(world.workers) == 4)
        world.jobs.kill(killed)
        await world.ended(killed)
        return [job.activity[-1].text for job in world.jobs.kept]

    assert run(root, scenario) == [
        "done: nothing written", "done: a.score, b.score",
        "done: neon.score.new (neon.score was changed meanwhile)", "killed: kill"]


# ---------------------------------------------------------------- the caps

def test_two_jobs_run_and_a_third_waits_for_one_to_end(root):
    async def scenario(world):
        gate = asyncio.Event()
        tried = [world.tries(("wait", gate)), world.tries(("wait", asyncio.Event()), addon=MAIL),
                 world.tries(addon=GUI)]                 # agent_max_running is 2
        why = world.jobs.why_not(GUI)
        gate.set()
        await world.ended(tried[0])
        return tried, why, world.tries(addon=GUI), world.jobs.table()

    tried, why, then, table = run(root, scenario)
    assert tried == [30001, 30002, "EAGAIN"] and why == "too many jobs"
    assert then == 30003                                 # a refusal used up no pid
    assert [row["pid"] for row in table] == [30001, 30002, 30003]        # and left no row
    assert not (root / ".hallux").exists()               # nor a folder of copies


def test_with_no_agents_at_once_every_start_is_refused(root):
    async def scenario(world):
        off = [world.tries(), world.tries(addon=MAIL)], world.jobs.why_not(MUSIC)
        world.hardware = ROOMY                           # a change acts on the next spawn
        return off, world.tries(), world.jobs.why_not(MAIL)

    off, then, why = run(root, scenario, Hardware(agent_max_running=0))
    assert off == (["EAGAIN", "EAGAIN"], "agents are off")
    assert then == 30001 and why is None
    assert not (root / ".hallux").exists()               # a refusal makes no folder of copies


def test_one_job_of_an_addons_agent_at_a_time(root):
    async def scenario(world):
        gate = asyncio.Event()
        first = world.tries(("wait", gate))
        second, why = world.tries(), world.jobs.why_not(MUSIC)
        other = world.jobs.why_not(MAIL)                 # another addon's agent may start
        gate.set()
        await world.ended(first)
        return first, second, why, other, world.tries()

    assert run(root, scenario) == (30001, "EAGAIN", "already running", None, 30002)


def test_the_budget_for_all_jobs_is_never_passed(root):
    """With the defaults, $1.00 a job and $2.00 for all: a job that runs counts with its full
    cap, one that has ended with what it cost, and the one that asks with its full cap."""
    async def scenario(world):
        seen = [world.tries(("end", CHEAP)), world.tries(("end", CHEAP), addon=MAIL)]   # 1 + 1
        await world.ended(30001), await world.ended(30002)                  # both cost $0.30
        seen.append(world.tries(("wait", asyncio.Event())))                 # 0.60 + 1.00
        seen += [world.tries(addon=MAIL), world.jobs.why_not(MAIL)]         # 0.60 + 1.00 + 1.00
        world.jobs.refill()                                                 # 0 + 1.00 + 1.00
        return seen, world.tries(addon=MAIL), world.jobs.spent_since_refill

    seen, after_the_refill, counted = run(root, scenario, Hardware())
    assert seen == [30001, 30002, 30003, "EAGAIN", "jobs budget used"]
    assert after_the_refill == 30004 and counted == 0.0


def test_a_killed_job_counts_with_its_full_cap_until_its_cost_arrives(root):
    async def scenario(world):
        cost_arrives = asyncio.Event()
        pid = world.tries(("wait", asyncio.Event()), lingers=cost_arrives)
        await world.until(lambda: world.workers)
        world.jobs.kill(pid)
        await asyncio.sleep(0.02)
        meanwhile = [world.jobs.why_not(MAIL), world.jobs.why_not(MUSIC),
                     world.row(pid)["state"], world.jobs.spent_since_refill]
        cost_arrives.set()
        await world.ended(pid)
        return meanwhile, world.jobs.why_not(MAIL), world.jobs.spent_since_refill

    meanwhile, then, counted = run(root, scenario, Hardware(agent_budget_usd=1.5))
    assert meanwhile == ["jobs budget used", "already running", "killed", 0.0]   # 1.00 + 1.00
    assert then is None and counted == 0.07              # 0.07 + 1.00 fits into 1.50


def test_a_job_whose_cost_isnt_known_counts_with_its_full_cap_for_good(root):
    async def scenario(world):
        pid = world.tries(("wait", asyncio.Event()), stopped=Outcome(ok=False))
        await world.until(lambda: world.workers)
        world.jobs.kill(pid)
        await world.ended(pid)
        return world.jobs.spent, world.jobs.spent_boot, world.jobs.why_not(MAIL)

    assert run(root, scenario, Hardware()) == (1.0, 1.0, None)      # 1.00 + 1.00 just fits
    assert run(root, scenario, Hardware(agent_budget_usd=1.99))[2] == "jobs budget used"


def test_over_the_boots_budget_no_job_starts(root):
    async def scenario(world):
        world.boot_over = True
        refused_ = world.tries(), world.jobs.why_not(MUSIC)
        world.boot_over = False                          # the cap was raised
        return refused_, world.tries()

    assert run(root, scenario) == (("EAGAIN", "boot budget used"), 30001)


@pytest.mark.parametrize("hardware, words", [
    (Hardware(agent_max_running=0), "agents are off"),
    (Hardware(agent_budget_usd=0), "agents are off"),    # that turns them off too
    (Hardware(agent_max_running=1), "too many jobs"),
    (Hardware(agent_budget_usd=1.5), "jobs budget used"),
    (Hardware(), None),
])
def test_why_an_agent_cant_start_is_the_check_spawn_makes(root, hardware, words):
    async def scenario(world):
        world.hardware = Hardware()                      # one job of another addon runs
        world.tries(("wait", asyncio.Event()))
        world.hardware = hardware
        before = world.jobs.table()
        return world.jobs.why_not(MAIL), world.tries(addon=MAIL), before, world.jobs.table()

    why, tried, before, after = run(root, scenario)
    assert why == words and (tried == "EAGAIN") == (words is not None)
    assert len(after) - len(before) == (words is None)   # asking started nothing


def test_the_jobs_dollars_are_a_sum_of_their_own(root):
    async def scenario(world):
        for addon in (MUSIC, MAIL):
            await world.ended(world.spawn(("end", CHEAP), addon=addon, folder="/tmp/work"))
        first_boot = world.jobs.spent, world.jobs.spent_boot, world.jobs.spent_since_refill
        running = world.spawn(("wait", asyncio.Event()), folder="/tmp/work")
        await world.until(lambda: len(world.workers) == 3)
        await world.jobs.end_boot()                      # its cost is read: it counts in this boot
        ended = world.jobs.spent, world.jobs.spent_boot
        world.jobs.new_boot()
        return first_boot, running, ended, (world.jobs.spent, world.jobs.spent_boot,
                                            world.jobs.spent_since_refill)

    first_boot, _, ended, next_boot = run(root, scenario)
    assert first_boot == (0.6, 0.6, 0.6)
    assert [round(amount, 2) for amount in ended] == [0.67, 0.67]
    assert round(next_boot[0], 2) == 0.67 and next_boot[1:] == (0.0, 0.0)

