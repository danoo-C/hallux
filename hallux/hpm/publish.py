"""hpm publish and hpm show, without the AI (docs/hpm/hpm.md, section 5; sharing.md,
section 3; the plan's step 2).

Publish takes the manifest a world keeps for a package (/usr/local/share/hpm/<name>/hpm.toml),
collects the files its patterns match, checks everything it can, and only then packs a
release into the store. The world is written last, and only under /usr/local/share/hpm/<name>/:
the manifest's new version and the changelog's new entry.

The questions go through a Questions object, so the command asks on the terminal, the tests
answer from a script, and without a terminal a question that has no flag is an error that
names its flag.
"""
from __future__ import annotations

import dataclasses
import datetime
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from hallux.disk import Disk
from hallux.hpm.archive import (
    CHANGELOG, ArchiveError, listing, pack, read_member, sha256, to_machine, to_member,
)
from hallux.hpm.manifest import Manifest, ManifestError, Version
from hallux.hpm.store import Release, Store
from hallux.hpm.world import (
    MANIFESTS, HpmError, collect, manifest_path, read_world_manifest, world_user,
)

# A data package holding one of these may hold your own life: memories, a chat.
PRIVATE_NAMES = re.compile(r"memory\.md|shared\.md|state\.json|history.*|chat.*")
SEED_GROWTH = 2                           # a seed this many times bigger than before is told
SHOWN_FILES = 30                          # files of one kind that `hpm show` lists by name
SHOWN_ENTRIES = 3                         # changelog entries that `hpm show` shows


# ---------------------------------------------------------------------- the questions

class Questions:
    """Questions on the terminal. Without one (a pipe), every question is an error that
    names the flag that answers it."""

    def __init__(self, interactive: bool | None = None) -> None:
        self.interactive = (sys.stdin.isatty() and sys.stdout.isatty()
                            if interactive is None else interactive)

    def _needs_terminal(self, question: str, flag: str) -> None:
        if not self.interactive:
            raise HpmError(f"{question}: there is no terminal to ask in; pass {flag}")

    def ask(self, question: str, default: str, flag: str) -> str:
        self._needs_terminal(question, flag)
        answer = input(f"{question} [{default}]: ").strip()
        return answer or default

    def confirm(self, question: str, default: bool, flag: str) -> bool:
        self._needs_terminal(question, flag)
        while True:
            answer = input(f"{question} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
            if not answer:
                return default
            if answer in ("y", "yes", "n", "no"):
                return answer.startswith("y")

    def edit(self, template: str, flag: str) -> str:
        """The text you write, starting from `template`, in $VISUAL or $EDITOR."""
        self._needs_terminal("the changelog entry", flag)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if not editor:
            raise HpmError(f"there is no $EDITOR to write the changelog entry in; set one, "
                           f"or pass {flag}")
        handle, name = tempfile.mkstemp(prefix="hpm-changelog-", suffix=".md")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                f.write(template)
            if subprocess.run([*shlex.split(editor), name]).returncode != 0:
                raise HpmError(f"the editor ({editor}) ended with an error; nothing published")
            return Path(name).read_text(encoding="utf-8")
        finally:
            Path(name).unlink(missing_ok=True)

    def say(self, text: str) -> None:
        print(text)


# ---------------------------------------------------------------------- publishing

def publish(world: Path, name: str, store: Store, questions: Questions, *,
            every: bool = False, version: str | None = None, changelog: str | None = None,
            user: str | None = None, private: bool | None = None, suggested: bool = False,
            today: datetime.date | None = None) -> list[Release]:
    """Publish a package from a world into the store; with `every` (--all), its extras too,
    each that changed since its last release. With `suggested` (--yes), each takes the
    version hpm suggests, without asking. Returns what was published."""
    disk = Disk(world)
    today = today or datetime.date.today()
    first = _world_manifest(disk, name)[0]
    names = [name]
    if every:
        if version is not None:
            raise HpmError("--version can't go with --all: each package gets its own")
        names += [extra.package for extra in first.extras.values()]
        missing = [n for n in names[1:] if read_world_manifest(disk, n) is None]
        if missing:
            raise HpmError(f"no manifest in this world for {', '.join(missing)} "
                           f"(each extra needs one at {MANIFESTS}/<name>/hpm.toml)")
    home = _home(disk, names, user)
    published = []
    for each in names:
        release = _publish_one(disk, each, store, questions, home, version=version,
                               changelog=changelog, private=private, suggested=suggested,
                               today=today, unchanged_is_fine=every)
        if release is not None:
            published.append(release)
    if every and not published:
        questions.say("nothing changed since the last releases; nothing published")
    return published


def _world_manifest(disk: Disk, name: str) -> tuple[Manifest, str]:
    try:
        found = read_world_manifest(disk, name)
    except ManifestError as e:
        raise HpmError(f"{manifest_path(name)}: {e}") from None
    if found is None:
        raise HpmError(f"this world has no manifest for {name}: write one at "
                       f"{manifest_path(name)} (hpm init, which drafts it, comes later)")
    if found[0].name != name:
        raise HpmError(f"{manifest_path(name)} is the manifest of {found[0].name}, not {name}")
    return found


def _home(disk: Disk, names: list[str], user: str | None) -> str | None:
    """The home `~` stands for, if any of the packages has a `~` pattern."""
    tilde = any(pattern.startswith("~/")
                for each in names for _, pattern in _world_manifest(disk, each)[0].patterns())
    if not tilde:
        return None
    home = world_user(disk, user)
    if home is None:
        raise HpmError("this world has no user home, so the ~ patterns match nothing")
    return home


def _publish_one(disk: Disk, name: str, store: Store, q: Questions, home: str | None, *,
                 version: str | None, changelog: str | None, private: bool | None,
                 suggested: bool, today: datetime.date,
                 unchanged_is_fine: bool) -> Release | None:
    manifest, text = _world_manifest(disk, name)
    collected = collect(disk, manifest, home)
    migrations = _migrations(disk, name)

    problems = [f"{pattern} matches nothing in this world: the app moved something, and the "
                f"manifest has to follow" for pattern in collected.empty]
    problems += [f"{path} is a link; a package holds plain files" for path in collected.links]
    problems += _shared_with_family(disk, manifest, set(collected.files), home, q)
    if problems:
        raise HpmError(f"{name} can't be published: " + "; ".join(problems))

    ours = {to_member(path): sha256(real) for path, (_, real) in collected.files.items()}
    ours |= {member: sha256(real) for member, real in migrations.items()}
    latest = store.latest(name)
    before = latest.manifest() if latest else None
    theirs = {} if latest is None else listing(latest.path)
    if latest is not None and not _changed(manifest, before, ours, theirs):
        if unchanged_is_fine:
            q.say(f"{name} {latest.version}: unchanged, not published")
            return None
        raise HpmError(f"{name}: nothing changed since {latest.version}; nothing to publish")
    if before is not None:
        _check_data(name, manifest, before, latest)

    new_version = _version(name, manifest, before, latest, version, suggested, q)
    new_text = _with_value(text, "version", f'"{new_version}"')
    new_text = _privacy(name, manifest, collected, new_text, private, q)
    _seeds(collected, theirs, q)
    entry = _entry(new_version, changelog, today, q)
    world_changelog = f"{MANIFESTS}/{name}/{CHANGELOG}"
    old_changelog = _read_text(disk, world_changelog)
    new_changelog = _put_on_top(old_changelog, entry)

    try:
        checked = Manifest.load(new_text)
    except ManifestError as e:
        raise HpmError(f"the manifest with its new version doesn't read: {e}") from None
    if checked.version != new_version:
        raise HpmError(f"{manifest_path(name)}: hpm couldn't set the version in it")

    with tempfile.TemporaryDirectory(prefix="hpm-publish-") as temp:
        folder = Path(temp) / "package"
        for path, (_, real) in collected.files.items():
            target = folder / to_member(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(real, target)
        for member, real in migrations.items():
            (folder / member).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(real, folder / member)
        folder.mkdir(exist_ok=True)
        (folder / "hpm.toml").write_text(new_text, encoding="utf-8")
        (folder / CHANGELOG).write_text(new_changelog, encoding="utf-8")
        try:
            packed = pack(folder, Path(temp) / "release.hpm")
        except ArchiveError as e:
            raise HpmError(str(e)) from None
        release = store.add(packed)

    try:                                          # the world last: the release is safe already
        disk.write_file(manifest_path(name), new_text, parents=True)
        disk.write_file(world_changelog, new_changelog, parents=True)
    except OSError as e:
        raise HpmError(f"{name} {new_version} is in the store, but the world's "
                       f"{MANIFESTS}/{name}/ couldn't be written ({e.strerror or e}); set "
                       f"version = \"{new_version}\" in its hpm.toml by hand") from None
    size = sum(real.stat().st_size for _, real in collected.files.values())
    q.say(f"published {name} {new_version}: {len(collected.files)} files, {_size(size)}")
    return release


def _migrations(disk: Disk, name: str) -> dict[str, Path]:
    """The package's migration notes in the world, by their names in the package."""
    try:
        folder = disk.real(f"{MANIFESTS}/{name}/migrations")
    except OSError:
        return {}
    if not folder.is_dir():
        return {}
    found, wrong = {}, []
    for real in sorted(folder.iterdir()):
        if real.is_file() and not real.is_symlink() and real.name.endswith(".md"):
            found[f"migrations/{real.name}"] = real
        else:
            wrong.append(real.name)
    if wrong:
        raise HpmError(f"{MANIFESTS}/{name}/migrations/ holds only .md notes, not "
                       f"{', '.join(wrong)}")
    return found


def _shared_with_family(disk: Disk, manifest: Manifest, ours: set[str], home: str | None,
                        q: Questions) -> list[str]:
    """The files this package and another package of the same app both carry: the app and
    its extras, whose manifests are in the world beside this one."""
    app = manifest.for_app or manifest.name
    if app == manifest.name:
        app_manifest = manifest
    else:
        try:
            got = read_world_manifest(disk, app)
        except ManifestError:
            got = None
        app_manifest = got[0] if got else None
    family = {app} | ({e.package for e in app_manifest.extras.values()} if app_manifest else set())
    family.discard(manifest.name)
    problems = []
    for other in sorted(family):
        try:
            got = read_world_manifest(disk, other)
        except ManifestError:
            q.say(f"note: {manifest_path(other)} has problems; not checked for shared files")
            continue
        if got is None:
            continue
        both = sorted(ours & set(collect(disk, got[0], home).files))
        problems += [f"{path} is in {manifest.name} and in {other}; one package must carry it"
                     for path in both]
    return problems


def _changed(manifest: Manifest, before: Manifest, ours: dict[str, str],
             theirs: dict[str, tuple[int, str]]) -> bool:
    if dataclasses.replace(manifest, version=before.version) != before:
        return True
    old = {name: sha for name, (_, sha) in theirs.items() if name not in ("hpm.toml", CHANGELOG)}
    return old != ours


def _check_data(name: str, manifest: Manifest, before: Manifest, latest: Release) -> None:
    if manifest.data_format < before.data_format:
        raise HpmError(f"{name}: data_format is {manifest.data_format}, lower than "
                       f"{before.data_format} in {latest.version}; it only goes up")
    if set(manifest.files["data"]) != set(before.files["data"]) \
            and manifest.data_format == before.data_format:
        raise HpmError(
            f"{name}: the data moved since {latest.version} (files.data was "
            f"{list(before.files['data'])}, now {list(manifest.files['data'])}), but "
            f"data_format is still {manifest.data_format}: an update would leave the data "
            f"behind. Raise data_format, and write a migration for it (docs/hpm/migrations.md)")


def bump(version: Version, major: bool) -> Version:
    """The next version: the first number up for a new data format (1.4 → 2.0), else the
    last (1.4 → 1.5, 1.4.1 → 1.4.2; 2 → 2.1)."""
    numbers = list(version.numbers)
    if major:
        return Version(f"{numbers[0] + 1}.0")
    if len(numbers) == 1:
        return Version(f"{numbers[0]}.1")
    numbers[-1] += 1
    return Version(".".join(map(str, numbers)))


def _version(name: str, manifest: Manifest, before: Manifest | None, latest: Release | None,
             given: str | None, take_suggested: bool, q: Questions) -> Version:
    if given is None:
        if latest is None:
            suggested = manifest.version
        else:
            suggested = bump(latest.version, manifest.data_format > before.data_format)
        if take_suggested:
            given = str(suggested)
        else:
            given = q.ask(f"{name}'s version", str(suggested), "--version, or --yes for "
                          f"the suggested {suggested}")
    try:
        version = Version(given)
    except ValueError as e:
        raise HpmError(str(e)) from None
    if latest is not None and not version > latest.version:
        raise HpmError(f"{name} {version} must be higher than the store's latest, "
                       f"{latest.version}")
    return version


def _with_value(text: str, key: str, value: str) -> str:
    """The manifest's text with a top-level `key = value`: its line changed, or a new line
    before the first table. Comments and the rest stay as they were."""
    lines = text.splitlines(keepends=True)
    table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")),
                 len(lines))
    pattern = re.compile(rf"^(\s*{key}\s*=\s*)(\"[^\"]*\"|'[^']*'|true|false)(.*)$", re.S)
    found = [i for i in range(table) if pattern.match(lines[i])]
    if len(found) > 1:
        raise HpmError(f"the manifest says {key} twice")
    if found:
        i = found[0]
        lines[i] = pattern.sub(lambda m: m.group(1) + value + m.group(3), lines[i])
    else:
        if table and not lines[table - 1].endswith("\n"):
            lines[table - 1] += "\n"
        lines.insert(table, f"{key} = {value}\n")
    return "".join(lines)


def _privacy(name: str, manifest: Manifest, collected, text: str, private: bool | None,
             q: Questions) -> str:
    """A data package that holds memories or a chat and isn't private: told, and asked."""
    if manifest.private or not (manifest.files["data"] or manifest.for_app):
        return text
    hits = [path for path in collected.files
            if PRIVATE_NAMES.fullmatch(posixpath.basename(path))]
    if not hits:
        return text
    shown = ", ".join(hits[:5]) + (f" and {len(hits) - 5} more" if len(hits) > 5 else "")
    q.say(f"warning: {name} holds what may be your own memories or chats: {shown}")
    if private is None:
        private = q.confirm(f"mark {name} private, so that hpm push never sends it?", True,
                            "--private yes or --private no")
    if not private:
        return text
    q.say(f"{name} is marked private (private = true in its manifest)")
    return _with_value(text, "private", "true")


def _seeds(collected, theirs: dict[str, tuple[int, str]], q: Questions) -> None:
    for path, (kind, real) in collected.files.items():
        if kind != "seed" or to_member(path) not in theirs:
            continue
        old, new = theirs[to_member(path)][0], real.stat().st_size
        if old and new > SEED_GROWTH * old:
            q.say(f"warning: the seed {path} is {_size(new)}, more than {SEED_GROWTH} times "
                  f"its {_size(old)} in the last release; it may hold your own data now")


def _entry(version: Version, changelog: str | None, today: datetime.date, q: Questions) -> str:
    title = f"## {version} ({today.isoformat()})"
    if changelog is None:
        written = q.edit(f"{title}\n\n", "--changelog TEXT")
        lines = written.splitlines()
        if lines and lines[0].startswith("## "):
            title, lines = lines[0].rstrip(), lines[1:]
        body = "\n".join(lines).strip()
    else:
        body = changelog.strip()
    if not body:
        raise HpmError("the changelog entry is empty; nothing published")
    return f"{title}\n\n{body}\n"


def _read_text(disk: Disk, path: str) -> str:
    try:
        real = disk.real(path)
        return real.read_text(encoding="utf-8") if real.is_file() else ""
    except OSError:
        return ""


def _put_on_top(changelog: str, entry: str) -> str:
    """The entry at the top of the changelog, newest first: under its "# " title if it has
    one."""
    if not changelog.strip():
        return entry
    lines = changelog.splitlines(keepends=True)
    if lines[0].startswith("# "):
        rest = "".join(lines[1:]).lstrip("\n")
        return lines[0] + "\n" + entry + ("\n" + rest if rest else "")
    return entry + "\n" + changelog


def _size(count: int) -> str:
    for unit in ("bytes", "KB", "MB"):
        if count < 1024 or unit == "MB":
            return f"{count} {unit}" if unit == "bytes" else f"{count:.1f} {unit}"
        count /= 1024
    return f"{count:.1f} MB"


# ---------------------------------------------------------------------- showing

def show(store: Store, name: str) -> str:
    """What `hpm show NAME` prints: the newest release's manifest, every version in the
    store, the newest changelog entries, and the files by kind with their sizes."""
    releases = store.releases(name)
    if not releases:
        raise HpmError(f"there is no package {name} in the store ({store.local})")
    latest = releases[-1]
    m = latest.manifest()
    head = f"{m.name} {m.version}" + (f"  ·  {m.summary}" if m.summary else "") \
        + (f"  ·  by {m.author}" if m.author else "")
    lines = [head, "", "versions: " + ", ".join(str(r.version) for r in releases)]
    if m.is_bundle:
        lines.append("bundle of: " + ", ".join(m.bundle))
    lines.append(f"data format: {m.data_format}")
    if m.for_app:
        lines.append(f"for: {m.for_app}")
    if m.requires_addons:
        lines.append("needs the addons: " + ", ".join(m.requires_addons))
    if m.requires_packages:
        lines.append("needs the packages: " + ", ".join(m.requires_packages))
    if m.private:
        lines.append("private: hpm push never sends it")
    if m.memory_line:
        lines.append(f"memory line: {m.memory_line}")
    if m.rules:
        lines.append("rules (they change the whole machine):")
        lines += [f"  {rule}" for rule in m.rules]
    if m.extras:
        lines.append("extras:")
        for extra in m.extras.values():
            more = ["ticked" if extra.default else "not ticked"]
            if extra.needs:
                more.append("needs " + ", ".join(extra.needs))
            lines.append(f"  {extra.key:<12} {extra.package}  ({'; '.join(more)})")
    files: dict[str, list[tuple[str, int]]] = {}
    for member, (size, _) in sorted(listing(latest.path).items()):
        if member.startswith("files/"):
            path = to_machine(member)
            files.setdefault(m.kind_of(path) or "?", []).append((path, size))
    for kind in ("app", "seed", "data", "?"):
        if kind not in files:
            continue
        listed = files[kind]
        lines.append(f"{kind} files: {len(listed)}, {_size(sum(s for _, s in listed))}")
        lines += [f"  {path}  {_size(size)}" for path, size in listed[:SHOWN_FILES]]
        if len(listed) > SHOWN_FILES:
            lines.append(f"  … and {len(listed) - SHOWN_FILES} more")
    entries = _entries((read_member(latest.path, CHANGELOG) or b"").decode("utf-8", "replace"))
    if entries:
        lines += ["", "changelog:"] + [f"  {line}" if line.strip() else ""
                                       for entry in entries[:SHOWN_ENTRIES]
                                       for line in entry.splitlines()]
    return "\n".join(lines)


def _entries(changelog: str) -> list[str]:
    """The changelog's entries, newest first: each from its "## " line to the next."""
    entries, current = [], None
    for line in changelog.splitlines():
        if line.startswith("## "):
            if current is not None:
                entries.append("\n".join(current).strip())
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        entries.append("\n".join(current).strip())
    return entries
