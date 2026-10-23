"""The store on your PC, above every world (docs/hpm/hpm.md, section 4; the plan's
decision 3 and step 2).

    $HPM_HOME, else $XDG_DATA_HOME/hallux/hpm/, else ~/.local/share/hallux/hpm/
      config.toml                      the model, effort and cap for AI work (step 6)
      local/<name>/<version>.hpm       what you published yourself
      stores/<store>/index.toml        friends' stores (step 8)
      mine/<store>/                    a clone of your own store on GitHub (step 8)
      cache/<store>/<name>-<version>.hpm   downloads (step 8)

Folders are made when something is first written into them. A world can't see any of it.

A package is found in local/ and in every friend's store (hallux/hpm/remote.py): "local" is
your own store on the PC, any other name a friend's. A name in more than one is ambiguous,
and the caller asks which.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from hallux.disk import TEMP_MARK, copy_whole
from hallux.hpm.archive import ArchiveError, read_manifest
from hallux.hpm.manifest import NAME, Manifest, Version
from hallux.hpm.world import HpmError

SUFFIX = ".hpm"


def store_home(env: dict | None = None) -> Path:
    """Where the store is: $HPM_HOME, else $XDG_DATA_HOME/hallux/hpm, else
    ~/.local/share/hallux/hpm. HPM_HOME keeps the tests away from your real store."""
    env = os.environ if env is None else env
    if env.get("HPM_HOME"):
        return Path(env["HPM_HOME"]).expanduser()
    if env.get("XDG_DATA_HOME"):
        return Path(env["XDG_DATA_HOME"]).expanduser() / "hallux" / "hpm"
    return Path.home() / ".local" / "share" / "hallux" / "hpm"


@dataclass(frozen=True)
class Release:
    """One version of a package in the store."""
    name: str
    version: Version
    path: Path
    where: str = "local"                    # "local", or the friend's store it came from
    yanked: bool = False

    def manifest(self) -> Manifest:
        return read_manifest(self.path)


LOCAL = "local"


class Ambiguous(HpmError):
    """A package's name is in more than one store."""

    def __init__(self, name: str, places: list[str]) -> None:
        self.name, self.places = name, places
        super().__init__(f"{name} is in {' and '.join(places)}: name the one you mean, as "
                         + " or ".join(f"{p}/{name}" for p in places))


class Store:
    def __init__(self, home: Path | str | None = None) -> None:
        self.home = Path(home) if home is not None else store_home()
        self.local = self.home / "local"
        from hallux.hpm.remote import Remotes
        self.remotes = Remotes(self.home)

    def wheres(self) -> list[str]:
        """local, and every friend's store."""
        return [LOCAL] + self.remotes.names()

    def places(self, name: str) -> list[str]:
        """The stores that have a version of the package that isn't yanked."""
        return [where for where in self.wheres() if self.latest(name, where) is not None]

    def names(self, where: str = LOCAL) -> list[str]:
        """Every package with a release in a store (local/ unless named), sorted."""
        if where != LOCAL:
            return sorted(name for name in self.remotes.packages(where)
                          if self.latest(name, where) is not None)
        if not self.local.is_dir():
            return []
        return sorted(p.name for p in self.local.iterdir()
                      if p.is_dir() and NAME.fullmatch(p.name) and self.releases(p.name))

    def releases(self, name: str, where: str = LOCAL) -> list[Release]:
        """The releases of a package in a store, oldest first (in a friend's store yanked ones
        too). A file in a folder of local/ that isn't named <version>.hpm is an error that
        names it: the store is hpm's alone."""
        if where != LOCAL:
            return self.remotes.releases(where, name)
        folder = self.local / name
        if not folder.is_dir():
            return []
        found = []
        for path in folder.iterdir():
            if path.name.startswith(".") and TEMP_MARK in path.name:
                continue                          # a copy that is under way, or was cut short
            if not path.name.endswith(SUFFIX) or not path.is_file():
                raise HpmError(f"{path} doesn't belong in the store: it holds only "
                               f"<version>{SUFFIX} files")
            try:
                version = Version(path.name[:-len(SUFFIX)])
            except ValueError:
                raise HpmError(f"{path} doesn't belong in the store: {path.name[:-len(SUFFIX)]!r} "
                               f"is no version") from None
            found.append(Release(name, version, path))
        return sorted(found, key=lambda release: release.version)

    def latest(self, name: str, where: str = LOCAL) -> Release | None:
        """The newest release that isn't yanked."""
        releases = [r for r in self.releases(name, where) if not r.yanked]
        return releases[-1] if releases else None

    def find(self, name: str, where: str | None = None) -> Release | None:
        """The newest release of a package in a store; without one, in the one store that has
        it (local first if only it has). Ambiguous if several have it."""
        if where is not None:
            return self.latest(name, where)
        places = self.places(name)
        if len(places) > 1:
            raise Ambiguous(name, places)
        return self.latest(name, places[0]) if places else None

    def add(self, file: Path | str) -> Release:
        """Put a packed release into local/, under its manifest's name and version. A version
        that is there already (1.4.0 is 1.4) is refused, and so is one lower than the latest:
        a release is never changed, and versions only go up. The file appears whole or not
        at all; `file` itself stays where it is."""
        file = Path(file)
        try:
            manifest = read_manifest(file)
        except ArchiveError as e:
            raise HpmError(str(e)) from None
        latest = self.latest(manifest.name)
        if latest is not None and manifest.version == latest.version:
            raise HpmError(f"{manifest.name} {manifest.version} is in the store already "
                           f"(as {latest.version}); a release is never changed")
        if latest is not None and manifest.version < latest.version:
            raise HpmError(f"{manifest.name} {manifest.version} is lower than the store's "
                           f"latest, {latest.version}")
        target = self.local / manifest.name / f"{manifest.version}{SUFFIX}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise HpmError(f"{target} exists already")
        copy_whole(file, target)
        return Release(manifest.name, manifest.version, target)
