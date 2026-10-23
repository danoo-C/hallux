"""The install engine: install, update, remove, roll back and adopt, with no screen
(docs/hpm/hpm.md, sections 3, 6, 6a, 7, 7a, 8 and 9; sharing.md, section 4; the plan's
decisions 4 to 7 and step 3).

Two calls for each: a plan (plan_install, plan_remove, plan_adopt), which writes nothing
and says file by file what would happen and what must be asked; and apply(plan, answers),
which takes the backup first, then writes package after package, recording each in the
world's record as it ends. The command (step 4) and the Packages tab (step 5) only ask the
plan's questions and call apply.

What a package carries goes into the world through its Disk: Disk.place, then copy_whole.
So nothing lands outside the world's folder or in /.hallux. hpm's own files there are
record.py's.
"""
from __future__ import annotations

import errno
import os
import posixpath
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from hallux.disk import BOOT_FILES, Disk, copy_whole, write_whole
from hallux.hpm import migrate as mig
from hallux.hpm import record as rec
from hallux.hpm.archive import ArchiveError, package_files, sha256, unpack
from hallux.hpm.manifest import Manifest, Version, place
from hallux.hpm.store import Release, Store
from hallux.hpm.world import MANIFESTS, HpmError, world_user

# Answers to a file's question. Merge is for a memory file (memory.md, shared.md): the AI
# keeps the lines of both, and hpm writes what it gives back (hallux/hpm/ai.py).
OVERWRITE, SKIP, BOTH, FAIL, REMOVE, KEEP, MERGE = (
    "overwrite", "skip", "both", "fail", "remove", "keep", "merge")
MERGEABLE = ("memory.md", "shared.md")
REPLACE = "replace"                       # the old untagged memory line: replace it, or KEEP
STORE_ALL = "/"                           # "local/": every package of a store
META = "meta"                             # the manifest, changelog and notes in /usr/local/share/hpm
FULL = (errno.ENOSPC, errno.EDQUOT)
# Folders a remove never takes away, even when empty.
KEPT_FOLDERS = {"/", "/usr", "/usr/local", "/usr/local/bin", "/usr/local/share",
                "/usr/local/share/apps", MANIFESTS, "/home", "/etc", "/opt", "/var", "/root"}


@dataclass
class Action:
    """One file of a plan, and what will happen to it."""
    package: str
    path: str                             # where, in the world: "/home/danika-hous/.kittystory/x"
    machine: str                          # as the package names it: "~/.kittystory/x"
    kind: str                             # app, seed, data, or META
    mark: str                             # new, same, ours, changed, foreign, in-the-way,
                                          # seed-kept, data-kept; for a remove: gone, ours, changed
    op: str                               # write, skip, record, remove, keep, or ask
    source: Path | None = None            # the file in the unpacked package
    choices: tuple[str, ...] = ()         # when op is ask
    default: str | None = None
    owner: str | None = None              # another package whose record holds the path


@dataclass(frozen=True)
class Pending:
    """A migration a package waits for (migrations.md): the notes from the format its data is
    in, and the manifest whose data patterns the new layout has."""
    notes: tuple
    layout: Manifest


@dataclass
class Item:
    """One package of a plan."""
    name: str
    release: Release | None
    manifest: Manifest | None
    extras: tuple[str, ...] = ()          # the keys of its extras that are in the plan
    was: str | None = None                # the version installed before, for an update
    needs: tuple[str, ...] = ()           # packages of the plan it can't do without
    blocked: str | None = None            # why it can't be installed at all
    actions: list[Action] = field(default_factory=list)
    old_line: str | None = None           # an untagged memory line about it (section 7a)
    home: str | None = None
    migrate: Pending | None = None        # the world's data must be migrated first
    incoming: Pending | None = None       # its own data must be, before it comes in
    skip: str | None = None               # why it is left out: its migration was cancelled
    migrated: dict | None = None          # its data's migration that landed, for the machine

    @property
    def live(self) -> bool:
        return not self.blocked and not self.skip


@dataclass
class Plan:
    kind: str                             # install, remove or adopt
    disk: Disk
    items: list[Item]
    home: str | None = None
    loud: list[tuple[str, str, str]] = field(default_factory=list)   # (package, path, why)
    notes: list[str] = field(default_factory=list)                   # addons, and the like
    temp: tempfile.TemporaryDirectory | None = None
    data: bool = False                    # a remove with --data
    merged: dict[str, str] = field(default_factory=dict)   # a path: the merged text to write

    @property
    def questions(self) -> list[Action]:
        return [a for item in self.items if item.live for a in item.actions if a.op == "ask"]

    def memory_questions(self) -> list[Item]:
        return [item for item in self.items if item.old_line and item.live]

    def migrations(self) -> list[Item]:
        """The packages whose data in the world waits for a migration."""
        return [item for item in self.items if item.migrate and item.live]

    def incomings(self) -> list[Item]:
        """The data packages whose own data waits for one, before it comes in."""
        return [item for item in self.items if item.incoming and item.live]

    def grouped(self) -> dict[tuple[str, str], list[Action]]:
        """The questions by package and folder: "3 packs are already installed here"."""
        groups: dict[tuple[str, str], list[Action]] = {}
        for action in self.questions:
            groups.setdefault((action.package, posixpath.dirname(action.path)), []).append(action)
        return groups

    def close(self) -> None:
        if self.temp is not None:
            self.temp.cleanup()
            self.temp = None


@dataclass
class Done:
    """What happened to one package."""
    name: str
    version: str | None
    was: str | None
    status: str                           # installed, updated, removed, adopted, rolled back,
                                          # failed, skipped
    why: str = ""
    written: int = 0
    removed: int = 0
    places: tuple[str, ...] = ()          # the folders it wrote into, for the machine's note
    migrated: dict | None = None          # {"from", "to", "gone", "into"}: its data moved


@dataclass
class Outcome:
    done: list[Done]
    backup: str | None = None

    def count(self, status: str) -> int:
        return sum(1 for d in self.done if d.status == status)

    @property
    def notes(self) -> list[dict]:
        """For the machine's <installed> (step 5): what was written or removed."""
        return [{"name": d.name, "version": d.version, "was": d.was, "files": d.written,
                 "places": list(d.places), **({"removed": True} if d.status == "removed" else {}),
                 **({"data_migrated": d.migrated} if d.migrated else {})}
                for d in self.done if d.status in ("installed", "updated", "removed",
                                                   "rolled back")]

    def summary(self) -> str:
        parts = []
        for status in ("installed", "updated", "removed", "adopted", "rolled back"):
            if n := self.count(status):
                parts.append(f"{n} {status}")
        failed = [d for d in self.done if d.status == "failed"]
        if failed:
            parts.append(f"{len(failed)} failed: " + ", ".join(f"{d.name} ({d.why})" for d in failed))
        skipped = [d for d in self.done if d.status == "skipped"]
        if skipped:
            parts.append(f"{len(skipped)} skipped: " + ", ".join(f"{d.name} ({d.why})"
                                                                 for d in skipped))
        return " · ".join(parts) or "nothing to do"


# ---------------------------------------------------------------------- what is wanted

@dataclass(frozen=True)
class Want:
    """A package to install, with the keys of the extras chosen (None: its defaults). `store`
    is the store it comes from (None: the one that has it); with `hint`, the store is only
    where to look first, as for an extra, which comes from its app's store if that has it."""
    name: str
    extras: tuple[str, ...] | None = None
    version: str | None = None
    store: str | None = None
    hint: bool = False


def qualified(want: Want) -> Want:
    """"danika/kittystory" as a name: the package kittystory of the store danika."""
    if "/" in want.name and not want.name.endswith(STORE_ALL):
        where, _, name = want.name.partition("/")
        return Want(name, want.extras, want.version, where)
    return want


def _release(store: Store, want: Want) -> Release:
    want = qualified(want)
    where = want.store
    if want.hint and where is not None and not store.releases(want.name, where):
        # not in its app's store: your own, else wherever it is
        where = "local" if store.releases(want.name, "local") else None
    if want.version is None:
        release = store.find(want.name, where)
        if release is None:
            raise HpmError(f"there is no package {want.name} in "
                           + (f"the store {where}" if where else "the store"))
        return release
    version = Version(want.version)
    places = [where] if where else store.places(want.name) or ["local"]
    for place in places:
        for release in store.releases(want.name, place):
            if release.version == version:
                return release                    # named exactly: a yanked one too
    raise HpmError(f"the store has no {want.name} {want.version}")


def expand(store: Store, wants: list[Want]) -> list[Want]:
    """Stores and bundles into packages. "local/" is every package of your store that isn't
    a bundle or another package's extra (those come with their app)."""
    out: list[Want] = []
    for want in wants:
        if want.name.endswith(STORE_ALL):
            where = want.name[:-1]
            if where not in store.wheres():
                raise HpmError(f"there is no store {where!r} (hpm store list shows them)")
            manifests = {name: store.latest(name, where).manifest()
                         for name in store.names(where)}
            extras = {e.package for m in manifests.values() for e in m.extras.values()}
            out += [Want(name, store=where) for name, m in manifests.items()
                    if not m.is_bundle and name not in extras]
            continue
        want = qualified(want)
        release = _release(store, want)
        if release.manifest().is_bundle:
            out += expand(store, [Want(name, store=release.where, hint=True)
                                  for name in release.manifest().bundle])
        else:
            out.append(want if want.store or release.where == "local"
                       else Want(want.name, want.extras, want.version, release.where))
    return out


# ---------------------------------------------------------------------- planning an install

def plan_install(world: Path | str, store: Store, wants: list[Want], user: str | None = None,
                 addons_folder: Path | None = None) -> Plan:
    """What installing (or updating to) these packages would do. Nothing is written; the
    packages are unpacked into a temporary folder that the plan keeps until it is closed."""
    disk = Disk(world)
    record = rec.load(disk)
    items: dict[str, Item] = {}
    chosen: dict[str, set[str]] = {}
    order: list[str] = []

    def add(want: Want, by: str | None = None, auto: bool = False) -> None:
        release = _release(store, want)
        there = record.get(release.name, {})
        if auto and release.name not in items and not there.get("incomplete") \
                and there.get("version") is not None and Version(there["version"]) == release.version:
            return                                # an extra that is there already, as it is
        manifest = release.manifest()
        here = release.where                      # what it needs comes from there first
        if manifest.is_bundle:
            for name in manifest.bundle:
                add(Want(name, store=here, hint=True), by)
            return
        keys = set(want.extras if want.extras is not None
                   else [k for k, e in manifest.extras.items() if e.default])
        unknown = keys - set(manifest.extras)
        if unknown:
            raise HpmError(f"{manifest.name} has no extra {', '.join(sorted(unknown))} "
                           f"(its extras: {', '.join(manifest.extras) or 'none'})")
        keys = _with_needs(manifest, keys)
        if manifest.name in items:
            new = keys - chosen[manifest.name]
            chosen[manifest.name] |= keys
            if want.version is not None and items[manifest.name].release.version != release.version:
                raise HpmError(f"{manifest.name} is wanted in two versions")
        else:
            new = keys
            chosen[manifest.name] = keys
            before = record.get(manifest.name, {})
            items[manifest.name] = Item(manifest.name, release, manifest,
                                        was=None if before.get("incomplete")
                                        else before.get("version"))
            order.append(manifest.name)
            for name in manifest.requires_packages:
                if name not in record:
                    add(Want(name, store=here, hint=True))
            if manifest.for_app and manifest.for_app not in record:
                add(Want(manifest.for_app, extras=(), store=here, hint=True))
        for key in [k for k in manifest.extras if k in new]:     # in the manifest's order
            add(Want(manifest.extras[key].package, store=here, hint=True), auto=True)

    for want in expand(store, wants):
        add(want)

    for name, item in items.items():
        item.extras = tuple(k for k in item.manifest.extras if k in chosen[name])
        needs = set(item.manifest.requires_packages)
        if item.manifest.for_app:
            needs.add(item.manifest.for_app)
        for other in items.values():              # an extra after its app, and after the
            for extra in other.manifest.extras.values():    # extras it needs
                if extra.package == name:
                    needs.add(other.name)
                    needs |= {other.manifest.extras[n].package for n in extra.needs}
        item.needs = tuple(sorted(n for n in needs if n in items))
    ordered = [items[name] for name in _ordered(items, order)]

    plan = Plan("install", disk, ordered)
    homes_needed = any(p.startswith("~/") for item in ordered for _, p in item.manifest.patterns())
    plan.home = world_user(disk, user) if homes_needed else None
    if homes_needed and plan.home is None:
        raise HpmError("this world has no user home, so files under ~ have nowhere to go")
    plan.temp = tempfile.TemporaryDirectory(prefix="hpm-plan-")
    try:
        _check_addons(plan, addons_folder)
        for item in ordered:
            item.home = plan.home
            _check_format(item, items, record, store, disk)
            if item.blocked:
                continue
            folder = Path(plan.temp.name) / item.name
            try:
                unpack(item.release.path, folder)
            except ArchiveError as e:
                item.blocked = str(e)
                continue
            _walk(plan, item, folder, record)
            if item.manifest.memory_line:
                item.old_line = rec.untagged_line(disk, item.name)
    except BaseException:
        plan.close()
        raise
    for item in ordered:                         # what can't go without what it needs
        missing = [n for n in item.needs if items[n].blocked]
        if missing and not item.blocked:
            item.blocked = f"needs {', '.join(missing)}, which can't be installed"
    return plan


def _with_needs(manifest: Manifest, keys: set[str]) -> set[str]:
    """The chosen extras, and every extra they need: ticking characters ticks packs."""
    out, todo = set(), list(keys)
    while todo:
        key = todo.pop()
        if key not in out:
            out.add(key)
            todo += manifest.extras[key].needs
    return out


def _ordered(items: dict[str, Item], first: list[str]) -> list[str]:
    """The packages, each after what it needs; in the order they were asked for otherwise."""
    done: list[str] = []
    on: set[str] = set()

    def visit(name: str, path: list[str]) -> None:
        if name in done:
            return
        if name in on:
            raise HpmError("the packages need each other in a circle: " + " → ".join(path + [name]))
        on.add(name)
        for need in items[name].needs:
            visit(need, path + [name])
        on.discard(name)
        done.append(name)

    for name in first:
        visit(name, [])
    return done


def addons_known(root: Path, folder: Path | None = None) -> tuple[set[str], tuple | None, str | None]:
    """The addons Hallux has (the *.py files of its addons folder, never imported here), the
    ones the world gets (its config's `addons`; None: every one), and why the config can't be
    read, if it can't."""
    from hallux import config
    from hallux.app import ADDONS_FOLDER
    folder = folder or ADDONS_FOLDER
    have = {p.stem for p in folder.glob("*.py")} if folder.is_dir() else set()
    try:
        return have, config.load(root).addons, None
    except ValueError as e:
        return have, None, str(e)


def addon_problems(manifest: Manifest, have: set[str], gets: tuple | None) -> list[str]:
    """What is missing of a package's requires.addons, in words."""
    out = []
    for addon in manifest.requires_addons:
        if addon not in have:
            out.append(f"needs the {addon} addon, which Hallux doesn't have")
        elif gets is not None and addon not in gets:
            out.append(f"needs the {addon} addon, which this world doesn't get (its config's "
                       f"addons)")
    return out


def _check_addons(plan: Plan, folder: Path | None) -> None:
    have, gets, unread = addons_known(plan.disk.root, folder)
    if unread:
        plan.notes.append(f"the world's config can't be read, so its addons aren't known: {unread}")
    for item in plan.items:
        for problem in addon_problems(item.manifest, have, gets):
            there = " there" if "world" in problem else ""
            plan.notes.append(f"{item.name} {problem}; it installs, but that part won't "
                              f"work{there}")


def _check_format(item: Item, items: dict[str, Item], record: dict, store: Store,
                  disk: Disk) -> None:
    """The data formats (migrations.md, section 2). The world's data in an older format waits
    for the package's notes; incoming data in an older format than its app, for the app's;
    a newer format in the world is refused, and so is data newer than its app."""
    fmt = item.manifest.data_format
    there = record.get(item.name, {}).get("data_format")
    if there is not None and there > fmt:
        item.blocked = (f"the world's data is in format {there}, newer than {fmt} of "
                        f"{item.name} {item.release.version}: an older app on newer data")
        return
    if there is not None and there < fmt:
        try:
            notes = mig.chain(mig.release_notes(item.release), there, fmt,
                              f"{item.name} {item.release.version}")
        except HpmError as e:
            item.blocked = str(e)
            return
        item.migrate = Pending(tuple(notes), item.manifest)
    app = item.manifest.for_app
    if not app:
        return
    if app in items:
        app_format, layout = items[app].manifest.data_format, items[app].manifest
    else:
        app_format = record.get(app, {}).get("data_format")
        layout = None
    if app_format is None or fmt == app_format:
        return
    if fmt > app_format:
        item.blocked = (f"{item.name} {item.release.version} has data in format {fmt}, newer "
                        f"than {app_format} of {app} here; update {app} first")
        return
    try:                       # the app's notes: the release coming, else the world's, else the store's
        if app in items:
            notes = mig.release_notes(items[app].release)
        else:
            notes = mig.world_notes(disk, app)
            got = None
            try:
                from hallux.hpm.world import read_world_manifest
                got = read_world_manifest(disk, app)
            except ValueError:
                pass
            layout = got[0] if got else None
            if not notes or layout is None:
                found = store.find(app, item.release.where) or store.find(app, "local")
                if found is not None and found.manifest().data_format >= app_format:
                    notes = notes or mig.release_notes(found)
                    layout = layout or found.manifest()
        if layout is None:
            raise HpmError(f"{app}'s manifest isn't in this world or the store, so the new "
                           f"layout of its data isn't known")
        chained = mig.chain(notes, fmt, app_format, app)
    except HpmError as e:
        item.blocked = (f"{item.name} {item.release.version} has data in format {fmt}, and "
                        f"{app} here has {app_format}: {e}")
        return
    item.incoming = Pending(tuple(chained), layout)


def _meta_files(folder: Path, name: str) -> dict[str, Path]:
    """The package's manifest, changelog and notes, for /usr/local/share/hpm/<name>/."""
    out = {f"{MANIFESTS}/{name}/hpm.toml": folder / "hpm.toml"}
    if (folder / "CHANGELOG.md").is_file():
        out[f"{MANIFESTS}/{name}/CHANGELOG.md"] = folder / "CHANGELOG.md"
    notes = folder / "migrations"
    if notes.is_dir():
        for note in sorted(notes.iterdir()):
            out[f"{MANIFESTS}/{name}/migrations/{note.name}"] = note
    return out


def _walk(plan: Plan, item: Item, folder: Path, record: dict) -> None:
    """Every file of the package, marked, as drag and drop's tree marks what is in the way."""
    disk, manifest = plan.disk, item.manifest
    installed = record.get(item.name)
    mine = installed["files"] if installed else {}
    files = package_files(folder)
    unlisted = sorted(path for path in files if manifest.kind_of(path) is None)
    if unlisted:
        item.blocked = (f"it carries files its manifest doesn't list: {', '.join(unlisted[:5])}"
                        + (" …" if len(unlisted) > 5 else ""))
        return
    entries = [(machine, manifest.kind_of(machine), source) for machine, source in files.items()]
    entries += [(path, META, source) for path, source in _meta_files(folder, item.name).items()]
    seen: set[str] = set()
    for machine, kind, source in entries:
        path = place(machine, plan.home) if machine.startswith("~/") else machine
        seen.add(path)
        try:
            real = disk.place(path)
        except OSError as e:
            item.blocked = f"{path} can't be written: {e.strerror or e}"
            return
        action = _mark(disk, item, path, machine, kind, source, real, mine, record, installed)
        item.actions.append(action)
        _loud(plan, item, path, kind)
    if installed:                                 # an update: what the new version lost
        for path, old in sorted(mine.items()):
            if path in seen or old["kind"] in ("data", "seed"):
                continue                          # data is never removed by an update
            real = disk.root / path.lstrip("/")
            if not real.is_file() or real.is_symlink():
                continue
            if sha256(real) == old["sha256"]:
                item.actions.append(Action(item.name, path, path, old["kind"], "ours", "remove"))
            else:
                item.actions.append(Action(item.name, path, path, old["kind"], "changed", "ask",
                                           choices=(REMOVE, KEEP), default=KEEP))
    if manifest.rules:
        plan.loud.append((item.name, "", "it adds rules, which change the whole machine: "
                          + " · ".join(manifest.rules)))


def _mark(disk: Disk, item: Item, path: str, machine: str, kind: str, source: Path, real: Path,
          mine: dict, record: dict, installed: dict | None) -> Action:
    def act(mark: str, op: str, **more) -> Action:
        return Action(item.name, path, machine, kind, mark, op, source, **more)

    for parent in real.parents:                   # a file where a folder must be
        if parent == disk.root:
            break
        if os.path.lexists(parent) and not parent.is_dir():
            return act("in-the-way", "ask", choices=(SKIP, FAIL), default=SKIP)
    try:
        found = real.lstat()
    except FileNotFoundError:
        return act("new", "write")
    if not stat.S_ISREG(found.st_mode):
        return act("in-the-way", "ask", choices=(SKIP, FAIL), default=SKIP)
    if kind == "seed":
        return act("seed-kept", "record")
    there = sha256(real)
    if there == sha256(source):
        return act("same", "record")
    if installed and kind == "data":
        return act("data-kept", "skip")           # an update never overwrites data
    if path in mine:
        if mine[path]["sha256"] == there:
            return act("ours", "write") if kind in ("app", META) else act("data-kept", "skip")
        return act("changed", "ask", choices=(OVERWRITE, SKIP, BOTH) + _merge(path), default=SKIP)
    default = SKIP if kind == "data" else OVERWRITE
    return act("foreign", "ask", choices=(OVERWRITE, SKIP, BOTH) + _merge(path), default=default,
               owner=rec.owner(record, path, but=item.name))


def _merge(path: str) -> tuple[str, ...]:
    return (MERGE,) if posixpath.basename(path) in MERGEABLE else ()


def _loud(plan: Plan, item: Item, path: str, kind: str) -> None:
    """What must be shown loudly: a file the machine reads at every boot, and another
    program's card."""
    if path in BOOT_FILES or posixpath.basename(path) == ".bashrc":
        plan.loud.append((item.name, path, "the machine reads it at every boot"))
    elif posixpath.dirname(path) == "/usr/local/bin" and posixpath.basename(path) not in (
            item.name, item.manifest.for_app):
        plan.loud.append((item.name, path, "it is a card in /usr/local/bin, and not this "
                          "package's own"))


def rewalk(plan: Plan, item: Item, folder: Path | None = None,
           manifest: Manifest | None = None) -> None:
    """Mark a package's files again, after its migration changed the world (or, for data
    coming in, the package itself: `folder` and `manifest` are its migrated form)."""
    if manifest is not None:
        item.manifest = manifest
    item.actions = []
    plan.loud = [entry for entry in plan.loud if entry[0] != item.name]
    _walk(plan, item, folder or Path(plan.temp.name) / item.name, rec.load(plan.disk))


# ---------------------------------------------------------------------- planning a remove

def plan_remove(world: Path | str, name: str, data: bool = False) -> Plan:
    """What `hpm remove` would do: the package's app files and its manifest's folder, unless
    you changed them since (asked); seeds and data stay, unless `data`."""
    disk = Disk(world)
    record = rec.load(disk)
    if name not in record:
        raise HpmError(f"{name} isn't installed in this world")
    entry = record[name]
    item = Item(name, None, None, was=entry["version"])
    for path, old in sorted(entry["files"].items()):
        real = disk.root / path.lstrip("/")
        if old["kind"] in ("seed", "data") and not data:
            continue
        if not real.is_file() or real.is_symlink():
            item.actions.append(Action(name, path, path, old["kind"], "gone", "skip"))
        elif old["kind"] in ("seed", "data") or sha256(real) == old["sha256"]:
            item.actions.append(Action(name, path, path, old["kind"], "ours", "remove"))
        else:
            item.actions.append(Action(name, path, path, old["kind"], "changed", "ask",
                                       choices=(REMOVE, KEEP), default=KEEP))
    plan = Plan("remove", disk, [item], data=data)
    return plan


# ---------------------------------------------------------------------- planning an adopt

def plan_adopt(world: Path | str, release: Release, user: str | None = None) -> Plan:
    """Recording an app that was in the world before hpm (section 7a): the files identical
    to the release's become the package's; the others stay foreign. Nothing else is
    written, but the old memory line may be replaced."""
    disk = Disk(world)
    manifest = release.manifest()
    item = Item(manifest.name, release, manifest)
    plan = Plan("adopt", disk, [item])
    if any(p.startswith("~/") for _, p in manifest.patterns()):
        plan.home = world_user(disk, user)
    item.home = plan.home
    plan.temp = tempfile.TemporaryDirectory(prefix="hpm-adopt-")
    folder = Path(plan.temp.name) / "package"
    try:
        unpack(release.path, folder)
    except ArchiveError as e:
        plan.close()
        raise HpmError(str(e)) from None
    files = {m: (manifest.kind_of(m), s) for m, s in package_files(folder).items()}
    files |= {p: (META, s) for p, s in _meta_files(folder, manifest.name).items()}
    for machine, (kind, source) in sorted(files.items()):
        if machine.startswith("~/") and plan.home is None:
            continue
        path = place(machine, plan.home) if machine.startswith("~/") else machine
        try:
            real = disk.place(path)
        except OSError:
            continue
        if real.is_file() and not real.is_symlink() and sha256(real) == sha256(source):
            item.actions.append(Action(item.name, path, machine, kind, "same", "record", source))
        else:
            item.actions.append(Action(item.name, path, machine, kind, "foreign", "skip", source))
    if manifest.memory_line:
        item.old_line = rec.untagged_line(disk, item.name)
    return plan


# ---------------------------------------------------------------------- carrying it out

def apply(plan: Plan, answers: dict[str, str] | None = None, all_files: str | None = None,
          progress=None, stop=None, merged: dict[str, str] | None = None,
          backup: rec.Backup | None = None) -> Outcome:
    """Carry the plan out. `answers` answers its questions: a placed path to one of the
    question's choices, and "memory:<name>" to REPLACE or KEEP for an old memory line.
    `all_files` answers every file question that `answers` doesn't, if it is one of that
    question's choices. A question left without an answer is an error before anything is
    written. `progress(done)` is told after each package. `stop`, a threading.Event, ends
    the write between two packages, never in the middle of one: the rest are skipped.
    `backup` is the update's backup that its migrations made (hallux/hpm/migrate.py): the
    install adds to it, so one rollback undoes both. A migration still waiting is an error."""
    waiting = [item.name for item in plan.migrations() + plan.incomings()]
    if waiting:
        plan.close()
        raise HpmError(f"the data of {', '.join(waiting)} has to be migrated first: hpm runs "
                       f"the migration before it writes")
    answers = dict(answers or {})
    for action in plan.questions:
        answer = answers.get(action.path)
        if answer is None and all_files in action.choices:
            answer = answers[action.path] = all_files
        if answer is None:
            raise HpmError(f"{action.path} ({action.package}, {action.mark}) has no answer; "
                           f"it is one of: {', '.join(action.choices)}")
        if answer not in action.choices:
            raise HpmError(f"{action.path}: {answer!r} isn't one of {', '.join(action.choices)}")
        if answer == MERGE and action.path not in (merged or {}):
            raise HpmError(f"{action.path}: merge needs the merged text, and there is none")
    for item in plan.memory_questions():
        answers.setdefault(f"memory:{item.name}", REPLACE)
    try:
        if plan.kind == "remove":
            return _apply_remove(plan, answers, progress)
        plan.merged = dict(merged or {})
        return _apply_install(plan, answers, progress, stop, backup)
    finally:
        plan.close()


def _resolved(action: Action, answers: dict[str, str]) -> str:
    """What happens to the file: write, both, skip, record, remove, keep, fail."""
    if action.op != "ask":
        return action.op
    answer = answers[action.path]
    return {OVERWRITE: "write", SKIP: "skip", BOTH: "both", FAIL: "fail", REMOVE: "remove",
            KEEP: "keep", MERGE: "merge"}[answer]


def _apply_install(plan: Plan, answers: dict[str, str], progress, stop=None,
                   backup: rec.Backup | None = None) -> Outcome:
    disk = plan.disk
    record = rec.load(disk)
    live = [item for item in plan.items if item.live]
    touched = {a.path: a.package for item in live for a in item.actions
               if _resolved(a, answers) in ("write", "remove", "merge")}
    touched |= {_beside(a.path): a.package for item in live for a in item.actions
                if _resolved(a, answers) == "both"}
    if plan.kind == "install" and live:
        entries = {item.name: record.get(item.name) for item in live}
        memory = {item.name: {"untagged": item.old_line if answers.get(f"memory:{item.name}") == REPLACE
                              else None} for item in live}
        if backup is not None:
            rec.extend_backup(disk, backup, touched, entries, memory)
        else:
            backup = rec.make_backup(disk, live[0].name, touched, entries, memory)
    elif plan.kind != "install":
        backup = None
    done: list[Done] = []
    failed: set[str] = set()
    full = None
    for item in plan.items:
        version = str(item.release.version) if item.release else None
        if item.blocked:
            done.append(Done(item.name, version, item.was, "failed", item.blocked))
            failed.add(item.name)
        elif item.skip:
            done.append(Done(item.name, version, item.was, "skipped", item.skip))
            failed.add(item.name)                 # what needs it can't go either
        elif full is not None:
            done.append(Done(item.name, version, item.was, "skipped", full))
        elif stop is not None and stop.is_set():
            done.append(Done(item.name, version, item.was, "skipped", "stopped"))
        elif missing := [n for n in item.needs if n in failed]:
            done.append(Done(item.name, version, item.was, "skipped",
                             "needs " + ", ".join(missing)))
            failed.add(item.name)
        else:
            result = _install_item(plan, item, answers, record)
            done.append(result)
            if result.status == "failed":
                failed.add(item.name)
                if result.why == "the disk is full":
                    full = "the disk was full"
        if progress is not None:
            progress(done[-1])
    return Outcome(done, backup.name if backup else None)


def _beside(path: str) -> str:
    """Where "keep both" writes the package's file: metal-head.pack -> metal-head.hpm-new.pack."""
    folder, name = posixpath.split(path)
    stem, dot, ext = name.rpartition(".")
    new = f"{stem}.hpm-new.{ext}" if dot and stem else f"{name}.hpm-new"
    return posixpath.join(folder, new)


def _install_item(plan: Plan, item: Item, answers: dict[str, str], record: dict) -> Done:
    disk = plan.disk
    version = str(item.release.version)
    old = record.get(item.name)
    adopting = plan.kind == "adopt"
    files = {} if old is None or adopting else {p: f for p, f in old["files"].items()
                                                if f["kind"] in ("data", "seed")}
    written = removed = 0
    places: set[str] = set()
    entry = {"version": version, "from": item.release.where, "installed": rec.now(),
             "data_format": item.manifest.data_format, "extras": list(item.extras),
             "home": item.home, "memory_line": item.manifest.memory_line,
             "rules": list(item.manifest.rules), "files": files}
    if adopting:
        entry["adopted"] = True
    why = None
    for action in item.actions:
        what = "skip" if adopting and action.op == "skip" else _resolved(action, answers)
        try:
            if what == "fail":
                why = f"{action.path} is in the way"
                break
            if what in ("write", "both"):
                target = action.path if what == "write" else _beside(action.path)
                real = disk.place(target)
                _make_folders(disk, real)
                copy_whole(action.source, real)
                files[target] = {"kind": action.kind, "sha256": sha256(real)}
                written += 1
                places.add(_place_of(action.machine if what == "write" else target))
            elif what == "merge":                 # the AI's merged text, in place of both
                real = disk.place(action.path)
                write_whole(real, plan.merged[action.path])
                files[action.path] = {"kind": action.kind, "sha256": sha256(real)}
                written += 1
                places.add(_place_of(action.machine))
            elif what == "record":
                real = disk.place(action.path)
                files[action.path] = {"kind": action.kind, "sha256": sha256(real)}
            elif what == "remove":
                real = disk.place(action.path)
                real.unlink(missing_ok=True)
                files.pop(action.path, None)
                _remove_empty_folders(disk, action.path, item.home)
                removed += 1
            elif what == "keep":
                files.pop(action.path, None)      # yours now, not the package's
        except OSError as e:
            why = "the disk is full" if e.errno in FULL else f"{action.path}: {e.strerror or e}"
            break
    if why is not None:
        entry["incomplete"] = True
        record[item.name] = entry
        rec.save(disk, record)
        return Done(item.name, version, item.was, "failed", why, written, removed,
                    tuple(sorted(places)))
    record[item.name] = entry
    rec.save(disk, record)
    replace = item.old_line if answers.get(f"memory:{item.name}") == REPLACE else None
    if item.manifest.memory_line or item.manifest.rules or replace:
        rec.set_memory(disk, item.name, version, item.manifest.memory_line, item.manifest.rules,
                       replace)
    status = "adopted" if adopting else ("updated" if item.was else "installed")
    return Done(item.name, version, item.was, status, "", written, removed, tuple(sorted(places)),
                item.migrated)


def _place_of(path: str) -> str:
    """The folder a file is in, as the machine's note names it: "/usr/local/bin/kittystory"
    stays; "~/.kittystory/packs/x.pack" -> "~/.kittystory/packs/"."""
    if posixpath.dirname(path) == "/usr/local/bin":
        return path
    return posixpath.dirname(path) + "/"


def _make_folders(disk: Disk, real: Path) -> None:
    """The folders above a file, made inside the world only."""
    missing = []
    for parent in real.parents:
        if parent == disk.root or parent.is_dir():
            break
        missing.append(parent)
    for folder in reversed(missing):
        disk.place("/" + folder.relative_to(disk.root).as_posix())   # never under /.hallux
        folder.mkdir()


def _remove_empty_folders(disk: Disk, path: str, home: str | None) -> None:
    keep = KEPT_FOLDERS | ({home} if home else set())
    folder = posixpath.dirname(path)
    while folder not in keep and folder.count("/") > 1:
        real = disk.root / folder.lstrip("/")
        try:
            if real.is_symlink() or not real.is_dir() or any(real.iterdir()):
                return
            real.rmdir()
        except OSError:
            return
        folder = posixpath.dirname(folder)


def _apply_remove(plan: Plan, answers: dict[str, str], progress) -> Outcome:
    disk = plan.disk
    record = rec.load(disk)
    item = plan.items[0]
    entry = record[item.name]
    touched = {a.path: item.name for a in item.actions if _resolved(a, answers) == "remove"}
    backup = rec.make_backup(disk, item.name, touched, {item.name: entry},
                             {item.name: {"untagged": None}})
    removed = 0
    files = dict(entry["files"])
    why = None
    for action in item.actions:
        what = _resolved(action, answers)
        try:
            if what == "remove":
                disk.place(action.path).unlink(missing_ok=True)
                files.pop(action.path, None)
                _remove_empty_folders(disk, action.path, entry.get("home"))
                removed += 1
            elif what in ("keep", "skip"):
                files.pop(action.path, None)
        except OSError as e:
            why = f"{action.path}: {e.strerror or e}"
            break
    if why is not None:
        record[item.name] = {**entry, "files": files, "incomplete": True}
        rec.save(disk, record)
        result = Done(item.name, entry["version"], None, "failed", why, 0, removed)
    else:
        record.pop(item.name)                     # its seeds and data stay, as yours
        rec.save(disk, record)
        rec.remove_memory(disk, item.name)
        result = Done(item.name, entry["version"], None, "removed", "", 0, removed)
    if progress is not None:
        progress(result)
    return Outcome([result], backup.name)


# ---------------------------------------------------------------------- rolling back

def rollback(world: Path | str, name: str) -> Outcome:
    """Put back what the newest backup that holds the package has of it: its files as they
    were, the files its install added taken away, its record entry and its memory lines."""
    disk = Disk(world)
    found = [b for b in rec.backups(disk) if b.holds(name)]
    if not found:
        raise HpmError(f"there is no backup of {name} in this world to roll back to")
    backup = found[-1]
    record = rec.load(disk)
    restored = removed = 0
    for path, info in sorted(backup.data["files"].items()):
        if info["package"] != name:
            continue
        real = disk.place(path)
        if info["was"] == "there":
            _make_folders(disk, real)
            copy_whole(backup.folder / "files" / path.lstrip("/"), real)
            restored += 1
        elif real.is_file() and not real.is_symlink():
            real.unlink()
            _remove_empty_folders(disk, path, (record.get(name) or {}).get("home"))
            removed += 1
    before = backup.data["entries"].get(name)
    rec.remove_memory(disk, name)
    if before is None:
        record.pop(name, None)
    else:
        record[name] = before
        if before.get("memory_line") or before.get("rules"):
            rec.set_memory(disk, name, before["version"], before.get("memory_line", ""),
                           tuple(before.get("rules", ())))
    untagged = backup.data.get("memory", {}).get(name, {}).get("untagged")
    if untagged:
        rec.restore_line(disk, untagged)
    rec.save(disk, record)
    rec.mark_rolled_back(backup, name)
    version = before["version"] if before else None
    return Outcome([Done(name, version, None, "rolled back", backup.name, restored, removed)],
                   backup.name)
