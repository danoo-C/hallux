"""The Disk and the addons as tools for the agent, served by the Claude Agent SDK's in-process
MCP servers: one for hallux's own tools, and one per addon. A job of an addon's agent gets
servers of its own, with fewer tools, on its fenced disk (build_job_servers)."""
from __future__ import annotations

import errno
import functools
import json
from typing import Any, Callable, Protocol, Sequence

from claude_agent_sdk import SdkMcpTool, ToolAnnotations, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from hallux.addons import Addon, Events, call, description_for, schema_for
from hallux.disk import Disk
from hallux.jobdisk import JobDisk

SERVER = "hallux"

# Read-only tools can return a lot (a 64 KB file chunk, a big listing). Keep those results
# inline for the model instead of letting Claude Code swap them for a preview.
READS = ToolAnnotations(readOnlyHint=True, maxResultSizeChars=200_000)

PATH = {"type": "string", "description": "Path inside the machine, absolute or relative to the cwd."}
JOB_PATH = {"type": "string",
            "description": "Path inside your folder: relative to it, or absolute in the machine."}
TEXT = {"type": "string"}
FLAG = {"type": "boolean"}


class Fields(Protocol):
    """The block-mode fields on screen (hallux.terminal.Terminal provides them)."""

    def field_text(self, id: str) -> str: ...     # raises ValueError for an unknown field

    def field_saved(self, id: str) -> None: ...


class Processes(Protocol):
    """The jobs of the addons' agents, as the main agent reaches them (hallux.agents.Jobs)."""

    def table(self) -> list[dict]: ...

    def kill(self, pid: int) -> None: ...             # raises OSError for a pid that isn't running


class Reports(Protocol):
    """What a job's tools tell hallux about it (hallux.agents.Job provides it)."""

    def set_status(self, text: object) -> str: ...    # raises OSError once the job has ended

    def tool_began(self, name: str, args: dict | None = None) -> None: ...

    def tool_ended(self, result: str | None = None) -> None: ...


def schema(required: dict[str, dict], optional: dict[str, dict] | None = None) -> dict:
    optional = optional or {}
    return {"type": "object", "properties": required | optional,
            "required": list(required), "additionalProperties": False}


def run(op: Callable[[], Any]) -> dict[str, Any]:
    """Run a Disk method. Failures come back as errno names the AI turns into shell errors."""
    try:
        payload, is_error = op(), False
    except OSError as e:
        payload, is_error = {"error": errno.errorcode.get(e.errno, "EIO")}, True
    except ValueError as e:
        payload, is_error = {"error": str(e)}, True
    text = json.dumps(payload, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}], "is_error": is_error}


def build_tools(disk: Disk, fields: Fields | None = None, addons: Sequence[Addon] = (),
                events: Events | None = None, jobs: Processes | None = None,
                screens: Callable[[], Sequence[int]] | None = None) -> list[SdkMcpTool]:
    """hallux's own tools. `screens` gives the job numbers of the full-screen programs that
    are put aside (the terminal's suspended_forms)."""
    def make(name: str, description: str, input_schema: dict, method: Callable,
             annotations: ToolAnnotations | None = None) -> SdkMcpTool:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            return run(lambda: method(**args))
        return tool(name, description, input_schema, annotations)(handler)

    def save_field(field: str, path: str) -> dict:
        text = fields.field_text(field)
        result = disk.write_file(path, text)
        fields.field_saved(field)
        lines = text.count("\n") + (not text.endswith("\n") and text != "")
        return result | {"lines": lines}

    def list_addons() -> list[dict]:
        return [{"name": addon.name, "summary": addon.summary} for addon in addons]

    def attached(name: str) -> Addon:
        for addon in addons:
            if addon.name == name:
                return addon
        raise ValueError(f"no addon {name!r}; there are: {', '.join(a.name for a in addons)}")

    def addon_help(name: str) -> dict:
        return {"manual": attached(name).manual}

    def addon_listen(name: str, on: bool = True) -> dict:
        if not attached(name).has_events:
            raise ValueError(f"the addon {name!r} has no events")
        events.listen(name, on)
        return {"listening": events.listening()}

    def list_processes() -> dict:
        return {"jobs": jobs.table() if jobs is not None else [],
                "screens": list(screens()) if screens is not None else []}

    def kill_process(pid: int) -> dict:
        jobs.kill(pid)
        return {"ok": True}

    block_mode = [] if fields is None else [
        make("save_field",
             "Block mode: write a field's current text, exactly as the user left it, to a "
             "file (nano's ^O, vim's :w). Returns size and lines.",
             schema({"field": TEXT, "path": PATH}), save_field),
    ]
    return block_mode + [
        make("list_dir",
             "List a directory, hidden entries included: name, mode (drwxr-xr-x), size, mtime "
             "(local time) and, for symlinks, target. For ls and globbing.",
             schema({}, {"path": PATH}), disk.list_dir, READS),
        make("stat",
             "Metadata of one path itself, not following symlinks. Same fields as list_dir. "
             "For ls -l <file>, ls -d, test -e/-f/-d and stat.",
             schema({"path": PATH}), disk.stat, READS),
        make("read_file",
             "Read a file as text, 64 KB per call. Returns text, size and truncated; when "
             "truncated, call again with offset=next_offset. Binary files return binary=true.",
             schema({"path": PATH}, {"offset": {"type": "integer", "minimum": 0}}),
             disk.read_file, READS),
        make("find",
             "Recursively list everything under path whose name matches a glob pattern "
             "(default *): absolute path and type (f, d or l). Up to 1000 entries.",
             schema({}, {"path": PATH, "pattern": TEXT}), disk.find, READS),
        make("write_file",
             "Create or overwrite a file with text; append=true adds to the end (>>). "
             "The parent directory must exist, unless parents=true creates it (for files the "
             "machine makes itself, like copy-up; not for the user's redirects).",
             schema({"path": PATH, "content": TEXT}, {"append": FLAG, "parents": FLAG}),
             disk.write_file),
        make("edit_file",
             "Replace exactly one occurrence of old with new in a file (sed -i, dotfiles).",
             schema({"path": PATH, "old": TEXT, "new": TEXT}), disk.edit_file),
        make("make_dir",
             "Create a directory; parents=true works like mkdir -p.",
             schema({"path": PATH}, {"parents": FLAG}), disk.make_dir),
        make("chdir",
             "Change the shell's working directory (cd). Relative paths resolve against it.",
             schema({"path": PATH}), disk.chdir),
        make("remove",
             "Delete a file or a symlink (the link itself, never its target); directories "
             "need recursive=true. Removing / empties the machine but keeps its memory.",
             schema({"path": PATH}, {"recursive": FLAG}), disk.remove),
        make("move",
             "Move or rename (mv). If dst is an existing directory, src moves into it.",
             schema({"src": PATH, "dst": PATH}), disk.move),
        make("copy",
             "Copy (cp). If dst is an existing directory, src is copied into it. Directories "
             "need recursive=true; symlinks inside them are copied as links.",
             schema({"src": PATH, "dst": PATH}, {"recursive": FLAG}), disk.copy),
        make("memory_read",
             "Read the machine's memory (/.hallux/memory.md, invisible to the OS). Empty on "
             "first boot.",
             schema({}), disk.memory_read, READS),
        make("memory_edit",
             "Replace exactly one occurrence of old with new in the memory; an empty old "
             "appends new to the end. Returns the new size: keep the memory short.",
             schema({"old": TEXT, "new": TEXT}), disk.memory_edit),
        make("list_processes",
             "What is real behind ps, top, htop and jobs. jobs: the machine's real background "
             "jobs, which addon functions started: pid, addon, agent, state (running; waiting "
             "inside a tool call; done, failed or killed), seconds, tokens, folder and a "
             "status line. A job that has ended is listed once. screens: the job numbers of "
             "the suspended full-screen programs whose screens are kept.",
             schema({}), list_processes, READS),
    ] + ([] if not addons else [
        make("list_addons",
             "The addons attached to this machine, name and summary: the same list as "
             "<addons> in <boot>.",
             schema({}), list_addons, READS),
        make("addon_help",
             "An addon's manual: what it is, what its functions do and what their limits are. "
             "Read it before you use that addon for the first time in a boot.",
             schema({"name": TEXT}), addon_help, READS),
    ]) + ([] if events is None or not any(addon.has_events for addon in addons) else [
        make("addon_listen",
             "Hear an addon's events from now on, for the rest of this boot: they arrive as "
             "<events>. on=false stops it. Returns the addons you listen to.",
             schema({"name": TEXT}, {"on": FLAG}), addon_listen),
    ]) + ([] if jobs is None or not any(addon.agent for addon in addons) else [
        make("kill_process",
             "End a background job by its pid (kill). ESRCH: no job has that pid, or it has "
             "ended already.",
             schema({"pid": {"type": "integer"}}), kill_process),
    ])


def build_server(disk: Disk, fields: Fields | None = None, addons: Sequence[Addon] = (),
                 events: Events | None = None, jobs: Processes | None = None,
                 screens: Callable[[], Sequence[int]] | None = None
                 ) -> tuple[McpSdkServerConfig, list[str]]:
    """The MCP server for ClaudeAgentOptions.mcp_servers, and the names for allowed_tools."""
    tools = build_tools(disk, fields, addons, events, jobs, screens)
    return create_sdk_mcp_server(SERVER, tools=tools), [f"mcp__{SERVER}__{t.name}" for t in tools]


def build_addon_tools(addon: Addon, disk: Disk | None = None,
                      spawn: Callable | None = None) -> list[SdkMcpTool]:
    """An addon's exposed functions as tools. A function's docstring is its description.
    `disk` is the machine's disk, for the functions that take the handle, and `spawn` is what
    starts a job of this addon's agent, for the functions that ask for it."""
    def make(name: str, function: Callable) -> SdkMcpTool:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            return await call(function, args, disk, spawn)
        return tool(name, description_for(function), schema_for(function))(handler)

    return [make(name, function) for name, function in addon.functions.items()]


def build_addon_servers(addons: Sequence[Addon], disk: Disk | None = None,
                        spawn: Callable | None = None
                        ) -> tuple[dict[str, McpSdkServerConfig], list[str]]:
    """One MCP server per addon, so two addons can each have a play: the AI sees
    mcp__music__play. Returns the servers by name, and the names for allowed_tools.
    `spawn` is what starts a job, hallux.agents.Jobs.spawn: an addon with an agent gets it
    tied to itself, so the job its function starts is one of its own agent's."""
    servers, allowed = {}, []
    for addon in addons:
        own = None if spawn is None or addon.agent is None else functools.partial(spawn, addon)
        tools = build_addon_tools(addon, disk, own)
        servers[addon.name] = create_sdk_mcp_server(addon.name, tools=tools)
        allowed += [f"mcp__{addon.name}__{t.name}" for t in tools]
    return servers, allowed


def build_job_servers(addon: Addon, disk: JobDisk, job: Reports
                      ) -> tuple[dict[str, McpSdkServerConfig], dict[str, SdkMcpTool]]:
    """All the tools one job of an addon's agent has: four file tools on its fenced disk and
    set_status, in hallux's group, and the functions its addon's agent() lists, in a group of
    the addon's name. Returns the servers by name, and the tools by the names for
    allowed_tools.

    They are the main agent's tools on another disk: the same wrapper turns an answer or an
    error into a result. Each one says when it begins and ends, so the job's row shows the
    call it is in without anyone guessing it from the session's messages."""
    def reporting(name: str, handler: Callable) -> Callable:
        async def reported(args: dict[str, Any]) -> dict[str, Any]:
            job.tool_began(name, args)
            answer = None                        # none: the call was cut short
            try:
                result = await handler(args)
                answer = result["content"][0]["text"]
                return result
            finally:
                job.tool_ended(answer)
        return reported

    def make(name: str, description: str, input_schema: dict, method: Callable,
             annotations: ToolAnnotations | None = None) -> SdkMcpTool:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            return run(lambda: method(**args))
        return tool(name, description, input_schema, annotations)(reporting(name, handler))

    def of_addon(name: str, function: Callable) -> SdkMcpTool:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            return await call(function, args, disk)      # its disk handle is the job's disk
        return tool(name, description_for(function),
                    schema_for(function))(reporting(name, handler))

    async def set_status(args: dict[str, Any]) -> dict[str, Any]:
        return run(lambda: {"status": job.set_status(args["text"])})

    groups = {SERVER: [
        make("list_dir",
             "List a directory in your folder, hidden entries included: name, mode "
             "(drwxr-xr-x), size, mtime (local time) and, for symlinks, target. Without a "
             "path: the folder itself.",
             schema({}, {"path": JOB_PATH}), disk.list_dir, READS),
        make("read_file",
             "Read a file as text, 64 KB per call. Returns text, size and truncated; when "
             "truncated, call again with offset=next_offset. Binary files return binary=true. "
             "A file you have written reads as you wrote it.",
             schema({"path": JOB_PATH}, {"offset": {"type": "integer", "minimum": 0}}),
             disk.read_file, READS),
        make("write_file",
             "Create a file, or overwrite one you created or were given, with text; "
             "append=true adds to the end. The directory must exist. Every other file is "
             "read-only for you: EACCES.",
             schema({"path": JOB_PATH, "content": TEXT}, {"append": FLAG}), disk.write_file),
        make("edit_file",
             "Replace exactly one occurrence of old with new in a file you created or were "
             "given.",
             schema({"path": JOB_PATH, "old": TEXT, "new": TEXT}), disk.edit_file),
        # Not reported as a call: the line it sets is what the row shows of it.
        tool("set_status",
             "Say in one line what you are doing now: at most 80 characters, shown in the "
             "machine's process table. Returns the line as it was kept.",
             schema({"text": TEXT}))(set_status),
    ]}
    if addon.agent.tools:
        groups[addon.name] = [of_addon(name, function)
                              for name, function in addon.agent.tools.items()]
    servers = {group: create_sdk_mcp_server(group, tools=tools) for group, tools in groups.items()}
    named = {f"mcp__{group}__{t.name}": t for group, tools in groups.items() for t in tools}
    return servers, named
