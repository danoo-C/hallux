"""The hpm command (hallux/hpm/cli.py) and its screens (hallux/hpm/screens.py), and the mark
of a running world (hallux/hpm/world.py, hallux/app.py). Worlds and stores are temporary
folders; the screens are answered by a script, or driven by their keys on a pipe."""
import io
import os
import sys

import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from hallux import app
from hallux.disk import Disk
from hallux.hpm import cli
from hallux.hpm import record as rec
from hallux.hpm.archive import pack
from hallux.hpm.engine import BOTH, FAIL, KEEP, OVERWRITE, REMOVE, SKIP, Action, Want
from hallux.hpm.manifest import Manifest
from hallux.hpm.publish import Questions
from hallux.hpm.screens import Checkboxes, Choice, Conflicts, Pick
from hallux.hpm.store import Store
from hallux.hpm.world import mark_running, read_mark, running, unmark_running

APP = '''name = "kittystory"
version = "{version}"
summary = "Chat with characters"
memory_line = "kittystory: split-screen chat"
[files]
app = ["/usr/local/bin/kittystory", "/usr/local/share/apps/kittystory/**"]
[extras]
packs      = {{ package = "kittystory-packs", default = true }}
characters = {{ package = "kittystory-chars", default = false, needs = ["packs"] }}
'''
PACKS = 'name = "kittystory-packs"\nversion = "{version}"\nsummary = "3 packs"\nfor = "kittystory"\n' \
        '[files]\ndata = ["~/.kittystory/packs/*.pack"]\n'
CHARS = 'name = "kittystory-chars"\nversion = "{version}"\nsummary = "Emma, Lucy"\nfor = "kittystory"\n' \
        '[files]\ndata = ["~/.kittystory/chars/*/char.md"]\n'


def put(store, tmp_path, manifest, files, version="1.0"):
    text = manifest.format(version=version)
    name = text.split('"')[1]
    folder = tmp_path / "pkgs" / f"{name}-{version}"
    folder.mkdir(parents=True)
    (folder / "hpm.toml").write_text(text)
    for path, content in files.items():
        member = ("files/home/" + path[2:]) if path.startswith("~/") else "files/root" + path
        (folder / member).parent.mkdir(parents=True, exist_ok=True)
        (folder / member).write_text(content)
    return store.add(pack(folder, tmp_path / "pkgs" / f"{name}-{version}.hpm"))


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "store")
    put(store, tmp_path, APP, {"/usr/local/bin/kittystory": "the card\n",
                               "/usr/local/share/apps/kittystory/app.js": "// 1.0\n"})
    put(store, tmp_path, PACKS, {"~/.kittystory/packs/tsundere.pack": "tsundere\n"})
    put(store, tmp_path, CHARS, {"~/.kittystory/chars/Emma/char.md": "Emma\n"})
    return store


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "oliver-test"
    (root / ".hallux").mkdir(parents=True)
    (root / ".hallux/memory.md").write_text("# memory\n## Invented programs\n- calc: a calculator\n")
    (root / "home/user").mkdir(parents=True)
    (root / "home/user/.profile").write_text("x\n")
    return root


class Said(Questions):
    """What hpm says, kept; questions answered from a list."""

    def __init__(self, *answers, interactive=False):
        super().__init__(interactive=interactive)
        self.answers, self.said = list(answers), []

    def say(self, text, kind=None):
        self.said.append(text)

    def confirm(self, question, default, flag):
        self._needs_terminal(question, flag)
        return self.answers.pop(0) if self.answers else default


class Screens:
    """The full-screen questions, answered from a script."""

    def __init__(self, checkboxes="defaults", pick=None, conflicts="defaults"):
        self.answer = {"checkboxes": checkboxes, "pick": pick, "conflicts": conflicts}
        self.shown = []

    def checkboxes(self, choices, title=""):
        self.shown.append(("checkboxes", choices))
        answer = self.answer["checkboxes"]
        return Checkboxes(choices, title).result() if answer == "defaults" else answer

    def pick(self, title, options):
        self.shown.append(("pick", options))
        return self.answer["pick"]

    def conflicts(self, groups):
        self.shown.append(("conflicts", groups))
        answer = self.answer["conflicts"]
        if answer == "defaults":
            return {q.path: q.default for qs in groups.values() for q in qs}
        return answer


def hpm(world, store, *args, q=None, screens=None):
    q = q or Said()
    code = cli.main([*args, "--world", str(world)] if "--world" not in args and args[0] not in (
        "show", "search") else list(args), questions=q, store=store, screens=screens or Screens())
    return code, q.said


def files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file() and ".hallux" not in p.parts)


# ---------------------------------------------------------------- install

def test_install_with_flags_only(world, store):
    code, said = hpm(world, store, "install", "kittystory", "--extras", "packs")
    assert code == 0
    assert "home/user/.kittystory/packs/tsundere.pack" in files(world)
    assert said[-1].startswith("2 installed  (backup: ")
    assert "  ✓ kittystory 1.0 installed, 3 files" in said
    record = rec.load(Disk(world))
    assert record["kittystory"]["extras"] == ["packs"] and "kittystory-chars" not in record


def test_install_without_a_terminal_names_the_flag(world, store, capsys):
    before = files(world)
    code, _ = hpm(world, store, "install", "kittystory")
    assert code == 1
    assert "pass --extras K,K (or none), or --yes for the defaults" in capsys.readouterr().err
    assert files(world) == before and rec.load(Disk(world)) == {}


def test_yes_takes_the_defaults(world, store):
    code, _ = hpm(world, store, "install", "kittystory", "--yes")
    assert code == 0 and sorted(rec.load(Disk(world))) == ["kittystory", "kittystory-packs"]


def test_extras_none_and_an_extra_nobody_has(world, store, capsys):
    assert hpm(world, store, "install", "kittystory", "--extras", "none")[0] == 0
    assert sorted(rec.load(Disk(world))) == ["kittystory"]
    assert hpm(world, store, "install", "kittystory", "--extras", "sprites")[0] == 1
    assert "no package here has the extra sprites" in capsys.readouterr().err


def test_the_checkboxes_choose(world, store):
    screens = Screens(checkboxes=[Want("kittystory", extras=("packs", "characters"))])
    code, _ = hpm(world, store, "install", "kittystory", q=Said(interactive=True), screens=screens)
    assert code == 0
    kind, choices = screens.shown[0]
    assert kind == "checkboxes" and [c.name for c in choices] == ["kittystory"]
    assert choices[0].labels == {"packs": "3 packs", "characters": "Emma, Lucy"}
    assert choices[0].card == ["the card"]
    assert sorted(rec.load(Disk(world))) == ["kittystory", "kittystory-chars", "kittystory-packs"]


def test_cancelling_the_checkboxes_writes_nothing(world, store):
    code, said = hpm(world, store, "install", "kittystory", q=Said(interactive=True),
                     screens=Screens(checkboxes=None))
    assert code == 1 and said == ["cancelled; nothing was written"]
    assert rec.load(Disk(world)) == {}


def test_a_conflict_answered_on_the_screen(world, store):
    (world / "usr/local/bin").mkdir(parents=True)
    (world / "usr/local/bin/kittystory").write_text("the machine's own card\n")
    screens = Screens(conflicts={"/usr/local/bin/kittystory": BOTH})
    code, _ = hpm(world, store, "install", "kittystory", "--yes", q=Said(interactive=True),
                  screens=screens)
    assert code == 0 and screens.shown[0][0] == "conflicts"
    assert (world / "usr/local/bin/kittystory").read_text() == "the machine's own card\n"
    assert (world / "usr/local/bin/kittystory.hpm-new").read_text() == "the card\n"


def test_a_conflict_without_a_terminal(world, store, capsys):
    (world / "usr/local/bin").mkdir(parents=True)
    (world / "usr/local/bin/kittystory").write_text("mine\n")
    assert hpm(world, store, "install", "kittystory", "--yes")[0] == 1
    assert "pass --overwrite all or none" in capsys.readouterr().err
    assert hpm(world, store, "install", "kittystory", "--yes", "--overwrite", "none")[0] == 0
    assert (world / "usr/local/bin/kittystory").read_text() == "mine\n"


def test_overwrite_all_still_skips_a_folder_in_the_way(world, store):
    (world / "usr/local/bin/kittystory").mkdir(parents=True)
    code, said = hpm(world, store, "install", "kittystory", "--extras", "none", "--overwrite", "all")
    assert code == 0 and (world / "usr/local/bin/kittystory").is_dir()


def test_several_users_are_picked(world, store):
    (world / "home/other").mkdir()
    (world / "home/other/.profile").write_text("x\n")
    screens = Screens(pick="other")
    code, _ = hpm(world, store, "install", "kittystory", "--yes", q=Said(interactive=True),
                  screens=screens)
    assert code == 0 and screens.shown[0] == ("pick", ["other", "user"])
    assert (world / "home/other/.kittystory/packs/tsundere.pack").exists()


def test_several_users_without_a_terminal(world, store, capsys):
    (world / "home/other").mkdir()
    (world / "home/other/.profile").write_text("x\n")
    assert hpm(world, store, "install", "kittystory", "--yes")[0] == 1
    assert "say which with --user" in capsys.readouterr().err
    assert hpm(world, store, "install", "kittystory", "--yes", "--user", "other")[0] == 0


@pytest.mark.parametrize("name, words", [
    ("danika/", "there is no store 'danika'"),
    ("danika/kittystory", "there is no store 'danika'"),
    ("kitty story", "is no NAME: a NAME is a package"),
    ("kittymusic", "there is no package kittymusic in the store"),
])
def test_names_that_arent(world, store, capsys, name, words):
    assert hpm(world, store, "install", name, "--yes")[0] == 1
    assert words in capsys.readouterr().err


def test_a_whole_store_and_a_store_name(world, store):
    assert hpm(world, store, "install", "local/", "--yes")[0] == 0
    assert sorted(rec.load(Disk(world))) == ["kittystory", "kittystory-packs"]
    assert hpm(world, store, "install", "local/kittystory-chars", "--yes")[0] == 0
    assert "kittystory-chars" in rec.load(Disk(world))


# ---------------------------------------------------------------- the old memory line

OLD = "- kittystory (was lt-love): the machine's own words"


def with_old_line(world):
    path = world / ".hallux/memory.md"
    path.write_text(path.read_text() + OLD + "\n")


def test_the_old_line_without_a_terminal(world, store, capsys):
    with_old_line(world)
    assert hpm(world, store, "install", "kittystory", "--extras", "none")[0] == 1
    assert "pass --old-line replace or keep, or --yes" in capsys.readouterr().err


@pytest.mark.parametrize("args, kept", [(["--old-line", "keep"], True),
                                        (["--old-line", "replace"], False),
                                        (["--yes"], False)])
def test_the_old_line_by_flag(world, store, args, kept):
    with_old_line(world)
    extras = [] if "--yes" in args else ["--extras", "none"]
    assert hpm(world, store, "install", "kittystory", *extras, *args)[0] == 0
    assert (OLD in Disk(world).memory_read()["text"]) is kept


def test_the_old_line_asked(world, store):
    with_old_line(world)
    q = Said(False, interactive=True)                 # "replace it?" no
    hpm(world, store, "install", "kittystory", "--extras", "none", q=q)
    assert any("its own line about kittystory" in line for line in q.said)
    assert OLD in Disk(world).memory_read()["text"]


# ---------------------------------------------------------------- update, remove, list, rollback

def test_update(world, store, tmp_path):
    hpm(world, store, "install", "kittystory", "--yes")
    code, said = hpm(world, store, "update")
    assert code == 0 and said == ["everything is up to date"]
    put(store, tmp_path, APP, {"/usr/local/bin/kittystory": "the card, 1.1\n",
                               "/usr/local/share/apps/kittystory/app.js": "// 1.1\n"}, version="1.1")
    code, said = hpm(world, store, "list")
    assert said[0] == "kittystory 1.0  ↑ 1.1 in the store  extras: packs"
    code, said = hpm(world, store, "update")
    assert code == 0 and "  ✓ kittystory 1.1 updated (was 1.0), 3 files" in said
    assert (world / "usr/local/bin/kittystory").read_text() == "the card, 1.1\n"
    assert rec.load(Disk(world))["kittystory"]["extras"] == ["packs"]


def test_an_extra_that_is_there_already_is_left_alone(world, store, tmp_path):
    hpm(world, store, "install", "kittystory", "--yes")
    put(store, tmp_path, APP, {"/usr/local/bin/kittystory": "1.1\n",
                               "/usr/local/share/apps/kittystory/app.js": "1.1\n"}, version="1.1")
    code, said = hpm(world, store, "update")
    assert said[-1].startswith("1 updated") and not any("kittystory-packs" in s for s in said)


def test_update_shows_the_checkboxes_on_a_terminal(world, store, tmp_path):
    hpm(world, store, "install", "kittystory", "--yes")
    put(store, tmp_path, APP, {"/usr/local/bin/kittystory": "1.1\n",
                               "/usr/local/share/apps/kittystory/app.js": "1.1\n"}, version="1.1")
    screens = Screens()
    hpm(world, store, "update", q=Said(interactive=True), screens=screens)
    kind, choices = screens.shown[0]
    assert choices[0].note == "installed 1.0 → 1.1"
    assert choices[0].extras == {"packs": True, "characters": False}


def test_update_of_what_isnt_installed(world, store, capsys):
    assert hpm(world, store, "update", "kittystory")[0] == 1
    assert "kittystory isn't installed in this world" in capsys.readouterr().err


def test_remove_and_rollback(world, store):
    hpm(world, store, "install", "kittystory", "--yes")
    code, said = hpm(world, store, "remove", "kittystory")
    assert code == 0 and said[-1].startswith("1 removed")
    assert "usr/local/bin/kittystory" not in files(world)
    assert "home/user/.kittystory/packs/tsundere.pack" in files(world)
    code, said = hpm(world, store, "rollback", "kittystory")
    assert code == 0 and said[0].startswith("kittystory back to 1.0 (")
    assert "usr/local/bin/kittystory" in files(world)


def test_remove_a_file_you_changed_with_overwrite_none(world, store):
    hpm(world, store, "install", "kittystory", "--extras", "none")
    (world / "usr/local/bin/kittystory").write_text("mine\n")
    assert hpm(world, store, "remove", "kittystory")[0] == 1          # asked, and no terminal
    assert hpm(world, store, "remove", "kittystory", "--overwrite", "none")[0] == 0
    assert (world / "usr/local/bin/kittystory").read_text() == "mine\n"


def test_remove_with_data(world, store):
    hpm(world, store, "install", "kittystory", "--yes")
    hpm(world, store, "remove", "kittystory-packs", "--data")
    assert "home/user/.kittystory/packs/tsundere.pack" not in files(world)


def test_list_and_backups(world, store):
    code, said = hpm(world, store, "list")
    assert said == ["nothing installed by hpm in this world"]
    hpm(world, store, "install", "kittystory", "--yes")
    code, said = hpm(world, store, "list")
    assert said[:2] == ["kittystory 1.0  extras: packs", "kittystory-packs 1.0"]
    assert said[2].startswith("backups: 1, ")
    code, said = hpm(world, store, "backups")
    assert said[-1].startswith("1 backups, ")
    assert hpm(world, store, "backups", "--clean")[0] == 1               # asked: no terminal
    code, said = hpm(world, store, "backups", "--clean", "--yes")
    assert said == ["removed 1 backups"] and rec.backups(Disk(world)) == []


def test_search(world, store):
    code, said = hpm(world, store, "search", "EMMA")
    assert said == ["kittystory-chars 1.0  Emma, Lucy"]
    code, said = hpm(world, store, "search", "dragons")
    assert said == ["nothing in the store has 'dragons' in its name or summary"]


# ---------------------------------------------------------------- adopt, and publish adopting

def test_adopt(world, store):
    (world / "usr/local/bin").mkdir(parents=True)
    (world / "usr/local/bin/kittystory").write_text("the card\n")
    code, said = hpm(world, store, "adopt", "kittystory")
    assert code == 0 and said[0].startswith("kittystory 1.0: 1 files are the release's, ")
    assert said[-1] == "1 adopted"
    assert hpm(world, store, "list")[1][0] == "kittystory 1.0  (adopted)"


def test_publish_adopts_its_own_world(world, store):
    hpm(world, store, "install", "kittystory", "--extras", "none")
    rec.save(Disk(world), {})                        # as if it was built here, not installed
    (world / "usr/local/bin/kittystory").write_text("the card, better\n")
    code, said = hpm(world, store, "publish", "kittystory", "--yes", "--changelog", "better")
    assert code == 0 and "published kittystory 1.1: 2 files, 24 bytes" in said
    assert hpm(world, store, "list")[1][0] == "kittystory 1.1  (adopted)"


def extras_of(world, name="kittystory"):
    return rec.load(Disk(world))[name]["extras"]


def test_publish_all_records_the_extras_in_its_own_world(world, store):
    """Fix 04: publish --all adopts the app first and its extras after; the app's entry
    lists them all the same."""
    hpm(world, store, "install", "kittystory", "--extras", "packs,characters")
    rec.save(Disk(world), {})                        # as if it was built here
    (world / "usr/local/bin/kittystory").write_text("the card, better\n")
    (world / "home/user/.kittystory/packs/tsundere.pack").write_text("tsundere, better\n")
    (world / "home/user/.kittystory/chars/Emma/char.md").write_text("Emma, better\n")
    code, said = hpm(world, store, "publish", "kittystory", "--all", "--yes", "--changelog", "x")
    assert code == 0, said
    assert extras_of(world) == ["packs", "characters"]


def test_publish_from_a_world_that_installed_it_keeps_its_extras(world, store):
    """Fix 04, the case of publishing from a second world: its extras were installed, and
    the adopt after publish must not wipe them from its record."""
    hpm(world, store, "install", "kittystory", "--extras", "packs,characters")
    assert extras_of(world) == ["packs", "characters"]
    (world / "usr/local/bin/kittystory").write_text("the card, with a feature\n")
    assert hpm(world, store, "publish", "kittystory", "--yes", "--changelog", "x")[0] == 0
    assert extras_of(world) == ["packs", "characters"]


def test_adopting_an_extra_adds_its_key_to_the_app(world, store, tmp_path):
    hpm(world, store, "install", "kittystory", "--extras", "packs,characters")
    record = rec.load(Disk(world))
    record["kittystory"]["extras"] = []
    del record["kittystory-chars"]
    rec.save(Disk(world), record)
    assert hpm(world, store, "adopt", "kittystory-chars")[0] == 0
    assert extras_of(world) == ["characters"]
    assert hpm(world, store, "adopt", "kittystory")[0] == 0     # the app: what is recorded
    assert extras_of(world) == ["packs", "characters"]
    put(store, tmp_path, CHARS, {"~/.kittystory/chars/Emma/char.md": "Emma 1.1\n"}, version="1.1")
    put(store, tmp_path, APP, {"/usr/local/bin/kittystory": "the card\n",
                               "/usr/local/share/apps/kittystory/app.js": "// 1.1\n"},
        version="1.1")
    assert hpm(world, store, "update", "kittystory", "--yes")[0] == 0
    assert rec.load(Disk(world))["kittystory-chars"]["version"] == "1.1"


SEEDED = APP.replace('[extras]', 'seed = ["/usr/local/share/apps/kittystory/state.json"]\n[extras]')
STATE = "/usr/local/share/apps/kittystory/state.json"


def seeded(store, tmp_path):
    put(store, tmp_path, SEEDED, {"/usr/local/bin/kittystory": "the card\n",
                                  "/usr/local/share/apps/kittystory/app.js": "// 1.0\n",
                                  STATE: '{"chat": []}\n'}, version="1.1")


def test_a_world_that_installed_it_publishes_the_clean_seed(world, store, tmp_path):
    """Fix 06: the second world's used seed stays home; the release's goes out again."""
    from hallux.hpm.archive import read_member
    seeded(store, tmp_path)
    hpm(world, store, "install", "kittystory", "--extras", "none")
    (world / STATE.lstrip("/")).write_text('{"chat": ["hi Emma, it is me"]}\n')
    code, said = hpm(world, store, "publish", "kittystory", "--yes", "--changelog", "x")
    assert code == 1                                  # only the used seed: nothing changed
    (world / "usr/local/bin/kittystory").write_text("the card, with a feature\n")
    code, said = hpm(world, store, "publish", "kittystory", "--changelog", "x", "--version", "1.2")
    assert code == 0                                  # fix 07: no question, the copy is there
    assert any(line.startswith("note: published the clean seed ") for line in said)
    release = store.latest("kittystory")
    assert str(release.version) == "1.2"
    assert read_member(release.path, "files/root" + STATE) == b'{"chat": []}\n'


def test_publish_keeps_the_old_line_without_a_terminal_and_says_so(world, store):
    hpm(world, store, "install", "kittystory", "--extras", "none")
    rec.save(Disk(world), {})
    with_old_line(world)
    (world / "usr/local/bin/kittystory").write_text("new\n")
    q = Said()
    cli.main(["publish", "kittystory", "--world", str(world), "--version", "1.1", "--changelog",
              "x"], questions=q, store=store, screens=Screens())
    assert any("hpm adopt kittystory --old-line replace" in line for line in q.said)
    assert OLD in Disk(world).memory_read()["text"]


# ---------------------------------------------------------------- a running world

def test_a_running_world_is_refused_for_what_writes(world, store, capsys):
    hpm(world, store, "install", "kittystory", "--yes")
    mark = mark_running(world)                        # this process: alive
    try:
        for args in (["install", "kittystory-chars", "--yes"], ["update"],
                     ["remove", "kittystory"], ["rollback", "kittystory"]):
            assert hpm(world, store, *args)[0] == 1
            assert "this world is running" in capsys.readouterr().err
        assert hpm(world, store, "list")[0] == 0
        assert hpm(world, store, "adopt", "kittystory")[0] == 0
    finally:
        unmark_running(world, mark)
    assert hpm(world, store, "remove", "kittystory")[0] == 0


def test_a_dead_mark_and_a_reused_number(world):
    (world / ".hallux/running").write_text('{"pid": 999999999, "start": 1}\n')
    assert running(world) is None
    mark = mark_running(world)
    assert running(world) == os.getpid()
    (world / ".hallux/running").write_text(f'{{"pid": {os.getpid()}, "start": {mark["start"] + 1}}}\n')
    assert running(world) is None                     # the number, but another process
    (world / ".hallux/running").write_text("not json")
    assert running(world) is None


def test_unmark_takes_only_its_own_mark(world):
    mark = mark_running(world)
    (world / ".hallux/running").write_text('{"pid": 1, "start": 5}\n')
    unmark_running(world, mark)
    assert read_mark(world) == {"pid": 1, "start": 5}


def test_hallux_marks_the_world_while_it_runs(tmp_path, monkeypatch):
    root = tmp_path / "w"
    seen = []

    def run(root_, hardware, flags, headless):
        seen.append(running(root_))
        raise RuntimeError("the machine crashed")

    monkeypatch.setattr(app, "_run", run)
    monkeypatch.setattr(sys, "argv", ["hallux", str(root), "--script", "-"])
    with pytest.raises(RuntimeError):
        app.main()
    assert seen == [os.getpid()] and running(root) is None and read_mark(root) is None

    def ends(root_, hardware, flags, headless):
        seen.append(running(root_))
        sys.exit(0)

    monkeypatch.setattr(app, "_run", ends)
    with pytest.raises(SystemExit):
        app.main()
    assert seen[-1] == os.getpid() and read_mark(root) is None


# ---------------------------------------------------------------- the screens' models

def manifest():
    return Manifest.load(APP.format(version="1.0"))


def test_checkboxes_tick_needs_and_untick_what_needs():
    screen = Checkboxes([Choice("kittystory", manifest())])
    assert [c.extras for c in screen.choices] == [{"packs": True, "characters": False}]
    screen.cursor = 2                                 # characters
    screen.toggle()
    assert screen.choices[0].extras == {"packs": True, "characters": True}
    screen.choices[0].extras["packs"] = True
    screen.cursor = 1                                 # packs
    screen.toggle()
    assert screen.choices[0].extras == {"packs": False, "characters": False}
    screen.cursor = 2
    screen.toggle()                                   # ticking characters ticks packs again
    assert screen.choices[0].extras == {"packs": True, "characters": True}
    assert screen.result() == [Want("kittystory", extras=("packs", "characters"))]


def test_checkboxes_fold_and_all_and_none():
    screen = Checkboxes([Choice("kittystory", manifest()), Choice("kittycalc", manifest())])
    assert screen.title == "2 packages" and len(screen.rows()) == 2  # folded with several
    screen.open()
    assert len(screen.rows()) == 4
    screen.cursor = 1
    screen.close()
    assert len(screen.rows()) == 2 and screen.cursor == 0
    screen.none()
    assert screen.result() == []
    screen.all()
    assert [w.name for w in screen.result()] == ["kittystory", "kittycalc"]
    screen.cursor = 0
    screen.toggle()
    assert [w.name for w in screen.result()] == ["kittycalc"]


def test_checkboxes_v_shows_the_card_and_the_memory_line():
    screen = Checkboxes([Choice("kittystory", manifest(), card=["# kittystory", "the card"])])
    screen.show_card()
    assert "the card" in screen.viewing and "  kittystory: split-screen chat" in screen.viewing


def q(path, mark="foreign", choices=(OVERWRITE, SKIP, BOTH), default=SKIP, package="kittystory-packs"):
    return Action(package, path, path, "data", mark, "ask", choices=choices, default=default)


def test_conflicts_keys_on_a_row_and_for_all():
    questions = [q("/home/user/.kittystory/packs/a.pack"), q("/home/user/.kittystory/packs/b.pack"),
                 q("/usr/local/bin/kittystory", "in-the-way", (SKIP, FAIL), SKIP, "kittystory"),
                 q("/usr/local/share/apps/kittystory/old.js", "changed", (REMOVE, KEEP), KEEP,
                   "kittystory")]
    screen = Conflicts({("x", "y"): questions})
    assert screen.title == "4 files are in the way"
    screen.answer(OVERWRITE)                          # o on the first row, and down
    assert screen.cursor == 1
    screen.answer(BOTH)                               # k
    screen.answer(OVERWRITE)                          # o on a folder in the way: not a choice
    assert screen.cursor == 2
    screen.answer(FAIL)
    screen.answer(KEEP)                               # k on a dropped file: keep
    assert screen.result() == {"/home/user/.kittystory/packs/a.pack": OVERWRITE,
                               "/home/user/.kittystory/packs/b.pack": BOTH,
                               "/usr/local/bin/kittystory": FAIL,
                               "/usr/local/share/apps/kittystory/old.js": KEEP}
    screen.answer_all(OVERWRITE)
    assert screen.result()["/usr/local/bin/kittystory"] == FAIL      # can't be overwritten
    screen.answer_all(SKIP)
    assert set(screen.result().values()) == {SKIP, KEEP}


# ---------------------------------------------------------------- the screens, on a pipe

def keys_into(screen, keys):
    with create_pipe_input() as pipe:
        pipe.send_text(keys)
        return screen.run(input=pipe, output=DummyOutput())


def test_the_checkbox_screen_by_its_keys():
    screen = Checkboxes([Choice("kittystory", manifest())])
    result = keys_into(screen, "\x1b[B\x1b[B \r")     # down, down, space on characters, Enter
    assert result == [Want("kittystory", extras=("packs", "characters"))]


def test_q_cancels_the_checkbox_screen():
    assert keys_into(Checkboxes([Choice("kittystory", manifest())]), " q") is None


def test_v_and_back_on_the_checkbox_screen():
    screen = Checkboxes([Choice("kittystory", manifest(), card=["the card"])])
    result = keys_into(screen, "vq\r")                # v, back with q, Enter
    assert result == [Want("kittystory", extras=("packs",))]


def test_the_conflict_screen_by_its_keys():
    screen = Conflicts({("p", "f"): [q("/a.pack"), q("/b.pack")]})
    assert keys_into(screen, "ok\r") == {"/a.pack": OVERWRITE, "/b.pack": BOTH}
    assert keys_into(Conflicts({("p", "f"): [q("/a.pack")]}), "O\r") == {"/a.pack": OVERWRITE}


def test_the_pick_screen():
    assert keys_into(Pick("whose home?", ["other", "user"]), "\x1b[B\r") == "user"


# ---------------------------------------------------------------- colors (docs/plans/hpm/colors/)

class Terminal(io.StringIO):
    def isatty(self):
        return True


def test_say_paints_on_a_terminal_and_not_with_no_color(monkeypatch):
    from hallux.hpm.publish import Questions as Real
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("HPM_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    out = Terminal()
    monkeypatch.setattr(sys, "stdout", out)
    Real(interactive=False).say("  ✓ kittystory 1.1 updated")
    assert out.getvalue() == "  \x1b[1;32m✓\x1b[0m\x1b[32m kittystory 1.1 updated\x1b[0m\n"
    monkeypatch.setenv("NO_COLOR", "1")
    out = Terminal()
    monkeypatch.setattr(sys, "stdout", out)
    Real(interactive=False).say("  ✓ kittystory 1.1 updated")
    assert out.getvalue() == "  ✓ kittystory 1.1 updated\n"


def test_a_question_is_bold_with_its_default_dim(monkeypatch):
    from hallux.hpm.publish import Questions as Real
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("HPM_COLOR", "always")
    asked = []
    monkeypatch.setattr("builtins.input", lambda prompt: asked.append(prompt) or "")
    monkeypatch.delitem(sys.modules, "readline", raising=False)
    assert Real(interactive=True).ask("kittystory's version", "1.2", "--version") == "1.2"
    assert asked == ["\x1b[1mkittystory's version \x1b[0m\x1b[90m[1.2]\x1b[0m: "]


def test_the_error_is_red_on_a_terminal_and_plain_in_a_pipe(world, store, monkeypatch, capsys):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("HPM_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert hpm(world, store, "update", "kittymusic")[0] == 1
    assert capsys.readouterr().err == "hpm: kittymusic isn't installed in this world; hpm install it\n"
    err = Terminal()
    monkeypatch.setattr(sys, "stderr", err)
    assert hpm(world, store, "update", "kittymusic")[0] == 1
    assert err.getvalue() == ("\x1b[1;31mhpm:\x1b[0m\x1b[31m kittymusic isn't installed in this "
                              "world; hpm install it\x1b[0m\n")


def test_an_update_in_colors_reads_the_same_without_them(world, store, tmp_path, monkeypatch):
    from hallux.hpm.paint import strip_codes
    from hallux.hpm.publish import Questions as Real
    monkeypatch.setenv("HPM_COLOR", "always")
    hpm(world, store, "install", "kittystory", "--extras", "packs")
    put(store, tmp_path, APP, {"/usr/local/bin/kittystory": "the card 1.1\n",
                               "/usr/local/share/apps/kittystory/app.js": "// 1.1\n"}, version="1.1")
    out = Terminal()
    monkeypatch.setattr(sys, "stdout", out)
    assert cli.main(["update", "--world", str(world), "--yes"], questions=Real(interactive=False),
                    store=store, screens=Screens()) == 0
    painted = out.getvalue()
    assert "  \x1b[1;32m✓\x1b[0m\x1b[32m kittystory 1.1 updated (was 1.0), 3 files\x1b[0m" in painted
    summary = [line for line in painted.splitlines() if "(backup: " in line][0]
    assert summary.startswith("\x1b[32m1 updated\x1b[0m\x1b[90m  (backup: ")
    plain = strip_codes(painted)
    assert "  ✓ kittystory 1.1 updated (was 1.0), 3 files" in plain.splitlines()
    assert "\x1b" not in plain
