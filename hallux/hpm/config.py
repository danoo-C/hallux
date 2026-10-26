"""hpm's own settings: ~/.config/hallux/hpm.toml (docs/plans/hpm/config/).

The file is found by the user's home, never by the folder hpm runs in, so a world, the repo
or anywhere else reads the same one. XDG_CONFIG_HOME is not read: a shell that sets it and a
shortcut that doesn't would read two files. HPM_CONFIG names another file (the tests).

    store  = "~/hpm-live"   where the store is
    editor = "nano"         for changelog entries and manifests
    color  = "auto"         auto | always | never

Who wins: a flag, then the environment, then this file, then the default.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from hallux.hpm.world import HpmError

KEYS = ("store", "editor", "color")
COLORS = ("auto", "always", "never")
PLACE = Path(".config") / "hallux" / "hpm.toml"


def home_of(env) -> Path:
    return Path(env["HOME"]) if env.get("HOME") else Path.home()


def config_path(env=None) -> Path:
    """HPM_CONFIG if set, else ~/.config/hallux/hpm.toml."""
    env = os.environ if env is None else env
    if env.get("HPM_CONFIG"):
        return Path(env["HPM_CONFIG"]).expanduser()
    return home_of(env) / PLACE


def expand(text: str, env=None) -> Path:
    """A path of the file: `~` is the user's home. Relative paths aren't paths here."""
    env = os.environ if env is None else env
    if text == "~" or text.startswith("~/"):
        return home_of(env) / text[2:]
    return Path(text)


@dataclass(frozen=True)
class Config:
    path: Path
    store: Path | None = None
    editor: str | None = None
    color: str | None = None
    raw: dict | None = None                  # what the file says, as written

    def said(self, key: str):
        return (self.raw or {}).get(key)


_read: dict[Path, tuple[tuple, Config]] = {}
_root_told = False


def load(env=None) -> Config:
    """The file, checked. No file: an empty Config. A mistake is an HpmError that names
    the file and the key. Read again only when the file changed."""
    env = os.environ if env is None else env
    path = config_path(env)
    _tell_root(path)
    try:
        info = path.stat()
    except FileNotFoundError:
        return Config(path)
    except OSError as e:
        raise HpmError(f"{path} can't be read: {e.strerror or e}") from None
    stamp = (info.st_mtime_ns, info.st_size, env.get("HOME"))
    if path in _read and _read[path][0] == stamp:
        return _read[path][1]
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise HpmError(f"{path} can't be read: {e}") from None
    except tomllib.TOMLDecodeError as e:
        raise HpmError(f"{path} isn't TOML hpm can read: {e}") from None
    config = Config(path, raw=dict(data), **check(path, data, env))
    _read[path] = (stamp, config)
    return config


def check(path: Path, data: dict, env=None) -> dict:
    """The file's values, checked and expanded; every problem at once, as an HpmError."""
    problems = [f"unknown key {key!r} (hpm knows {', '.join(KEYS)})"
                for key in data if key not in KEYS]
    out = {}
    store = data.get("store")
    if store is not None:
        if not isinstance(store, str) or not store.strip():
            problems.append("store must be the path of a folder, like \"~/hpm-live\"")
        elif not (store.startswith("/") or store == "~" or store.startswith("~/")):
            problems.append(f"store must start with / or ~/ (not {store!r}): a relative path "
                            f"would depend on where hpm runs")
        else:
            out["store"] = expand(store, env)
    editor = data.get("editor")
    if editor is not None:
        if not isinstance(editor, str) or not editor.strip():
            problems.append("editor must be a command, like \"nano\"")
        else:
            out["editor"] = editor
    color = data.get("color")
    if color is not None:
        if color not in COLORS:
            problems.append(f"color must be one of {', '.join(COLORS)}")
        else:
            out["color"] = color
    if problems:
        raise HpmError(f"{path}: " + "; ".join(problems))
    return out


def _tell_root(path: Path) -> None:
    """Run as root, hpm reads root's file, not the user's: said once (decision 8)."""
    global _root_told
    if _root_told or not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    _root_told = True
    print(f"note: hpm runs as root, so it reads {path}, not yours; hpm never needs sudo",
          file=sys.stderr)


# ---------------------------------------------------------------------- the settings

def store_from_file(env=None) -> Path | None:
    """The store the file names; an error if that folder isn't there (hpm doesn't make a
    store where a typo points)."""
    config = load(env)
    if config.store is None:
        return None
    if not config.store.is_dir():
        raise HpmError(f"{config.path}: store = {config.said('store')!r}, but {config.store} "
                       f"is no folder. Fix it with: hpm config set store PATH")
    return config.store


def editor_command(env=None) -> tuple[str | None, str]:
    """The editor, and where it came from: HPM_EDITOR, the file, $VISUAL, $EDITOR, then nano
    if it is installed, else vi (decision 4). (None, "") when there is none at all."""
    env = os.environ if env is None else env
    if env.get("HPM_EDITOR"):
        return env["HPM_EDITOR"], "HPM_EDITOR"
    config = load(env)
    if config.editor:
        return config.editor, "the file"
    for name in ("VISUAL", "EDITOR"):
        if env.get(name):
            return env[name], f"${name}"
    for name in ("nano", "vi"):
        if shutil.which(name, path=env.get("PATH")):
            return name, "the default"
    return None, ""


def file_color(env=None) -> str | None:
    """The file's color, or None if it has none or can't be read (colors never stop hpm:
    the error is told where the file is read for the store)."""
    try:
        return load(env).color
    except HpmError:
        return None


# ---------------------------------------------------------------------- what wins

def explain(env=None) -> list[tuple[str, str, str, bool]]:
    """Each setting as `hpm config` shows it: (key, value, where it came from, whether the
    environment set it). A value the environment hides says what the file has."""
    env = os.environ if env is None else env
    config = load(env)
    home = str(home_of(env))

    def tilde(path) -> str:
        text = str(path)
        return "~" + text[len(home):] if text == home or text.startswith(home + "/") else text

    def hidden(key: str) -> str:
        return f" (the file says {config.said(key)})" if config.said(key) is not None else ""

    out = []
    if env.get("HPM_HOME"):
        out.append(("store", tilde(Path(env["HPM_HOME"]).expanduser()),
                    "from HPM_HOME" + hidden("store"), True))
    elif config.store is not None:
        missing = "" if config.store.is_dir() else ": no such folder (hpm config set store PATH)"
        out.append(("store", tilde(config.store), "from the file" + missing, False))
    elif env.get("XDG_DATA_HOME"):
        out.append(("store", tilde(Path(env["XDG_DATA_HOME"]).expanduser() / "hallux" / "hpm"),
                    "from XDG_DATA_HOME", True))
    else:
        out.append(("store", tilde(home_of(env) / ".local/share/hallux/hpm"), "the default",
                    False))
    editor, source = editor_command(env)
    from_env = source in ("HPM_EDITOR", "$VISUAL", "$EDITOR")
    out.append(("editor", editor or "(none: no nano or vi either)",
                ("from " + source + hidden("editor")) if from_env
                else ("from the file" if source == "the file" else "the default"), from_env))
    if env.get("HPM_COLOR", "").strip().lower() in ("always", "never"):
        out.append(("color", env["HPM_COLOR"].strip().lower(), "from HPM_COLOR" + hidden("color"),
                    True))
    elif env.get("NO_COLOR") or env.get("TERM") == "dumb":
        why = "NO_COLOR" if env.get("NO_COLOR") else "TERM=dumb"
        out.append(("color", "never", f"from {why}" + hidden("color"), True))
    elif config.color is not None:
        out.append(("color", config.color, "from the file", False))
    else:
        out.append(("color", "auto", "the default", False))
    return out


# ---------------------------------------------------------------------- writing it

LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*=")


def set_value(key: str, value: str, env=None) -> tuple[Path, str]:
    """Write one key into the file, made if it isn't there: the key's line changed in place,
    or added at the end; comments and other lines stay. The value is checked as `load`
    checks it, and nothing is written if it is wrong. Returns the file and the value as
    written (a store inside the home is written with ~)."""
    from hallux.disk import write_whole
    env = os.environ if env is None else env
    if key not in KEYS:
        raise HpmError(f"hpm has no setting {key!r}; it has {', '.join(KEYS)}")
    path = config_path(env)
    if key == "store":                        # the shell made ~/hpm-live absolute: back to ~
        home = str(home_of(env))
        if value.startswith(home + "/"):
            value = "~" + value[len(home):]
    checked = check(path, {key: value}, env)
    if key == "store" and not checked["store"].is_dir():
        raise HpmError(f"{checked['store']} is no folder; nothing written")
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as e:
        raise HpmError(f"{path} can't be read: {e.strerror or e}") from None
    line = f"{key} = {_quoted(value)}\n"
    lines = text.splitlines(keepends=True)
    found = [i for i, each in enumerate(lines) if (m := LINE.match(each)) and m.group(1) == key]
    if len(found) > 1:
        raise HpmError(f"{path} says {key} twice; fix it by hand")
    if found:
        lines[found[0]] = line
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(line)
    new = "".join(lines)
    try:
        data = tomllib.loads(new)
    except tomllib.TOMLDecodeError as e:
        raise HpmError(f"{path} wouldn't read after the change ({e}); nothing written") from None
    check(path, data, env)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_whole(path, new)
    except OSError as e:
        raise HpmError(f"{path} can't be written: {e.strerror or e}") from None
    return path, value


def _quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
