"""Reading a drop, hallux/importing.py: the text a terminal sends for a drop becomes real
paths. Real files in a temporary folder, and a stand-in for wslpath, which notes what it
was asked."""
import asyncio
import errno
import os
import shutil
import socket
import stat
import threading
import time
from pathlib import Path
from urllib.parse import quote

import pytest

import hallux.importing
from hallux.disk import TEMP_MARK, Disk, copy_whole
from hallux.importing import (COPYING, DONE, EMPTY, EXISTS, FILE, FOLDER, FULL, HERE, IN_THE_WAY,
                              LEADS, LINK, LONGEST, LOOKING, MEANWHILE, MORE, NO_PLACE,
                              NOT_COPIED, OTHER, READY, STOPPED, UNREADABLE, Counts, Imports,
                              Line, NotADrop, Result, Seen, Tree, carry_out, from_windows, look,
                              read_drop)

DISTRO = "kali-linux"                         # the user's, in every text their terminals sent
# Eight files, as the user dragged onto Windows Terminal at once on 2026-10-10. The first
# two and the last have the names of that drop; the plan doesn't record the other five.
EIGHT = (".bash_history", ".bashrc", ".profile", "hallux.hlx", "notes.txt", "special.ai",
         "todo.md", "matus_bonar.txt")
NO_SUCH = "no such file or folder on this computer: "
OUT_OF_REACH = "can't be reached from here: "


class Wslpath:
    """A stand-in for wslpath: it knows the paths it was given, and notes what it is asked."""

    def __init__(self, known=None):
        self.known, self.asked = known or {}, []

    def __call__(self, text):
        self.asked.append(text)
        return self.known.get(text)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A home with what the user dragged, in the distribution the user has."""
    home = tmp_path / "home" / "danika-hous"
    for folder in ("Pictures", "Music"):
        (home / folder).mkdir(parents=True)
    for name in EIGHT + ("my file.txt", "it's.txt"):
        (home / name).write_text(name)
    monkeypatch.setenv("WSL_DISTRO_NAME", DISTRO)
    return home


@pytest.fixture
def drives(tmp_path, monkeypatch):
    """A folder that stands in for /mnt, with a file on C: that has a space in its name."""
    mount = tmp_path / "mnt"
    (mount / "c" / "Users" / "dano").mkdir(parents=True)
    (mount / "c" / "Users" / "dano" / "my file.txt").write_text("from Windows")
    (mount / "c" / "Users" / "dano" / "b.txt").write_text("from Windows too")
    monkeypatch.setattr(hallux.importing, "MOUNT", str(mount))
    return mount


@pytest.fixture
def wslpath():
    """One that knows no path at all."""
    return Wslpath()


def windows(path, host="wsl$", distro=DISTRO, slash="\\"):
    """A path of this computer as Windows Terminal pastes it: \\\\wsl$\\kali-linux\\home\\…"""
    return f"{slash * 2}{host}{slash}{distro}" + str(path).replace("/", slash)


def vscode(path, distro=DISTRO):
    """And as VS Code's terminal types it: '//wsl/kali-linux/home/…'"""
    return f"'//wsl/{distro}{path}'"


def cut(text):
    """A text as a refusal repeats it: the end of it, where a path has its name."""
    return text if len(text) <= 60 else "…" + text[-59:]


def refused(text, translate):
    """The text is no drop. Returns the words that say why."""
    with pytest.raises(NotADrop) as info:
        read_drop(text, translate)
    return str(info.value)


def script(tmp_path, monkeypatch, body):
    """A program named wslpath, in front of everything else on the PATH."""
    programs = tmp_path / "bin"
    programs.mkdir()
    (programs / "wslpath").write_text(f"#!/bin/sh\n{body}\n")
    (programs / "wslpath").chmod(0o755)
    monkeypatch.setenv("PATH", f"{programs}{os.pathsep}{os.environ['PATH']}")


# ---------------------------------------------------------------- one path, and several

@pytest.mark.parametrize("form", ["{}", '"{}"', "'{}'", "  {}\r\n"])
def test_one_path_is_read_with_quotes_around_it_and_without(home, wslpath, form):
    assert read_drop(form.format(home / "notes.txt"), wslpath) == [home / "notes.txt"]
    assert wslpath.asked == []


def test_one_path_with_a_space_needs_no_quotes(home, wslpath):
    assert read_drop(str(home / "my file.txt"), wslpath) == [home / "my file.txt"]


def test_two_paths_are_cut_at_the_space_between_them(home, wslpath):
    text = f"{home / 'notes.txt'} {home / 'Music'}"
    assert read_drop(text, wslpath) == [home / "notes.txt", home / "Music"]


@pytest.mark.parametrize("mark", ['"', "'"])
def test_a_path_is_quoted_because_of_its_space_beside_one_that_is_not(home, wslpath, mark):
    text = f"{mark}{home / 'my file.txt'}{mark} {home / 'notes.txt'}"
    assert read_drop(text, wslpath) == [home / "my file.txt", home / "notes.txt"]


def test_a_backslash_in_front_of_a_space_is_a_shells_way(home, wslpath):
    text = str(home / "my file.txt").replace(" ", "\\ ") + f" {home / 'notes.txt'}"
    assert read_drop(text, wslpath) == [home / "my file.txt", home / "notes.txt"]


def test_a_quote_in_the_middle_of_a_name_is_a_character(home, wslpath):
    text = f"{home}/it's.txt {home}/notes.txt"
    assert read_drop(text, wslpath) == [home / "it's.txt", home / "notes.txt"]


def test_one_pair_of_quotes_comes_off_a_name_that_has_a_quote_in_it(home, wslpath):
    assert read_drop(f"'{home}/it's.txt'", wslpath) == [home / "it's.txt"]


def test_a_backslash_is_a_character_before_it_is_a_shells_escape(home, wslpath):
    (home / "a\\b.txt").write_text("a backslash in its name")
    (home / "ab.txt").write_text("and what a shell would make of it")
    text = f"{home}/a\\b.txt {home}/notes.txt"
    assert read_drop(text, wslpath) == [home / "a\\b.txt", home / "notes.txt"]


def test_paths_may_come_one_to_a_line(home, wslpath):
    text = f"{home / 'notes.txt'}\r\n{home / 'Music'}\r\n"
    assert read_drop(text, wslpath) == [home / "notes.txt", home / "Music"]


def test_the_same_path_twice_is_listed_once(home, wslpath):
    text = f"{home / 'notes.txt'} {home / 'Music'} {home / 'notes.txt'} {home / 'Music'}/"
    assert read_drop(text, wslpath) == [home / "notes.txt", home / "Music"]
    assert read_drop(vscode(home / "Music") * 2, wslpath) == [home / "Music"]


def test_a_link_is_a_path_as_it_was_dropped_also_one_that_leads_nowhere(home, wslpath):
    (home / "shots").symlink_to(home / "Pictures")
    (home / "dead").symlink_to(home / "gone")
    text = f"{home / 'shots'} {home / 'dead'}"
    assert read_drop(text, wslpath) == [home / "shots", home / "dead"]     # not resolved


# ---------------------------------------------------------------- file://

def test_a_file_address_is_turned_into_its_path(home, wslpath):
    address = "file://" + quote(str(home / "my file.txt"))
    assert "%20" in address
    assert read_drop(address, wslpath) == [home / "my file.txt"]
    for host in ("localhost", socket.gethostname()):
        named = f"file://{host}" + quote(str(home / "notes.txt"))
        assert read_drop(f"{address} {named}", wslpath) == [
            home / "my file.txt", home / "notes.txt"]


def test_a_file_address_of_another_computer_names_nothing_here(home, wslpath):
    address = "file://elsewhere.example" + quote(str(home / "notes.txt"))
    assert refused(address, wslpath) == NO_SUCH + cut(address)
    assert refused("file://[", wslpath) == NO_SUCH + "file://["         # and no address at all


# ---------------------------------------------------------------- what the user's terminals sent

def test_the_users_own_drop_a_folder_onto_windows_terminal(home, wslpath):
    text = windows(home / "Pictures")
    assert text.startswith("\\\\wsl$\\kali-linux\\") and text.endswith("\\danika-hous\\Pictures")
    assert read_drop(text, wslpath) == [home / "Pictures"]
    assert wslpath.asked == []                        # by rule: wslpath takes one path a call


def test_eight_files_dragged_at_once_are_one_paste(home, wslpath):
    text = " ".join(windows(home / name) for name in EIGHT)
    assert read_drop(text, wslpath) == [home / name for name in EIGHT]     # in their order
    assert wslpath.asked == []


def test_the_same_folder_as_vs_codes_terminal_typed_it(home, wslpath, monkeypatch):
    text = vscode(home / "Pictures")
    assert text.startswith("'//wsl/kali-linux/") and text.endswith("/danika-hous/Pictures'")
    assert read_drop(text, wslpath) == [home / "Pictures"]
    monkeypatch.setenv("WSL_DISTRO_NAME", "Kali-Linux")       # Windows doesn't mind the case
    assert read_drop(text, wslpath) == [home / "Pictures"]
    assert wslpath.asked == []


def test_two_drops_into_vs_code_come_with_nothing_between_them(home, wslpath):
    text = vscode(home / "Pictures") + vscode(home / "hallux.hlx")
    assert "Pictures''//wsl/" in text
    assert read_drop(text, wslpath) == [home / "Pictures", home / "hallux.hlx"]
    assert wslpath.asked == []


@pytest.mark.parametrize("host", ["wsl$", "wsl.localhost", "WSL.LOCALHOST"])
@pytest.mark.parametrize("slash", ["\\", "/"])
def test_both_names_of_the_share_are_read_with_either_slash(home, wslpath, host, slash):
    text = windows(home / "special.ai", host, slash=slash)
    assert read_drop(text, wslpath) == [home / "special.ai"]
    assert wslpath.asked == []


@pytest.mark.parametrize("name", ["Ubuntu", None])
def test_a_path_of_another_distribution_cant_be_reached(home, wslpath, monkeypatch, name):
    if name is None:
        monkeypatch.delenv("WSL_DISTRO_NAME")
    else:
        monkeypatch.setenv("WSL_DISTRO_NAME", name)
    written = f"//wsl/kali-linux{home / 'Pictures'}"
    assert refused(vscode(home / "Pictures"), wslpath) == OUT_OF_REACH + written
    assert wslpath.asked == [written]                 # once, though three readings name it


def test_what_cant_be_reached_is_named_as_one_path_also_in_a_paste_of_several(home, wslpath):
    first = windows(home / "notes.txt", distro="Ubuntu")
    text = f"{first} {windows(home / 'Music', distro='Ubuntu')}"
    assert refused(text, wslpath) == OUT_OF_REACH + first
    text = f"{home / 'notes.txt'} {first}"            # and when it isn't the first of them
    assert refused(text, wslpath) == OUT_OF_REACH + first


def test_a_file_of_this_distribution_that_is_gone_is_no_such_file(home, wslpath):
    text = windows(home / "gone.txt")
    assert refused(text, wslpath) == NO_SUCH + cut(text)
    assert wslpath.asked == []                        # wslpath could say nothing else of it


def test_the_whole_distribution_is_its_root(home, wslpath):
    assert read_drop("\\\\wsl$\\kali-linux", wslpath) == [Path("/")]
    assert read_drop("\\\\wsl$\\kali-linux\\", wslpath) == [Path("/")]


# ---------------------------------------------------------------- a Windows drive

@pytest.mark.parametrize("text", [
    r"C:\Users\dano\my file.txt", r'"C:\Users\dano\my file.txt"', "c:/Users/dano/my file.txt"])
def test_a_drive_is_found_where_wsl_mounts_it(drives, wslpath, text):
    assert read_drop(text, wslpath) == [drives / "c" / "Users" / "dano" / "my file.txt"]
    assert wslpath.asked == []


def test_a_drive_the_rule_cant_find_is_asked_of_wslpath(drives, tmp_path):
    (tmp_path / "windows" / "d").mkdir(parents=True)
    (tmp_path / "windows" / "d" / "cat.png").write_text("a cat")
    wslpath = Wslpath({r"D:\cat.png": str(tmp_path / "windows" / "d" / "cat.png")})
    assert read_drop(r"D:\cat.png", wslpath) == [tmp_path / "windows" / "d" / "cat.png"]
    assert wslpath.asked == [r"D:\cat.png"]


def test_no_backslash_of_a_windows_path_is_eaten(drives, wslpath):
    text = r'"C:\Users\dano\my file.txt" C:\Users\dano\b.txt'
    users = drives / "c" / "Users" / "dano"
    assert read_drop(text, wslpath) == [users / "my file.txt", users / "b.txt"]
    assert wslpath.asked == []


def test_a_drive_that_wslpath_refuses_cant_be_reached(drives, wslpath):
    assert refused(r"E:\photos\cat.png", wslpath) == OUT_OF_REACH + r"E:\photos\cat.png"


def test_a_file_that_isnt_where_wslpath_says_is_no_such_file(drives):
    wslpath = Wslpath({r"C:\gone.txt": str(drives / "c" / "gone.txt")})
    assert refused(r"C:\gone.txt", wslpath) == NO_SUCH + r"C:\gone.txt"


def test_a_path_that_exists_as_it_is_written_is_not_translated(home, wslpath):
    text = f"/{home / 'notes.txt'}"                   # two slashes in front, as a share has
    assert read_drop(text, wslpath) == [Path(text)]
    assert wslpath.asked == []


# ---------------------------------------------------------------- what is no drop

def test_one_path_of_two_that_doesnt_exist_makes_it_no_drop(home, wslpath):
    text = f"{home / 'notes.txt'} {home / 'gone.txt'}"
    assert len(text) > 60
    assert refused(text, wslpath) == NO_SUCH + "…" + text[-59:]       # 60 characters of it
    assert refused(text, wslpath).endswith("/danika-hous/gone.txt")


@pytest.mark.parametrize("text", ["ls", "notes.txt", "./notes.txt", "~/notes.txt", "hello there"])
def test_a_word_is_never_a_file_in_halluxs_own_directory(home, wslpath, monkeypatch, text):
    monkeypatch.chdir(home)
    (home / "ls").write_text("a file named like a command")
    assert refused(text, wslpath) == NO_SUCH + text
    assert wslpath.asked == []


@pytest.mark.parametrize("text", ["", "   \r\n", "/tmp\0/etc", "/" + "a" * LONGEST])
def test_an_empty_text_a_nul_and_a_text_too_long_are_not_a_path(wslpath, text):
    assert refused(text, wslpath) == "not a path"


def test_a_text_of_64_kb_is_still_read(wslpath):
    text = "/" + "a" * (LONGEST - 1)
    assert refused(text, wslpath) == NO_SUCH + cut(text)


def test_a_quote_that_never_closes_is_no_drop(home, wslpath):
    text = f"'{home / 'notes.txt'}"
    assert refused(text, wslpath).startswith(NO_SUCH)


# ---------------------------------------------------------------- wslpath itself

def test_without_wslpath_nothing_is_translated(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert from_windows("C:\\") is None


def test_wslpath_gets_the_path_as_one_argument_and_its_answer_is_the_path(tmp_path, monkeypatch):
    script(tmp_path, monkeypatch, 'printf "%s|%s|%s\\n" "$#" "$1" "$2"')
    assert from_windows(r"C:\Users\dano\a b.png") == r"2|-u|C:\Users\dano\a b.png"


def test_a_wslpath_that_fails_or_says_nothing_translates_nothing(tmp_path, monkeypatch):
    script(tmp_path, monkeypatch, 'echo "wslpath: $2"; exit 1')
    assert from_windows(r"\\wsl$\Ubuntu\home") is None
    (tmp_path / "bin" / "wslpath").write_text("#!/bin/sh\n")
    assert from_windows("C:\\") is None


def test_a_wslpath_that_hangs_is_given_up(tmp_path, monkeypatch):
    script(tmp_path, monkeypatch, "exec sleep 30")
    monkeypatch.setattr(hallux.importing, "WSLPATH_SECONDS", 0.2)
    started = time.monotonic()
    assert from_windows("C:\\") is None
    assert time.monotonic() - started < 5


@pytest.mark.skipif(shutil.which("wslpath") is None, reason="only in WSL")
def test_the_real_wslpath_knows_where_c_is():
    found = from_windows("C:\\")
    assert found is not None and found.startswith("/") and found.rstrip("/").endswith("/c")


# ================================================================ the tree

MUSIC = "/home/user/Music"

not_as_root = pytest.mark.skipif(os.geteuid() == 0, reason="root reads everything")


@pytest.fixture
def root(tmp_path):
    """A machine. Its user has an empty Music folder, and a Pictures folder with a picture."""
    root = tmp_path / "world"
    (root / "home" / "user" / "Music").mkdir(parents=True)
    (root / "home" / "user" / "Pictures").mkdir()
    (root / "home" / "user" / "Pictures" / "cat.png").write_text("a cat")
    (root / ".hallux").mkdir()
    (root / ".hallux" / "memory.md").write_text("# memory\n")
    return root


@pytest.fixture
def disk(root):
    return Disk(root)


@pytest.fixture
def desk(tmp_path):
    """A folder of the user's computer, outside the machine: what is dragged lies here."""
    desk = tmp_path / "desk"
    desk.mkdir()
    return desk


def put(folder, **files):
    """Files in a folder, each with its text. Returns the folder."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, held in files.items():
        (folder / name.replace("_", ".")).write_text(held)
    return folder


def as_it_is(folder):
    """Everything in a folder as it is now: what it is, what it holds, when it was changed."""
    seen = {}
    for path in [folder, *sorted(folder.rglob("*"))]:
        found = path.lstat()
        held = (os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file()
                else None)
        seen[str(path.relative_to(folder))] = (found.st_mode, found.st_mtime_ns, held)
    return seen


def looked(disk, sources, into=MUSIC, **more):
    """look(), and the machine is as it was afterwards: nothing was written."""
    before = as_it_is(disk.root)
    tree = look(disk, sources, into, **more)
    assert as_it_is(disk.root) == before
    return tree


def drawn(tree):
    """The lines of a tree, as few words as a test needs: each name behind its depth, and
    its mark."""
    return [("  " * line.depth + line.name + "/" * (line.kind == FOLDER), line.mark)
            for line in tree.lines]


def test_a_file_into_an_empty_folder_is_one_line(disk, desk):
    put(desk, notes_txt="hello")
    tree = looked(disk, [desk / "notes.txt"])
    assert tree.into == MUSIC and tree.refused is None and not tree.stopped
    assert tree.lines == (Line(0, "notes.txt", FILE, 5),)
    assert tree.counts == Counts(folders=0, files=1, bytes=5, marks={})


def test_a_folder_with_folders_in_it(disk, desk):
    put(desk / "Pictures", cat_png="12345", a_txt="1", Zoo_png="12")
    put(desk / "Pictures" / "holiday", beach_jpg="123", dunes_jpg="1234")
    put(desk / "Pictures" / "holiday" / "raw", one_raw="1234567")
    put(desk, notes_txt="hello")
    tree = looked(disk, [desk / "Pictures", desk / "notes.txt"], "/home/user/Music")
    assert tree.lines == (
        Line(0, "Pictures", FOLDER, size=22, files=6),
        Line(1, "Zoo.png", FILE, 2),                  # by name, as sorted() does: Z before a
        Line(1, "a.txt", FILE, 1),
        Line(1, "cat.png", FILE, 5),
        Line(1, "holiday", FOLDER, size=14, files=3), # a folder among the files, by its name
        Line(2, "beach.jpg", FILE, 3),
        Line(2, "dunes.jpg", FILE, 4),
        Line(2, "raw", FOLDER, size=7, files=1),
        Line(3, "one.raw", FILE, 7),
        Line(0, "notes.txt", FILE, 5))
    assert tree.counts == Counts(folders=3, files=7, bytes=27, marks={})


def test_the_sources_come_in_the_order_they_were_dropped(disk, desk):
    put(desk, b_txt="b", a_txt="a")
    assert drawn(looked(disk, [desk / "b.txt", desk / "a.txt"])) == [("b.txt", ""), ("a.txt", "")]


def test_the_destination_may_be_given_from_the_shells_directory(disk, desk):
    put(desk, notes_txt="hello")
    disk.cwd = "/home/user"
    assert looked(disk, [desk / "notes.txt"], "Music/../Music").into == MUSIC


# ---------------------------------------------------------------- the marks

def test_a_file_over_a_file_exists(disk, root, desk):
    put(desk, cat_png="another cat")
    tree = looked(disk, [desk / "cat.png"], "/home/user/Pictures")
    assert tree.lines == (Line(0, "cat.png", FILE, 11, mark=EXISTS),)
    assert tree.counts == Counts(files=1, bytes=11, marks={EXISTS: 1})


def test_a_file_where_a_folder_is_and_a_folder_where_a_file_is_are_in_the_way(disk, root, desk):
    put(desk, Pictures="a file named like the folder")
    put(desk / "cat.png", inside_txt="a folder named like the picture")
    tree = looked(disk, [desk / "Pictures"], "/home/user")
    assert drawn(tree) == [("Pictures", IN_THE_WAY)]
    tree = looked(disk, [desk / "cat.png"], "/home/user/Pictures")
    assert drawn(tree) == [("cat.png/", IN_THE_WAY)]  # and what is in it is left out
    assert tree.counts == Counts(folders=1, marks={IN_THE_WAY: 1})


def test_a_link_at_the_place_is_in_the_way_wherever_it_leads(disk, root, desk, tmp_path):
    put(desk, notes_txt="hello", gone_txt="hello")
    put(desk / "album", one_png="1")
    put(desk / "out", two_png="2")
    home = root / "home" / "user"
    (home / "Music" / "notes.txt").symlink_to(home / "Pictures" / "cat.png")   # to a file
    (home / "Music" / "gone.txt").symlink_to(home / "nowhere")                 # to nothing
    (home / "Music" / "album").symlink_to(home / "Pictures")                   # to a folder
    (home / "Music" / "out").symlink_to(tmp_path)                              # out of the machine
    tree = looked(disk, [desk / "notes.txt", desk / "gone.txt", desk / "album", desk / "out"])
    assert drawn(tree) == [("notes.txt", IN_THE_WAY), ("gone.txt", IN_THE_WAY),
                           ("album/", IN_THE_WAY), ("out/", IN_THE_WAY)]


def test_the_machines_own_folder_dropped_where_it_is_is_already_here(disk, root):
    tree = looked(disk, [root / "home" / "user" / "Pictures"], "/home/user")
    assert tree.lines == (Line(0, "Pictures", FOLDER, mark=HERE),)     # the user's first drop
    assert tree.counts == Counts(folders=1, marks={HERE: 1})
    tree = looked(disk, [root / "home" / "user" / "Pictures" / "cat.png"], "/home/user/Pictures")
    assert drawn(tree) == [("cat.png", HERE)]


def test_a_file_that_is_its_own_place_inside_a_dropped_folder_is_already_here(disk, root, desk):
    put(desk / "Pictures", dog_png="a dog")
    os.link(root / "home" / "user" / "Pictures" / "cat.png", desk / "Pictures" / "cat.png")
    tree = looked(disk, [desk / "Pictures"], "/home/user")
    assert drawn(tree) == [("Pictures/", ""), ("  cat.png", HERE), ("  dog.png", "")]


def test_what_the_disk_refuses_cant_go_there(disk, root, desk):
    put(desk / ".hallux", config_toml="model = 'mine'")
    tree = looked(disk, [desk / ".hallux"], "/")
    assert tree.lines == (Line(0, ".hallux", FOLDER, mark=NO_PLACE),)
    assert tree.counts == Counts(folders=1, marks={NO_PLACE: 1})
    put(desk / "deeper" / ".hallux", config_toml="not the machine's")
    assert drawn(looked(disk, [desk / "deeper"], "/")) == [                 # only the one in /
        ("deeper/", ""), ("  .hallux/", ""), ("    config.toml", "")]


def test_a_destination_behind_a_link_out_of_the_machine_takes_nothing(disk, root, desk, tmp_path):
    put(desk, notes_txt="hello")
    put(desk / "album", one_png="1")
    outside = put(tmp_path / "outside" / "sub")
    (root / "home" / "user" / "out").symlink_to(tmp_path / "outside")
    before = as_it_is(tmp_path / "outside")
    tree = looked(disk, [desk / "notes.txt", desk / "album"], "/home/user/out/sub")
    assert tree.refused is None
    assert drawn(tree) == [("notes.txt", NO_PLACE), ("album/", NO_PLACE)]
    assert as_it_is(tmp_path / "outside") == before and outside.is_dir()


@not_as_root
def test_a_folder_that_cant_be_listed_and_a_file_that_cant_be_opened_cant_be_read(disk, desk):
    put(desk / "album" / "locked", one_png="1")
    put(desk / "album", secret_txt="12345", open_txt="1")
    (desk / "album" / "locked").chmod(0)
    (desk / "album" / "secret.txt").chmod(0)
    try:
        tree = looked(disk, [desk / "album"])
    finally:
        (desk / "album" / "locked").chmod(0o755)
    assert drawn(tree) == [("album/", ""), ("  locked/", UNREADABLE), ("  open.txt", ""),
                           ("  secret.txt", UNREADABLE)]
    assert tree.counts == Counts(folders=2, files=2, bytes=6, marks={UNREADABLE: 2})


def test_a_dropped_link_that_leads_nowhere_cant_be_read(disk, desk):
    (desk / "dead").symlink_to(desk / "gone")
    assert looked(disk, [desk / "dead"]).lines == (Line(0, "dead", OTHER, mark=UNREADABLE),)


def test_a_pipe_is_not_copied(disk, desk):
    os.mkfifo(desk / "pipe")
    os.mkfifo(put(desk / "album") / "another")
    tree = looked(disk, [desk / "pipe", desk / "album"])
    assert tree.lines == (Line(0, "pipe", OTHER, mark=NOT_COPIED),
                          Line(0, "album", FOLDER, size=0, files=1),
                          Line(1, "another", OTHER, mark=NOT_COPIED))
    assert tree.counts == Counts(folders=1, files=2, marks={NOT_COPIED: 2})


def test_a_link_in_a_dropped_folder_is_copied_as_a_link_and_not_followed(disk, desk):
    put(desk / "album" / "holiday", beach_jpg="123")
    (desk / "album" / "latest").symlink_to("holiday/beach.jpg")
    (desk / "album" / "all").symlink_to(desk)         # a folder, and the album is in it again
    (desk / "album" / "dead").symlink_to("gone")
    tree = looked(disk, [desk / "album"])
    assert tree.lines == (
        Line(0, "album", FOLDER, size=3, files=4),
        Line(1, "all", LINK, mark=f"→ {desk}"),
        Line(1, "dead", LINK, mark="→ gone"),
        Line(1, "holiday", FOLDER, size=3, files=1),
        Line(2, "beach.jpg", FILE, 3),
        Line(1, "latest", LINK, mark="→ holiday/beach.jpg"))
    assert tree.counts == Counts(folders=2, files=4, bytes=3, marks={LEADS: 3})


def test_a_link_in_a_dropped_folder_whose_name_is_taken_is_in_the_way(disk, root, desk):
    (put(desk / "Pictures") / "cat.png").symlink_to("dog.png")
    (desk / "Pictures" / "pet.png").symlink_to("dog.png")
    (root / "home" / "user" / "Pictures" / "pet.png").symlink_to("dog.png")    # by the same link
    tree = looked(disk, [desk / "Pictures"], "/home/user")
    assert drawn(tree) == [("Pictures/", ""), ("  cat.png", IN_THE_WAY), ("  pet.png", IN_THE_WAY)]


def test_a_dropped_link_is_followed_and_comes_under_its_own_name(disk, desk):
    put(desk / "Pictures", cat_png="12345")
    (desk / "shots").symlink_to(desk / "Pictures")
    (desk / "pet.png").symlink_to(desk / "Pictures" / "cat.png")
    tree = looked(disk, [desk / "shots", desk / "pet.png"])
    assert tree.lines == (Line(0, "shots", FOLDER, size=5, files=1),
                          Line(1, "cat.png", FILE, 5), Line(0, "pet.png", FILE, 5))


def test_a_folder_into_a_folder_of_its_name_is_merged(disk, root, desk):
    put(desk / "Pictures", cat_png="another cat", dog_png="a dog")
    tree = looked(disk, [desk / "Pictures"], "/home/user")
    assert drawn(tree) == [("Pictures/", ""), ("  cat.png", EXISTS), ("  dog.png", "")]
    assert tree.counts == Counts(folders=1, files=2, bytes=16, marks={EXISTS: 1})


# ---------------------------------------------------------------- what refuses the whole drop

def test_a_folder_isnt_copied_into_itself(disk, root, desk):
    home = root / "home"
    for into in ("/home", "/home/user", MUSIC):       # the folder itself, and inside it
        tree = looked(disk, [desk, home], into)
        assert tree.refused == "would be copied into itself: home"
        assert tree.lines == () and tree.counts == Counts()
    (desk / "the machine").symlink_to(root)           # and by another name
    assert looked(disk, [desk / "the machine"]).refused == (
        "would be copied into itself: the machine")
    assert looked(disk, [Path("/")]).refused == "would be copied into itself: /"


def test_a_destination_that_is_gone_or_is_no_folder(disk, root, desk):
    put(desk, notes_txt="hello")
    tree = looked(disk, [desk / "notes.txt"], "/home/user/Videos")
    assert tree.refused == "the folder is gone: /home/user/Videos" and tree.lines == ()
    tree = looked(disk, [desk / "notes.txt"], "/home/user/Pictures/cat.png")
    assert tree.refused == "the folder is gone: /home/user/Pictures/cat.png"


def test_a_path_that_ends_in_two_dots_comes_under_the_name_of_what_it_leads_to(disk, desk):
    put(desk / "album" / "holiday", beach_jpg="123")
    tree = looked(disk, [desk / "album" / "holiday" / ".."])
    assert drawn(tree) == [("album/", ""), ("  holiday/", ""), ("    beach.jpg", "")]


# ---------------------------------------------------------------- the limits

def test_a_folder_lists_fifty_entries_and_counts_them_all(disk, desk):
    put(desk / "many", **{f"f{number:02}_txt": "12" for number in range(60)})
    tree = looked(disk, [desk / "many"])
    assert len(tree.lines) == 52
    assert tree.lines[0] == Line(0, "many", FOLDER, size=120, files=60)
    assert tree.lines[50] == Line(1, "f49.txt", FILE, 2)
    assert tree.lines[51] == Line(1, "… 10 more", MORE)
    assert tree.counts == Counts(folders=1, files=60, bytes=120, marks={})


def test_fifty_entries_are_listed_whole(disk, desk):
    put(desk / "many", **{f"f{number:02}_txt": "12" for number in range(50)})
    tree = looked(disk, [desk / "many"])
    assert len(tree.lines) == 51 and all(line.kind != MORE for line in tree.lines)


def test_what_a_folder_doesnt_list_is_walked_all_the_same(disk, root, desk):
    for number in range(53):
        put(desk / "many" / f"d{number:02}", new_txt="123", cat_png="12")
    put(desk / "many" / "d51", **{f"f{number:02}_txt": "1" for number in range(60)})
    put(root / "home" / "user" / "Music" / "many" / "d52", cat_png="here already")
    tree = looked(disk, [desk / "many"])
    assert len(tree.lines) == 1 + 50 * 3 + 1          # and no line of a folder that has none
    assert tree.lines[0] == Line(0, "many", FOLDER, size=325, files=166)
    assert tree.lines[-1] == Line(1, "… 3 more", MORE)
    assert tree.counts == Counts(folders=54, files=166, bytes=325, marks={EXISTS: 1})


def test_every_dropped_thing_has_a_line_however_many_there_are(disk, desk):
    put(desk, **{f"f{number:02}_txt": "1" for number in range(60)})
    tree = looked(disk, sorted(desk.iterdir()))
    assert len(tree.lines) == 60 and tree.lines[-1].name == "f59.txt"


def test_the_tree_keeps_so_many_lines_and_counts_on(disk, desk, monkeypatch):
    monkeypatch.setattr(hallux.importing, "TREE_MAX", 5)
    put(desk / "album", **{f"f{number}_txt": "12" for number in range(7)})
    put(desk / "album" / "zz", one_png="1", two_png="2")
    put(desk, notes_txt="hello")
    tree = looked(disk, [desk / "album", desk / "notes.txt"])
    assert drawn(tree) == [("album/", ""), ("  f0.txt", ""), ("  f1.txt", ""), ("  f2.txt", ""),
                           ("  f3.txt", ""), ("… and more", "")]
    assert tree.lines[0] == Line(0, "album", FOLDER, size=16, files=9)
    assert tree.lines[-1] == Line(0, "… and more", MORE)
    assert tree.counts == Counts(folders=2, files=10, bytes=21, marks={})


def test_a_tree_of_just_so_many_lines_is_whole(disk, desk, monkeypatch):
    monkeypatch.setattr(hallux.importing, "TREE_MAX", 5)
    put(desk / "album", **{f"f{number}_txt": "12" for number in range(4)})
    tree = looked(disk, [desk / "album"])
    assert len(tree.lines) == 5 and tree.lines[-1].name == "f3.txt"


# ---------------------------------------------------------------- in a thread

def test_a_walk_that_is_stopped_before_it_starts_returns_at_once(disk, desk):
    put(desk / "album", one_png="1")
    stop = threading.Event()
    stop.set()
    tree = looked(disk, [desk / "album"], stop=stop)
    assert tree.stopped and tree.lines == () and tree.counts == Counts()
    assert tree.into == MUSIC and tree.refused is None


def test_a_walk_tells_how_far_it_is_and_stops_when_it_is_told_to(disk, root, desk, monkeypatch):
    monkeypatch.setattr(hallux.importing, "TELL_SECONDS", 0)
    put(desk / "album", **{f"f{number}_txt": "12" for number in range(9)})
    put(root / "home" / "user" / "Music" / "album", f1_txt="here already", f3_txt="and this")
    stop, told = threading.Event(), []

    def tell(counts):
        told.append(counts)
        if counts.files == 4:
            stop.set()

    tree = looked(disk, [desk / "album"], stop=stop, tell=tell)
    assert [counts.files for counts in told] == [0, 1, 2, 3, 4]
    assert [counts.marks for counts in told] == [                 # each as it was then
        {}, {}, {EXISTS: 1}, {EXISTS: 1}, {EXISTS: 2}]
    assert told[-1] == Counts(folders=1, files=4, bytes=8, marks={EXISTS: 2})
    assert tree.stopped and tree.lines == () and tree.counts == told[-1]


def test_a_walk_tells_some_times_a_second_not_at_every_file(disk, desk):
    put(desk / "album", **{f"f{number}_txt": "12" for number in range(200)})
    told = []
    tree = looked(disk, [desk / "album"], tell=told.append)
    assert tree.counts.files == 200 and len(told) < 20


# ================================================================ the copy

PICTURES = "/home/user/Pictures"


@pytest.fixture
def music(root):
    return root / "home" / "user" / "Music"


def held(folder):
    """What a folder holds: every path below it with its bytes, and a link with where it
    leads."""
    return {str(path.relative_to(folder)): os.readlink(path) if path.is_symlink()
            else path.read_bytes() if path.is_file() else None
            for path in sorted(folder.rglob("*"))}


def left_behind(folder):
    """The files a copy made beside the ones it wrote, and should have taken away."""
    return [path for path in folder.rglob("*") if TEMP_MARK in path.name]


def failing(monkeypatch, code, *names):
    """A copy_whole that fails with this errno for the files of these names."""
    def stand_in(source, real, stop=None, wrote=None):
        if source.name in names:
            raise OSError(code, os.strerror(code))
        return copy_whole(source, real, stop, wrote)

    monkeypatch.setattr(hallux.importing, "copy_whole", stand_in)


def test_a_file_arrives_under_its_name(disk, root, desk, music):
    put(desk, notes_txt="hello")
    assert carry_out(disk, [desk / "notes.txt"], MUSIC, None) == Result(
        MUSIC, files=1, folders=0, bytes=5, names=("notes.txt",))
    assert held(music) == {"notes.txt": b"hello"} and left_behind(root) == []


def test_a_folder_arrives_with_all_that_is_in_it(disk, root, desk, music):
    put(desk / "album", cat_png="12345", sound_bin="\x00\xff")
    put(desk / "album" / "holiday" / "raw", one_raw="1234567")
    put(desk / "album" / "empty")
    result = carry_out(disk, [desk / "album"], MUSIC, None)
    assert result == Result(MUSIC, files=3, folders=4, bytes=15, names=("album/",))
    assert held(music / "album") == held(desk / "album") and left_behind(root) == []
    assert (music / "album" / "empty").is_dir()


def test_three_hundred_files_arrive_as_they_are(disk, root, desk, music):
    for number in range(300):
        folder = desk / "many" / f"d{number % 7}" / f"e{number % 3}"
        put(folder, **{f"f{number}_bin": chr(number) * number})
    (desk / "many" / "latest").symlink_to("d0/e0/f0.bin")
    result = carry_out(disk, [desk / "many"], MUSIC, None)
    assert (result.files, result.folders, result.failed, result.ended) == (301, 29, (), None)
    assert held(music / "many") == held(desk / "many") and len(held(music / "many")) == 329


def test_a_folder_into_a_folder_of_its_name_is_merged_into_it(disk, root, desk):
    put(desk / "Pictures", dog_png="a dog")
    put(desk / "Pictures" / "holiday", beach_jpg="123")
    result = carry_out(disk, [desk / "Pictures"], "/home/user", None)
    assert result == Result("/home/user", files=2, folders=1, bytes=8, names=("Pictures/",))
    assert held(root / "home" / "user" / "Pictures") == {         # only holiday was made
        "cat.png": b"a cat", "dog.png": b"a dog", "holiday": None, "holiday/beach.jpg": b"123"}


def test_a_file_that_exists_is_replaced_or_skipped_as_the_user_said(disk, root, desk):
    cat = root / "home" / "user" / "Pictures" / "cat.png"
    cat.chmod(0o640)
    put(desk, cat_png="another cat")
    os.utime(desk / "cat.png", ns=(1_600_000_000_000_000_000, 1_500_000_000_000_000_000))
    before = as_it_is(root)
    assert carry_out(disk, [desk / "cat.png"], PICTURES, False) == Result(
        PICTURES, skipped={EXISTS: 1})
    assert carry_out(disk, [desk / "cat.png"], PICTURES, None) == Result(   # the user wasn't
        PICTURES, skipped={MEANWHILE: 1})                                   # asked about it
    assert as_it_is(root) == before
    assert carry_out(disk, [desk / "cat.png"], PICTURES, True) == Result(
        PICTURES, files=1, bytes=11, names=("cat.png",))
    assert cat.read_text() == "another cat" and left_behind(root) == []
    assert stat.S_IMODE(cat.stat().st_mode) == 0o640              # the old file's mode,
    assert cat.stat().st_mtime_ns == 1_500_000_000_000_000_000    # the source's time


def test_what_has_a_mark_that_skips_is_skipped_and_its_place_stays(disk, root, desk, music):
    put(desk / "taken", inside_txt="a folder where a file is")
    put(desk, linked_txt="a file where a link is")
    put(music, taken="a file", own_txt="the machine's own")
    (music / "linked.txt").symlink_to("own.txt")
    os.mkfifo(desk / "pipe")
    (desk / "dead").symlink_to(desk / "gone")
    sources = [desk / "taken", desk / "linked.txt", desk / "pipe", desk / "dead", music / "own.txt"]
    before = as_it_is(root)
    for overwrite in (True, False, None):
        assert carry_out(disk, sources, MUSIC, overwrite) == Result(MUSIC, skipped={
            IN_THE_WAY: 2, NOT_COPIED: 1, UNREADABLE: 1, HERE: 1})
    assert as_it_is(root) == before


def test_nothing_is_written_into_the_hidden_folder_or_out_of_the_machine(disk, root, desk,
                                                                         tmp_path):
    put(desk / ".hallux", config_toml="model = 'mine'", memory_md="# not the machine's")
    put(desk, notes_txt="hello")
    outside = put(tmp_path / "outside" / "sub")
    (root / "home" / "user" / "out").symlink_to(tmp_path / "outside")
    before, beyond = as_it_is(root), as_it_is(tmp_path / "outside")
    assert carry_out(disk, [desk / ".hallux"], "/", True) == Result("/", skipped={NO_PLACE: 1})
    into = "/home/user/out/sub"
    assert carry_out(disk, [desk / "notes.txt", desk / ".hallux"], into, True) == Result(
        into, skipped={NO_PLACE: 2})
    assert as_it_is(root) == before and as_it_is(tmp_path / "outside") == beyond
    assert outside.is_dir() and (root / ".hallux" / "memory.md").read_text() == "# memory\n"


def test_a_link_in_a_dropped_folder_arrives_as_the_link_it_is(disk, desk, music):
    put(desk / "album" / "holiday", beach_jpg="123")
    (desk / "album" / "latest").symlink_to("holiday/beach.jpg")
    (desk / "album" / "all").symlink_to(desk)         # leads out of the machine: dead in it
    (desk / "album" / "dead").symlink_to("gone")
    result = carry_out(disk, [desk / "album"], MUSIC, None)
    assert result == Result(MUSIC, files=4, folders=2, bytes=3, names=("album/",))
    assert os.readlink(music / "album" / "latest") == "holiday/beach.jpg"
    assert os.readlink(music / "album" / "all") == str(desk)
    assert os.readlink(music / "album" / "dead") == "gone"
    assert (music / "album" / "latest").read_text() == "123"


def test_a_dropped_link_arrives_as_what_it_leads_to(disk, desk, music):
    put(desk / "Pictures", cat_png="12345")
    (desk / "shots").symlink_to(desk / "Pictures")
    (desk / "pet.png").symlink_to(desk / "Pictures" / "cat.png")
    result = carry_out(disk, [desk / "shots", desk / "pet.png"], MUSIC, None)
    assert result == Result(MUSIC, files=2, folders=1, bytes=10, names=("shots/", "pet.png"))
    assert held(music) == {"pet.png": b"12345", "shots": None, "shots/cat.png": b"12345"}
    assert not (music / "shots").is_symlink() and not (music / "pet.png").is_symlink()


def test_a_new_file_has_a_new_files_mode_whatever_the_source_has(disk, root, desk, music):
    put(desk, photo_jpg="from a Windows drive", secret_txt="private")
    (desk / "photo.jpg").chmod(0o777)
    (desk / "secret.txt").chmod(0o600)
    (root / "plain.txt").write_text("x")              # the way the machine makes a file
    carry_out(disk, [desk / "photo.jpg", desk / "secret.txt"], MUSIC, None)
    assert (music / "photo.jpg").stat().st_mode == (root / "plain.txt").stat().st_mode
    assert (music / "secret.txt").stat().st_mode == (root / "plain.txt").stat().st_mode


def test_a_copy_stopped_inside_a_big_file_leaves_its_place_as_it_was(disk, root, desk, music,
                                                                    monkeypatch):
    monkeypatch.setattr(hallux.importing, "TELL_SECONDS", 0)
    put(desk, a_txt="first", c_txt="never reached")
    (desk / "big.bin").write_bytes(b"x" * 3 * 1024 * 1024)
    put(music, **{"big_bin": "the old one"})
    stop, told = threading.Event(), []

    def tell(counts):
        told.append(counts.bytes)
        if counts.bytes > 1024 * 1024:                # after the first piece of big.bin
            stop.set()

    result = carry_out(disk, [desk / "a.txt", desk / "big.bin", desk / "c.txt"], MUSIC, True,
                       stop=stop, tell=tell)
    assert result == Result(MUSIC, files=1, bytes=5, ended=STOPPED, names=("a.txt",))
    assert told == [5, 5, 5 + 1024 * 1024]            # a.txt's piece, a.txt, the first piece
    assert held(music) == {"a.txt": b"first", "big.bin": b"the old one"}
    assert left_behind(root) == []


def test_a_copy_that_is_stopped_before_it_starts_writes_nothing(disk, root, desk):
    put(desk / "album", one_png="1")
    stop, before = threading.Event(), as_it_is(root)
    stop.set()
    assert carry_out(disk, [desk / "album"], MUSIC, None, stop=stop) == Result(MUSIC, ended=STOPPED)
    assert as_it_is(root) == before


def test_what_fails_is_that_files_and_the_copy_goes_on(disk, root, desk, music, monkeypatch):
    put(desk / "album", a_txt="first", b_txt="can't be had", c_txt="third")
    failing(monkeypatch, errno.EIO, "b.txt")
    result = carry_out(disk, [desk / "album"], MUSIC, None)
    assert result == Result(MUSIC, files=2, folders=1, bytes=10, names=("album/",),
                            failed=(("album/b.txt", "Input/output error"),))
    assert held(music) == {"album": None, "album/a.txt": b"first", "album/c.txt": b"third"}


@not_as_root
def test_a_file_that_cant_be_read_is_skipped_between_two_that_can(disk, root, desk, music,
                                                                 monkeypatch):
    put(desk / "album", a_txt="first", b_txt="secret", c_txt="third")
    (desk / "album" / "b.txt").chmod(0)
    assert carry_out(disk, [desk / "album"], MUSIC, None) == Result(
        MUSIC, files=2, folders=1, bytes=10, names=("album/",), skipped={UNREADABLE: 1})
    monkeypatch.setattr(hallux.importing.os, "access", lambda path, mode: True)   # it seemed
    result = carry_out(disk, [desk / "album"], MUSIC, True)                       # readable
    assert result.failed == (("album/b.txt", "Permission denied"),) and result.files == 2
    assert held(music) == {"album": None, "album/a.txt": b"first", "album/c.txt": b"third"}
    assert left_behind(root) == []


def test_the_result_names_so_many_failures_and_counts_the_rest(disk, desk, monkeypatch):
    monkeypatch.setattr(hallux.importing, "FAILED_MAX", 2)
    names = [f"f{number}.txt" for number in range(5)]
    put(desk, ok_txt="fine", **{name.replace(".", "_"): "x" for name in names})
    failing(monkeypatch, errno.EIO, *names)
    result = carry_out(disk, sorted(desk.iterdir()), MUSIC, None)
    assert result.failed == (("f0.txt", "Input/output error"), ("f1.txt", "Input/output error"))
    assert (result.more, result.files, result.names) == (3, 1, ("ok.txt",))


@pytest.mark.parametrize("code", [errno.ENOSPC, errno.EDQUOT])
def test_a_full_disk_ends_the_copy_and_what_was_written_stays(disk, desk, music, monkeypatch, code):
    put(desk / "album", a_txt="first", b_txt="one too many", c_txt="third")
    failing(monkeypatch, code, "b.txt")
    result = carry_out(disk, [desk / "album"], MUSIC, None)
    assert result == Result(MUSIC, files=1, folders=1, bytes=5, ended=FULL, names=("album/",))
    assert held(music) == {"album": None, "album/a.txt": b"first"}


def test_a_destination_that_goes_away_ends_the_copy(disk, root, desk, music):
    put(desk / "album", a_txt="first", b_txt="second", c_txt="third")

    def tell(counts):
        if counts.files == 1:                         # after a.txt, someone removes the folder
            shutil.rmtree(music)

    result = carry_out(disk, [desk / "album"], MUSIC, None, tell=tell)
    assert result == Result(MUSIC, files=1, folders=1, bytes=5, names=("album/",),
                            ended="the folder is gone: /home/user/Music")
    assert not music.exists() and left_behind(root) == []


def test_a_copy_that_look_refuses_never_starts(disk, root, desk):
    put(desk, notes_txt="hello")
    before = as_it_is(root)
    assert carry_out(disk, [root / "home"], MUSIC, True) == Result(
        MUSIC, ended="would be copied into itself: home")
    assert carry_out(disk, [desk / "notes.txt"], "/home/user/Videos", True) == Result(
        "/home/user/Videos", ended="the folder is gone: /home/user/Videos")
    assert as_it_is(root) == before


@not_as_root
def test_a_folder_that_cant_be_made_fails_with_what_is_in_it(disk, root, desk, music):
    put(desk / "album", a_txt="first")
    put(desk, notes_txt="hello")
    music.chmod(0o555)
    try:
        result = carry_out(disk, [desk / "album", desk / "notes.txt"], MUSIC, None)
    finally:
        music.chmod(0o755)
    assert result == Result(MUSIC, failed=(
        ("album", "Permission denied"), ("album/a.txt", "No such file or directory"),
        ("notes.txt", "Permission denied")))
    assert held(music) == {}


def test_a_folder_is_made_only_where_none_is(tmp_path):
    (tmp_path / "there").mkdir()
    (tmp_path / "file").write_text("x")
    (tmp_path / "link").symlink_to(tmp_path / "there")
    assert hallux.importing._make_folder(tmp_path / "new") is True
    assert hallux.importing._make_folder(tmp_path / "there") is False
    for taken in ("file", "link"):                    # a name that something else took meanwhile
        with pytest.raises(FileExistsError):
            hallux.importing._make_folder(tmp_path / taken)
    assert (tmp_path / "new").is_dir() and (tmp_path / "link").is_symlink()


def test_a_reader_that_has_the_old_file_open_reads_it_to_its_end(disk, root, desk):
    cat = root / "home" / "user" / "Pictures" / "cat.png"
    put(desk, cat_png="another cat")
    with cat.open() as reader:                        # opened before the copy, read after it
        carry_out(disk, [desk / "cat.png"], PICTURES, True)
        assert reader.read() == "a cat"
    assert cat.read_text() == "another cat"


def test_the_names_are_those_under_which_something_was_written(disk, root, desk, music):
    put(desk / "Kept", cat_png="another cat")         # a folder in which nothing can be written
    put(desk / "new", one_png="1")
    put(desk / "empty")
    (put(desk / "Linked") / "latest").symlink_to("../new/one.png")
    put(desk, a_txt="a", own_txt="in the way of nothing, but there already")
    put(music / "Kept", cat_png="a cat")
    put(music / "Linked")                             # there already, and gets a link
    put(music, own_txt="the machine's")
    sources = [desk / "new", desk / "Kept", desk / "own.txt", desk / "a.txt", desk / "empty",
               desk / "Linked"]
    result = carry_out(disk, sources, MUSIC, False)
    assert result.names == ("new/", "a.txt", "empty/", "Linked/")         # in the order of the drop
    assert result.skipped == {EXISTS: 2} and (result.files, result.folders) == (3, 2)


def test_a_copy_tells_how_far_it_is_and_ends_at_the_trees_counts(disk, root, desk, music):
    put(desk / "album", a_txt="12345", b_txt="123", cat_png="1234567")
    put(desk / "album" / "holiday", beach_jpg="12")
    os.mkfifo(desk / "album" / "pipe")
    put(music / "album", b_txt="here already")
    sources, told = [desk / "album"], []
    counts = look(disk, sources, MUSIC).counts
    result = carry_out(disk, sources, MUSIC, False, tell=told.append)
    assert [(done.folders, done.files, done.bytes) for done in told] == [
        (1, 0, 0), (1, 1, 5), (1, 2, 8), (1, 3, 15), (2, 3, 15), (2, 4, 17), (2, 5, 17)]
    assert told[-1] == Counts(counts.folders, counts.files, counts.bytes)     # copied or not
    assert (result.files, result.bytes, result.skipped) == (3, 14, {EXISTS: 1, NOT_COPIED: 1})


def test_inside_a_big_file_a_copy_tells_some_times_a_second(disk, desk, monkeypatch):
    monkeypatch.setattr(hallux.disk, "PIECE", 4)
    put(desk, big_bin="0123456789")
    told = []
    carry_out(disk, [desk / "big.bin"], MUSIC, True, tell=lambda done: told.append(done.bytes))
    assert told == [10]                               # three pieces in no time: one word
    monkeypatch.setattr(hallux.importing, "TELL_SECONDS", 0)
    carry_out(disk, [desk / "big.bin"], MUSIC, True, tell=lambda done: told.append(done.bytes))
    assert told == [10, 4, 8, 10, 10]


# ================================================================ the machine's side

def in_a_loop(scenario):
    """Run a scenario in an event loop, where the panel makes its calls."""
    return asyncio.run(asyncio.wait_for(scenario(), 20))


async def until(condition, seconds=5):
    """Wait until something holds. The test fails if it never does."""
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "it never happened"
        await asyncio.sleep(0.002)


def threads():
    """The threads of imports that are alive."""
    return [thread for thread in threading.enumerate() if thread.name == "hallux-import"]


class Watched:
    """The machine's imports in the user's Music folder, and what was to be seen at every
    call for a new drawing."""

    def __init__(self, disk):
        disk.cwd = MUSIC
        self.imports = Imports(disk, lambda: self.drawn.append(self.imports.watch().state))
        self.drawn = []
        for name in ("watch", "drop", "reads", "start", "stop", "clear", "close"):
            setattr(self, name, getattr(self.imports, name))

    async def has(self, state):
        await until(lambda: self.watch().state == state)
        return self.watch()


@pytest.fixture
def held_back(monkeypatch):
    """Walks and copies that wait: each goes on when the test sets this, and ends at once
    when it is stopped."""
    go = threading.Event()
    real_look, real_copy = hallux.importing.look, hallux.importing.copy_whole

    def waited(stop):
        while not go.is_set() and not stop.is_set():
            time.sleep(0.001)

    def slow_look(disk, sources, into, stop=None, tell=None):
        waited(stop)
        return real_look(disk, sources, into, stop, tell)

    def slow_copy(source, real, stop=None, wrote=None):
        waited(stop)
        return real_copy(source, real, stop, wrote)

    monkeypatch.setattr(hallux.importing, "look", slow_look)
    monkeypatch.setattr(hallux.importing, "copy_whole", slow_copy)
    return go


def test_a_drop_is_looked_at_in_a_thread_and_then_its_tree_is_there(disk, desk, held_back):
    put(desk / "album", one_png="1")

    async def scenario():
        files = Watched(disk)
        assert files.watch() == Seen(EMPTY, MUSIC)
        assert files.drop(str(desk / "album")) is None
        assert files.watch() == Seen(LOOKING, MUSIC, ("album",))
        assert files.drawn == [] and len(threads()) == 1
        held_back.set()
        seen = await files.has(READY)
        assert seen == Seen(READY, MUSIC, ("album",), look(disk, [desk / "album"], MUSIC).lines,
                            Counts(folders=1, files=1, bytes=1))
        assert drawn(seen) == [("album/", ""), ("  one.png", "")]
        assert files.drawn[-1] == READY               # the terminal was asked to draw it
        await until(lambda: threads() == [])

    in_a_loop(scenario)


def test_more_drops_add_to_the_list_and_the_tree_is_worked_out_again(disk, desk, held_back):
    put(desk / "album", one_png="1")
    put(desk, notes_txt="hello", b_txt="b")

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "album"))
        disk.cwd = PICTURES                           # the list goes where its first drop went
        assert files.drop(str(desk / "notes.txt")) is None        # while the first is looked at
        assert files.watch() == Seen(LOOKING, MUSIC, ("album", "notes.txt"))
        await until(lambda: len(threads()) == 1)      # the first walk was stopped: one is left
        held_back.set()
        seen = await files.has(READY)
        assert drawn(seen) == [("album/", ""), ("  one.png", ""), ("notes.txt", "")]
        assert files.drop(f"'{desk / 'b.txt'}'") is None          # and when the tree is there
        assert files.watch().state == LOOKING and files.watch().lines == ()
        seen = await files.has(READY)
        assert drawn(seen)[2:] == [("notes.txt", ""), ("b.txt", "")]
        assert seen.counts == Counts(folders=1, files=3, bytes=7)
        assert files.drawn.count(READY) == 2          # the walk that was replaced reached nobody
        await until(lambda: threads() == [])

    in_a_loop(scenario)


def test_the_destination_is_the_shells_directory_at_the_first_drop(disk, desk, music):
    put(desk, notes_txt="hello", b_txt="b")

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "notes.txt"))
        disk.cwd = PICTURES                           # an answer of the AI changes it meanwhile
        files.drop(str(desk / "b.txt"))
        assert (await files.has(READY)).into == MUSIC
        files.start(None)
        seen = await files.has(DONE)
        assert seen.into == seen.result.into == MUSIC
        assert held(music) == {"b.txt": b"b", "notes.txt": b"hello"}
        files.clear()
        assert files.watch() == Seen(EMPTY, PICTURES)             # where a drop would go now

    in_a_loop(scenario)


def test_a_drop_that_is_refused_leaves_the_list_as_it_was(disk, root, desk, held_back):
    put(desk, notes_txt="hello")
    put(desk / "other", notes_txt="another one of that name")
    held_back.set()

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "notes.txt"))
        before = await files.has(READY)
        for text, said in [
                (str(desk / "notes.txt"), "already in the list: notes.txt"),
                (str(desk / "other" / "notes.txt"), "two things named notes.txt"),
                (f"{desk / 'other'} {root / 'home'}", "would be copied into itself: home"),
                ("hello", "no such file or folder on this computer: hello"),
                ("", "not a path")]:
            assert files.drop(text) == said
            assert files.watch() == before and threads() == []
        held_back.clear()
        files.start(None)
        copying = await files.has(COPYING)
        assert files.drop(str(desk / "other")) == "a copy is running"
        assert files.watch() == copying
        held_back.set()
        await files.has(DONE)

    in_a_loop(scenario)


def test_two_things_of_one_name_in_one_drop_are_refused(disk, desk):
    put(desk / "a", notes_txt="one")
    put(desk / "b", notes_txt="another")

    async def scenario():
        files = Watched(disk)
        text = f"{desk / 'a' / 'notes.txt'} {desk / 'b' / 'notes.txt'}"
        assert files.drop(text) == "two things named notes.txt"
        assert files.watch() == Seen(EMPTY, MUSIC) and threads() == []

    in_a_loop(scenario)


def test_a_copy_runs_in_a_thread_and_its_result_is_shown(disk, desk, music, held_back, caplog):
    put(desk / "album", a_txt="12345", b_txt="123")
    held_back.set()

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "album"))
        ready = await files.has(READY)
        held_back.clear()
        files.start(None)
        seen = files.watch()
        assert (seen.state, seen.lines, seen.counts) == (COPYING, ready.lines, ready.counts)
        assert seen.through == Counts(folders=0, files=0, bytes=0) and len(threads()) == 1
        await until(lambda: files.watch().through.folders == 1)   # the folder is made, and the
        assert held(music) == {"album": None}                     # first file is held back
        held_back.set()
        seen = await files.has(DONE)
        assert seen == Seen(DONE, MUSIC, ("album",), result=Result(
            MUSIC, files=2, folders=1, bytes=8, names=("album/",)))
        assert held(music) == {"album": None, "album/a.txt": b"12345", "album/b.txt": b"123"}
        assert files.drawn[-1] == DONE and COPYING in files.drawn
        await until(lambda: threads() == [])

    with caplog.at_level("INFO", logger="hallux"):
        in_a_loop(scenario)
    assert ("import into /home/user/Music: 2 files, 1 folders, 8 bytes; 0 skipped, 0 failed"
            in caplog.text)


def test_a_copy_asks_for_a_new_drawing_some_times_a_second_not_at_every_file(disk, desk):
    put(desk / "album", **{f"f{number}_txt": "12" for number in range(200)})

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "album"))
        await files.has(READY)
        files.start(None)
        assert (await files.has(DONE)).result.files == 200
        assert 2 <= len(files.drawn) < 20             # the tree, the copy now and then, its end

    in_a_loop(scenario)


def test_start_does_nothing_without_a_tree_that_can_be_copied(disk, root, desk, held_back):
    put(desk, notes_txt="hello")

    async def scenario():
        files = Watched(disk)
        files.start(None)                             # nothing was dropped
        assert files.watch().state == EMPTY
        files.drop(str(desk / "notes.txt"))
        files.start(None)                             # the tree isn't there yet
        assert files.watch().state == LOOKING
        files.clear()
        held_back.set()
        disk.cwd = "/home/user/Videos"                # a folder that is gone
        files.drop(str(desk / "notes.txt"))
        seen = await files.has(READY)
        assert seen.refused == "the folder is gone: /home/user/Videos" and seen.lines == ()
        files.start(True)
        assert files.watch() == seen
        files.clear()
        disk.cwd = "/home/user"                       # nothing in the tree would be copied
        files.drop(str(root / "home" / "user" / "Pictures"))
        seen = await files.has(READY)
        assert drawn(seen) == [("Pictures/", HERE)] and seen.counts.to_copy == 0
        files.start(True)
        assert files.watch() == seen
        await until(lambda: threads() == [])

    in_a_loop(scenario)


def test_a_copy_that_is_stopped_is_done_and_says_so(disk, desk, music, held_back):
    put(desk / "album", a_txt="12345", b_txt="123")
    held_back.set()

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "album"))
        await files.has(READY)
        held_back.clear()
        files.start(None)
        await until(lambda: files.watch().through.folders == 1)
        files.stop()
        seen = await files.has(DONE)
        assert seen.result == Result(MUSIC, folders=1, ended=STOPPED, names=("album/",))
        assert held(music) == {"album": None} and left_behind(music) == []
        await until(lambda: threads() == [])

    in_a_loop(scenario)


def test_a_walk_that_is_stopped_leaves_a_tree_that_cant_be_copied(disk, desk, held_back):
    put(desk / "album", a_txt="12345")

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "album"))
        files.stop()
        seen = await files.has(READY)
        assert (seen.refused, seen.lines) == (STOPPED, ())
        files.start(None)
        assert files.watch() == seen
        held_back.set()
        files.drop(str(desk / "album" / "a.txt"))     # one more drop, and it is looked at whole
        assert drawn(await files.has(READY)) == [("album/", ""), ("  a.txt", ""), ("a.txt", "")]

    in_a_loop(scenario)


def test_clearing_empties_the_list_and_stops_the_walk(disk, desk, music, held_back):
    put(desk, notes_txt="hello")

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "notes.txt"))
        files.clear()                                 # while it is looked at
        assert files.watch() == Seen(EMPTY, MUSIC)
        await until(lambda: threads() == [])          # the walk ended, though nobody let it go
        assert files.watch() == Seen(EMPTY, MUSIC) and files.drawn == []
        held_back.set()
        files.drop(str(desk / "notes.txt"))
        await files.has(READY)
        files.clear()                                 # with the tree there
        assert files.watch() == Seen(EMPTY, MUSIC)
        files.drop(str(desk / "notes.txt"))
        await files.has(READY)
        held_back.clear()
        files.start(None)
        copying = files.watch()
        files.clear()                                 # not while it copies
        assert files.watch() == copying
        held_back.set()
        await files.has(DONE)
        files.clear()                                 # the result is forgotten
        assert files.watch() == Seen(EMPTY, MUSIC) and held(music) == {"notes.txt": b"hello"}

    in_a_loop(scenario)


def test_a_drop_after_a_copy_starts_a_new_list_for_where_the_shell_is_then(disk, desk):
    put(desk, notes_txt="hello", b_txt="b")

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "notes.txt"))
        await files.has(READY)
        files.start(None)
        await files.has(DONE)
        disk.cwd = PICTURES
        assert files.drop("hello").startswith("no such file")     # refused: the result stays
        assert files.watch().state == DONE
        assert files.drop(str(desk / "b.txt")) is None
        seen = await files.has(READY)
        assert (seen.into, seen.names, seen.result) == (PICTURES, ("b.txt",), None)
        assert drawn(seen) == [("b.txt", "")]

    in_a_loop(scenario)


def test_closing_stops_a_copy_and_waits_until_its_thread_is_gone(disk, desk, music, held_back):
    put(desk / "album", a_txt="12345")
    held_back.set()

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "album"))
        await files.has(READY)
        held_back.clear()
        files.start(None)
        await until(lambda: files.watch().through.folders == 1)
        started = time.monotonic()
        files.close()
        assert time.monotonic() - started < 1 and threads() == []
        await asyncio.sleep(0.01)                     # and what it ended with reaches nobody
        assert files.watch().state == COPYING and DONE not in files.drawn
        assert held(music) == {"album": None} and left_behind(music) == []

    in_a_loop(scenario)


def test_closing_waits_for_a_walk_too_and_for_one_that_was_replaced(disk, desk, monkeypatch):
    put(desk, notes_txt="hello", b_txt="b")
    real_look = hallux.importing.look

    def slow_to_stop(disk, sources, into, stop=None, tell=None):
        time.sleep(0.2 if len(sources) == 1 else 0)   # the first one, in the middle of a folder
        stop.wait(5)
        return real_look(disk, sources, into, stop, tell)

    monkeypatch.setattr(hallux.importing, "look", slow_to_stop)

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "notes.txt"))
        files.drop(str(desk / "b.txt"))               # the first walk is stopped, and still at it
        assert len(threads()) == 2
        files.close()
        assert threads() == [] and files.drawn == []

    in_a_loop(scenario)


def test_a_thread_that_fails_says_so_in_the_tab_and_in_the_log(disk, desk, monkeypatch, caplog):
    put(desk, notes_txt="hello")

    def mistake(*args, **more):
        raise RuntimeError("a mistake in here")

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "notes.txt"))
        await files.has(READY)
        monkeypatch.setattr(hallux.importing, "carry_out", mistake)
        files.start(None)
        seen = await files.has(DONE)
        assert seen.result == Result(MUSIC, ended="failed: RuntimeError: a mistake in here")
        monkeypatch.setattr(hallux.importing, "look", mistake)
        files.drop(str(desk / "notes.txt"))
        seen = await files.has(READY)
        assert seen.refused == "couldn't be looked at: RuntimeError: a mistake in here"
        files.start(None)
        assert files.watch() == seen

    in_a_loop(scenario)
    assert caplog.text.count("an import's thread failed") == 2 and "Traceback" in caplog.text


def test_while_it_is_looked_at_the_counts_grow_and_only_the_walk_that_counts_is_heard(
        disk, desk, monkeypatch):
    put(desk, a_txt="a", b_txt="b")
    gates, real_look, real_copy = [], hallux.importing.look, hallux.importing.copy_whole
    copies = threading.Event()

    def telling(disk, sources, into, stop=None, tell=None):
        gates.append(threading.Event())
        mine = gates[-1]
        tell(Counts(folders=0, files=len(sources) * 10, bytes=5))         # so far
        mine.wait(5)
        tell(Counts(folders=0, files=len(sources) * 100, bytes=50))
        return real_look(disk, sources, into, stop, tell)

    def held(source, place, stop=None, wrote=None):
        copies.wait(5)
        return real_copy(source, place, stop, wrote)

    monkeypatch.setattr(hallux.importing, "look", telling)
    monkeypatch.setattr(hallux.importing, "copy_whole", held)

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "a.txt"))
        await until(lambda: files.watch().counts.files == 10)
        assert files.watch() == Seen(LOOKING, MUSIC, ("a.txt",), counts=Counts(0, 10, 5))
        await until(lambda: files.drawn == [LOOKING])             # its first word is drawn at once
        files.drop(str(desk / "b.txt"))
        await until(lambda: files.watch().counts.files == 20)
        gates[0].set()                                # the walk that was replaced says more
        await until(lambda: len(threads()) == 1)
        assert files.watch().counts == Counts(0, 20, 5)           # and nobody hears it
        gates[1].set()
        seen = await files.has(READY)
        assert seen.counts == Counts(files=2, bytes=2) and seen.through == Counts()
        files.start(None)                             # a tenth of a second hasn't passed
        assert files.watch().through == Counts()      # the copy starts at nothing,
        copies.set()
        await files.has(DONE)
        assert COPYING in files.drawn                 # and its first word is drawn at once too

    in_a_loop(scenario)


@pytest.mark.parametrize("why, said", [({"stopped": True}, STOPPED), ({"refused": "no"}, "no")])
def test_a_tree_that_is_refused_or_cut_short_cant_be_copied_whatever_it_counted(
        disk, desk, monkeypatch, why, said):
    put(desk, notes_txt="hello")
    monkeypatch.setattr(hallux.importing, "look", lambda disk, sources, into, stop, tell: Tree(
        into, counts=Counts(files=3, bytes=9), **why))

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "notes.txt"))
        seen = await files.has(READY)
        assert seen.refused == said and seen.counts.to_copy == 3
        files.start(None)
        assert files.watch() == seen and threads() == []

    in_a_loop(scenario)


def test_the_users_answer_about_what_exists_reaches_the_copy(disk, root, desk):
    put(desk, cat_png="another cat")
    cat = root / "home" / "user" / "Pictures" / "cat.png"

    async def scenario():
        files = Watched(disk)
        for overwrite, result, holds in [
                (False, Result(PICTURES, skipped={EXISTS: 1}), "a cat"),
                (None, Result(PICTURES, skipped={MEANWHILE: 1}), "a cat"),
                (True, Result(PICTURES, files=1, bytes=11, names=("cat.png",)), "another cat")]:
            disk.cwd = PICTURES
            files.drop(str(desk / "cat.png"))
            assert drawn(await files.has(READY)) == [("cat.png", EXISTS)]
            files.start(overwrite)
            assert (await files.has(DONE)).result == result and cat.read_text() == holds

    in_a_loop(scenario)


def test_a_drop_into_a_directory_behind_the_fence_is_taken_and_its_tree_says_so(
        disk, root, desk, tmp_path):
    put(desk, notes_txt="hello")
    put(tmp_path / "outside" / "sub")
    (root / "home" / "user" / "out").symlink_to(tmp_path / "outside")

    async def scenario():
        files = Watched(disk)
        disk.cwd = "/home/user/out/sub"               # a link that was made behind the shell's back
        assert files.drop(str(desk / "notes.txt")) is None
        seen = await files.has(READY)
        assert drawn(seen) == [("notes.txt", NO_PLACE)] and seen.refused is None
        files.start(None)
        assert files.watch() == seen

    in_a_loop(scenario)


def test_a_thread_that_outlives_the_loop_reports_to_nobody(disk, desk, held_back, monkeypatch):
    put(desk, notes_txt="hello")
    raised = []
    monkeypatch.setattr(threading, "excepthook", raised.append)

    async def scenario():
        Watched(disk).drop(str(desk / "notes.txt"))

    in_a_loop(scenario)                               # the loop is closed, and the walk goes on
    [thread] = threads()
    held_back.set()
    thread.join(5)
    assert not thread.is_alive() and raised == []


def test_closing_doesnt_wait_for_ever_for_a_thread_that_doesnt_answer(disk, desk, monkeypatch,
                                                                     caplog):
    put(desk, notes_txt="hello")
    inside, let_go = threading.Event(), threading.Event()
    monkeypatch.setattr(hallux.importing, "CLOSE_SECONDS", 0.05)
    monkeypatch.setattr(hallux.importing, "copy_whole",
                        lambda source, place, stop, wrote: inside.set() or let_go.wait(5) and False)

    async def scenario():
        files = Watched(disk)
        files.drop(str(desk / "notes.txt"))
        await files.has(READY)
        files.start(None)
        await until(inside.is_set)                    # in the middle of a file
        started = time.monotonic()
        files.close()                                 # a drive that doesn't answer, say
        assert 0.04 < time.monotonic() - started < 1 and len(threads()) == 1

    in_a_loop(scenario)
    assert "an import didn't stop in 0 seconds" in caplog.text
    let_go.set()
    for thread in threads():
        thread.join(5)
    assert threads() == []


def test_a_text_reads_as_a_drop_or_doesnt(disk, desk):
    put(desk, notes_txt="hello")
    files = Imports(disk)
    assert files.reads(f"'{desk / 'notes.txt'}'") is True
    assert files.reads("hello") is False and files.reads("") is False
    assert files.watch().state == EMPTY               # asking adds nothing


def test_what_would_be_copied_is_what_has_no_mark_that_skips_it():
    assert Counts().to_copy == 0
    assert Counts(folders=2, files=5, marks={EXISTS: 2, LEADS: 1}).to_copy == 7
    assert Counts(folders=2, files=5, marks={HERE: 1, IN_THE_WAY: 2, NO_PLACE: 1, UNREADABLE: 1,
                                             NOT_COPIED: 1, EXISTS: 1}).to_copy == 1
