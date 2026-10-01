import asyncio
import json
import re
import sys
import threading
import time
from pathlib import Path

import jsonschema
import pytest
from claude_agent_sdk import AssistantMessage, ToolUseBlock
from test_machine import FakeModel, FakeTerminal, result, screen

from hallux import addons, app, config, script, tools
from hallux.config import Hardware
from hallux.disk import Disk
from hallux.machine import SYSTEM_PROMPT, Machine

# The smallest addon that passes every check (docs/plans/addons-plan.md).
DICE = '''\
"""A die: real random numbers.

This second paragraph isn't part of the summary.
"""
import random


def prompt() -> str:
    return "roll(sides) throws a die with that many sides and returns the number."


def roll(sides: int = 6) -> dict:
    """Throw a die."""
    if not 2 <= sides <= 1000:
        raise ValueError("sides must be between 2 and 1000")
    return {"value": random.randint(1, sides)}


EXPOSED = [roll]
'''


def func(head, body="return {}", doc="Do the thing.", start="def"):
    """The source of one function: func("ping() -> dict")."""
    lines = [f"{start} {head}:", f'    """{doc}"""' if doc else "", f"    {body}"]
    return "\n".join(line for line in lines if line)


def fake(doc='"""A fake addon."""',
         prompt='def prompt() -> str:\n    return "the manual"',
         functions=func("ping() -> dict", 'return {"ok": True}'),
         exposed="EXPOSED = [ping]",
         top=""):
    """The source of a fake addon that passes every check, with any part replaced."""
    return "\n\n".join(part for part in (doc, top, prompt, functions, exposed) if part) + "\n"


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "addons").mkdir()
    yield tmp_path / "addons"
    for name in [n for n in sys.modules if n.startswith(addons.MODULE_PREFIX)]:
        del sys.modules[name]


def test_a_good_addon(folder):
    (folder / "dice.py").write_text(DICE)
    [dice], skipped = addons.load(folder)
    assert skipped == {}
    assert dice.name == "dice"
    assert dice.summary == "A die: real random numbers."
    assert dice.manual == "roll(sides) throws a die with that many sides and returns the number."
    assert list(dice.functions) == ["roll"]
    assert dice.functions["roll"](sides=2)["value"] in (1, 2)
    assert dice.stop is None


def test_an_addon_is_imported_under_a_private_name(folder):
    (folder / "json.py").write_text(fake())
    [addon], _ = addons.load(folder)
    assert addon.name == "json"
    assert sys.modules["json"] is json and "hallux_addon_json" in sys.modules


def test_only_exposed_is_reachable(folder):
    (folder / "sound.py").write_text(fake(
        functions=func("play(path: str, loud: bool = False) -> dict") + "\n\n\n"
                  + func("helper(anything)", "return anything", doc=""),
        exposed="EXPOSED = (play,)"))
    [sound], _ = addons.load(folder)
    assert list(sound.functions) == ["play"]


def test_hints_written_as_text_are_read(folder):
    (folder / "late.py").write_text(fake(
        top="from __future__ import annotations",
        functions=func("scale(by: float, *, name: str) -> dict"),
        exposed="EXPOSED = [scale]"))
    assert [a.name for a in addons.load(folder)[0]] == ["late"]


def test_stop_is_the_hook_and_a_tool_only_when_exposed(folder):
    (folder / "hook.py").write_text(fake(top=func("stop()", "return {'ok': True}", doc="")))
    (folder / "both.py").write_text(fake(top=func("stop() -> dict", "return {'ok': True}"),
                                         exposed="EXPOSED = [ping, stop]"))
    [both, hook], skipped = addons.load(folder)
    assert skipped == {}
    assert hook.stop() == {"ok": True} and list(hook.functions) == ["ping"]
    assert both.stop is both.functions["stop"]


def test_stop_may_take_arguments_if_it_works_without_them(folder):
    (folder / "fade.py").write_text(fake(
        top=func("stop(fade: float = 0.0) -> dict", "return {'fade': fade}"),
        exposed="EXPOSED = [ping, stop]"))
    [fade], skipped = addons.load(folder)
    assert skipped == {}
    assert fade.stop() == {"fade": 0.0} and fade.functions["stop"](fade=1.5) == {"fade": 1.5}


@pytest.mark.parametrize("file, source, reason", [
    # 1. the file name
    ("_private.py", fake(), "file name must be"),
    ("my-addon.py", fake(), "file name must be"),
    ("Music.py", fake(), "file name must be"),
    ("a__b.py", fake(), "file name must be"),
    ("hallux.py", fake(), "the name hallux is taken by the disk tools"),
    # 2. the import
    ("needs.py", fake(top="import no_such_library"), "No module named 'no_such_library'"),
    ("typo.py", "def (:\n", r"SyntaxError: invalid syntax \(typo\.py, line 1\)"),
    ("crash.py", fake(top="1 / 0"), "ZeroDivisionError: division by zero"),
    ("quits.py", fake(top="raise SystemExit('no sound card')"), "SystemExit: no sound card"),
    # 3. the summary
    ("nodoc.py", fake(doc=""), "no docstring"),
    ("blank.py", fake(doc='"""   """'), "no docstring"),
    # 4. prompt exists
    ("mute.py", fake(prompt=""), r"no prompt\(\) function"),
    ("text.py", fake(prompt='prompt = "the manual"'), r"no prompt\(\) function"),
    # 5. prompt() returns text
    ("empty.py", fake(prompt='def prompt():\n    return "  \\n"'), r"prompt\(\) returned no text"),
    ("none.py", fake(prompt="def prompt():\n    pass"), r"prompt\(\) returned no text"),
    ("raises.py", fake(prompt='def prompt():\n    raise RuntimeError("boom")'),
     "RuntimeError: boom"),
    # 6. EXPOSED
    ("closed.py", fake(exposed=""), "no EXPOSED list"),
    ("word.py", fake(exposed='EXPOSED = "ping"'), "no EXPOSED list"),
    ("nothing.py", fake(exposed="EXPOSED = []"), "EXPOSED is empty"),
    ("names.py", fake(exposed='EXPOSED = ["ping"]'), "EXPOSED holds a str, not a function"),
    ("builtin.py", fake(exposed="EXPOSED = [ping, print]"),
     "EXPOSED holds a builtin_function_or_method, not a function"),
    ("twice.py", fake(exposed="EXPOSED = [ping, ping]"), "two functions called ping"),
    ("lambda.py", fake(exposed="EXPOSED = [lambda: {}]"), "<lambda>, which can't be a tool"),
    ("later.py", fake(functions=func("ping() -> dict", start="async def")), "ping is async"),
    # 7. the docstring and the type hints
    ("undescribed.py", fake(functions=func("ping() -> dict", doc="")),
     "ping has no docstring: it's what the AI is told the function does"),
    ("blankdoc.py", fake(functions=func("ping() -> dict", doc="  ")), "ping has no docstring"),
    ("bare.py", fake(functions=func("ping(times) -> dict")), r"ping\(times\) has no type hint"),
    ("notes.py", fake(functions=func("ping(notes: list) -> dict")),
     r"ping\(notes\): the type hint must be str, int, float or bool"),
    ("maybe.py", fake(functions=func("ping(name: str | None = None) -> dict")),
     r"ping\(name\): the type hint must be"),
    ("star.py", fake(functions=func("ping(*names: str) -> dict")),
     r"ping\(names\): only named parameters"),
    ("kwargs.py", fake(functions=func("ping(**options: str) -> dict")),
     r"ping\(options\): only named parameters"),
    ("unknown.py", fake(top="from __future__ import annotations",
                        functions=func("ping(color: Colour) -> dict")),
     "NameError: name 'Colour' is not defined"),
    # 8. stop
    ("force.py", fake(top=func("stop(force: bool) -> dict")),
     r"stop\(\) must work without arguments"),
    ("flag.py", fake(top="stop = True"), r"stop\(\) must work without arguments"),
])
def test_a_failed_check_skips_the_addon_with_a_reason(folder, file, source, reason):
    (folder / file).write_text(source)
    loaded, skipped = addons.load(folder)
    name = file.removesuffix(".py")
    assert loaded == [] and list(skipped) == [name]
    assert re.search(reason, skipped[name]), skipped[name]


def test_the_first_failed_check_gives_the_reason(folder):
    (folder / "many.py").write_text(fake(doc="", prompt="", exposed=""))
    assert addons.load(folder)[1] == {"many": "no docstring: its first line is the addon's summary"}


def test_a_broken_addon_doesnt_stop_the_others(folder, caplog):
    (folder / "broken.py").write_text(fake(top="import no_such_library"))
    (folder / "dice.py").write_text(DICE)
    (folder / "quiet.py").write_text(fake(prompt=""))
    loaded, skipped = addons.load(folder)
    assert [a.name for a in loaded] == ["dice"]
    assert skipped == {"broken": "No module named 'no_such_library'",
                       "quiet": "no prompt() function"}
    assert "hallux_addon_broken" not in sys.modules
    assert "addon broken skipped: No module named 'no_such_library'" in caplog.text
    assert "Traceback" in caplog.text and "addon quiet skipped: no prompt()" in caplog.text


def test_only_python_files_are_addons(folder):
    (folder / "dice.py").write_text(DICE)
    (folder / "notes.txt").write_text("not an addon")
    (folder / "package").mkdir()
    (folder / "package" / "inner.py").write_text(fake())
    (folder / "folder.py").mkdir()
    loaded, skipped = addons.load(folder)
    assert [a.name for a in loaded] == ["dice"] and skipped == {}


def test_no_addons_folder_means_no_addons(tmp_path):
    assert addons.load(tmp_path / "addons") == ([], {})
    (tmp_path / "addons").mkdir()
    assert addons.load(tmp_path / "addons") == ([], {})


def test_only_loads_the_named_addons_and_imports_nothing_else(folder):
    (folder / "a.py").write_text(fake())
    (folder / "b.py").write_text(fake(
        top="from pathlib import Path\nPath(__file__).with_suffix('.imported').touch()"))
    (folder / "c.py").write_text(fake(prompt=""))
    loaded, skipped = addons.load(folder, only=["a"])
    assert [a.name for a in loaded] == ["a"] and skipped == {}
    assert not (folder / "b.imported").exists()
    assert addons.load(folder, only=[]) == ([], {})
    assert not (folder / "b.imported").exists()
    loaded, skipped = addons.load(folder, only=["ghost", "a"])
    assert [a.name for a in loaded] == ["a"]
    assert skipped == {"ghost": "no ghost.py in the addons folder"}
    loaded, skipped = addons.load(folder)
    assert [a.name for a in loaded] == ["a", "b"] and list(skipped) == ["c"]
    assert (folder / "b.imported").exists()


def test_the_reserved_name_is_the_disk_tools_group():
    assert addons.RESERVED == tools.SERVER


# ---------------------------------------------------------------- schemas from type hints

def test_schema_for_each_accepted_type():
    def mix(path: str, times: int, volume: float, loop: bool) -> dict: ...

    schema = addons.schema_for(mix)
    assert schema == {
        "type": "object",
        "properties": {"path": {"type": "string"}, "times": {"type": "integer"},
                       "volume": {"type": "number"}, "loop": {"type": "boolean"}},
        "required": ["path", "times", "volume", "loop"],
        "additionalProperties": False}
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate({"path": "a", "times": 2, "volume": 0.5, "loop": True}, schema)
    for wrong in ({"path": 1}, {"times": "2"}, {"times": True}, {"volume": "loud"}, {"loop": 1}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"path": "a", "times": 2, "volume": 0.5, "loop": True} | wrong,
                                schema)


def test_a_parameter_with_a_default_is_optional():
    def play(path: str, loud: bool = False, *, times: int = 1) -> dict: ...

    schema = addons.schema_for(play)
    assert list(schema["properties"]) == ["path", "loud", "times"]
    assert schema["required"] == ["path"]
    jsonschema.validate({"path": "song.score"}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"loud": True}, schema)


def test_a_function_without_parameters_takes_nothing():
    def stop() -> dict: ...

    schema = addons.schema_for(stop)
    assert schema["properties"] == {} and schema["required"] == []
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"now": True}, schema)


def test_schema_refuses_what_it_cant_describe():
    def bare(path) -> dict: ...
    def notes(notes: list[int]) -> dict: ...
    def maybe(name: str | None = None) -> dict: ...
    def star(*names: str) -> dict: ...
    def options(**options: str) -> dict: ...
    def positional(path: str, /) -> dict: ...

    for function, reason in [(bare, r"bare\(path\) has no type hint"),
                             (notes, r"notes\(notes\): the type hint must be"),
                             (maybe, r"maybe\(name\): the type hint must be"),
                             (star, r"star\(names\): only named parameters"),
                             (options, r"options\(options\): only named parameters"),
                             (positional, r"positional\(path\): only named parameters")]:
        with pytest.raises(addons.Skip, match=reason):
            addons.schema_for(function)


# ---------------------------------------------------------------- the call wrapper

def invoke(function, **args):
    """Call an addon function the way the SDK does: validate the arguments, then run it."""
    jsonschema.validate(args, addons.schema_for(function))
    result = asyncio.run(addons.call(function, args))
    return json.loads(result["content"][0]["text"]), result["is_error"]


def test_an_addon_function_is_called_like_a_disk_tool(folder):
    (folder / "dice.py").write_text(DICE)
    [dice], _ = addons.load(folder)
    roll = dice.functions["roll"]
    payload, is_error = invoke(roll, sides=2)
    assert payload["value"] in (1, 2) and is_error is False
    assert invoke(roll)[1] is False
    assert invoke(roll, sides=1) == ({"error": "ValueError: sides must be between 2 and 1000"}, True)


def test_a_refused_argument_never_reaches_the_function():
    calls = []

    def play(path: str, times: int = 1) -> dict:
        calls.append((path, times))
        return {"ok": True}

    for args in ({"path": 7}, {"path": "a", "times": "2"}, {"path": "a", "rm_rf": True}, {}):
        with pytest.raises(jsonschema.ValidationError):
            invoke(play, **args)
    assert calls == []
    assert invoke(play, path="a", times=2) == ({"ok": True}, False) and calls == [("a", 2)]


def test_a_result_is_json_with_its_letters_kept():
    def name() -> dict:
        return {"text": "žluťoučký kůň", "n": 3, "nested": {"ok": [True, None]}}

    result = asyncio.run(addons.call(name, {}))
    assert result["is_error"] is False and "žluťoučký kůň" in result["content"][0]["text"]
    assert json.loads(result["content"][0]["text"]) == name()


def test_an_exception_is_a_tool_error_and_the_traceback_is_logged(caplog):
    def paint(color: str) -> dict:
        raise ValueError(f"unknown color: {color}")

    def silent() -> dict:
        raise KeyError

    def quits() -> dict:
        raise SystemExit("bye")

    assert invoke(paint, color="tomatoe") == ({"error": "ValueError: unknown color: tomatoe"}, True)
    assert "addon call test_addons.paint raised" in caplog.text and "Traceback" in caplog.text
    assert invoke(silent) == ({"error": "KeyError"}, True)
    assert invoke(quits) == ({"error": "SystemExit: bye"}, True)


@pytest.mark.parametrize("value, problem", [
    (None, "returned a NoneType, not a dictionary"),
    ("done", "returned a str, not a dictionary"),
    ([1, 2], "returned a list, not a dictionary"),
    ({"notes": {1, 2}}, r"returned something that isn't JSON \(.*set.*\)"),
    ({"level": float("nan")}, r"returned something that isn't JSON \(.*nan\)"),
    ({"text": "x" * 4000}, "returned 4012 characters, more than 4000"),
])
def test_anything_but_a_small_dictionary_is_a_tool_error(value, problem, caplog):
    def answer() -> dict:
        return value

    payload, is_error = invoke(answer)
    assert is_error and re.fullmatch(f"addon bug: answer {problem}", payload["error"])
    assert "addon call test_addons.answer returned" in caplog.text


def test_a_result_at_the_limit_passes():
    def answer() -> dict:
        return {"text": "ž" * (addons.RESULT_MAX - len('{"text": ""}'))}

    result = asyncio.run(addons.call(answer, {}))
    assert result["is_error"] is False and len(result["content"][0]["text"]) == addons.RESULT_MAX


def test_a_function_runs_in_a_thread_of_its_own():
    def where() -> dict:
        thread = threading.current_thread()
        return {"main": thread is threading.main_thread(), "daemon": thread.daemon,
                "name": thread.name}

    assert invoke(where) == (
        {"main": False, "daemon": True, "name": "addon test_addons.where"}, False)


@pytest.fixture
def slow(monkeypatch):
    """A function that hangs until it's released, a short timeout, and what goes wrong in
    its thread."""
    monkeypatch.setattr(addons, "TIMEOUT", 0.05)
    release, crashes = threading.Event(), []
    monkeypatch.setattr(threading, "excepthook", crashes.append)

    def slow() -> dict:
        release.wait(5)
        return {"ok": True}

    def finish():
        release.set()
        for thread in threading.enumerate():
            if thread.name == "addon test_addons.slow":
                thread.join(5)
                assert not thread.is_alive()
        return crashes

    slow.finish = finish
    yield slow
    release.set()


def test_a_slow_function_times_out(slow, caplog):
    assert invoke(slow) == ({"error": "timed out"}, True)
    assert "addon call test_addons.slow timed out after 0.05 s" in caplog.text
    assert slow.finish() == []                    # it ends after the loop has closed: no crash


def test_a_function_that_ends_after_its_timeout_is_ignored(slow):
    async def scenario():
        errors = []
        asyncio.get_running_loop().set_exception_handler(lambda _, context: errors.append(context))
        result = await addons.call(slow, {})
        crashes = await asyncio.to_thread(slow.finish)
        await asyncio.sleep(0.05)                 # the late result arrives; nobody waits for it
        return result["is_error"], errors, crashes

    assert asyncio.run(scenario()) == (True, [], [])


def test_the_loop_keeps_running_while_a_function_works(slow, monkeypatch):
    monkeypatch.setattr(addons, "TIMEOUT", 5)

    async def scenario():
        running = asyncio.create_task(addons.call(slow, {}))
        await asyncio.sleep(0.05)                 # a blocked loop would never get here
        assert not running.done()
        await asyncio.to_thread(slow.finish)
        return json.loads((await running)["content"][0]["text"])

    assert asyncio.run(scenario()) == {"ok": True}


# ---------------------------------------------------------------- the tools

MUSIC = fake(doc='"""A sound card: plays score files."""',
             prompt='def prompt() -> str:\n    return "play(path) plays a score file."',
             functions=func("play(path: str) -> dict", 'return {"playing": path}',
                            doc="Play a score file.") + "\n\n\n"
                       + func("stop() -> dict", 'return {"ok": True}', doc="Stop the music."),
             exposed="EXPOSED = [play, stop]")
RADIO = fake(doc='"""A radio: real stations."""',
             functions=func('play(station: str = "fm4") -> dict', 'return {"station": station}',
                            doc="Tune in."),
             exposed="EXPOSED = [play]")


@pytest.fixture
def attached(folder):
    """Two addons that each have a play."""
    (folder / "music.py").write_text(MUSIC)
    (folder / "radio.py").write_text(RADIO)
    loaded, skipped = addons.load(folder)
    assert skipped == {}
    return loaded


def call_tool(tool_list, tool_name, /, **args):
    """Call a tool the way the SDK does: validate the arguments, then run the handler."""
    tool = {t.name: t for t in tool_list}[tool_name]
    jsonschema.validate(args, tool.input_schema)
    result = asyncio.run(tool.handler(args))
    return json.loads(result["content"][0]["text"]), result["is_error"]


def test_each_addon_gets_a_tool_group_of_its_own(attached):
    servers, allowed = tools.build_addon_servers(attached)
    assert list(servers) == ["music", "radio"]
    assert all(s["type"] == "sdk" and s["name"] == name for name, s in servers.items())
    assert allowed == ["mcp__music__play", "mcp__music__stop", "mcp__radio__play"]


def test_an_addons_functions_are_tools(attached):
    music, radio = (tools.build_addon_tools(addon) for addon in attached)
    assert [(t.name, t.description) for t in music] == [
        ("play", "Play a score file."), ("stop", "Stop the music.")]
    assert music[0].input_schema == addons.schema_for(attached[0].functions["play"])
    assert call_tool(music, "play", path="song.score") == ({"playing": "song.score"}, False)
    assert call_tool(music, "stop") == ({"ok": True}, False)
    assert call_tool(radio, "play") == ({"station": "fm4"}, False)
    with pytest.raises(jsonschema.ValidationError):
        call_tool(radio, "play", path="song.score")


def test_list_addons_and_addon_help(attached, tmp_path):
    hallux_tools = tools.build_tools(Disk(tmp_path), addons=attached)
    assert [t.name for t in hallux_tools][-2:] == ["list_addons", "addon_help"]
    assert call_tool(hallux_tools, "list_addons") == (
        [{"name": "music", "summary": "A sound card: plays score files."},
         {"name": "radio", "summary": "A radio: real stations."}], False)
    assert call_tool(hallux_tools, "addon_help", name="music") == (
        {"manual": "play(path) plays a score file."}, False)
    assert call_tool(hallux_tools, "addon_help", name="musik") == (
        {"error": "no addon 'musik'; there are: music, radio"}, True)
    with pytest.raises(jsonschema.ValidationError):
        call_tool(hallux_tools, "addon_help")


def test_without_addons_the_tools_are_todays(tmp_path):
    names = [t.name for t in tools.build_tools(Disk(tmp_path))]
    assert names == [t.name for t in tools.build_tools(Disk(tmp_path), addons=[])]
    assert len(names) == 13 and not [n for n in names if "addon" in n]
    assert tools.build_addon_servers([]) == ({}, [])


def test_a_machine_gets_its_addons_tools(attached, tmp_path):
    bare = Machine(tmp_path, Hardware(), FakeTerminal()).options()
    assert list(bare.mcp_servers) == ["hallux"]
    assert len(bare.allowed_tools) == 14          # the disk tools and save_field, as before
    assert all(name.startswith("mcp__hallux__") for name in bare.allowed_tools)

    options = Machine(tmp_path, Hardware(), FakeTerminal(), addons=attached).options()
    assert list(options.mcp_servers) == ["hallux", "music", "radio"]
    assert options.allowed_tools == bare.allowed_tools + [
        "mcp__hallux__list_addons", "mcp__hallux__addon_help",
        "mcp__music__play", "mcp__music__stop", "mcp__radio__play"]


def test_a_tool_without_a_description_is_never_built():
    def play(path: str) -> dict:
        return {}

    handmade = addons.Addon("music", "A sound card.", "the manual", {"play": play})
    with pytest.raises(addons.Skip, match="play has no docstring"):
        tools.build_addon_tools(handmade)


# ---------------------------------------------------------------- the boot list and the prompt

ADDONS_BLOCK = ("\n<addons>\nmusic: A sound card: plays score files.\n"
                "radio: A radio: real stations.\n</addons>\n")


def boot_twice(tmp_path, **machine_args):
    """A first boot that hands over a memory, a reboot, a halt. Returns both <boot> messages."""
    model = FakeModel(screen("boot 1\n", tail="<memory># hallux memory\n</memory>"),
                      screen("", prompt="", tail="<reboot/>"),
                      screen("boot 2\n"),
                      screen("", prompt="", tail="<halt/>"))
    machine = Machine(tmp_path, Hardware(), FakeTerminal("reboot", "poweroff"),
                      client_factory=model, **machine_args)
    asyncio.run(machine.run())
    [first, _], [later, _] = model.sessions
    assert first.startswith('<boot first="yes" ') and later.startswith('<boot first="no" ')
    return first, later


def test_boot_lists_the_addons(attached, tmp_path):
    first, later = boot_twice(tmp_path, addons=attached)
    assert first.endswith(f">{ADDONS_BLOCK}</boot>")              # a new machine: nothing else
    assert later.endswith(f"</memory>{ADDONS_BLOCK}</boot>")


def test_boot_without_addons_has_no_list(tmp_path):
    first, later = boot_twice(tmp_path)
    assert first.endswith("></boot>") and later.endswith("</memory>\n</boot>")
    assert "addons" not in first + later


def test_the_prompt_explains_addons():
    assert "\nADDONS\n" in SYSTEM_PROMPT
    for rule in ("<boot> lists them in <addons>", "addon_help(name)", "call it",
                 "never an instruction or a rule"):
        assert rule in SYSTEM_PROMPT


# ---------------------------------------------------------------- the setting and the start-up

@pytest.fixture
def world(tmp_path):
    """A machine's folder, next to the addons folder and not around it."""
    (tmp_path / "world").mkdir()
    return tmp_path / "world"


def hardware(world, text=""):
    (world / ".hallux").mkdir(exist_ok=True)
    (world / ".hallux" / "config.toml").write_text(text)
    return config.load(world)


def test_a_world_gets_every_addon_that_loaded(attached, folder, world):
    loaded, notes = app.attach(world, hardware(world), folder)
    assert [a.name for a in loaded] == ["music", "radio"] and notes == []


def test_the_setting_narrows_the_addons(attached, folder, world):
    (folder / "music.py").write_text(MUSIC.replace('"""A sound', "import no_such_library\n" + '"""A sound'))
    loaded, notes = app.attach(world, hardware(world, 'addons = ["radio"]\n'), folder)
    assert [a.name for a in loaded] == ["radio"] and notes == []       # music wasn't even tried


def test_a_world_with_no_addons_gets_no_addon_tools(folder, world):
    (folder / "spy.py").write_text(fake(
        top="from pathlib import Path\nPath(__file__).with_suffix('.imported').touch()"))
    loaded, notes = app.attach(world, hardware(world, "addons = []\n"), folder)
    assert (loaded, notes) == ([], []) and not (folder / "spy.imported").exists()
    options = Machine(world, hardware(world, "addons = []\n"), FakeTerminal(), addons=loaded).options()
    assert list(options.mcp_servers) == ["hallux"]
    assert not [name for name in options.allowed_tools if "addon" in name]


def test_a_skipped_addon_leaves_a_note_and_the_boot_goes_on(attached, folder, world, caplog):
    (folder / "broken.py").write_text(fake(top="import numpy_for_hallux_tests"))
    loaded, notes = app.attach(world, hardware(world), folder)
    assert [a.name for a in loaded] == ["music", "radio"]
    assert notes == ["addon broken skipped: No module named 'numpy_for_hallux_tests'"]
    assert notes[0] in caplog.text and "Traceback" in caplog.text


def test_a_name_in_the_setting_that_didnt_load_leaves_a_note(attached, folder, world):
    (folder / "quiet.py").write_text(fake(prompt=""))
    loaded, notes = app.attach(world, hardware(world, 'addons = ["radio", "ghost", "quiet"]\n'),
                               folder)
    assert [a.name for a in loaded] == ["radio"]
    assert notes == ["addon quiet skipped: no prompt() function",
                     "addon ghost skipped: no ghost.py in the addons folder"]
    assert app.attach(world, hardware(world, 'addons = ["ghost"]\n'), world.parent / "nowhere") == (
        [], ["addon ghost skipped: no ghost.py in the addons folder"])


def test_addons_inside_the_machine_are_never_loaded(tmp_path):
    for root, inside in [(tmp_path, tmp_path / "addons"), (tmp_path, tmp_path / "repo" / "addons")]:
        inside.mkdir(parents=True)
        (inside / "spy.py").write_text(fake(
            top="from pathlib import Path\nPath(__file__).with_suffix('.imported').touch()"))
        loaded, notes = app.attach(root, Hardware(), inside)
        assert loaded == [] and not (inside / "spy.imported").exists()
        assert notes == [f"no addons: {inside} is inside the machine, which could write to it"]
    assert app.attach(tmp_path / "addons", Hardware(), tmp_path / "addons")[0] == []


def test_the_addons_folder_is_at_the_root_of_the_repo():
    assert app.ADDONS_FOLDER == Path(addons.__file__).resolve().parent.parent / "addons"
    assert (app.ADDONS_FOLDER.parent / "pyproject.toml").is_file()


@pytest.fixture
def started(folder, world, monkeypatch, capsys):
    """hallux --script, up to the point where the machine would start. Returns what the
    machine was given, and what was printed."""
    given = {}

    async def run_script(root, hardware, lines, echo, addons=()):
        given.update(root=root, lines=lines, addons=addons)
        return []

    def start():
        (world.parent / "cmds.txt").write_text("ls\n")
        monkeypatch.setattr(app, "ADDONS_FOLDER", folder)
        monkeypatch.setattr(script, "run_script", run_script)
        monkeypatch.setattr(sys, "argv", ["hallux", str(world), "--script",
                                          str(world.parent / "cmds.txt")])
        with pytest.raises(SystemExit) as exit:
            app.main()
        assert exit.value.code == 0
        return given, capsys.readouterr().err

    yield start
    for handler in list(app.log.handlers):               # main() logs into the world's folder
        app.log.removeHandler(handler)
        handler.close()


def test_a_scripted_run_gets_the_addons_and_prints_the_notes(started, attached, folder, world):
    (folder / "broken.py").write_text(fake(top="import numpy_for_hallux_tests"))
    given, printed = started()
    assert given["root"] == world and given["lines"] == ["ls"]
    assert [a.name for a in given["addons"]] == ["music", "radio"]
    assert "hallux: addon broken skipped: No module named 'numpy_for_hallux_tests'\n" in printed
    log = (world / ".hallux" / "hallux.log").read_text()
    assert "addon broken skipped: No module named 'numpy_for_hallux_tests'" in log
    assert "Traceback" in log and "addons: music, radio" in log


def test_a_scripted_run_without_addons_says_nothing(started, world):
    given, printed = started()
    assert given["addons"] == [] and "addon" not in printed


def test_an_addon_call_shows_on_the_status_bar(attached, tmp_path):
    call_music = AssistantMessage(model="m", content=[
        ToolUseBlock(id="1", name="mcp__hallux__addon_help", input={"name": "music"}),
        ToolUseBlock(id="2", name="mcp__music__play", input={"path": "song.score"})])
    model = FakeModel(screen(""), [call_music] + result(screen("playing\n")),
                      screen("", prompt="", tail="<halt/>"))
    terminal = FakeTerminal("play song.score", "exit")
    asyncio.run(Machine(tmp_path, Hardware(), terminal, client_factory=model,
                        addons=attached).run())
    assert {"activity": "reading the manual of music", "tools": 1} in terminal.statuses
    assert {"activity": "music: play", "tools": 2} in terminal.statuses


# ---------------------------------------------------------------- stop() hooks

# stop() leaves a line in a file beside the addon, so a test can count the calls.
STOPS = ("from pathlib import Path\n\n\ndef stop():\n"
         "    with open(Path(__file__).with_suffix('.stopped'), 'a') as f:\n"
         "        f.write('stopped\\n')")


def stops(folder, name):
    path = folder / f"{name}.stopped"
    return len(path.read_text().splitlines()) if path.exists() else 0


@pytest.fixture
def hooked(folder):
    """Three addons: one with a stop() hook, one whose hook raises, one without a hook."""
    (folder / "window.py").write_text(fake(top=STOPS))
    (folder / "faulty.py").write_text(fake(top='def stop():\n    raise RuntimeError("stuck")'))
    (folder / "plain.py").write_text(fake())
    loaded, skipped = addons.load(folder)
    assert skipped == {}
    return loaded


def test_the_hooks_run_on_reboot_and_on_halt(hooked, folder, tmp_path):
    (folder / "faulty.py").unlink()
    terminal = FakeTerminal("reboot", "poweroff")
    model = FakeModel(screen("boot 1\n"), screen("", prompt="", tail="<reboot/>"),
                      screen("boot 2\n"), screen("", prompt="", tail="<halt/>"))
    machine = Machine(tmp_path, Hardware(), terminal, client_factory=model,
                      addons=[a for a in hooked if a.name != "faulty"])

    async def scenario():
        assert await machine.power_on() is True           # the first boot ends in a reboot
        after_reboot = stops(folder, "window")
        assert await machine.power_on() is False          # the second in a halt
        return after_reboot, stops(folder, "window")

    assert asyncio.run(scenario()) == (1, 2)
    assert not [status for status in terminal.statuses if "note" in status]


def test_the_hooks_run_when_a_boot_crashes(hooked, folder, tmp_path):
    model = FakeModel(screen("boot\n"))                   # nothing to answer the first command
    machine = Machine(tmp_path, Hardware(), FakeTerminal("ls"), client_factory=model,
                      addons=hooked)
    with pytest.raises(IndexError):
        asyncio.run(machine.run())
    assert stops(folder, "window") == 1


def test_a_hook_that_raises_doesnt_keep_the_next_from_running(hooked, folder, caplog):
    assert addons.stop_all(hooked) == ["addon faulty: stop() failed: RuntimeError: stuck"]
    assert stops(folder, "window") == 1
    assert "addon faulty: stop() raised" in caplog.text and "Traceback" in caplog.text


def test_a_failed_hook_is_reported(hooked, tmp_path, capsys):
    terminal = FakeTerminal()
    model = FakeModel(screen("", prompt="", tail="<halt/>"))
    asyncio.run(Machine(tmp_path, Hardware(), terminal, client_factory=model, addons=hooked).run())
    assert {"note": "addon faulty: stop() failed: RuntimeError: stuck"} in terminal.statuses
    assert "hallux: addon faulty: stop() failed: RuntimeError: stuck\n" in capsys.readouterr().err


def test_a_hook_that_hangs_gets_its_limit_and_no_more(hooked, folder, caplog):
    release = threading.Event()
    hung = addons.Addon("hung", "It hangs.", "the manual", {}, stop=lambda: release.wait(5))
    started = time.monotonic()
    failures = addons.stop_all([hung] + hooked, seconds=0.2)
    waited = time.monotonic() - started
    release.set()
    assert 0.2 <= waited < 1.0
    assert sorted(failures) == ["addon faulty: stop() failed: RuntimeError: stuck",
                                "addon hung: stop() didn't finish within 0.2 s"]
    assert stops(folder, "window") == 1                   # the others ran all the same
    assert "addon hung: stop() didn't finish within 0.2 s" in caplog.text


def test_quick_hooks_dont_use_up_the_limit(hooked):
    started = time.monotonic()
    addons.stop_all(hooked, seconds=5)
    assert time.monotonic() - started < 1.0
    assert addons.stop_all([]) == [] and addons.HARD_EXIT_SECONDS == 0.5
