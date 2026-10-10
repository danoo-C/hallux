import asyncio
import json

import jsonschema
import pytest

from hallux.disk import Disk
from hallux.tools import build_server, build_tools


@pytest.fixture
def root(tmp_path):
    (tmp_path / "home" / "user").mkdir(parents=True)
    (tmp_path / "home" / "user" / "notes.md").write_text("hello\n")
    return tmp_path


@pytest.fixture
def tools(root):
    return {t.name: t for t in build_tools(Disk(root))}


def call(tools, name, **args):
    """Call a tool the way the SDK does: validate the arguments, then run the handler."""
    jsonschema.validate(args, tools[name].input_schema)
    result = asyncio.run(tools[name].handler(args))
    return json.loads(result["content"][0]["text"]), result["is_error"]


def test_server_and_allowed_tool_names(root):
    server, allowed = build_server(Disk(root))
    assert server["type"] == "sdk" and server["name"] == "hallux"
    assert allowed == [f"mcp__hallux__{t.name}" for t in build_tools(Disk(root))]
    assert "mcp__hallux__memory_edit" in allowed and len(allowed) == 14


def test_schemas_are_strict(tools):
    for t in tools.values():
        schema = t.input_schema
        assert schema["type"] == "object" and schema["additionalProperties"] is False
        assert set(schema["required"]) <= set(schema["properties"])
        jsonschema.Draft202012Validator.check_schema(schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"path": "x", "rm_rf": True}, tools["read_file"].input_schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({}, tools["read_file"].input_schema)


def test_results(tools, root):
    assert call(tools, "read_file", path="/home/user/notes.md") == (
        {"text": "hello\n", "size": 6, "truncated": False}, False)
    assert call(tools, "chdir", path="/home/user") == ({"cwd": "/home/user"}, False)
    assert call(tools, "write_file", path="ünïcode.txt", content="žluťoučký kůň\n")[1] is False
    payload, _ = call(tools, "read_file", path="ünïcode.txt")
    assert payload["text"] == "žluťoučký kůň\n"
    assert call(tools, "memory_edit", old="", new="# memory\n") == ({"ok": True, "size": 9}, False)
    assert call(tools, "memory_read") == ({"text": "# memory\n"}, False)


def test_errors_are_errno_names_without_host_paths(tools, root):
    for name, args, expected in [
        ("read_file", {"path": "/nope"}, "ENOENT"),
        ("list_dir", {"path": "/home/user/notes.md"}, "ENOTDIR"),
        ("remove", {"path": "/home"}, "EISDIR"),
        ("read_file", {"path": "/.hallux/memory.md"}, "ENOENT"),
    ]:
        result = asyncio.run(tools[name].handler(args))
        assert result["is_error"] is True
        assert json.loads(result["content"][0]["text"]) == {"error": expected}
        assert str(root) not in result["content"][0]["text"]
    payload, is_error = call(tools, "edit_file", path="/home/user/notes.md", old="bye", new="x")
    assert is_error and "0 times" in payload["error"]


class Screen:
    """Stands in for the terminal's block-mode fields."""

    def __init__(self, **texts):
        self.texts, self.saved = texts, []

    def field_text(self, id):
        if id not in self.texts:
            raise ValueError(f"no field {id!r} on the screen")
        return self.texts[id]

    def field_saved(self, id):
        self.saved.append(id)


def test_save_field_only_exists_with_block_mode(root):
    assert "save_field" not in {t.name for t in build_tools(Disk(root))}
    _, allowed = build_server(Disk(root), fields=Screen())
    assert "mcp__hallux__save_field" in allowed and len(allowed) == 15


def test_save_field_writes_exactly_what_the_user_typed(root):
    screen = Screen(text="hi\nthere")
    tools = {t.name: t for t in build_tools(Disk(root), fields=screen)}
    assert call(tools, "save_field", field="text", path="/home/user/hello.txt") == (
        {"ok": True, "size": 8, "lines": 2}, False)
    assert (root / "home" / "user" / "hello.txt").read_text() == "hi\nthere"
    assert screen.saved == ["text"]
    payload, is_error = call(tools, "save_field", field="nope", path="/x")
    assert is_error and "no field 'nope'" in payload["error"]
    assert call(tools, "save_field", field="text", path="/.hallux/memory.md")[0] == {"error": "ENOENT"}


def test_list_processes_is_on_every_machine_with_the_kept_screens(root):
    """Job control: jobs reads the kept screens through it, and a machine without an addon
    has kept screens too. Its table of jobs is just empty there."""
    assert call({t.name: t for t in build_tools(Disk(root))}, "list_processes") == (
        {"jobs": [], "screens": []}, False)
    kept = [2, 5]
    tools = {t.name: t for t in build_tools(Disk(root), screens=lambda: kept)}
    assert call(tools, "list_processes") == ({"jobs": [], "screens": [2, 5]}, False)
    kept.remove(2)                                          # asked each time, not once
    assert call(tools, "list_processes") == ({"jobs": [], "screens": [5]}, False)
    assert "screens" in tools["list_processes"].description


def test_kill_process_isnt_there_without_an_agent_addon(root):
    assert "kill_process" not in {t.name for t in build_tools(Disk(root), screens=lambda: [1])}
