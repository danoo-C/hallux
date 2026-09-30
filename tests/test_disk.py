import errno
import os
import re

import pytest

import hallux.disk
from hallux.disk import READ_LIMIT, Disk


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "world"
    (root / "home" / "user").mkdir(parents=True)
    (root / "home" / "user" / "notes.md").write_text("hello\n")
    (root / ".hallux").mkdir()
    (root / ".hallux" / "memory.md").write_text("# memory\n")
    (root / ".hallux" / "config.toml").write_text('model = "claude-opus-5-5"\n')
    return root


@pytest.fixture
def outside(tmp_path):
    secret = tmp_path / "outside"
    secret.mkdir()
    (secret / "secret.txt").write_text("host secret\n")
    return secret


@pytest.fixture
def disk(root):
    return Disk(root)


def fails(code, fn, *args, **kwargs):
    with pytest.raises(OSError) as info:
        fn(*args, **kwargs)
    assert info.value.errno == code, errno.errorcode.get(info.value.errno)


# ---------------------------------------------------------------- paths and the jail

def test_virtual_paths_resolve_like_a_shell(disk):
    disk.cwd = "/home/user"
    assert disk.virtual("notes.md") == "/home/user/notes.md"
    assert disk.virtual("") == "/home/user"
    assert disk.virtual("..") == "/home"
    assert disk.virtual("../../../..") == "/"            # can't climb above /
    assert disk.virtual("/etc/passwd") == "/etc/passwd"
    assert disk.virtual("//etc//./passwd") == "/etc/passwd"


def test_absolute_paths_map_into_the_root_never_the_host(disk, root):
    assert disk.real("/etc/passwd") == root / "etc" / "passwd"
    assert disk.real("/../../etc/passwd") == root / "etc" / "passwd"
    assert disk.real("/") == root


def test_symlink_out_of_the_root_is_refused(disk, root, outside):
    (root / "escape").symlink_to(outside)
    (root / "home" / "user" / "secret").symlink_to(outside / "secret.txt")
    fails(errno.EACCES, disk.list_dir, "/escape")
    fails(errno.EACCES, disk.read_file, "/escape/secret.txt")
    fails(errno.EACCES, disk.read_file, "/home/user/secret")
    fails(errno.EACCES, disk.write_file, "/escape/new.txt", "x")
    fails(errno.EACCES, disk.chdir, "/escape")
    fails(errno.EACCES, disk.copy, "/home/user/secret", "/stolen.txt")
    assert not (root / "stolen.txt").exists()
    assert (outside / "secret.txt").read_text() == "host secret\n"


def test_symlink_inside_the_root_is_followed(disk, root):
    (root / "docs").symlink_to(root / "home" / "user")
    assert disk.read_file("/docs/notes.md")["text"] == "hello\n"


def test_symlink_loop_fails_cleanly(disk, root):
    (root / "a").symlink_to(root / "b")
    (root / "b").symlink_to(root / "a")
    with pytest.raises(OSError):
        disk.read_file("/a")


def test_hidden_folder_is_invisible_to_the_os(disk, root):
    assert ".hallux" not in [e["name"] for e in disk.list_dir("/")]
    assert not any(".hallux" in e["path"] for e in disk.find("/")["entries"])
    fails(errno.ENOENT, disk.list_dir, "/.hallux")
    fails(errno.ENOENT, disk.stat, "/.hallux")
    fails(errno.ENOENT, disk.read_file, "/.hallux/memory.md")
    fails(errno.ENOENT, disk.read_file, "/.hallux/config.toml")
    fails(errno.ENOENT, disk.write_file, "/.hallux/memory.md", "wiped")
    fails(errno.ENOENT, disk.remove, "/.hallux", recursive=True)
    fails(errno.ENOENT, disk.move, "/home/user/notes.md", "/.hallux/notes.md")
    (root / "sneaky").symlink_to(root / ".hallux")
    fails(errno.ENOENT, disk.read_file, "/sneaky/config.toml")
    assert (root / ".hallux" / "memory.md").read_text() == "# memory\n"


# ---------------------------------------------------------------- reading

def test_list_dir_entries(disk, root):
    (root / "home" / "user" / "projects").mkdir()
    (root / "home" / "user" / "link").symlink_to(root / "home" / "user" / "notes.md")
    entries = {e["name"]: e for e in disk.list_dir("/home/user")}
    assert list(entries) == ["link", "notes.md", "projects"]
    assert entries["notes.md"]["mode"].startswith("-") and entries["notes.md"]["size"] == 6
    assert entries["projects"]["mode"].startswith("d")
    assert entries["link"]["mode"].startswith("l")
    assert entries["link"]["target"] == "/home/user/notes.md"      # virtual, not the host path
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", entries["notes.md"]["mtime"])


def test_list_dir_errors(disk):
    fails(errno.ENOENT, disk.list_dir, "/nope")
    fails(errno.ENOTDIR, disk.list_dir, "/home/user/notes.md")


def test_stat_describes_the_link_itself(disk, root):
    (root / "link").symlink_to(root / "home")
    assert disk.stat("/link")["mode"].startswith("l")
    assert disk.stat("/")["name"] == "/"
    assert disk.stat("/home/user/notes.md")["name"] == "notes.md"
    fails(errno.ENOENT, disk.stat, "/nope")


def test_read_text_and_binary(disk, root):
    assert disk.read_file("/home/user/notes.md") == {"text": "hello\n", "size": 6, "truncated": False}
    (root / "blob.bin").write_bytes(b"\x7fELF\x00\x01")
    assert disk.read_file("/blob.bin") == {"binary": True, "size": 6}
    fails(errno.ENOENT, disk.read_file, "/nope")
    fails(errno.EISDIR, disk.read_file, "/home")


def test_read_large_file_in_chunks_without_splitting_characters(disk, root):
    text = "a" * (READ_LIMIT - 1) + "é" + "ž" * 10         # "é" straddles the 64 KB boundary
    (root / "big.txt").write_text(text, encoding="utf-8")
    first = disk.read_file("/big.txt")
    assert first["truncated"] and first["text"] == "a" * (READ_LIMIT - 1)
    second = disk.read_file("/big.txt", offset=first["next_offset"])
    assert not second["truncated"]
    assert first["text"] + second["text"] == text


def test_find(disk, root):
    (root / "home" / "user" / "src").mkdir()
    (root / "home" / "user" / "src" / "main.py").write_text("")
    (root / "home" / "user" / "fib.py").write_text("")
    found = disk.find("/", "*.py")
    assert found == {"entries": [{"path": "/home/user/fib.py", "type": "f"},
                                 {"path": "/home/user/src/main.py", "type": "f"}],
                     "truncated": False}
    assert {"path": "/home/user/src", "type": "d"} in disk.find("/home")["entries"]


def test_find_is_capped(disk, root, monkeypatch):
    monkeypatch.setattr(hallux.disk, "FIND_LIMIT", 2)
    for i in range(5):
        (root / f"f{i}").write_text("")
    found = disk.find("/", "f*")
    assert len(found["entries"]) == 2 and found["truncated"]


# ---------------------------------------------------------------- writing

def test_write_overwrite_and_append(disk, root):
    disk.cwd = "/home/user"
    assert disk.write_file("todo.txt", "- a\n") == {"ok": True, "size": 4}
    disk.write_file("todo.txt", "- b\n", append=True)
    assert (root / "home" / "user" / "todo.txt").read_text() == "- a\n- b\n"
    disk.write_file("todo.txt", "new")
    assert (root / "home" / "user" / "todo.txt").read_text() == "new"


def test_write_keeps_line_endings_and_needs_a_parent(disk, root):
    disk.write_file("/dos.txt", "a\r\nb\r\n")
    assert (root / "dos.txt").read_bytes() == b"a\r\nb\r\n"
    fails(errno.ENOENT, disk.write_file, "/no/such/dir/file", "x")
    fails(errno.EISDIR, disk.write_file, "/home", "x")


def test_edit_file_replaces_exactly_once(disk, root):
    bashrc = root / "home" / "user" / ".bashrc"
    bashrc.write_text('PS1="\\u@\\h:\\w\\$ "\nalias ll="ls -l"\n')
    disk.edit_file("/home/user/.bashrc", 'PS1="\\u@\\h:\\w\\$ "', 'PS1="cow daysi moo> "')
    assert bashrc.read_text() == 'PS1="cow daysi moo> "\nalias ll="ls -l"\n'
    with pytest.raises(ValueError, match="0 times"):
        disk.edit_file("/home/user/.bashrc", "nothing like this", "x")
    with pytest.raises(ValueError, match="5 times"):
        disk.edit_file("/home/user/.bashrc", "l", "x")        # alias ll="ls -l" has five


def test_make_dir(disk, root):
    disk.make_dir("/tmp")
    fails(errno.EEXIST, disk.make_dir, "/tmp")
    fails(errno.ENOENT, disk.make_dir, "/a/b/c")
    disk.make_dir("/a/b/c", parents=True)
    disk.make_dir("/a/b/c", parents=True)                  # mkdir -p on an existing dir is fine
    assert (root / "a" / "b" / "c").is_dir()


def test_chdir(disk):
    assert disk.chdir("/home/user") == {"cwd": "/home/user"}
    assert disk.read_file("notes.md")["text"] == "hello\n"
    disk.chdir("../..")
    assert disk.cwd == "/"
    disk.chdir("..")
    assert disk.cwd == "/"
    fails(errno.ENOENT, disk.chdir, "/nope")
    fails(errno.ENOTDIR, disk.chdir, "/home/user/notes.md")
    assert disk.cwd == "/"


def test_remove(disk, root):
    disk.remove("/home/user/notes.md")
    assert not (root / "home" / "user" / "notes.md").exists()
    fails(errno.ENOENT, disk.remove, "/home/user/notes.md")
    fails(errno.EISDIR, disk.remove, "/home")
    disk.remove("/home", recursive=True)
    assert not (root / "home").exists()


def test_remove_symlink_removes_the_link_not_the_target(disk, root, outside):
    (root / "inside").symlink_to(root / "home")
    (root / "outlink").symlink_to(outside)
    disk.remove("/inside")
    disk.remove("/outlink")
    assert (root / "home" / "user" / "notes.md").exists()
    assert (outside / "secret.txt").exists()
    assert not (root / "inside").is_symlink() and not (root / "outlink").is_symlink()


def test_rm_rf_root_empties_the_machine_but_keeps_its_memory(disk, root):
    fails(errno.EISDIR, disk.remove, "/")
    disk.remove("/", recursive=True)
    assert root.is_dir()
    assert [p.name for p in root.iterdir()] == [".hallux"]
    assert (root / ".hallux" / "memory.md").read_text() == "# memory\n"


def test_move(disk, root):
    disk.move("/home/user/notes.md", "/home/user/renamed.md")
    assert (root / "home" / "user" / "renamed.md").read_text() == "hello\n"
    disk.make_dir("/archive")
    assert disk.move("/home/user/renamed.md", "/archive") == {"ok": True, "path": "/archive/renamed.md"}
    fails(errno.EINVAL, disk.move, "/home", "/home/user")
    fails(errno.EBUSY, disk.move, "/", "/home")
    fails(errno.ENOENT, disk.move, "/nope", "/x")


def test_copy(disk, root, outside):
    assert disk.copy("/home/user/notes.md", "/home") == {"ok": True, "path": "/home/notes.md"}
    fails(errno.EISDIR, disk.copy, "/home/user", "/backup")
    (root / "home" / "user" / "out").symlink_to(outside)
    disk.copy("/home/user", "/backup", recursive=True)
    assert (root / "backup" / "notes.md").read_text() == "hello\n"
    assert (root / "backup" / "out").is_symlink()          # copied as a link, not the host files
    fails(errno.EACCES, disk.read_file, "/backup/out/secret.txt")
    fails(errno.EINVAL, disk.copy, "/home", "/home/user/again", recursive=True)
    fails(errno.EINVAL, disk.copy, "/home/notes.md", "/home/notes.md")


# ---------------------------------------------------------------- memory

def test_memory_read_and_edit(disk, root):
    assert disk.memory_read() == {"text": "# memory\n"}
    disk.memory_edit("", "## Rules\n1. errors are haiku\n")
    disk.memory_edit("1. errors are haiku\n", "1. errors are haiku\n2. be grumpy\n")
    assert disk.memory_read()["text"] == "# memory\n## Rules\n1. errors are haiku\n2. be grumpy\n"
    with pytest.raises(ValueError):
        disk.memory_edit("not in memory", "x")
    assert not (root / ".hallux" / "memory.tmp").exists()


def test_memory_on_first_boot(tmp_path):
    disk = Disk(tmp_path)
    assert disk.memory_read() == {"text": ""}
    assert disk.memory_edit("", "# hallux memory\n") == {"ok": True, "size": 16}
    assert (tmp_path / ".hallux" / "memory.md").read_text() == "# hallux memory\n"
    assert os.listdir(tmp_path / ".hallux") == ["memory.md"]
