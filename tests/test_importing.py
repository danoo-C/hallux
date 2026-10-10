"""Reading a drop, hallux/importing.py: the text a terminal sends for a drop becomes real
paths. Real files in a temporary folder, and a stand-in for wslpath, which notes what it
was asked."""
import os
import shutil
import socket
import threading
import time
from pathlib import Path
from urllib.parse import quote

import pytest

import hallux.importing
from hallux.disk import Disk
from hallux.importing import (EXISTS, FILE, FOLDER, HERE, IN_THE_WAY, LEADS, LINK, LONGEST, MORE,
                              NO_PLACE, NOT_COPIED, OTHER, UNREADABLE, Counts, Line, NotADrop,
                              from_windows, look, read_drop)

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
