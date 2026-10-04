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

from hallux.addons import ADDON_NAME

EFFORTS = ("low", "medium", "high", "xhigh", "max")
CONFIG_FILE = Path(".hallux") / "config.toml"

WHEN = {                                      # when a change of each setting takes effect
    "tick_budget_usd": "now", "event_budget_usd": "now",
    "max_budget_usd": "reboot", "model": "reboot", "effort": "reboot", "fallback_model": "reboot",
    "status_bar": "start", "addons": "start", "keep_transcripts": "start", "os_sandbox": "start",
}
# A typed number: digits with at most one point, and at most twelve digits in front of it.
# So nan, inf, 1e9 and a number too long to be finite are no numbers here.
NUMBER = re.compile(r"[0-9]{1,12}(\.[0-9]*)?|\.[0-9]+")
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

    @property
    def model_effort(self) -> str | None:
        """The effort to send: Haiku 4.5 has no effort levels, so it gets none."""
        return None if "haiku" in self.model else self.effort


def load(root: Path, **flags: object) -> Hardware:
    """Read the hardware for the machine in `root`. Raises ValueError with a readable message."""
    hardware = Hardware()
    path = Path(root) / CONFIG_FILE
    try:
        if path.exists():
            hardware = replace(hardware, **_settings(path.read_text(encoding="utf-8")))
        hardware = replace(hardware, **{k: v for k, v in flags.items() if v is not None})
        _validate(hardware)
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
    else:
        raise KeyError(name)
    return None if ok else words


def typed(name: str, text: str) -> object:
    """The value of the setting `name` that `text` stands for, as typed in the panel.
    Raises ValueError with the reason when it is none."""
    if WHEN[name] == "start":
        raise ValueError("is set when Hallux starts: edit config.toml")
    text = text.strip()
    value: object = text
    if name in ("max_budget_usd", "tick_budget_usd", "event_budget_usd"):
        dollars = text.removeprefix("$").strip()
        if NUMBER.fullmatch(dollars):
            value = float(dollars)
        elif not dollars and name == "max_budget_usd":
            value = None                      # nothing typed: no cap
    elif name == "fallback_model":
        value = text or None
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
    try:
        path.parent.mkdir(exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_bytes(text.encode("utf-8"))
        os.replace(temp, path)                # atomic: a crash never leaves half a config
    except OSError as e:
        raise ValueError(f"config.toml: {e.strerror or e}. Nothing saved.") from None


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
