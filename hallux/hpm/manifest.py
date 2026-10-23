"""hpm.toml, a package's manifest (docs/hpm/hpm.md, section 3; the plan's step 1).

Manifest.load(text) reads one and checks it. Every problem is found, then all are told at
once in one ManifestError, so that one round of fixes makes the file right.

Paths and patterns are the machine's: "/usr/local/bin/kittystory" is a path in the world,
"~/.kittystory/packs/*.pack" one under the home of the world's user, whoever that is. A
pattern keeps its "~" until place() is given the home (step 3). In a pattern "*" stands for
any part of one name and "**" for any number of folders; nothing else is a wildcard.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from functools import total_ordering

from hallux.addons import ADDON_NAME

KINDS = ("app", "seed", "data")         # the three kinds of files, widest first
NARROWEST_FIRST = ("data", "seed", "app")   # a file two kinds match takes the narrower
MANIFEST_MAX = 64 * 1024                # bytes of an hpm.toml
NAME = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,39}")
VERSION = re.compile(r"(0|[1-9][0-9]{0,5})(\.(0|[1-9][0-9]{0,5})){0,3}")
TEXT_MAX = 120                          # characters of a summary or an author
LINE_MAX = 300                          # characters of the memory line, and of each rule
PROBLEMS_MAX = 2000                     # characters of the error that lists them
# Names the machine only imagines, and its own hidden folder: no package reads or writes there.
REFUSED_TOPS = (".hallux", "proc", "sys", "dev")
WILDCARDS_NOT_OURS = set("?[]\\{}")

TOP_KEYS = {"name", "version", "summary", "author", "data_format", "requires", "memory_line",
            "files", "extras", "for", "bundle", "private", "rules"}
REQUIRES_KEYS = {"addons", "packages"}
EXTRA_KEYS = {"package", "default", "needs"}
NOT_IN_A_BUNDLE = ("files", "extras", "for", "rules")   # a bundle carries nothing of its own


class ManifestError(ValueError):
    """A manifest that can't be used, with every problem it has."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        many = "1 problem" if len(problems) == 1 else f"{len(problems)} problems"
        text = f"the manifest has {many}: " + "; ".join(problems)
        super().__init__(text if len(text) <= PROBLEMS_MAX else text[:PROBLEMS_MAX - 1] + "…")


# ---------------------------------------------------------------------- versions

@total_ordering
class Version:
    """A version: whole numbers with dots, 1.4, 1.4.1, 2.0; nothing like -beta. Compared
    number by number, so 1.4 < 1.10 < 2.0. A missing number counts as 0, so 1.4 and 1.4.0
    are the same version: a store can't hold both. Each number has one way of being
    written: "1.04" is refused, and so is anything with letters."""

    def __init__(self, text: str) -> None:
        if not isinstance(text, str) or not VERSION.fullmatch(text):
            raise ValueError(f"{str(text)[:30]!r} is no version: whole numbers with dots, like "
                             f"1.4 or 2.0.1, without leading zeros, at most four of them")
        self.text = text
        self.numbers = tuple(int(n) for n in text.split("."))

    @property
    def _key(self) -> tuple[int, ...]:
        numbers = list(self.numbers)
        while len(numbers) > 1 and numbers[-1] == 0:
            numbers.pop()
        return tuple(numbers)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Version) and self._key == other._key

    def __lt__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key < other._key

    def __hash__(self) -> int:
        return hash(self._key)

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return f"Version({self.text!r})"


# ---------------------------------------------------------------------- paths and patterns

def _head(text: str) -> tuple[str, str] | None:
    """A path or pattern split into "/" or "~/" and the rest, or None without either."""
    for head in ("~/", "/"):
        if text.startswith(head):
            return head, text[len(head):]
    return None


def _path_problem(text: object, wildcards: bool) -> str | None:
    """Why `text` can't be a machine path (or with `wildcards`, a pattern), or None."""
    if not isinstance(text, str) or not text:
        return "must be a path as text"
    shown = repr(text[:60])
    split = _head(text)
    if split is None:
        return f"{shown} must start with / or ~/"
    head, rest = split
    if not rest:
        return f"{shown} names no file"
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        return f"{shown} has a control character in it"
    names = rest.split("/")
    if any(name == "" for name in names):
        return f"{shown} has an empty name in it (// or a / at the end)"
    if any(name in (".", "..") for name in names):
        return f"{shown} may not have . or .. in it"
    if head == "/" and names[0] in REFUSED_TOPS:
        return f"{shown} is under /{names[0]}, where no package may go"
    if wildcards:
        if WILDCARDS_NOT_OURS & set(text):
            return f"{shown}: only * and ** are wildcards (no ? [ ] {{ }} \\)"
        for name in names:
            if "**" in name and name != "**":
                return f"{shown}: ** must be a whole name, as in /a/**/b"
    elif "*" in text:
        return f"{shown} is a path, and can't have * in it"
    return None


def check_path(path: str) -> str:
    """A machine path of a file, as hpm keeps them: "/…" or "~/…", or ValueError."""
    if problem := _path_problem(path, wildcards=False):
        raise ValueError(problem)
    return path


def check_pattern(pattern: str) -> str:
    """A pattern of a manifest's files, or ValueError."""
    if problem := _path_problem(pattern, wildcards=True):
        raise ValueError(problem)
    return pattern


_compiled: dict[str, re.Pattern] = {}


def _regex(pattern: str) -> re.Pattern:
    """The pattern as a regular expression over whole machine paths. A "**" at the end is one
    or more names (the folder's contents, not the folder); elsewhere it is none or more."""
    if pattern not in _compiled:
        head, rest = _head(check_pattern(pattern))
        names = rest.split("/")
        parts = []
        for i, name in enumerate(names):
            last = i == len(names) - 1
            if name == "**":
                parts.append("[^/]+(?:/[^/]+)*" if last else "(?:[^/]+/)*")
            else:
                parts.append("[^/]*".join(map(re.escape, name.split("*"))) + ("" if last else "/"))
        _compiled[pattern] = re.compile(re.escape(head) + "".join(parts))
    return _compiled[pattern]


def match(pattern: str, path: str) -> bool:
    """Does the machine path match the pattern? A "~/" pattern matches only "~/" paths."""
    return _regex(pattern).fullmatch(path) is not None


def expand(pattern: str, paths) -> list[str]:
    """The paths of `paths` the pattern matches, sorted."""
    regex = _regex(pattern)
    return sorted(path for path in paths if regex.fullmatch(path))


def place(path: str, home: str) -> str:
    """A machine path with its "~" put at the home of the world's user ("/home/danika-hous").
    A path under / stays as it is."""
    check_path(path)
    if path.startswith("~/"):
        return check_path(home.rstrip("/") + "/" + path[2:])
    return path


# ---------------------------------------------------------------------- the manifest

@dataclass(frozen=True)
class Extra:
    """One checkbox at install: a package of its own, ticked by default or not, and the
    other extras it needs."""
    key: str
    package: str
    default: bool = False
    needs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manifest:
    name: str
    version: Version
    summary: str = ""
    author: str = ""
    data_format: int = 1
    requires_addons: tuple[str, ...] = ()
    requires_packages: tuple[str, ...] = ()
    memory_line: str = ""
    files: dict[str, tuple[str, ...]] = field(default_factory=lambda: {k: () for k in KINDS})
    extras: dict[str, Extra] = field(default_factory=dict)
    for_app: str | None = None              # `for`: the app a data package is useless without
    bundle: tuple[str, ...] = ()
    private: bool = False
    rules: tuple[str, ...] = ()

    @property
    def is_bundle(self) -> bool:
        return bool(self.bundle)

    def patterns(self):
        """Every (kind, pattern) of its files."""
        for kind in KINDS:
            for pattern in self.files[kind]:
                yield kind, pattern

    def kind_of(self, path: str) -> str | None:
        """The kind of a machine path in this package: the narrowest kind that has a pattern
        matching it (data, then seed, then app), or None if no pattern does."""
        for kind in NARROWEST_FIRST:
            if any(match(pattern, path) for pattern in self.files[kind]):
                return kind
        return None

    @classmethod
    def load(cls, text: str | bytes) -> Manifest:
        """Read and check an hpm.toml. Raises ManifestError with every problem it has."""
        if isinstance(text, bytes):
            if len(text) > MANIFEST_MAX:
                raise ManifestError([f"it is bigger than {MANIFEST_MAX // 1024} KB"])
            try:
                text = text.decode("utf-8")
            except UnicodeDecodeError:
                raise ManifestError(["it isn't UTF-8 text"]) from None
        if len(text.encode("utf-8")) > MANIFEST_MAX:
            raise ManifestError([f"it is bigger than {MANIFEST_MAX // 1024} KB"])
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise ManifestError([f"it isn't TOML: {e}"]) from None
        return _checked(data)


def _checked(data: dict) -> Manifest:
    problems: list[str] = []
    for key in sorted(set(data) - TOP_KEYS):
        problems.append(f"unknown key {key[:30]!r}")

    name = data.get("name")
    if not (isinstance(name, str) and NAME.fullmatch(name)):
        problems.append("name must be 1 to 40 letters, digits or -, starting with a letter")
        name = None

    version = None
    if "version" not in data:
        problems.append("version is missing")
    else:
        try:
            version = Version(data["version"])
        except ValueError as e:
            problems.append(f"version: {e}")

    texts = {key: _text(data, key, TEXT_MAX, problems) for key in ("summary", "author")}
    memory_line = _text(data, "memory_line", LINE_MAX, problems)

    data_format = data.get("data_format", 1)
    if not (isinstance(data_format, int) and not isinstance(data_format, bool)
            and data_format >= 1):
        problems.append("data_format must be a whole number from 1")
        data_format = 1

    requires = data.get("requires", {})
    addons: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()
    if not isinstance(requires, dict):
        problems.append("requires must be a table, with addons and packages")
    else:
        for key in sorted(set(requires) - REQUIRES_KEYS):
            problems.append(f"requires: unknown key {key[:30]!r}")
        addons = _names(requires, "addons", "requires.addons", ADDON_NAME, problems)
        packages = _names(requires, "packages", "requires.packages", NAME, problems)

    files = _files(data.get("files", {}), problems)
    extras = _extras(data.get("extras", {}), problems)

    for_app = data.get("for")
    if for_app is not None and not (isinstance(for_app, str) and NAME.fullmatch(for_app)):
        problems.append("for must be the name of the app a data package is for")
        for_app = None

    bundle: tuple[str, ...] = ()
    if "bundle" in data:
        bundle = _names(data, "bundle", "bundle", NAME, problems)
        if not bundle and isinstance(data["bundle"], list):
            problems.append("bundle must name at least one package")
        for key in NOT_IN_A_BUNDLE:
            if key in data:
                problems.append(f"a bundle has no {key}: it only lists packages")

    private = data.get("private", False)
    if not isinstance(private, bool):
        problems.append("private must be true or false")
        private = False

    rules: tuple[str, ...] = ()
    if "rules" in data:
        listed = data["rules"]
        if not (isinstance(listed, list) and listed and all(_one_line(r, LINE_MAX)
                                                             for r in listed)):
            problems.append(f"rules must be a list of lines, each of at most {LINE_MAX} "
                            f"characters")
        else:
            rules = tuple(listed)

    if problems:
        raise ManifestError(problems)
    return Manifest(name=name, version=version, summary=texts["summary"],
                    author=texts["author"], data_format=data_format, requires_addons=addons,
                    requires_packages=packages, memory_line=memory_line, files=files,
                    extras=extras, for_app=for_app, bundle=bundle, private=private,
                    rules=rules)


def _one_line(value: object, limit: int) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= limit
            and "\n" not in value and "\r" not in value)


def _text(data: dict, key: str, limit: int, problems: list[str]) -> str:
    if key not in data:
        return ""
    if not _one_line(data[key], limit):
        problems.append(f"{key} must be one line of text, of at most {limit} characters")
        return ""
    return data[key]


def _names(table: dict, key: str, shown: str, rule: re.Pattern,
           problems: list[str]) -> tuple[str, ...]:
    listed = table.get(key, [])
    if not (isinstance(listed, list) and all(isinstance(n, str) and rule.fullmatch(n)
                                             for n in listed)):
        problems.append(f"{shown} must be a list of names")
        return ()
    if len(set(listed)) != len(listed):
        problems.append(f"{shown} names one package twice")
    return tuple(listed)


def _files(table: object, problems: list[str]) -> dict[str, tuple[str, ...]]:
    files = {kind: () for kind in KINDS}
    if not isinstance(table, dict):
        problems.append("files must be a table, with app, seed and data")
        return files
    for key in sorted(set(table) - set(KINDS)):
        problems.append(f"files: unknown kind {key[:30]!r} (app, seed or data)")
    seen: dict[str, str] = {}                     # pattern: the kind it was first written in
    for kind in KINDS:
        listed = table.get(kind, [])
        if not isinstance(listed, list):
            problems.append(f"files.{kind} must be a list of patterns")
            continue
        good = []
        for pattern in listed:
            if problem := _path_problem(pattern, wildcards=True):
                problems.append(f"files.{kind}: {problem}")
                continue
            if pattern in seen:
                problems.append(f"{pattern[:60]!r} is in files.{seen[pattern]} and in "
                                f"files.{kind}" if seen[pattern] != kind else
                                f"{pattern[:60]!r} is twice in files.{kind}")
                continue
            seen[pattern] = kind
            good.append(pattern)
        files[kind] = tuple(good)
    return files


def _extras(table: object, problems: list[str]) -> dict[str, Extra]:
    if not isinstance(table, dict):
        problems.append("extras must be a table of checkboxes")
        return {}
    extras: dict[str, Extra] = {}
    packages: dict[str, str] = {}
    for key, value in table.items():
        where = f"extras.{key[:30]}"
        if not NAME.fullmatch(key):
            problems.append(f"{where}: an extra's key must be a name (letters, digits, -)")
            continue
        if not isinstance(value, dict):
            problems.append(f"{where} must be a table: {{ package = \"…\", default = … }}")
            continue
        for unknown in sorted(set(value) - EXTRA_KEYS):
            problems.append(f"{where}: unknown key {unknown[:30]!r}")
        package = value.get("package")
        if not (isinstance(package, str) and NAME.fullmatch(package)):
            problems.append(f"{where}: package must be the name of a package")
            continue
        if package in packages:
            problems.append(f"{where}: {package} is the package of extras.{packages[package]} "
                            f"too")
        packages[package] = key
        default = value.get("default", False)
        if not isinstance(default, bool):
            problems.append(f"{where}: default must be true or false")
            default = False
        needs = value.get("needs", [])
        if not (isinstance(needs, list) and all(isinstance(n, str) for n in needs)):
            problems.append(f"{where}: needs must be a list of other extras' keys")
            needs = []
        extras[key] = Extra(key, package, default, tuple(needs))
    for extra in extras.values():
        for need in extra.needs:
            if need == extra.key:
                problems.append(f"extras.{extra.key} needs itself")
            elif need not in extras:
                problems.append(f"extras.{extra.key} needs {need[:30]!r}, which is no extra here")
    if circle := _circle(extras):
        problems.append("the extras' needs go round in a circle: " + " → ".join(circle))
    return extras


def _circle(extras: dict[str, Extra]) -> list[str] | None:
    """A circle of needs among the extras, as the keys along it, or None."""
    state: dict[str, str] = {}                    # "on": on the path now; "done": no circle

    def walk(key: str, path: list[str]) -> list[str] | None:
        state[key] = "on"
        for need in extras[key].needs:
            if need not in extras or need == key:
                continue                          # told already
            if state.get(need) == "on":
                return path[path.index(need):] + [need]
            if need not in state and (found := walk(need, path + [need])):
                return found
        state[key] = "done"
        return None

    for key in extras:
        if key not in state and (found := walk(key, [key])):
            return found
    return None
