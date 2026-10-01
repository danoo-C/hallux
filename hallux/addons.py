"""Addons: real abilities the machine can't imagine, one Python file each (docs/addons.md).

An addon is a bridge, like a sound card. Its file holds a docstring whose first line is the
summary, prompt(), which returns the manual, and EXPOSED, the list of functions the AI may
call. Importing an addon runs its code with your full rights, so the folder must be one that
no machine can write to.
"""
from __future__ import annotations

import importlib.util
import inspect
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterable

log = logging.getLogger("hallux")

MODULE_PREFIX = "hallux_addon_"               # so an addon called music can't shadow a package
RESERVED = "hallux"                           # the disk tools' group (hallux.tools.SERVER)
# No double underscore: the AI sees mcp__<addon>__<function>, split at the "__".
ADDON_NAME = re.compile(r"[a-z](_?[a-z0-9])*")
FUNCTION_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
HINTS = (str, int, float, bool)


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

    Returns the addons that passed and, for every other file, the reason it was skipped.
    Nothing an addon does here raises: a broken one must not keep the machine from starting."""
    wanted = None if only is None else set(only)
    addons, skipped = [], {}
    for path in sorted(Path(folder).glob("*.py")):
        name = path.stem
        if not path.is_file() or (wanted is not None and name not in wanted):
            continue
        try:
            addons.append(_check(path))
        except Skip as e:
            skipped[name] = str(e)
            log.warning("addon %s skipped: %s", name, e)
        except (Exception, SystemExit) as e:  # raised by the addon's own code
            skipped[name] = str(e) if isinstance(e, ImportError) else f"{type(e).__name__}: {e}"
            log.warning("addon %s skipped: %s", name, skipped[name], exc_info=True)
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
        if not FUNCTION_NAME.fullmatch(function.__name__):
            raise Skip(f"EXPOSED holds a function called {function.__name__}, which can't "
                       f"be a tool name")
        if function.__name__ in functions:
            raise Skip(f"EXPOSED holds two functions called {function.__name__}")
        functions[function.__name__] = function
    for function in functions.values():
        _check_hints(function)

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


def _check_hints(function: Callable) -> None:
    """Every parameter needs a type hint that can become a JSON schema."""
    for p in inspect.signature(function, eval_str=True).parameters.values():
        where = f"{function.__name__}({p.name})"
        if p.kind not in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
            raise Skip(f"{where}: only named parameters work, not *args, **kwargs or "
                       f"positional-only ones")
        if p.annotation is p.empty:
            raise Skip(f"{where} has no type hint")
        if not any(p.annotation is hint for hint in HINTS):
            raise Skip(f"{where}: the type hint must be str, int, float or bool")
