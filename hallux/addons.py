"""Addons: real abilities the machine can't imagine, one Python file each (docs/addons.md).

An addon is a bridge, like a sound card. Its file holds a docstring whose first line is the
summary, prompt(), which returns the manual, and EXPOSED, the list of functions the AI may
call. Importing an addon runs its code with your full rights, so the folder must be one that
no machine can write to.

load() finds and checks the addons. description_for() and schema_for() turn a function's
docstring and type hints into a tool, call() runs a function for the AI, and stop_all() ends
whatever the addons still have running.
"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import logging
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

log = logging.getLogger("hallux")

MODULE_PREFIX = "hallux_addon_"               # so an addon called music can't shadow a package
RESERVED = "hallux"                           # the disk tools' group (hallux.tools.SERVER)
# No double underscore: the AI sees mcp__<addon>__<function>, split at the "__".
ADDON_NAME = re.compile(r"[a-z](_?[a-z0-9])*")
FUNCTION_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}
TIMEOUT = 10.0                                # seconds a call may take
RESULT_MAX = 4000                             # characters of JSON a call may return
HARD_EXIT_SECONDS = 0.5                       # all the stop() hooks together, on the hard exit


@dataclass(frozen=True)
class Addon:
    name: str                                 # the file name without .py
    summary: str                              # the docstring's first line
    manual: str                               # what prompt() returned
    functions: dict[str, Callable]            # EXPOSED by name: all the AI can reach
    stop: Callable[..., object] | None = None  # ends what's still running; called bare


class Skip(Exception):
    """A check failed; the message is the reason."""


def load(folder: Path, only: Iterable[str] | None = None) -> tuple[list[Addon], dict[str, str]]:
    """Import and check every .py file in `folder`, or just the addons named in `only`.

    Returns the addons that passed and, for every other file, the reason it was skipped. A
    name in `only` that has no file is skipped too, with that as the reason.
    Nothing an addon does here raises: a broken one must not keep the machine from starting."""
    wanted = None if only is None else set(only)
    addons, skipped, found = [], {}, set()
    for path in sorted(Path(folder).glob("*.py")):
        name = path.stem
        if not path.is_file() or (wanted is not None and name not in wanted):
            continue
        found.add(name)
        try:
            addons.append(_check(path))
        except Skip as e:
            skipped[name] = str(e)
            log.warning("addon %s skipped: %s", name, e)
        except (Exception, SystemExit) as e:  # raised by the addon's own code
            skipped[name] = str(e) if isinstance(e, ImportError) else _describe(e)
            log.warning("addon %s skipped: %s", name, skipped[name], exc_info=True)
    for name in sorted((wanted or set()) - found):
        skipped[name] = f"no {name}.py in the addons folder"
        log.warning("addon %s skipped: %s", name, skipped[name])
    return addons, skipped


def _check(path: Path) -> Addon:
    """The checks, in order; the first that fails skips the addon."""
    name = path.stem
    if not ADDON_NAME.fullmatch(name):
        raise Skip("the file name must be lowercase letters and digits, starting with a "
                   "letter, with single underscores between them")
    if name == RESERVED:
        raise Skip(f"the name {RESERVED} is taken by the disk tools")

    module = _import(path)

    doc = inspect.getdoc(module) or ""
    summary = doc.partition("\n")[0].strip()
    if not summary:
        raise Skip("no docstring: its first line is the addon's summary")

    prompt = getattr(module, "prompt", None)
    if not callable(prompt):
        raise Skip("no prompt() function")
    manual = prompt()
    if not isinstance(manual, str) or not manual.strip():
        raise Skip("prompt() returned no text")

    exposed = getattr(module, "EXPOSED", None)
    if not isinstance(exposed, list | tuple):
        raise Skip("no EXPOSED list")
    if not exposed:
        raise Skip("EXPOSED is empty: the AI would have nothing to call")
    functions: dict[str, Callable] = {}
    for function in exposed:
        if not inspect.isfunction(function):
            raise Skip(f"EXPOSED holds a {type(function).__name__}, not a function")
        if inspect.iscoroutinefunction(function):
            raise Skip(f"{function.__name__} is async: an addon function is a plain def")
        if not FUNCTION_NAME.fullmatch(function.__name__):
            raise Skip(f"EXPOSED holds a function called {function.__name__}, which can't "
                       f"be a tool name")
        if function.__name__ in functions:
            raise Skip(f"EXPOSED holds two functions called {function.__name__}")
        functions[function.__name__] = function
    for function in functions.values():
        description_for(function)
        schema_for(function)

    stop = getattr(module, "stop", None)
    if stop is not None and not _works_bare(stop):
        raise Skip("stop() must work without arguments: that's how Hallux calls it")

    return Addon(name, summary, manual, functions, stop)


def _import(path: Path) -> ModuleType:
    name = MODULE_PREFIX + path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module                # dataclasses and pickle look the module up here
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


def _works_bare(function: object) -> bool:
    """Can it be called with no arguments? Parameters with defaults are fine."""
    try:
        inspect.signature(function).bind()
    except TypeError:                         # a required parameter, or not callable at all
        return False
    return True


def _describe(error: BaseException) -> str:
    name = type(error).__name__
    return f"{name}: {error}" if str(error) else name


def description_for(function: Callable) -> str:
    """What the AI is told a function's tool does: the docstring. Raises Skip without one."""
    description = inspect.getdoc(function)
    if not description:
        raise Skip(f"{function.__name__} has no docstring: it's what the AI is told the "
                   f"function does")
    return description


def schema_for(function: Callable) -> dict[str, Any]:
    """The strict JSON schema of a function's arguments, built from its type hints.

    A parameter with a default is optional. Raises Skip, with the reason, for a parameter
    that has no hint or one that can't become a schema."""
    properties, required = {}, []
    for p in inspect.signature(function, eval_str=True).parameters.values():
        where = f"{function.__name__}({p.name})"
        if p.kind not in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
            raise Skip(f"{where}: only named parameters work, not *args, **kwargs or "
                       f"positional-only ones")
        if p.annotation is p.empty:
            raise Skip(f"{where} has no type hint")
        json_type = next((t for hint, t in JSON_TYPES.items() if p.annotation is hint), None)
        if json_type is None:
            raise Skip(f"{where}: the type hint must be str, int, float or bool")
        properties[p.name] = {"type": json_type}
        if p.default is p.empty:
            required.append(p.name)
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


async def call(function: Callable, args: dict[str, Any]) -> dict[str, Any]:
    """Run an addon function for the AI and turn whatever happens into a tool result.

    The function gets a thread of its own, so a slow one freezes neither the keyboard nor the
    status bar. A thread can't be stopped: after the timeout the AI gets its error, and the
    function runs on with nobody waiting for it."""
    loop = asyncio.get_running_loop()
    outcome: asyncio.Future[tuple[dict, bool]] = loop.create_future()

    def deliver(result: tuple[dict, bool]) -> None:
        if not outcome.done():                # after the timeout nobody is waiting
            outcome.set_result(result)

    def work() -> None:
        result = _run(function, args)
        try:
            loop.call_soon_threadsafe(deliver, result)
        except RuntimeError:                  # the loop is closed: the machine is off
            pass

    # A daemon thread, not asyncio's pool: a function that hangs must not keep Hallux
    # from quitting.
    threading.Thread(target=work, name=f"addon {_label(function)}", daemon=True).start()
    try:
        payload, is_error = await asyncio.wait_for(outcome, TIMEOUT)
    except TimeoutError:
        log.warning("addon call %s timed out after %g s", _label(function), TIMEOUT)
        payload, is_error = {"error": "timed out"}, True
    return {"content": [{"type": "text", "text": _json(payload)}], "is_error": is_error}


def stop_all(addons: Iterable[Addon], seconds: float = TIMEOUT) -> list[str]:
    """Call every addon's stop() hook, so that nothing an addon started outlives the boot.

    The hooks run side by side, each in a thread of its own, and get `seconds` in total. One
    that raises or hangs keeps neither the others from running nor Hallux from going on.
    Returns a line for each hook that failed; the tracebacks are in the log."""
    failures: list[str] = []

    def stop(addon: Addon) -> None:
        try:
            addon.stop()
        except (Exception, SystemExit) as e:
            log.warning("addon %s: stop() raised", addon.name, exc_info=True)
            failures.append(f"addon {addon.name}: stop() failed: {_describe(e)}")

    threads = [(addon, threading.Thread(target=stop, args=(addon,), daemon=True,
                                        name=f"addon {addon.name}.stop"))
               for addon in addons if addon.stop is not None]
    for _, thread in threads:
        thread.start()
    deadline = time.monotonic() + seconds
    for addon, thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
        if thread.is_alive():
            log.warning("addon %s: stop() didn't finish within %g s", addon.name, seconds)
            failures.append(f"addon {addon.name}: stop() didn't finish within {seconds:g} s")
    return failures


def _run(function: Callable, args: dict[str, Any]) -> tuple[dict, bool]:
    """Call the function. Returns what the AI gets, and whether that is an error."""
    try:
        result = function(**args)
    except (Exception, SystemExit) as e:
        log.warning("addon call %s raised", _label(function), exc_info=True)
        return {"error": _describe(e)}, True
    if problem := _problem_with(result):
        log.warning("addon call %s %s", _label(function), problem)
        return {"error": f"addon bug: {function.__name__} {problem}"}, True
    return result, False


def _problem_with(result: object) -> str | None:
    """Why a result can't go to the AI. It has to be a small dictionary: the model reads
    every character of it."""
    if not isinstance(result, dict):
        return f"returned a {type(result).__name__}, not a dictionary"
    try:
        size = len(_json(result))
    except (TypeError, ValueError) as e:
        return f"returned something that isn't JSON ({e})"
    if size > RESULT_MAX:
        return f"returned {size} characters, more than {RESULT_MAX}"
    return None


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def _label(function: Callable) -> str:
    """music.play, for the log."""
    return f"{function.__module__.removeprefix(MODULE_PREFIX)}.{function.__name__}"
