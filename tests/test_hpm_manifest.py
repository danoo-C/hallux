"""hpm.toml, hallux/hpm/manifest.py: reading, the checks, kinds of files, patterns, versions.
No world, no disk: text in, a Manifest or a ManifestError out."""
import pytest

from hallux.hpm.manifest import (
    Extra, Manifest, ManifestError, Version, check_path, check_pattern, expand, match, place,
)

# hpm.md, section 3, as it stands: typed by hand, comments and all.
KITTYSTORY = '''
name = "kittystory"
version = "1.4"
summary = "Chat with characters built from personality packs"
author = "danika"
data_format = 2                              # migrations.md

requires.addons = ["web"]                    # the app's -w mode needs the web addon
requires.packages = []

memory_line = "kittystory: split-screen chat with characters made from personality packs; ..."

[files]
app  = ["/usr/local/bin/kittystory", "/usr/local/share/apps/kittystory/**"]
seed = ["/usr/local/share/apps/kittystory/data/state.json"]   # installed only if missing
data = []                                    # this package carries no data of its own

[extras]                                     # the checkboxes at install
packs      = { package = "kittystory-packs",    default = true }
characters = { package = "kittystory-chars",    default = true,  needs = ["packs"] }
memories   = { package = "kittystory-memories", default = false, needs = ["characters"] }
'''

CHARS = '''
name = "kittystory-chars"
version = "1.1"
data_format = 2
for = "kittystory"
[files]
data = ["~/.kittystory/chars/*/char.md", "~/.kittystory/scene.md", "~/.kittystory/assets/**"]
'''

BUNDLE = '''
name = "kitty-desktop"
version = "1.0"
summary = "All of danika's kitty apps"
bundle = ["kittystory", "kittymusic", "kittydash", "kittycalc", "kittyshop", "kittyfiles"]
'''

THEME = '''
name = "kittystory-theme"
version = "1.0"
for = "kittystory"
rules = ["Every program's colors are pink and soft, like a kitty's nose."]
'''


def problems(text: str) -> list[str]:
    with pytest.raises(ManifestError) as caught:
        Manifest.load(text)
    return caught.value.problems


def one(text: str) -> str:
    found = problems(text)
    assert len(found) == 1, found
    return found[0]


def base(more: str = "") -> str:
    return f'name = "app"\nversion = "1.0"\n{more}'


# ---------------------------------------------------------------- good manifests

def test_the_designs_kittystory_manifest_is_read():
    m = Manifest.load(KITTYSTORY)
    assert (m.name, str(m.version), m.author, m.data_format) == ("kittystory", "1.4", "danika", 2)
    assert m.summary == "Chat with characters built from personality packs"
    assert m.requires_addons == ("web",) and m.requires_packages == ()
    assert m.memory_line.startswith("kittystory: split-screen chat")
    assert m.files == {"app": ("/usr/local/bin/kittystory", "/usr/local/share/apps/kittystory/**"),
                       "seed": ("/usr/local/share/apps/kittystory/data/state.json",),
                       "data": ()}
    assert m.extras == {
        "packs": Extra("packs", "kittystory-packs", True, ()),
        "characters": Extra("characters", "kittystory-chars", True, ("packs",)),
        "memories": Extra("memories", "kittystory-memories", False, ("characters",)),
    }
    assert list(m.extras) == ["packs", "characters", "memories"]     # the order of the file
    assert not m.is_bundle and not m.private and m.for_app is None


def test_a_data_package():
    m = Manifest.load(CHARS)
    assert m.for_app == "kittystory" and m.data_format == 2
    assert m.files["data"] == ("~/.kittystory/chars/*/char.md", "~/.kittystory/scene.md",
                               "~/.kittystory/assets/**")


def test_a_bundle_has_a_version_and_only_its_list():
    m = Manifest.load(BUNDLE)
    assert m.is_bundle and m.bundle[0] == "kittystory" and len(m.bundle) == 6
    assert str(m.version) == "1.0"
    assert m.files == {"app": (), "seed": (), "data": ()}


def test_a_rules_extra():
    m = Manifest.load(THEME)
    assert m.rules == ("Every program's colors are pink and soft, like a kitty's nose.",)


def test_the_defaults():
    m = Manifest.load(base())
    assert (m.summary, m.author, m.memory_line) == ("", "", "")
    assert m.data_format == 1 and m.private is False and m.rules == () and m.extras == {}
    assert m.requires_addons == () and m.requires_packages == ()
    assert Manifest.load(base('[extras]\nx = { package = "x-data" }')).extras["x"].default is False


def test_bytes_are_read_as_utf8():
    assert Manifest.load(KITTYSTORY.encode()).name == "kittystory"
    assert one(b'name = "\xff"') == "it isn't UTF-8 text"


# ---------------------------------------------------------------- kinds of files

def test_a_file_two_kinds_match_takes_the_narrower():
    m = Manifest.load(KITTYSTORY)
    assert m.kind_of("/usr/local/share/apps/kittystory/data/state.json") == "seed"
    assert m.kind_of("/usr/local/share/apps/kittystory/app.js") == "app"
    assert m.kind_of("/usr/local/share/apps/kittystory/sprites/emma.svg") == "app"
    assert m.kind_of("/usr/local/bin/kittystory") == "app"
    assert m.kind_of("/usr/local/bin/kittymusic") is None
    assert m.kind_of("~/.kittystory/packs/tsundere.pack") is None


def test_data_wins_over_seed_and_app():
    m = Manifest.load(base('[files]\napp = ["/opt/a/**"]\nseed = ["/opt/a/s/*"]\n'
                           'data = ["/opt/a/s/d.json"]'))
    assert m.kind_of("/opt/a/s/d.json") == "data"
    assert m.kind_of("/opt/a/s/x.json") == "seed"
    assert m.kind_of("/opt/a/x") == "app"


# ---------------------------------------------------------------- the checks

def test_every_problem_is_told_at_once():
    found = problems('''
name = "9lives"
version = "1.04"
colour = "pink"
data_format = 0
memory_line = "two\\nlines"
private = "yes"
[files]
app = ["usr/bin/x", "/proc/cpuinfo"]
code = ["/x"]
[extras]
a = { package = "pa", needs = ["b"] }
b = { package = "pb", needs = ["a"] }
c = { package = "pc", needs = ["nothing"], colour = "red" }
''')
    text = " | ".join(found)
    for words in ("unknown key 'colour'", "name must be", "version:", "data_format",
                  "memory_line", "private", "must start with / or ~/", "under /proc",
                  "unknown kind 'code'", "circle", "'nothing', which is no extra",
                  "extras.c: unknown key 'colour'"):
        assert words in text, words
    assert len(found) == 12


def test_the_error_says_how_many():
    with pytest.raises(ManifestError, match="the manifest has 2 problems: name must be"):
        Manifest.load('name = "-"\nversion = "x"')


@pytest.mark.parametrize("text, words", [
    ('version = "1.0"', "name must be"),
    ('name = "app"', "version is missing"),
    (base('summary = "' + "x" * 121 + '"'), "summary must be one line"),
    (base('author = ["danika"]'), "author must be one line"),
    (base('memory_line = "' + "x" * 301 + '"'), "memory_line must be one line"),
    (base("data_format = true"), "data_format must be a whole number"),
    (base("data_format = 1.5"), "data_format must be a whole number"),
    (base('requires = "web"'), "requires must be a table"),
    (base('requires.addons = ["Web Addon"]'), "requires.addons must be a list of names"),
    (base('requires.addons = ["web", "web"]'), "requires.addons names one package twice"),
    (base('requires.colours = []'), "requires: unknown key 'colours'"),
    (base('requires.packages = ["9x"]'), "requires.packages must be a list of names"),
    (base('files = ["/x"]'), "files must be a table"),
    (base('[files]\napp = "/x"'), "files.app must be a list of patterns"),
    (base('[files]\napp = ["/x"]\ndata = ["/x"]'), "'/x' is in files.app and in files.data"),
    (base('[files]\napp = ["/x", "/x"]'), "'/x' is twice in files.app"),
    (base('extras = 3'), "extras must be a table"),
    (base('[extras]\nx = "x-data"'), "extras.x must be a table"),
    (base('[extras]\n"a b" = { package = "x" }'), "an extra's key must be a name"),
    (base('[extras]\nx = { default = true }'), "extras.x: package must be the name"),
    (base('[extras]\nx = { package = "p", default = "yes" }'), "default must be true or false"),
    (base('[extras]\nx = { package = "p", needs = "y" }'), "needs must be a list"),
    (base('[extras]\nx = { package = "p", needs = ["x"] }'), "extras.x needs itself"),
    (base('[extras]\nx = { package = "p" }\ny = { package = "p" }'), "p is the package of extras.x"),
    (base('for = "the app"'), "for must be the name"),
    (base('rules = []'), "rules must be a list of lines"),
    (base('rules = ["one\\ntwo"]'), "rules must be a list of lines"),
    (base('bundle = []'), "bundle must name at least one package"),
    (base('bundle = "kittystory"'), "bundle must be a list of names"),
    ('name = "b"\nbundle = ["x"]', "version is missing"),
    ('name = "b"\nversion = "1.0"\nbundle = ["x"]\n[files]\napp = ["/x"]',
     "a bundle has no files"),
    ("name = ", "it isn't TOML"),
])
def test_each_check(text, words):
    assert words in one(text)


def test_a_circle_of_three_is_named():
    found = one(base('[extras]\na = { package = "pa", needs = ["c"] }\n'
                     'b = { package = "pb", needs = ["a"] }\nc = { package = "pc", needs = ["b"] }'))
    assert "a → c → b → a" in found


def test_a_too_big_manifest():
    assert "bigger than 64 KB" in one(base("summary = '" + "x" * 70_000 + "'"))


# ---------------------------------------------------------------- patterns and paths

@pytest.mark.parametrize("pattern, path, matches", [
    ("/usr/local/bin/kittystory", "/usr/local/bin/kittystory", True),
    ("/usr/local/bin/kitty*", "/usr/local/bin/kittystory", True),
    ("/usr/local/bin/*", "/usr/local/bin/sub/x", False),           # * stays in one name
    ("/a/**", "/a/b", True),
    ("/a/**", "/a/b/c/d", True),
    ("/a/**", "/a", False),                                       # the contents, not the folder
    ("/a/**/z", "/a/z", True),                                    # none or more folders
    ("/a/**/z", "/a/b/c/z", True),
    ("/a/**/z", "/a/b/c/zz", False),
    ("~/.kittystory/chars/*/char.md", "~/.kittystory/chars/Emma/char.md", True),
    ("~/.kittystory/chars/*/char.md", "~/.kittystory/chars/Emma/memory.md", False),
    ("~/.kittystory/packs/*.pack", "~/.kittystory/packs/tsundere.pack", True),
    ("~/.kittystory/**", "/home/user/.kittystory/x", False),      # ~ only matches ~
    ("/home/*/.bashrc", "~/.bashrc", False),
    ("/a.b/c", "/aXb/c", False),                                  # a dot is a dot
])
def test_match(pattern, path, matches):
    assert match(pattern, path) is matches


def test_expand_over_a_list_of_paths():
    paths = ["~/.kittystory/chars/Lucy/char.md", "~/.kittystory/chars/Emma/char.md",
             "~/.kittystory/chars/Emma/memory.md", "~/.kittystory/shared.md"]
    assert expand("~/.kittystory/chars/*/char.md", paths) == [
        "~/.kittystory/chars/Emma/char.md", "~/.kittystory/chars/Lucy/char.md"]
    assert expand("~/.kittystory/**", paths) == sorted(paths)
    assert expand("/nothing/**", paths) == []


@pytest.mark.parametrize("pattern, words", [
    ("usr/bin/x", "must start with / or ~/"),
    ("/", "names no file"),
    ("~/", "names no file"),
    ("/usr//bin", "empty name"),
    ("/usr/bin/", "empty name"),
    ("/usr/../etc/passwd", ". or .."),
    ("~/./x", ". or .."),
    ("/.hallux/memory.md", "under /.hallux"),
    ("/proc/cpuinfo", "under /proc"),
    ("/sys/x", "under /sys"),
    ("/dev/null", "under /dev"),
    ("/usr/bin/x?", "only * and ** are wildcards"),
    ("/usr/[ab]", "only * and ** are wildcards"),
    ("/usr/x**", "** must be a whole name"),
    ("/usr/bin/a\tb", "control character"),
])
def test_refused_patterns(pattern, words):
    with pytest.raises(ValueError, match=words.replace("*", r"\*").replace(".", r"\.")):
        check_pattern(pattern)


def test_paths_have_no_wildcards():
    assert check_path("~/.kittystory/x") == "~/.kittystory/x"
    with pytest.raises(ValueError, match="can't have"):
        check_path("/usr/bin/*")


def test_a_hallux_folder_under_a_home_is_only_a_folder():
    assert check_pattern("~/.hallux/notes.md")                    # not the machine's /.hallux


def test_place_puts_the_home_in():
    assert place("~/.kittystory/x", "/home/danika-hous") == "/home/danika-hous/.kittystory/x"
    assert place("~/.kittystory/x", "/root/") == "/root/.kittystory/x"
    assert place("/usr/local/bin/x", "/home/user") == "/usr/local/bin/x"
    with pytest.raises(ValueError):
        place("~/x", "home/user")


# ---------------------------------------------------------------- versions

def test_versions_compare_number_by_number():
    assert Version("1.4") < Version("1.10") < Version("2.0") < Version("10")
    assert Version("1.4.1") > Version("1.4")
    assert sorted(map(Version, ["2.0", "1.10", "1.4", "1.9.9"])) == list(
        map(Version, ["1.4", "1.9.9", "1.10", "2.0"]))


def test_one_version_is_written_in_one_way_and_14_is_140():
    assert Version("1.4") == Version("1.4.0") and hash(Version("1.4")) == hash(Version("1.4.0"))
    assert str(Version("1.4.0")) == "1.4.0"                      # as it was written
    assert len({Version("1.4"), Version("1.4.0")}) == 1          # a store can't hold both


@pytest.mark.parametrize("text", ["", "1.", ".1", "1.04", "01", "1.4-beta", "v1.4", "1..4",
                                  "1.2.3.4.5", "1234567", 1.4, None])
def test_refused_versions(text):
    with pytest.raises(ValueError):
        Version(text)
