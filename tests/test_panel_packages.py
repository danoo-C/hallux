"""The Packages tab of hallux's own panel (hallux/panel_tabs/packages.py), and what runs it
(hallux/hpm/running.py). The tab is shown in a real panel on a pipe, around a real Installs
on a temporary world, with a store of its own."""
import asyncio
import threading

import pytest

pytest.importorskip("prompt_toolkit")
from test_panel import ESC, StandIn, drawn, session  # noqa: E402

from hallux.disk import Disk  # noqa: E402
from hallux.hpm import record as rec  # noqa: E402
from hallux.hpm.archive import pack  # noqa: E402
from hallux.hpm.engine import Want  # noqa: E402
from hallux.hpm.running import ASKING, DONE, FAILED, LISTING, Installs  # noqa: E402
from hallux.hpm.store import Store  # noqa: E402
from hallux.panel import Panel, key_of  # noqa: E402
from hallux.panel_tabs.files import FilesTab  # noqa: E402
from hallux.panel_tabs.packages import PackagesTab  # noqa: E402

ENTER, DOWN, RIGHT = "\r", "\x1b[B", "\x1b[C"

APP = '''name = "kittystory"
version = "{version}"
summary = "Chat with characters built from personality packs"
memory_line = "kittystory: split-screen chat"
requires.addons = ["web"]
[files]
app = ["/usr/local/bin/kittystory"]
[extras]
packs      = {{ package = "kittystory-packs", default = true }}
characters = {{ package = "kittystory-chars", default = true, needs = ["packs"] }}
'''
PACKS = 'name = "kittystory-packs"\nversion = "{version}"\nsummary = "3 packs"\nfor = "kittystory"\n' \
        '[files]\ndata = ["~/.kittystory/packs/*.pack"]\n'
CHARS = 'name = "kittystory-chars"\nversion = "{version}"\nsummary = "Emma, Lucy, Emilly"\n' \
        'for = "kittystory"\n[files]\ndata = ["~/.kittystory/chars/*/char.md"]\n'
CALC = 'name = "kittycalc"\nversion = "{version}"\nsummary = "GUI calculator"\n' \
       'memory_line = "kittycalc: a GUI calculator"\n[files]\napp = ["/usr/local/bin/kittycalc"]\n'


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
    put(store, tmp_path, APP, {"/usr/local/bin/kittystory": "# kittystory\nthe card\n"}, "1.4")
    put(store, tmp_path, PACKS, {"~/.kittystory/packs/tsundere.pack": "tsundere\n"})
    put(store, tmp_path, CHARS, {"~/.kittystory/chars/Emma/char.md": "Emma\n"}, "1.1")
    put(store, tmp_path, CALC, {"/usr/local/bin/kittycalc": "calc\n"})
    return store


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "world"
    (root / ".hallux").mkdir(parents=True)
    (root / ".hallux/memory.md").write_text("# memory\n## Invented programs\n")
    (root / "home/user").mkdir(parents=True)
    (root / "home/user/.profile").write_text("x\n")
    return root


def tab_of(installs):
    return PackagesTab(installs.watch, installs.catalog, installs.installed,
                       installs.plan_install, installs.plan_remove, installs.go,
                       installs.stop, installs.back, installs.migration_go,
                       installs.migration_cancel)


def panel_of(installs, *more):
    """The tab in a panel. What the threads change draws the panel again, as the terminal's
    refresh does in Hallux."""
    tab = tab_of(installs)
    panel = Panel([StandIn("Agents"), *more, tab, StandIn("Config")])
    installs.changed = panel.invalidate
    return panel, tab


async def until(installs, *states, seconds=5):
    for _ in range(int(seconds / 0.02)):
        if installs.watch().state in states:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"still {installs.watch().state}, not {states}")


def rows(panel):
    return [row for row in drawn(panel) if row.strip()]


def on(tab, name):
    """The cursor on a package's row."""
    tab.model.cursor = [i for i, (c, k) in enumerate(tab.model.entries())
                        if c.name == name and k is None][0]


# ---------------------------------------------------------------- its key, and the panel's

def test_the_tab_is_chosen_with_g_and_underlined_there(world, store):
    panel, tab = panel_of(Installs(Disk(world), store))
    assert key_of(tab) == "g"

    async def script(press):
        await press("g")
        assert panel.tab is tab
        row = panel._tab_row()
        at = [text for style, text, *_ in row if "underline" in style]
        assert "g" in at and "P" not in at
        assert "a g c tabs" in "".join(t for _, t in panel._foot())
    session(panel, script)


def test_p_still_opens_the_files_tabs_path_row(world, store):
    files = FilesTab(*(lambda *a: None for _ in range(6)))
    files.watch = lambda: __import__("hallux.importing", fromlist=["Seen"]).Seen("empty", "/")
    panel, tab = panel_of(Installs(Disk(world), store), files)

    async def script(press):
        await press("f")
        await press("p")
        assert files.row is not None                  # p is the path row's, not a tab's
    session(panel, script)


def test_two_tabs_with_one_key_are_refused():
    class Twin(StandIn):
        key = "g"
    with pytest.raises(ValueError, match="the same key, g: Packages and Garden"):
        Panel([tab_of(Installs(Disk("/nonexistent"))), Twin("Garden")])


# ---------------------------------------------------------------- the list

def test_the_list_at_80_and_120_columns(world, store):
    for columns in (80, 120):
        panel, tab = panel_of(Installs(Disk(world), store))

        async def script(press):
            await press("g")
            return rows(panel)
        shown = session(panel, script, columns=columns)
        assert shown[1].startswith(" local · 2 packages")
        assert "installed here: 0" in shown[1]
        assert shown[2].startswith("▸ [ ]   kittycalc")         # sorted by name
        assert shown[3].startswith("  [ ] ▸ kittystory")
        assert all(len(row) <= columns for row in shown)
        assert any("needs the web addon" in row for row in shown) is False   # web.py exists


def test_ticking_folding_and_needs(world, store):
    installs = Installs(Disk(world), store)
    panel, tab = panel_of(installs)

    async def script(press):
        await press("g")
        on(tab, "kittystory")
        await press(" ")                               # kittystory
        await press(RIGHT)                             # its extras
        shown = rows(panel)
        assert any("[x] packs" in row for row in shown) and any("[x] characters" in row for row in shown)
        await press(DOWN)
        await press(" ")                               # packs off: characters off too
        return tab.model.result()
    assert session(panel, script) == [Want("kittystory", extras=())]


def test_all_none_and_the_views(world, store):
    installs = Installs(Disk(world), store)
    panel, tab = panel_of(installs)

    async def script(press):
        await press("g")
        await press("+")
        assert [w.name for w in tab.model.result()] == ["kittycalc", "kittystory"]
        await press("-")
        assert tab.model.result() == []
        await press("i")                               # installed here: none
        assert any("Nothing here in this view" in row for row in rows(panel))
        await press("i")
        await press("u")
        assert tab.view == "updates"
        await press("u")
        assert tab.view == "the store"
    session(panel, script)


def test_the_filter_row(world, store):
    panel, tab = panel_of(Installs(Disk(world), store))

    async def script(press):
        await press("g")
        await press("/")
        assert tab.typing
        await press("calc")                            # its letters: a and c choose no tab
        assert panel.tab is tab
        await press(ENTER)
        shown = rows(panel)
        assert any("kittycalc" in row for row in shown)
        assert not any("kittystory" in row for row in shown)
        assert "“calc”" in shown[1]
    session(panel, script)


def test_v_shows_the_card_and_esc_goes_back(world, store):
    panel, tab = panel_of(Installs(Disk(world), store))

    async def script(press):
        await press("g")
        on(tab, "kittystory")
        await press("v")
        assert any("the card" in row for row in rows(panel))
        await press(ESC)
        assert panel.is_open and tab.model.viewing is None
    session(panel, script)


# ---------------------------------------------------------------- installing

def test_install_with_a_conflict_and_the_note(world, store):
    (world / "home/user/.kittystory/packs").mkdir(parents=True)
    (world / "home/user/.kittystory/packs/tsundere.pack").write_text("my own\n")
    installs = Installs(Disk(world), store)
    panel, tab = panel_of(installs)

    async def script(press):
        await press("g")
        on(tab, "kittystory")
        await press(" ")
        await press(ENTER)
        await until(installs, ASKING)
        await press("")
        shown = rows(panel)
        assert any(row.startswith(" kittystory 1.4: 2 new") for row in shown)
        assert any("1 file is in the way" in row for row in shown)
        assert any("tsundere.pack" in row and "different, not hpm's" in row for row in shown)
        assert tab.typing                              # o s k f r are answers here
        await press("k")                               # keep both
        await press("f")                               # f is not the Files tab here
        assert panel.tab is tab
        await press(ENTER)
        await until(installs, DONE)
        await press("")
        shown = rows(panel)
        assert any("3 installed" in row for row in shown)
        assert any("The machine is told with your next line" in row for row in shown)
        await press(ENTER)
        assert installs.watch().state == LISTING
        return installs.waiting()
    notes = session(panel, script)
    assert [n["name"] for n in notes] == ["kittystory", "kittystory-packs", "kittystory-chars"]
    assert (world / "home/user/.kittystory/packs/tsundere.pack").read_text() == "my own\n"
    assert (world / "home/user/.kittystory/packs/tsundere.hpm-new.pack").exists()
    assert rec.memory_lines(Disk(world), "kittystory") == [
        "- kittystory: split-screen chat [hpm kittystory 1.4]"]


def test_esc_at_the_questions_writes_nothing(world, store):
    installs = Installs(Disk(world), store)
    panel, tab = panel_of(installs)

    async def script(press):
        await press("g")
        on(tab, "kittystory")
        await press(" ")
        await press(ENTER)
        await until(installs, ASKING)
        await press(ESC)
        assert panel.is_open and installs.watch().state == LISTING
    session(panel, script)
    assert rec.load(Disk(world)) == {} and not (world / "usr").exists()


def test_the_old_memory_line_is_asked_on_the_tab(world, store):
    (world / ".hallux/memory.md").write_text("## Invented programs\n- kittycalc: the machine's own\n")
    installs = Installs(Disk(world), store)
    panel, tab = panel_of(installs)

    async def script(press):
        await press("g")
        on(tab, "kittycalc")
        await press(" ")
        await press(ENTER)
        await until(installs, ASKING)
        await press("")
        assert any("its own line about kittycalc" in row for row in rows(panel))
        await press("n")                               # keep it
        await press(ENTER)
        await until(installs, DONE)
    session(panel, script)
    assert "- kittycalc: the machine's own" in Disk(world).memory_read()["text"]


def test_remove_from_the_tab(world, store):
    installs = Installs(Disk(world), store)
    panel, tab = panel_of(installs)

    async def script(press):
        await press("g")
        on(tab, "kittycalc")
        await press("r")
        assert any("isn't installed here" in t for _, t in panel._foot())
        await press(" ")
        await press(ENTER)
        await until(installs, ASKING)
        await press(ENTER)
        await until(installs, DONE)
        await press(ENTER)
        assert any("installed ✓" in row for row in rows(panel))
        on(tab, "kittycalc")
        await press("r")
        await until(installs, ASKING)
        await press("")
        assert any("remove kittycalc 1.0: 2 files" in row for row in rows(panel))   # and its manifest
        await press(ENTER)
        await until(installs, DONE)
        return installs.waiting()
    notes = session(panel, script)
    assert notes[-1]["removed"] is True and not (world / "usr/local/bin/kittycalc").exists()


def test_a_store_that_cant_be_read(world, tmp_path):
    store = Store(tmp_path / "broken")
    (store.local / "kittystory").mkdir(parents=True)
    (store.local / "kittystory" / "notes.txt").write_text("x")
    panel, tab = panel_of(Installs(Disk(world), store))

    async def script(press):
        await press("g")
        return rows(panel)
    assert any("The store can't be read" in row for row in session(panel, script))


def test_an_empty_store(world, tmp_path):
    panel, tab = panel_of(Installs(Disk(world), Store(tmp_path / "empty")))

    async def script(press):
        await press("g")
        return rows(panel)
    assert any("The store has no packages yet" in row for row in session(panel, script))


# ---------------------------------------------------------------- Installs, without a tab

def run(coroutine):
    return asyncio.run(asyncio.wait_for(coroutine, 10))


def test_a_plan_that_fails_says_why(world, store):
    os_world = world
    (os_world / "home/other").mkdir()
    (os_world / "home/other/.profile").write_text("x\n")
    installs = Installs(Disk(world), store)

    async def go():
        installs.plan_install([Want("kittystory")])
        await until(installs, FAILED)
        return installs.watch().error
    assert "say which with --user" in run(go())


def test_esc_stops_between_packages(world, store, monkeypatch):
    installs = Installs(Disk(world), store)
    from hallux.hpm import engine
    real, gate = engine._install_item, threading.Event()

    def slow(plan, item, answers, record):
        done = real(plan, item, answers, record)
        installs.stop()                                # Esc, after the first package
        return done

    monkeypatch.setattr(engine, "_install_item", slow)

    async def go():
        installs.plan_install([Want("kittystory")])
        await until(installs, ASKING)
        installs.go({})
        await until(installs, DONE)
        return installs.watch().outcome
    outcome = run(go())
    assert [(d.name, d.status) for d in outcome.done] == [
        ("kittystory", "installed"), ("kittystory-packs", "skipped"), ("kittystory-chars", "skipped")]
    assert outcome.done[1].why == "stopped"


def test_notes_are_told_once_and_forgotten_at_a_boot(world, store):
    installs = Installs(Disk(world), store)

    async def go():
        installs.plan_install([Want("kittycalc")])
        await until(installs, ASKING)
        installs.go({})
        await until(installs, DONE)
    run(go())
    first = installs.waiting()
    assert [n["name"] for n in first] == ["kittycalc"]
    installs.told(first)
    assert installs.waiting() == ()
    installs._notes = first
    installs.forget()
    assert installs.waiting() == ()


def test_the_memory_takes_one_edit_at_a_time(world):
    disk = Disk(world)
    threads = [threading.Thread(target=lambda n=n: [disk.memory_edit("", f"- line {n}.{i}\n")
                                                    for i in range(50)]) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    text = disk.memory_read()["text"]
    assert all(f"- line {n}.{i}\n" in text for n in range(4) for i in range(50))
