"""Migrations (hallux/hpm/migrate.py; docs/hpm/migrations.md; the plan's step 7): the notes,
the staging disk, one package's migration in the command, data coming in, rollback, and
publish's checks and note. With a stand-in model that follows the note of migrations.md,
section 3: no model is called."""
import json

import pytest
from test_hpm_ai import StandIn, call, hand_over, says  # noqa: F401  (hand_over: a fixture)

from hallux.disk import Disk
from hallux.hpm import cli, engine, migrate
from hallux.hpm import record as rec
from hallux.hpm.archive import pack
from hallux.hpm.engine import Want, plan_install
from hallux.hpm.publish import Questions
from hallux.hpm.store import Store
from hallux.hpm.world import HpmError

HOME = "/home/danika"
APP1 = '''name = "kittystory"
version = "{version}"
summary = "Chat with characters"
memory_line = "kittystory: chat with characters"
[files]
app = ["/usr/local/bin/kittystory"]
'''
APP2 = '''name = "kittystory"
version = "{version}"
summary = "Chat with characters"
memory_line = "kittystory: chat with characters, 2.0"
data_format = 2
[files]
app = ["/usr/local/bin/kittystory"]
data = ["~/.kittystory/characters/*.toml", "~/.kittystory/memories/*.md"]
'''
NOTE = """# kittystory data format 1 → 2

Before: ~/.kittystory/chars/<Name>/{char.md, memory.md}
After:  ~/.kittystory/characters/<name>.toml   name, pack, notes
        ~/.kittystory/memories/<name>.md       memory.md, unchanged

Steps:
1. For each folder in chars/: read char.md, write characters/<name>.toml
   (the name in lowercase, the folder's name kept in `name`).
2. Copy memory.md to memories/<name>.md (with the copy tool: byte for byte).
3. shared.md, scene.md and assets/ stay where they are.

Checks:
- every folder in chars/ has a characters/<name>.toml
- every memories/<name>.md is the chars/<Name>/memory.md it came from, byte for byte
- no characters/*.toml without a folder it came from

Old paths, removed once the user accepts: ~/.kittystory/chars/
"""
CHECKS = migrate.read_note("1-to-2.md", NOTE).checks
BIG = "".join(f"2026-10-{d % 28 + 1:02d} Emma remembers line {d}\n" for d in range(8000))
CHARS = {"Emma": ("name: Emma\npack: sensitive-sweetheart\n", BIG),
         "Lucy": ("name: Lucy\npack: tsundere\n", "met at the cafe\n"),
         "emilly": ("name: emilly\npack: dirty\n", "likes rain\n")}


def put(store, tmp_path, manifest, files, version, notes=None):
    text = manifest.format(version=version)
    name = text.split('"')[1]
    folder = tmp_path / "pkgs" / f"{name}-{version}"
    folder.mkdir(parents=True)
    (folder / "hpm.toml").write_text(text)
    for path, content in files.items():
        member = ("files/home/" + path[2:]) if path.startswith("~/") else "files/root" + path
        (folder / member).parent.mkdir(parents=True, exist_ok=True)
        (folder / member).write_text(content)
    for note, content in (notes or {}).items():
        (folder / "migrations").mkdir(exist_ok=True)
        (folder / "migrations" / note).write_text(content)
    return store.add(pack(folder, tmp_path / "pkgs" / f"{name}-{version}.hpm"))


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "store")
    put(store, tmp_path, APP1, {"/usr/local/bin/kittystory": "the 1.0 card\n"}, "1.0")
    return store


def update(store, tmp_path):
    """kittystory 2.0 in the store, with its note."""
    put(store, tmp_path, APP2, {"/usr/local/bin/kittystory": "the 2.0 card: characters/\n"},
        "2.0", {"1-to-2.md": NOTE})


@pytest.fixture
def world(tmp_path, store):
    root = tmp_path / "test-hallux"
    (root / ".hallux").mkdir(parents=True)
    (root / ".hallux/memory.md").write_text("## Invented programs\n- calc: a calculator\n")
    (root / "etc").mkdir()
    (root / "etc/passwd").write_text("danika:x:1000:1000::/home/danika:/bin/bash\n")
    (root / "home/danika/.kittystory").mkdir(parents=True)
    (root / "home/danika/.kittystory/shared.md").write_text("we all met\n")
    for name, (char, memory) in CHARS.items():
        folder = root / f"home/danika/.kittystory/chars/{name}"
        folder.mkdir(parents=True)
        (folder / "char.md").write_text(char)
        (folder / "memory.md").write_text(memory)
    assert hpm(root, store, "install", "kittystory", "--yes")[0] == 0
    return root


class Said(Questions):
    def __init__(self, *answers, interactive=False):
        super().__init__(interactive=interactive)
        self.answers, self.said, self.asked = list(answers), [], []

    def say(self, text, kind=None):
        self.said.append(text)

    def confirm(self, question, default, flag):
        self._needs_terminal(question, flag)
        self.asked.append(question)
        return default

    def choose(self, question, keys, flag):
        self._needs_terminal(question, flag)
        self.asked.append(question)
        return self.answers.pop(0)


def hpm(world, store, *args, q=None, model=None):
    q = q or Said()
    code = cli.main([*args, "--world", str(world)], questions=q, store=store,
                    client_factory=model)
    return code, q.said


# ---------------------------------------------------------------- the stand-in model

def chars(world):
    return sorted(p.name for p in (world / "home/danika/.kittystory/chars").iterdir())


def planner():
    """The plan: what is in chars/, read with the tools."""
    async def turn(session, message):
        found = json.loads(await call(session, "list_dir", path="~/.kittystory/chars"))
        rows = [{"what": e["name"], "old": [f"~/.kittystory/chars/{e['name']}/"],
                 "new": [f"~/.kittystory/characters/{e['name'].lower()}.toml",
                         f"~/.kittystory/memories/{e['name'].lower()}.md"]} for e in found]
        return "Three characters move.\n```json\n" + json.dumps({"rows": rows}) + "\n```"
    return turn


def migrator(held=True, leave_out=None):
    """The migration: each char.md read and written as TOML, each memory copied, and never
    read: the big one is only ever copied."""
    async def turn(session, message):
        found = json.loads(await call(session, "list_dir", path="~/.kittystory/chars"))
        for entry in found:
            name = entry["name"]
            if name == leave_out:
                continue
            char = json.loads(await call(session, "read_file",
                                         path=f"~/.kittystory/chars/{name}/char.md"))["text"]
            pack_name = char.split("pack: ")[1].strip()
            await call(session, "write_file", path=f"~/.kittystory/characters/{name.lower()}.toml",
                       content=f'name = "{name}"\npack = "{pack_name}"\nnotes = ""\n')
            await call(session, "copy", **{"from": f"~/.kittystory/chars/{name}/memory.md",
                                           "to": f"~/.kittystory/memories/{name.lower()}.md"})
        checks = [{"check": c, "held": held, "why": "3 of 3" if held else "1 is missing"}
                  for c in CHECKS]
        return "Done.\n" + json.dumps({"checks": checks})
    return turn


def kitty(world, path=""):
    return world / "home/danika/.kittystory" / path


def record(world):
    return rec.load(Disk(world))


# ---------------------------------------------------------------- the notes

def test_a_note_is_read():
    note = migrate.read_note("1-to-2.md", NOTE)
    assert (note.old, note.new) == (1, 2)
    assert note.old_paths == ("~/.kittystory/chars/",)
    assert note.checks[0] == "every folder in chars/ has a characters/<name>.toml"
    assert len(note.checks) == 3
    assert migrate.read_note("2-to-3.md", "x\nOld paths: none\n").old_paths == ()


@pytest.mark.parametrize("name,text,words", [
    ("one-to-two.md", NOTE, "named <from>-to-<to>.md"),
    ("2-to-1.md", NOTE, "only goes up"),
    ("1-to-2.md", "# a note\nno line\n", "no line 'Old paths"),
    ("1-to-2.md", "Old paths: ~/\n", "names no file"),
    ("1-to-2.md", "Old paths: /usr\n", "whole top folder"),
    ("1-to-2.md", "Old paths: /.hallux/memory.md\n", "where no package may go"),
    ("1-to-2.md", "Old paths: chars/\n", "must start with / or ~/"),
])
def test_a_note_that_isnt(name, text, words):
    with pytest.raises(HpmError, match=words):
        migrate.read_note(name, text)


def test_the_chain_of_notes():
    one, two = (migrate.read_note(n, "Old paths: none\n") for n in ("1-to-2.md", "2-to-3.md"))
    assert migrate.chain([two, one], 1, 3, "x") == [one, two]
    assert migrate.chain([one], 1, 2, "x") == [one]
    assert migrate.chain([], 2, 2, "x") == []
    with pytest.raises(HpmError, match=r"no migration from data format 2 \(migrations/2-to-3.md\)"):
        migrate.chain([one], 1, 3, "kittystory 3.0")


# ---------------------------------------------------------------- the formats in a plan

def test_older_data_waits_for_a_migration(world, store, tmp_path):
    update(store, tmp_path)
    plan = plan_install(world, store, [Want("kittystory")])
    item = plan.items[0]
    assert not item.blocked and item.migrate is not None
    assert [n.name for n in item.migrate.notes] == ["1-to-2.md"]
    with pytest.raises(HpmError, match="has to be migrated first"):
        engine.apply(plan, {})
    assert (world / "usr/local/bin/kittystory").read_text() == "the 1.0 card\n"


def test_a_missing_note_blocks_the_update(world, store, tmp_path):
    put(store, tmp_path, APP2, {"/usr/local/bin/kittystory": "2.0\n"}, "2.0")
    item = plan_install(world, store, [Want("kittystory")]).items[0]
    assert "no migration from data format 1" in item.blocked


def test_newer_data_is_refused(world, store, tmp_path):
    entry = record(world)
    entry["kittystory"]["data_format"] = 3
    rec.save(Disk(world), entry)
    put(store, tmp_path, APP1, {"/usr/local/bin/kittystory": "1.1\n"}, "1.1")
    item = plan_install(world, store, [Want("kittystory")]).items[0]
    assert "an older app on newer data" in item.blocked


# ---------------------------------------------------------------- the staging disk

def staging(world, tmp_path):
    disk = Disk(world)
    allowed = lambda path: path.startswith(f"{HOME}/.kittystory/characters/")  # noqa: E731
    return migrate.StagingDisk(disk, tmp_path / "staging", allowed, HOME)


def test_the_staging_disk_writes_only_into_its_folder(world, tmp_path):
    stage = staging(world, tmp_path)
    stage.write_file("~/.kittystory/characters/emma.toml", 'name = "Emma"\n')
    assert (tmp_path / "staging/home/danika/.kittystory/characters/emma.toml").is_file()
    assert not kitty(world, "characters").exists()             # the world is untouched
    assert stage.read_file(f"{HOME}/.kittystory/characters/emma.toml")["text"] == 'name = "Emma"\n'
    assert stage.read_file("~/.kittystory/shared.md")["text"] == "we all met\n"   # the world's
    names = [e["name"] for e in stage.list_dir("~/.kittystory")]
    assert "characters" in names and "chars" in names
    found = [e["path"] for e in stage.find("~/.kittystory", "*.toml")["entries"]]
    assert found == [f"{HOME}/.kittystory/characters/emma.toml"]
    for path in ("~/.kittystory/shared.md", "/etc/passwd", "/.hallux/memory.md",
                 "~/.kittystory/memories/emma.md"):
        with pytest.raises(OSError):
            stage.write_file(path, "x")
    assert (world / "home/danika/.kittystory/shared.md").read_text() == "we all met\n"


def test_copy_copies_the_bytes(world, tmp_path):
    stage = staging(world, tmp_path)
    stage.copy("~/.kittystory/chars/Emma/memory.md", "~/.kittystory/characters/emma.md")
    copied = tmp_path / "staging/home/danika/.kittystory/characters/emma.md"
    assert copied.read_text() == BIG
    assert stage.copy_problems() == []
    copied.write_text("changed")
    assert stage.copy_problems() == [f"{HOME}/.kittystory/characters/emma.md isn't "
                                     f"{HOME}/.kittystory/chars/Emma/memory.md byte for byte"]
    with pytest.raises(OSError):
        stage.copy("~/.kittystory/chars/Emma", "~/.kittystory/characters/x.md")    # a folder


# ---------------------------------------------------------------- an update with a migration

def test_an_update_migrates_and_a_rollback_brings_back_1x(world, store, tmp_path):
    update(store, tmp_path)
    before = {p.relative_to(world).as_posix(): p.read_bytes() for p in kitty(world).rglob("*")
              if p.is_file()}
    model = StandIn(planner(), migrator())
    code, said = hpm(world, store, "update", "kittystory", "--accept-migration", model=model)
    assert code == 0, said
    assert (world / "usr/local/bin/kittystory").read_text() == "the 2.0 card: characters/\n"
    assert not kitty(world, "chars").exists()                  # the old path went
    assert kitty(world, "shared.md").read_text() == "we all met\n"
    for name, (char, memory) in CHARS.items():
        assert kitty(world, f"memories/{name.lower()}.md").read_text() == memory
        assert f'name = "{name}"' in kitty(world, f"characters/{name.lower()}.toml").read_text()
    assert BIG not in "".join(model.messages)                  # the big memory never went to it
    entry = record(world)["kittystory"]
    assert (entry["version"], entry["data_format"]) == ("2.0", 2)
    assert f"{HOME}/.kittystory/memories/emma.md" in entry["files"]
    assert not (world / ".hallux/hpm/staging").exists() or not any(
        (world / ".hallux/hpm/staging").iterdir())
    assert len(rec.backups(Disk(world))) == 2                  # the install, and this update's
    assert any("6 files in, 6 old ones out" in line for line in said)

    assert hpm(world, store, "rollback", "kittystory")[0] == 0
    after = {p.relative_to(world).as_posix(): p.read_bytes() for p in kitty(world).rglob("*")
             if p.is_file()}
    assert after == before
    assert (world / "usr/local/bin/kittystory").read_text() == "the 1.0 card\n"
    entry = record(world)["kittystory"]
    assert (entry["version"], entry["data_format"]) == ("1.0", 1)


def test_cancel_at_the_plan_changes_nothing(world, store, tmp_path):
    update(store, tmp_path)
    q = Said("q", interactive=True)
    code, said = hpm(world, store, "update", "kittystory", "--yes", q=q,
                     model=StandIn(planner()))
    assert code == 0
    assert chars(world) == ["Emma", "Lucy", "emilly"]
    assert not kitty(world, "characters").exists()
    assert (world / "usr/local/bin/kittystory").read_text() == "the 1.0 card\n"
    assert record(world)["kittystory"]["data_format"] == 1
    assert len(rec.backups(Disk(world))) == 1                  # only the install's
    assert not any((world / ".hallux/hpm/staging").iterdir())
    assert any("Emma" in line and "→" in line for line in said)
    assert any("you cancelled its migration" in line for line in said)


def test_roll_back_at_the_end_and_look_first(world, store, tmp_path):
    update(store, tmp_path)
    q = Said("", "l", "r", interactive=True)
    code, said = hpm(world, store, "update", "kittystory", "--yes", q=q,
                     model=StandIn(planner(), migrator()))
    assert chars(world) == ["Emma", "Lucy", "emilly"]
    assert not kitty(world, "characters").exists()
    assert record(world)["kittystory"]["version"] == "1.0"
    assert len(rec.backups(Disk(world))) == 1
    assert any(f"── ~/.kittystory/memories/emma.md  (copy of ~/.kittystory/chars/Emma/memory.md)"
               in line for line in said)
    assert any('name = "Lucy"' in line for line in said)
    assert any("you rolled its migration back" in line for line in said)


def test_a_check_that_fails_is_shown_and_accept_still_asks(world, store, tmp_path):
    update(store, tmp_path)
    q = Said("", "", interactive=True)
    code, said = hpm(world, store, "update", "kittystory", "--yes", q=q,
                     model=StandIn(planner(), migrator(held=False, leave_out="Lucy")))
    text = "\n".join(said)
    assert "✗ every file the plan named is staged: missing: ~/.kittystory/characters/lucy.toml" in text
    assert "1 is missing  (the AI)" in text
    assert any(a.startswith("Enter accept") for a in q.asked)
    assert record(world)["kittystory"]["version"] == "2.0"     # accepted, as asked


def test_accept_migration_refuses_when_a_check_fails(world, store, tmp_path):
    update(store, tmp_path)
    code, said = hpm(world, store, "update", "kittystory", "--accept-migration",
                     model=StandIn(planner(), migrator(held=False)))
    assert code == 0                                           # skipped, not failed
    assert chars(world) == ["Emma", "Lucy", "emilly"]
    assert record(world)["kittystory"]["version"] == "1.0"
    assert any("didn't hold" in line for line in said)


def test_without_a_terminal_the_flag_is_named(world, store, tmp_path, capsys):
    update(store, tmp_path)
    code, _ = hpm(world, store, "update", "kittystory", model=StandIn())
    assert code == 1
    assert "--accept-migration" in capsys.readouterr().err
    assert chars(world) == ["Emma", "Lucy", "emilly"]
    assert len(rec.backups(Disk(world))) == 1


def test_a_plan_hpm_cant_read_is_shown_once_then_fails(world, store, tmp_path):
    update(store, tmp_path)
    model = StandIn(says("I will move them."), says("still no JSON"))
    code, said = hpm(world, store, "update", "kittystory", "--accept-migration", model=model)
    assert len(model.messages) == 2 and "hpm couldn't take that plan" in model.messages[1]
    assert any("its migration failed" in line or "can't be used" in line for line in said)
    assert chars(world) == ["Emma", "Lucy", "emilly"]
    assert len(rec.backups(Disk(world))) == 1


def test_two_notes_in_a_row(world, store, tmp_path):
    three = APP2.replace("data_format = 2", "data_format = 3").replace(
        '"~/.kittystory/characters/*.toml", ', '"~/.kittystory/people/*.toml", ')
    note2 = ("# 2 → 3\nCharacters move to people/.\n\nChecks:\n- every character is in people/\n\n"
             "Old paths: ~/.kittystory/characters/\n")
    put(store, tmp_path, three.replace("data = [", 'data = ["~/.kittystory/characters/*.toml", '),
        {"/usr/local/bin/kittystory": "3.0\n"}, "3.0", {"1-to-2.md": NOTE, "2-to-3.md": note2})

    def plan3():
        async def turn(session, message):
            found = json.loads(await call(session, "list_dir", path="~/.kittystory/characters"))
            rows = [{"what": e["name"], "old": [f"~/.kittystory/characters/{e['name']}"],
                     "new": [f"~/.kittystory/people/{e['name']}"]} for e in found]
            return json.dumps({"rows": rows})
        return turn

    def move3():
        async def turn(session, message):
            found = json.loads(await call(session, "list_dir", path="~/.kittystory/characters"))
            for e in found:
                await call(session, "copy", **{"from": f"~/.kittystory/characters/{e['name']}",
                                               "to": f"~/.kittystory/people/{e['name']}"})
            return json.dumps({"checks": [{"check": "every character is in people/", "held": True}]})
        return turn

    model = StandIn(planner(), migrator(), plan3(), move3())
    code, said = hpm(world, store, "update", "kittystory", "--accept-migration", model=model)
    assert code == 0, said
    assert sorted(p.name for p in kitty(world, "people").iterdir()) == [
        "emilly.toml", "emma.toml", "lucy.toml"]
    assert not kitty(world, "characters").exists()             # a step on the way: never landed
    assert not kitty(world, "chars").exists()
    assert kitty(world, "memories/emma.md").read_text() == BIG
    assert record(world)["kittystory"]["data_format"] == 3


# ---------------------------------------------------------------- data coming in

CHARS_PACKAGE = '''name = "kittystory-chars"
version = "{version}"
for = "kittystory"
[files]
data = ["~/.kittystory/chars/*/char.md", "~/.kittystory/chars/*/memory.md"]
'''


def test_incoming_data_is_migrated_with_the_apps_note(world, store, tmp_path):
    update(store, tmp_path)
    assert hpm(world, store, "update", "kittystory", "--accept-migration",
               model=StandIn(planner(), migrator()))[0] == 0
    put(store, tmp_path, CHARS_PACKAGE, {"~/.kittystory/chars/Mia/char.md": "name: Mia\npack: tsundere\n",
                                         "~/.kittystory/chars/Mia/memory.md": "Mia's day\n"}, "1.0")
    plan = plan_install(world, store, [Want("kittystory-chars")])
    assert plan.items[0].incoming is not None and not plan.items[0].migrate
    plan.close()
    code, said = hpm(world, store, "install", "kittystory-chars", "--yes", "--accept-migration",
                     model=StandIn(planner(), migrator()))
    assert code == 0, said
    assert kitty(world, "characters/mia.toml").read_text().startswith('name = "Mia"')
    assert kitty(world, "memories/mia.md").read_text() == "Mia's day\n"
    assert not kitty(world, "chars").exists()
    entry = record(world)["kittystory-chars"]
    assert entry["data_format"] == 2
    assert f"{HOME}/.kittystory/memories/mia.md" in entry["files"]
    assert any("data coming in" in line for line in said)


def test_incoming_data_whose_app_has_no_note(world, store, tmp_path):
    entry = record(world)
    entry["kittystory"]["data_format"] = 2                     # as if, with no note anywhere
    rec.save(Disk(world), entry)
    put(store, tmp_path, CHARS_PACKAGE, {"~/.kittystory/chars/Mia/char.md": "x\n"}, "1.0")
    item = plan_install(world, store, [Want("kittystory-chars")]).items[0]
    assert "no migration from data format 1" in item.blocked


# ---------------------------------------------------------------- publish

def test_publish_refuses_a_hole_in_the_chain(world, store, tmp_path, capsys):
    disk = Disk(world)
    text = APP2.format(version="1.0").replace("data_format = 2", "data_format = 3")
    disk.write_file("/usr/local/share/hpm/kittystory/hpm.toml", text, parents=True)
    disk.write_file("/usr/local/share/hpm/kittystory/migrations/1-to-2.md", NOTE, parents=True)
    (kitty(world, "characters")).mkdir()
    kitty(world, "characters/emma.toml").write_text("x\n")
    kitty(world, "memories").mkdir()
    kitty(world, "memories/emma.md").write_text("x\n")
    code, said = hpm(world, store, "publish", "kittystory", "--yes", "--changelog", "x")
    assert code == 1
    err = capsys.readouterr().err
    assert "no migration from data format 2 (migrations/2-to-3.md)" in err
    assert store.latest("kittystory").manifest().data_format == 1      # nothing published


def test_publish_offers_the_note_when_the_data_moved(world, store, tmp_path, capsys):
    disk = Disk(world)
    text = APP1.format(version="1.0") + 'data = ["~/.kittystory/characters/*.toml"]\n'
    disk.write_file("/usr/local/share/hpm/kittystory/hpm.toml", text)
    kitty(world, "characters").mkdir()
    kitty(world, "characters/emma.toml").write_text('name = "Emma"\n')
    code, _ = hpm(world, store, "publish", "kittystory", "--yes", "--changelog", "x")
    assert code == 1
    assert "--write-migration" in capsys.readouterr().err

    target = "/usr/local/share/hpm/kittystory/migrations/1-to-2.md"
    model = StandIn(says_after_writing(target, NOTE))
    code, said = hpm(world, store, "publish", "kittystory", "--yes", "--changelog", "x",
                     "--write-migration", model=model)
    assert code == 0, said
    released = store.latest("kittystory")
    assert str(released.version) == "2.0"
    assert released.manifest().data_format == 2
    assert [n.name for n in migrate.release_notes(released)] == ["1-to-2.md"]
    assert any("never ran on real data" in line for line in said)
    assert "release_read_file" in " ".join(model.options[0].allowed_tools)


def says_after_writing(path, text):
    async def turn(session, message):
        await call(session, "write_file", path=path, content=text)
        return "chars/ goes to characters/"
    return turn


# ---------------------------------------------------------------- in the Packages tab

def tab_and_panel(world, store, model):
    from test_panel import StandIn as Blank

    from hallux.hpm.running import Installs
    from hallux.panel import Panel
    from hallux.panel_tabs.packages import PackagesTab
    installs = Installs(Disk(world), store)
    installs.client_factory = model
    tab = PackagesTab(installs.watch, installs.catalog, installs.installed,
                      installs.plan_install, installs.plan_remove, installs.go, installs.stop,
                      installs.back, installs.migration_go, installs.migration_cancel)
    panel = Panel([Blank("Agents"), tab, Blank("Config")])
    installs.changed = panel.invalidate
    return installs, tab, panel


async def until(installs, *states, seconds=5):
    import asyncio
    for _ in range(int(seconds / 0.02)):
        if installs.watch().state in states:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"still {installs.watch().state}, not {states}")


def shown(panel):
    from test_panel import drawn
    return "\n".join(row for row in drawn(panel) if row.strip())


def tick(tab, name):
    tab.model.cursor = [i for i, (c, k) in enumerate(tab.model.entries())
                        if c.name == name and k is None][0]


def test_the_tab_migrates_with_enter_and_looks_with_l(world, store, tmp_path):
    from test_panel import session

    from hallux.hpm.running import ASKING, DONE, MIGRATION
    update(store, tmp_path)
    installs, tab, panel = tab_and_panel(world, store, StandIn(planner(), migrator()))

    async def script(press):
        await press("g")
        tick(tab, "kittystory")
        await press(" ")
        await press("\r")
        await until(installs, ASKING)
        await press("")
        assert "its data migrates 1 → 2 first, with the AI" in shown(panel)
        await press("\r")                                  # on to the migration
        assert installs.watch().state == MIGRATION
        await press("")
        assert "kittystory's data is in format 1; kittystory 2.0 needs 2." in shown(panel)
        assert tab.typing
        await press("c")                                   # no tab's letter here
        assert panel.tab is tab
        await press("\r")                                  # let the AI start: its plan
        await until(installs, MIGRATION)
        await press("")
        text = shown(panel)
        assert "kittystory data 1 → 2" in text and "Emma" in text and "(in ~/.kittystory/)" in text
        assert "chars/Emma/ → characters/emma.toml · memories/emma.md" in text
        await press("\r")                                  # migrate
        await until(installs, MIGRATION)
        await press("")
        text = shown(panel)
        assert "6 files staged (3 written, 3 copied) · 6 of 6 checks held" in text
        assert "accept removes 6 old file(s): ~/.kittystory/chars/" in text
        assert not kitty(world, "characters").exists()     # nothing in the world yet
        await press("l")
        await press("")
        assert "── ~/.kittystory/characters/emma.toml" in shown(panel)
        assert "── ~/.kittystory/characters/emilly.toml" in shown(panel)
        await press("\x1b[B")                             # ↓ scrolls the staged files
        assert "── ~/.kittystory/characters/emilly.toml" not in shown(panel)
        await press("l")
        await press("\r")                                  # accept
        await until(installs, DONE)
        await press("")
        text = shown(panel)
        assert "✓ kittystory's data: 6 files in, 6 old ones out; format 2" in text
        assert "1 updated" in text
        await press("\r")
        return installs.waiting()
    notes = session(panel, script)
    assert notes[0]["data_migrated"] == {          # the machine is told where its data is now
        "from": 1, "to": 2, "gone": ["~/.kittystory/chars/"],
        "into": ["~/.kittystory/characters/", "~/.kittystory/memories/"]}
    assert record(world)["kittystory"]["data_format"] == 2
    assert kitty(world, "memories/emma.md").read_text() == BIG
    assert not kitty(world, "chars").exists()


def test_q_at_the_tabs_plan_and_esc_at_its_checks(world, store, tmp_path):
    from test_panel import ESC, session

    from hallux.hpm.running import ASKING, DONE, MIGRATION
    update(store, tmp_path)
    for keys in (("\r", "q"), ("\r", "\r", ESC)):
        installs, tab, panel = tab_and_panel(world, store, StandIn(planner(), migrator()))

        async def script(press):
            await press("g")
            tick(tab, "kittystory")
            await press(" ")
            await press("\r")
            await until(installs, ASKING)
            await press("\r")
            for key in keys:
                await until(installs, MIGRATION)
                await press(key)
            await until(installs, DONE)
            await press("")
            text = shown(panel)
            assert "1 skipped" in text and "nothing of it was written" in text
            assert panel.tab is tab                        # Esc cancelled; the panel stays
            await press("\r")
        session(panel, script)
        assert chars(world) == ["Emma", "Lucy", "emilly"]
        assert not kitty(world, "characters").exists()
        assert record(world)["kittystory"]["version"] == "1.0"
        assert len(rec.backups(Disk(world))) == 1
        assert not any((world / ".hallux/hpm/staging").iterdir())
