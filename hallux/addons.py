"""Addons: real abilities the machine can't imagine, one Python file each (docs/addons.md).

An addon is a bridge, like a sound card. Its file holds a docstring whose first line is the
summary, prompt(), which returns the manual, and EXPOSED, the list of functions the AI may
call. Importing an addon runs its code with your full rights, so the folder must be one that
no machine can write to.

load() finds and checks the addons. description_for() and schema_for() turn a function's
docstring and type hints into a tool, call() runs a function for the AI, and stop_all() ends
whatever the addons still have running.

An addon can also report that something happened, such as a button pressed in its window
(docs/addon-events.md). It defines connect(emit), and what it emits waits in Events, the hub,
if the AI listens to that addon.

An addon must not open a path of the machine by itself: it would work around the path jail.
A function whose first parameter is called disk gets a DiskHandle instead.

An addon can also bring an agent: a second AI that works in the background, in a job of its
own (docs/addon-agents.md). It defines agent(), which returns the declaration, and starts a
job from a function that has a parameter called spawn, which Hallux fills as it fills disk.
"""
from __future__ import annotations

import asyncio
import contextlib
import copy
import errno
import functools
import importlib.util
import inspect
import json
import logging
import re
import sys
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

from hallux.disk import Disk

log = logging.getLogger("hallux")

MODULE_PREFIX = "hallux_addon_"               # so an addon called music can't shadow a package
RESERVED = "hallux"                           # the disk tools' group (hallux.tools.SERVER)
DISK = "disk"                                 # a first parameter of this name gets the handle
SPAWN = "spawn"                               # a parameter of this name gets what starts a job
EFFORTS = ("low", "medium", "high", "xhigh", "max")      # for the machine, and for an agent
AGENT_KEYS = ("name", "prompt", "tools", "effort", "status")    # of a declaration: the first
STATUS_MAX = 80                               # three are required; a status line's characters
# No double underscore: the AI sees mcp__<addon>__<function>, split at the "__".
ADDON_NAME = re.compile(r"[a-z](_?[a-z0-9])*")
FUNCTION_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
JSON_TYPES = {str: {"type": "string"}, int: {"type": "integer"}, float: {"type": "number"},
              bool: {"type": "boolean"}, list[str]: {"type": "array", "items": {"type": "string"}}}
TIMEOUT = 10.0                                # seconds a call may take
RESULT_MAX = 4000                             # characters of JSON a call may return
HARD_EXIT_SECONDS = 0.5                       # all the stop() hooks together, on the hard exit
EVENTS_MAX = 10                               # events that may wait for the AI at a time


@dataclass(frozen=True)
class Agent:
    """What an addon's agent() declares: who its agent is, and what a job of it gets."""
    name: str                                 # how its jobs show in the process table
    prompt: str                               # its own instructions; hallux's rules go in front
    tools: dict[str, Callable]                # the addon's functions it may call, by name
    effort: str | None = None                 # what it asks for; config.toml decides
    status: str | None = None                 # its status line until it sets one; None: its name


@dataclass(frozen=True)
class Addon:
    name: str                                 # the file name without .py
    summary: str                              # the docstring's first line
    manual: str                               # what prompt() returned
    functions: dict[str, Callable]            # EXPOSED by name: all the AI can reach
    stop: Callable[..., object] | None = None  # ends what's still running; called bare
    has_events: bool = False                  # it has connect() or an agent: it can be heard
    agent: Agent | None = None                # what agent() declared, if it has one


class Skip(Exception):
    """A check failed; the message is the reason."""


class Refused(Exception):
    """A job can't start. The spawn that hallux hands an addon function raises it, with the
    errno name the AI is told, as a failed fork is: EAGAIN when too many jobs run or a budget
    is used up, or the name the disk has for a folder or a file, with its path. An addon
    imports nothing from hallux, so only hallux raises it; an addon can catch it like any
    error."""

    def __init__(self, code: str, path: str | None = None) -> None:
        super().__init__(code if path is None else f"{code}: {path}")
        self.code, self.path = code, path


class DiskHandle:
    """The machine's files for an addon function, through the path jail (hallux.disk).

    A function whose first parameter is called disk gets one with every call. Paths are the
    machine's: absolute, or relative to its working directory. What the jail refuses raises
    what Disk raises, an OSError or a ValueError, so the function can catch it. One that it
    lets through reaches the AI the way the disk tools say it: {"error": "ENOENT"}."""

    def __init__(self, disk: Disk):
        self._disk = disk
        self._raised: BaseException | None = None

    def read_text(self, path: str) -> str:
        """A whole text file. One over 1 MB is EFBIG, a binary one a ValueError."""
        return self._through(self._disk.read_text, path)

    def write_text(self, path: str, content: str) -> None:
        """Create or overwrite a file. Its folder must exist."""
        self._through(self._disk.write_file, path, content)

    def _through(self, method: Callable, *args: object) -> Any:
        try:
            return method(*args)
        except (OSError, ValueError) as e:
            self._raised = e
            raise

    def refusal(self, error: BaseException) -> str | None:
        """What the AI is told, if `error` is the one this handle raised last. An error of the
        addon's own is none of the handle's, even when it is an OSError too."""
        if error is not self._raised:
            return None
        if isinstance(error, OSError):
            return errno.errorcode.get(error.errno, "EIO")
        return str(error)


class Events:
    """What the addons report, waiting for the AI. One hub for a whole run of Hallux.

    An addon calls its emit from any thread, whenever something happened. Only the events
    of addons the AI listens to are kept; the rest are dropped at once, so they cost nothing."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listening: set[str] = set()
        self._waiting: deque[tuple[str, dict]] = deque()
        self._unheard: Counter[str] = Counter()          # dropped because nobody listened
        self._notes: list[str] = []                      # dropped because something is wrong
        self.paused = False                              # the budget is used up: keep nothing
        self.on_arrival: Callable[[], None] | None = None    # called, in the addon's thread,
                                                             # when an event starts to wait

    def emit(self, addon: str, data: object) -> None:
        """Take one event of an addon. Never raises: the caller is the addon's own thread."""
        with self._lock:
            if addon not in self._listening:
                self._unheard[addon] += 1
                return
            if self.paused:
                return
            if problem := _problem_with(data):
                return self._drop(addon, f"it is {problem}")
            if len(self._waiting) >= EVENTS_MAX:
                return self._drop(addon, f"more than {EVENTS_MAX} are waiting")
            self._waiting.append((addon, json.loads(_json(data))))        # a copy, plain data
            wake = self.on_arrival
        if wake is not None:
            with contextlib.suppress(Exception):         # a loop that has just closed
                wake()

    def _drop(self, addon: str, why: str) -> None:
        note = f"addon {addon}: event dropped: {why}"
        if note not in self._notes:                      # an addon that repeats itself: once
            self._notes.append(note)
            log.warning(note)

    def emitter(self, addon: str) -> Callable[[object], None]:
        """The emit an addon gets in connect(): it reports under the addon's own name."""
        return functools.partial(self.emit, addon)

    def listen(self, addon: str, on: bool = True) -> None:
        """From now on the AI hears this addon. Off also drops what it has waiting."""
        with self._lock:
            if on:
                self._listening.add(addon)
            else:
                self._listening.discard(addon)
                self._waiting = deque(event for event in self._waiting if event[0] != addon)

    def listening(self) -> list[str]:
        with self._lock:
            return sorted(self._listening)

    def pause(self, on: bool = True) -> None:
        """Paused, the hub keeps no event, whoever listens, and drops what waits."""
        with self._lock:
            self.paused = on
            if on:
                self._waiting.clear()

    def pending(self) -> int:
        """How many events wait."""
        with self._lock:
            return len(self._waiting)

    def take(self) -> list[tuple[str, dict]]:
        """Everything that waits, oldest first. The queue is empty afterwards."""
        with self._lock:
            waiting, self._waiting = list(self._waiting), deque()
            return waiting

    def take_notes(self) -> list[str]:
        """What went wrong since the last time, for the status bar."""
        with self._lock:
            notes, self._notes = self._notes, []
            return notes

    def reset(self) -> dict[str, int]:
        """A boot starts or ends: nobody listens, nothing waits. Returns how many events
        nobody listened to, per addon, for the log."""
        with self._lock:
            unheard, self._unheard = dict(self._unheard), Counter()
            self._listening, self._waiting, self.paused = set(), deque(), False
            return unheard


def load(folder: Path, only: Iterable[str] | None = None,
         events: Events | None = None) -> tuple[list[Addon], dict[str, str]]:
    """Import and check every .py file in `folder`, or just the addons named in `only`.

    Returns the addons that passed and, for every other file, the reason it was skipped. A
    name in `only` that has no file is skipped too, with that as the reason. An addon with
    connect() gets its emit from `events`, the hub.
    Nothing an addon does here raises: a broken one must not keep the machine from starting."""
    events = events or Events()
    wanted = None if only is None else set(only)
    addons, skipped, found = [], {}, set()
    for path in sorted(Path(folder).glob("*.py")):
        name = path.stem
        if not path.is_file() or (wanted is not None and name not in wanted):
            continue
        found.add(name)
        try:
            addons.append(_check(path, events))
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


def _check(path: Path, events: Events) -> Addon:
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
    functions = _functions(exposed, "EXPOSED")

    stop = getattr(module, "stop", None)
    if stop is not None and not _works_bare(stop):
        raise Skip("stop() must work without arguments: that's how Hallux calls it")

    agent = _agent(module, functions)

    connect = getattr(module, "connect", None)
    if connect is not None:
        emit = events.emitter(name)
        if not _works_with(connect, emit):
            raise Skip("connect() must work with one argument: the emit function")
        connect(emit)                         # last: only an addon that loads can report

    return Addon(name, summary, manual, functions, stop,
                 has_events=connect is not None or agent is not None, agent=agent)


def _functions(listed: Iterable, where: str) -> dict[str, Callable]:
    """The functions of a list, by name, each checked as a tool: EXPOSED, or an agent's tools."""
    functions: dict[str, Callable] = {}
    for function in listed:
        if not inspect.isfunction(function):
            raise Skip(f"{where} holds a {type(function).__name__}, not a function")
        if inspect.iscoroutinefunction(function):
            raise Skip(f"{function.__name__} is async: an addon function is a plain def")
        if not FUNCTION_NAME.fullmatch(function.__name__):
            raise Skip(f"{where} holds a function called {function.__name__}, which can't "
                       f"be a tool name")
        if function.__name__ in functions:
            raise Skip(f"{where} holds two functions called {function.__name__}")
        functions[function.__name__] = function
    for function in functions.values():
        description_for(function)
        schema_for(function)
    return functions


def _agent(module: ModuleType, functions: dict[str, Callable]) -> Agent | None:
    """What the addon's agent() declares, checked; None for an addon without one. An agent and
    a function that starts its job come together: either alone would do nothing."""
    starters = [name for name, function in functions.items() if takes_spawn(function)]
    declare = getattr(module, "agent", None)
    if declare is None:
        if starters:
            raise Skip(f"{starters[0]} takes {SPAWN}, and the addon has no agent() whose job "
                       f"it could start")
        return None
    if not _works_bare(declare):
        raise Skip("agent() must be a function that works without arguments")
    declared = declare()
    if not isinstance(declared, dict):
        raise Skip(f"agent() returned a {type(declared).__name__}, not a dictionary")
    if unknown := sorted(str(key) for key in declared if key not in AGENT_KEYS):
        raise Skip(f"agent() has a key it can't have: {', '.join(unknown)} "
                   f"(it takes {', '.join(AGENT_KEYS)})")
    if missing := [key for key in AGENT_KEYS[:3] if key not in declared]:
        raise Skip(f"agent() has no {missing[0]}")
    name, prompt, effort, status = (declared.get(key) for key in ("name", "prompt", "effort",
                                                                  "status"))
    if not isinstance(name, str) or not ADDON_NAME.fullmatch(name):
        raise Skip("agent()'s name must be lowercase letters and digits, starting with a "
                   "letter, with single underscores between them")
    if not isinstance(prompt, str) or not prompt.strip():
        raise Skip("agent()'s prompt must be text, and not empty")
    if not isinstance(declared["tools"], list | tuple):
        raise Skip("agent()'s tools must be a list of functions; it may be empty")
    tools = _functions(declared["tools"], "agent()'s tools")
    if inside := [name for name, function in tools.items() if takes_spawn(function)]:
        raise Skip(f"{inside[0]} is a tool of the agent and takes {SPAWN}: a job can't start "
                   f"a job")
    if effort is not None and effort not in EFFORTS:
        raise Skip(f"agent()'s effort must be one of {', '.join(EFFORTS)}, not {effort!r}")
    if status is not None and not (isinstance(status, str) and status.strip()
                                   and len(status) <= STATUS_MAX and len(status.splitlines()) == 1):
        raise Skip(f"agent()'s status must be one line of at most {STATUS_MAX} characters")
    if not starters:
        raise Skip(f"agent() without an exposed function that takes {SPAWN}: nothing could "
                   f"start its job")
    return Agent(name, prompt, tools, effort, status)


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
    return _works_with(function)


def _works_with(function: object, *args: object) -> bool:
    """Can it be called with exactly these arguments?"""
    try:
        inspect.signature(function).bind(*args)
    except TypeError:                         # the parameters don't fit, or not callable at all
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

    A parameter with a default is optional. A first parameter called disk is Hallux's to fill
    (see DiskHandle): it needs no hint, and the AI never sees it. The same holds for one called
    spawn, which is the first parameter, or the second after disk. Raises Skip, with the
    reason, for a parameter that has no hint or one that can't become a schema."""
    properties, required = {}, []
    parameters = list(inspect.signature(function, eval_str=True).parameters.values())
    with_disk = bool(parameters) and parameters[0].name == DISK
    for position, p in enumerate(parameters):
        where = f"{function.__name__}({p.name})"
        if p.kind not in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
            raise Skip(f"{where}: only named parameters work, not *args, **kwargs or "
                       f"positional-only ones")
        if p.name == DISK:
            if position:
                raise Skip(f"{where}: {DISK} must be the first parameter")
            continue
        if p.name == SPAWN:
            if position != with_disk:
                raise Skip(f"{where}: {SPAWN} must be the first parameter, or the second "
                           f"after {DISK}")
            continue
        if p.annotation is p.empty:
            raise Skip(f"{where} has no type hint")
        # By ==, not by is: list[str] is a new object each time it is written.
        described = next((s for hint, s in JSON_TYPES.items() if p.annotation == hint), None)
        if described is None:
            raise Skip(f"{where}: the type hint must be str, int, float, bool or list[str]")
        properties[p.name] = copy.deepcopy(described)     # each schema its own
        if p.default is p.empty:
            required.append(p.name)
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


def takes_disk(function: Callable) -> bool:
    """Does the function want the disk handle? It does if its first parameter is called disk."""
    return next(iter(inspect.signature(function).parameters), None) == DISK


def takes_spawn(function: Callable) -> bool:
    """Does the function start a job? It does if it has a parameter called spawn."""
    return SPAWN in inspect.signature(function).parameters


class _OneCall:
    """A spawn for one call of an addon function. When the function has returned, or hallux
    has stopped waiting for it, the spawn is dead and raises Refused: a thread that runs on
    can't start a job behind everyone's back."""

    def __init__(self, spawn: Callable) -> None:
        self.spawn: Callable | None = spawn
        self.lock = threading.Lock()          # ending it waits for a start that is under way

    def __call__(self, *args: object, **more: object) -> object:
        with self.lock:
            if self.spawn is None:
                raise Refused("ESTALE")
            return self.spawn(*args, **more)

    def end(self) -> None:
        with self.lock:
            self.spawn = None


async def call(function: Callable, args: dict[str, Any], disk: Disk | None = None,
               spawn: Callable | None = None) -> dict[str, Any]:
    """Run an addon function for the AI and turn whatever happens into a tool result.

    `disk` is the machine's disk, for a function that takes the handle. `spawn` is what
    starts a job, for a function that asks for it; it works for this one call.
    The function gets a thread of its own, so a slow one freezes neither the keyboard nor the
    status bar. A thread can't be stopped: after the timeout the AI gets its error, and the
    function runs on with nobody waiting for it."""
    loop = asyncio.get_running_loop()
    outcome: asyncio.Future[tuple[dict, bool]] = loop.create_future()
    starter = None if spawn is None else _OneCall(spawn)

    def deliver(result: tuple[dict, bool]) -> None:
        if not outcome.done():                # after the timeout nobody is waiting
            outcome.set_result(result)

    def work() -> None:
        result = _run(function, args, disk, starter)
        if starter is not None:
            starter.end()                     # the function has returned
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
    finally:
        if starter is not None:
            starter.end()                     # nobody waits any more: it starts nothing now
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


def _run(function: Callable, args: dict[str, Any], disk: Disk | None = None,
         spawn: Callable | None = None) -> tuple[dict, bool]:
    """Call the function. Returns what the AI gets, and whether that is an error."""
    handle, filled = None, {}
    if takes_disk(function):
        if disk is None:
            log.warning("addon call %s got no disk", _label(function))
            return {"error": f"{function.__name__} needs the machine's disk, and this call "
                             f"has none"}, True
        handle = filled[DISK] = DiskHandle(disk)
    if takes_spawn(function):
        if spawn is None:
            log.warning("addon call %s got no spawn", _label(function))
            return {"error": f"{function.__name__} starts a job, and this call can't "
                             f"start one"}, True
        filled[SPAWN] = spawn
    try:
        # By name, so that a disk among the AI's arguments is an error and never the handle.
        result = function(**filled, **args)
    except Refused as refused:                # no fault of the addon's, and no warning: a job
        told = {"error": refused.code}        # couldn't start, and the AI hears why
        return told | ({"path": refused.path} if refused.path else {}), True
    except (Exception, SystemExit) as e:
        if handle is not None and (refused := handle.refusal(e)):
            return {"error": refused}, True   # the jail said no: no fault of the addon's
        log.warning("addon call %s raised", _label(function), exc_info=True)
        return {"error": _describe(e)}, True
    if problem := _problem_with(result):
        log.warning("addon call %s returned %s", _label(function), problem)
        return {"error": f"addon bug: {function.__name__} returned {problem}"}, True
    return result, False


def _problem_with(data: object) -> str | None:
    """Why a result or an event can't go to the AI: what it is instead of a small dictionary.
    Small, because the model reads every character of it."""
    if not isinstance(data, dict):
        return f"a {type(data).__name__}, not a dictionary"
    try:
        size = len(_json(data))
    except (TypeError, ValueError) as e:
        return f"something that isn't JSON ({e})"
    if size > RESULT_MAX:
        return f"{size} characters, more than {RESULT_MAX}"
    return None


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def _label(function: Callable) -> str:
    """music.play, for the log."""
    return f"{function.__module__.removeprefix(MODULE_PREFIX)}.{function.__name__}"
