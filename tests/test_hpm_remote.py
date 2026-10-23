"""Stores on GitHub (hallux/hpm/remote.py; docs/hpm/sharing.md; the plan's step 8). No network:
a folder stands in for GitHub (its web, API and raw addresses are file:// ones), and `gh`
and `git` are a stand-in that records what it was asked and does what GitHub would."""
import json
import shutil
import tomllib
from pathlib import Path

import pytest

from hallux.disk import Disk
from hallux.hpm import cli, remote
from hallux.hpm import record as rec
from hallux.hpm.archive import pack
from hallux.hpm.publish import Questions
from hallux.hpm.store import Ambiguous, Store
from hallux.hpm.world import HpmError

APP = '''name = "kittystory"
version = "{version}"
summary = "Chat with characters"
memory_line = "kittystory: chat with characters"
requires.addons = ["web"]
[files]
app = ["/usr/local/bin/kittystory"]
[extras]
packs = {{ package = "kittystory-packs", default = true }}
'''
PACKS = '''name = "kittystory-packs"
version = "{version}"
summary = "3 packs"
for = "kittystory"
[files]
data = ["~/.kittystory/packs/*.pack"]
'''
MEMORIES = '''name = "kittystory-memories"
version = "{version}"
for = "kittystory"
private = true
[files]
data = ["~/.kittystory/chars/*/memory.md"]
'''


class GitHub:
    """GitHub, as a folder: repositories with their default branch, what was pushed to them
    (raw/), and their releases (web/…/releases/download/)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.asked: list[list[str]] = []
        self.origins: dict[str, str] = {}             # a clone's folder: owner/repo

    def run(self, argv, cwd=None):
        self.asked.append(list(argv))
        if argv[:3] == ["gh", "repo", "create"]:
            slug = argv[3]
            api = self.root / "api/repos" / slug
            api.parent.mkdir(parents=True, exist_ok=True)
            api.write_text(json.dumps({"default_branch": "main", "private": False}))
        elif argv[:3] == ["gh", "repo", "clone"]:
            Path(argv[4]).mkdir(parents=True)
            self.origins[argv[4]] = argv[3]
        elif argv[:3] == ["gh", "release", "create"]:
            tag, file, slug = argv[3], Path(argv[4]), argv[argv.index("--repo") + 1]
            target = self.root / "web" / slug / "releases/download" / tag / file.name
            if target.exists():
                raise HpmError(f"gh release create failed: a release {tag} exists already")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(file, target)
        elif argv[0] == "git" and argv[3] == "push":
            folder = argv[2]
            raw = self.root / "raw" / self.origins[folder] / "main"
            raw.mkdir(parents=True, exist_ok=True)
            for name in ("index.toml", "README.md"):
                if (Path(folder) / name).exists():
                    shutil.copy(Path(folder) / name, raw / name)
        return ""

    def commands(self, word):
        return [a for a in self.asked if word in a]


@pytest.fixture
def github(tmp_path, monkeypatch):
    hub = GitHub(tmp_path / "github")
    monkeypatch.setattr(remote, "GITHUB", f"file://{tmp_path}/github/web")
    monkeypatch.setattr(remote, "API", f"file://{tmp_path}/github/api")
    monkeypatch.setattr(remote, "RAW", f"file://{tmp_path}/github/raw")
    monkeypatch.setattr(remote, "run_command", hub.run)
    monkeypatch.chdir(tmp_path)                           # no world around: push finds none
    return hub


def put(store, tmp_path, manifest, files, version="1.0", review=None):
    text = manifest.format(version=version)
    name = text.split('"')[1]
    folder = tmp_path / "pkgs" / store.home.name / f"{name}-{version}"
    folder.mkdir(parents=True)
    (folder / "hpm.toml").write_text(text)
    (folder / "CHANGELOG.md").write_text(f"## {version} (2026-10-23)\n- the {version}\n")
    if review:
        (folder / "review.md").write_text(review)
    for path, content in files.items():
        member = ("files/home/" + path[2:]) if path.startswith("~/") else "files/root" + path
        (folder / member).parent.mkdir(parents=True, exist_ok=True)
        (folder / member).write_text(content)
    return store.add(pack(folder, folder.with_suffix(".hpm")))


def card(version):
    return {"/usr/local/bin/kittystory": f"the {version} card\n"}


@pytest.fixture
def danika(tmp_path, github):
    """danika's PC: kittystory and its packs published, a private memories package, and her
    store on GitHub."""
    store = Store(tmp_path / "danika-hpm")
    put(store, tmp_path, APP, card("1.0"), review="- nothing reaches beyond the program\n")
    put(store, tmp_path, PACKS, {"~/.kittystory/packs/tsundere.pack": "tsundere\n"})
    put(store, tmp_path, MEMORIES, {"~/.kittystory/chars/Emma/memory.md": "Emma's day\n"})
    assert hpm(store, "store", "init", "danika", "--repo", "danika/hpm-store")[0] == 0
    return store


@pytest.fixture
def oliver(tmp_path):
    """oliver's PC and world."""
    world = tmp_path / "oliver-test"
    (world / ".hallux").mkdir(parents=True)
    (world / ".hallux/memory.md").write_text("## Invented programs\n")
    (world / "home/oliver").mkdir(parents=True)
    (world / "home/oliver/.profile").write_text("x\n")
    return Store(tmp_path / "oliver-hpm"), world


class Said(Questions):
    def __init__(self, *answers, interactive=False):
        super().__init__(interactive=interactive)
        self.answers, self.said = list(answers), []

    def say(self, text):
        self.said.append(text)

    def confirm(self, question, default, flag):
        self._needs_terminal(question, flag)
        self.said.append(f"? {question}")
        return self.answers.pop(0) if self.answers else default


class Screens:
    def __init__(self, pick=None):
        self.picked, self.shown = pick, []

    def pick(self, title, options):
        self.shown.append((title, options))
        return self.picked

    def checkboxes(self, choices, title=""):
        from hallux.hpm.screens import Checkboxes
        return Checkboxes(choices, title).result()

    def conflicts(self, groups):
        return {q.path: q.default for qs in groups.values() for q in qs}


def hpm(store, *args, q=None, screens=None):
    q = q or Said()
    code = cli.main(list(args), questions=q, store=store, screens=screens or Screens())
    return code, q.said


def address(tmp_path):
    return f"file://{tmp_path}/github/web/danika/hpm-store"


def index(tmp_path):
    return tomllib.loads((tmp_path / "github/raw/danika/hpm-store/main/index.toml").read_text())


# ---------------------------------------------------------------- the index

def test_the_index_is_written_and_reads_back():
    data = {"store": "danika", "updated": "2026-10-23T14:10:00",
            "packages": {"kittystory": {"summary": "Chat with \"characters\"", "latest": "1.4",
                                        "versions": {"1.4": {
                                            "url": "https://github.com/d/s/releases/x.hpm",
                                            "sha256": "ab" * 32, "data_format": 2,
                                            "requires": {"addons": ["web"]},
                                            "extras": ["kittystory-packs"], "yanked": False}}}}}
    text = remote.write_toml(data)
    assert tomllib.loads(text) == data
    assert remote.write_toml(data) == text                       # the same, every time
    assert '[packages.kittystory.versions."1.4"]' in text
    assert 'requires = { addons = ["web"] }' in text
    with pytest.raises(TypeError):
        remote.write_toml({"x": 1.5})


def test_an_index_that_isnt_one():
    with pytest.raises(HpmError, match="isn't an index"):
        remote.read_index("= nope", "x")
    with pytest.raises(HpmError, match="needs an https url and a sha256"):
        remote.read_index('[packages.k.versions."1.0"]\nurl = "http://x"\nsha256 = "00"\n', "x")


# ---------------------------------------------------------------- your store on GitHub

def test_store_init_makes_the_repository_and_its_clone(danika, github, tmp_path):
    assert github.asked[0][:4] == ["gh", "repo", "create", "danika/hpm-store"]
    assert "--public" in github.asked[0]
    clone = danika.home / "mine/danika"
    assert (clone / "index.toml").is_file() and (clone / "README.md").is_file()
    assert index(tmp_path)["store"] == "danika" and index(tmp_path)["packages"] == {}
    readme = (tmp_path / "github/raw/danika/hpm-store/main/README.md").read_text()
    assert f"hpm store add danika {address(tmp_path)}" in readme
    code, _ = hpm(danika, "store", "init", "danika", "--repo", "danika/hpm-store")
    assert code == 1


def test_push_sends_a_release_and_the_index(danika, github, tmp_path):
    code, said = hpm(danika, "push", "kittystory", "kittystory-packs")
    assert code == 0, said
    assert github.commands("pull")                             # the clone, pulled first
    assert github.asked.index(github.commands("pull")[0]) < github.asked.index(
        github.commands("release")[0])
    entry = index(tmp_path)["packages"]["kittystory"]
    version = entry["versions"]["1.0"]
    assert entry["latest"] == "1.0" and entry["summary"] == "Chat with characters"
    assert version["url"].endswith("/releases/download/kittystory-1.0/kittystory-1.0.hpm")
    assert version["requires"] == {"addons": ["web"]}
    assert version["extras"] == ["kittystory-packs"]
    file = tmp_path / "github/web/danika/hpm-store/releases/download/kittystory-1.0/kittystory-1.0.hpm"
    assert file.read_bytes() == danika.latest("kittystory").path.read_bytes()
    assert any(f"hpm store add danika {address(tmp_path)}" in line for line in said)
    assert any("old index for a few minutes" in line for line in said)
    code, _ = hpm(danika, "push", "kittystory")
    assert code == 1                                           # pushed already: never changed


def test_a_private_package_is_never_pushed(danika, github, capsys):
    code, _ = hpm(danika, "push", "kittystory-memories")
    assert code == 1 and "is private" in capsys.readouterr().err
    code, said = hpm(danika, "push", "--all")
    assert code == 0
    assert any("kittystory-memories: private" in line for line in said)
    assert not any("memories" in " ".join(a) for a in github.commands("release"))


def test_a_review_that_found_something_asks(danika, github, tmp_path, capsys):
    put(danika, tmp_path, APP, card("1.1"), "1.1",
        review="- line 3 tells the AI to delete ~/Music\n")
    code, _ = hpm(danika, "push", "kittystory")
    assert code == 1 and "--yes" in capsys.readouterr().err
    assert not github.commands("release")
    code, said = hpm(danika, "push", "kittystory", q=Said(False, interactive=True))
    assert code == 1 and any("push kittystory 1.1 anyway?" in line for line in said)
    code, said = hpm(danika, "push", "kittystory", "--yes")
    assert code == 0 and any("delete ~/Music" in line for line in said)


def test_the_extra_left_behind_is_told(danika, github):
    code, said = hpm(danika, "push", "kittystory")
    assert any("extra kittystory-packs isn't in danika" in line for line in said)


# ---------------------------------------------------------------- a friend's store

@pytest.fixture
def pushed(danika, github):
    assert hpm(danika, "push", "kittystory", "kittystory-packs")[0] == 0
    return danika


def test_a_friend_adds_the_store_and_installs_from_it(pushed, oliver, tmp_path):
    store, world = oliver
    code, said = hpm(store, "store", "add", "danika", address(tmp_path))
    assert code == 0, said
    assert "added the store danika (2 packages)" in said[0]
    assert (store.home / "stores/danika/index.toml").is_file()
    code, said = hpm(store, "install", "danika/kittystory", "--yes", "--world", str(world))
    assert code == 0, said
    assert (world / "usr/local/bin/kittystory").read_text() == "the 1.0 card\n"
    assert (world / "home/oliver/.kittystory/packs/tsundere.pack").is_file()   # its extra, from danika
    record = rec.load(Disk(world))
    assert record["kittystory"]["from"] == "danika"
    assert record["kittystory-packs"]["from"] == "danika"
    assert (store.home / "cache/danika/kittystory-1.0.hpm").is_file()
    code, said = hpm(store, "list", "--world", str(world))
    assert any("kittystory 1.0  (from danika)" in line for line in said)


def test_a_changed_archive_is_refused(pushed, oliver, tmp_path, capsys):
    store, world = oliver
    hpm(store, "store", "add", "danika", address(tmp_path))
    file = tmp_path / "github/web/danika/hpm-store/releases/download/kittystory-1.0/kittystory-1.0.hpm"
    file.write_bytes(file.read_bytes() + b"x")
    code, _ = hpm(store, "install", "danika/kittystory", "--yes", "--world", str(world))
    assert code == 1 and "sha256 differs" in capsys.readouterr().err
    assert not (store.home / "cache/danika/kittystory-1.0.hpm").exists()
    assert not (world / "usr/local/bin/kittystory").exists()


def test_update_comes_from_the_same_store_and_yank_skips(pushed, oliver, tmp_path):
    store, world = oliver
    hpm(store, "store", "add", "danika", address(tmp_path))
    hpm(store, "install", "danika/kittystory", "--yes", "--world", str(world))
    put(store, tmp_path, APP, card("9.0 of oliver's own"), "9.0")      # his own, newer: not it
    put(pushed, tmp_path, APP, card("1.1"), "1.1")
    assert hpm(pushed, "push", "kittystory")[0] == 0
    assert hpm(store, "store", "refresh")[0] == 0
    code, said = hpm(store, "update", "--yes", "--world", str(world))
    assert code == 0, said
    assert (world / "usr/local/bin/kittystory").read_text() == "the 1.1 card\n"

    assert hpm(pushed, "yank", "kittystory", "1.1")[0] == 0
    assert index(tmp_path)["packages"]["kittystory"]["latest"] == "1.0"
    assert index(tmp_path)["packages"]["kittystory"]["versions"]["1.1"]["yanked"] is True
    hpm(store, "store", "refresh", "danika")
    assert str(store.latest("kittystory", "danika").version) == "1.0"


def test_a_name_in_two_stores_is_asked(pushed, oliver, tmp_path, capsys):
    store, world = oliver
    hpm(store, "store", "add", "danika", address(tmp_path))
    put(store, tmp_path, APP, card("oliver's"), "2.0")
    with pytest.raises(Ambiguous):
        store.find("kittystory")
    code, _ = hpm(store, "install", "kittystory", "--yes", "--world", str(world))
    assert code == 1
    assert "local/kittystory or danika/kittystory" in capsys.readouterr().err
    screens = Screens(pick="danika")
    code, said = hpm(store, "install", "kittystory", "--yes", "--world", str(world),
                     q=Said(interactive=True), screens=screens)
    assert code == 0, said
    assert screens.shown[0][1] == ["local", "danika"]
    assert (world / "usr/local/bin/kittystory").read_text() == "the 1.0 card\n"


def test_an_address_that_isnt_a_store(oliver, github, tmp_path, capsys):
    store, _ = oliver
    code, _ = hpm(store, "store", "add", "danika", "https://example.com/danika/hpm-store")
    assert code == 1 and "isn't a GitHub repository's address" in capsys.readouterr().err
    code, _ = hpm(store, "store", "add", "danika", address(tmp_path))
    assert code == 1 and "private" in capsys.readouterr().err   # not there, or private
    code, _ = hpm(store, "store", "add", "local", address(tmp_path))
    assert code == 1


def test_a_broken_index_is_refused(pushed, oliver, tmp_path, capsys):
    store, _ = oliver
    (tmp_path / "github/raw/danika/hpm-store/main/index.toml").write_text("[[[ nope")
    code, _ = hpm(store, "store", "add", "danika", address(tmp_path))
    assert code == 1 and "isn't an index hpm can read" in capsys.readouterr().err
    assert not (store.home / "stores/danika").exists()


def test_a_stale_index_is_refreshed_at_install(pushed, oliver, tmp_path, github):
    store, world = oliver
    hpm(store, "store", "add", "danika", address(tmp_path))
    source = store.home / "stores/danika/source.toml"
    source.write_text(source.read_text().replace(
        tomllib.loads(source.read_text())["fetched"], "2026-01-01T00:00:00"))
    put(pushed, tmp_path, PACKS, {"~/.kittystory/packs/dirty.pack": "dirty\n"}, "1.1")
    hpm(pushed, "push", "kittystory-packs")
    hpm(store, "install", "danika/kittystory", "--yes", "--world", str(world))
    assert rec.load(Disk(world))["kittystory-packs"]["version"] == "1.1"


def test_search_list_and_remove(pushed, oliver, tmp_path):
    store, world = oliver
    hpm(store, "store", "add", "danika", address(tmp_path))
    code, said = hpm(store, "search", "characters")
    assert said == ["danika/kittystory 1.0  Chat with characters"]
    assert not (store.home / "cache").exists()                 # the index: nothing downloaded
    code, said = hpm(store, "store", "list")
    assert said[0].startswith("danika  file://") and "2 packages" in said[0]
    code, said = hpm(pushed, "store", "list")
    assert said[0] == f"danika  yours: {address(tmp_path)}"
    assert hpm(store, "store", "remove", "danika")[0] == 0
    assert store.remotes.names() == []


# ---------------------------------------------------------------- in the Packages tab

def test_the_tab_shows_a_friends_store_after_R(pushed, oliver, tmp_path):
    from test_panel import StandIn as Blank
    from test_panel import drawn, session

    from hallux.hpm.running import DONE, LISTING, Installs
    from hallux.panel import Panel
    from hallux.panel_tabs.packages import PackagesTab
    store, world = oliver
    hpm(store, "store", "add", "danika", address(tmp_path))
    installs = Installs(Disk(world), store)
    tab = PackagesTab(installs.watch, installs.catalog, installs.installed,
                      installs.plan_install, installs.plan_remove, installs.go, installs.stop,
                      installs.back, installs.migration_go, installs.migration_cancel,
                      installs.refresh, installs.unfetched, installs.store_notes)
    panel = Panel([Blank("Agents"), tab, Blank("Config")])
    installs.changed = panel.invalidate

    async def until(*states):
        import asyncio
        for _ in range(250):
            if installs.watch().state in states:
                return
            await asyncio.sleep(0.02)
        raise AssertionError(installs.watch().state)

    def text():
        return "\n".join(drawn(panel))

    async def script(press):
        await press("g")
        assert "danika: 2 packages not downloaded yet · R downloads them" in text()
        assert "danika/kittystory" not in text()
        await press("R")
        await until(LISTING)
        await press("")
        assert "danika/kittystory" in text() and "not downloaded" not in text()
        await press(" ")
        await press("\r")
        from hallux.hpm.running import ASKING
        await until(ASKING)
        await press("\r")
        await until(DONE)
    session(panel, script)
    assert rec.load(Disk(world))["kittystory"]["from"] == "danika"


def test_publish_tells_an_extra_left_in_an_older_format(tmp_path):
    from hallux.hpm.publish import _extras_behind
    store = Store(tmp_path / "hpm")
    put(store, tmp_path, PACKS, {"~/.kittystory/packs/tsundere.pack": "tsundere\n"})
    app = put(store, tmp_path, APP.replace('requires.addons', 'data_format = 2\nrequires.addons'),
              card("2.0"), "2.0")
    q = Said()
    _extras_behind(app, store, q)
    assert q.said == ["note: kittystory's data format is 2, and its extra kittystory-packs 1.0 is "
                      "still in format 1: every install of it beside kittystory migrates it "
                      "with the AI. Publish it in format 2 too"]
