"""hpm's own Claude session, for what needs judgement (docs/hpm/hpm.md, section 11; the
plan's decisions 9 and 10 and step 6): drafting a manifest (init), a changelog entry,
merging two memory files, and reviewing a card.

One session per job, built like an addon agent's job (hallux.agents.Session): the SDK's
client, made by `client_factory` so that the tests use a stand-in; `shared_options`, so the
session gets nothing of Claude Code's and nothing of yours, and the world's OS sandbox when
it has it on; the job's prompt (hallux/hpm/prompts/); its own tools, and nothing else; and
the cap of the store's config.toml as the SDK's max_budget_usd.

The tools are the world's Disk, read-only (list_dir, stat, read_file, find), and a
write_file that reaches only the paths the job may write. There is no remove, no
memory_edit and no shell.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from hallux import config
from hallux.addons import EFFORTS
from hallux.disk import HIDDEN_NAME, Disk
from hallux.hpm.store import Store
from hallux.hpm.world import HpmError

log = logging.getLogger("hallux")

PROMPTS = Path(__file__).resolve().parent / "prompts"
SERVER = "hpm"
MAX_TURNS = 60
CONFIG = "config.toml"
DEFAULTS = {"model": None, "effort": "medium", "cap_usd": 1.00, "base_world": None}


# ---------------------------------------------------------------------- the store's settings

@dataclass(frozen=True)
class Settings:
    """The store's config.toml: what hpm's AI runs on and may cost, and the base world of
    the test install."""
    model: str | None = None              # None: the model the world runs on
    effort: str = "medium"
    cap_usd: float = 1.00                 # per session
    base_world: str | None = None
    path: Path | None = None              # where they were read from

    def model_for(self, world: Path) -> str:
        if self.model:
            return self.model
        try:
            return config.load(world).model
        except ValueError:
            return config.Hardware().model


def settings(store: Store) -> Settings:
    """The store's config.toml, checked: an unknown key or a wrong value is an error that
    names the file. Without the file, the defaults."""
    path = store.home / CONFIG
    if not path.exists():
        return Settings(path=path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise HpmError(f"{path} can't be read: {e}") from None
    problems = [f"unknown key {key!r}" for key in sorted(set(data) - set(DEFAULTS))]
    model, effort = data.get("model"), data.get("effort", "medium")
    cap, base = data.get("cap_usd", 1.00), data.get("base_world")
    if model is not None and not (isinstance(model, str) and model.strip()):
        problems.append("model must be a model name, like claude-opus-5-5")
    if effort not in EFFORTS:
        problems.append(f"effort must be one of {', '.join(EFFORTS)}")
    if not (isinstance(cap, (int, float)) and not isinstance(cap, bool) and 0 < cap <= 50):
        problems.append("cap_usd must be a number of dollars above 0 (at most 50)")
    if base is not None and not isinstance(base, str):
        problems.append("base_world must be the path of a world")
    if problems:
        raise HpmError(f"{path}: " + "; ".join(problems))
    return Settings(model, effort, float(cap), base, path)


# ---------------------------------------------------------------------- a job

@dataclass
class Job:
    """What one session is for."""
    name: str                             # init, changelog, merge, review
    message: str                          # the one message it is sent
    may_write: Callable[[str], bool] = lambda path: False     # a machine path it may write
    release: Path | None = None           # a last release, unpacked, to read (changelog)
    tools: bool = True                    # False: the message holds all it needs


@dataclass
class Answer:
    ok: bool
    text: str = ""                        # its last words
    cost_usd: float = 0.0
    why: str = ""
    wrote: list[str] = field(default_factory=list)            # the machine paths it wrote


def real_client():
    """The SDK's client, which calls the model and costs money. The tests set
    HALLUX_NO_REAL_MODEL, and then asking for it is a loud error: a test must give a
    stand-in, and never reach the model by a question it answered with a default."""
    import os
    if os.environ.get("HALLUX_NO_REAL_MODEL"):
        raise RuntimeError("a test reached for the real model: give hpm's session a stand-in "
                           "client_factory")
    from claude_agent_sdk import ClaudeSDKClient
    return ClaudeSDKClient


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


class Session:
    """One job's Claude session on a world."""

    def __init__(self, world: Path | str, job: Job, ai: Settings, client_factory=None) -> None:
        self.world = Path(world)
        self.disk = Disk(self.world)
        self.job, self.ai = job, ai
        self.client_factory = client_factory or real_client()
        self.wrote: list[str] = []
        self.tools: dict[str, Any] = {}           # by the names for allowed_tools
        self.servers = self._servers()

    # the tools
    def _servers(self) -> dict:
        from claude_agent_sdk import create_sdk_mcp_server, tool
        from hallux.tools import READS, run, schema
        path = {"type": "string", "description": "An absolute path on the machine."}
        made = []

        def make(name, description, input_schema, method, annotations=None):
            async def handler(args: dict[str, Any]) -> dict[str, Any]:
                return run(lambda: method(**args))
            made.append(tool(name, description, input_schema, annotations)(handler))

        if self.job.tools:
            disk = self.disk
            make("list_dir", "List a directory of the machine: name, mode, size, mtime.",
                 schema({"path": path}), disk.list_dir, READS)
            make("stat", "One entry of the machine's disk.", schema({"path": path}), disk.stat,
                 READS)
            make("read_file", "Read a file as text, 64 KB per call; when truncated, call again "
                 "with offset=next_offset.",
                 schema({"path": path}, {"offset": {"type": "integer", "minimum": 0}}),
                 disk.read_file, READS)
            make("find", "Find entries under a directory whose names match a glob pattern "
                 "(at most 1000).", schema({"path": path}, {"pattern": {"type": "string"}}),
                 disk.find, READS)
            make("write_file", "Write a whole file, as text. Only the files your instructions "
                 "name may be written; anything else is refused with EACCES.",
                 schema({"path": path, "content": {"type": "string"}}), self._write)
            if self.job.release is not None:
                old = Disk(self.job.release)
                make("release_list_dir", "List a directory of the last release, by the "
                     "machine's path.", schema({"path": path}), old.list_dir, READS)
                make("release_read_file", "Read a file of the last release, by the machine's "
                     "path, 64 KB per call.",
                     schema({"path": path}, {"offset": {"type": "integer", "minimum": 0}}),
                     old.read_file, READS)
        if not made:
            return {}
        self.tools = {f"mcp__{SERVER}__{t.name}": t for t in made}
        return {SERVER: create_sdk_mcp_server(SERVER, tools=made)}

    def _write(self, path: str, content: str) -> dict:
        import errno
        virtual = self.disk.virtual(path)
        if not self.job.may_write(virtual):
            raise OSError(errno.EACCES, f"{virtual} isn't yours to write")
        result = self.disk.write_file(virtual, content, parents=True)
        self.wrote.append(virtual)
        return result

    # the session
    def options(self):
        from claude_agent_sdk import ClaudeAgentOptions
        from hallux.agents import shared_options
        try:
            hardware = config.load(self.world)
        except ValueError:
            hardware = config.Hardware()
        model = self.ai.model_for(self.world)
        effort = None if "haiku" in model else self.ai.effort
        return ClaudeAgentOptions(
            system_prompt=prompt(self.job.name), model=model, effort=effort,
            max_turns=MAX_TURNS, max_budget_usd=self.ai.cap_usd, mcp_servers=self.servers,
            allowed_tools=list(self.tools), **shared_options(hardware, self.disk.hidden))

    async def ask(self, follow: Callable[[Answer], str | None] | None = None) -> Answer:
        """Send the job's message, and read the session to its result. `follow(answer)` may
        give one more message for the same session, once (init's problems, shown to the AI):
        the answer is then the second one's, with what the whole session cost."""
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
        cost, text = 0.0, ""
        try:
            async with self.client_factory(options=self.options()) as client:
                message, rounds = self.job.message, 0
                while message is not None:
                    rounds += 1
                    await client.query(message)
                    result, said = None, ""
                    async for event in client.receive_response():
                        if isinstance(event, AssistantMessage):
                            for block in event.content:
                                if isinstance(block, TextBlock) and block.text.strip():
                                    said = block.text
                        elif isinstance(event, ResultMessage):
                            result = event
                    if result is None:
                        return self._ended(Answer(False, said, cost, "the session ended without "
                                                  "a result", list(self.wrote)))
                    cost = result.total_cost_usd or cost
                    text = result.result or said
                    if result.subtype != "success" or result.is_error:
                        why = {"error_max_turns": "it took too many turns",
                               "error_max_budget_usd": f"it reached the cap of "
                                                       f"${self.ai.cap_usd:.2f}"}.get(
                            result.subtype, "; ".join(result.errors or []) or result.subtype)
                        return self._ended(Answer(False, text, cost, why, list(self.wrote)))
                    message = None
                    if follow is not None and rounds == 1:
                        message = follow(Answer(True, text, cost, "", list(self.wrote)))
        except Exception as e:
            log.warning("hpm %s: the session failed", self.job.name, exc_info=True)
            return self._ended(Answer(False, text, cost, f"{type(e).__name__}: {e}",
                                      list(self.wrote)))
        return self._ended(Answer(True, text, cost, "", list(self.wrote)))

    def _ended(self, answer: Answer) -> Answer:
        """A line in the world's log, as a job's end gets."""
        line = (f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} INFO hpm {self.job.name}: "
                f"{'done' if answer.ok else 'failed: ' + answer.why}, ~${answer.cost_usd:.4f}, "
                f"model {self.ai.model_for(self.world)}\n")
        try:
            with open(self.world / HIDDEN_NAME / "hallux.log", "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass
        return answer


def run_job(world: Path | str, job: Job, ai: Settings, client_factory=None,
            follow: Callable[[Answer], str | None] | None = None) -> Answer:
    """A job from the terminal or a thread of its own: one session, run to its end."""
    return asyncio.run(Session(world, job, ai, client_factory).ask(follow))


# ---------------------------------------------------------------------- the four jobs

def init_job(name: str, card: str, memory_line: str | None) -> Job:
    """hpm init: the manifest's first draft, and the extras', and a clean seed."""
    own = f"/usr/local/share/hpm/{name}/"

    def may_write(path: str) -> bool:
        if path.startswith(own + "seed/"):
            return True
        parts = path.split("/")                   # "", usr, local, share, hpm, <package>, hpm.toml
        return (len(parts) == 7 and path.startswith("/usr/local/share/hpm/")
                and parts[6] == "hpm.toml" and (parts[5] == name or parts[5].startswith(name + "-")))

    lines = [f"The program is {name}. Its card, /usr/local/bin/{name}:", "", card.rstrip(), ""]
    if memory_line:
        lines += ["What the machine's memory says of it:", "", memory_line, ""]
    lines.append(f"Draft its package: write /usr/local/share/hpm/{name}/hpm.toml, and the "
                 f"manifests of its extras.")
    return Job("init", "\n".join(lines), may_write)


def changelog_job(name: str, release: Path, added: list[str], changed: list[str],
                  removed: list[str], version: str) -> Job:
    def listed(word: str, paths: list[str]) -> list[str]:
        return [f"{word}:"] + [f"  {p}" for p in paths[:200]] + (
            [f"  … and {len(paths) - 200} more"] if len(paths) > 200 else []) if paths else []
    text = "\n".join([f"{name}, from its last release to {version}.", ""]
                     + listed("Added", added) + listed("Changed", changed)
                     + listed("Removed", removed))
    return Job("changelog", text, release=release)


def merge_job(path: str, ours: str, theirs: str) -> Job:
    return Job("merge", f"The file is {path}.\n\nOn the machine:\n<<<\n{ours}\n>>>\n\n"
                        f"In the package:\n<<<\n{theirs}\n>>>", tools=False)


def review_job(name: str, card: str, manifest: str) -> Job:
    return Job("review", f"The program is {name}.\n\nIts manifest:\n<<<\n{manifest}\n>>>\n\n"
                         f"Its card:\n<<<\n{card}\n>>>", tools=False)


def cost(answer: Answer) -> str:
    return f"~${answer.cost_usd:.4f}"


def bare(text: str) -> str:
    """An answer without a fence the model may have put around it anyway."""
    lines = text.strip("\n").splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        lines = lines[1:-1]
    return "\n".join(lines) + ("\n" if lines else "")
