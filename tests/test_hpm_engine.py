"""The install engine (hallux/hpm/engine.py): plans and their marks, apply, many packages
at once, backups and rollback, remove, adopt. Packages are packed straight into a store of
their own; every world is a temporary folder."""
import errno
import os

import pytest

from hallux.disk import Disk
from hallux.hpm import engine
from hallux.hpm import record as rec
from hallux.hpm.archive import pack
from hallux.hpm.engine import (
    BOTH, FAIL, KEEP, OVERWRITE, REMOVE, REPLACE, SKIP, Want, apply, plan_adopt, plan_install,
    plan_remove, rollback,
)
from hallux.hpm.store import Store
from hallux.hpm.world import HpmError

APP_FILES = {
    "/usr/local/bin/kittystory": "# kittystory\nthe card\n",
    "/usr/local/share/apps/kittystory/index.html": "<html></html>\n",
    "/usr/local/share/apps/kittystory/app.js": "// 1.4\n",
    "/usr/local/share/apps/kittystory/data/state.json": "{}\n",
}
APP = '''name = "kittystory"
version = "{version}"
data_format = {fmt}
memory_line = "kittystory: split-screen chat with characters"
requires.addons = ["web"]
[files]
app  = ["/usr/local/bin/kittystory", "/usr/local/share/apps/kittystory/**"]
seed = ["/usr/local/share/apps/kittystory/data/state.json"]
[extras]
packs      = {{ package = "kittystory-packs", default = true }}
characters = {{ package = "kittystory-chars", default = true, needs = ["packs"] }}
memories   = {{ package = "kittystory-memories", default = false, needs = ["characters"] }}
'''
PACKS_FILES = {"~/.kittystory/packs/tsundere.pack": "tsundere\n",
               "~/.kittystory/packs/metal-head.pack": "metal\n"}
PACKS = '''name = "kittystory-packs"
version = "{version}"
data_format = {fmt}
for = "kittystory"
[files]
data = ["~/.kittystory/packs/*.pack"]
'''
CHARS_FILES = {"~/.kittystory/chars/Emma/char.md": "Emma\n",
               "~/.kittystory/chars/Lucy/char.md": "Lucy\n"}
CHARS = '''name = "kittystory-chars"
version = "{version}"
data_format = {fmt}
for = "kittystory"
[files]
data = ["~/.kittystory/chars/*/char.md"]
'''
MEMORIES_FILES = {"~/.kittystory/chars/Emma/memory.md": "2026-10-03 met the user\n",
                  "~/.kittystory/shared.md": "shared\n"}
MEMORIES = '''name = "kittystory-memories"
version = "{version}"
for = "kittystory"
private = true
[files]
data = ["~/.kittystory/chars/*/memory.md", "~/.kittystory/shared.md"]
'''


def to_member(path):
    return ("files/home/" + path[2:]) if path.startswith("~/") else ("files/root" + path)


def put(store, tmp_path, manifest, files=None, version="1.4", fmt=1, extra=""):
    """A release packed by hand and added to the store."""
    text = manifest.format(version=version, fmt=fmt) + extra
    name = text.split('"')[1]
    folder = tmp_path / "packages" / f"{name}-{version}"
    folder.mkdir(parents=True)
    (folder / "hpm.toml").write_text(text)
    (folder / "CHANGELOG.md").write_text(f"## {version}\n\nmade by a test\n")
    for path, content in (files or {}).items():
        target = folder / to_member(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return store.add(pack(folder, tmp_path / "packages" / f"{name}-{version}.hpm"))


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "store")
    put(store, tmp_path, APP, APP_FILES)
    put(store, tmp_path, PACKS, PACKS_FILES, version="1.0")
    put(store, tmp_path, CHARS, CHARS_FILES, version="1.1")
    put(store, tmp_path, MEMORIES, MEMORIES_FILES, version="1.0")
    return store


@pytest.fixture
def addons(tmp_path):
    folder = tmp_path / "addons"
    folder.mkdir()
    (folder / "web.py").write_text("raise SystemExit('never imported')\n")
    return folder


MEMORY = "# hallux memory\n## Invented programs\n- kittymusic: a player\n\n## Stable facts\n- x\n"


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "oliver-test"
    (root / ".hallux").mkdir(parents=True)
    (root / ".hallux/memory.md").write_text(MEMORY)
    (root / "etc").mkdir()
    (root / "etc/passwd").write_text("root:x:0:0::/root:/bin/bash\nuser:x:1000:1000::/home/user:/bin/bash\n")
    (root / "home/user").mkdir(parents=True)
    return root


def install(world, store, wants=None, answers=None, all_files=None, addons=None, user=None):
    plan = plan_install(world, store, wants or [Want("kittystory")], user=user, addons_folder=addons)
    return apply(plan, answers, all_files)


def actions(plan):
    return {a.path: a for item in plan.items for a in item.actions}


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file() and ".hallux" not in p.parts}


# ---------------------------------------------------------------- the world's user

def test_home_files_go_to_the_worlds_user(world, store, addons):
    outcome = install(world, store, addons=addons)
    assert (world / "home/user/.kittystory/packs/tsundere.pack").read_text() == "tsundere\n"
    assert (world / "home/user/.kittystory/chars/Emma/char.md").read_text() == "Emma\n"
    assert outcome.summary() == "3 installed"


def test_several_users(world, store):
    (world / "etc/passwd").write_text("a:x:1000:1000::/home/a:/bin/sh\nb:x:1001:1001::/home/b:/bin/sh\n")
    with pytest.raises(HpmError, match="say which with --user"):
        plan_install(world, store, [Want("kittystory")])
    install(world, store, user="b")
    assert (world / "home/b/.kittystory/packs/tsundere.pack").exists()


def test_no_home_for_home_files(world, store):
    os.remove(world / "etc/passwd")
    os.rmdir(world / "home/user")
    with pytest.raises(HpmError, match="no user home"):
        plan_install(world, store, [Want("kittystory")])
    install(world, store, [Want("kittystory", extras=())])      # the app alone needs none
    assert (world / "usr/local/bin/kittystory").exists()


# ---------------------------------------------------------------- what is wanted, in which order

def test_the_order_follows_needs(world, store):
    plan = plan_install(world, store, [Want("kittystory", extras=("characters",))])
    assert [i.name for i in plan.items] == ["kittystory", "kittystory-packs", "kittystory-chars"]
    assert plan.items[0].extras == ("packs", "characters")          # ticking characters ticks packs
    assert plan.items[2].needs == ("kittystory", "kittystory-packs")   # its app, and packs
    plan.close()


def test_a_data_package_alone_brings_its_app(world, store):
    plan = plan_install(world, store, [Want("kittystory-chars")])
    assert [i.name for i in plan.items] == ["kittystory", "kittystory-chars"]
    assert plan.items[0].extras == ()
    plan.close()


def test_an_unknown_extra(world, store):
    with pytest.raises(HpmError, match="kittystory has no extra sprites"):
        plan_install(world, store, [Want("kittystory", extras=("sprites",))])


def test_a_bundle_and_a_whole_store(world, store, tmp_path):
    put(store, tmp_path, 'name = "kittycalc"\nversion = "{version}"\n[files]\napp = ["/usr/local/bin/kittycalc"]\n',
        {"/usr/local/bin/kittycalc": "calc\n"}, version="1.0")
    put(store, tmp_path, 'name = "kitty-desktop"\nversion = "{version}"\nbundle = ["kittystory", "kittycalc"]\n',
        version="1.0")
    plan = plan_install(world, store, [Want("kitty-desktop")])
    assert [i.name for i in plan.items] == ["kittystory", "kittystory-packs", "kittystory-chars",
                                            "kittycalc"]
    plan.close()
    plan = plan_install(world, store, [Want("local/")])
    assert sorted(i.name for i in plan.items) == ["kittycalc", "kittystory", "kittystory-chars",
                                                  "kittystory-packs"]
    plan.close()
    with pytest.raises(HpmError, match="there is no store 'danika'"):
        plan_install(world, store, [Want("danika/")])


def test_needs_in_a_circle(world, store, tmp_path):
    put(store, tmp_path, 'name = "a"\nversion = "{version}"\nrequires.packages = ["b"]\n', version="1.0")
    put(store, tmp_path, 'name = "b"\nversion = "{version}"\nrequires.packages = ["a"]\n', version="1.0")
    with pytest.raises(HpmError, match="in a circle: a → b → a"):
        plan_install(world, store, [Want("a")])


def test_a_package_missing_from_the_store(world, store):
    with pytest.raises(HpmError, match="no package kittymusic in the store"):
        plan_install(world, store, [Want("kittymusic")])


# ---------------------------------------------------------------- what is checked first

def test_addons_are_found_by_file_name_and_never_imported(world, store, addons):
    plan = plan_install(world, store, [Want("kittystory")], addons_folder=addons)
    assert plan.notes == []
    plan.close()
    (world / ".hallux/config.toml").write_text("addons = []\n")
    plan = plan_install(world, store, [Want("kittystory")], addons_folder=addons)
    assert plan.notes == ["kittystory needs the web addon, which this world doesn't get (its "
                          "config's addons); it installs, but that part won't work there"]
    plan.close()
    plan = plan_install(world, store, [Want("kittystory")], addons_folder=addons.parent / "none")
    assert "which Hallux doesn't have" in plan.notes[0]
    plan.close()


def test_a_newer_data_format_in_the_world_is_refused(world, store, tmp_path):
    put(store, tmp_path, APP, APP_FILES, version="2.0", fmt=2)
    install(world, store, [Want("kittystory", version="2.0", extras=())])
    plan = plan_install(world, store, [Want("kittystory", version="1.4", extras=())])
    assert "newer than 1" in plan.items[0].blocked
    plan.close()


def test_an_older_data_format_needs_a_migration(world, store, tmp_path):
    install(world, store, [Want("kittystory", extras=())])
    put(store, tmp_path, APP, APP_FILES, version="2.0", fmt=2)
    plan = plan_install(world, store, [Want("kittystory", extras=())])
    assert "has no migration from data format 1" in plan.items[0].blocked   # no note
    outcome = apply(plan)
    assert outcome.done[0].status == "failed" and "migration" in outcome.done[0].why
    assert rec.load(Disk(world))["kittystory"]["version"] == "1.4"


def test_incoming_data_in_an_older_format_needs_a_migration(world, store, tmp_path):
    put(store, tmp_path, APP, APP_FILES, version="2.0", fmt=2)
    plan = plan_install(world, store, [Want("kittystory", extras=("packs",))])
    assert "has data in format 1, and kittystory here has 2" in plan.items[1].blocked
    plan.close()


# ---------------------------------------------------------------- the marks

def test_new_files_are_written_and_recorded(world, store):
    outcome = install(world, store)
    record = rec.load(Disk(world))
    entry = record["kittystory"]
    assert entry["version"] == "1.4" and entry["extras"] == ["packs", "characters"]
    assert entry["files"]["/usr/local/bin/kittystory"]["kind"] == "app"
    assert entry["files"]["/usr/local/share/apps/kittystory/data/state.json"]["kind"] == "seed"
    assert entry["files"]["/usr/local/share/hpm/kittystory/hpm.toml"]["kind"] == "meta"
    assert record["kittystory-packs"]["files"]["/home/user/.kittystory/packs/tsundere.pack"] == {
        "kind": "data", "sha256": entry and record["kittystory-packs"]["files"][
            "/home/user/.kittystory/packs/tsundere.pack"]["sha256"]}
    assert (world / "usr/local/share/hpm/kittystory/hpm.toml").exists()
    assert (world / "usr/local/share/hpm/kittystory/CHANGELOG.md").exists()
    assert outcome.done[0].places == ("/usr/local/bin/kittystory",
                                      "/usr/local/share/apps/kittystory/",
                                      "/usr/local/share/apps/kittystory/data/",
                                      "/usr/local/share/hpm/kittystory/")


def test_the_same_file_is_skipped_silently(world, store):
    (world / "home/user/.kittystory/packs").mkdir(parents=True)
    (world / "home/user/.kittystory/packs/tsundere.pack").write_text("tsundere\n")
    plan = plan_install(world, store, [Want("kittystory")])
    assert actions(plan)["/home/user/.kittystory/packs/tsundere.pack"].mark == "same"
    assert plan.questions == []
    apply(plan)
    assert "/home/user/.kittystory/packs/tsundere.pack" in rec.load(Disk(world))[
        "kittystory-packs"]["files"]


def test_a_different_file_hpm_didnt_write_is_asked(world, store):
    (world / "home/user/.kittystory/packs").mkdir(parents=True)
    (world / "home/user/.kittystory/packs/metal-head.pack").write_text("my own metal\n")
    (world / "usr/local/bin").mkdir(parents=True)
    (world / "usr/local/bin/kittystory").write_text("the machine's own card\n")
    plan = plan_install(world, store, [Want("kittystory")])
    pack_q = actions(plan)["/home/user/.kittystory/packs/metal-head.pack"]
    card_q = actions(plan)["/usr/local/bin/kittystory"]
    assert (pack_q.mark, pack_q.op, pack_q.choices, pack_q.default) == (
        "foreign", "ask", (OVERWRITE, SKIP, BOTH), SKIP)              # data: skip by default
    assert card_q.default == OVERWRITE
    assert list(plan.grouped()) == [("kittystory", "/usr/local/bin"),
                                    ("kittystory-packs", "/home/user/.kittystory/packs")]
    with pytest.raises(HpmError, match="metal-head.pack .* has no answer"):
        apply(plan_install(world, store, [Want("kittystory")]), {"/usr/local/bin/kittystory": OVERWRITE})
    apply(plan, {"/usr/local/bin/kittystory": OVERWRITE,
                 "/home/user/.kittystory/packs/metal-head.pack": BOTH})
    assert (world / "usr/local/bin/kittystory").read_text() == "# kittystory\nthe card\n"
    assert (world / "home/user/.kittystory/packs/metal-head.pack").read_text() == "my own metal\n"
    assert (world / "home/user/.kittystory/packs/metal-head.hpm-new.pack").read_text() == "metal\n"


def test_skip_leaves_it_and_doesnt_record_it(world, store):
    (world / "usr/local/bin").mkdir(parents=True)
    (world / "usr/local/bin/kittystory").write_text("mine\n")
    install(world, store, all_files=SKIP)
    assert (world / "usr/local/bin/kittystory").read_text() == "mine\n"
    assert "/usr/local/bin/kittystory" not in rec.load(Disk(world))["kittystory"]["files"]


def test_an_answer_that_isnt_a_choice(world, store):
    (world / "usr/local/bin").mkdir(parents=True)
    (world / "usr/local/bin/kittystory").write_text("mine\n")
    with pytest.raises(HpmError, match="'merge' isn't one of overwrite, skip, both"):
        install(world, store, answers={"/usr/local/bin/kittystory": "merge"})


def test_a_folder_or_link_in_the_way(world, store):
    (world / "usr/local/bin/kittystory").mkdir(parents=True)          # a folder where the card goes
    (world / "usr/local/share/apps").mkdir(parents=True)
    (world / "usr/local/share/apps/kittystory").write_text("a file where a folder must be\n")
    plan = plan_install(world, store, [Want("kittystory", extras=())])
    marks = {p: a.mark for p, a in actions(plan).items() if a.op == "ask"}
    assert marks["/usr/local/bin/kittystory"] == "in-the-way"
    assert marks["/usr/local/share/apps/kittystory/app.js"] == "in-the-way"
    assert actions(plan)["/usr/local/bin/kittystory"].choices == (SKIP, FAIL)
    outcome = apply(plan, all_files=SKIP)
    assert outcome.summary() == "1 installed"
    assert (world / "usr/local/bin/kittystory").is_dir()


def test_a_seed_that_is_there_is_never_touched(world, store):
    (world / "usr/local/share/apps/kittystory/data").mkdir(parents=True)
    (world / "usr/local/share/apps/kittystory/data/state.json").write_text('{"chat": "mine"}\n')
    plan = plan_install(world, store, [Want("kittystory", extras=())])
    assert actions(plan)["/usr/local/share/apps/kittystory/data/state.json"].mark == "seed-kept"
    apply(plan)
    assert "mine" in (world / "usr/local/share/apps/kittystory/data/state.json").read_text()


def test_loud_files(world, store, tmp_path):
    put(store, tmp_path, 'name = "theme"\nversion = "{version}"\nrules = ["All is pink."]\n'
        '[files]\napp = ["~/.bashrc", "/usr/local/bin/kittymusic", "/usr/local/bin/theme"]\n',
        {"~/.bashrc": "alias ls='ls --color'\n", "/usr/local/bin/kittymusic": "taken over\n",
         "/usr/local/bin/theme": "its own card\n"}, version="1.0")
    plan = plan_install(world, store, [Want("theme")])
    assert sorted(plan.loud) == [
        ("theme", "", "it adds rules, which change the whole machine: All is pink."),
        ("theme", "/home/user/.bashrc", "the machine reads it at every boot"),
        ("theme", "/usr/local/bin/kittymusic",
         "it is a card in /usr/local/bin, and not this package's own")]
    apply(plan)
    assert "1. All is pink. [hpm theme 1.0]" in Disk(world).memory_read()["text"]


def test_a_package_with_files_its_manifest_doesnt_list(world, store, tmp_path):
    put(store, tmp_path, 'name = "sly"\nversion = "{version}"\n[files]\napp = ["/usr/local/bin/sly"]\n',
        {"/usr/local/bin/sly": "card\n", "/etc/motd": "surprise\n"}, version="1.0")
    plan = plan_install(world, store, [Want("sly")])
    assert plan.items[0].blocked.startswith("it carries files its manifest doesn't list: /etc/motd")
    assert apply(plan).summary().startswith("1 failed: sly")
    assert not (world / "etc/motd").exists()


def test_a_home_that_links_out_of_the_world(world, store, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    os.rmdir(world / "home/user")
    (world / "home/user").symlink_to(outside)
    plan = plan_install(world, store, [Want("kittystory-packs")])
    assert "can't be written" in plan.items[1].blocked
    apply(plan)
    assert list(outside.iterdir()) == []


# ---------------------------------------------------------------- the memory line

def test_the_memory_line_is_written(world, store):
    install(world, store)
    assert rec.memory_lines(Disk(world), "kittystory") == [
        "- kittystory: split-screen chat with characters [hpm kittystory 1.4]"]


def test_the_old_untagged_line_is_asked_about(world, store):
    old = "- kittystory (was lt-love): split-screen chat; ~/.kittystory/"
    (world / ".hallux/memory.md").write_text(MEMORY.replace("- kittymusic", old + "\n- kittymusic"))
    plan = plan_install(world, store, [Want("kittystory")])
    assert [i.old_line for i in plan.memory_questions()] == [old]
    apply(plan)                                                       # replaced by default
    assert old not in Disk(world).memory_read()["text"]
    rollback(world, "kittystory")
    assert old in Disk(world).memory_read()["text"]


def test_the_old_line_kept(world, store):
    old = "- kittystory: the machine's own words"
    (world / ".hallux/memory.md").write_text(MEMORY.replace("- kittymusic", old + "\n- kittymusic"))
    install(world, store, answers={"memory:kittystory": KEEP})
    text = Disk(world).memory_read()["text"]
    assert old in text and "[hpm kittystory 1.4]" in text


# ---------------------------------------------------------------- updates

def test_an_update_replaces_ours_asks_about_changed_and_keeps_data(world, store, tmp_path):
    install(world, store)
    (world / "usr/local/share/apps/kittystory/index.html").write_text("<html>mine</html>\n")
    (world / "home/user/.kittystory/packs/tsundere.pack").write_text("tsundere, my way\n")
    newer = dict(APP_FILES, **{"/usr/local/share/apps/kittystory/app.js": "// 1.5\n",
                               "/usr/local/share/apps/kittystory/index.html": "<html>1.5</html>\n"})
    put(store, tmp_path, APP, newer, version="1.5")
    put(store, tmp_path, PACKS, {k: v.upper() for k, v in PACKS_FILES.items()}, version="1.1")
    plan = plan_install(world, store, [Want("kittystory")])
    marks = {p: (a.mark, a.op) for p, a in actions(plan).items()}
    assert marks["/usr/local/share/apps/kittystory/app.js"] == ("ours", "write")
    assert marks["/usr/local/share/apps/kittystory/index.html"] == ("changed", "ask")
    assert marks["/home/user/.kittystory/packs/tsundere.pack"] == ("data-kept", "skip")
    assert marks["/home/user/.kittystory/packs/metal-head.pack"] == ("data-kept", "skip")
    outcome = apply(plan, all_files=SKIP)
    assert outcome.summary() == "2 updated"               # kittystory-chars 1.1 is there as it is
    assert (world / "usr/local/share/apps/kittystory/app.js").read_text() == "// 1.5\n"
    assert (world / "usr/local/share/apps/kittystory/index.html").read_text() == "<html>mine</html>\n"
    assert (world / "home/user/.kittystory/packs/tsundere.pack").read_text() == "tsundere, my way\n"
    assert (world / "home/user/.kittystory/packs/metal-head.pack").read_text() == "metal\n"
    assert rec.memory_lines(Disk(world), "kittystory") == [
        "- kittystory: split-screen chat with characters [hpm kittystory 1.5]"]
    assert outcome.notes[0] == {"name": "kittystory", "version": "1.5", "was": "1.4",
                                "files": outcome.done[0].written,
                                "places": list(outcome.done[0].places)}


def test_an_update_removes_an_app_file_the_new_version_dropped(world, store, tmp_path):
    install(world, store, [Want("kittystory", extras=())])
    smaller = {k: v for k, v in APP_FILES.items() if not k.endswith("index.html")}
    put(store, tmp_path, APP, smaller, version="1.5")
    plan = plan_install(world, store, [Want("kittystory", extras=())])
    assert actions(plan)["/usr/local/share/apps/kittystory/index.html"].op == "remove"
    apply(plan)
    assert not (world / "usr/local/share/apps/kittystory/index.html").exists()


def test_an_update_asks_before_removing_a_dropped_file_you_changed(world, store, tmp_path):
    install(world, store, [Want("kittystory", extras=())])
    (world / "usr/local/share/apps/kittystory/index.html").write_text("mine\n")
    put(store, tmp_path, APP, {k: v for k, v in APP_FILES.items() if "index" not in k}, version="1.5")
    plan = plan_install(world, store, [Want("kittystory", extras=())])
    question = actions(plan)["/usr/local/share/apps/kittystory/index.html"]
    assert (question.choices, question.default) == ((REMOVE, KEEP), KEEP)
    apply(plan, {question.path: KEEP})
    assert (world / "usr/local/share/apps/kittystory/index.html").read_text() == "mine\n"
    assert question.path not in rec.load(Disk(world))["kittystory"]["files"]


# ---------------------------------------------------------------- backups and rollback

def test_the_backup_holds_exactly_what_is_overwritten(world, store, tmp_path):
    install(world, store, [Want("kittystory", extras=())])
    put(store, tmp_path, APP, dict(APP_FILES, **{"/usr/local/share/apps/kittystory/app.js": "// 1.5\n",
                                                 "/usr/local/share/apps/kittystory/new.js": "new\n"}),
        version="1.5")
    outcome = install(world, store, [Want("kittystory", extras=())])
    backup = rec.backups(Disk(world))[-1]
    assert backup.name == outcome.backup
    there = {p for p, i in backup.data["files"].items() if i["was"] == "there"}
    missing = {p for p, i in backup.data["files"].items() if i["was"] == "missing"}
    assert there == {"/usr/local/share/apps/kittystory/app.js",
                     "/usr/local/share/hpm/kittystory/hpm.toml",
                     "/usr/local/share/hpm/kittystory/CHANGELOG.md"}
    assert missing == {"/usr/local/share/apps/kittystory/new.js"}
    assert backup.data["entries"]["kittystory"]["version"] == "1.4"


def test_a_rollback_brings_the_files_the_record_and_the_line_back(world, store, tmp_path):
    install(world, store, [Want("kittystory", extras=())])
    before = snapshot(world)
    record_before = rec.load(Disk(world))
    put(store, tmp_path, APP, dict(APP_FILES, **{"/usr/local/share/apps/kittystory/app.js": "// 1.5\n",
                                                 "/usr/local/share/apps/kittystory/new.js": "new\n"}),
        version="1.5", extra="\n")
    install(world, store, [Want("kittystory", extras=())])
    assert rec.load(Disk(world))["kittystory"]["version"] == "1.5"
    outcome = rollback(world, "kittystory")
    assert outcome.done[0].status == "rolled back" and outcome.done[0].version == "1.4"
    assert snapshot(world) == before
    assert rec.load(Disk(world)) == record_before
    assert rec.memory_lines(Disk(world), "kittystory") == [
        "- kittystory: split-screen chat with characters [hpm kittystory 1.4]"]
    outcome = rollback(world, "kittystory")                         # the next one: before 1.4
    assert outcome.done[0].version is None
    assert "kittystory" not in rec.load(Disk(world))
    assert not (world / "usr/local/bin/kittystory").exists()
    assert rec.memory_lines(Disk(world), "kittystory") == []
    with pytest.raises(HpmError, match="no backup of kittystory"):
        rollback(world, "kittystory")


# ---------------------------------------------------------------- many packages at once

def many(store, tmp_path, count=15):
    for n in range(count):
        put(store, tmp_path, f'name = "kitty{n}"\nversion = "{{version}}"\n'
            + (f'requires.packages = ["kitty{n - 1}"]\n' if n == 8 else "")
            + f'[files]\napp = ["/usr/local/bin/kitty{n}"]\n',
            {f"/usr/local/bin/kitty{n}": f"card {n}\n"}, version="1.0")
    put(store, tmp_path, 'name = "all-kitties"\nversion = "{version}"\nbundle = ['
        + ", ".join(f'"kitty{n}"' for n in range(count)) + "]\n", version="1.0")


def test_one_failing_in_the_middle_skips_what_needs_it(world, store, tmp_path):
    many(store, tmp_path)
    (world / "usr/local/bin/kitty7").mkdir(parents=True)              # in the way of kitty7
    plan = plan_install(world, store, [Want("all-kitties")])
    assert [i.name for i in plan.items][:9] == [f"kitty{n}" for n in range(9)]
    outcome = apply(plan, all_files=FAIL)
    assert outcome.summary() == ("13 installed · 1 failed: kitty7 (/usr/local/bin/kitty7 is in "
                                 "the way) · 1 skipped: kitty8 (needs kitty7)")
    record = rec.load(Disk(world))
    assert record["kitty7"]["incomplete"] is True and "kitty8" not in record
    os.rmdir(world / "usr/local/bin/kitty7")
    outcome = install(world, store, [Want("kitty7"), Want("kitty8")])
    assert outcome.summary() == "2 installed"                        # kitty7 finished, kitty8 new
    assert "incomplete" not in rec.load(Disk(world))["kitty7"]


def test_a_full_disk_stops_everything(world, store, tmp_path, monkeypatch):
    many(store, tmp_path, count=5)
    real = engine.copy_whole
    calls = []

    def filling(source, target, *rest):
        calls.append(target)
        if len(calls) == 4:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(source, target, *rest)

    monkeypatch.setattr(engine, "copy_whole", filling)
    outcome = install(world, store, [Want("all-kitties")])
    statuses = [(d.name, d.status) for d in outcome.done]
    assert statuses[0] == ("kitty0", "installed")
    assert statuses[1] == ("kitty1", "failed") and outcome.done[1].why == "the disk is full"
    assert all(status == "skipped" for _, status in statuses[2:])
    assert outcome.done[2].why == "the disk was full"


def test_progress_is_told_after_each_package(world, store):
    told = []
    plan = plan_install(world, store, [Want("kittystory")])
    apply(plan, progress=told.append)
    assert [d.name for d in told] == ["kittystory", "kittystory-packs", "kittystory-chars"]


# ---------------------------------------------------------------- remove

def test_remove_takes_the_app_and_keeps_the_data(world, store):
    install(world, store)
    outcome = apply(plan_remove(world, "kittystory"))
    assert outcome.summary() == "1 removed" and outcome.notes[0]["removed"] is True
    assert not (world / "usr/local/bin/kittystory").exists()
    assert not (world / "usr/local/share/apps/kittystory/app.js").exists()
    assert sorted(p.name for p in (world / "usr/local/share/apps/kittystory").rglob("*")) == [
        "data", "state.json"]                                         # the seed stays
    assert not (world / "usr/local/share/hpm/kittystory").exists()   # its empty folders go
    assert (world / "usr/local/bin").is_dir()                         # never these
    assert (world / "home/user/.kittystory/packs/tsundere.pack").exists()
    record = rec.load(Disk(world))
    assert "kittystory" not in record and "kittystory-packs" in record
    assert rec.memory_lines(Disk(world), "kittystory") == []


def test_remove_keeps_the_seed(world, store):
    install(world, store, [Want("kittystory", extras=())])
    apply(plan_remove(world, "kittystory"))
    assert (world / "usr/local/share/apps/kittystory/data/state.json").exists()


def test_remove_asks_about_a_file_you_changed(world, store):
    install(world, store, [Want("kittystory", extras=())])
    (world / "usr/local/bin/kittystory").write_text("my card\n")
    plan = plan_remove(world, "kittystory")
    question = actions(plan)["/usr/local/bin/kittystory"]
    assert (question.mark, question.choices) == ("changed", (REMOVE, KEEP))
    apply(plan, {question.path: KEEP})
    assert (world / "usr/local/bin/kittystory").read_text() == "my card\n"


def test_remove_with_data_backs_it_up_and_a_rollback_brings_it_back(world, store):
    install(world, store)
    apply(plan_remove(world, "kittystory-packs", data=True))
    assert not (world / "home/user/.kittystory/packs").exists()
    assert (world / "home/user").is_dir()                             # the home stays
    rollback(world, "kittystory-packs")
    assert (world / "home/user/.kittystory/packs/tsundere.pack").read_text() == "tsundere\n"
    assert "kittystory-packs" in rec.load(Disk(world))


def test_remove_what_isnt_installed(world):
    with pytest.raises(HpmError, match="kittystory isn't installed in this world"):
        plan_remove(world, "kittystory")


# ---------------------------------------------------------------- adopt

def test_adopt_records_the_identical_files(world, store):
    for path, text in APP_FILES.items():                              # installed the old way
        (world / path.lstrip("/")).parent.mkdir(parents=True, exist_ok=True)
        (world / path.lstrip("/")).write_text(text)
    (world / "usr/local/share/apps/kittystory/app.js").write_text("// changed by the machine\n")
    old = "- kittystory: chat, installed by kittystory-web.update"
    (world / ".hallux/memory.md").write_text(MEMORY.replace("- kittymusic", old + "\n- kittymusic"))
    before = snapshot(world)
    outcome = apply(plan_adopt(world, store.latest("kittystory")))
    assert outcome.summary() == "1 adopted"
    assert snapshot(world) == before                                   # no file written
    entry = rec.load(Disk(world))["kittystory"]
    assert entry["adopted"] is True and entry["version"] == "1.4"
    assert "/usr/local/bin/kittystory" in entry["files"]
    assert "/usr/local/share/apps/kittystory/app.js" not in entry["files"]
    assert old not in Disk(world).memory_read()["text"]
    assert rec.memory_lines(Disk(world), "kittystory")
    plan = plan_install(world, store, [Want("kittystory", extras=())])  # the next update asks
    assert actions(plan)["/usr/local/share/apps/kittystory/app.js"].mark == "foreign"
    assert actions(plan)["/usr/local/bin/kittystory"].mark == "same"
    plan.close()


# ---------------------------------------------------------------- clean seed copies (fix 06)

NOTES = '''name = "kittynotes"
version = "{version}"
data_format = {fmt}
[files]
app  = ["/usr/local/bin/kittynotes"]
seed = ["/usr/local/share/apps/kittynotes/state.json", "~/.kittynotes/first.md"]
'''
NOTES_FILES = {"/usr/local/bin/kittynotes": "notes\n",
               "/usr/local/share/apps/kittynotes/state.json": '{"notes": []}\n',
               "~/.kittynotes/first.md": "# your first note\n"}
COPIES = {"/usr/local/share/apps/kittynotes/state.json":
          "usr/local/share/hpm/kittynotes/seed/usr/local/share/apps/kittynotes/state.json",
          "~/.kittynotes/first.md": "usr/local/share/hpm/kittynotes/seed/~/.kittynotes/first.md"}


def test_install_writes_a_clean_copy_of_each_seed(world, store, tmp_path):
    put(store, tmp_path, NOTES, NOTES_FILES, version="1.0")
    install(world, store, [Want("kittynotes")])
    files = rec.load(Disk(world))["kittynotes"]["files"]
    for machine, copy in COPIES.items():
        assert (world / copy).read_text() == NOTES_FILES[machine]
        assert files["/" + copy]["kind"] == "meta"
    (world / "usr/local/share/apps/kittynotes/state.json").write_text('{"notes": ["mine"]}\n')
    (world / "home/user/.kittynotes/first.md").write_text("my own note\n")
    (world / COPIES["~/.kittynotes/first.md"]).write_text("# a better first note\n")
    new = dict(NOTES_FILES, **{"/usr/local/bin/kittynotes": "notes 1.1\n",
                               "/usr/local/share/apps/kittynotes/state.json": '{"notes": [], "v": 2}\n'})
    put(store, tmp_path, NOTES, new, version="1.1")
    plan = plan_install(world, store, [Want("kittynotes")])
    marks = {a.path: (a.mark, a.op) for a in plan.items[0].actions}
    assert marks["/" + COPIES["/usr/local/share/apps/kittynotes/state.json"]] == ("ours", "write")
    assert marks["/" + COPIES["~/.kittynotes/first.md"]][1] == "ask"           # you changed it
    apply(plan, answers={"/" + COPIES["~/.kittynotes/first.md"]: SKIP})
    assert (world / COPIES["/usr/local/share/apps/kittynotes/state.json"]).read_text() == \
        '{"notes": [], "v": 2}\n'
    assert (world / "usr/local/share/apps/kittynotes/state.json").read_text() == \
        '{"notes": ["mine"]}\n'                                              # the seed: kept
    apply(plan_remove(world, "kittynotes"), all_files=REMOVE)
    assert not (world / COPIES["/usr/local/share/apps/kittynotes/state.json"]).exists()


def test_adopt_records_a_clean_copy_that_matches(world, store, tmp_path):
    put(store, tmp_path, NOTES, NOTES_FILES, version="1.0")
    for machine, copy in COPIES.items():
        (world / copy).parent.mkdir(parents=True, exist_ok=True)
        (world / copy).write_text(NOTES_FILES[machine])
    apply(plan_adopt(world, store.latest("kittynotes")))
    files = rec.load(Disk(world))["kittynotes"]["files"]
    assert all(files["/" + copy]["kind"] == "meta" for copy in COPIES.values())


# ---------------------------------------------------------------- where hpm's own files are

def test_hpms_files_are_only_in_its_hidden_folder(world, store):
    install(world, store)
    hidden = {p.relative_to(world / ".hallux").as_posix().split("/")[0]
              for p in (world / ".hallux").rglob("*") if p.is_file()}
    assert hidden == {"memory.md", "hpm"}
    assert (world / ".hallux/hpm/installed.json").is_file()
    assert len(list((world / ".hallux/hpm/backups").iterdir())) == 1


# ---------------------------------------------------------------- done when

def test_done_when(world, store, tmp_path):
    """kittystory with its packs and characters installs into a fresh world, updates to a
    newer version with one file changed by hand (asked about, not replaced), and is
    removed again with the data kept."""
    assert install(world, store).summary() == "3 installed"
    (world / "usr/local/share/apps/kittystory/index.html").write_text("<html>by hand</html>\n")
    put(store, tmp_path, APP, dict(APP_FILES, **{"/usr/local/share/apps/kittystory/index.html":
                                                 "<html>1.5</html>\n"}), version="1.5")
    plan = plan_install(world, store, [Want("kittystory", extras=())])
    assert [q.path for q in plan.questions] == ["/usr/local/share/apps/kittystory/index.html"]
    assert apply(plan, all_files=SKIP).summary() == "1 updated"
    assert (world / "usr/local/share/apps/kittystory/index.html").read_text() == "<html>by hand</html>\n"
    plan = plan_remove(world, "kittystory")
    assert [q.path for q in plan.questions] == []                      # index.html isn't its any more
    assert apply(plan).summary() == "1 removed"
    assert (world / "home/user/.kittystory/chars/Emma/char.md").read_text() == "Emma\n"
    assert (world / "usr/local/share/apps/kittystory/index.html").exists()
