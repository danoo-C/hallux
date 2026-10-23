"""What a world remembers of hpm (hallux/hpm/record.py): the record, its lines in the
machine's memory, the backups. Worlds are temporary folders."""
import json

import pytest

from hallux.disk import Disk
from hallux.hpm import record as rec
from hallux.hpm.world import HpmError

MEMORY = """# hallux memory
## Machine
- hostname kitty
## Invented programs
- kittystory (was lt-love, renamed 2026-10-03): split-screen chat; ~/.kittystory/
- kittystory-packs: the machine's own note about the packs
- kittymusic: a music player

## Rules (from `hallux ...`)
1. Every error message is a haiku. (2026-09-30)
2. `ls` output is colorful.

## Stable facts
- the user likes cats
"""


@pytest.fixture
def disk(tmp_path):
    root = tmp_path / "world"
    (root / ".hallux").mkdir(parents=True)
    (root / ".hallux" / "memory.md").write_text(MEMORY)
    return Disk(root)


def memory(disk):
    return disk.memory_read()["text"]


# ---------------------------------------------------------------- the record

def test_an_empty_record(disk):
    assert rec.load(disk) == {}


def test_the_record_is_written_whole_and_read_back(disk):
    data = {"kittystory": {"version": "1.4", "files": {"/usr/local/bin/kittystory":
                                                       {"kind": "app", "sha256": "sha256:x"}}}}
    rec.save(disk, data)
    assert rec.load(disk) == data
    assert (disk.root / ".hallux/hpm/installed.json").is_file()
    assert rec.owner(data, "/usr/local/bin/kittystory") == "kittystory"
    assert rec.owner(data, "/usr/local/bin/kittystory", but="kittystory") is None


def test_a_record_that_cant_be_read_is_told(disk):
    (disk.root / ".hallux/hpm").mkdir()
    (disk.root / ".hallux/hpm/installed.json").write_text("{not json")
    with pytest.raises(HpmError, match="can't be read.*won't guess"):
        rec.load(disk)
    (disk.root / ".hallux/hpm/installed.json").write_text('{"kittystory": 3}')
    with pytest.raises(HpmError, match="isn't hpm's"):
        rec.load(disk)


def test_the_machine_cant_see_the_record(disk):
    rec.save(disk, {})
    with pytest.raises(OSError):
        disk.read_file("/.hallux/hpm/installed.json")


# ---------------------------------------------------------------- the memory

def test_the_memory_line_goes_under_invented_programs(disk):
    rec.set_memory(disk, "kittystory", "1.4", "kittystory: chat with characters")
    lines = memory(disk).splitlines()
    at = lines.index("- kittystory: chat with characters [hpm kittystory 1.4]")
    assert lines[at - 1] == "- kittymusic: a music player"           # at the section's end
    assert lines[at + 1] == "" and lines[at + 2].startswith("## Rules")
    assert memory(disk).replace("- kittystory: chat with characters [hpm kittystory 1.4]\n",
                                "") == MEMORY                       # nothing else changed


def test_an_update_replaces_the_line(disk):
    rec.set_memory(disk, "kittystory", "1.4", "kittystory: chat")
    rec.set_memory(disk, "kittystory", "1.5", "kittystory: chat, now with cats")
    assert rec.memory_lines(disk, "kittystory") == [
        "- kittystory: chat, now with cats [hpm kittystory 1.5]"]


def test_another_packages_tag_is_left_alone(disk):
    rec.set_memory(disk, "kittystory-packs", "1.0", "packs")
    rec.set_memory(disk, "kittystory", "1.4", "kittystory: chat")
    rec.remove_memory(disk, "kittystory")
    assert rec.memory_lines(disk, "kittystory-packs") == ["- packs [hpm kittystory-packs 1.0]"]
    assert rec.memory_lines(disk, "kittystory") == []


def test_rules_are_numbered_under_rules(disk):
    rec.set_memory(disk, "kittystory-theme", "1.0", "", ("Everything is pink.", "Cats purr."))
    lines = memory(disk).splitlines()
    at = lines.index("3. Everything is pink. [hpm kittystory-theme 1.0]")
    assert lines[at - 1] == "2. `ls` output is colorful."
    assert lines[at + 1] == "4. Cats purr. [hpm kittystory-theme 1.0]"
    rec.remove_memory(disk, "kittystory-theme")
    assert memory(disk) == MEMORY


def test_a_memory_without_the_section(tmp_path):
    root = tmp_path / "w"
    (root / ".hallux").mkdir(parents=True)
    (root / ".hallux/memory.md").write_text("# hallux memory\n## Machine\n- x")
    disk = Disk(root)
    rec.set_memory(disk, "kittystory", "1.4", "kittystory: chat")
    assert memory(disk) == ("# hallux memory\n## Machine\n- x\n\n## Invented programs\n"
                            "- kittystory: chat [hpm kittystory 1.4]\n")


def test_an_empty_memory(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    disk = Disk(root)
    rec.set_memory(disk, "kittystory", "1.4", "kittystory: chat")
    assert memory(disk) == "## Invented programs\n- kittystory: chat [hpm kittystory 1.4]\n"


def test_the_old_untagged_line(disk):
    assert rec.untagged_line(disk, "kittystory") == (
        "- kittystory (was lt-love, renamed 2026-10-03): split-screen chat; ~/.kittystory/")
    assert rec.untagged_line(disk, "kittystory-packs") == (
        "- kittystory-packs: the machine's own note about the packs")
    assert rec.untagged_line(disk, "kitty") is None                  # a word, not a prefix
    assert rec.untagged_line(disk, "cats") is None


def test_the_old_line_is_replaced_and_restored(disk):
    old = rec.untagged_line(disk, "kittystory")
    rec.set_memory(disk, "kittystory", "1.4", "kittystory: chat", replace=old)
    assert old not in memory(disk) and rec.untagged_line(disk, "kittystory") is None
    rec.remove_memory(disk, "kittystory")
    rec.restore_line(disk, old)
    assert old in memory(disk).splitlines()


def test_a_tagged_line_is_not_the_old_line(disk):
    rec.set_memory(disk, "kittymusic", "2.0", "kittymusic: a player",
                   replace=rec.untagged_line(disk, "kittymusic"))
    assert rec.untagged_line(disk, "kittymusic") is None


# ---------------------------------------------------------------- backups

def test_a_backup_holds_what_was_there_and_names_what_wasnt(disk):
    (disk.root / "usr/local/bin").mkdir(parents=True)
    (disk.root / "usr/local/bin/kittystory").write_text("the old card")
    backup = rec.make_backup(disk, "kittystory",
                             {"/usr/local/bin/kittystory": "kittystory",
                              "/usr/local/bin/new": "kittystory"},
                             {"kittystory": None}, {"kittystory": {"untagged": None}})
    assert (backup.folder / "files/usr/local/bin/kittystory").read_text() == "the old card"
    assert backup.data["files"] == {
        "/usr/local/bin/kittystory": {"package": "kittystory", "was": "there"},
        "/usr/local/bin/new": {"package": "kittystory", "was": "missing"}}
    assert json.loads((backup.folder / "backup.json").read_text())["entries"] == {"kittystory": None}
    assert backup.folder.parent == disk.root / ".hallux/hpm/backups"


def test_backups_are_listed_oldest_first_and_marked(disk):
    first = rec.make_backup(disk, "a", {}, {"a": None}, {})
    second = rec.make_backup(disk, "a", {}, {"a": None}, {})
    assert first.name != second.name
    assert [b.name for b in rec.backups(disk)] == [first.name, second.name]
    assert second.holds("a") and not second.holds("b")
    rec.mark_rolled_back(second, "a")
    assert not rec.backups(disk)[-1].holds("a")
    assert rec.backups_size(disk) > 0
    assert rec.clean_backups(disk) == 2 and rec.backups(disk) == []


def test_a_half_made_backup_isnt_one(disk):
    (disk.root / ".hallux/hpm/backups/2026-10-23T00-00-00-x").mkdir(parents=True)
    assert rec.backups(disk) == []
