"""Stores on GitHub, for sharing with friends (docs/hpm/sharing.md; the plan's decision 18 and
step 8).

A store you share is a public GitHub repository with an `index.toml`; each version's archive
is a file of a GitHub release of it. There is no server.

    stores/<name>/index.toml        a friend's store, as it was last downloaded
    stores/<name>/source.toml       where it comes from: owner, repo, branch, when
    mine/<name>/                    a clone of your own store, which push changes
    mine/<name>.toml                its owner and repository
    cache/<name>/<package>-<version>.hpm    a friend's archive, checked against the index

Reading a friend's store needs nothing but HTTPS (urllib): GitHub's API for the repository's
default branch, then the raw index. Making your store and pushing to it go through `gh` and
`git`, which you sign into yourself; hpm never asks for a token. The tests put folders in
place of GitHub (GITHUB, API and RAW are file:// addresses there) and stand-ins for the two
commands (run_command).
"""
from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from hallux.disk import write_whole
from hallux.hpm.archive import ArchiveError, read_manifest, sha256
from hallux.hpm.manifest import NAME, Version
from hallux.hpm.world import HpmError

GITHUB = "https://github.com"
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
TIMEOUT = 20                                  # seconds, for each download
INDEX_MAX = 4 * 1024 * 1024
ARCHIVE_MAX = 256 * 1024 * 1024
STALE = datetime.timedelta(hours=1)
RESERVED = {"local"}                          # your own store on the PC
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}")
INDEX, SOURCE = "index.toml", "source.toml"


# ---------------------------------------------------------------------- TOML, written by hpm

def _key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key)


def _value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_value(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"hpm writes no {type(value).__name__} into TOML")


def write_toml(data: dict) -> str:
    """The few kinds of values hpm's own files hold: text, whole numbers, true and false,
    lists of them, and tables. A table of tables gets a header; a table of plain values that
    sits under a key named in INLINE is written in one line. Read back with tomllib, and an
    error if it doesn't come back the same."""
    lines: list[str] = []

    def table(path: list[str], body: dict) -> None:
        plain = {k: v for k, v in body.items() if not _is_table(k, v)}
        tables = {k: v for k, v in body.items() if _is_table(k, v)}
        if path and (plain or not tables):
            lines.append("")
            lines.append("[" + ".".join(_key(p) for p in path) + "]")
        for k, v in plain.items():
            lines.append(f"{_key(k)} = {_value(v)}")
        for k, v in tables.items():
            table(path + [k], v)

    table([], data)
    text = "\n".join(lines).lstrip("\n") + "\n"
    if tomllib.loads(text) != data:
        raise HpmError("hpm wrote TOML that doesn't read back as it was meant (a bug)")
    return text


INLINE = {"requires"}


def _is_table(key: str, value) -> bool:
    return isinstance(value, dict) and key not in INLINE


# ---------------------------------------------------------------------- downloads

def _allowed(url: str) -> bool:
    return url.startswith(("https://", GITHUB + "/", API + "/", RAW + "/"))


def fetch(url: str, limit: int = INDEX_MAX) -> bytes:
    """A download over HTTPS, at most `limit` bytes, with a time limit. Errors in words: not
    there or private, not reachable."""
    if not _allowed(url):
        raise HpmError(f"{url}: hpm downloads only over https://")
    request = urllib.request.Request(url, headers={"User-Agent": "hpm (Hallux)"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            data = answer.read(limit + 1)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise HpmError(f"{url}: GitHub says {e.code} ({e.reason}). The store isn't there, "
                           f"or it is private: hpm reads public stores only for now") from None
        raise HpmError(f"{url}: GitHub answered {e.code} ({e.reason})") from None
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(e, urllib.error.URLError) and url.startswith("file:") and \
                isinstance(reason, FileNotFoundError):
            raise HpmError(f"{url}: not found. The store isn't there, or it is private: hpm "
                           f"reads public stores only for now") from None
        raise HpmError(f"{url} can't be reached ({reason}); is the network up?") from None
    if len(data) > limit:
        raise HpmError(f"{url} is bigger than {limit // (1024 * 1024)} MB")
    return data


def repository(url: str) -> tuple[str, str]:
    """(owner, repo) of a repository's address as the browser shows it."""
    base = GITHUB.rstrip("/") + "/"
    rest = url.strip()
    if not rest.startswith(base):
        raise HpmError(f"{url!r} isn't a GitHub repository's address; it looks like "
                       f"{GITHUB}/<owner>/<repo>")
    rest = rest[len(base):].strip("/")
    rest = rest[:-4] if rest.endswith(".git") else rest
    if not REPO.fullmatch(rest):
        raise HpmError(f"{url!r} isn't a GitHub repository's address; it looks like "
                       f"{GITHUB}/<owner>/<repo>")
    owner, repo = rest.split("/")
    return owner, repo


def check_index(data: dict, where: str) -> dict:
    """An index, checked enough to be used: its packages, each version's address and sum."""
    packages = data.get("packages", {})
    if not isinstance(packages, dict):
        raise HpmError(f"{where}: packages must be a table")
    for name, entry in packages.items():
        if not NAME.fullmatch(name) or not isinstance(entry, dict):
            raise HpmError(f"{where}: {name!r} isn't a package's name")
        versions = entry.get("versions", {})
        if not isinstance(versions, dict):
            raise HpmError(f"{where}: {name}'s versions must be a table")
        for version, info in versions.items():
            try:
                Version(version)
            except ValueError:
                raise HpmError(f"{where}: {name} {version!r} is no version") from None
            if not (isinstance(info, dict) and isinstance(info.get("url"), str)
                    and _allowed(info["url"]) and isinstance(info.get("sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", info["sha256"])):
                raise HpmError(f"{where}: {name} {version} needs an https url and a sha256")
    return data


def read_index(text: str | bytes, where: str) -> dict:
    try:
        data = tomllib.loads(text.decode("utf-8") if isinstance(text, bytes) else text)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise HpmError(f"{where} isn't an index hpm can read: {e}") from None
    return check_index(data, where)


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------- a friend's release

class RemoteRelease:
    """A version of a package in a friend's store. Its archive is downloaded the first time
    its path is wanted, into cache/, and its sha256 must be the index's, every time; so must
    its name and version. A file that isn't is deleted and refused."""

    def __init__(self, name: str, version: Version, where: str, url: str, sha: str,
                 cache: Path, yanked: bool = False, summary: str = "") -> None:
        self.name, self.version, self.where = name, version, where
        self.url, self.sha, self.cache, self.yanked = url, sha, cache, yanked
        self.summary = summary

    def __repr__(self) -> str:
        return f"RemoteRelease({self.where}/{self.name} {self.version})"

    def __eq__(self, other) -> bool:
        return isinstance(other, RemoteRelease) and (self.name, self.version, self.where) == (
            other.name, other.version, other.where)

    def __hash__(self) -> int:
        return hash((self.name, self.version, self.where))

    @property
    def fetched(self) -> bool:
        return self.cache.is_file()

    @property
    def path(self) -> Path:
        if self.cache.is_file() and sha256(self.cache) == f"sha256:{self.sha}":
            return self.cache
        self.cache.unlink(missing_ok=True)
        data = fetch(self.url, ARCHIVE_MAX)
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        write_whole(self.cache, data)
        if sha256(self.cache) != f"sha256:{self.sha}":
            self.cache.unlink()
            raise HpmError(f"{self.where}/{self.name} {self.version}: the archive isn't the one "
                           f"the index names (its sha256 differs); refused and deleted")
        try:
            manifest = read_manifest(self.cache)
        except ArchiveError as e:
            self.cache.unlink()
            raise HpmError(f"{self.where}/{self.name} {self.version}: {e}") from None
        if manifest.name != self.name or manifest.version != self.version:
            self.cache.unlink()
            raise HpmError(f"{self.where}/{self.name} {self.version}: the archive holds "
                           f"{manifest.name} {manifest.version}; refused")
        return self.cache

    def manifest(self):
        return read_manifest(self.path)


# ---------------------------------------------------------------------- friends' stores

@dataclass
class Remote:
    """One friend's store, as added."""
    name: str
    folder: Path
    source: dict                              # owner, repo, branch, url, fetched
    index: dict

    @property
    def stale(self) -> bool:
        try:
            when = datetime.datetime.fromisoformat(self.source.get("fetched", ""))
        except ValueError:
            return True
        return datetime.datetime.now() - when > STALE


class Remotes:
    """The friends' stores of a store on the PC (stores/), and your own clones (mine/)."""

    def __init__(self, home: Path) -> None:
        self.home = Path(home)
        self.stores = self.home / "stores"
        self.mine = self.home / "mine"
        self.cache = self.home / "cache"

    def names(self) -> list[str]:
        if not self.stores.is_dir():
            return []
        return sorted(p.name for p in self.stores.iterdir()
                      if p.is_dir() and (p / INDEX).is_file() and (p / SOURCE).is_file())

    def get(self, name: str) -> Remote:
        folder = self.stores / name
        if name not in self.names():
            raise HpmError(f"there is no store {name!r} (hpm store list; hpm store add "
                           f"{name} <address> adds one)")
        where = str(folder / INDEX)
        index = read_index((folder / INDEX).read_bytes(), where)
        try:
            source = tomllib.loads((folder / SOURCE).read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as e:
            raise HpmError(f"{folder / SOURCE} can't be read: {e}") from None
        return Remote(name, folder, source, index)

    # adding, refreshing, removing
    def add(self, name: str, url: str) -> Remote:
        if not NAME.fullmatch(name) or name in RESERVED:
            raise HpmError(f"{name!r} can't be a store's name: letters, digits and -, not "
                           f"'local' (that is your own store on this PC)")
        if (self.stores / name).exists():
            raise HpmError(f"there is a store {name} already; hpm store remove {name} first")
        owner, repo = repository(url)
        return self._download(name, {"owner": owner, "repo": repo, "url": url})

    def refresh(self, name: str) -> Remote:
        return self._download(name, dict(self.get(name).source))

    def refresh_stale(self, say) -> None:
        """Every store whose index is older than an hour, downloaded again; one that can't be
        is used as it was, and said so."""
        for name in self.names():
            try:
                if self.get(name).stale:
                    self.refresh(name)
            except HpmError as e:
                say(f"note: the store {name} couldn't be refreshed, its index is as it was: {e}")

    def _download(self, name: str, source: dict) -> Remote:
        owner, repo = source["owner"], source["repo"]
        about = fetch(f"{API}/repos/{owner}/{repo}")
        try:
            branch = json.loads(about)["default_branch"]
        except (ValueError, KeyError, TypeError):
            raise HpmError(f"GitHub's answer about {owner}/{repo} has no default branch") from None
        if not isinstance(branch, str) or not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", branch):
            raise HpmError(f"{owner}/{repo}: {branch!r} is no branch hpm can use")
        address = f"{RAW}/{owner}/{repo}/{branch}/{INDEX}"
        text = fetch(address)
        index = read_index(text, address)
        folder = self.stores / name
        folder.mkdir(parents=True, exist_ok=True)
        write_whole(folder / INDEX, text)
        source = {**source, "branch": branch, "fetched": now()}
        write_whole(folder / SOURCE, write_toml(source))
        return Remote(name, folder, source, index)

    def remove(self, name: str) -> None:
        self.get(name)
        shutil.rmtree(self.stores / name)
        shutil.rmtree(self.cache / name, ignore_errors=True)

    # what a store has
    def releases(self, store: str, name: str) -> list[RemoteRelease]:
        """Every version of a package in a friend's store, oldest first, yanked ones too."""
        entry = self.get(store).index.get("packages", {}).get(name)
        if not entry:
            return []
        out = []
        for version, info in entry.get("versions", {}).items():
            out.append(RemoteRelease(name, Version(version), store, info["url"], info["sha256"],
                                     self.cache / store / f"{name}-{version}.hpm",
                                     bool(info.get("yanked")), entry.get("summary", "")))
        return sorted(out, key=lambda r: r.version)

    def packages(self, store: str) -> dict[str, dict]:
        return dict(self.get(store).index.get("packages", {}))


# ---------------------------------------------------------------------- the commands

def run_command(argv: list[str], cwd: Path | None = None) -> str:
    """`gh` or `git`, with its output; an error with what it said if it fails."""
    if shutil.which(argv[0]) is None:
        how = {"gh": "GitHub's command line: https://cli.github.com, then gh auth login",
               "git": "git: your system's package manager has it"}.get(argv[0], argv[0])
        raise HpmError(f"{argv[0]} isn't installed; hpm needs it for this. Install {how}")
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise HpmError(f"{' '.join(argv[:3])} took more than 10 minutes; stopped") from None
    if done.returncode != 0:
        said = (done.stderr or done.stdout).strip().splitlines()[-3:]
        raise HpmError(f"{' '.join(argv[:3])} failed: " + " / ".join(said))
    return done.stdout


def empty_index(name: str) -> dict:
    return {"store": name, "updated": now(), "packages": {}}


def readme(name: str, owner: str, repo: str) -> str:
    return (f"# {name}: a store of Hallux packages\n\n"
            f"Packages for Hallux, put here by hpm. To add this store:\n\n"
            f"    hpm store add {name} {GITHUB}/{owner}/{repo}\n\n"
            f"Then `hpm install {name}/<package>`. The archives are this repository's "
            f"releases; `index.toml` lists them with their sha256. hpm writes both: don't edit "
            f"them by hand.\n")


class Mine:
    """Your own store on GitHub, through its clone in mine/<name>/."""

    def __init__(self, home: Path, name: str) -> None:
        self.home, self.name = Path(home), name
        self.folder = Path(home) / "mine" / name
        self.about = Path(home) / "mine" / f"{name}.toml"

    @staticmethod
    def names(home: Path) -> list[str]:
        folder = Path(home) / "mine"
        if not folder.is_dir():
            return []
        return sorted(p.stem for p in folder.glob("*.toml") if (folder / p.stem).is_dir())

    @property
    def repo(self) -> tuple[str, str]:
        try:
            about = tomllib.loads(self.about.read_text(encoding="utf-8"))
            return about["owner"], about["repo"]
        except (OSError, tomllib.TOMLDecodeError, KeyError):
            raise HpmError(f"{self.about} can't be read: it says which repository the store "
                           f"{self.name} is (hpm store init made it)") from None

    @property
    def address(self) -> str:
        owner, repo = self.repo
        return f"{GITHUB}/{owner}/{repo}"

    def init(self, slug: str) -> None:
        if not NAME.fullmatch(self.name) or self.name in RESERVED:
            raise HpmError(f"{self.name!r} can't be a store's name: letters, digits and -, "
                           f"not 'local'")
        if not REPO.fullmatch(slug):
            raise HpmError(f"--repo {slug!r} must be OWNER/REPO, like danika/hpm-store")
        if self.folder.exists() or self.about.exists():
            raise HpmError(f"you have a store {self.name} already, in {self.folder}")
        owner, repo = slug.split("/")
        run_command(["gh", "repo", "create", slug, "--public",
                     "--description", f"hpm store {self.name}: Hallux packages"])
        self.folder.parent.mkdir(parents=True, exist_ok=True)
        run_command(["gh", "repo", "clone", slug, str(self.folder)])
        write_whole(self.about, write_toml({"owner": owner, "repo": repo}))
        write_whole(self.folder / INDEX, write_toml(empty_index(self.name)))
        write_whole(self.folder / "README.md", readme(self.name, owner, repo))
        self.commit(f"hpm store {self.name}", ["README.md", INDEX], first=True)

    def index(self) -> dict:
        if not (self.folder / INDEX).is_file():
            raise HpmError(f"{self.folder} has no {INDEX}: is it hpm's clone of your store?")
        return read_index((self.folder / INDEX).read_bytes(), str(self.folder / INDEX))

    def pull(self) -> None:
        run_command(["git", "-C", str(self.folder), "pull", "--ff-only"])

    def save_index(self, index: dict) -> None:
        index["updated"] = now()
        write_whole(self.folder / INDEX, write_toml(index))

    def commit(self, message: str, files: list[str], first: bool = False) -> None:
        git = ["git", "-C", str(self.folder)]
        run_command(git + ["add", *files])
        run_command(git + ["commit", "-m", message])
        run_command(git + (["push", "-u", "origin", "HEAD"] if first else ["push"]))

    def release(self, tag: str, file: Path, title: str, notes: str) -> str:
        """A GitHub release with the archive; returns the archive's download address."""
        owner, repo = self.repo
        run_command(["gh", "release", "create", tag, str(file), "--repo", f"{owner}/{repo}",
                     "--title", title, "--notes", notes])
        return f"{GITHUB}/{owner}/{repo}/releases/download/{tag}/{file.name}"
