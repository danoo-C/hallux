"""The machine: one Claude agent session per boot, wired to a terminal.

The terminal side only reads keys and writes the AI's text. It never draws a character
of its own; see docs/concept.md, "The terminal".
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Callable, Protocol

from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, ToolUseBlock,
)

from hallux.config import Hardware
from hallux.disk import Disk
from hallux.protocol import Reply, envelope, parse
from hallux.tools import SERVER, build_server

log = logging.getLogger("hallux")
SYSTEM_PROMPT = (files("hallux") / "prompt.md").read_text(encoding="utf-8")


@dataclass(frozen=True)
class Key:
    """A key the terminal hands to the AI while a line is being typed (Ctrl-L)."""
    name: str
    line: str


class Terminal(Protocol):
    async def read_line(self, prompt: str, default: str = "") -> str | Key:
        """Read one line. Raises EOFError on Ctrl-D and KeyboardInterrupt on Ctrl-C."""

    def write(self, text: str) -> None: ...

    def size(self) -> tuple[int, int]: ...


class Machine:
    def __init__(self, root: Path, hardware: Hardware, terminal: Terminal,
                 client_factory: Callable[..., ClaudeSDKClient] = ClaudeSDKClient):
        self.disk = Disk(root)
        self.hardware = hardware
        self.terminal = terminal
        self.client_factory = client_factory
        self.prompt = ""

    def options(self) -> ClaudeAgentOptions:
        server, allowed = build_server(self.disk)
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
        while await self.power_on():
            log.info("reboot")

    async def power_on(self) -> bool:
        """One boot-to-shutdown lifetime. Returns True if the machine wants to reboot."""
        self.disk.cwd = "/"
        async with self.client_factory(options=self.options()) as client:   # empty RAM
            reply = await self.send(client, "boot", fatal=True)
            restore = ""                         # the line to put back after Ctrl-L
            while not (reply.halt or reply.reboot):
                try:
                    line = await self.terminal.read_line(self.prompt, restore)
                except EOFError:
                    reply = await self.send(client, "eof", halt_on_error=True)
                    continue
                except KeyboardInterrupt:
                    restore = ""
                    reply = await self.send(client, "signal", "SIGINT")
                    continue
                if isinstance(line, Key):
                    restore = line.line
                    reply = await self.send(client, "key", line.line, name=line.name)
                else:
                    restore = ""
                    reply = await self.send(client, "input", line)
            return reply.reboot

    async def send(self, client: ClaudeSDKClient, tag: str, body: str = "", *,
                   fatal: bool = False, halt_on_error: bool = False, **attrs: object) -> Reply:
        """Send one envelope, show the AI's screen, remember its prompt."""
        text, interrupted = await self.exchange(client, self.envelope(tag, body, **attrs))
        if interrupted:                          # Ctrl-C while the AI was working
            text, _ = await self.exchange(client, self.envelope("signal", "SIGINT"))
        if text is None:                         # the model failed; the error went to stderr
            if fatal:
                raise SystemExit(1)
            return Reply(screen="", prompt=None, halt=halt_on_error)
        reply = parse(text)
        self.terminal.write(reply.screen)
        if reply.prompt is not None:
            self.prompt = reply.prompt
        else:
            log.warning("reply without <prompt>; keeping the previous prompt")
        return reply

    def envelope(self, tag: str, body: str = "", **attrs: object) -> str:
        cols, rows = self.terminal.size()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        return envelope(tag, body, **attrs, cwd=self.disk.cwd, time=now, cols=cols, rows=rows)

    async def exchange(self, client: ClaudeSDKClient, message: str) -> tuple[str | None, bool]:
        """One round trip. Returns (reply text or None on error, interrupted by Ctrl-C)."""
        log.info(">> %s", message)
        interrupted = False
        loop = asyncio.get_running_loop()

        def on_ctrl_c() -> None:
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                loop.create_task(client.interrupt())

        try:
            loop.add_signal_handler(signal.SIGINT, on_ctrl_c)
            catching_ctrl_c = True
        except (NotImplementedError, RuntimeError, ValueError):     # Windows, other threads
            catching_ctrl_c = False
        try:
            await client.query(message)
            result = None
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ToolUseBlock):
                            log.info("   tool %s %s", block.name.removeprefix(f"mcp__{SERVER}__"),
                                     block.input)
                elif isinstance(msg, ResultMessage):
                    result = msg
        finally:
            if catching_ctrl_c:
                loop.remove_signal_handler(signal.SIGINT)
        if result is None or (result.is_error and not interrupted):
            self.hardware_error(result)
            return None, interrupted
        log.info("<< %s", result.result)
        log.info("   %s, %d turns, %.1fs, $%.4f", result.subtype, result.num_turns,
                 result.duration_ms / 1000, result.total_cost_usd or 0)
        return result.result or "", interrupted

    @staticmethod
    def hardware_error(result: ResultMessage | None) -> None:
        """The one thing the terminal may say itself: the model couldn't be reached."""
        if result is None:
            detail = "no reply"
        else:
            detail = "; ".join(result.errors or []) or result.result or result.subtype
            if result.api_error_status:
                detail = f"HTTP {result.api_error_status}: {detail}"
        log.error("model error: %s", detail)
        print(f"hallux: the model failed ({detail})", file=sys.stderr)
