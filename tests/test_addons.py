import json
import re
import sys

import pytest

from hallux import addons, tools

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


def fake(doc='"""A fake addon."""',
         prompt='def prompt() -> str:\n    return "the manual"',
         functions='def ping() -> dict:\n    return {"ok": True}',
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
        functions="def play(path: str, loud: bool = False) -> dict:\n    return {}\n\n\n"
                  "def helper(anything):\n    return anything",
        exposed="EXPOSED = (play,)"))
    [sound], _ = addons.load(folder)
    assert list(sound.functions) == ["play"]


def test_hints_written_as_text_are_read(folder):
    (folder / "late.py").write_text(fake(
        top="from __future__ import annotations",
        functions="def scale(by: float, *, name: str) -> dict:\n    return {}",
        exposed="EXPOSED = [scale]"))
    assert [a.name for a in addons.load(folder)[0]] == ["late"]


def test_stop_is_the_hook_and_a_tool_only_when_exposed(folder):
    stop = "def stop() -> dict:\n    return {'ok': True}"
    (folder / "hook.py").write_text(fake(top=stop))
    (folder / "both.py").write_text(fake(top=stop, exposed="EXPOSED = [ping, stop]"))
    [both, hook], skipped = addons.load(folder)
    assert skipped == {}
    assert hook.stop() == {"ok": True} and list(hook.functions) == ["ping"]
    assert both.stop is both.functions["stop"]


def test_stop_may_take_arguments_if_it_works_without_them(folder):
    (folder / "fade.py").write_text(fake(
        top="def stop(fade: float = 0.0) -> dict:\n    return {'fade': fade}",
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
    # 7. the type hints
    ("bare.py", fake(functions="def ping(times) -> dict:\n    return {}"),
     r"ping\(times\) has no type hint"),
    ("notes.py", fake(functions="def ping(notes: list) -> dict:\n    return {}"),
     r"ping\(notes\): the type hint must be str, int, float or bool"),
    ("maybe.py", fake(functions="def ping(name: str | None = None) -> dict:\n    return {}"),
     r"ping\(name\): the type hint must be"),
    ("star.py", fake(functions="def ping(*names: str) -> dict:\n    return {}"),
     r"ping\(names\): only named parameters"),
    ("kwargs.py", fake(functions="def ping(**options: str) -> dict:\n    return {}"),
     r"ping\(options\): only named parameters"),
    ("unknown.py", fake(top="from __future__ import annotations",
                        functions="def ping(color: Colour) -> dict:\n    return {}"),
     "NameError: name 'Colour' is not defined"),
    # 8. stop
    ("force.py", fake(top="def stop(force: bool) -> dict:\n    return {}"),
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
    loaded, skipped = addons.load(folder)
    assert [a.name for a in loaded] == ["a", "b"] and list(skipped) == ["c"]
    assert (folder / "b.imported").exists()


def test_the_reserved_name_is_the_disk_tools_group():
    assert addons.RESERVED == tools.SERVER
