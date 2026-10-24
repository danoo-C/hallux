"""hpm publish and hpm show (hallux/hpm/publish.py, hallux/hpm/cli.py), without the AI: a
kittystory world made in a temporary folder, manifests written by hand, a store of its own,
and questions answered from a script."""
import datetime
import os
import tarfile

import pytest

from hallux.hpm import cli
from hallux.hpm.archive import listing, read_member
from hallux.hpm.publish import Questions, bump, publish, show
from hallux.hpm.manifest import Version
from hallux.hpm.store import Store
from hallux.hpm.world import HpmError

TODAY = datetime.date(2026, 10, 23)
HOME = "home/danika-hous"

APP = '''name = "kittystory"
version = "1.4"                 # the version
summary = "Chat with characters built from personality packs"
author = "danika"
data_format = 1
requires.addons = ["web"]
memory_line = "kittystory: split-screen chat with characters made from personality packs"

[files]
app  = ["/usr/local/bin/kittystory", "/usr/local/share/apps/kittystory/**"]
seed = ["/usr/local/share/apps/kittystory/data/state.json"]

[extras]
packs      = { package = "kittystory-packs",    default = true }
characters = { package = "kittystory-chars",    default = true,  needs = ["packs"] }
memories   = { package = "kittystory-memories", default = false, needs = ["characters"] }
'''

PACKS = '''name = "kittystory-packs"
version = "1.0"
for = "kittystory"
[files]
data = ["~/.kittystory/packs/*.pack"]
'''

CHARS = '''name = "kittystory-chars"
version = "1.0"
for = "kittystory"
[files]
data = ["~/.kittystory/chars/*/char.md", "~/.kittystory/scene.md", "~/.kittystory/assets/**"]
'''

MEMORIES = '''name = "kittystory-memories"
version = "1.0"
for = "kittystory"
[files]
data = ["~/.kittystory/chars/*/memory.md", "~/.kittystory/shared.md"]
'''

WORLD = {
    ".hallux/memory.md": "# hallux memory\n",
    "etc/passwd": "root:x:0:0:root:/root:/bin/bash\n"
                  "danika-hous:x:1000:1000::/home/danika-hous:/bin/bash\n",
    "usr/local/bin/kittystory": "# kittystory\nthe card\n",
    "usr/local/share/apps/kittystory/index.html": "<html></html>\n",
    "usr/local/share/apps/kittystory/app.js": "// the app\n",
    "usr/local/share/apps/kittystory/sprites/emma.svg": "<svg/>\n",
    "usr/local/share/apps/kittystory/data/state.json": "{}\n",
    f"{HOME}/.kittystory/packs/tsundere.pack": "tsundere\n",
    f"{HOME}/.kittystory/packs/dirty.pack": "dirty\n",
    f"{HOME}/.kittystory/chars/Emma/char.md": "Emma\n",
    f"{HOME}/.kittystory/chars/Emma/memory.md": "2026-10-03 met the user\n",
    f"{HOME}/.kittystory/chars/emilly/char.md": "Emilly\n",
    f"{HOME}/.kittystory/shared.md": "shared\n",
    f"{HOME}/.kittystory/scene.md": "who is where\n",
    f"{HOME}/.kittystory/assets/places.md": "the park\n",
    "usr/local/share/hpm/kittystory/hpm.toml": APP,
    "usr/local/share/hpm/kittystory-packs/hpm.toml": PACKS,
    "usr/local/share/hpm/kittystory-chars/hpm.toml": CHARS,
    "usr/local/share/hpm/kittystory-memories/hpm.toml": MEMORIES,
}


class Script(Questions):
    """Answers from a list, in order; what hpm says is kept."""

    def __init__(self, *answers):
        super().__init__(interactive=True)
        self.answers = list(answers)
        self.asked, self.said = [], []

    def _next(self, question, default):
        self.asked.append(question)
        return self.answers.pop(0) if self.answers else default

    def ask(self, question, default, flag):
        answer = self._next(question, default)
        return default if answer is None else answer

    def confirm(self, question, default, flag):
        answer = self._next(question, default)
        return default if answer is None else answer

    def edit(self, template, flag):
        answer = self._next("edit", template)
        return template + "edited\n" if answer is None else answer

    def say(self, text):
        self.said.append(text)


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "test-hallux"
    for name, text in WORLD.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "store")


def go(world, store, name="kittystory", q=None, **flags):
    flags.setdefault("changelog", "the first release")
    return publish(world, name, store, q or Script(), today=TODAY, **flags)


def members(release):
    return sorted(listing(release.path))


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------- the files

def test_the_app_is_collected_with_its_seed(world, store):
    [release] = go(world, store)
    assert (release.name, str(release.version)) == ("kittystory", "1.4")
    assert release.path == store.local / "kittystory" / "1.4.hpm"
    assert members(release) == [
        "CHANGELOG.md", "files/root/usr/local/bin/kittystory",
        "files/root/usr/local/share/apps/kittystory/app.js",
        "files/root/usr/local/share/apps/kittystory/data/state.json",
        "files/root/usr/local/share/apps/kittystory/index.html",
        "files/root/usr/local/share/apps/kittystory/sprites/emma.svg", "hpm.toml"]
    assert "seed files: 1" in show(store, "kittystory")
    assert "  /usr/local/share/apps/kittystory/data/state.json" in show(store, "kittystory")


def test_home_files_come_from_the_worlds_user(world, store):
    [release] = go(world, store, "kittystory-packs")
    assert members(release) == ["CHANGELOG.md", "files/home/.kittystory/packs/dirty.pack",
                                "files/home/.kittystory/packs/tsundere.pack", "hpm.toml"]


def test_a_world_with_several_users_needs_one_named(world, store):
    (world / "etc/passwd").write_text("a:x:1000:1000::/home/a:/bin/sh\n"
                                      "danika-hous:x:1001:1001::/home/danika-hous:/bin/sh\n")
    with pytest.raises(HpmError, match="say which with --user"):
        go(world, store, "kittystory-packs")
    assert go(world, store, "kittystory-packs", user="danika-hous")


def test_a_pattern_that_matches_nothing_stops_it(world, store):
    os.remove(world / HOME / ".kittystory/scene.md")
    before = snapshot(world)
    with pytest.raises(HpmError, match="~/.kittystory/scene.md matches nothing in this world"):
        go(world, store, "kittystory-chars")
    assert store.releases("kittystory-chars") == [] and snapshot(world) == before


def test_a_link_is_refused(world, store):
    (world / HOME / ".kittystory/packs/linked.pack").symlink_to(
        world / HOME / ".kittystory/packs/dirty.pack")
    with pytest.raises(HpmError, match="~/.kittystory/packs/linked.pack is a link"):
        go(world, store, "kittystory-packs")


def test_a_file_both_the_app_and_an_extra_carry(world, store):
    (world / "usr/local/share/hpm/kittystory-chars/hpm.toml").write_text(CHARS.replace(
        '"~/.kittystory/assets/**"]',
        '"~/.kittystory/assets/**", "/usr/local/share/apps/kittystory/sprites/*.svg"]'))
    for name in ("kittystory", "kittystory-chars"):
        with pytest.raises(HpmError, match="/usr/local/share/apps/kittystory/sprites/emma.svg "
                                           "is in kittystory(-chars)? and in kittystory"):
            go(world, store, name)


def test_family_problems_names_every_file_two_packages_carry(world, store):
    """Fix 01: the one check init and publish share, in publish's words."""
    from hallux.disk import Disk
    from hallux.hpm.publish import family_problems
    disk = Disk(world)
    assert family_problems(disk, "kittystory", "/home/danika-hous") == []
    (world / "usr/local/share/hpm/kittystory-chars/hpm.toml").write_text(CHARS.replace(
        '"~/.kittystory/assets/**"]',
        '"~/.kittystory/assets/**", "/usr/local/share/apps/kittystory/sprites/*.svg"]'))
    assert family_problems(disk, "kittystory", "/home/danika-hous") == [
        "/usr/local/share/apps/kittystory/sprites/emma.svg is in kittystory and in "
        "kittystory-chars; one package must carry it"]
    (world / "usr/local/share/hpm/kittystory-packs/hpm.toml").write_text("name = 3\n")
    assert any(p.startswith("/usr/local/share/hpm/kittystory-packs/hpm.toml has problems")
               for p in family_problems(disk, "kittystory", "/home/danika-hous"))


def test_no_manifest_in_the_world(world, store):
    with pytest.raises(HpmError, match="this world has no manifest for kittymusic"):
        go(world, store, "kittymusic")


def test_a_manifest_of_another_name(world, store):
    (world / "usr/local/share/hpm/kittymusic").mkdir()
    (world / "usr/local/share/hpm/kittymusic/hpm.toml").write_text(PACKS)
    with pytest.raises(HpmError, match="is the manifest of kittystory-packs, not kittymusic"):
        go(world, store, "kittymusic")


def test_migration_notes_go_with_the_release(world, store):
    notes = world / "usr/local/share/hpm/kittystory/migrations"
    notes.mkdir()
    (notes / "1-to-2.md").write_text("# kittystory data format 1 → 2\n\nOld paths: none\n")
    [release] = go(world, store)
    assert "migrations/1-to-2.md" in members(release)
    (notes / "run.sh").write_text("#!/bin/sh\n")
    with pytest.raises(HpmError, match="holds only .md notes, not run.sh"):
        go(world, store, version="1.5")


def test_a_bundle_is_published(world, store):
    (world / "usr/local/share/hpm/kitty-desktop").mkdir()
    (world / "usr/local/share/hpm/kitty-desktop/hpm.toml").write_text(
        'name = "kitty-desktop"\nversion = "1.0"\nbundle = ["kittystory", "kittymusic"]\n')
    [release] = go(world, store, "kitty-desktop")
    assert members(release) == ["CHANGELOG.md", "hpm.toml"]
    assert "bundle of: kittystory, kittymusic" in show(store, "kitty-desktop")


# ---------------------------------------------------------------- versions

def test_the_first_release_suggests_the_manifests_version(world, store):
    q = Script()
    [release] = go(world, store, q=q)
    assert q.asked == ["kittystory's version"] and str(release.version) == "1.4"


def test_the_next_release_suggests_the_last_number_up(world, store):
    go(world, store)
    (world / "usr/local/bin/kittystory").write_text("# kittystory\na better card\n")
    [release] = go(world, store)
    assert str(release.version) == "1.5"
    assert 'version = "1.5"                 # the version' in (
        world / "usr/local/share/hpm/kittystory/hpm.toml").read_text()


def test_a_new_data_format_suggests_the_first_number_up(world, store):
    go(world, store, "kittystory-chars")
    text = (world / "usr/local/share/hpm/kittystory-chars/hpm.toml").read_text()
    (world / "usr/local/share/hpm/kittystory-chars/hpm.toml").write_text(
        text.replace('for = "kittystory"', 'for = "kittystory"\ndata_format = 2'))
    with pytest.raises(HpmError, match="no migration from data format 1"):
        go(world, store, "kittystory-chars")              # a new format needs its note
    notes = world / "usr/local/share/hpm/kittystory-chars/migrations"
    notes.mkdir()
    (notes / "1-to-2.md").write_text("# 1 → 2\n\nOld paths: none\n")
    [release] = go(world, store, "kittystory-chars")
    assert str(release.version) == "2.0"


def test_the_answer_is_the_version(world, store):
    [release] = go(world, store, q=Script("1.4.1"))
    assert str(release.version) == "1.4.1"


def test_a_version_not_above_the_latest_is_refused(world, store):
    go(world, store)
    (world / "usr/local/bin/kittystory").write_text("changed\n")
    with pytest.raises(HpmError, match="must be higher than the store's latest, 1.4"):
        go(world, store, version="1.3")
    with pytest.raises(HpmError, match="must be higher than the store's latest, 1.4"):
        go(world, store, version="1.4.0")
    with pytest.raises(HpmError, match="is no version"):
        go(world, store, version="1.5-beta")


def test_nothing_changed_is_refused(world, store):
    go(world, store)
    with pytest.raises(HpmError, match="nothing changed since 1.4; nothing to publish"):
        go(world, store)


def test_a_new_memory_line_is_a_change(world, store):
    go(world, store)
    path = world / "usr/local/share/hpm/kittystory/hpm.toml"
    path.write_text(path.read_text().replace("personality packs\"", "packs, now with cats\""))
    assert str(go(world, store)[0].version) == "1.5"


def test_a_tag_in_the_memory_line_is_taken_out(world, store):
    """Fix 02: hpm adds its own tag when it installs; one in the manifest would be a second."""
    path = world / "usr/local/share/hpm/kittystory/hpm.toml"
    path.write_text(path.read_text().replace('made from personality packs"',
                                             'made from personality packs [hpm kittystory 1.0]"'))
    q = Script()
    release = go(world, store, q=q)[0]
    line = 'memory_line = "kittystory: split-screen chat with characters made from personality packs"'
    assert line in read_member(release.path, "hpm.toml").decode()
    assert line in path.read_text() and "[hpm" not in path.read_text()
    assert ('/usr/local/share/hpm/kittystory/hpm.toml: memory_line: took out '
            '"[hpm kittystory 1.0]"; hpm adds its own when it installs') in q.said


def test_a_clean_memory_line_is_not_touched(world, store):
    q = Script()
    go(world, store, q=q)
    assert not any("memory_line" in line for line in q.said)


STILL_RIGHT = ("kittystory: the card changed since 1.4, but the summary, memory line and "
               "requires are as they were. Still right?")


def test_a_new_card_with_the_old_words_is_asked_about(world, store):
    """Fix 03."""
    go(world, store)
    (world / "usr/local/bin/kittystory").write_text("# kittystory\nthe card, without -g\n")
    q = Script(False)
    with pytest.raises(HpmError, match="edit /usr/local/share/hpm/kittystory/hpm.toml, then "
                                       "publish again"):
        go(world, store, q=q)
    assert q.asked[0] == STILL_RIGHT and [str(r.version) for r in store.releases("kittystory")] == ["1.4"]
    q = Script(True)
    assert str(go(world, store, q=q)[0].version) == "1.5"
    q = Script()
    (world / "usr/local/bin/kittystory").write_text("# kittystory\nthe card, once more\n")
    go(world, store, q=q, suggested=True)                              # --yes: only said
    assert STILL_RIGHT not in q.asked
    assert ("note: kittystory: the card changed since 1.5, but the summary, memory line and "
            "requires are as they were; check them in /usr/local/share/hpm/kittystory/hpm.toml"
            in q.said)


def test_no_question_when_the_card_or_the_words_changed(world, store):
    go(world, store)
    (world / "usr/local/share/apps/kittystory/app.js").write_text("// new\n")   # not the card
    q = Script()
    go(world, store, q=q)
    assert STILL_RIGHT.replace("1.4", "1.5") not in q.asked and STILL_RIGHT not in q.asked
    (world / "usr/local/bin/kittystory").write_text("# kittystory\nthe card, new\n")
    path = world / "usr/local/share/hpm/kittystory/hpm.toml"
    path.write_text(path.read_text().replace('requires.addons = ["web"]', 'requires.addons = []'))
    q = Script()
    go(world, store, q=q)
    assert not any("Still right?" in question for question in q.asked)


@pytest.mark.parametrize("given, major, expected", [
    ("1.4", False, "1.5"), ("1.4.1", False, "1.4.2"), ("2", False, "2.1"),
    ("1.4", True, "2.0"), ("1.4.9", True, "2.0"),
])
def test_bump(given, major, expected):
    assert bump(Version(given), major) == Version(expected)


# ---------------------------------------------------------------- the changelog

def test_the_changelog_goes_on_top_in_the_world_and_the_release(world, store):
    go(world, store, changelog="the first release")
    (world / "usr/local/bin/kittystory").write_text("changed\n")
    [release] = go(world, store, changelog="a better card")
    expected = ("## 1.5 (2026-10-23)\n\na better card\n\n"
                "## 1.4 (2026-10-23)\n\nthe first release\n")
    assert (world / "usr/local/share/hpm/kittystory/CHANGELOG.md").read_text() == expected
    assert read_member(release.path, "CHANGELOG.md").decode() == expected


def test_a_changelog_with_a_title_keeps_it_on_top(world, store):
    (world / "usr/local/share/hpm/kittystory/CHANGELOG.md").write_text(
        "# kittystory\n\n## 1.3\n\nolder\n")
    go(world, store, changelog="new")
    assert (world / "usr/local/share/hpm/kittystory/CHANGELOG.md").read_text() == (
        "# kittystory\n\n## 1.4 (2026-10-23)\n\nnew\n\n## 1.3\n\nolder\n")


def test_the_editor_writes_the_entry(world, store):
    q = Script(None, "## 1.4 (2026-10-23)\n\n- the web app\n- sprites\n")
    go(world, store, q=q, changelog=None)
    assert (world / "usr/local/share/hpm/kittystory/CHANGELOG.md").read_text() == (
        "## 1.4 (2026-10-23)\n\n- the web app\n- sprites\n")


def test_an_empty_entry_stops_it_and_writes_nothing(world, store):
    before = snapshot(world)
    with pytest.raises(HpmError, match="the changelog entry is empty"):
        go(world, store, q=Script(None, "## 1.4 (2026-10-23)\n\n   \n"), changelog=None)
    with pytest.raises(HpmError, match="the changelog entry is empty"):
        go(world, store, changelog="  ")
    assert store.releases("kittystory") == [] and snapshot(world) == before


# ---------------------------------------------------------------- data, privacy, seeds

def test_data_that_moved_without_a_new_format_stops_it(world, store):
    go(world, store, "kittystory-chars")
    path = world / "usr/local/share/hpm/kittystory-chars/hpm.toml"
    path.write_text(path.read_text().replace('"~/.kittystory/scene.md", ', ""))
    with pytest.raises(HpmError, match="the data moved since 1.0.*but data_format is still 1"):
        go(world, store, "kittystory-chars")
    path.write_text(path.read_text().replace('for = "kittystory"',
                                             'for = "kittystory"\ndata_format = 2'))
    notes = world / "usr/local/share/hpm/kittystory-chars/migrations"
    notes.mkdir()
    (notes / "1-to-2.md").write_text("# 1 → 2\n\nOld paths: ~/.kittystory/scene.md\n")
    assert str(go(world, store, "kittystory-chars")[0].version) == "2.0"


def test_a_data_format_never_goes_down(world, store):
    path = world / "usr/local/share/hpm/kittystory-chars/hpm.toml"
    path.write_text(CHARS.replace('for = "kittystory"', 'for = "kittystory"\ndata_format = 2'))
    go(world, store, "kittystory-chars")
    path.write_text(CHARS)
    with pytest.raises(HpmError, match="data_format is 1, lower than 2 in 1.0"):
        go(world, store, "kittystory-chars")


def test_memories_are_told_and_marked_private_on_yes(world, store):
    q = Script(None, True)                        # the version, then "mark it private?"
    [release] = go(world, store, "kittystory-memories", q=q)
    assert any("may be your own memories or chats" in line and "memory.md" in line
               for line in q.said)
    assert "private = true" in (world / "usr/local/share/hpm/kittystory-memories/hpm.toml"
                                ).read_text()
    assert release.manifest().private is True


def test_memories_kept_public_on_no(world, store):
    [release] = go(world, store, "kittystory-memories", q=Script(None, False))
    assert release.manifest().private is False


def test_private_from_the_flag(world, store):
    [release] = go(world, store, "kittystory-memories", private=True)
    assert release.manifest().private is True


def test_without_a_terminal_the_question_names_its_flag(world, store):
    with pytest.raises(HpmError, match="no terminal to ask in; pass --private yes or "
                                       "--private no"):
        publish(world, "kittystory-memories", store, Questions(interactive=False),
                version="1.0", changelog="x", today=TODAY)
    with pytest.raises(HpmError, match="no terminal to ask in; pass --version, or --yes for "
                                       "the suggested 1.4"):
        publish(world, "kittystory", store, Questions(interactive=False), changelog="x")
    with pytest.raises(HpmError, match="no terminal to ask in; pass --changelog TEXT"):
        publish(world, "kittystory", store, Questions(interactive=False), version="1.4")


def test_a_private_package_isnt_asked(world, store):
    path = world / "usr/local/share/hpm/kittystory-memories/hpm.toml"
    path.write_text(MEMORIES.replace('for = "kittystory"', 'for = "kittystory"\nprivate = true'))
    q = Script()
    go(world, store, "kittystory-memories", q=q)
    assert q.asked == ["kittystory-memories's version"]


def test_a_seed_that_grew_is_told(world, store):
    go(world, store)
    (world / "usr/local/share/apps/kittystory/data/state.json").write_text("{" + "x" * 50 + "}\n")
    q = Script()
    go(world, store, q=q)
    assert any("the seed /usr/local/share/apps/kittystory/data/state.json" in line
               and "may hold your own data now" in line for line in q.said)


# ---------------------------------------------------------------- --all

def test_all_publishes_each_that_changed(world, store):
    published = go(world, store, every=True)
    assert [r.name for r in published] == ["kittystory", "kittystory-packs", "kittystory-chars",
                                           "kittystory-memories"]
    (world / HOME / ".kittystory/packs/new.pack").write_text("new\n")
    q = Script()
    published = go(world, store, q=q, every=True, private=False)
    assert [(r.name, str(r.version)) for r in published] == [("kittystory-packs", "1.1")]
    assert "kittystory 1.4: unchanged, not published" in q.said
    assert "kittystory-chars 1.0: unchanged, not published" in q.said


def test_all_with_nothing_changed(world, store):
    go(world, store, every=True, private=False)
    q = Script()
    assert go(world, store, q=q, every=True) == []
    assert q.said[-1] == "nothing changed since the last releases; nothing published"


def test_all_needs_every_extras_manifest_and_no_version(world, store):
    with pytest.raises(HpmError, match="--version can't go with --all"):
        go(world, store, every=True, version="2.0")
    os.remove(world / "usr/local/share/hpm/kittystory-memories/hpm.toml")
    with pytest.raises(HpmError, match="no manifest in this world for kittystory-memories"):
        go(world, store, every=True)
    assert store.names() == []


# ---------------------------------------------------------------- what is written

def test_publish_writes_only_the_store_and_its_own_folder_in_the_world(world, store):
    before = snapshot(world)
    go(world, store)
    after = snapshot(world)
    changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    assert changed == {"usr/local/share/hpm/kittystory/CHANGELOG.md"}
    (world / "usr/local/bin/kittystory").write_text("changed\n")
    before = snapshot(world)
    go(world, store)
    after = snapshot(world)
    changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    assert changed == {"usr/local/share/hpm/kittystory/CHANGELOG.md",
                       "usr/local/share/hpm/kittystory/hpm.toml"}
    assert sorted(p.name for p in store.local.rglob("*") if p.is_file()) == ["1.4.hpm", "1.5.hpm"]


def test_a_release_holds_the_new_version_in_its_manifest(world, store):
    go(world, store)
    (world / "usr/local/bin/kittystory").write_text("changed\n")
    [release] = go(world, store)
    with tarfile.open(release.path) as tar:
        text = tar.extractfile("hpm.toml").read().decode()
    assert 'version = "1.5"' in text and "# the version" in text


# ---------------------------------------------------------------- show

def test_show_lists_the_versions_the_files_and_the_changelog(world, store):
    go(world, store, changelog="the first release")
    (world / "usr/local/bin/kittystory").write_text("changed\n")
    go(world, store, changelog="a better card")
    text = show(store, "kittystory")
    assert text.splitlines()[0] == ("kittystory 1.5  ·  Chat with characters built from "
                                    "personality packs  ·  by danika")
    for line in ("versions: 1.4, 1.5", "data format: 1", "needs the addons: web",
                 "memory line: kittystory: split-screen chat", "extras:",
                 "  packs        kittystory-packs  (ticked)",
                 "  memories     kittystory-memories  (not ticked; needs characters)",
                 "app files: 4,", "  /usr/local/bin/kittystory  8 bytes",
                 "changelog:", "  ## 1.5 (2026-10-23)", "  a better card", "  ## 1.4 (2026-10-23)"):
        assert line in text, line


def test_show_of_a_package_the_store_doesnt_have(store):
    with pytest.raises(HpmError, match="there is no package kittymusic in the store"):
        show(store, "kittymusic")


# ---------------------------------------------------------------- the command

def test_the_command_publishes_and_shows(world, store, capsys):
    q = Script(False)                                 # no review of the card by the AI
    assert cli.main(["publish", "kittystory", "--world", str(world), "--version", "1.4",
                     "--changelog", "first"], questions=q, store=store) == 0
    assert q.said == ["published kittystory 1.4: 5 files, 57 bytes",
                      "  ✓ kittystory 1.4 adopted", "1 adopted"]   # its own world records it
    assert cli.main(["show", "kittystory"], questions=q, store=store) == 0
    assert q.said[-1].startswith("kittystory 1.4")


def test_the_command_finds_the_world_it_is_in(world, store, monkeypatch):
    monkeypatch.chdir(world / HOME / ".kittystory")
    assert cli.main(["publish", "kittystory-packs", "--changelog", "first"],
                    questions=Script(), store=store) == 0
    assert store.latest("kittystory-packs")


def test_the_command_tells_an_error_and_fails(world, store, capsys):
    assert cli.main(["publish", "kittymusic", "--world", str(world)],
                    questions=Script(), store=store) == 1
    assert capsys.readouterr().err.startswith("hpm: this world has no manifest for kittymusic")


def test_the_private_flag(world, store):
    assert cli.main(["publish", "kittystory-memories", "--world", str(world), "--changelog",
                     "x", "--private", "no"], questions=Script(), store=store) == 0
    assert store.latest("kittystory-memories").manifest().private is False


def test_yes_takes_the_suggested_versions_without_a_terminal(world, store):
    publish(world, "kittystory", store, Questions(interactive=False), every=True, suggested=True,
            changelog="first", private=False, today=TODAY)
    (world / "usr/local/bin/kittystory").write_text("changed\n")
    (world / HOME / ".kittystory/packs/new.pack").write_text("new\n")
    published = publish(world, "kittystory", store, Questions(interactive=False), every=True,
                        suggested=True, changelog="more", private=False, today=TODAY)
    assert [(r.name, str(r.version)) for r in published] == [("kittystory", "1.5"),
                                                              ("kittystory-packs", "1.1")]
    assert cli.main(["publish", "kittystory", "--world", str(world), "--all", "--yes",
                     "--changelog", "x"], questions=Questions(interactive=False),
                    store=store) == 0               # nothing changed: told, not an error
