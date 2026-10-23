"""hpm in a running world: the engine in a thread for the panel's Packages tab, and the notes
the machine is told of in <installed> (docs/hpm/hpm.md, sections 9 and 10; the plan's step 5
and decision 19).

Built as the Files tab's Imports is (hallux/importing.py). Everything is called in the
event loop, as the panel calls it. A plan and a write work in a daemon thread of their own,
so the panel stays alive, and so does an answer of the AI that runs; what they end with
comes back into the loop, and `changed` has the terminal draw the tab again.

The AI takes no part. It learns of what was written in front of its next message, as
<installed>, and from its memory's tagged line at the next boot.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Callable

from hallux.disk import Disk
from hallux.hpm import engine
from hallux.hpm import record as rec
from hallux.hpm.archive import read_member
from hallux.hpm.engine import Done, Outcome, Plan, Want
from hallux.hpm.manifest import Manifest, Version
from hallux.hpm.store import Release, Store
from hallux.hpm.world import HpmError

log = logging.getLogger("hallux")

LISTING, PLANNING, ASKING, WRITING, DONE, FAILED = (
    "listing", "planning", "asking", "writing", "done", "failed")
NOTES_MAX = 20                                # notes kept for the AI, at most
CLOSE_SECONDS = 2.0


@dataclass(frozen=True)
class Entry:
    """One package of the store, as the tab lists it."""
    name: str
    release: Release
    manifest: Manifest
    installed: str | None = None              # the version this world has, if any
    problems: tuple[str, ...] = ()            # missing addons, in words
    labels: dict[str, str] = field(default_factory=dict)    # an extra's key: what it is
    card: tuple[str, ...] = ()

    @property
    def newer(self) -> bool:
        return self.installed is not None and self.manifest.version > Version(self.installed)


@dataclass(frozen=True)
class Seen:
    """What the tab shows, as it is at one moment."""
    state: str
    doing: str = ""                           # "install" or "remove"
    plan: Plan | None = None                  # in ASKING
    progress: tuple[Done, ...] = ()           # in WRITING and DONE
    outcome: Outcome | None = None            # in DONE
    error: str | None = None                  # in FAILED


class Installs:
    def __init__(self, disk: Disk, store: Store | None = None,
                 changed: Callable[[], None] | None = None) -> None:
        self.disk = disk
        self.store = store or Store()
        self.changed = changed or (lambda: None)
        self._state = LISTING
        self._doing = ""
        self._plan: Plan | None = None
        self._outcome: Outcome | None = None
        self._error: str | None = None
        self._progress: list[Done] = []
        self._lock = threading.Lock()         # for what a thread reports
        self._stop: threading.Event | None = None
        self._threads: list[threading.Thread] = []
        self._notes: tuple[dict, ...] = ()    # for the AI, oldest first
        self._catalog: list[Entry] | None = None

    # ------------------------------------------------------------------ what the tab is shown

    def watch(self) -> Seen:
        with self._lock:
            progress = tuple(self._progress)
        return Seen(self._state, self._doing, self._plan, progress, self._outcome, self._error)

    def catalog(self, fresh: bool = False) -> list[Entry]:
        """The store's packages: each app and bundle, with its extras under it (an extra of
        another package isn't a row of its own, unless its app isn't in the store). Read once,
        and again when `fresh` or after a write. An HpmError says what is wrong with the store."""
        if self._catalog is not None and not fresh:
            return self._catalog
        record = rec.load(self.disk)
        have, gets, _ = engine.addons_known(self.disk.root)
        manifests = {}
        for name in self.store.names():
            release = self.store.latest(name)
            manifests[name] = (release, release.manifest())
        extras = {e.package: m.name for _, m in manifests.values() for e in m.extras.values()}
        entries = []
        for name, (release, manifest) in manifests.items():
            if extras.get(name) in manifests:
                continue                          # it is shown under its app
            labels = {}
            for key, extra in manifest.extras.items():
                found = manifests.get(extra.package)
                labels[key] = (found[1].summary or extra.package) if found else "(not in the store)"
            card = read_member(release.path, f"files/root/usr/local/bin/{name}") or b""
            entries.append(Entry(name, release, manifest, record.get(name, {}).get("version"),
                                 tuple(engine.addon_problems(manifest, have, gets)), labels,
                                 tuple(card.decode("utf-8", "replace").splitlines())))
        self._catalog = entries
        return entries

    def installed(self) -> dict:
        return rec.load(self.disk)

    # ------------------------------------------------------------------ what the tab asks for

    def plan_install(self, wants: list[Want]) -> None:
        """Work out what installing these would do, in a thread; then ASKING."""
        self._begin("install", PLANNING,
                    lambda stop: engine.plan_install(self.disk.root, self.store, wants),
                    self._planned)

    def plan_remove(self, name: str, data: bool = False) -> None:
        self._begin("remove", PLANNING,
                    lambda stop: engine.plan_remove(self.disk.root, name, data), self._planned)

    def go(self, answers: dict[str, str]) -> None:
        """Carry the plan out with these answers, in a thread; then DONE."""
        plan = self._plan
        if self._state != ASKING or plan is None:
            return
        self._plan = None

        def write(stop: threading.Event) -> Outcome:
            return engine.apply(plan, answers, progress=self._told_progress, stop=stop)

        self._begin(self._doing, WRITING, write, self._written)

    def stop(self) -> None:
        """Stop the write between two packages; a plan that is being worked out is dropped."""
        if self._stop is not None:
            self._stop.set()

    def back(self) -> None:
        """Back to the list: a plan that was shown is dropped, an outcome or error forgotten.
        Not while something runs."""
        if self._state in (PLANNING, WRITING):
            return
        if self._plan is not None:
            self._plan.close()
        self._plan, self._outcome, self._error, self._state = None, None, None, LISTING

    # ------------------------------------------------------------------ what the AI is told

    def waiting(self) -> tuple[dict, ...]:
        return self._notes

    def told(self, notes) -> None:
        self._notes = tuple(note for note in self._notes if not any(note is n for n in notes))

    def forget(self) -> None:
        """A boot starts: its session reads the memory, where the tagged lines are."""
        self._notes = ()

    def close(self) -> None:
        """Hallux ends: stop between packages, and wait a little for the thread."""
        self.stop()
        for thread in self._threads:
            thread.join(CLOSE_SECONDS)
        if self._plan is not None:
            self._plan.close()

    # ------------------------------------------------------------------ the threads

    def _told_progress(self, done: Done) -> None:            # in the thread
        with self._lock:
            self._progress.append(done)
        self._ask(self.changed)

    def _ask(self, function: Callable, *args: object) -> None:
        try:
            self._loop.call_soon_threadsafe(function, *args)
        except RuntimeError:                  # the loop is closed: Hallux is off
            pass

    def _begin(self, doing: str, state: str, work: Callable[[threading.Event], object],
               landed: Callable[[object], None]) -> None:
        """Do `work` in a thread; what it returns goes to `landed` in the loop, and an
        HpmError it raises makes the state FAILED, with its words."""
        if self._state in (PLANNING, WRITING):
            return
        self._loop = asyncio.get_running_loop()
        stop = threading.Event()
        self._stop, self._doing, self._state, self._error = stop, doing, state, None
        if state == PLANNING:
            with self._lock:
                self._progress = []

        def land(outcome: object) -> None:            # in the loop
            if isinstance(outcome, BaseException):
                self._state, self._error = FAILED, str(outcome)
            else:
                landed(outcome)
            self.changed()

        def body() -> None:                           # the thread
            try:
                outcome = work(stop)
            except HpmError as e:
                outcome = e
            except Exception as e:                    # a mistake in here: the log has it
                log.exception("hpm's thread failed")
                outcome = HpmError(f"{type(e).__name__}: {e}")
            self._ask(land, outcome)

        thread = threading.Thread(target=body, name="hallux-hpm", daemon=True)
        self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        thread.start()

    def _planned(self, plan: Plan) -> None:
        if self._stop is not None and self._stop.is_set():
            plan.close()                              # Esc while it was worked out
            self._state = LISTING
            return
        self._plan, self._state = plan, ASKING

    def _written(self, outcome: Outcome) -> None:
        self._outcome, self._state = outcome, DONE
        self._catalog = None                          # the installed versions changed
        self._notes = (*self._notes, *outcome.notes)[-NOTES_MAX:]
        log.info("hpm %s: %s", self._doing, outcome.summary())
