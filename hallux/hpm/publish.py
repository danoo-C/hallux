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
import json
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
from hallux.hpm import record as rec
from hallux.hpm.archive import (
    CHANGELOG, REVIEW, ArchiveError, listing, pack, read_member, sha256, to_machine, to_member,
)
from hallux.hpm.manifest import Manifest, ManifestError, Version
from hallux.hpm.store import Release, Store
from hallux.hpm.world import (
    MANIFESTS, HpmError, clean_seed_path, collect, manifest_path, read_world_manifest,
    world_user,
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

    def choose(self, question: str, keys: str, flag: str) -> str:
        """One of the letters of `keys`, or "" for Enter."""
        self._needs_terminal(question, flag)
        while True:
            answer = input(f"{question}: ").strip().lower()
            if answer == "" or (len(answer) == 1 and answer in keys):
                return answer

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
            today: datetime.date | None = None, draft=None, review=None,
            write_note=None, seeds: str | None = None) -> list[Release]:
    """Publish a package from a world into the store; with `every` (--all), its extras too,
    each that changed since its last release. `draft(name, latest, ours, theirs, version)`
    may give the AI's draft of the changelog entry, and `review(name, card, manifest)` the
    AI's review of a card, saved in the release as review.md (hallux/hpm/assist.py), and
    `write_note(name, latest, before, after, old, new)` has the AI write the migration note
    when the data moved without one. With `suggested` (--yes), each takes the version hpm
    suggests, without asking. `seeds` (--seeds) answers for a used seed with no clean copy:
    "release" or "world". Returns what was published."""
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
                               today=today, unchanged_is_fine=every, draft=draft,
                               review=review, write_note=write_note, seeds=seeds)
        if release is not None:
            published.append(release)
            _extras_behind(release, store, questions)
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


def _publish_one(*args, **flags) -> Release | None:
    """One package; a folder of its own for the seeds of the last release it may send
    again (fix 07)."""
    with tempfile.TemporaryDirectory(prefix="hpm-seeds-") as scratch:
        return _publish_one_in(*args, scratch=Path(scratch), **flags)


def _publish_one_in(disk: Disk, name: str, store: Store, q: Questions, home: str | None, *,
                    version: str | None, changelog: str | None, private: bool | None,
                    suggested: bool, today: datetime.date,
                    unchanged_is_fine: bool, draft=None, review=None,
                    write_note=None, seeds: str | None = None,
                    scratch: Path) -> Release | None:
    manifest, text = _world_manifest(disk, name)
    collected, bare, differing = _with_clean_seeds(disk, name, collect(disk, manifest, home))
    migrations = _migrations(disk, name)

    problems = [f"{pattern} matches nothing in this world: the app moved something, and the "
                f"manifest has to follow" for pattern in collected.empty]
    problems += [f"{path} is a link; a package holds plain files" for path in collected.links]
    problems += _shared_with_family(disk, manifest, set(collected.files), home, q)
    if problems:
        raise HpmError(f"{name} can't be published: " + "; ".join(problems))

    latest = store.latest(name)
    before = latest.manifest() if latest else None
    step = _note_needed(manifest, before, migrations) if before is not None else None
    if step is not None and write_note is not None \
            and write_note(name, latest, before, manifest, *step):
        if manifest.data_format != step[1]:
            text = _with_value(text, "data_format", str(step[1]))
            disk.write_file(manifest_path(name), text, parents=True)
            q.say(f"{manifest_path(name)}: data_format is {step[1]} now")
        manifest, text = _world_manifest(disk, name)
        migrations = _migrations(disk, name)

    theirs = {} if latest is None else listing(latest.path)
    collected = _used_seeds(name, collected, bare, latest, theirs, q, seeds, suggested, scratch)
    ours = {to_member(path): sha256(real) for path, (_, real) in collected.files.items()}
    ours |= {member: sha256(real) for member, real in migrations.items()}
    if latest is not None and not _changed(manifest, before, ours, theirs):
        if unchanged_is_fine:
            q.say(f"{name} {latest.version}: unchanged, not published")
            return None
        raise HpmError(f"{name}: nothing changed since {latest.version}; nothing to publish")
    if before is not None:
        _check_data(name, manifest, before, latest)
        _same_words(name, manifest, before, latest, ours, theirs, q, suggested)
    _check_notes(name, manifest, migrations, store)

    new_version = _version(name, manifest, before, latest, version, suggested, q)
    new_text = _with_value(text, "version", f'"{new_version}"')
    new_text = _clean_memory_line(name, manifest, new_text, q)
    new_text = _privacy(name, manifest, collected, new_text, private, q)
    _seeds(collected, theirs, q)
    for path in differing:
        q.say(f"note: published the clean seed {clean_seed_path(name, path)}; the world's own "
              f"{posixpath.basename(path)} differs. To publish a new first state, write it "
              f"there.")
    drafted = draft(name, latest, ours, theirs, new_version, new_text) \
        if changelog is None and draft else None
    entry = _entry(new_version, changelog, today, q, drafted)
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
        card = collected.files.get(f"/usr/local/bin/{name}")
        if review is not None and card is not None:
            said = review(name, card[1].read_text(encoding="utf-8", errors="replace"), new_text)
            if said:
                (folder / REVIEW).write_text(said, encoding="utf-8")
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


def _with_clean_seeds(disk: Disk, name: str, collected):
    """A seed with a clean copy at /usr/local/share/hpm/<name>/seed/<path> (hpm init writes
    one where a seed holds your chat, install one for each seed) is published in place of
    the world's own (sharing.md, section 3). Also returned: the seeds with no copy, and
    those whose copy differs from the world's file (fix 07)."""
    files = dict(collected.files)
    bare, differing = [], []
    for path, (kind, real) in collected.files.items():
        if kind != "seed":
            continue
        try:
            clean = disk.real(clean_seed_path(name, path), follow=False)
        except OSError:
            clean = None
        if clean is not None and clean.is_file() and not clean.is_symlink():
            files[path] = (kind, clean)
            if sha256(clean) != sha256(real):
                differing.append(path)
        else:
            bare.append(path)
    return dataclasses.replace(collected, files=files), bare, differing


def _used_seeds(name: str, collected, bare: list[str], latest: Release | None,
                theirs: dict[str, tuple[int, str]], q: Questions, seeds: str | None,
                suggested: bool, scratch: Path):
    """A seed with no clean copy that changed since the last release may hold this world's
    own use: asked whether to keep the release's or send the world's (fix 07). --seeds
    answers for all; --yes keeps the release's. A first release isn't asked: init has just
    looked at the seeds."""
    if latest is None:
        return collected
    files = dict(collected.files)
    for path in bare:
        member = to_member(path)
        kind, real = files[path]
        if member not in theirs or sha256(real) == theirs[member][1]:
            continue
        answer = seeds
        if answer is None and suggested:
            answer = "release"
            q.say(f"{name}: kept {latest.version}'s seed {path}: it changed in this world and "
                  f"has no clean copy (--seeds world sends this world's)")
        if answer is None:
            q.say(f"{name}: the seed {path} changed since {latest.version}, and there's no "
                  f"clean copy of it. It may hold this world's own use (a chat, a story).\n"
                  f"  r  keep {latest.version}'s seed (the default)\n"
                  f"  w  publish this world's file\n"
                  f"  s  stop")
            answer = {"": "release", "r": "release", "w": "world", "s": "stop"}[
                q.choose("r, w or s", "rws", "--seeds release|world, or --yes for the last "
                                             "release's")]
        if answer == "stop":
            raise HpmError(f"write a clean one at {clean_seed_path(name, path)}, then publish "
                           f"again")
        if answer == "release":
            target = scratch / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read_member(latest.path, member) or b"")
            files[path] = (kind, target)
    return dataclasses.replace(collected, files=files)


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


def _family_names(disk: Disk, manifest: Manifest) -> tuple[str, Manifest | None]:
    """The program a package belongs to, and that program's manifest in the world (None if
    it has none, or one that doesn't read)."""
    app = manifest.for_app or manifest.name
    if app == manifest.name:
        return app, manifest
    try:
        got = read_world_manifest(disk, app)
    except ManifestError:
        got = None
    return app, got[0] if got else None


def _shared(path: str, a: str, b: str) -> str:
    return f"{path} is in {a} and in {b}; one package must carry it"


def _shared_with_family(disk: Disk, manifest: Manifest, ours: set[str], home: str | None,
                        q: Questions) -> list[str]:
    """The files this package and another package of the same app both carry: the app and
    its extras, whose manifests are in the world beside this one."""
    app, app_manifest = _family_names(disk, manifest)
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
        problems += [_shared(path, manifest.name, other) for path in both]
    return problems


def family_problems(disk: Disk, app: str, home: str | None,
                    unreadable: bool = True) -> list[str]:
    """The files that two packages of one program both carry: the app and every extra its
    manifest lists, whose manifests are in the world. Each problem names the file and both
    packages, in publish's words. A manifest that doesn't read is a problem too, unless
    `unreadable` is False (the caller has told it already)."""
    try:
        got = read_world_manifest(disk, app)
    except ManifestError as e:
        return [f"{manifest_path(app)} has problems: {e}"] if unreadable else []
    if got is None:
        return []
    members = [(app, got[0])]
    problems = []
    for extra in got[0].extras.values():
        try:
            found = read_world_manifest(disk, extra.package)
        except ManifestError as e:
            if unreadable:
                problems.append(f"{manifest_path(extra.package)} has problems: {e}")
            continue
        if found is not None:
            members.append((extra.package, found[0]))
    carried = [(name, set(collect(disk, manifest, home).files)) for name, manifest in members]
    for i, (a, files_a) in enumerate(carried):
        for b, files_b in carried[i + 1:]:
            problems += [_shared(path, a, b) for path in sorted(files_a & files_b)]
    return problems


def _changed(manifest: Manifest, before: Manifest, ours: dict[str, str],
             theirs: dict[str, tuple[int, str]]) -> bool:
    if dataclasses.replace(manifest, version=before.version) != before:
        return True
    old = {name: sha for name, (_, sha) in theirs.items()
           if name not in ("hpm.toml", CHANGELOG, REVIEW)}
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
            f"behind. Raise data_format, and write a migration for it (hpm publish "
            f"--write-migration has the AI write it; docs/hpm/migrations.md)")


def _same_words(name: str, manifest: Manifest, before: Manifest, latest: Release,
                ours: dict[str, str], theirs: dict[str, tuple[int, str]], q: Questions,
                suggested: bool) -> None:
    """The card changed, and the summary, memory line and requires are word for word as in
    the last release: asked if they are still right (fix 03). With --yes, or without a
    terminal, it is only said."""
    card = to_member(f"/usr/local/bin/{name}")
    if card not in ours or card not in theirs or ours[card] == theirs[card][1]:
        return
    words = lambda m: (m.summary, rec.untag(m.memory_line) if m.memory_line else "",  # noqa: E731
                       m.requires_addons, m.requires_packages)
    if words(manifest) != words(before):
        return
    said = (f"{name}: the card changed since {latest.version}, but the summary, memory line "
            f"and requires are as they were")
    if suggested or not q.interactive:
        q.say(f"note: {said}; check them in {manifest_path(name)}")
        return
    question = f"{said}. Still right?"
    if not q.confirm(question, True, "--yes"):
        raise HpmError(f"edit {manifest_path(name)}, then publish again")


def _extras_behind(release: Release, store: Store, q: Questions) -> None:
    """An app's data format went up, and an extra of it is still in an older one: every
    install of that extra next to the app migrates it (migrations.md, section 2). Told."""
    manifest = release.manifest()
    for extra in manifest.extras.values():
        found = store.latest(extra.package)
        if found is not None and found.manifest().data_format < manifest.data_format:
            q.say(f"note: {release.name}'s data format is {manifest.data_format}, and its extra "
                  f"{extra.package} {found.version} is still in format "
                  f"{found.manifest().data_format}: every install of it beside {release.name} "
                  f"migrates it with the AI. Publish it in format {manifest.data_format} too")


def _note_needed(manifest: Manifest, before: Manifest, migrations: dict[str, Path]):
    """The step from the last release's format that needs a note the world doesn't have:
    (old, new), or None. The data moved without a new format: the next one."""
    moved = set(manifest.files["data"]) != set(before.files["data"])
    old = before.data_format
    if manifest.data_format < old or not (moved or manifest.data_format > old):
        return None
    new = manifest.data_format if manifest.data_format > old else old + 1
    return None if f"migrations/{old}-to-{new}.md" in migrations else (old, new)


def _check_notes(name: str, manifest: Manifest, migrations: dict[str, Path], store: Store) -> None:
    """Every note reads, and a world with data in the format of any earlier release can come
    to this one: the chain of notes has no hole (migrations.md, section 3)."""
    from hallux.hpm.migrate import chain, read_note
    notes = [read_note(member.split("/", 1)[1], real.read_text(encoding="utf-8", errors="replace"))
             for member, real in migrations.items()]
    formats = sorted({r.manifest().data_format for r in store.releases(name)})
    for start in formats:
        if start < manifest.data_format:
            try:
                chain(notes, start, manifest.data_format, name)
            except HpmError as e:
                raise HpmError(f"{name} can't be published: {e}. Write it at "
                               f"{MANIFESTS}/{name}/migrations/ (hpm publish --write-migration "
                               f"has the AI write the last step)") from None


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
    pattern = re.compile(rf"^(\s*{key}\s*=\s*)(\"(?:[^\"\\]|\\.)*\"|'[^']*'|true|false)(.*)$",
                         re.S)
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


def _clean_memory_line(name: str, manifest: Manifest, text: str, q: Questions) -> str:
    """The manifest's memory line without hpm's tags (and without a "- " in front): hpm
    adds its own tag when it installs, so one copied into the manifest would be a second."""
    line = manifest.memory_line
    if not line:
        return text
    clean = rec.untag(line)
    if clean == line.strip():
        return text
    end = rec.TAGS.search(line.strip())
    tags = re.findall(r"\[hpm [^\]\s]+ [^\]\s]+\]", end.group(0)) if end else []
    took = " ".join(f'"{t}"' for t in tags) or 'the "- " in front'
    q.say(f"{manifest_path(name)}: memory_line: took out {took}; hpm adds its own when it "
          f"installs")
    return _with_value(text, "memory_line", json.dumps(clean, ensure_ascii=False))


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


def _entry(version: Version, changelog: str | None, today: datetime.date, q: Questions,
           drafted: str | None = None) -> str:
    """The changelog's new entry: --changelog, else the AI's draft (to edit, on a terminal),
    else what you write in $EDITOR."""
    title = f"## {version} ({today.isoformat()})"
    if changelog is None and drafted and not q.interactive:
        changelog = drafted
    if changelog is None:
        written = q.edit(f"{title}\n\n" + (f"{drafted}\n" if drafted else ""),
                         "--changelog TEXT, or --draft for the AI's")
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
