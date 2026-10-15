"""The Files tab of hallux's own panel. What it draws is tested from made-up states, without a
pipe. What it does is tested in a real panel on a pipe, around a real Imports on a temporary
machine, with the files dragged from a folder beside it."""
import asyncio
import threading
import time

import pytest

pytest.importorskip("prompt_toolkit")

from test_importing import MUSIC, desk, disk, put, root  # noqa: E402,F401  (fixtures)
from test_panel import ESC, StandIn, click, drawn, paste, session  # noqa: E402
from test_panel_config import ENTER, Machine as Settings, to  # noqa: E402

import hallux.importing  # noqa: E402
from hallux.importing import (  # noqa: E402
    COPYING, DONE, EMPTY, EXISTS, FILE, FOLDER, FULL, HERE, IN_THE_WAY, LINK, LOOKING, MORE,
    NOT_COPIED, OTHER, READY, STOPPED, Counts, Imports, Line, Result, Seen,
)
from hallux.panel import Panel  # noqa: E402
from hallux.panel_tabs import files  # noqa: E402
from hallux.panel_tabs.files import FilesTab, draw  # noqa: E402
from hallux.statusbar import GRAY, RED, YELLOW_NOTE  # noqa: E402

UP, DOWN, PAGE_DOWN, BACKSPACE, F5 = "\x1b[A", "\x1b[B", "\x1b[6~", "\x7f", "\x1b[15~"
HEAD, BODY = 2, 5                                     # the rows of the screen they start on


# ---------------------------------------------------------------- what the tab draws

def text(drawn_):
    """The head's two lines and the body's, as text."""
    return (["".join(part for _, part in line) for line in drawn_.head],
            ["".join(part for _, part in line).rstrip() for line in drawn_.body])


def styles(line):
    """The styles of a line's parts, by their text."""
    return {part.strip(): style for style, part in line if part.strip()}


TREE = (Line(0, "Pictures", FOLDER, 2_200_000, 13), Line(1, "holiday", FOLDER, 1_200_000, 8),
        Line(2, "beach.jpg", FILE, 340_000), Line(2, "dunes.jpg", FILE, 212_000),
        Line(2, "… 6 more", MORE), Line(1, "cat.png", FILE, 88_000, mark=EXISTS),
        Line(0, "notes.txt", FILE, 1_200))
COUNTS = Counts(2, 14, 2_300_000, {EXISTS: 1})


def test_nothing_dropped_yet():
    assert text(draw(Seen(EMPTY, "/home/danika-hous/Music"))) == (
        [" Drop files or folders onto this window.",
         " They are copied into /home/danika-hous/Music"], [])


def test_after_a_drop_the_tree_as_the_plan_has_it():
    head, body = text(draw(Seen(READY, "/home/danika-hous/Music", ("Pictures", "notes.txt"),
                                TREE, COUNTS)))
    assert head == [" into /home/danika-hous/Music",
                    " 2 folders · 14 files · 2.3 MB · 1 exists already"]
    assert body == [
        " Pictures/                                          13 files    2.2 MB",
        "   holiday/                                          8 files    1.2 MB",
        "     beach.jpg                                                  340 kB",
        "     dunes.jpg                                                  212 kB",
        "     … 6 more",
        "   cat.png                                                       88 kB   exists",
        " notes.txt                                                      1.2 kB"]
    assert max(len(line) for line in body) <= 79      # one column is left free


def test_the_colours_of_a_tree():
    drawn_ = draw(Seen(READY, MUSIC, (), TREE + (Line(0, "x", FILE, 1, mark=HERE),),
                       Counts(2, 15, 2_300_001, {EXISTS: 1, HERE: 1})))
    assert styles(drawn_.head[1]) == {"2 folders · 15 files · 2.3 MB": "",
                                      "· 1 exists already": f"fg:{YELLOW_NOTE}",
                                      "· 1 can't be copied": f"fg:{GRAY}"}
    assert styles(drawn_.body[5])["exists"] == f"fg:{YELLOW_NOTE}"
    assert styles(drawn_.body[7])["is already here"] == f"fg:{GRAY}"     # a mark that skips
    assert drawn_.body[4] == [(f"fg:{GRAY}", "     … 6 more")]


def test_every_kind_of_line_and_every_mark_has_its_columns():
    lines = (Line(0, "a", FOLDER, 0, 0), Line(0, "b", FOLDER, 812, 1, IN_THE_WAY),
             Line(0, "c", LINK, 0, 0, "→ ../cat.png"), Line(0, "d", OTHER, 0, 0, NOT_COPIED),
             Line(0, "… and more", MORE))
    head, body = text(draw(Seen(READY, MUSIC, (), lines, Counts(2, 2, 812)), 60))
    assert head[1] == " 2 folders · 2 files · 812 B"
    assert body == [" a/                        0 files       0 B",
                    " b/                         1 file     812 B   in the way",
                    " c                                             → ../cat.png",
                    " d                                             not copied",
                    " … and more"]
    assert max(len(line) for line in body) <= 59


def test_a_name_is_shown_clean_and_cut_to_the_window():
    lines = (Line(0, "bad\x1b[31mname\n.txt", FILE, 5), Line(1, "x" * 200, FILE, 5))
    _, body = text(draw(Seen(READY, MUSIC, (), lines, Counts(0, 2, 10)), 60))
    assert body[0].startswith(" bad?[31mname?.txt ")
    assert body[1].startswith("   xxxxxxxxxx") and "…" in body[1] and body[1].endswith("5 B")
    assert len(body[1]) == 59


def test_a_long_destination_keeps_its_end():
    head, _ = text(draw(Seen(READY, "/home/user/" + "deep/" * 30 + "Music", (), (), Counts()),
                        60))
    assert head[0].startswith(" into …") and head[0].endswith("/deep/Music")
    assert len(head[0]) == 59


def test_while_it_looks_the_counts_grow_and_the_names_are_shown():
    seen = Seen(LOOKING, MUSIC, ("Pictures", "notes.txt"), counts=Counts(1, 468, 5_300_000))
    assert text(draw(seen)) == ([f" into {MUSIC}", " 1 folder · 468 files · 5.3 MB · counting…"],
                                [" Pictures", " notes.txt"])
    assert text(draw(Seen(LOOKING, MUSIC, ("a",))))[0][1] == " 0 files · 0 B · counting…"


def test_a_refused_tree_says_why_in_red():
    drawn_ = draw(Seen(READY, MUSIC, ("Music",), refused="would be copied into itself: Music"))
    assert text(drawn_) == ([f" into {MUSIC}", " would be copied into itself: Music"], [])
    assert drawn_.head[1][0][0] == f"fg:{RED}"


def test_while_it_copies_the_second_line_counts():
    seen = Seen(COPYING, MUSIC, ("Pictures",), TREE, Counts(40, 1400, 2_100_000_000),
                through=Counts(3, 120, 34_000_000))
    head, body = text(draw(seen))
    assert head == [f" into {MUSIC}", " copying… 120 of 1,400 files · 34 MB of 2.1 GB"]
    assert body[0].startswith(" Pictures/")                   # the tree stays


def test_after_a_copy_of_everything():
    seen = Seen(DONE, MUSIC, ("Pictures",), result=Result(MUSIC, 14, 2, 2_300_000))
    assert text(draw(seen)) == ([f" copied 14 files (2.3 MB) into {MUSIC}", " nothing skipped"],
                                [" everything was copied"])


def test_after_a_copy_what_wasnt_copied_with_its_reason():
    result = Result(MUSIC, 1, 0, 5, {EXISTS: 3, IN_THE_WAY: 1},
                    (("Pictures/cat.png", "Permission denied"),), more=2)
    drawn_ = draw(Seen(DONE, MUSIC, ("Pictures",), result=result))
    assert text(drawn_) == ([f" copied 1 file (5 B) into {MUSIC}", " 4 skipped · 3 failed"],
                            [" 3 skipped: exists", " 1 skipped: in the way",
                             " Pictures/cat.png  Permission denied", " … 2 more failed"])
    assert styles(drawn_.body[2])["Permission denied"] == f"fg:{RED}"


def test_a_copy_that_was_stopped_or_ended_early():
    stopped = draw(Seen(DONE, MUSIC, ("a",), result=Result(MUSIC, 3, 0, 900, ended=STOPPED)))
    assert text(stopped) == ([f" stopped: copied 3 files (900 B) into {MUSIC}",
                              " nothing skipped"], [])
    assert stopped.head[0][0][0] == "bold"
    full = draw(Seen(DONE, MUSIC, ("a",), result=Result(MUSIC, 0, 0, 0, ended=FULL)))
    assert text(full)[0][0] == f" the disk is full: copied 0 files (0 B) into {MUSIC}"
    assert full.head[0][0][0] == f"fg:{RED}"
    broken = draw(Seen(DONE, MUSIC, ("a",), result=Result(
        MUSIC, ended="failed: KeyError: " + "x" * 200)), 60)
    assert text(broken)[0][0].startswith(" failed: KeyError: xxx") and len(text(broken)[0][0]) == 59


# ---------------------------------------------------------------- in a panel, on a pipe

@pytest.fixture
def world(disk):
    """The machine's imports in the user's Music folder, and a panel around them: two stand-in
    tabs, the Files tab and a Config tab."""
    disk.cwd = MUSIC
    imports = Imports(disk)
    settings = Settings()
    tab = FilesTab(imports.watch, imports.drop, imports.reads, imports.start, imports.stop,
                   imports.clear)
    panel = Panel([StandIn("Agents"), StandIn("Details"), tab, settings.tab()])
    imports.changed = panel.invalidate                   # as the machine has the terminal draw
    yield panel, tab, imports
    imports.close()


@pytest.fixture
def slow_copy(monkeypatch):
    """Copies that wait for the test, file by file. A walk doesn't."""
    go = threading.Event()
    real = hallux.importing.copy_whole

    def held(source, place, stop=None, wrote=None):
        while not go.is_set() and not (stop and stop.is_set()):
            time.sleep(0.001)
        return real(source, place, stop, wrote)

    monkeypatch.setattr(hallux.importing, "copy_whole", held)
    return go


async def until(panel, condition, seconds=3):
    """Wait until the panel has drawn what the condition wants, and return the screen."""
    deadline = time.monotonic() + seconds
    while not condition(rows := drawn(panel)):
        assert time.monotonic() < deadline, "\n".join(rows)
        await asyncio.sleep(0.02)
    return rows


def music(root):
    return root / "home" / "user" / "Music"


def test_a_drop_from_the_files_tab_and_from_the_config_tab(world, desk):
    panel, tab, imports = world
    album = put(desk / "album", one_png="1", two_png="22")

    async def script(press):
        await press("f")
        await press(paste(str(album)))
        in_files = await until(panel, lambda rows: "album/" in rows[BODY])
        await press("x")
        await press("c")
        await press(paste(str(album)))
        in_config = await until(panel, lambda rows: "album/" in rows[BODY])
        return in_files, in_config, panel.tab

    in_files, in_config, shown = session(panel, script)
    for rows in (in_files, in_config):
        assert rows[0].endswith("Agents     Details   [ Files ]   Config")
        assert rows[HEAD:HEAD + 2] == [f" into {MUSIC}", " 1 folder · 2 files · 3 B"]
        assert rows[BODY].startswith(" album/") and rows[BODY].endswith("2 files       3 B")
        assert rows[BODY + 1].startswith("   one.png") and rows[BODY + 2].startswith("   two.png")
        assert rows[-1] == " Enter copy · x clear · p path · a d f c tabs · Esc close"
    assert shown is tab


def test_a_drop_that_is_refused_from_another_tab_shows_the_files_tab_with_the_reason(world,
                                                                                     desk):
    panel, tab, imports = world
    album = put(desk / "album", one_png="1")

    async def script(press):
        await press(paste(str(album)))
        await until(panel, lambda rows: "album/" in rows[BODY])
        await press("c" + paste(str(album)))
        return panel.tab, drawn(panel)[-1]

    assert session(panel, script) == (tab, " already in the list: album")


def test_a_long_reason_keeps_its_end_in_the_foot():
    said = "no such file or folder on this computer: …" + "/very/long" * 6 + "/gone.txt"
    assert files.fitted(said, 78) == ("no such file or folder on this computer: …ry/long/very"
                                      "/long/very/long/gone.txt")
    assert len(files.fitted(said, 78)) == 78 and files.fitted("short", 78) == "short"
    assert files.fitted("x" * 100, 20) == "…" + "x" * 19


def test_a_paste_that_is_no_path(world):
    panel, tab, imports = world

    async def script(press):
        await press(paste("hello"))                          # in the Config tab
        in_config = panel.tab.title, drawn(panel)[-1]
        await press("f")
        await press(paste("hello"))
        return in_config, drawn(panel)[-1], imports.watch().state

    (title, config_foot), files_foot, state = session(panel, script)
    assert title == "Config" and config_foot.startswith(" ↑ ↓ move · Enter change")
    assert files_foot == " no such file or folder on this computer: hello"
    assert state == EMPTY


def test_a_paste_into_the_config_tabs_open_row_is_typed_into_it(world, desk):
    panel, tab, imports = world
    config = panel.tabs[-1]

    async def script(press):
        await press(to("model") + ENTER)
        await press(paste(str(desk)))
        return panel.tab, config.state.typed.text, imports.watch().state

    shown, typed, state = session(panel, script)
    assert shown is config and typed == str(desk) and state == EMPTY


def test_enter_copies_when_nothing_is_in_the_way(world, desk, root):
    panel, tab, imports = world
    album = put(desk / "album", one_png="1", two_png="22")

    async def script(press):
        await press("f" + paste(str(album)))
        await until(panel, lambda rows: "album/" in rows[BODY])
        await press(ENTER)
        rows = await until(panel, lambda rows: rows[HEAD].startswith(" copied"))
        return rows, tab.wants_first()

    rows, wants_first = session(panel, script)
    assert not wants_first                                   # its result was on the screen
    assert rows[HEAD:BODY + 1] == [f" copied 2 files (3 B) into {MUSIC}", " nothing skipped", "",
                                   " everything was copied"]
    assert rows[-1] == " x clear · p path · a d f c tabs · Esc close"
    assert (music(root) / "album" / "two.png").read_text() == "22"
    assert (music(root) / "album" / "one.png").read_text() == "1"


@pytest.mark.parametrize("answer, then, copied", [
    ("o", "new", " copied 1 file (3 B) into /home/user/Music"),
    ("s", "old", " copied 0 files (0 B) into /home/user/Music"),
])
def test_a_file_that_exists_is_asked_about(world, desk, root, answer, then, copied):
    panel, tab, imports = world
    (music(root) / "cat.png").write_text("old")
    put(desk, cat_png="new")

    async def script(press):
        await press("f" + paste(str(desk / "cat.png")))
        before = await until(panel, lambda rows: "cat.png" in rows[BODY])
        await press(ENTER)
        asked = drawn(panel)[-1], tab.typing
        await press(answer)
        return before, asked, await until(panel, lambda rows: rows[HEAD].startswith(" copied"))

    before, asked, after = session(panel, script)
    assert before[HEAD + 1] == " 1 file · 3 B · 1 exists already" and before[BODY].endswith("exists")
    assert asked == (" 1 file exists already: o overwrite · s skip · Esc back", True)
    assert after[HEAD] == copied and (music(root) / "cat.png").read_text() == then
    if answer == "s":
        assert after[HEAD + 1:BODY + 1] == [" 1 skipped", "", " 1 skipped: exists"]


def test_esc_drops_the_question_and_nothing_is_copied(world, desk, root):
    panel, tab, imports = world
    (music(root) / "cat.png").write_text("old")
    put(desk, cat_png="new")

    async def script(press):
        await press("f" + paste(str(desk / "cat.png")))
        await until(panel, lambda rows: "cat.png" in rows[BODY])
        await press(ENTER)
        await press(ESC, wait=0.2)
        after_esc = panel.is_open, tab.typing, imports.watch().state
        await press(ENTER)
        await press("x")                                     # any other key drops it too
        return after_esc, panel.is_open, tab.typing, imports.watch().state

    assert session(panel, script) == ((True, False, READY), True, False, READY)
    assert (music(root) / "cat.png").read_text() == "old"


def test_x_clears_and_enter_does_nothing_with_nothing_dropped(world, desk):
    panel, tab, imports = world
    put(desk, notes_txt="hi")

    async def script(press):
        await press("f" + ENTER)
        empty = imports.watch().state, drawn(panel)[-1]
        await press(paste(str(desk / "notes.txt")))
        await until(panel, lambda rows: "notes.txt" in rows[BODY])
        await press("x")
        return empty, imports.watch().state, drawn(panel)[HEAD]

    (state, foot), cleared, head = session(panel, script)
    assert state == EMPTY and foot == " p path · a d f c tabs · Esc close"
    assert cleared == EMPTY and head == " Drop files or folders onto this window."


def test_a_typed_drop_is_taken_without_enter(world, desk):
    """As VS Code's terminal types a drop: the path in single quotes, as keys, without paste
    brackets. Every letter that does something in the panel is in it."""
    panel, tab, imports = world
    folder = put(desk / "adfckyxsop", one_png="1")
    agents, details, _, config = panel.tabs
    config.shown = lambda: setattr(config, "shows", getattr(config, "shows", 0) + 1)

    async def script(press):
        await press("f")
        await press(f"'{folder}'", wait=0.8)                 # and then nothing for a while
        row = tab.row                                        # TAKE_SECONDS are over
        rows = await until(panel, lambda rows: "adfckyxsop/" in rows[BODY])
        return rows, tab.typing, row, panel.tab

    rows, typing, row, shown = session(panel, script)
    assert shown is tab and not typing and row is None      # the row closed by itself
    assert rows[HEAD + 1] == " 1 folder · 1 file · 1 B"
    assert (agents.shows, details.shows, config.shows) == (0, 0, 1)     # no letter chose a tab
    assert imports.watch().names == ("adfckyxsop",) and imports.watch().state == READY


def test_a_pause_of_the_computer_in_the_middle_of_a_typed_drop_changes_nothing(world, desk,
                                                                              monkeypatch):
    """Python may stop for a moment between two keys, to collect its garbage: that is no
    hand. The keys of one read are a drop's however long they take."""
    panel, tab, imports = world
    put(desk, notes_txt="hi")

    class Paused(files.Buffer):
        def insert_text(self, data, *args, **more):
            if len(self.text) == 5:
                time.sleep(0.2)
            return super().insert_text(data, *args, **more)

    monkeypatch.setattr(files, "Buffer", Paused)

    async def script(press):
        await press("f")
        await press(f"'{desk / 'notes.txt'}'", wait=0.5)
        return await until(panel, lambda rows: "notes.txt" in rows[BODY])

    assert session(panel, script)[HEAD + 1] == " 1 file · 2 B" and tab.row is None


def test_two_typed_drops_one_after_the_other(world, desk):
    panel, tab, imports = world
    put(desk, a_txt="1", b_txt="2")

    async def script(press):
        await press("f")
        await press(f"'{desk / 'a.txt'}'", wait=0.5)
        await press(f"'{desk / 'b.txt'}'", wait=0.5)
        return await until(panel, lambda rows: "b.txt" in rows[BODY + 1])

    rows = session(panel, script)
    assert rows[BODY].startswith(" a.txt") and rows[HEAD + 1] == " 2 files · 2 B"


def test_a_path_typed_by_hand_waits_for_enter(world, desk):
    """A key that comes by itself is a hand's. The row keeps what was typed until Enter, also
    when it names something that exists."""
    panel, tab, imports = world
    put(desk, notes_txt="hi")

    async def script(press):
        await press("f")
        await press("/")                                     # by itself: it opens the row
        await press(str(desk)[1:], wait=0.5)
        waiting = tab.row.text, imports.watch().state, drawn(panel)
        await press(f"/notes.txt{ENTER}")
        return waiting, tab.row, await until(panel, lambda rows: "notes.txt" in rows[BODY])

    (typed, state, rows), row, after = session(panel, script)
    assert typed == str(desk) and state == EMPTY
    assert rows[4].startswith(" path: ") and rows[4].endswith(str(desk)[-20:])
    assert rows[-1] == (
        " type or drop a path · Enter take · Esc leave the row")
    assert row is None and after[HEAD + 1] == " 1 file · 2 B"


def test_a_typed_path_that_doesnt_exist_stays_in_the_row(world, desk):
    panel, tab, imports = world

    async def script(press):
        await press("f")
        await press(f"'{desk / 'gone.txt'}'", wait=0.5)
        waited = tab.row.text if tab.row else None
        await press(ENTER)
        said = drawn(panel)[-1], tab.row is not None
        await press(ESC, wait=0.2)
        return waited, said, tab.row, panel.is_open, drawn(panel)[4]

    waited, (foot, still_open), row, panel_open, row_four = session(panel, script)
    assert waited == f"'{desk / 'gone.txt'}'"
    assert foot.startswith(" no such file or folder on this computer: …") and still_open
    assert foot.endswith("/gone.txt'") and len(foot) == 79
    assert row is None and panel_open and row_four == ""


def test_the_row_edits_and_p_opens_it_empty(world):
    panel, tab, imports = world

    async def script(press):
        await press("fp")
        opened = tab.row.text, drawn(panel)[4]
        await press("abc" + BACKSPACE + "\x1b[D" + "X", wait=0.1)
        return opened, tab.row.text, drawn(panel)[4]

    (empty, row), edited, shown = session(panel, script)
    assert empty == "" and row == " path:"
    assert edited == "aXb" and shown == " path: aXb"


def test_while_a_copy_runs_p_and_a_slash_open_nothing_and_s_stops(world, desk, slow_copy):
    panel, tab, imports = world
    put(desk / "album", one_png="1", two_png="22")

    async def script(press):
        await press("f" + paste(str(desk / "album")))
        await until(panel, lambda rows: "album/" in rows[BODY])
        await press(ENTER)
        copying = await until(panel, lambda rows: rows[HEAD + 1].startswith(" copying…"))
        await press("p/'x")
        typing, row = tab.typing, tab.row
        await press("s")
        return copying, typing, row, await until(panel, lambda rows: "stopped" in rows[HEAD])

    copying, typing, row, stopped = session(panel, script)
    assert copying[HEAD + 1] == " copying… 0 of 2 files · 0 B of 3 B"
    assert copying[-1] == " s stop · a d f c tabs · Esc close"
    assert not typing and row is None
    assert stopped[HEAD].startswith(" stopped: copied 0 files")


def test_a_long_tree_scrolls_and_the_head_and_the_foot_stay(world, desk):
    panel, tab, imports = world
    for folder in ("a", "b"):                              # 2 folders and 98 files: 100 lines
        put(desk / folder, **{f"f{n:02}_txt": "x" for n in range(49)})

    async def script(press):
        await press("f" + paste(f"{desk / 'a'} {desk / 'b'}"))
        first = await until(panel, lambda rows: rows[BODY].startswith(" a/"))
        await press(DOWN)
        down = drawn(panel)
        await press(PAGE_DOWN)
        paged = drawn(panel)
        await press(UP)
        up = drawn(panel)
        await press("cf")                                      # another tab, and back
        return first, down, paged, up, drawn(panel)

    first, down, paged, up, again = session(panel, script)
    for rows in (first, down, paged, up, again):
        assert len(rows) == 24 and rows[HEAD] == f" into {MUSIC}"
        assert rows[HEAD + 1] == " 2 folders · 98 files · 98 B"
        assert rows[-1].startswith(" ↑ ↓ scroll · Enter copy")
    assert first[BODY + 1].startswith("   f00.txt") and down[BODY].startswith("   f00.txt")
    assert paged[BODY].startswith("   f17.txt")                # 18 rows of body: 17 further
    assert up[BODY].startswith("   f16.txt") and again[BODY].startswith(" a/")


def test_the_wheel_scrolls_the_tree(world, desk):
    panel, tab, imports = world
    put(desk / "a", **{f"f{n:02}_txt": "x" for n in range(40)})

    async def script(press):
        await press("f" + paste(str(desk / "a")))
        await until(panel, lambda rows: rows[BODY].startswith(" a/"))
        await press(f"\x1b[<65;10;{BODY + 3}M")             # the wheel, down
        return drawn(panel)[BODY]

    assert session(panel, script).startswith(f"   f{files.WHEEL - 1:02}.txt")


def test_the_panel_opens_on_files_while_a_copy_runs_and_until_its_result_is_seen(disk, desk,
                                                                                 slow_copy):
    put(desk, notes_txt="hi")
    disk.cwd = MUSIC
    imports = Imports(disk)
    tab = FilesTab(imports.watch, imports.drop, imports.reads, imports.start, imports.stop,
                   imports.clear)
    panel = Panel([StandIn("Agents"), StandIn("Details"), tab, StandIn("Config")])

    async def scenario():
        assert imports.drop(str(desk / "notes.txt")) is None
        while imports.watch().state != READY:
            await asyncio.sleep(0.01)
        before = tab.wants_first()
        imports.start(None)
        running = tab.wants_first()
        slow_copy.set()
        while imports.watch().state != DONE:
            await asyncio.sleep(0.01)
        ended = tab.wants_first()
        panel.open()
        opened_on = panel.tab
        panel.close()
        panel.open()
        return before, running, ended, opened_on, panel.tab, tab.wants_first()

    try:
        before, running, ended, opened_on, again, after = asyncio.run(scenario())
    finally:
        imports.close()
    assert (before, running, ended) == (False, True, True)
    assert opened_on is tab and again is panel.tabs[-1] and not after   # shown once: seen


def test_the_tab_row_has_four_tabs_and_fits_sixty_columns(world):
    panel, tab, imports = world

    async def script(press):
        await press("f")
        return drawn(panel)

    rows = session(panel, script, rows=16, columns=60)
    assert rows[0] == " Hallux           Agents     Details   [ Files ]   Config"
    assert rows[HEAD:HEAD + 2] == [" Drop files or folders onto this window.",
                                   " They are copied into /home/user/Music"]
    assert rows[-1] == " p path · a d f c tabs · Esc close"



def test_a_file_that_appears_after_the_tree_is_skipped(world, desk, root):
    """Nobody was asked about it: it wasn't there when the tree was made."""
    panel, tab, imports = world
    put(desk, cat_png="new")

    async def script(press):
        await press("f" + paste(str(desk / "cat.png")))
        await until(panel, lambda rows: "cat.png" in rows[BODY])
        (music(root) / "cat.png").write_text("old")
        await press(ENTER)
        return await until(panel, lambda rows: rows[HEAD].startswith(" copied"))

    rows = session(panel, script)
    assert rows[HEAD + 1:BODY + 1] == [" 1 skipped", "", " 1 skipped: appeared meanwhile"]
    assert (music(root) / "cat.png").read_text() == "old"


def test_a_new_drop_is_seen_from_the_top(world, desk):
    panel, tab, imports = world
    put(desk / "a", **{f"f{n:02}_txt": "x" for n in range(40)})
    put(desk, notes_txt="hi")

    async def script(press):
        await press("f" + paste(str(desk / "a")))
        await until(panel, lambda rows: rows[BODY].startswith(" a/"))
        await press(PAGE_DOWN)
        scrolled = drawn(panel)[BODY]
        await press(paste(str(desk / "notes.txt")))
        return scrolled, await until(panel, lambda rows: " 41 files" in rows[HEAD + 1])

    scrolled, rows = session(panel, script)
    assert scrolled.startswith("   f16.txt") and rows[BODY].startswith(" a/")


def test_in_the_row_a_paste_is_typed_and_a_key_that_is_no_character_isnt(world, desk):
    panel, tab, imports = world

    async def script(press):
        await press("fp")
        await press(F5 + paste("one\ntwo") + F5)
        return tab.row.text, panel.tab, imports.watch().state

    assert session(panel, script) == ("one two", tab, EMPTY)


def test_a_typed_drop_that_is_edited_waits_for_enter(world, desk):
    panel, tab, imports = world
    put(desk, notes_txt="hi")

    async def script(press):
        await press("f")
        await press(f"'{desk / 'notes.txt'}'x" + BACKSPACE, wait=0.5)
        return tab.row.text, imports.watch().state

    assert session(panel, script) == (f"'{desk / 'notes.txt'}'", EMPTY)


def test_a_typed_drop_into_the_row_that_p_opened(world, desk):
    panel, tab, imports = world
    put(desk, notes_txt="hi")

    async def script(press):
        await press("fp")
        await press(f"'{desk / 'notes.txt'}'", wait=0.8)
        return tab.row, await until(panel, lambda rows: "notes.txt" in rows[BODY])

    row, rows = session(panel, script)
    assert row is None and rows[HEAD + 1] == " 1 file · 2 B"


def test_a_drop_that_a_hand_finishes_waits_for_enter(world, desk):
    panel, tab, imports = world
    put(desk, notes_txt="hi")

    async def script(press):
        await press("f")
        await press(f"'{desk / 'notes.tx'}")
        await press("t")
        await press("'", wait=0.8)
        waiting = tab.row.text, imports.watch().state
        await press(ENTER)
        return waiting, await until(panel, lambda rows: "notes.txt" in rows[BODY])

    (typed, state), rows = session(panel, script)
    assert typed == f"'{desk / 'notes.txt'}'" and state == EMPTY


def test_a_tab_shown_again_has_its_row_closed(world):
    panel, tab, imports = world

    async def script(press):
        await press("fp")
        await press("abc")                                   # the letters are the row's
        await press(click(0, drawn(panel)[0].index("Config")))
        await press(click(0, drawn(panel)[0].index("Files")))
        return tab.row, panel.tab, drawn(panel)[4]

    assert session(panel, script) == (None, tab, "")


def test_enter_while_a_copy_runs_asks_nothing(world, desk, root, slow_copy):
    panel, tab, imports = world
    (music(root) / "cat.png").write_text("old")
    put(desk / "album", one_png="1")
    put(desk, cat_png="new")

    async def script(press):
        await press("f" + paste(f"{desk / 'cat.png'} {desk / 'album'}"))
        await until(panel, lambda rows: "album/" in "".join(rows))
        await press(ENTER + "o")
        await until(panel, lambda rows: rows[HEAD + 1].startswith(" copying…"))
        await press(ENTER)
        asking = tab.asking, drawn(panel)[-1]
        slow_copy.set()
        return asking, await until(panel, lambda rows: rows[HEAD].startswith(" copied"))

    (asking, foot), rows = session(panel, script)
    assert not asking and foot == " s stop · a d f c tabs · Esc close"
    assert rows[HEAD] == f" copied 2 files (4 B) into {MUSIC}"
