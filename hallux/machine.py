"""The machine: one Claude agent session per boot, wired to a terminal.

The terminal side only reads keys and writes the AI's text. It never draws a character
of the machine's screen itself; see docs/concept.md, "The terminal". Its one exception is
hallux's own status bar on the bottom row, which the AI is never told about.
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

from hallux import config, sandbox
from hallux.addons import Addon, Events, stop_all
from hallux.config import Hardware
from hallux.disk import Disk
from hallux.passwords import Passwords
from hallux.protocol import (
    Action, Field, Form, Reply, ScreenStream, Secret, envelope, json_body, parse, resolve,
)
from hallux.statusbar import describe
from hallux.tools import SERVER, build_addon_servers, build_server

log = logging.getLogger("hallux")
SYSTEM_PROMPT = (files("hallux") / "prompt.md").read_text(encoding="utf-8")


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

    async def end_form(self) -> None: ...

    def field_text(self, id: str) -> str: ...

    def field_saved(self, id: str) -> None: ...


class Machine:
    def __init__(self, root: Path, hardware: Hardware, terminal: Terminal,
                 client_factory: Callable[..., ClaudeSDKClient] = ClaudeSDKClient,
                 addons: Sequence[Addon] = (), events: Events | None = None,
                 from_flags: Iterable[str] = ()):
        self.disk = Disk(root)
        self.hardware = hardware                 # the settings as they are now
        self.running = hardware                  # the settings this boot's session started with
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
        self.fields: dict[str, Field] = {}       # block mode: the fields on screen now
        self.in_form = False                     # a full-screen program is on screen
        self.tick_spent = 0.0                    # raw mode: dollars spent on ticks this run
        self.last_turn_cost = 0.0
        self.stream: ScreenStream | None = None  # what the last answer showed while written

    # ---------------------------------------------------------------- for hallux's own panel

    def view(self) -> config.View:
        """What the panel shows: the settings, and how far the budgets are."""
        paused = {"event_budget_usd": self.events.paused,
                  "tick_budget_usd": "tick_budget_usd" in self.notes}
        return config.View(
            hardware=self.hardware, running=self.running, spent_boot=self.session_spent,
            spent_ticks=self.tick_spent if self.in_form else None, spent_events=self.event_spent,
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
        self.hardware = dataclasses.replace(self.hardware, **{name: value})
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
        log.info("budgets refilled: events $%.2f, ticks $%.2f", self.event_spent, self.tick_spent)
        self.event_spent = self.tick_spent = 0.0
        self.settle()
        return "budgets refilled"

    # ---------------------------------------------------------------- the machine itself

    def options(self) -> ClaudeAgentOptions:
        server, allowed = build_server(self.disk, fields=self.terminal, addons=self.addons,
                                       events=self.events)
        addon_servers, addon_tools = build_addon_servers(self.addons, self.disk)
        hw = self.hardware
        return ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            model=hw.model,
            effort=hw.model_effort,
            fallback_model=hw.fallback_model,
            max_budget_usd=hw.max_budget_usd,
            mcp_servers={SERVER: server} | addon_servers,
            strict_mcp_config=True,             # no MCP servers from your own Claude config
            tools=[],                           # no built-in Bash/Read/Write/... at all
            allowed_tools=allowed + addon_tools,
            permission_mode="dontAsk",          # anything not allowed above is denied
            setting_sources=[],                 # ignore your CLAUDE.md and settings
            include_partial_messages=True,      # the answer as it's written, for streaming
            # hallux.log has everything; Claude Code needn't keep its own transcript, which
            # would also show hallux sessions in your `claude --resume` list
            extra_args={} if hw.keep_transcripts else {"no-session-persistence": None},
            cli_path=sandbox.wrapper(self.disk.hidden) if hw.os_sandbox else None,
        )

    async def run(self) -> None:
        """Power on, reboot as often as the machine asks, return when it halts."""
        await self.terminal.start()
        try:
            while await self.power_on():
                log.info("reboot")
        finally:
            self.terminal.stop()

    async def power_on(self) -> bool:
        """One boot-to-shutdown lifetime. Returns True if the machine wants to reboot."""
        self.disk.cwd = "/"
        self.session_spent = 0.0
        self.forget_events()
        self.note("event_budget_usd", None)      # a new boot: nothing is heard, nothing paused
        self.running = self.hardware             # the bar shows what runs, not what is set
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
                    events = [] if secret else self.events.take()   # none at a password prompt
                    try:
                        if events:
                            line = None          # they come before the keyboard is read again
                        elif secret:
                            line = await self.terminal.read_secret(self.prompt)
                        else:
                            line = await self.read_shell_line(restore)
                    except EOFError:
                        line = Key("C-d", "", keep_line=False)
                    except KeyboardInterrupt:
                        line = Key("C-c", "", keep_line=False)
                    if events:                   # the line to put back stays as it is
                        reply = await self.send_events(client, events)
                    elif isinstance(line, Interrupted):
                        restore = line.line      # an event ended the read: it's sent next
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
            finally:                             # halt, reboot or a crash
                await self.terminal.end_form()
                self.stop_addons()
                self.forget_events()

    async def read_shell_line(self, restore: str) -> str | Key | Interrupted:
        """Read a line at the shell prompt. While the AI listens to an addon, an event ends
        the read, and what was typed so far comes back as Interrupted."""
        if not self.events.listening():          # nothing can arrive: the AI isn't at work
            return await self.terminal.read_line(self.prompt, restore)
        loop = asyncio.get_running_loop()
        reading = True

        def wake() -> None:
            if reading and not self.terminal.interrupt_prompt():
                loop.call_later(0.01, wake)      # the prompt isn't up yet: try again

        self.events.on_arrival = lambda: loop.call_soon_threadsafe(wake)
        if self.events.pending():                # one slipped in before anyone watched
            loop.call_soon(wake)
        try:
            return await self.terminal.read_line(self.prompt, restore)
        finally:
            reading = False
            self.events.on_arrival = None

    async def send_events(self, client: ClaudeSDKClient, events: list[tuple[str, dict]]) -> Reply:
        """Tell the AI what the addons it listens to have reported, oldest first."""
        body = "".join(f"\n{envelope('event', json_body(data), addon=name)}"
                       for name, data in events) + "\n"
        names = ", ".join(sorted({name for name, _ in events}))
        before = self.spent
        reply = await self.send(client, "events", body, activity=f"{names}: event")
        self.event_spent += self.spent - before
        self.check_events()
        return reply

    def check_events(self) -> None:
        """What the hub had to drop goes onto the bar. And events are model calls that nobody
        typed for: once they have used up their budget, they stop until a line is typed."""
        self.notify(self.events.take_notes())
        budget = self.hardware.event_budget_usd
        if self.events.listening() and not self.events.paused and self.event_spent >= budget:
            self.events.pause()
            log.warning("%s ($%.2f of $%.2f)", self.events_note(), self.event_spent, budget)
            self.notify([self.events_note()], "event_budget_usd")

    def events_note(self) -> str:
        """Why the events are paused, for the bar."""
        return ("events paused: budget used" if self.hardware.event_budget_usd
                else "events are off: event_budget_usd is 0")

    def refill_event_budget(self) -> None:
        """The user typed a line: somebody is at the keyboard, so events may spend again."""
        self.event_spent = 0.0
        self.settle()

    def settle(self) -> None:
        """Put the machine in line with its settings: lift a pause whose budget allows it
        again, and pause what is over its budget."""
        hw = self.hardware
        if self.events.paused and self.event_spent < hw.event_budget_usd:
            self.events.pause(False)
            self.note("event_budget_usd", None)
        elif self.events.paused:
            self.note("event_budget_usd", self.events_note())    # "used" may now be "off"
        if self.tick_spent < hw.tick_budget_usd:
            self.note("tick_budget_usd", None)   # the program ticks again with its next screen
        self.check_events()

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
        if form.tick and self.tick_spent >= self.hardware.tick_budget_usd:
            form = dataclasses.replace(form, tick=0)             # live updates stop here
            self.note("tick_budget_usd", "live updates paused: tick budget used")
        self.fields = {field.id: field for field in form.fields}
        self.in_form = True
        await self.terminal.show_form(reply.screen, form, reply.patch)
        try:
            action = await self.terminal.next_action()
        except EOFError:                          # the full-screen app died: back to the shell
            log.error("block mode ended unexpectedly")
            await self.leave_block_mode()
            return await self.send(client, "key", "", name="C-c")
        if action.key == "tick":                  # raw mode: time passed, nothing was pressed
            reply = await self.send(client, "tick", activity="updating…")
            self.tick_spent += self.last_turn_cost
            return reply
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
                   **attrs: object) -> Reply:
        """Send one envelope and show the reply: a screen and a prompt, or a form."""
        text, interrupted = await self.exchange(client, self.envelope(tag, body, **attrs),
                                                activity, fatal)
        if interrupted:                          # Ctrl-C while the AI was working
            text, _ = await self.exchange(
                client, self.envelope("key", "", name="C-c", interrupted="yes"), activity, fatal)
        if text is None:                         # the model failed; the error is reported
            if fatal:
                raise SystemExit(1)
            await self.leave_block_mode()        # never leave anyone stuck in a form
            return Reply(screen="", prompt=None, halt=halt_on_error)
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
        await self.terminal.end_form()

    def envelope(self, tag: str, body: str = "", **attrs: object) -> str:
        cols, rows = self.terminal.size()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
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
        finally:
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                loop.remove_signal_handler(signal.SIGINT)
        if result is not None:
            session_total = result.total_cost_usd or self.session_spent
            turn_cost = self.last_turn_cost = session_total - self.session_spent
            self.session_spent = session_total
            self.spent += turn_cost
            self.terminal.set_status(cost=self.spent, seconds=result.duration_ms / 1000)
        self.show_listening()                    # the AI may just have called addon_listen
        self.check_events()
        if result is None or (result.is_error and not interrupted):
            self.hardware_error(result, fatal)
            return None, interrupted
        log.info("<< %s", result.result)
        log.info("   %s, %d turns, %.1fs, $%.4f (this boot $%.4f)", result.subtype,
                 result.num_turns, result.duration_ms / 1000, turn_cost, self.session_spent)
        return result.result or "", interrupted

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
