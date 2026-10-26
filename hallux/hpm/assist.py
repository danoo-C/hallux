"""What hpm asks of its AI, around the session of ai.py (docs/hpm/hpm.md, sections 5, 7 and
11; sharing.md, sections 3 and 4; migrations.md, section 3; the plan's steps 6 and 7): hpm
init, the changelog's draft, the card's review, a merge of memories, a migration note at
publish, and the test install. (A migration itself is hallux/hpm/migrate.py's.)

Every one of them costs money, so each asks first: on a terminal a question that names the
model and the cap, without one only its flag. What the AI gives back is checked by hpm's
code before anything of it is used.
"""
from __future__ import annotations

import asyncio
import dataclasses
import posixpath
import shutil
import tempfile
from pathlib import Path

from hallux import config
from hallux.disk import Disk
from hallux.hpm import ai
from hallux.hpm import record as rec
from hallux.hpm.manifest import Manifest, ManifestError
from hallux.hpm.publish import PRIVATE_NAMES, Questions, _with_value, family_problems
from hallux.hpm.store import Release, Store
from hallux.hpm.world import (
    MANIFESTS, HpmError, collect, manifest_path, read_world_manifest, world_user,
)


def may_spend(q: Questions, what: str, settings: ai.Settings, world: Path, flag: str,
              given: bool, default: bool = True) -> bool:
    """Whether the AI may do `what`: the flag, else a question on the terminal, else no."""
    if given:
        return True
    if not q.interactive:
        return False
    return q.confirm(f"{what}, with the AI ({settings.model_for(world)}, effort "
                     f"{settings.effort}, at most ${settings.cap_usd:.2f})?", default, flag)


# ---------------------------------------------------------------------- hpm init

def init(world: Path, store: Store, name: str, q: Questions, *, yes: bool = False,
         user: str | None = None, client_factory=None) -> list[str]:
    """Draft a program's manifest, and its extras', with the AI: from its card and the
    memory's line about it. hpm checks what it wrote, shows the problems to the AI once, and
    then to you; marks a memories package private if the AI didn't; and on a terminal opens
    the manifest in $EDITOR before it is kept. Returns the manifests written."""
    disk = Disk(world)
    if read_world_manifest(disk, name) is not None:
        raise HpmError(f"{name} has a manifest already ({manifest_path(name)}): edit it, or "
                       f"move it away to draft it again")
    try:
        card = disk.read_text(f"/usr/local/bin/{name}")
    except (OSError, ValueError):
        raise HpmError(f"this world has no card /usr/local/bin/{name} to draft {name} from") \
            from None
    settings = ai.settings(store)
    if not may_spend(q, f"draft {name}'s manifest", settings, world, "--yes", yes):
        raise HpmError(f"drafting {name}'s manifest needs the AI: pass --yes to let it, or "
                       f"write {manifest_path(name)} by hand")
    home = world_user(disk, user)
    before = _left_from_before(disk, name)
    if before:
        q.say("there from before, and kept as they are (hpm checks them with the new draft): "
              + ", ".join(before), kind="note")
    line = rec.untagged_line(disk, name) or next(iter(rec.memory_lines(disk, name)), None)
    line = rec.untag(line) if line else None      # hpm adds its own tag when it installs
    job = ai.init_job(name, card, line)

    def problems_of(answer: ai.Answer) -> str | None:
        found = _problems(disk, name, answer.wrote, home)
        if not found:
            return None
        return ("hpm checked what you wrote, and found these problems. Fix them in the same "
                "files:\n" + "\n".join(f"- {p}" for p in found))

    q.say(f"the AI is drafting {name}'s manifest…")
    answer = ai.run_job(world, job, settings, client_factory, follow=problems_of)
    if not answer.ok:
        raise HpmError(f"the AI's draft didn't end well ({answer.why}; {ai.cost(answer)}); "
                       f"what it wrote is left as it is: {', '.join(answer.wrote) or 'nothing'}")
    manifests = sorted(p for p in set(answer.wrote) if p.endswith("/hpm.toml"))
    if manifest_path(name) not in manifests:
        raise HpmError(f"the AI wrote no {manifest_path(name)} ({ai.cost(answer)})")
    for path in manifests:
        _keep_private(disk, path, home, q)
    q.say(answer.text.strip())
    for path in sorted(set(manifests) | set(_family_paths(disk, name))):
        q.say(f"\n--- {path}\n" + disk.read_text(path).rstrip(), kind="dim")
    if q.interactive and q.confirm(f"edit {manifest_path(name)} before it is kept?", False,
                                   "--yes"):
        text = q.edit(disk.read_text(manifest_path(name)), "--yes")
        disk.write_file(manifest_path(name), text)
    left = _problems(disk, name, manifests, home)
    q.say(f"the AI's part cost {ai.cost(answer)}")
    if left:
        raise HpmError("the manifests still have problems; fix them by hand, then hpm publish: "
                       + "; ".join(left))
    return manifests


def _family_paths(disk: Disk, name: str) -> list[str]:
    """The manifests of the program in the world: its own, and each extra's its [extras]
    lists that is there."""
    try:
        got = read_world_manifest(disk, name)
    except ManifestError:
        return [manifest_path(name)]
    if got is None:
        return []
    paths = [manifest_path(name)]
    for extra in got[0].extras.values():
        try:
            disk.read_text(manifest_path(extra.package))
        except (OSError, ValueError):
            continue
        paths.append(manifest_path(extra.package))
    return paths


def _left_from_before(disk: Disk, name: str) -> list[str]:
    """Manifests of the program's extras that are in the world before init writes: an
    earlier init's, when only the program's own manifest was moved away."""
    try:
        folder = disk.real(MANIFESTS)
    except OSError:
        return []
    if not folder.is_dir():
        return []
    return [manifest_path(p.name) for p in sorted(folder.iterdir())
            if p.name.startswith(name + "-") and (p / "hpm.toml").is_file()]


def _problems(disk: Disk, name: str, wrote: list[str], home: str | None) -> list[str]:
    """What is wrong with the program's manifests: each one alone (those written now and
    those of the family that are there), an extra the program doesn't list, and the files
    two of them carry (fix 01)."""
    written = set(p for p in wrote if p.endswith("/hpm.toml"))
    out, listed = [], None
    try:
        got = read_world_manifest(disk, name)
        listed = {e.package for e in got[0].extras.values()} if got else None
    except ManifestError:
        pass
    for path in sorted(written | set(_family_paths(disk, name))):
        try:
            manifest = Manifest.load(disk.read_text(path))
        except ManifestError as e:
            out += [f"{path}: {problem}" for problem in e.problems]
            continue
        except (OSError, ValueError) as e:
            out.append(f"{path} can't be read: {e}")
            continue
        if path != manifest_path(manifest.name):
            out.append(f"{path} holds the manifest of {manifest.name}, which belongs at "
                       f"{manifest_path(manifest.name)}")
        if listed is not None and manifest.name != name and path in written \
                and manifest.name not in listed:
            out.append(f"{path} is not listed under [extras] of {name}'s manifest; publish "
                       f"--all would leave it out")
        found = collect(disk, manifest, home)
        out += [f"{path}: {pattern} matches nothing on the machine" for pattern in found.empty]
    if listed is not None:
        out += family_problems(disk, name, home, unreadable=False)
    return out


def _keep_private(disk: Disk, path: str, home: str | None, q: Questions) -> None:
    """A data package whose files hold memories or a chat is private, whatever the AI wrote
    (sharing.md, section 3)."""
    try:
        text = disk.read_text(path)
        manifest = Manifest.load(text)
    except (OSError, ValueError, ManifestError):
        return
    if manifest.private or not (manifest.files["data"] or manifest.for_app):
        return
    files = collect(disk, manifest, home).files
    if any(PRIVATE_NAMES.fullmatch(posixpath.basename(p)) for p in files):
        disk.write_file(path, _with_value(text, "private", "true"))
        q.say(f"{manifest.name} holds memories or a chat: marked private, so hpm push never "
              f"sends it", kind="note")


# ---------------------------------------------------------------------- publish's helpers

def changelog_drafter(world: Path, store: Store, q: Questions, *, given: bool,
                      client_factory=None):
    """For publish: a function that drafts an entry from what changed, or None if the AI
    may not."""
    settings = ai.settings(store)

    def draft(name: str, release: Release | None, ours: dict, theirs: dict, version,
              manifest: str | None = None) -> str | None:
        if release is None:
            return None                           # a first release: nothing to compare
        if not may_spend(q, f"draft the changelog of {name} {version}", settings, world,
                         "--draft", given):
            return None
        added = sorted(m for m in ours if m not in theirs)
        changed = sorted(m for m in ours if m in theirs and theirs[m][1] != ours[m])
        removed = sorted(m for m in theirs if m not in ours and m.startswith(("files/", "migrations/")))
        from hallux.hpm.archive import to_machine, unpack
        machine = lambda ms: [to_machine(m) if m.startswith("files/") else m for m in ms]  # noqa: E731
        with tempfile.TemporaryDirectory(prefix="hpm-release-") as temp:
            unpack(release.path, Path(temp) / "p")
            old = Path(temp) / "world"
            try:
                home = world_user(Disk(world)) or "/home/user"
            except HpmError:                      # several users: the files under / still read
                home = "/home/user"
            _as_world(Path(temp) / "p", old, home)
            job = ai.changelog_job(name, old, machine(added), machine(changed), machine(removed),
                                   str(version), manifest)
            q.say(f"the AI is drafting the changelog of {name}…")
            answer = ai.run_job(world, job, settings, client_factory)
        q.say(f"the AI's draft cost {ai.cost(answer)}")
        if not answer.ok:
            q.say(f"the AI's draft didn't end well ({answer.why}); write the entry yourself",
                  kind="warning")
            return None
        entry, disagrees = split_manifest_block(answer.text)
        if disagrees:
            q.say(f"the AI says the manifest disagrees with this version (fix it in "
                  f"{manifest_path(name)} before you publish, if it is right):\n{disagrees}",
                  kind="warning")
        return entry

    return draft


def split_manifest_block(text: str) -> tuple[str, str]:
    """The changelog's entry, and the block after a line "Manifest:" that names what in the
    manifest disagrees with the change ("" if there is none)."""
    lines = text.strip().splitlines()
    at = next((i for i, line in enumerate(lines) if line.strip().rstrip(":").lower() == "manifest"
               and line.strip().endswith(":")), None)
    if at is None:
        return text.strip(), ""
    return "\n".join(lines[:at]).strip(), "\n".join(lines[at + 1:]).strip()


def _as_world(package: Path, into: Path, home: str) -> None:
    """An unpacked package laid out as a world: files/root/ at /, files/home/ at the home."""
    for root, at in (("root", "/"), ("home", home + "/")):
        source = package / "files" / root
        if source.is_dir():
            target = into / at.strip("/")
            shutil.copytree(source, target, dirs_exist_ok=True)
    into.mkdir(parents=True, exist_ok=True)


def card_reviewer(world: Path, store: Store, q: Questions, *, given: bool, client_factory=None):
    """For publish: a function that reviews a package's card, or None if the AI may not."""
    settings = ai.settings(store)

    def review(name: str, card: str, manifest: str) -> str | None:
        if not may_spend(q, f"have {name}'s card reviewed for what reaches beyond it",
                         settings, world, "--review", given):
            return None
        q.say(f"the AI is reviewing {name}'s card…")
        answer = ai.run_job(world, ai.review_job(name, card, manifest), settings, client_factory)
        q.say(f"the review cost {ai.cost(answer)}")
        if not answer.ok:
            q.say(f"the review didn't end well ({answer.why}); the release has none",
                  kind="warning")
            return None
        text = answer.text.strip()
        q.say(f"the review of {name}:\n{text}")
        return text + "\n"

    return review


def note_writer(world: Path, store: Store, q: Questions, *, given: bool, client_factory=None):
    """For publish: a function that has the AI write the migration note old → new when the
    data moved, or that says no when the AI may not. The note never ran on real data, and
    publish says so."""
    from hallux.hpm import migrate
    from hallux.hpm.archive import unpack
    settings = ai.settings(store)

    def write(name: str, release: Release, before: Manifest, after: Manifest, old: int,
              new: int) -> bool:
        moved = set(after.files["data"]) != set(before.files["data"])
        what = (f"{name}'s data moved since {release.version} "
                f"({list(before.files['data'])} → {list(after.files['data'])})" if moved
                else f"{name}'s data format goes {old} → {new}")
        q.say(f"{what}, and there is no note migrations/{old}-to-{new}.md for it")
        if not may_spend(q, f"have the note {old}-to-{new}.md written", settings, world,
                         "--write-migration", given):
            return False
        target = f"{MANIFESTS}/{name}/migrations/{old}-to-{new}.md"
        disk = Disk(world)

        def problems_of(answer: ai.Answer) -> str | None:
            try:
                migrate.read_note(f"{old}-to-{new}.md", disk.read_text(target))
            except (OSError, ValueError) as e:
                return f"hpm can't read {target}: {e}. Write it there."
            except HpmError as e:
                return f"hpm checked the note, and found: {e}. Fix it in the same file."
            return None

        with tempfile.TemporaryDirectory(prefix="hpm-release-") as temp:
            unpack(release.path, Path(temp) / "p")
            try:
                home = world_user(disk) or "/home/user"
            except HpmError:
                home = "/home/user"
            _as_world(Path(temp) / "p", Path(temp) / "world", home)
            job = migrate.write_note_job(name, old, new, Path(temp) / "world", before, after)
            q.say(f"the AI is writing {name}'s migration note…")
            answer = ai.run_job(world, job, settings, client_factory, follow=problems_of)
        q.say(f"the note cost {ai.cost(answer)}")
        left = problems_of(answer)
        if not answer.ok or left:
            q.say(f"the note can't be used ({answer.why or left}); write it yourself at {target}",
                  kind="warning")
            return False
        q.say(f"--- {target}\n" + disk.read_text(target).rstrip(), kind="dim")
        q.say("this note never ran on real data: the test install tries it on a copy of your "
              "base world (hpm publish --test)")
        return True

    return write


# ---------------------------------------------------------------------- merging memories

def merge(world: Path, store: Store, path: str, ours: str, theirs: str,
          client_factory=None) -> tuple[str | None, ai.Answer]:
    """Two memory files merged by the AI. Hallux's own check after it: every line of both is
    in the result, or the merge is refused (None)."""
    settings = ai.settings(store)
    answer = ai.run_job(world, ai.merge_job(path, ours, theirs), settings, client_factory)
    if not answer.ok:
        return None, answer
    merged = ai.bare(answer.text)
    have = set(line.strip() for line in merged.splitlines())
    lost = [line for line in (ours + "\n" + theirs).splitlines()
            if line.strip() and line.strip() not in have]
    if lost:
        answer.why = f"the merge left out {len(lost)} line(s), such as {lost[0][:60]!r}"
        return None, answer
    return merged, answer


# ---------------------------------------------------------------------- the test install

def test_install(store: Store, release: Release, q: Questions, client_factory=None) -> None:
    """Install the release into a copy of the base world, boot it and type the program's name
    once, with the model, effort and cap of the store's config.toml. The copy is removed."""
    from hallux.hpm.engine import OVERWRITE, Want, apply, plan_install
    from hallux.script import run_script
    settings = ai.settings(store)
    if not settings.base_world:
        raise HpmError(f"the test install needs a base world: set base_world in "
                       f"{settings.path} to a world to copy")
    base = Path(settings.base_world).expanduser()
    if not (base / ".hallux").is_dir():
        raise HpmError(f"base_world {base} is no Hallux world")
    with tempfile.TemporaryDirectory(prefix="hpm-test-") as temp:
        copy = Path(temp) / base.name
        shutil.copytree(base, copy, symlinks=True)
        (copy / ".hallux" / "running").unlink(missing_ok=True)
        manifest = release.manifest()
        extras = [k for k, e in manifest.extras.items() if e.default and store.find(e.package)]
        missing = [e.package for k, e in manifest.extras.items()
                   if e.default and k not in extras]
        if missing:
            q.say(f"the test install leaves out {', '.join(missing)}: not in the store yet")
        plan = plan_install(copy, store, [Want(release.name, extras=tuple(extras),
                                               version=str(release.version))])
        backup = _test_migrations(plan, store, q, client_factory)
        answers = {a.path: (OVERWRITE if OVERWRITE in a.choices else a.default)
                   for a in plan.questions}
        outcome = apply(plan, answers, backup=backup)
        q.say(f"test install into a copy of {base.name}: {outcome.summary()}")
        hardware = config.load(copy)
        model = settings.model_for(base)
        hardware = dataclasses.replace(hardware, model=model, max_budget_usd=settings.cap_usd,
                                       effort=None if "haiku" in model else settings.effort)
        more = {"client_factory": client_factory} if client_factory else {}
        records, _ = asyncio.run(run_script(copy, hardware, [release.name], **more))
        spent = sum(r.cost for r in records)              # the boot, the line, the Ctrl-D
        for record in records:
            if record.typed == "(boot)" and record.error:
                q.say(f"the copy didn't boot: {record.error}", kind="warning")
            elif record.typed == release.name:
                q.say(f"$ {record.typed}\n{record.output.rstrip()}" + (
                    f"\n(error: {record.error})" if record.error else ""))
        q.say(f"the test install cost ~${spent:.4f}; its copy is removed")


def _test_migrations(plan, store: Store, q: Questions, client_factory=None):
    """The migrations a test install needs, run on the copy and accepted whatever the checks
    say (the copy goes after), with the plan and the checks shown. Returns the backup."""
    from hallux.hpm import migrate
    shared = migrate.Shared()
    for item in plan.incomings() + plan.migrations():
        m = migrate.Migration(plan, item, store, incoming=item.incoming is not None,
                              shared=shared, client_factory=client_factory)
        while m.state == migrate.PLANNING:
            m.plan_rows()
            q.say("\n".join(m.plan_lines()))
            m.migrate()
        q.say("\n".join(m.checked_lines()))
        m.accept()
    return shared.backup
