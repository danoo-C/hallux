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
from typing import AsyncContextManager, Callable, Protocol

from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, ToolUseBlock,
)

from hallux.config import Hardware
from hallux.disk import Disk
from hallux.protocol import Action, Field, Form, Reply, envelope, parse, resolve
from hallux.statusbar import describe
from hallux.tools import SERVER, build_server

log = logging.getLogger("hallux")
SYSTEM_PROMPT = (files("hallux") / "prompt.md").read_text(encoding="utf-8")


@dataclass(frozen=True)
class Key:
    """A key for the machine, pressed while a line was being typed (Ctrl-C, Tab, Ctrl-L...)."""
    name: str                    # "C-c", "Tab", "M-.", "F1"
    line: str                    # what was typed so far
    cursor: int = 0              # characters before the cursor
    keep_line: bool = True       # False for keys that end the line (Ctrl-C, Ctrl-D, Ctrl-Z)


class Terminal(Protocol):
    status_bar: bool             # True: model errors go to the bar instead of stderr

    async def start(self) -> None: ...

    def stop(self) -> None: ...

    async def read_line(self, prompt: str, default: str = "") -> str | Key:
        """Read one line, or return the key for the machine that interrupted typing."""

    def write(self, text: str) -> None: ...

    def size(self) -> tuple[int, int]: ...

    def busy(self, interrupt: Callable[[], None], activity: str = "thinking…") -> AsyncContextManager:
        """While the AI works: animate the bar, keep reading keys, call interrupt on Ctrl-C."""

    def set_status(self, **changes: object) -> None: ...

    # block mode: full-screen programs with editable fields (hallux.blockmode)
    async def show_form(self, screen: str, form: Form) -> None: ...

    async def next_action(self) -> Action:
        """Wait for an action key or click. Raises EOFError if the form can't go on."""

    async def end_form(self) -> None: ...

    def field_text(self, id: str) -> str: ...

    def field_saved(self, id: str) -> None: ...


class Machine:
    def __init__(self, root: Path, hardware: Hardware, terminal: Terminal,
                 client_factory: Callable[..., ClaudeSDKClient] = ClaudeSDKClient):
        self.disk = Disk(root)
        self.hardware = hardware
        self.terminal = terminal
        self.client_factory = client_factory
        self.prompt = ""
        self.spent = 0.0                         # dollars, all boots
        self.session_spent = 0.0                 # dollars, this boot (the SDK reports a total)
        self.fields: dict[str, Field] = {}       # block mode: the fields on screen now

    def options(self) -> ClaudeAgentOptions:
        server, allowed = build_server(self.disk, fields=self.terminal)
        hw = self.hardware
        return ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            model=hw.model,
            effort=hw.model_effort,
            fallback_model=hw.fallback_model,
            max_budget_usd=hw.max_budget_usd,
            mcp_servers={SERVER: server},
            strict_mcp_config=True,             # no MCP servers from your own Claude config
            tools=[],                           # no built-in Bash/Read/Write/... at all
            allowed_tools=allowed,
            permission_mode="dontAsk",          # anything not allowed above is denied
            setting_sources=[],                 # ignore your CLAUDE.md and settings
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
        async with self.client_factory(options=self.options()) as client:   # empty RAM
            try:
                reply = await self.send(client, "boot", fatal=True, activity="booting…")
                restore = ""                     # the line to put back at the next prompt
                while not (reply.halt or reply.reboot):
                    if reply.form is not None:   # a full-screen program in block mode
                        reply = await self.block_mode(client, reply)
                        continue
                    try:
                        line = await self.terminal.read_line(self.prompt, restore)
                    except EOFError:
                        line = Key("C-d", "", keep_line=False)
                    except KeyboardInterrupt:
                        line = Key("C-c", "", keep_line=False)
                    if isinstance(line, Key):
                        reply = await self.send(client, "key", line.line, name=line.name,
                                                cursor=line.cursor,
                                                halt_on_error=line.name == "C-d")
                        restore = line.line if line.keep_line else ""
                    else:
                        reply = await self.send(client, "input", line)
                        restore = ""
                    if reply.edit is not None:   # the AI rewrote the line (Tab, Ctrl-R...)
                        restore = reply.edit
                return reply.reboot
            finally:
                await self.terminal.end_form()

    async def block_mode(self, client: ClaudeSDKClient, reply: Reply) -> Reply:
        """Show the AI's form, let the user work in it, send back the action they end with."""
        form, to_load = resolve(reply.form, self.fields)
        form = self.load_files(form, to_load)
        self.fields = {field.id: field for field in form.fields}
        await self.terminal.show_form(reply.screen, form)
        try:
            action = await self.terminal.next_action()
        except EOFError:                          # the full-screen app died: back to the shell
            log.error("block mode ended unexpectedly")
            await self.leave_block_mode()
            return await self.send(client, "key", "", name="C-c")
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
                   activity: str = "thinking…", **attrs: object) -> Reply:
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
        if reply.form is not None:               # block mode shows it; the shell prompt stays
            return reply
        await self.leave_block_mode()
        self.terminal.write(reply.screen)
        if reply.prompt is not None:
            self.prompt = reply.prompt
        else:
            log.warning("reply without <prompt>; keeping the previous prompt")
        return reply

    async def leave_block_mode(self) -> None:
        self.fields = {}
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
        try:
            async with self.terminal.busy(interrupt, activity):
                await client.query(message)
                async for msg in client.receive_response():
                    if isinstance(msg, AssistantMessage):
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
            turn_cost = session_total - self.session_spent
            self.session_spent = session_total
            self.spent += turn_cost
            self.terminal.set_status(cost=self.spent, seconds=result.duration_ms / 1000)
        if result is None or (result.is_error and not interrupted):
            self.hardware_error(result, fatal)
            return None, interrupted
        log.info("<< %s", result.result)
        log.info("   %s, %d turns, %.1fs, $%.4f (this boot $%.4f)", result.subtype,
                 result.num_turns, result.duration_ms / 1000, turn_cost, self.session_spent)
        return result.result or "", interrupted

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
