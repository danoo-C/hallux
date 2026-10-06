"""The machine: one Claude agent session per boot, wired to a terminal.

The terminal side only reads keys and writes the AI's text. It never draws a character
of the machine's screen itself; see docs/concept.md, "The terminal". It has two things of
its own, which the AI is never told about: hallux's status bar on the bottom row, and
hallux's panel (hallux.panel), which Ctrl+F12 puts over the screen for as long as it is
open. The machine provides what the panel shows and does: view, change, save and refill.
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import signal
import sys
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import AsyncContextManager, Callable, Iterable, Protocol, Sequence

from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, StreamEvent, ToolUseBlock,
)

from hallux import config
from hallux.addons import Addon, Events, stop_all
from hallux.agents import Job, JobEvent, Jobs, Session, Worker, shared_options
from hallux.config import Hardware
from hallux.disk import Disk
from hallux.passwords import Passwords
from hallux.protocol import (
    Action, Field, Form, Reply, ScreenStream, Secret, envelope, json_body, parse, resolve,
)
from hallux.statusbar import PANEL_KEY, Running, describe
from hallux.tools import SERVER, build_addon_servers, build_server

log = logging.getLogger("hallux")
SYSTEM_PROMPT = (files("hallux") / "prompt.md").read_text(encoding="utf-8")
JOBS_PROMPT = (files("hallux") / "prompt_jobs.md").read_text(encoding="utf-8")    # its last
                                                 # section, on a machine that can start a job
TICKS_PAUSED = "live updates paused: tick budget used"       # the bar's note for it


@dataclass(frozen=True)
class Key:
    """A key for the machine, pressed while a line was being typed (Ctrl-C, Tab, Ctrl-L...)."""
    name: str                    # "C-c", "Tab", "M-.", "F1"
    line: str                    # what was typed so far
    cursor: int = 0              # characters before the cursor
    keep_line: bool = True       # False for keys that end the line (Ctrl-C, Ctrl-D, Ctrl-Z)


@dataclass(frozen=True)
class Interrupted:
    """The prompt was ended from outside while a line was being typed: an addon has an event."""
    line: str                    # what was typed so far
    cursor: int = 0              # characters before the cursor


class Terminal(Protocol):
    status_bar: bool             # True: model errors go to the bar instead of stderr
    streams: bool                # True: show the AI's screen while it's being written
    attended: bool               # False: nobody is at the keyboard, so nobody can raise a budget

    async def start(self) -> None: ...

    def stop(self) -> None: ...

    async def read_line(self, prompt: str, default: str = "") -> str | Key | Interrupted:
        """Read one line, or return the key for the machine that interrupted typing."""

    def interrupt_prompt(self) -> bool:
        """End the shell prompt that is being read: read_line returns Interrupted. False, and
        nothing happens, when no shell prompt is being read."""

    async def read_secret(self, prompt: str) -> str | Key:
        """Read a password: nothing typed is shown or kept, and a key carries no text."""

    def write(self, text: str) -> None: ...

    def retract(self, text: str) -> None:
        """Take back text just written (a full-screen program's screen that was streamed)."""

    def size(self) -> tuple[int, int]: ...

    def busy(self, interrupt: Callable[[], None], activity: str = "thinking…") -> AsyncContextManager:
        """While the AI works: animate the bar, keep reading keys, call interrupt on Ctrl-C."""

    def set_status(self, **changes: object) -> None: ...

    # block mode: full-screen programs with editable fields (hallux.blockmode)
    async def show_form(self, screen: str, form: Form, patch: tuple | None = None) -> None:
        """Show a full-screen program; with a patch, only those rows of its screen change."""

    async def next_action(self) -> Action:
        """Wait for an action key or click. Raises EOFError if the form can't go on."""

    def keep_form(self, tick: float | None = None) -> None:
        """The action that came back isn't sent: the program stays as it is and takes keys
        again. With a tick, that is its tick from now on."""

    def set_tick(self, seconds: float) -> None:
        """Give the program on screen this tick; its clock starts again with it."""

    def wake_form(self) -> bool:
        """End the wait of a program without fields: next_action returns an action called
        wake. False, and nothing happens, in a program with fields and while the AI is busy
        with the screen."""

    async def end_form(self) -> None: ...

    def field_text(self, id: str) -> str: ...

    def field_saved(self, id: str) -> None: ...


def events_block(events: Sequence[JobEvent]) -> str:
    """The job events that go in front of a message, as the <events> the AI knows, on a line
    of their own. Nothing, without events."""
    if not events:
        return ""
    body = "".join(f"\n{envelope('event', json_body(event.data), addon=event.addon)}"
                   for event in events) + "\n"
    return envelope("events", body) + "\n"


class Machine:
    def __init__(self, root: Path, hardware: Hardware, terminal: Terminal,
                 client_factory: Callable[..., ClaudeSDKClient] = ClaudeSDKClient,
                 addons: Sequence[Addon] = (), events: Events | None = None,
                 from_flags: Iterable[str] = (),
                 worker_factory: Callable[[Job], Worker] | None = None):
        self.disk = Disk(root)
        self.hardware = hardware                 # the settings as they are now
        self.running = hardware                  # what this boot's session runs on: see power_on
        self.unsaved: dict[str, object] = {}     # changed in this run and not saved yet
        self.from_flags = set(from_flags)        # the settings a flag set for this run
        self.notes: dict[str, str] = {}          # what the bar's note says, by reason
        self.terminal = terminal
        self.client_factory = client_factory
        self.addons = tuple(addons)              # the real hardware attached to this machine
        self.events = events or Events()         # what the addons report, for the AI
        self.heard = ""                          # the addons listened to, as the bar shows them
        self.event_spent = 0.0                   # dollars spent on events since a line was typed
        self.passwords = Passwords(self.disk.hidden / "passwords.json")
        self.prompt = ""
        self.secret: Secret | None = None        # the prompt asks for a password
        self.spent = 0.0                         # dollars, all boots
        self.session_spent = 0.0                 # dollars, this boot (the SDK reports a total)
        self.refilled_at = 0.0                   # of those, spent before the budgets were refilled
        self.fields: dict[str, Field] = {}       # block mode: the fields on screen now
        self.in_form = False                     # a full-screen program is on screen
        self.tick_spent = 0.0                    # raw mode: dollars spent on ticks this run
        self.tick_asked = 0.0                    # the tick the program on screen asked for,
        self.ticks_stopped = False               # and whether a budget has stopped its ticks
        self.last_turn_cost = 0.0
        self.stream: ScreenStream | None = None  # what the last answer showed while written
        self.wake: Callable[[], None] | None = None     # ends the shell prompt, while one that
                                                 # an event may end is being read
        # The jobs of the addons' agents (hallux.agents). They read the settings as they are,
        # ask whether the boot is over its budget, and say when one of them reports or ends.
        # A job's worker is a Claude session of its own, unless a test hands in a stand-in.
        self.jobs = Jobs(self.disk, lambda: self.hardware, worker_factory or self.session,
                         on_report=self.job_reported, on_event=self.job_event_waits,
                         over_budget=self.over_budget, addons=self.addons,
                         running=lambda: self.running.model)

    # ---------------------------------------------------------------- for hallux's own panel

    def view(self) -> config.View:
        """What the panel shows: the settings, and how far the budgets are."""
        paused = {"max_budget_usd": self.over_budget(),
                  "event_budget_usd": "event_budget_usd" in self.notes,
                  "tick_budget_usd": "tick_budget_usd" in self.notes}
        return config.View(
            hardware=self.hardware, running=self.running, spent_boot=self.boot_spent(),
            spent_since_refill=self.boot_spent() - self.refilled_at,
            spent_ticks=self.tick_spent if self.in_form else None, spent_events=self.event_spent,
            spent_jobs=self.jobs.spent_since_refill,
            paused=frozenset(name for name, used_up in paused.items() if used_up),
            from_flags=frozenset(self.from_flags), unsaved=frozenset(self.unsaved),
            path=self.disk.root / config.CONFIG_FILE)

    def change(self, name: str, text: str) -> str | None:
        """A new value for a setting, as it was typed in the panel. Returns why it wasn't
        taken, or None."""
        try:
            value = config.typed(name, text)
        except ValueError as e:
            return str(e)
        old = getattr(self.hardware, name)
        if value == old:                         # Enter on a row that was left as it was
            return None
        changed = dataclasses.replace(self.hardware, **{name: value})
        if reason := config.check_together(changed, name):       # two that can't both hold
            return reason
        self.hardware = changed
        self.unsaved[name] = value
        self.from_flags.discard(name)            # the flag's value is gone for this run
        log.info("config: %s %s -> %s", name, old, value)
        self.settle()
        return None

    def save(self) -> str | None:
        """Write what was changed in this run into config.toml. Returns why it couldn't, or
        None."""
        try:
            config.save(self.disk.root, self.unsaved)
        except ValueError as e:
            return str(e)
        if self.unsaved:
            log.info("config saved: %s", ", ".join(self.unsaved))
        self.unsaved = {}
        return None

    def refill(self) -> str:
        """Start the counting of every budget anew, at the limits as they are. What was really
        spent stays on the bar. Returns a line for the panel."""
        log.info("budgets refilled: events $%.2f, ticks $%.2f, boot $%.2f, jobs $%.2f",
                 self.event_spent, self.tick_spent, self.boot_spent() - self.refilled_at,
                 self.jobs.spent_since_refill)
        self.event_spent = self.tick_spent = 0.0
        self.jobs.refill()
        self.refilled_at = self.boot_spent()     # the boot's cap counts from here
        self.settle()
        return "budgets refilled"

    # ---------------------------------------------------------------- the machine itself

    def options(self) -> ClaudeAgentOptions:
        server, allowed = build_server(self.disk, fields=self.terminal, addons=self.addons,
                                       events=self.events, jobs=self.jobs)
        addon_servers, addon_tools = build_addon_servers(self.addons, self.disk, self.jobs.spawn)
        hw = self.hardware
        return ClaudeAgentOptions(
            system_prompt=self.system_prompt(),
            model=hw.model,
            effort=hw.model_effort,
            fallback_model=hw.fallback_model,     # no max_budget_usd: hallux checks that itself
            mcp_servers={SERVER: server} | addon_servers,
            allowed_tools=allowed + addon_tools,
            **shared_options(hw, self.disk.hidden),     # what a job's session gets too
        )

    def system_prompt(self) -> str:
        """The prompt, and at its end the section on jobs for a machine that has an addon with
        an agent. Lines that only some machines get don't stand in the middle of it."""
        if not any(addon.agent for addon in self.addons):
            return SYSTEM_PROMPT
        return f"{SYSTEM_PROMPT.rstrip()}\n\n{JOBS_PROMPT}"

    def session(self, job: Job) -> Worker:
        """The worker of a job: a Claude session of its own, made as the machine's own is. It
        is told the model this boot really runs on, for a machine without agent_model."""
        return Session(job, lambda: self.running.model, self.client_factory)

    async def run(self) -> None:
        """Power on, reboot as often as the machine asks, return when it halts."""
        await self.terminal.start()
        self.jobs.start()                        # inside the loop: a job's worker runs in it
        try:
            while await self.power_on():
                log.info("reboot")
        finally:
            self.terminal.stop()

    async def power_on(self) -> bool:
        """One boot-to-shutdown lifetime. Returns True if the machine wants to reboot."""
        self.disk.cwd = "/"
        self.session_spent = self.refilled_at = 0.0
        self.jobs.new_boot()
        self.forget_events()
        for reason in ("event_budget_usd", "max_budget_usd", "model"):
            self.note(reason, None)              # a new boot: nothing spent, heard or waiting
        # What runs, which the bar shows: the settings the session starts with, and of the
        # effort what it really gets. A model that is switched to later keeps that effort.
        self.running = dataclasses.replace(self.hardware, effort=self.hardware.model_effort)
        self.terminal.set_status(model=self.running.model, effort=self.running.model_effort)
        async with self.client_factory(options=self.options()) as client:   # empty RAM
            try:
                body, first = self.boot_report()
                reply = await self.send(client, "boot", body, first="yes" if first else "no",
                                        fatal=True, activity="booting…", new_machine=first)
                restore = ""                     # the line to put back at the next prompt
                while not (reply.halt or reply.reboot):
                    if reply.form is not None:   # a full-screen program in block mode
                        reply = await self.block_mode(client, reply)
                        continue
                    secret = self.secret
                    self.check_events()
                    if self.hold() and not getattr(self.terminal, "attended", True):
                        log.info("halt: the budget is used, and a script can't raise it")
                        return False
                    events = [] if secret else self.events.take()   # none at a password prompt,
                    due = [] if secret else self.due()              # and no job's end by itself
                    try:
                        if events or due:
                            line = None          # they come before the keyboard is read again
                        elif secret:
                            line = await self.terminal.read_secret(self.prompt)
                        else:
                            line = await self.read_shell_line(restore)
                    except EOFError:
                        line = Key("C-d", "", keep_line=False)
                    except KeyboardInterrupt:
                        line = Key("C-c", "", keep_line=False)
                    if events or due:            # the line to put back stays as it is
                        reply = await self.send_events(client, events, due)
                    elif isinstance(line, Interrupted):
                        restore = line.line      # an event ended the read: it's sent next
                        continue
                    elif self.hold():            # the boot's budget is used: nothing is sent
                        if isinstance(line, Key) and line.name == "C-d":
                            log.info("halt: Ctrl-D, and the budget is used")
                            return False         # the way out of such a boot
                        if isinstance(line, Key):
                            restore = line.line if line.keep_line else ""
                        else:                    # the line comes back; a password never does
                            restore = "" if secret else line
                        continue
                    elif isinstance(line, Key):
                        self.passwords.cancel()
                        reply = await self.send(client, "key", line.line, name=line.name,
                                                cursor=line.cursor,
                                                halt_on_error=line.name == "C-d",
                                                **({"secret": secret.name} if secret else {}))
                        restore = line.line if line.keep_line else ""
                    elif secret:                 # a password: the AI hears only the verdict
                        self.refill_event_budget()
                        reply = await self.send(client, "input", **self.verdict(secret, line))
                        restore = ""
                    else:
                        self.passwords.cancel()
                        self.refill_event_budget()
                        reply = await self.send(client, "input", line)
                        restore = ""
                    if reply.edit is not None:   # the AI rewrote the line (Tab, Ctrl-R...)
                        restore = reply.edit
                return reply.reboot
            finally:                             # halt, reboot or a crash: a program that
                await self.leave_block_mode()    # is still on screen ends with the boot,
                await self.jobs.end_boot()       # and so does every job, before the addons'
                self.stop_addons()               # hooks: a job may be inside an addon function
                self.forget_events()

    async def read_shell_line(self, restore: str) -> str | Key | Interrupted:
        """Read a line at the shell prompt. While the AI listens to an addon, an event ends
        the read, and what was typed so far comes back as Interrupted: an addon's own event,
        or the end of one of its agent's jobs."""
        if not self.events.listening():          # nothing can arrive: the AI isn't at work,
            return await self.terminal.read_line(self.prompt, restore)     # and a job's end waits
        loop = asyncio.get_running_loop()
        reading = True

        def wake() -> None:
            if reading and not self.terminal.interrupt_prompt():
                loop.call_later(0.01, wake)      # the prompt isn't up yet: try again

        self.wake = wake
        self.events.on_arrival = lambda: loop.call_soon_threadsafe(wake)
        if self.events.pending() or self.due():  # one slipped in before anyone watched
            loop.call_soon(wake)
        try:
            return await self.terminal.read_line(self.prompt, restore)
        finally:
            reading = False
            self.wake = self.events.on_arrival = None

    async def send_events(self, client: ClaudeSDKClient, events: list[tuple[str, dict]],
                          due: Sequence[JobEvent] = (), stay: bool = False) -> Reply | None:
        """Tell the AI what the addons it listens to have reported, oldest first, and after
        that how its jobs ended: every job event that waits, also one that couldn't have gone
        out by itself. `due` are the ones this message is sent for. Each gets its mark: an
        event starts one message of its own, or a model that is down is called in a loop.
        `stay` is send()'s."""
        for event in due:
            event.had_turn = True
        ended = self.jobs.waiting()
        told = events + [(event.addon, event.data) for event in ended]
        body = "".join(f"\n{envelope('event', json_body(data), addon=name)}"
                       for name, data in told) + "\n"
        names = ", ".join(sorted({name for name, _ in told}))
        before = self.spent
        reply = await self.send(client, "events", body, activity=f"{names}: event",
                                carried=ended, stay=stay)
        self.event_spent += self.spent - before
        self.check_events()
        return reply

    def due(self) -> list[JobEvent]:
        """The job events that may go out by themselves now, in a message of their own. This
        one question decides both whether the prompt is ended for them and whether they are
        sent: if an event that has to wait counted as waiting, the prompt would be ended
        again and again. An event may go out when its addon is listened to, event budget is
        left, the boot isn't over its budget, and it hasn't had a message of its own yet."""
        if self.over_budget() or self.event_spent >= self.hardware.event_budget_usd:
            return []
        heard = self.events.listening()
        return [event for event in self.jobs.waiting()
                if event.addon in heard and not event.had_turn]

    def job_event_waits(self) -> None:
        """A job has ended, or something an event waited for has changed: a budget, the
        boot's cap. If an event may go out by itself now, whoever waits for the keyboard is
        woken. At the shell prompt the prompt ends, as it does for an addon's event. A
        full-screen program without fields is woken: a player would otherwise sit on
        "composing…" until a key is pressed. One with fields isn't: the wake would reach the
        AI without the fields, and its answer could lose what the user typed there."""
        if not self.due():
            return
        if self.wake is not None:
            self.wake()
        elif self.in_form and not self.fields:
            self.terminal.wake_form()            # no, while the AI is busy with the screen:
                                                 # block_mode looks again when it is shown

    def check_events(self) -> None:
        """What the hub had to drop goes onto the bar. And events are model calls that nobody
        typed for: once they have used up their budget, they stop until a line is typed."""
        self.notify(self.events.take_notes())
        budget = self.hardware.event_budget_usd
        if (self.events.listening() and self.event_spent >= budget
                and "event_budget_usd" not in self.notes):
            self.events.pause()
            log.warning("%s ($%.2f of $%.2f)", self.events_note(), self.event_spent, budget)
            self.notify([self.events_note()], "event_budget_usd")

    def events_note(self) -> str:
        """Why the events are paused, for the bar."""
        return ("events paused: budget used" if self.hardware.event_budget_usd
                else "events are off: event_budget_usd is 0")

    def refill_event_budget(self) -> None:
        """The user typed a line: somebody is at the keyboard, so events may spend again, and
        so may the addons' jobs."""
        self.event_spent = 0.0
        self.jobs.refill()
        self.settle()

    def settle(self) -> None:
        """Put the machine in line with its settings: lift a pause whose budget allows it
        again, and pause what is over its budget."""
        hw = self.hardware
        over, events_used = self.over_budget(), self.event_spent >= hw.event_budget_usd
        if not over:
            self.note("max_budget_usd", None)
        if not events_used:
            self.note("event_budget_usd", None)
        elif "event_budget_usd" in self.notes:
            self.note("event_budget_usd", self.events_note())    # "used" may now be "off"
        if self.events.paused and not over and not events_used:
            self.events.pause(False)
        if hw.model == self.running.model:
            self.note("model", None)             # no model waits to be switched to
        if not self.ticks_used_up():
            self.note("tick_budget_usd", None)
            if self.ticks_stopped and not over:  # both budgets allow it: the program on screen
                self.ticks_stopped = False       # ticks again, as it asked to
                self.terminal.set_tick(self.tick_asked)
        self.check_events()
        self.job_event_waits()                   # one that waited for a budget may go out now

    def boot_spent(self) -> float:
        """What this boot has spent: the main session, and each job once it has ended. The two
        are kept apart: an event's turn is measured as the change of the main session's sum."""
        return self.session_spent + self.jobs.spent_boot

    def over_budget(self) -> bool:
        """The boot has a cap, and has spent it since it started or since the last refill. A
        job that still runs isn't in it, so a boot can pass its cap by what its running jobs
        spend: at most the budget for all jobs."""
        cap = self.hardware.max_budget_usd
        return cap is not None and self.boot_spent() - self.refilled_at >= cap

    def job_reported(self) -> None:
        """A job reported or ended: the bar shows the jobs that run, and what those that have
        ended cost. That cost can take the boot over its cap while the machine sits at the
        prompt, where nothing else would ask: the bar says so at once, and not after the next
        line was typed into it."""
        self.show_jobs()
        if self.over_budget():
            self.hold()

    def show_jobs(self) -> None:
        """Tell the bar which jobs run, and the jobs' sum. The sum goes beside the main
        session's and not into it: a scripted run books every rise of the session's cost to
        the line that was typed last, and a job's cost would land on whatever that was.
        It is told at every report, also one that changes nothing on the bar: the terminal
        then draws again, and the panel's tabs show what a job says and does."""
        self.terminal.set_status(
            jobs=tuple(Running(job.addon.name, job.status, job.began, job.tokens)
                       for job in self.jobs.running()), jobs_cost=self.jobs.spent)

    def ticks_used_up(self) -> bool:
        """The program run has spent its tick budget. No tick goes to the AI, and every other
        message tells it so, until the budget allows ticks again or the program is left."""
        return self.tick_spent >= self.hardware.tick_budget_usd

    def hold(self) -> bool:
        """Asked before a message goes to the AI: True when it has to stay here, because the
        boot has used its budget. The bar says so, and events stop: nothing could go out for
        them, and each would only end the prompt."""
        if not self.over_budget():
            return False
        note = f"budget used: ${self.hardware.max_budget_usd:.2f} per boot"
        if getattr(self.terminal, "attended", True):             # somebody can raise it
            note += f" · raise it: {PANEL_KEY}"
        if self.notes.get("max_budget_usd") != note:             # said once
            log.warning("%s ($%.2f spent)", note, self.boot_spent() - self.refilled_at)
            self.notify([note], "max_budget_usd")
        self.events.pause()
        return True

    def notify(self, notes: list[str], reason: str = "reports") -> None:
        """Something the user should know, on the status bar. Without one, it's printed."""
        if notes:
            self.note(reason, " · ".join(notes))
            if not self.terminal.status_bar:
                for note in notes:
                    print(f"hallux: {note}", file=sys.stderr)

    def note(self, reason: str, text: str | None) -> None:
        """Put a note on the status bar for one reason, or take that reason's note away. The
        bar has one slot for notes: it shows all there are, and a note goes with its reason."""
        if self.notes.get(reason) == text:
            return
        if text is None:
            del self.notes[reason]
        else:
            self.notes[reason] = text
        self.terminal.set_status(note=" · ".join(self.notes.values()) or None)

    def forget_events(self) -> None:
        """A boot starts or ends: the AI listens to no addon, and no event waits for it."""
        self.event_spent = 0.0
        unheard = self.events.reset()
        if unheard:
            log.info("events nobody listened to: %s",
                     ", ".join(f"{name} {count}" for name, count in sorted(unheard.items())))
        self.show_listening()

    def show_listening(self) -> None:
        """Listening means money can be spent with nobody typing, so the bar says so."""
        heard = ", ".join(self.events.listening())
        if heard != self.heard:
            self.heard = heard
            self.terminal.set_status(listening=heard)

    def stop_addons(self) -> None:
        """The boot is over: whatever an addon started in it (a window, a sound) ends too."""
        self.notify(stop_all(self.addons))

    def verdict(self, secret: Secret, typed: str) -> dict[str, str]:
        """What the AI hears about a typed password: whether it's right, never what it is."""
        attrs = {"secret": secret.name}
        if secret.new:
            attrs["new"] = self.passwords.offer(secret.name, typed)
        else:
            attrs["match"] = self.passwords.check(secret.name, typed)
        if not typed:
            attrs["empty"] = "yes"
        return attrs

    def boot_report(self) -> tuple[str, bool]:
        """What <boot> carries: the memory, the machine's defining files and the list of its
        addons, so a normal boot needs no tools. A new machine (no memory yet) first gets an
        empty directory tree."""
        memory = self.disk.memory_read()["text"]
        first = not memory.strip()
        if first:
            self.disk.lay_skeleton()
        parts = [envelope("memory", "\n" + memory)] if not first else []
        parts += [envelope("file", text, path=path) for path, text in self.disk.boot_files().items()]
        if self.addons:
            listing = "".join(f"{addon.name}: {addon.summary}\n" for addon in self.addons)
            parts.append(envelope("addons", "\n" + listing))
        return "".join(f"\n{part}" for part in parts) + ("\n" if parts else ""), first

    async def block_mode(self, client: ClaudeSDKClient, reply: Reply) -> Reply:
        """Show the AI's form, let the user work in it, send back the action they end with."""
        form, to_load = resolve(reply.form, self.fields)
        form = self.load_files(form, to_load)
        held = self.hold()
        self.tick_asked = form.tick
        if form.tick and self.ticks_used_up():
            form = dataclasses.replace(form, tick=0)             # live updates stop here
            self.note("tick_budget_usd", TICKS_PAUSED)
        elif held:
            form = dataclasses.replace(form, tick=0)             # a tick couldn't be sent
        self.ticks_stopped = bool(self.tick_asked) and not form.tick
        self.fields = {field.id: field for field in form.fields}
        self.in_form = True
        await self.terminal.show_form(reply.screen, form, reply.patch)
        self.job_event_waits()                    # a job that ended while the AI answered: the
        while True:                               # wait below would never hear of it
            if held and not getattr(self.terminal, "attended", True):
                log.info("halt: the budget is used, and a script can't raise it")
                await self.leave_block_mode()
                return Reply(screen="", prompt=None, halt=True)
            try:
                action = await self.terminal.next_action()
            except EOFError:                      # the full-screen app died: back to the shell
                log.error("block mode ended unexpectedly")
                await self.leave_block_mode()
                return await self.send(client, "key", "", name="C-c")
            if action.key == "wake":              # a job's end, and nobody pressed a key
                # Asked again: the event may have gone out meanwhile, in front of a key.
                due = [] if self.fields else self.due()
                woken = await self.send_events(client, [], due, stay=True) if due else None
                if woken is not None:
                    return woken                  # the program's next screen, or its patch
                self.terminal.keep_form()         # nothing to send, or the model failed on
                continue                          # it: the program stays, and takes keys
            held = self.hold()
            late = action.key == "tick" and self.ticks_used_up()   # its budget was lowered
            if not held and not late:
                break
            self.terminal.keep_form(tick=0)       # not sent: the program stays, without ticks
            self.ticks_stopped = bool(self.tick_asked)
            if late:
                self.note("tick_budget_usd", TICKS_PAUSED)
        if action.key == "tick":                  # raw mode: time passed, nothing was pressed
            rows = self.jobs.table()              # with the jobs, while there are any: a
            reply = await self.send(              # program that shows them needs no tool call
                client, "tick", json_body({"jobs": rows}) if rows else "", activity="updating…")
            self.tick_spent += self.last_turn_cost
            return reply
        self.jobs.refill()                        # a key or an action: somebody is there
        if action.events:                         # raw mode: every key, as events
            return await self.send(client, "keys", "".join(action.events))
        attrs: dict[str, object] = {"key": action.key}
        if action.focus:
            attrs["focus"] = action.focus
        if action.row is not None:
            attrs |= {"row": action.row, "col": action.col}
        return await self.send(client, "action", self.field_report(action), **attrs)

    def load_files(self, form: Form, ids: set[str]) -> Form:
        """Fill these file="..." fields from the disk: the text never passes through the AI."""
        fields = []
        for field in form.fields:
            if field.id in ids:
                try:
                    field = dataclasses.replace(field, text=self.disk.read_text(field.file))
                except FileNotFoundError:
                    field = dataclasses.replace(field, text="")            # a new file
                except (OSError, ValueError) as e:
                    log.warning("can't load %s into a field: %s", field.file, e)
                    field = dataclasses.replace(field, text="")
            fields.append(field)
        return dataclasses.replace(form, fields=tuple(fields))

    @staticmethod
    def field_report(action: Action) -> str:
        """The fields as the user left them. Text the AI has already seen is left out."""
        parts = []
        for state in action.fields:
            attrs = {"id": state.id, "cursor": f"{state.cursor[0]}:{state.cursor[1]}",
                     "modified": "yes" if state.modified else "no"}
            if not state.changed:
                attrs["unchanged"] = "yes"
            parts.append(envelope("field", state.text if state.changed else "", **attrs))
        return "".join(f"\n{part}" for part in parts) + ("\n" if parts else "")

    async def send(self, client: ClaudeSDKClient, tag: str, body: str = "", *,
                   fatal: bool = False, halt_on_error: bool = False,
                   activity: str = "thinking…", new_machine: bool = False,
                   carried: list[JobEvent] | None = None, stay: bool = False,
                   **attrs: object) -> Reply | None:
        """Send one envelope and show the reply: a screen and a prompt, or a form.

        Every job event that waits goes along, as an <events> block in front of the message.
        It is told when the answer has come back: a message the model fails on leaves it
        waiting, for the next message of any kind. `carried` are the job events a message
        holds in its own body, which then gets no block. A boot has none: it starts with no
        jobs.

        A message the model fails on ends a full-screen program, so that nobody is stuck in
        it. With `stay` it doesn't, and None comes back: the message was one that nobody at
        the keyboard asked for, and a player isn't taken off the screen for it."""
        if carried is None:
            carried = [] if tag == "boot" else self.jobs.waiting()
            front = events_block(carried)
        else:
            front = ""
        text, interrupted = await self.exchange(
            client, front + self.envelope(tag, body, **attrs), activity, fatal)
        if interrupted:                          # Ctrl-C while the AI was working: nothing of
            carried = self.jobs.waiting()        # that answer was shown, so they go again
            text, _ = await self.exchange(
                client, events_block(carried)
                + self.envelope("key", "", name="C-c", interrupted="yes"), activity, fatal)
        if text is None:                         # the model failed; the error is reported
            if fatal:
                raise SystemExit(1)
            if stay:
                return None
            await self.leave_block_mode()        # never leave anyone stuck in a form
            return Reply(screen="", prompt=None, halt=halt_on_error)
        self.jobs.told(carried)
        reply = parse(text)
        shown = self.stream.shown if self.stream else ""
        self.apply_writes(reply, new_machine)
        if reply.cwd:                            # cd without a tool call (boot, cd ~)
            try:
                self.disk.chdir(reply.cwd)
            except (OSError, ValueError) as e:
                log.warning("can't change to %s: %s", reply.cwd, e)
        if reply.form is not None:               # block mode shows it; the shell prompt stays
            if shown:                            # a full-screen screen that streamed (the AI
                self.terminal.retract(shown)     # put the form last): take it back
            return reply
        await self.leave_block_mode()
        rest = self.stream.rest(reply.screen) if shown else None
        self.terminal.write(rest if rest is not None else reply.screen)
        if reply.prompt is not None:
            self.prompt, self.secret = reply.prompt, reply.secret
        else:
            log.warning("reply without <prompt>; keeping the previous prompt")
        return reply

    def apply_writes(self, reply: Reply, new_machine: bool = False) -> None:
        """Files (and, for a new machine, the whole memory) the AI wrote in its answer."""
        if reply.memory is not None:
            if new_machine:
                self.disk.memory_edit("", reply.memory)
            else:
                log.warning("ignored a whole new memory outside a first boot")
        for write in reply.files:
            try:
                self.disk.write_file(write.path, write.content, append=write.append, parents=True)
                log.info("   wrote %s (%d characters)", write.path, len(write.content))
            except (OSError, ValueError) as e:
                log.warning("can't write %s: %s", write.path, e)
                self.terminal.set_status(error=f"couldn't write {write.path}")

    async def leave_block_mode(self) -> None:
        self.note("tick_budget_usd", None)
        self.fields, self.in_form, self.tick_spent = {}, False, 0.0
        self.tick_asked, self.ticks_stopped = 0.0, False
        await self.terminal.end_form()

    def envelope(self, tag: str, body: str = "", **attrs: object) -> str:
        cols, rows = self.terminal.size()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        if self.ticks_used_up():                 # no tick comes, whatever the form asks for
            attrs["ticks"] = "paused"
        return envelope(tag, body, **attrs, cwd=self.disk.cwd, time=now, cols=cols, rows=rows)

    async def exchange(self, client: ClaudeSDKClient, message: str, activity: str = "thinking…",
                       fatal: bool = False) -> tuple[str | None, bool]:
        """One round trip. Returns (reply text or None on error, interrupted by Ctrl-C)."""
        log.info(">> %s", message)
        interrupted = False
        loop = asyncio.get_running_loop()

        def interrupt() -> None:
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                loop.create_task(client.interrupt())

        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.add_signal_handler(signal.SIGINT, interrupt)       # in case no raw keyboard
        result, tools = None, 0
        stream = self.stream = (ScreenStream() if getattr(self.terminal, "streams", False)
                                and not self.in_form else None)    # never under a form
        try:
            async with self.terminal.busy(interrupt, activity):
                await self.switch_model(client)
                await client.query(message)
                async for msg in client.receive_response():
                    if isinstance(msg, StreamEvent):
                        if stream is not None:
                            self.show_while_written(stream, msg.event)
                    elif isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, ToolUseBlock):
                                name = block.name.removeprefix(f"mcp__{SERVER}__")
                                log.info("   tool %s %s", name, block.input)
                                tools += 1
                                self.terminal.set_status(activity=describe(name, block.input),
                                                         tools=tools)
                    elif isinstance(msg, ResultMessage):
                        result = msg
                        # Counted here, inside the answer: its end may wait for the panel,
                        # and the panel shows what was spent.
                        session_total = result.total_cost_usd or self.session_spent
                        self.last_turn_cost = session_total - self.session_spent
                        self.session_spent = session_total
                        self.spent += self.last_turn_cost
                        self.terminal.set_status(cost=self.spent,
                                                 seconds=result.duration_ms / 1000)
        finally:
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                loop.remove_signal_handler(signal.SIGINT)
        self.show_listening()                    # the AI may just have called addon_listen
        self.check_events()
        if result is None or (result.is_error and not interrupted):
            self.hardware_error(result, fatal)
            return None, interrupted
        log.info("<< %s", result.result)
        log.info("   %s, %d turns, %.1fs, $%.4f (this boot $%.4f)", result.subtype,
                 result.num_turns, result.duration_ms / 1000, self.last_turn_cost,
                 self.session_spent)
        return result.result or "", interrupted

    async def switch_model(self, client: ClaudeSDKClient) -> None:
        """A model that was set in the panel runs from the next answer: the session is
        switched just before a message goes out, never while an answer is written. A switch
        that fails leaves the session as it is, and is tried again with the next message."""
        old, new = self.running.model, self.hardware.model
        if new == old:
            return
        try:
            await client.set_model(new)
        except Exception as e:                   # the SDK's own: "Model 'x' not found"
            note = f"model not switched: {e}"
            if self.notes.get("model") != note:  # said once
                log.warning("%s (it stays %s)", note, old)
                self.notify([note], "model")
            return
        self.running = dataclasses.replace(self.running, model=new)
        log.info("model: %s -> %s", old, new)
        self.note("model", None)
        self.terminal.set_status(model=new, effort=self.running.model_effort)

    def show_while_written(self, stream: ScreenStream, event: dict) -> None:
        """Streaming: print the screen as the AI writes it."""
        if event.get("type") == "content_block_start":
            if event.get("content_block", {}).get("type") == "text":
                stream.new_block()
        elif event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta" and (text := stream.feed(delta.get("text", ""))):
                if stream.shown == text:         # the first piece
                    self.terminal.set_status(activity="writing…")
                self.terminal.write(text)

    def hardware_error(self, result: ResultMessage | None, fatal: bool = False) -> None:
        """The model couldn't be reached. That's shown on the status bar, not the screen."""
        if result is None:
            detail = "no reply"
        else:
            detail = "; ".join(result.errors or []) or result.result or result.subtype
            if result.api_error_status:
                detail = f"{detail} (HTTP {result.api_error_status})"
        log.error("model error: %s", detail)
        self.terminal.set_status(error=detail)
        if fatal or not self.terminal.status_bar:
            print(f"hallux: the model failed ({detail})", file=sys.stderr)
