"""The hpm command (docs/hpm/hpm.md; the plan's steps 2 and 4).

    hpm install NAME… [--extras K,K|none] [--overwrite all|none] [--old-line replace|keep]
                      [--user U] [--yes] [--world W]
    hpm update [NAME…] [--overwrite …] [--old-line …] [--user U] [--yes] [--world W]
    hpm remove NAME [--data] [--overwrite all|none] [--world W]
    hpm rollback NAME [--world W]
    hpm adopt NAME [--version V] [--old-line …] [--user U] [--yes] [--world W]
    hpm list [--world W]
    hpm publish NAME [--all] [--version V | --yes] [--changelog TEXT] [--user U]
                     [--private yes|no] [--old-line replace|keep] [--world W]
    hpm show NAME
    hpm search WORD
    hpm backups --clean [--yes] [--world W]

A NAME is a package (kittystory), a package of a store (local/kittystory), a whole store
(local/, with the slash and nothing after it: bash would expand local/*), or a bundle.
Without --world, hpm works on the world you are in. Every question has a flag; without a
terminal a question whose flag is missing is an error that names it. install, update,
remove and rollback refuse a world that is running: use its Packages tab then.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hallux.disk import Disk
from hallux.hpm import engine
from hallux.hpm import record as rec
from hallux.hpm.archive import read_member
from hallux.hpm.engine import KEEP, OVERWRITE, REMOVE, REPLACE, SKIP, Plan, Want
from hallux.hpm.manifest import NAME, Version
from hallux.hpm.publish import Questions, publish, show
from hallux.hpm.store import Store
from hallux.hpm.world import HpmError, find_world, homes, refuse_running

FORMS = "a package (kittystory), local/kittystory, a whole store (local/), or a bundle"


# ---------------------------------------------------------------------- the screens

class TerminalScreens:
    """The full-screen questions, on your terminal."""

    def checkboxes(self, choices, title=""):
        from hallux.hpm.screens import Checkboxes
        return Checkboxes(choices, title).run()

    def pick(self, title, options):
        from hallux.hpm.screens import Pick
        return Pick(title, options).run()

    def conflicts(self, groups):
        from hallux.hpm.screens import Conflicts
        return Conflicts(groups).run()


# ---------------------------------------------------------------------- the command line

def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="hpm", description="the Hallux package manager: "
                                  "apps from one world into any other (docs/hpm/)")
    commands = cli.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def world(p):
        p.add_argument("--world", metavar="W", help="the world (else the one you are in)")

    def answers(p, extras=False):
        if extras:
            p.add_argument("--extras", metavar="K,K", help="the extras to install (none: "
                           "none of them), instead of the checkboxes")
        p.add_argument("--overwrite", choices=("all", "none"),
                       help="the answer to every file in the way (all: overwrite, or remove "
                            "what you changed; none: skip, or keep it)")
        p.add_argument("--old-line", choices=("replace", "keep"), dest="old_line",
                       help="the machine's own memory line about the program")
        p.add_argument("--user", metavar="U", help="whose home ~ is, in a world with several")
        p.add_argument("--yes", action="store_true",
                       help="the defaults, without the checkboxes; replace the old memory line")
        world(p)

    p = commands.add_parser("install", help="install packages into a world")
    p.add_argument("names", nargs="+", metavar="NAME")
    answers(p, extras=True)

    p = commands.add_parser("update", help="update packages (all with a newer version, "
                                           "without a name)")
    p.add_argument("names", nargs="*", metavar="NAME")
    answers(p)

    p = commands.add_parser("remove", help="remove a package; its data stays without --data")
    p.add_argument("name", metavar="NAME")
    p.add_argument("--data", action="store_true", help="its data too, after a backup")
    p.add_argument("--overwrite", choices=("all", "none"),
                   help="files you changed: all removes them, none keeps them")
    world(p)

    p = commands.add_parser("rollback", help="undo the last install, update or remove of a "
                                             "package")
    p.add_argument("name", metavar="NAME")
    world(p)

    p = commands.add_parser("adopt", help="record an app that was there before hpm")
    p.add_argument("name", metavar="NAME")
    p.add_argument("--version", metavar="V", help="the release to compare with (else the latest)")
    p.add_argument("--old-line", choices=("replace", "keep"), dest="old_line")
    p.add_argument("--user", metavar="U")
    p.add_argument("--yes", action="store_true", help="replace the old memory line")
    world(p)

    p = commands.add_parser("list", help="what a world has installed")
    world(p)

    p = commands.add_parser("publish", help="put a release of a package into the store")
    p.add_argument("name", metavar="NAME")
    p.add_argument("--all", action="store_true", help="its extras too, each that changed")
    p.add_argument("--version", metavar="V", help="the release's version (else asked)")
    p.add_argument("--yes", action="store_true",
                   help="the version hpm suggests for each, without asking")
    p.add_argument("--changelog", metavar="TEXT", help="the changelog entry (else $EDITOR)")
    p.add_argument("--user", metavar="U", help="whose home ~ is, in a world with several")
    p.add_argument("--private", choices=("yes", "no"),
                   help="the answer, if hpm asks whether to mark a package private")
    p.add_argument("--old-line", choices=("replace", "keep"), dest="old_line",
                   help="the machine's own memory line about the program, in this world")
    world(p)

    p = commands.add_parser("show", help="a package in the store: versions, files, changelog")
    p.add_argument("name", metavar="NAME")

    p = commands.add_parser("search", help="the store's packages whose name or summary has WORD")
    p.add_argument("word", metavar="WORD")

    p = commands.add_parser("backups", help="a world's backups")
    p.add_argument("--clean", action="store_true", help="remove them all, after a question")
    p.add_argument("--yes", action="store_true", help="without the question")
    world(p)
    return cli


def main(argv: list[str] | None = None, questions: Questions | None = None,
         store: Store | None = None, screens=None) -> int:
    flags = parser().parse_args(argv)
    run = Run(flags, questions or Questions(), store or Store(), screens or TerminalScreens())
    try:
        return getattr(run, flags.command)()
    except HpmError as e:
        print(f"hpm: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("hpm: stopped", file=sys.stderr)
        return 130


class Run:
    """One command: its flags, where it asks, and the store."""

    def __init__(self, flags, questions: Questions, store: Store, screens) -> None:
        self.flags, self.q, self.store, self.screens = flags, questions, store, screens

    @property
    def interactive(self) -> bool:
        return self.q.interactive

    def world(self) -> Path:
        return find_world(given=getattr(self.flags, "world", None))

    def say(self, text: str) -> None:
        self.q.say(text)

    # ------------------------------------------------------------------ install and update

    def install(self) -> int:
        world = self.world()
        refuse_running(world)
        wants = engine.expand(self.store, [self._want(name) for name in self.flags.names])
        wants = self._extras(world, wants)
        if wants is None:
            return self._cancelled()
        return self._install(world, wants)

    def update(self) -> int:
        world = self.world()
        refuse_running(world)
        record = rec.load(Disk(world))
        names = self.flags.names or sorted(record)
        wants = []
        for name in names:
            if name not in record:
                raise HpmError(f"{name} isn't installed in this world; hpm install it")
            latest = self.store.find(name)
            if latest is None:
                self.say(f"{name}: not in the store any more; left as it is")
                continue
            if latest.version > Version(record[name]["version"]) or record[name].get("incomplete"):
                manifest = latest.manifest()
                extras = tuple(k for k in record[name].get("extras", []) if k in manifest.extras)
                wants.append(Want(name, extras=extras))
            elif self.flags.names:
                self.say(f"{name} {record[name]['version']} is the newest")
        if not wants:
            self.say("everything is up to date")
            return 0
        if self.interactive and not self.flags.yes:
            wants = self._checkboxes(world, wants, record, title=f"{len(wants)} to update")
            if wants is None:
                return self._cancelled()
        return self._install(world, wants)

    def _want(self, name: str) -> Want:
        if "/" in name:
            where, _, rest = name.partition("/")
            if where != "local":
                raise HpmError(f"there is no store {where!r}: only local/ until friends' stores "
                               f"come (a NAME is {FORMS})")
            if not rest:
                return Want("local/")
            name = rest
        if not NAME.fullmatch(name):
            raise HpmError(f"{name!r} is no NAME: a NAME is {FORMS}")
        if self.store.find(name) is None:
            raise HpmError(f"there is no package {name} in the store (hpm search finds one)")
        return Want(name)

    def _extras(self, world: Path, wants: list[Want]) -> list[Want] | None:
        """The extras of each package: --extras, else the checkboxes, else (--yes) the
        defaults."""
        if self.flags.extras is not None:
            keys = [] if self.flags.extras == "none" else [k for k in self.flags.extras.split(",") if k]
            out, found = [], set()
            for want in wants:
                manifest = self.store.find(want.name).manifest()
                mine = tuple(k for k in keys if k in manifest.extras)
                found |= set(mine)
                out.append(Want(want.name, extras=mine, version=want.version))
            unknown = [k for k in keys if k not in found]
            if unknown:
                raise HpmError(f"no package here has the extra {', '.join(unknown)}")
            return out
        if self.flags.yes:
            return wants
        if not self.interactive:
            raise HpmError("which extras to install: there is no terminal for the checkboxes; "
                           "pass --extras K,K (or none), or --yes for the defaults")
        return self._checkboxes(world, wants, rec.load(Disk(world)))

    def _checkboxes(self, world: Path, wants: list[Want], record: dict,
                    title: str = "") -> list[Want] | None:
        from hallux.hpm.screens import Choice
        have, gets, _ = engine.addons_known(world)
        choices = []
        for want in wants:
            release = self.store.find(want.name)
            manifest = release.manifest()
            problems = engine.addon_problems(manifest, have, gets)
            notes = []
            if want.name in record:
                old = record[want.name]["version"]
                notes.append(f"installed {old} → {manifest.version}"
                             if Version(old) != manifest.version else "installed ✓")
            notes += [f"needs the {a} addon ✗" for a in manifest.requires_addons
                      if any(f"the {a} addon" in p for p in problems)]
            notes += [f"needs the {a} addon ✓" for a in manifest.requires_addons
                      if not any(f"the {a} addon" in p for p in problems)]
            labels = {}
            for key, extra in manifest.extras.items():
                other = self.store.find(extra.package)
                labels[key] = (other.manifest().summary or extra.package) if other else \
                    "(not in the store)"
            card = read_member(release.path, f"files/root/usr/local/bin/{want.name}")
            extras = ({k: k in want.extras for k in manifest.extras} if want.extras is not None
                      else {})
            choices.append(Choice(want.name, manifest, extras=extras, labels=labels,
                                  note=" · ".join(notes), bad=bool(problems),
                                  card=(card or b"").decode("utf-8", "replace").splitlines()))
        return self.screens.checkboxes(choices, title)

    def _user(self, world: Path) -> str | None:
        """--user, else the one user, else the user screen."""
        if self.flags.user or not self.interactive:
            return self.flags.user
        found = homes(Disk(world))
        if len(found) < 2:
            return None
        picked = self.screens.pick("This world has several users. Whose home is ~?",
                                   [home.rsplit("/", 1)[-1] for home in found])
        if picked is None:
            raise HpmError("cancelled; nothing was written")
        return picked

    def _install(self, world: Path, wants: list[Want]) -> int:
        plan = engine.plan_install(world, self.store, wants, user=self._user(world))
        return self._carry_out(plan)

    # ------------------------------------------------------------------ carrying a plan out

    def _carry_out(self, plan: Plan, answer_files: bool = True) -> int:
        try:
            for note in plan.notes:
                self.say(f"note: {note}")
            for name, path, why in plan.loud:
                self.say(f"!! {name}: {path + ': ' if path else ''}{why}")
            for item in plan.items:
                if item.blocked:
                    self.say(f"✗ {item.name}: {item.blocked}")
            answers = self._memory_answers(plan)
            if answer_files and plan.questions:
                files = self._file_answers(plan)
                if files is None:
                    return self._cancelled()
                answers |= files
            outcome = engine.apply(plan, answers, progress=self._progress)
        finally:
            plan.close()
        self.say(outcome.summary() + (f"  (backup: {outcome.backup})" if outcome.backup else ""))
        return 1 if outcome.count("failed") else 0

    def _memory_answers(self, plan: Plan) -> dict[str, str]:
        answers = {}
        for item in plan.memory_questions():
            key = f"memory:{item.name}"
            choice = getattr(self.flags, "old_line", None)
            if choice is not None:
                answers[key] = REPLACE if choice == "replace" else KEEP
            elif getattr(self.flags, "yes", False):
                answers[key] = REPLACE
            elif self.interactive:
                self.say(f"The machine's memory has its own line about {item.name}:\n"
                         f"  {item.old_line}")
                answers[key] = REPLACE if self.q.confirm(
                    "replace it with hpm's?", True, "--old-line replace|keep") else KEEP
            else:
                raise HpmError(f"the machine's memory has its own line about {item.name}: there "
                               f"is no terminal to ask whether to replace it; pass "
                               f"--old-line replace or keep, or --yes")
        return answers

    def _file_answers(self, plan: Plan) -> dict[str, str] | None:
        overwrite = getattr(self.flags, "overwrite", None)
        if overwrite is not None:
            wanted = (OVERWRITE, REMOVE) if overwrite == "all" else (SKIP, KEEP)
            return {q.path: next((c for c in wanted if c in q.choices), q.default)
                    for q in plan.questions}
        if not self.interactive:
            raise HpmError(f"{len(plan.questions)} file(s) are in the way, and there is no "
                           f"terminal to ask about them; pass --overwrite all or none")
        return self.screens.conflicts(plan.grouped())

    def _progress(self, done) -> None:
        sign = {"installed": "✓", "updated": "✓", "removed": "✓", "adopted": "✓",
                "failed": "✗", "skipped": "–"}.get(done.status, "·")
        version = f" {done.version}" if done.version else ""
        was = f" (was {done.was})" if done.was and done.status == "updated" else ""
        why = f": {done.why}" if done.why else ""
        files = f", {done.written} files" if done.written else ""
        self.say(f"  {sign} {done.name}{version} {done.status}{was}{files}{why}")

    def _cancelled(self) -> int:
        self.say("cancelled; nothing was written")
        return 1

    # ------------------------------------------------------------------ the other commands

    def remove(self) -> int:
        world = self.world()
        refuse_running(world)
        return self._carry_out(engine.plan_remove(world, self.flags.name, self.flags.data))

    def rollback(self) -> int:
        world = self.world()
        refuse_running(world)
        outcome = engine.rollback(world, self.flags.name)
        done = outcome.done[0]
        back = f"back to {done.version}" if done.version else "taken away: it wasn't installed before"
        self.say(f"{done.name} {back} ({done.written} files put back, {done.removed} taken away; "
                 f"backup {outcome.backup})")
        return 0

    def adopt(self) -> int:
        world = self.world()
        release = self.store.find(self.flags.name)
        if self.flags.version is not None:
            release = next((r for r in self.store.releases(self.flags.name)
                            if r.version == Version(self.flags.version)), None)
        if release is None:
            raise HpmError(f"the store has no {self.flags.name}"
                           + (f" {self.flags.version}" if self.flags.version else ""))
        plan = engine.plan_adopt(world, release, user=self._user(world))
        same = sum(1 for a in plan.items[0].actions if a.op == "record")
        other = sum(1 for a in plan.items[0].actions if a.op != "record")
        self.say(f"{release.name} {release.version}: {same} files are the release's, {other} "
                 f"aren't (they stay as they are, and an update asks about them)")
        return self._carry_out(plan, answer_files=False)

    def list(self) -> int:
        world = self.world()
        disk = Disk(world)
        record = rec.load(disk)
        if not record:
            self.say("nothing installed by hpm in this world")
        for name, entry in sorted(record.items()):
            latest = self.store.find(name)
            newer = f"  ↑ {latest.version} in the store" if latest and latest.version > Version(
                entry["version"]) else ""
            marks = [m for m in ("incomplete", "adopted") if entry.get(m)]
            extras = f"  extras: {', '.join(entry['extras'])}" if entry.get("extras") else ""
            self.say(f"{name} {entry['version']}{newer}{extras}"
                     + (f"  ({', '.join(marks)})" if marks else ""))
        backups = rec.backups(disk)
        if backups:
            from hallux.hpm.publish import _size
            self.say(f"backups: {len(backups)}, {_size(rec.backups_size(disk))} "
                     f"(hpm backups --clean removes them)")
        return 0

    def publish(self) -> int:
        world = self.world()
        released = publish(world, self.flags.name, self.store, self.q, every=self.flags.all,
                           version=self.flags.version, changelog=self.flags.changelog,
                           user=self.flags.user, suggested=self.flags.yes,
                           private=None if self.flags.private is None else self.flags.private == "yes")
        for release in released:                  # the world it came from has it now
            plan = engine.plan_adopt(world, release, user=self.flags.user)
            if plan.memory_questions() and not (self.interactive or self.flags.yes
                                                or self.flags.old_line):
                plan.items[0].old_line = None     # not asked, so not changed: told instead
                self.say(f"note: the machine's own line about {release.name} stays beside "
                         f"hpm's; hpm adopt {release.name} --old-line replace takes it out")
            self._carry_out(plan, answer_files=False)
        return 0

    def show(self) -> int:
        self.say(show(self.store, self.flags.name))
        return 0

    def search(self) -> int:
        word = self.flags.word.lower()
        found = 0
        for name in self.store.names():
            manifest = self.store.find(name).manifest()
            if word in name.lower() or word in manifest.summary.lower():
                self.say(f"{name} {manifest.version}  {manifest.summary}")
                found += 1
        if not found:
            self.say(f"nothing in the store has {self.flags.word!r} in its name or summary")
        return 0

    def backups(self) -> int:
        world = self.world()
        disk = Disk(world)
        found = rec.backups(disk)
        from hallux.hpm.publish import _size
        if not self.flags.clean:
            for backup in found:
                self.say(f"{backup.name}  {', '.join(backup.data['packages'])}")
            self.say(f"{len(found)} backups, {_size(rec.backups_size(disk))}")
            return 0
        if not found:
            self.say("there are no backups")
            return 0
        if not self.flags.yes and not self.q.confirm(
                f"remove all {len(found)} backups ({_size(rec.backups_size(disk))})? "
                f"hpm rollback can't go back past them then", False, "--yes"):
            return self._cancelled()
        self.say(f"removed {rec.clean_backups(disk)} backups")
        return 0
