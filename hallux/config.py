"""The machine's hardware: which Claude model runs it, at what effort, and with which addons.

Layers, later ones win: the defaults below < <root>/.hallux/config.toml < command-line flags.
No tool reaches config.toml, so the machine can't pick its own hardware. Hallux's own panel
can change it: `typed` makes a value of what was typed there, and `save` writes it back.
"""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path

from hallux.addons import ADDON_NAME, EFFORTS     # the loader checks an agent's effort too

MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5")     # for the panel to offer
CONFIG_FILE = Path(".hallux") / "config.toml"

WHEN = {                                      # when a change of each setting takes effect
    "tick_budget_usd": "now", "event_budget_usd": "now", "max_budget_usd": "now",
    "model": "now", "effort": "reboot", "fallback_model": "reboot",
    "status_bar": "start", "addons": "start", "keep_transcripts": "start", "os_sandbox": "start",
    # Addon agents: every job is a new session, so a change acts from the next job.
    "agent_model": "now", "agent_max_effort": "now", "agent_max_running": "now",
    "agent_job_budget_usd": "now", "agent_budget_usd": "now", "agent_timeout_seconds": "now",
}
# A typed number: digits with at most one point, and at most twelve digits in front of it.
# So nan, inf, 1e9 and a number too long to be finite are no numbers here.
NUMBER = re.compile(r"[0-9]{1,12}(\.[0-9]*)?|\.[0-9]+")
WHOLE = re.compile(r"[0-9]{1,6}")             # a typed count: digits only
# The value on a line of config.toml, to skip it: a string up to its closing quote, anything
# else up to the comment or the end of the line.
OLD_VALUE = re.compile(r'''"([^"\\]|\\.)*"|'[^']*'|[^#]*?(?=[ \t]*(#|\r?\n|\Z))''')


@dataclass(frozen=True)
class Hardware:
    model: str = "claude-opus-5-5"
    effort: str | None = "low"
    fallback_model: str | None = None
    max_budget_usd: float | None = None       # spending cap per boot
    status_bar: bool = True                   # hallux's own bottom row: activity, model, cost
    keep_transcripts: bool = False            # True: Claude Code also keeps its own transcript
    os_sandbox: bool = False                  # True: Claude Code runs inside bubblewrap
    tick_budget_usd: float = 0.25             # raw mode: live updates per program run, then pause
    event_budget_usd: float = 0.25            # addon events since the last typed line, then pause
    addons: tuple[str, ...] | None = None     # the addons it gets; None: every one that loaded
    # Addon agents (docs/addon-agents.md, section 6): what their jobs run on and may cost.
    agent_model: str | None = None            # None: the model the machine runs on
    agent_max_effort: str = "high"            # an agent gets the effort it asks for, at most this
    agent_max_running: int = 2                # jobs at the same time; 0 turns addon agents off
    agent_job_budget_usd: float = 1.00        # what one job may cost, then it is killed
    agent_budget_usd: float = 2.00            # all jobs since you last typed or pressed a key
    agent_timeout_seconds: float = 600        # how long one job may run

    @property
    def model_effort(self) -> str | None:
        """The effort to send: Haiku 4.5 has no effort levels, so it gets none."""
        return None if "haiku" in self.model else self.effort


@dataclass(frozen=True)
class View:
    """What the panel shows of a running machine: its settings, and how far its budgets are."""
    hardware: Hardware                        # the settings as they are now
    running: Hardware                         # what this boot's session started with
    spent_boot: float                         # dollars this boot has spent
    spent_since_refill: float                 # what counts for its cap; the same without a refill
    spent_ticks: float | None                 # by the program on screen, on ticks; None: no program
    spent_events: float                       # on events, since a line was typed
    paused: frozenset[str]                    # the budgets that are used up right now, by setting
    from_flags: frozenset[str]                # the settings a flag set for this run
    unsaved: frozenset[str]                   # the settings changed in this run and not saved yet
    path: Path                                # where config.toml is


def load(root: Path, **flags: object) -> Hardware:
    """Read the hardware for the machine in `root`. Raises ValueError with a readable message."""
    hardware = Hardware()
    path = Path(root) / CONFIG_FILE
    try:
        if path.exists():
            hardware = replace(hardware, **_settings(path.read_text(encoding="utf-8")))
        hardware = replace(hardware, **{k: v for k, v in flags.items() if v is not None})
        _validate(hardware)
        if reason := check_together(hardware):
            raise ValueError(reason)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from None
    return hardware


def check(name: str, value: object) -> str | None:
    """Why `value` can't be the setting `name`, or None. The words go behind the setting's name:
    in a row of the panel, and in what `load` says about a wrong file."""
    number = isinstance(value, int | float) and not isinstance(value, bool)
    if name == "model":
        ok = isinstance(value, str) and value != ""
        words = "must be a model name like claude-opus-5-5"
    elif name == "effort":
        ok = value is None or value in EFFORTS
        words = f"must be one of {', '.join(EFFORTS)}, not {value!r}"
    elif name == "fallback_model":
        ok, words = value is None or isinstance(value, str), "must be a model name"
    elif name in ("status_bar", "keep_transcripts", "os_sandbox"):
        ok, words = isinstance(value, bool), "must be true or false"
    elif name in ("tick_budget_usd", "event_budget_usd"):
        ok, words = number and value >= 0, "must be a number, 0 or more"
    elif name == "max_budget_usd":
        ok, words = value is None or (number and value > 0), "must be a positive number"
    elif name == "addons":
        ok = value is None or (isinstance(value, tuple) and all(
            isinstance(addon, str) and ADDON_NAME.fullmatch(addon) for addon in value))
        words = 'must be a list of addon names, like ["window"]'
    elif name == "agent_model":
        ok = value is None or (isinstance(value, str) and value != "")
        words = "must be a model name like claude-opus-5-5"
    elif name == "agent_max_effort":
        ok, words = value in EFFORTS, f"must be one of {', '.join(EFFORTS)}, not {value!r}"
    elif name == "agent_max_running":
        ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        words = "must be a whole number, 0 or more"
    elif name in ("agent_job_budget_usd", "agent_timeout_seconds"):
        ok, words = number and value > 0, "must be a positive number"
    elif name == "agent_budget_usd":
        ok, words = number and value >= 0, "must be a number, 0 or more"
    else:
        raise KeyError(name)
    return None if ok else words


def check_together(hw: Hardware, changed: str | None = None) -> str | None:
    """Why these settings can't hold together, or None. One rule: a budget per job above the
    budget for all jobs, with which no job could ever start. A budget for all jobs of 0 turns
    the agents off, and goes with any budget per job.

    With `changed`, the words go behind that setting, in its row of the panel. Without, they
    name both, for a wrong file. `load` asks this after its check of each setting, the machine
    for each change, and `save` once, for the file as it would be: never for one change of
    several, where the file's other value can still be the old one."""
    job, all_jobs = hw.agent_job_budget_usd, hw.agent_budget_usd
    if all_jobs == 0 or job <= all_jobs:
        return None
    if changed == "agent_job_budget_usd":
        return "is over the budget for all jobs"
    if changed == "agent_budget_usd":
        return "is under the budget per job"
    return f"agent_job_budget_usd ({job}) must not be more than agent_budget_usd ({all_jobs})"


def typed(name: str, text: str) -> object:
    """The value of the setting `name` that `text` stands for, as typed in the panel.
    Raises ValueError with the reason when it is none."""
    if WHEN[name] == "start":
        raise ValueError("is set when Hallux starts: edit config.toml")
    text = text.strip()
    value: object = text
    if name in ("max_budget_usd", "tick_budget_usd", "event_budget_usd", "agent_job_budget_usd",
                "agent_budget_usd"):
        dollars = text.removeprefix("$").strip()
        if NUMBER.fullmatch(dollars):
            value = float(dollars)
        elif not dollars and name == "max_budget_usd":
            value = None                      # nothing typed: no cap
    elif name in ("fallback_model", "agent_model"):
        value = text or None
    elif name == "agent_max_running":
        if WHOLE.fullmatch(text):
            value = int(text)
    elif name == "agent_timeout_seconds":
        seconds = text.removesuffix("s").strip()      # 90 or 90s
        if NUMBER.fullmatch(seconds):
            value = float(seconds)
    if reason := check(name, value):          # what is no number is still the text, and refused
        raise ValueError(reason)
    return value


def save(root: Path, changes: dict[str, object]) -> None:
    """Write `changes` into the config.toml of the machine in `root`: a setting's name to its new
    value, or to None, which takes its line out. Every other line stays as it is.
    Raises ValueError with a message for the panel; nothing was written then."""
    path = Path(root) / CONFIG_FILE
    try:
        old = path.read_bytes().decode("utf-8") if path.exists() else ""    # its own line endings
        settings = _checked(old)
    except OSError as e:
        raise ValueError(f"config.toml: {e.strerror or e}. Nothing saved.") from None
    except ValueError as e:
        raise ValueError(f"config.toml: {e}. Nothing saved.") from None
    text = old
    for name, value in changes.items():
        text = _with(text, name, value)
        settings = {k: v for k, v in {**settings, name: value}.items() if v is not None}
        try:
            safe = _checked(text) == settings     # the file says the old settings and this change
        except ValueError:
            safe = False
        if not safe:
            raise ValueError(f"config.toml: can't change {name} safely. Edit the file. "
                             f"Nothing saved.")
    if text == old:
        return
    if reason := check_together(replace(Hardware(), **settings)):     # the file as it would be
        raise ValueError(f"config.toml: {reason}. Nothing saved.")
    try:
        path.parent.mkdir(exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_bytes(text.encode("utf-8"))
        os.replace(temp, path)                # atomic: a crash never leaves half a config
    except OSError as e:
        raise ValueError(f"config.toml: {e.strerror or e}. Nothing saved.") from None


def agent_model(hw: Hardware, running: str) -> str:
    """The model an addon agent's job runs on: the one set for the agents, and without one the
    model the main session really runs on. `running` is that model, which is the `model`
    setting unless the setting holds a name that is no model: a running session refuses such
    a name and goes on, and a job, which is a new session, would fail on it."""
    return hw.agent_model or running


def agent_effort(hw: Hardware, asked: str | None, model: str) -> str | None:
    """The effort a job gets on `model`: what its addon asks for, and without an ask the
    `effort` setting as it is now, in both cases at most agent_max_effort. A job is a new
    session, so it needn't wait for a reboot as the machine does. Haiku gets none."""
    wanted = asked or hw.effort
    if wanted is None or "haiku" in model:
        return None
    return min(wanted, hw.agent_max_effort, key=EFFORTS.index)


def _settings(text: str) -> dict[str, object]:
    """The settings a config.toml's text holds. Raises ValueError: broken TOML is one."""
    settings = tomllib.loads(text)
    known = {f.name for f in fields(Hardware)}
    if unknown := sorted(set(settings) - known):
        raise ValueError(f"unknown setting {', '.join(unknown)} "
                         f"(known: {', '.join(sorted(known))})")
    if isinstance(settings.get("addons"), list):
        settings["addons"] = tuple(settings["addons"])
    return settings


def _validate(hw: Hardware) -> None:
    for f in fields(hw):
        if reason := check(f.name, getattr(hw, f.name)):
            raise ValueError(f"{f.name} {reason}")


def _checked(text: str) -> dict[str, object]:
    """The settings a config.toml's text holds, checked as `load` checks the file."""
    settings = _settings(text)
    _validate(replace(Hardware(), **settings))
    return settings


def _with(text: str, name: str, value: object) -> str:
    """A config.toml's `text` with the setting `name` at `value`, or without it for None. The
    line that sets it is changed, and what follows the value there stays; no line: a new one."""
    lines = re.findall(r"[^\n]*\n|[^\n]+", text)        # each with its own line ending
    for at, line in enumerate(lines):
        if head := re.match(rf"[ \t]*{re.escape(name)}[ \t]*=[ \t]*", line):
            if value is None:
                del lines[at]
            else:
                rest = line[OLD_VALUE.match(line, head.end()).end():]
                lines[at] = head[0] + _toml(value) + rest
            return "".join(lines)
    if value is None:
        return text
    eol = "\r\n" if "\r\n" in text else "\n"
    gap = eol if text and not text.endswith("\n") else ""    # the file ends without a line break
    return f"{text}{gap}{name} = {_toml(value)}{eol}"


def _toml(value: object) -> str:
    """A name or a number, as config.toml holds it."""
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return repr(value)
