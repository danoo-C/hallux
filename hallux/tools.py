"""The Disk as tools for the agent, served by the Claude Agent SDK's in-process MCP server."""
from __future__ import annotations

import errno
import json
from typing import Any, Callable

from claude_agent_sdk import SdkMcpTool, ToolAnnotations, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from hallux.disk import Disk

SERVER = "hallux"

# Read-only tools can return a lot (a 64 KB file chunk, a big listing). Keep those results
# inline for the model instead of letting Claude Code swap them for a preview.
READS = ToolAnnotations(readOnlyHint=True, maxResultSizeChars=200_000)

PATH = {"type": "string", "description": "Path inside the machine, absolute or relative to the cwd."}
TEXT = {"type": "string"}
FLAG = {"type": "boolean"}


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


def build_tools(disk: Disk) -> list[SdkMcpTool]:
    def make(name: str, description: str, input_schema: dict, method: Callable,
             annotations: ToolAnnotations | None = None) -> SdkMcpTool:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            return run(lambda: method(**args))
        return tool(name, description, input_schema, annotations)(handler)

    return [
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
             "The parent directory must exist.",
             schema({"path": PATH, "content": TEXT}, {"append": FLAG}), disk.write_file),
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
    ]


def build_server(disk: Disk) -> tuple[McpSdkServerConfig, list[str]]:
    """The MCP server for ClaudeAgentOptions.mcp_servers, and the names for allowed_tools."""
    tools = build_tools(disk)
    return create_sdk_mcp_server(SERVER, tools=tools), [f"mcp__{SERVER}__{t.name}" for t in tools]
