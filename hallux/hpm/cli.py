"""The hpm command (docs/hpm/hpm.md; the plan's steps 2 and 4).

    hpm install NAME… [--extras K,K|none] [--overwrite all|none] [--old-line replace|keep]
                      [--user U] [--yes] [--accept-migration] [--world W]
    hpm update [NAME…] [--overwrite …] [--old-line …] [--user U] [--yes]
                       [--accept-migration] [--world W]
    hpm remove NAME [--data] [--overwrite all|none] [--world W]
    hpm rollback NAME [--world W]
    hpm adopt NAME [--version V] [--old-line …] [--user U] [--yes] [--world W]
    hpm list [--world W]
    hpm publish NAME [--all] [--version V | --yes] [--changelog TEXT] [--user U]
                     [--private yes|no] [--seeds release|world] [--old-line replace|keep]
                     [--draft] [--review]
                     [--write-migration] [--test] [--world W]
    hpm init NAME [--yes] [--user U] [--world W]          the AI drafts the manifest
    hpm show NAME
    hpm search WORD
    hpm backups --clean [--yes] [--world W]
    hpm store init NAME --repo OWNER/REPO     your store on GitHub (gh and git)
    hpm store add NAME ADDRESS                a friend's: https://github.com/<owner>/<repo>
    hpm store list | remove NAME | refresh [NAME]
    hpm push NAME… [--all] [--store S] [--review] [--yes]     to your store on GitHub
    hpm yank NAME VERSION [--store S]
    hpm config [set KEY VALUE | path]         ~/.config/hallux/hpm.toml: store, editor, color

A NAME is a package (kittystory), a package of a store (local/kittystory, danika/kittystory),
a whole store (local/ or danika/, with the slash and nothing after it: bash would expand
danika/*), or a bundle. local is your own store on this PC; any other is a friend's
(docs/hpm/sharing.md). A name that is in two stores is asked about.
Without --world, hpm works on the world you are in. Every question has a flag; without a
terminal a question whose flag is missing is an error that names it. install, update,
remove and rollback refuse a world that is running: use its Packages tab then.

Data in an older format is migrated before the new version is installed
(docs/hpm/migrations.md): the AI's plan, then its migration into a staging folder, then the
checks, and you accept. Without a terminal, --accept-migration lets it run and accepts it
only if every check held.
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
from hallux.hpm.paint import enabled as paint_on
from hallux.hpm.paint import paint, span
from hallux.hpm.publish import Questions, publish, show
from hallux.hpm.store import LOCAL, Ambiguous, Store
from hallux.hpm.world import HpmError, find_world, homes, refuse_running

FORMS = ("a package (kittystory), one of a store (local/kittystory, danika/kittystory), a "
         "whole store (local/), or a bundle")


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
        p.add_argument("--accept-migration", action="store_true", dest="accept_migration",
                       help="data in an older format: let the AI migrate it, and accept the "
                            "migration if every check held (on a terminal hpm asks)")
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
    p.add_argument("--seeds", choices=("release", "world"),
                   help="a seed with no clean copy that changed since the last release: keep "
                        "the release's, or send this world's")
    p.add_argument("--old-line", choices=("replace", "keep"), dest="old_line",
                   help="the machine's own memory line about the program, in this world")
    p.add_argument("--draft", action="store_true",
                   help="the AI drafts the changelog entry (on a terminal hpm asks)")
    p.add_argument("--review", action="store_true",
                   help="the AI reviews the card (on a terminal hpm asks)")
    p.add_argument("--write-migration", action="store_true", dest="write_migration",
                   help="the data moved: the AI writes the migration note (on a terminal hpm "
                        "asks)")
    p.add_argument("--test", action="store_true",
                   help="install it into a copy of the base world and try it once (it asks)")
    world(p)

    p = commands.add_parser("init", help="the AI drafts a program's manifest, and its extras'")
    p.add_argument("name", metavar="NAME")
    p.add_argument("--yes", action="store_true", help="let the AI, without the question")
    p.add_argument("--user", metavar="U", help="whose home ~ is, in a world with several")
    world(p)

    p = commands.add_parser("show", help="a package in the store: versions, files, changelog")
    p.add_argument("name", metavar="NAME")

    p = commands.add_parser("search", help="the store's packages whose name or summary has WORD")
    p.add_argument("word", metavar="WORD")

    p = commands.add_parser("backups", help="a world's backups")
    p.add_argument("--clean", action="store_true", help="remove them all, after a question")
    p.add_argument("--yes", action="store_true", help="without the question")
    world(p)

    p = commands.add_parser("store", help="stores on GitHub: yours, and your friends'")
    stores = p.add_subparsers(dest="action", required=True, metavar="ACTION")
    q = stores.add_parser("init", help="make your store on GitHub (with gh), and its clone")
    q.add_argument("name", metavar="NAME")
    q.add_argument("--repo", metavar="OWNER/REPO", required=True,
                   help="the repository to make, like danika/hpm-store")
    q = stores.add_parser("add", help="add a friend's store")
    q.add_argument("name", metavar="NAME")
    q.add_argument("address", metavar="ADDRESS", help="https://github.com/<owner>/<repo>")
    stores.add_parser("list", help="the stores you have added, and your own")
    q = stores.add_parser("remove", help="remove a friend's store, and its downloads")
    q.add_argument("name", metavar="NAME")
    q = stores.add_parser("refresh", help="download the stores' indexes again")
    q.add_argument("name", metavar="NAME", nargs="?")

    p = commands.add_parser("push", help="send releases to your store on GitHub")
    p.add_argument("names", nargs="*", metavar="NAME")
    p.add_argument("--all", action="store_true", help="every package newer than in the store")
    p.add_argument("--store", metavar="S", help="which of your stores (if you have several)")
    p.add_argument("--review", action="store_true",
                   help="have the AI review a card that has no review yet (it asks on a "
                        "terminal)")
    p.add_argument("--yes", action="store_true", help="push even if the review found something")
    world(p)

    p = commands.add_parser("yank", help="mark a pushed version so nobody gets it by default")
    p.add_argument("name", metavar="NAME")
    p.add_argument("version", metavar="VERSION")
    p.add_argument("--store", metavar="S", help="which of your stores (if you have several)")

    p = commands.add_parser("config", help="hpm's settings: ~/.config/hallux/hpm.toml")
    p.add_argument("action", nargs="?", metavar="set|path",
                   help="nothing: every setting and where it came from; set KEY VALUE; path")
    p.add_argument("key", nargs="?", metavar="KEY", help="store, editor or color")
    p.add_argument("value", nargs="?", metavar="VALUE")
    return cli


def main(argv: list[str] | None = None, questions: Questions | None = None,
         store: Store | None = None, screens=None, client_factory=None) -> int:
    flags = parser().parse_args(argv)
    try:                                       # a wrong config file is an error like any other
        run = Run(flags, questions or Questions(), store, screens or TerminalScreens(),
                  client_factory)
        return getattr(run, {"store": "stores"}.get(flags.command, flags.command))()
    except HpmError as e:
        print(paint(f"hpm: {e}", "error", on=paint_on(sys.stderr)), file=sys.stderr)
        if flags.command in ("search", "show", "install", "update", "adopt"):
            note = empty_store_note(store)
            if note:
                print(paint(note, "note", on=paint_on(sys.stderr)), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(paint("hpm: stopped", "error", on=paint_on(sys.stderr)), file=sys.stderr)
        return 130


class Run:
    """One command: its flags, where it asks, and the store."""

    def __init__(self, flags, questions: Questions, store: Store, screens,
                 client_factory=None) -> None:
        self.flags, self.q, self._store, self.screens = flags, questions, store, screens
        self.client_factory = client_factory          # the AI's; the tests give a stand-in

    @property
    def store(self) -> Store:
        """The store, made when a command first needs it: `hpm config` must work even when
        the config file points at a folder that isn't there, to fix it."""
        if self._store is None:
            self._store = Store()
        return self._store

    @property
    def interactive(self) -> bool:
        return self.q.interactive

    @property
    def color(self) -> bool:
        """Colors on, for the pieces of a listing (docs/plans/hpm/colors/)."""
        return getattr(self.q, "color", False)

    def world(self) -> Path:
        return find_world(given=getattr(self.flags, "world", None))

    def say(self, text: str, kind: str | None = None) -> None:
        self.q.say(text, kind=kind)

    # ------------------------------------------------------------------ install and update

    def install(self) -> int:
        world = self.world()
        refuse_running(world)
        self.store.remotes.refresh_stale(self.say)
        wants = engine.expand(self.store, [self._want(name) for name in self.flags.names])
        wants = self._extras(world, wants)
        if wants is None:
            return self._cancelled()
        return self._install(world, wants)

    def update(self) -> int:
        world = self.world()
        refuse_running(world)
        record = rec.load(Disk(world))
        self.store.remotes.refresh_stale(self.say)
        names = self.flags.names or sorted(record)
        wants = []
        for name in names:
            if name not in record:
                raise HpmError(f"{name} isn't installed in this world; hpm install it")
            where = record[name].get("from") or LOCAL
            try:
                latest = self.store.find(name, where)
            except HpmError as e:                 # its store was removed, or can't be read
                self.say(f"{name}: {e}; left as it is")
                continue
            if latest is None:
                self.say(f"{name}: not in the store {where} any more; left as it is")
                continue
            if latest.version > Version(record[name]["version"]) or record[name].get("incomplete"):
                manifest = latest.manifest()
                extras = tuple(k for k in record[name].get("extras", []) if k in manifest.extras)
                wants.append(Want(name, extras=extras, store=where))
            elif self.flags.names:
                self.say(f"{name} {record[name]['version']} is the newest", kind="ok")
        if not wants:
            self.say("everything is up to date", kind="ok")
            return 0
        if self.interactive and not self.flags.yes:
            wants = self._checkboxes(world, wants, record, title=f"{len(wants)} to update")
            if wants is None:
                return self._cancelled()
        return self._install(world, wants)

    def _want(self, name: str) -> Want:
        """A NAME as a Want, with its store: the one named, the one that has it, or the one
        picked on the screen when several have it."""
        where = None
        if "/" in name:
            where, _, rest = name.partition("/")
            if where not in self.store.wheres():
                raise HpmError(f"there is no store {where!r} (hpm store list; a NAME is {FORMS})")
            if not rest:
                return Want(f"{where}/")
            name = rest
        if not NAME.fullmatch(name):
            raise HpmError(f"{name!r} is no NAME: a NAME is {FORMS}")
        try:
            release = self.store.find(name, where)
        except Ambiguous as e:
            if not self.interactive:
                raise
            picked = self.screens.pick(f"{name} is in several stores. Which one?", e.places)
            if picked is None:
                raise HpmError("cancelled; nothing was written") from None
            return Want(name, store=picked)
        if release is None:
            raise HpmError(f"there is no package {name} in "
                           + (f"the store {where}" if where else "the store")
                           + " (hpm search WORD lists the packages it has)")
        return Want(name, store=release.where)

    def _extras(self, world: Path, wants: list[Want]) -> list[Want] | None:
        """The extras of each package: --extras, else the checkboxes, else (--yes) the
        defaults."""
        if self.flags.extras is not None:
            keys = [] if self.flags.extras == "none" else [k for k in self.flags.extras.split(",") if k]
            out, found = [], set()
            for want in wants:
                manifest = engine._release(self.store, want).manifest()
                mine = tuple(k for k in keys if k in manifest.extras)
                found |= set(mine)
                out.append(Want(want.name, extras=mine, version=want.version, store=want.store))
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
            release = engine._release(self.store, want)
            manifest = release.manifest()
            problems = engine.addon_problems(manifest, have, gets)
            notes = []
            if want.name in record:
                old = record[want.name]["version"]
                notes.append(f"installed {old} → {manifest.version}"
                             if Version(old) != manifest.version else "installed ✓")
                there = record[want.name].get("data_format")
                if there is not None and there < manifest.data_format:
                    notes.append(f"data {there} → {manifest.data_format}, with the AI")
            notes += [f"needs the {a} addon ✗" for a in manifest.requires_addons
                      if any(f"the {a} addon" in p for p in problems)]
            notes += [f"needs the {a} addon ✓" for a in manifest.requires_addons
                      if not any(f"the {a} addon" in p for p in problems)]
            labels = {}
            for key, extra in manifest.extras.items():
                other = (self.store.find(extra.package, release.where)
                         or self.store.find(extra.package, LOCAL))
                labels[key] = (other.manifest().summary or extra.package) if other else \
                    "(not in the store)"
            card = read_member(release.path, f"files/root/usr/local/bin/{want.name}")
            review = (read_member(release.path, "review.md") or b"").decode("utf-8", "replace")
            extras = ({k: k in want.extras for k in manifest.extras} if want.extras is not None
                      else {})
            shown = want.name if release.where == LOCAL else f"{release.where}/{want.name}"
            choices.append(Choice(shown, manifest, extras=extras, labels=labels,
                                  note=" · ".join(notes), bad=bool(problems),
                                  card=(card or b"").decode("utf-8", "replace").splitlines(),
                                  review=review.splitlines()))
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
        """The plan's questions, its migrations and the write: data coming in is migrated
        first (in a temporary folder), then every question is asked, then the world's data
        is migrated, and only then is anything installed."""
        from hallux.hpm.migrate import Shared
        shared = Shared()
        try:
            for note in plan.notes:
                self.say(f"note: {note}")
            for name, path, why in plan.loud:
                self.say(f"!! {name}: {path + ': ' if path else ''}{why}")
            for item in plan.items:
                if item.blocked:
                    self.say(f"✗ {item.name}: {item.blocked}")
            for item in plan.incomings():
                self._migrate(plan, item, shared, incoming=True)
            answers, merged = self._memory_answers(plan), {}
            if answer_files and plan.questions:
                files = self._file_answers(plan)
                if files is None:
                    return self._cancelled()
                merged = self._merges(plan, files)
                answers |= files
            if plan.migrations():
                for item in plan.migrations():
                    self._migrate(plan, item, shared)
                more = [q for q in plan.questions if q.path not in answers]
                if more and answer_files:         # a migrated package walked again
                    files = self._file_answers(plan, more)
                    if files is None:
                        self.say("!! cancelled after the migration: the data is in its new "
                                 "format and the old version is still installed; hpm update "
                                 "installs the new one, hpm rollback puts the data back")
                        return 1
                    answers |= files
            outcome = engine.apply(plan, answers, progress=self._progress, merged=merged,
                                   backup=shared.backup)
        finally:
            plan.close()
        kind = "fail" if outcome.count("failed") else ("ok" if outcome.done else "plain")
        self.say(outcome.summary() + (f"  (backup: {outcome.backup})" if outcome.backup else ""),
                 kind=kind)
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
                         f"  {item.old_line}", kind="ask")
                answers[key] = REPLACE if self.q.confirm(
                    "replace it with hpm's?", True, "--old-line replace|keep") else KEEP
            else:
                raise HpmError(f"the machine's memory has its own line about {item.name}: there "
                               f"is no terminal to ask whether to replace it; pass "
                               f"--old-line replace or keep, or --yes")
        return answers

    def _file_answers(self, plan: Plan, only=None) -> dict[str, str] | None:
        questions = plan.questions if only is None else only
        overwrite = getattr(self.flags, "overwrite", None)
        if overwrite is not None:
            wanted = (OVERWRITE, REMOVE) if overwrite == "all" else (SKIP, KEEP)
            return {q.path: next((c for c in wanted if c in q.choices), q.default)
                    for q in questions}
        if not self.interactive:
            raise HpmError(f"{len(questions)} file(s) are in the way, and there is no "
                           f"terminal to ask about them; pass --overwrite all or none")
        groups = plan.grouped()
        if only is not None:
            paths = {q.path for q in only}
            groups = {k: [q for q in qs if q.path in paths] for k, qs in groups.items()}
            groups = {k: qs for k, qs in groups.items() if qs}
        return self.screens.conflicts(groups)

    def _migrate(self, plan: Plan, item, shared, incoming: bool = False) -> None:
        """One package's migration, on the terminal: the AI's plan of each note (Enter goes
        on, q cancels), its migration into the staging folder, the checks, and then Enter
        accepts, r rolls back, l looks first. A package whose migration doesn't land is left
        out of the install, and what needs it too."""
        from hallux.hpm import ai, assist, migrate
        pending = item.incoming if incoming else item.migrate
        start, end = pending.notes[0].old, pending.notes[-1].new
        what = f"{item.name}'s data" + (" coming in" if incoming else "")
        given = getattr(self.flags, "accept_migration", False)
        self.say(f"{what} is in format {start}, and {item.name} {item.release.version} needs "
                 f"{end}: it is migrated first ({', '.join(n.name for n in pending.notes)})")
        settings = ai.settings(self.store)
        if not assist.may_spend(self.q, f"migrate {what} {start} → {end}", settings,
                                plan.disk.root, "--accept-migration", given):
            if not self.interactive:
                raise HpmError(f"{what} has to be migrated {start} → {end} by the AI, and there "
                               f"is no terminal to ask; pass --accept-migration (it accepts "
                               f"only if every check holds). Nothing was written")
            item.skip = "its data wasn't migrated, so nothing of it was written"
            return
        ask = self.interactive and not given
        m = migrate.Migration(plan, item, self.store, incoming=incoming, shared=shared,
                              client_factory=self.client_factory)
        try:
            while m.state == migrate.PLANNING:
                self.say(f"the AI plans the migration ({m.note.name})…")
                m.plan_rows()
                self.say("\n".join(m.plan_lines()))
                if ask and self.q.choose("Enter migrate · q cancel (nothing changes)", "q",
                                         "--accept-migration") == "q":
                    m.cancel()
                    item.skip = "you cancelled its migration; nothing of it was written"
                    return
                self.say("the AI migrates, into a staging folder…")
                m.migrate()
            self.say("\n".join(m.checked_lines()))
            if ask:
                while True:
                    answer = self.q.choose("Enter accept (the old paths go, the backup stays) "
                                           "· r roll back · l look first", "rl",
                                           "--accept-migration")
                    if answer != "l":
                        break
                    self.say("\n".join(m.look_lines()))
                if answer == "r":
                    m.cancel()
                    item.skip = "you rolled its migration back; nothing of it was written"
                    return
            elif not m.held:
                m.cancel()
                item.skip = ("a check of its migration didn't hold, and --accept-migration "
                             "accepts only when every one does; nothing of it was written")
                return
            m.accept()
            self.say(f"✓ {what}: {m.landed} files in, {m.removed} old ones out; format {end} "
                     f"(the AI's part ~${m.spent:.4f})")
        except HpmError as e:
            if m.state not in (migrate.ACCEPTED, migrate.CANCELLED) and not m.landed:
                m.cancel()
            item.skip = f"its migration failed: {e}"
            self.say(f"✗ {item.name}: {e} (the AI's part ~${m.spent:.4f})")
        except BaseException:
            if m.state not in (migrate.ACCEPTED, migrate.CANCELLED) and not m.landed:
                m.cancel()
            raise

    def _merges(self, plan: Plan, answers: dict[str, str]) -> dict[str, str]:
        """Each file answered with merge, merged by the AI and shown; written only on yes.
        A merge that fails, or isn't wanted after all, is skipped."""
        from hallux.hpm import assist
        merged = {}
        for q in plan.questions:
            if answers.get(q.path) != engine.MERGE:
                continue
            ours = Disk(plan.disk.root).place(q.path).read_text(encoding="utf-8", errors="replace")
            theirs = q.source.read_text(encoding="utf-8", errors="replace")
            self.say(f"the AI is merging {q.path}…")
            text, answer = assist.merge(plan.disk.root, self.store, q.path, ours, theirs,
                                        client_factory=self.client_factory)
            self.say(f"the merge cost ~${answer.cost_usd:.4f}")
            if text is None:
                self.say(f"{q.path} is skipped: {answer.why or 'the merge failed'}")
                answers[q.path] = SKIP
                continue
            self.say(f"--- {q.path}, merged\n{text.rstrip()}\n---", kind="dim")
            if self.q.confirm(f"write the merged {q.path.rsplit('/', 1)[-1]}?", True,
                              "a terminal: merge is chosen on the screen"):
                merged[q.path] = text
            else:
                answers[q.path] = SKIP
        return merged

    def _progress(self, done) -> None:
        sign = {"installed": "✓", "updated": "✓", "removed": "✓", "adopted": "✓",
                "failed": "✗", "skipped": "–"}.get(done.status, "·")
        version = f" {done.version}" if done.version else ""
        was = f" (was {done.was})" if done.was and done.status == "updated" else ""
        why = f": {done.why}" if done.why else ""
        files = f", {done.written} files" if done.written else ""
        self.say(f"  {sign} {done.name}{version} {done.status}{was}{files}{why}")

    def _cancelled(self) -> int:
        self.say("cancelled; nothing was written", kind="warning")
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
                 f"backup {outcome.backup})", kind="ok")
        return 0

    def adopt(self) -> int:
        world = self.world()
        want = self._want(self.flags.name)
        release = self.store.find(want.name, want.store)
        if self.flags.version is not None:
            release = next((r for r in self.store.releases(want.name, want.store or LOCAL)
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
            where = entry.get("from") or LOCAL
            try:
                latest = self.store.find(name, where)
            except HpmError:
                latest = None
            on = self.color
            newer = span(f"  ↑ {latest.version} in the store", "cyan", on) \
                if latest and latest.version > Version(entry["version"]) else ""
            newer += span(f"  (from {where})", "dim", on) if where != LOCAL else ""
            marks = [span(m, "red" if m == "incomplete" else "dim", on)
                     for m in ("incomplete", "adopted") if entry.get(m)]
            extras = f"  extras: {', '.join(entry['extras'])}" if entry.get("extras") else ""
            self.say(f"{span(name, 'bold', on)} {entry['version']}{newer}{extras}"
                     + (f"  ({', '.join(marks)})" if marks else ""))
        backups = rec.backups(disk)
        if backups:
            from hallux.hpm.publish import _size
            self.say(span(f"backups: {len(backups)}, {_size(rec.backups_size(disk))} "
                          f"(hpm backups --clean removes them)", "dim", self.color))
        return 0

    def init(self) -> int:
        from hallux.hpm import assist
        world = self.world()
        written = assist.init(world, self.store, self.flags.name, self.q, yes=self.flags.yes,
                              user=self.flags.user, client_factory=self.client_factory)
        self.say(f"kept: {', '.join(written)}. Next: hpm publish {self.flags.name} --all",
                 kind="ok")
        return 0

    def publish(self) -> int:
        from hallux.hpm import assist
        world = self.world()
        draft = assist.changelog_drafter(world, self.store, self.q, given=self.flags.draft,
                                         client_factory=self.client_factory)
        review = assist.card_reviewer(world, self.store, self.q, given=self.flags.review,
                                      client_factory=self.client_factory)
        write_note = assist.note_writer(world, self.store, self.q,
                                        given=self.flags.write_migration,
                                        client_factory=self.client_factory)
        released = publish(world, self.flags.name, self.store, self.q, every=self.flags.all,
                           version=self.flags.version, changelog=self.flags.changelog,
                           user=self.flags.user, suggested=self.flags.yes, draft=draft,
                           review=review, write_note=write_note, seeds=self.flags.seeds,
                           private=None if self.flags.private is None else self.flags.private == "yes")
        for release in released:                  # the world it came from has it now
            plan = engine.plan_adopt(world, release, user=self.flags.user)
            if plan.memory_questions() and not (self.interactive or self.flags.yes
                                                or self.flags.old_line):
                plan.items[0].old_line = None     # not asked, so not changed: told instead
                self.say(f"note: the machine's own line about {release.name} stays beside "
                         f"hpm's; hpm adopt {release.name} --old-line replace takes it out")
            self._carry_out(plan, answer_files=False)
        app = next((r for r in released if r.name == self.flags.name), None)
        if app is not None and (self.flags.test or (self.interactive and self.q.confirm(
                f"try {app.name} {app.version} in a copy of the base world (a boot and one "
                f"line, with the AI)?", False, "--test"))):
            assist.test_install(self.store, app, self.q, client_factory=self.client_factory)
        return 0

    def show(self) -> int:
        self.say(show(self.store, self.flags.name, on=self.color))
        return 0

    def search(self) -> int:
        word = self.flags.word.lower()
        found = 0
        self.store.remotes.refresh_stale(self.say)
        for name in self.store.names():
            manifest = self.store.latest(name).manifest()
            if word in name.lower() or word in manifest.summary.lower():
                self.say(f"{span(name, 'bold', self.color)} {manifest.version}  {manifest.summary}")
                found += 1
        for where in self.store.remotes.names():          # from the index: nothing downloaded
            for name, entry in sorted(self.store.remotes.packages(where).items()):
                latest = self.store.latest(name, where)
                summary = entry.get("summary", "")
                if latest and (word in name.lower() or word in summary.lower()):
                    self.say(f"{span(where + '/', 'dim', self.color)}{span(name, 'bold', self.color)} "
                             f"{latest.version}  {summary}")
                    found += 1
        if not found:
            self.say(f"nothing in the store has {self.flags.word!r} in its name or summary")
            note = empty_store_note(self.store)
            if note:
                self.say(note)
        return 0

    def backups(self) -> int:
        world = self.world()
        disk = Disk(world)
        found = rec.backups(disk)
        from hallux.hpm.publish import _size
        if not self.flags.clean:
            for backup in found:
                self.say(f"{backup.name}  "
                         + span(', '.join(backup.data['packages']), "bold", self.color))
            self.say(span(f"{len(found)} backups, {_size(rec.backups_size(disk))}", "dim",
                          self.color))
            return 0
        if not found:
            self.say("there are no backups")
            return 0
        if not self.flags.yes and not self.q.confirm(
                f"remove all {len(found)} backups ({_size(rec.backups_size(disk))})? "
                f"hpm rollback can't go back past them then", False, "--yes"):
            return self._cancelled()
        self.say(f"removed {rec.clean_backups(disk)} backups", kind="ok")
        return 0

    # ------------------------------------------------------------------ the config file

    def config(self) -> int:
        """hpm config: every setting, its value, where it came from; set KEY VALUE; path."""
        from hallux.hpm import config as cfg
        action = self.flags.action
        if action == "path":
            self.say(str(cfg.config_path()))
            return 0
        if action == "set":
            if not self.flags.key or self.flags.value is None:
                raise HpmError("hpm config set KEY VALUE (the keys: "
                               + ", ".join(cfg.KEYS) + ")")
            path, value = cfg.set_value(self.flags.key, self.flags.value)
            self.say(f"✓ {self.flags.key} = {cfg._quoted(value)} in {_tilde(path)}")
            return 0
        if action is not None:
            raise HpmError(f"hpm config has no {action!r}: hpm config, hpm config set KEY "
                           f"VALUE, hpm config path")
        path = cfg.config_path()
        there = "" if path.exists() else span("  (not there yet: hpm config set makes it)",
                                              "dim", self.color)
        self.say(f"{'file':<8}{_tilde(path)}{there}")
        for key, value, source, from_env in cfg.explain():
            shown = span(f"{value:<28}", "cyan", self.color) if from_env else f"{value:<28}"
            self.say(f"{key:<8}{shown} {span(source, 'dim', self.color)}")
        return 0

    # ------------------------------------------------------------------ stores on GitHub

    def stores(self) -> int:
        """hpm store: the store is self.store, so the command is this."""
        from hallux.hpm import remote
        action, remotes = self.flags.action, self.store.remotes
        if action == "init":
            mine = remote.Mine(self.store.home, self.flags.name)
            mine.init(self.flags.repo)
            self.say(f"made your store {self.flags.name}: {mine.address}, its clone in "
                     f"{mine.folder}. hpm push NAME sends a package there; a friend adds it "
                     f"with:\n  hpm store add {self.flags.name} {mine.address}", kind="ok")
        elif action == "add":
            added = remotes.add(self.flags.name, self.flags.address)
            count = len(added.index.get("packages", {}))
            self.say(f"added the store {added.name} ({count} package{'s' * (count != 1)}): "
                     f"hpm install {added.name}/<package>, or {added.name}/ for all of them",
                     kind="ok")
        elif action == "list":
            for name in remote.Mine.names(self.store.home):
                self.say(f"{span(name, 'bold', self.color)}  yours: "
                         f"{remote.Mine(self.store.home, name).address}")
            for name in remotes.names():
                found = remotes.get(name)
                count = len(found.index.get("packages", {}))
                self.say(f"{span(name, 'bold', self.color)}  {found.source.get('url')}  "
                         f"{count} package{'s' * (count != 1)}"
                         + span(f", index from {found.source.get('fetched')}", "dim", self.color))
            if not remotes.names() and not remote.Mine.names(self.store.home):
                self.say("no stores yet: hpm store add NAME ADDRESS adds a friend's, hpm store "
                         "init NAME --repo OWNER/REPO makes yours")
        elif action == "remove":
            remotes.remove(self.flags.name)
            self.say(f"removed the store {self.flags.name} and its downloads; what you "
                     f"installed from it stays installed", kind="ok")
        elif action == "refresh":
            for name in [self.flags.name] if self.flags.name else remotes.names():
                found = remotes.refresh(name)
                self.say(f"{name}: {len(found.index.get('packages', {}))} packages")
        return 0

    def _mine(self):
        from hallux.hpm import remote
        names = remote.Mine.names(self.store.home)
        if not names:
            raise HpmError("you have no store on GitHub yet: hpm store init NAME --repo "
                           "OWNER/REPO makes one")
        name = self.flags.store or (names[0] if len(names) == 1 else None)
        if name is None:
            raise HpmError(f"you have several stores ({', '.join(names)}): pass --store")
        if name not in names:
            raise HpmError(f"you have no store {name} (yours: {', '.join(names)})")
        return remote.Mine(self.store.home, name)

    def push(self) -> int:
        """sharing.md, section 2: the newest release of each, private ones refused, the
        review shown, a GitHub release, and the index committed and pushed."""
        import tempfile

        from hallux.hpm import assist
        from hallux.hpm.publish import _entries
        mine = self._mine()
        mine.pull()
        index = mine.index()
        packages = index.setdefault("packages", {})
        if not self.flags.names and not self.flags.all:
            raise HpmError("name the packages to push, or --all")
        names = self.flags.names or self.store.names()
        chosen = []
        for name in names:
            release = self.store.latest(name)
            if release is None:
                raise HpmError(f"there is no {name} in your store on this PC: hpm publish it "
                               f"first")
            manifest = release.manifest()
            pushed = packages.get(name, {}).get("versions", {})
            if manifest.private:
                if self.flags.all:
                    self.say(f"– {name}: private, it never leaves this PC")
                    continue
                raise HpmError(f"{name} is private (its memories or chat stay on this PC): hpm "
                               f"push never sends it")
            if str(release.version) in pushed:
                if self.flags.all:
                    continue
                raise HpmError(f"{name} {release.version} is in {mine.name} already; a pushed "
                               f"version never changes (publish a newer one)")
            if self.flags.all and pushed and max(map(Version, pushed)) > release.version:
                continue
            chosen.append((release, manifest))
        if not chosen:
            self.say(f"nothing to push: {mine.name} has every release already")
            return 0
        going = {r.name for r, _ in chosen}
        for release, manifest in chosen:
            for extra in manifest.extras.values():
                if extra.package not in going and extra.package not in packages:
                    self.say(f"note: {release.name}'s extra {extra.package} isn't in "
                             f"{mine.name}; a friend can't tick it until you push it too")
        try:
            world = self.world()
        except HpmError:
            world = None
        reviewer = assist.card_reviewer(world, self.store, self.q, given=self.flags.review,
                                        client_factory=self.client_factory) if world else None
        reviews = {}
        for release, manifest in chosen:
            reviews[release.name] = self._push_review(release, manifest, reviewer, world)
        for release, manifest in chosen:
            name, version = release.name, str(release.version)
            changelog = (read_member(release.path, "CHANGELOG.md") or b"").decode("utf-8", "replace")
            notes = (_entries(changelog) or [f"{name} {version}"])[0]
            if reviews[name]:
                notes += "\n\nThe AI's review of the card:\n" + reviews[name]
            with tempfile.TemporaryDirectory(prefix="hpm-push-") as temp:
                file = Path(temp) / f"{name}-{version}.hpm"
                file.write_bytes(release.path.read_bytes())
                url = mine.release(f"{name}-{version}", file, f"{name} {version}", notes)
            entry = packages.setdefault(name, {})
            entry["summary"] = manifest.summary
            versions = entry.setdefault("versions", {})
            versions[version] = {
                "url": url, "sha256": sha_hex(release.path), "data_format": manifest.data_format,
                "requires": {"addons": list(manifest.requires_addons)},
                "extras": [e.package for e in manifest.extras.values()]}
            entry["latest"] = _latest(versions)
            mine.save_index(index)
            mine.commit(f"push {name} {version}", ["index.toml"])
            self.say(f"✓ pushed {name} {version} to {mine.name}")
        self.say(f"a friend adds the store with:\n  hpm store add {mine.name} {mine.address}\n"
                 f"GitHub may show the old index for a few minutes after a push.")
        return 0

    def _push_review(self, release, manifest, reviewer, world) -> str:
        """The card's review: the one made at publish, else the AI's now if it may. Shown;
        if it found something, push only on yes (--yes)."""
        name = release.name
        card = read_member(release.path, f"files/root/usr/local/bin/{name}")
        said = read_member(release.path, "review.md")
        text = said.decode("utf-8", "replace").strip() if said else ""
        if not text and card is not None:
            text = (reviewer(name, card.decode("utf-8", "replace"),
                             (read_member(release.path, "hpm.toml") or b"").decode()) or "").strip() \
                if reviewer else ""
            if not text:
                self.say(f"note: {name} {release.version}'s card has no review"
                         + ("" if world else " (hpm push in a world, with --review, has the AI "
                                             "make one)"))
        elif text:
            self.say(f"the review of {name}'s card, made at publish:\n{text}")
        if text and not _clean(text):
            if self.flags.yes:
                return text
            if not self.interactive:
                raise HpmError(f"the review of {name}'s card found something (above): pass "
                               f"--yes to push it anyway")
            if not self.q.confirm(f"the review found something; push {name} {release.version} "
                                  f"anyway?", False, "--yes"):
                raise HpmError(f"{name} isn't pushed; nothing was")
        return text

    def yank(self) -> int:
        mine = self._mine()
        mine.pull()
        index = mine.index()
        versions = index.get("packages", {}).get(self.flags.name, {}).get("versions", {})
        version = next((v for v in versions if Version(v) == Version(self.flags.version)), None)
        if version is None:
            raise HpmError(f"{mine.name} has no {self.flags.name} {self.flags.version}")
        versions[version]["yanked"] = True
        entry = index["packages"][self.flags.name]
        latest = _latest(versions)
        if latest:
            entry["latest"] = latest
        else:
            entry.pop("latest", None)
        mine.save_index(index)
        mine.commit(f"yank {self.flags.name} {version}", ["index.toml"])
        self.say(f"yanked {self.flags.name} {version} in {mine.name}: nobody gets it by "
                 f"default any more; the newest is "
                 + (f"{latest}" if latest else "none (every version is yanked)"), kind="ok")
        return 0


def _latest(versions: dict) -> str:
    """The newest version that isn't yanked, or ""."""
    live = [v for v, info in versions.items() if not info.get("yanked")]
    return str(max(map(Version, live))) if live else ""


def _clean(review: str) -> bool:
    """A review that found nothing."""
    lines = [line.strip("- ").strip().lower() for line in review.splitlines() if line.strip()]
    return lines == ["nothing reaches beyond the program"]


def _tilde(path: Path) -> str:
    """A path as the user types it: ~ for the home."""
    home = str(Path.home())
    text = str(path)
    return "~" + text[len(home):] if text == home or text.startswith(home + "/") else text


def empty_store_note(store: Store | None) -> str | None:
    """When the store is empty and nothing says where it is: where hpm looked, and how to
    point it elsewhere. None otherwise (or when the store can't be found at all)."""
    import os
    from hallux.hpm import config as cfg
    try:
        if os.environ.get("HPM_HOME") or cfg.load().store is not None:
            return None
        store = store or Store()
        if store.names() or store.remotes.names():
            return None
    except HpmError:
        return None
    return (f"note: the store at {_tilde(store.home)} is empty. If yours is elsewhere: "
            f"hpm config set store PATH")


def sha_hex(path: Path) -> str:
    from hallux.hpm.archive import sha256
    return sha256(path).split(":", 1)[1]
