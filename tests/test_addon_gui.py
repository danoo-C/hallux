"""The GUI addon, addons/gui.py. No test needs a display: pygame's "dummy" driver runs every
window in memory."""
import importlib.util
import json
import signal
import subprocess
import sys
import time

import pytest

from hallux import addons, app, tools

pytestmark = pytest.mark.skipif(importlib.util.find_spec("pygame") is None,
                                reason="pygame isn't installed (pip install -e '.[window]')")

CALC = {"name": "calc", "title": "Calculator", "size": [300, 300], "widgets": [
    {"id": "a", "type": "input", "pos": [10, 10], "size": [120, 32]},
    {"id": "notes", "type": "textarea", "pos": [10, 50], "size": [200, 80]},
    {"id": "go", "type": "button", "pos": [10, 140], "size": [80, 30], "text": "Go"},
    {"id": "tick", "type": "checkbox", "pos": [100, 140], "size": [150, 30], "text": "tick"},
    {"id": "pick", "type": "list", "pos": [10, 180], "size": [120, 60],
     "items": ["one", "two", "three", "four", "five"]},
    {"id": "level", "type": "slider", "pos": [140, 180], "size": [150, 30], "min": 0, "max": 10},
    {"id": "art", "type": "canvas", "pos": [140, 215], "size": [150, 80], "text": "/\\_/\\\n(o.o)"},
    {"id": "result", "type": "label", "pos": [220, 10], "size": [70, 30], "text": "0"}]}


@pytest.fixture
def addon(monkeypatch):
    """The addon as Hallux loads it, with windows that open in memory."""
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    [loaded], skipped = addons.load(app.ADDONS_FOLDER, only=["gui"])
    assert skipped == {}
    yield loaded
    loaded.stop()
    del sys.modules["hallux_addon_gui"]


@pytest.fixture
def gui(addon):
    """The addon's module: its functions and what's behind them."""
    return sys.modules["hallux_addon_gui"]


class Disk:
    """A stand-in for the disk handle: the machine's files, in a dictionary."""

    def __init__(self, **files):
        self.files = {path: json.dumps(f) if isinstance(f, dict) else f
                      for path, f in files.items()}

    def read_text(self, path):
        if path not in self.files:
            raise FileNotFoundError(2, "No such file", path)
        return self.files[path]


def test_the_file_passes_every_check_of_the_loader(addon):
    assert addon.name == "gui"
    assert addon.summary.startswith("Real windows on the desktop")
    assert list(addon.functions) == ["show", "update", "read", "close", "stop"]
    assert addon.stop is addon.functions["stop"] and addon.has_events
    assert "addon_listen" in addon.manual and '"event": "click"' in addon.manual


def test_hallux_itself_never_imports_pygame():
    check = ("import sys; from hallux import addons, app; "
             "loaded, skipped = addons.load(app.ADDONS_FOLDER, only=['gui']); "
             "print(len(loaded), skipped, 'pygame' in sys.modules)")
    done = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True)
    assert (done.stdout, done.stderr) == ("1 {} False\n", "")


def test_the_functions_are_tools(addon):
    built = {t.name: t for t in tools.build_addon_tools(addon)}
    assert built["show"].input_schema["required"] == ["path"]      # disk is never shown
    assert built["update"].input_schema["required"] == ["window", "changes"]
    assert all(t.description for t in built.values())


# ---------------------------------------------------------------- the checks

def test_a_good_layout_passes_and_gets_a_title(gui):
    checked = gui.check_layout({"name": "x", "size": [100, 100]})
    assert checked == {"name": "x", "size": [100, 100], "title": "x", "widgets": []}
    assert gui.check_layout(CALC)["title"] == "Calculator"


def test_every_problem_is_told_at_once(gui):
    bad = {"name": "no spaces", "size": [50, 5000], "colour": "red", "widgets": [
        {"id": "a", "type": "button", "pos": [90, 0], "size": [20, 20], "items": []},
        {"id": "a", "type": "dial", "pos": [0, 0], "size": [1, 1]},
        {"id": "window", "type": "label", "pos": [0, 0], "size": [1, 1], "text": "two\nlines"},
        {"id": "s", "type": "slider", "pos": [0, 0], "size": [1, 1], "min": 5, "max": 1},
        {"id": "l", "type": "list", "pos": [0, 0], "size": [1, 1], "items": ["x"], "value": "y"},
        {"id": "c", "type": "checkbox", "pos": [0, 0], "size": [1, 1], "value": "yes",
         "color": "red; rm -rf /", "font_size": 200, "enabled": 1}]}
    with pytest.raises(gui.GuiError) as told:
        gui.check_layout(bad)
    text = str(told.value)
    for problem in ["unknown key 'colour'", "name must be", "size must be",
                    "widget 'a': a button has no key 'items'", "type must be one of",
                    "the id is used twice", "id must be", "the text of a label is one line",
                    "min and max must be numbers", "value must be one of the items",
                    "widget 'c': value must be true or false", "widget 'c': color: a color",
                    "font_size must be", "enabled must be true or false"]:
        assert problem in text
    assert text.startswith("the layout has 14 problems: ")


def test_a_widget_outside_the_window_is_refused(gui):
    layout = {"name": "x", "size": [100, 100],
              "widgets": [{"id": "b", "type": "button", "pos": [50, 50], "size": [60, 10]}]}
    with pytest.raises(gui.GuiError, match="it reaches 110 x 60, outside the 100 x 100 window"):
        gui.check_layout(layout)


def test_the_list_of_problems_has_an_end(gui):
    widgets = [{"id": f"w{n}", "type": "label", "pos": [0, 0], "size": [1, 1], "text": 1}
               for n in range(100)]
    with pytest.raises(gui.GuiError) as told:
        gui.check_layout({"name": "x", "size": [100, 100], "widgets": widgets})
    assert len(str(told.value)) == gui.PROBLEMS_MAX and str(told.value).endswith("…")


def test_changes_are_checked_like_a_layout(gui):
    layout = gui.check_layout(CALC)
    changed = gui.apply_changes(layout, {"result": {"text": "42"}, "window": {"title": "Sum"}})
    assert changed["title"] == "Sum" and changed["widgets"][-1]["text"] == "42"
    assert layout["widgets"][-1]["text"] == "0"                     # the old one is untouched
    with pytest.raises(gui.GuiError) as told:
        gui.apply_changes(layout, {"nope": {"text": "x"}, "go": {"pos": [0, 0]},
                                   "window": {"size": [9, 9]}, "result": {"items": []}})
    for problem in ["no widget 'nope'", "widget 'go': pos can't change",
                    "only title and background can change"]:
        assert problem in str(told.value)
    with pytest.raises(gui.GuiError, match="a label has no key 'items'"):
        gui.apply_changes(layout, {"result": {"items": []}})
    with pytest.raises(gui.GuiError, match="must be a JSON object"):
        gui.apply_changes(layout, [])


def test_new_items_or_a_new_range_let_go_of_the_old_value(gui):
    layout = gui.apply_changes(gui.check_layout(CALC),
                               {"pick": {"value": "five"}, "level": {"value": 9}})
    changed = gui.apply_changes(layout, {"pick": {"items": ["a"]}, "level": {"max": 5}})
    assert "value" not in changed["widgets"][4] and "value" not in changed["widgets"][5]


def test_a_long_event_is_cut_to_fit(gui):
    event = {"event": "click", "window": "w", "id": "b",
             "values": {"a": "x" * 3000, "b": "y" * 3000, "c": True}}
    cut = gui.fit(event)
    assert cut["cut"] is True and cut["values"]["c"] is True
    assert len(json.dumps(cut)) <= gui.EVENT_MAX and cut["values"]["a"].startswith("xxx")
    small = {"event": "closed", "window": "w"}
    assert gui.fit(small) is small


def test_wrapping(gui):
    assert gui.wrap(len, "aaa bbb ccc", 7) == [(0, 7), (8, 11)]
    assert gui.wrap(len, "abcdefghij", 4) == [(0, 4), (4, 8), (8, 10)]   # a word too long
    assert gui.wrap(len, "a\n\nb", 9) == [(0, 1), (2, 2), (3, 4)]
    assert gui.wrap(len, "", 9) == [(0, 0)]


# ---------------------------------------------------------------- the window, in memory

@pytest.fixture
def screen(gui, monkeypatch):
    """The pygame window itself, without a child process, showing CALC."""
    monkeypatch.setenv("SDL_NO_SIGNAL_HANDLERS", "1")  # leave pytest's signals alone
    made = gui.Gui()
    assert made.answer({"cmd": "layout", "layout": gui.check_layout(CALC)}) == {"ok": True}
    yield made
    made.pg.quit()


def event(screen, kind, **fields):
    pg = screen.pg
    assert screen.handle(pg.event.Event(getattr(pg, kind), **fields)) is True


def click(screen, pos):
    event(screen, "MOUSEBUTTONDOWN", button=1, pos=pos)
    event(screen, "MOUSEBUTTONUP", button=1, pos=pos)


def typed(screen, text):
    event(screen, "TEXTINPUT", text=text)


def key(screen, name):
    event(screen, "KEYDOWN", key=getattr(screen.pg, name))


def kinds(screen):
    return [(r["event"], r.get("id")) for r in screen.reports]


def test_typing_goes_where_the_click_was(screen):
    click(screen, (20, 20))
    typed(screen, "12")
    key(screen, "K_LEFT")
    typed(screen, "x\x1b")                            # nothing unprintable gets in
    assert screen.values()["a"] == "1x2"
    key(screen, "K_BACKSPACE")
    key(screen, "K_DELETE")
    assert screen.values()["a"] == "1"
    click(screen, (5, 290))                           # nowhere: typing goes nowhere
    typed(screen, "lost")
    assert screen.values()["a"] == "1" and screen.reports == []


def test_enter_submits_an_input_once_while_held(screen):
    click(screen, (20, 20))
    typed(screen, "7")
    for _ in range(4):
        key(screen, "K_RETURN")
    assert screen.reports == [{"event": "submit", "window": "calc", "id": "a",
                               "values": {"a": "7", "notes": "", "tick": False, "pick": None,
                                          "level": 0}}]
    event(screen, "KEYUP", key=screen.pg.K_RETURN)
    key(screen, "K_KP_ENTER")
    assert len(screen.reports) == 2


def test_a_textarea_takes_lines_and_the_arrows(screen):
    click(screen, (20, 60))
    typed(screen, "one")
    key(screen, "K_RETURN")
    typed(screen, "two")
    key(screen, "K_UP")
    key(screen, "K_HOME")
    typed(screen, ">")
    assert screen.values()["notes"] == ">one\ntwo" and screen.reports == []
    key(screen, "K_DOWN")
    key(screen, "K_END")
    typed(screen, "!")
    assert screen.values()["notes"] == ">one\ntwo!"
    typed(screen, "z" * 3000)
    assert len(screen.values()["notes"]) == 2000      # a user can't type more than 2000
    screen.draw()


def test_tab_moves_between_what_takes_typing(screen):
    key(screen, "K_TAB")
    assert screen.focus.id == "a"
    key(screen, "K_TAB")
    assert screen.focus.id == "notes"
    key(screen, "K_TAB")
    assert screen.focus.id == "a"


def test_a_button_clicks_when_let_go_on_it(screen):
    event(screen, "MOUSEBUTTONDOWN", button=1, pos=(20, 150))
    assert screen.pressed.id == "go" and screen.reports == []
    event(screen, "MOUSEBUTTONUP", button=1, pos=(20, 150))
    assert kinds(screen) == [("click", "go")]
    event(screen, "MOUSEBUTTONDOWN", button=1, pos=(20, 150))
    event(screen, "MOUSEBUTTONUP", button=1, pos=(200, 150))      # dragged off: no click
    assert len(screen.reports) == 1


def test_checkbox_list_and_slider(screen):
    click(screen, (110, 155))
    assert screen.values()["tick"] is True and screen.reports == []
    click(screen, (20, 182 + screen.row_height(screen.widgets[4]) + 3))     # the second line
    assert screen.reports[-1] == {"event": "pick", "window": "calc", "id": "pick", "value": "two",
                                  "values": {"a": "", "notes": "", "tick": True, "pick": "two",
                                             "level": 0}}
    left, right = screen.track(screen.widgets[5])
    event(screen, "MOUSEBUTTONDOWN", button=1, pos=(left + 5, 195))
    event(screen, "MOUSEMOTION", pos=(right, 195), rel=(0, 0), buttons=(1, 0, 0))
    assert screen.values()["level"] == 10 and kinds(screen)[-1] == ("pick", "pick")  # dragging
    event(screen, "MOUSEBUTTONUP", button=1, pos=((left + right) // 2, 195))
    assert screen.reports[-1]["event"] == "slide" and screen.reports[-1]["value"] == 5


def test_a_disabled_widget_takes_nothing(screen):
    assert screen.answer({"cmd": "update", "changes": {"go": {"enabled": False},
                                                       "a": {"enabled": False}}}) == {"ok": True}
    click(screen, (20, 150))
    click(screen, (20, 20))
    typed(screen, "x")
    assert screen.reports == [] and screen.values()["a"] == ""
    screen.draw()


def test_the_wheel_scrolls_a_list(screen):
    event(screen, "MOUSEMOTION", pos=(20, 200), rel=(0, 0), buttons=(0, 0, 0))
    event(screen, "MOUSEWHEEL", x=0, y=-1)
    assert screen.widgets[4].scroll == 3
    event(screen, "MOUSEWHEEL", x=0, y=-5)                          # no further than the end
    assert screen.widgets[4].scroll == screen.scroll_room(screen.widgets[4]) > 3


def test_updates_change_what_is_shown(screen, gui):
    screen.draw()
    at = lambda pos: tuple(screen.screen.get_at(pos))[:3]          # noqa: E731
    assert at((5, 290)) == (0x2B, 0x2B, 0x2B)
    assert screen.answer({"cmd": "update", "changes": {
        "window": {"background": "tomato", "title": "Sum"}, "a": {"text": "99"},
        "pick": {"items": ["x", "y"], "value": "y"}, "level": {"value": 7.6}}}) == {"ok": True}
    screen.draw()
    assert at((5, 290)) == (0xFF, 0x63, 0x47)
    assert screen.values() | {} == {"a": "99", "notes": "", "tick": False, "pick": "y", "level": 8}
    assert screen.answer({"cmd": "update", "changes": {"a": {"color": "blurple"}}}) == {
        "error": "unknown color: blurple"}


def test_showing_again_keeps_what_the_user_did(screen, gui):
    click(screen, (20, 20))
    typed(screen, "kept")
    click(screen, (110, 155))
    layout = gui.check_layout(CALC | {"size": [320, 320], "background": "navy"})
    layout["widgets"][0] = layout["widgets"][0] | {"text": "from the file"}
    assert screen.answer({"cmd": "layout", "layout": layout}) == {"ok": True}
    assert screen.values()["a"] == "kept" and screen.values()["tick"] is True
    assert screen.screen.get_size() == (320, 320)
    screen.draw()


def test_every_widget_draws(screen):
    click(screen, (20, 60))
    typed(screen, "a long line of text that has to wrap more than once in this box " * 5)
    screen.draw()
    at = lambda pos: tuple(screen.screen.get_at(pos))[:3]          # noqa: E731
    assert at((141, 216)) == (0, 0, 0)                             # the canvas is black
    assert at((12, 12)) == (255, 255, 255)                         # an input is white
    assert at((15, 145)) == (217, 217, 217)                        # a button is #d9d9d9


def test_closing_is_an_event(screen):
    assert screen.handle(screen.pg.event.Event(screen.pg.QUIT)) is False
    assert screen.reports == [{"event": "closed", "window": "calc"}]
    assert screen.answer({"cmd": "dance"}) == {"error": "unknown message: dance"}


# ---------------------------------------------------------------- real child processes

def test_show_update_read_close(gui):
    disk = Disk(**{"/home/user/calc.json": CALC})
    with pytest.raises(gui.GuiError, match="no window called calc is open"):
        gui.read("calc")
    assert gui.show(disk, "/home/user/calc.json") == {"window": "calc"}
    child = gui._windows["calc"].process
    assert gui.show(disk, "/home/user/calc.json") == {"window": "calc"}   # the same window
    assert gui._windows["calc"].process is child
    assert gui.update("calc", '{"a": {"text": "5"}, "result": {"text": "10"}}') == {"ok": True}
    assert gui._layouts["calc"]["widgets"][-1]["text"] == "10"
    assert gui.read("calc") == {"window": "calc", "values": {
        "a": "5", "notes": "", "tick": False, "pick": None, "level": 0}}
    with pytest.raises(gui.GuiError, match="^unknown color: blurple$"):
        gui.update("calc", '{"a": {"color": "blurple"}}')
    assert "color" not in gui._layouts["calc"]["widgets"][0]          # refused: not kept
    with pytest.raises(gui.GuiError, match="changes isn't JSON"):
        gui.update("calc", "{")
    assert gui.close("calc") == {"ok": True}
    assert child.poll() == 0 and gui._windows == {}
    with pytest.raises(gui.GuiError, match="no window called calc is open"):
        gui.close("calc")


def test_a_bad_file_opens_no_window(gui):
    disk = Disk(**{"/a.json": "{oops", "/b.json": {"name": "b", "size": [1, 1]}})
    with pytest.raises(gui.GuiError, match=r"^/a.json isn't JSON: "):
        gui.show(disk, "/a.json")
    with pytest.raises(gui.GuiError, match="size must be"):
        gui.show(disk, "/b.json")
    with pytest.raises(FileNotFoundError):            # Hallux tells the AI: ENOENT
        gui.show(disk, "/c.json")
    unknown = Disk(**{"/c.json": {"name": "c", "size": [100, 100], "background": "blurple"}})
    with pytest.raises(gui.GuiError, match="unknown color: blurple"):
        gui.show(unknown, "/c.json")
    assert gui._windows == {}


def test_at_most_four_windows(gui):
    disk = Disk(**{f"/{n}.json": {"name": f"w{n}", "size": [100, 100]} for n in range(5)})
    for n in range(4):
        gui.show(disk, f"/{n}.json")
    with pytest.raises(gui.GuiError, match=r"^4 windows are open already \(w0, w1, w2, w3\)"):
        gui.show(disk, "/4.json")
    gui._windows["w1"].process.send_signal(signal.SIGTERM)          # the user closes one
    gui._windows["w1"].process.wait(5)
    assert gui.show(disk, "/4.json") == {"window": "w4"}
    assert sorted(gui._windows) == ["w0", "w2", "w3", "w4"]
    assert gui.stop() == {"ok": True} and gui._windows == {}


def wait_for(condition, seconds=5):
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "it never happened"
        time.sleep(0.01)


def test_the_user_closes_a_window_and_the_ai_hears_it(gui):
    reported = []
    gui.connect(reported.append)
    disk = Disk(**{"/c.json": CALC})
    gui.show(disk, "/c.json")
    child = gui._windows["calc"].process
    child.send_signal(signal.SIGTERM)                 # pygame takes it for the close button
    assert child.wait(5) == 0
    wait_for(lambda: reported)
    assert reported == [{"event": "closed", "window": "calc"}]
    with pytest.raises(gui.GuiError, match="^the window calc is closed$"):
        gui.read("calc")
    gui.show(disk, "/c.json")                         # a new window
    assert gui._windows["calc"].process is not child


def test_events_reach_hallux_only_while_it_listens(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    hub = addons.Events()
    [loaded], _ = addons.load(app.ADDONS_FOLDER, only=["gui"], events=hub)
    module = sys.modules["hallux_addon_gui"]
    disk = Disk(**{"/c.json": {"name": "c", "size": [100, 100]}})

    def the_user_closes_a_window():
        module.show(disk, "/c.json")
        link = module._windows["c"]
        link.process.send_signal(signal.SIGTERM)
        assert link.process.wait(5) == 0
        link.reader.join(5)

    try:
        the_user_closes_a_window()
        assert hub.pending() == 0 and hub.reset() == {"gui": 1}
        hub.listen("gui")
        the_user_closes_a_window()
        assert hub.take() == [("gui", {"event": "closed", "window": "c"})]
    finally:
        loaded.stop()
        del sys.modules["hallux_addon_gui"]


def test_a_click_in_a_real_child_reaches_hallux(gui):
    """A click carries the id of its button. The pipe must never take it for an answer:
    that was the bug of the first live try, where only "closed" ever arrived."""
    reported = []
    gui.connect(reported.append)
    gui.CHILD[:] = [sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(app.ADDONS_FOLDER)!r})
import gui
shown = gui.Gui.layout
def layout(self, layout):
    done = shown(self, layout)
    pg = self.pg
    pg.event.post(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(20, 150)))
    pg.event.post(pg.event.Event(pg.MOUSEBUTTONUP, button=1, pos=(20, 150)))
    return done
gui.Gui.layout = layout
sys.exit(gui.child_main())"""]
    gui.show(Disk(**{"/c.json": CALC}), "/c.json")
    wait_for(lambda: reported)
    assert reported == [{"event": "click", "window": "calc", "id": "go", "values": {
        "a": "", "notes": "", "tick": False, "pick": None, "level": 0}}]
    assert gui.read("calc")["values"]["a"] == ""      # and questions are still answered


# ---------------------------------------------------------------- fonts, and what didn't draw

@pytest.fixture
def pg(gui, monkeypatch):
    monkeypatch.setenv("SDL_NO_SIGNAL_HANDLERS", "1")
    import pygame
    pygame.font.init()
    yield pygame
    pygame.quit()


def dejavu(pg, gui):
    path = pg.font.match_font(gui.SANS)
    if path is None or "dejavu" not in path.lower():
        pytest.skip("DejaVu Sans isn't installed")
    return path


def test_pygames_own_font_says_what_it_lacks(pg, gui):
    fonts = gui.Fonts(pg, None, None, None)
    assert fonts.missing("aé÷ ➤🐾‍️") == ["➤", "🐾"]   # joiners never count


def test_dejavu_draws_the_symbols_and_lacks_emoji(pg, gui):
    fonts = gui.Fonts(pg, dejavu(pg, gui), None, None)
    assert fonts.missing("➤ ⌫ ÷ × − ♥ é") == []
    assert fonts.missing("🐾 ok") == ["🐾"]


def test_a_line_is_drawn_in_runs_and_measured_the_same(pg, gui):
    """With pygame's font first and DejaVu standing in for the emoji font, whatever
    pygame's font lacks goes to the second one, scaled to the line."""
    fonts = gui.Fonts(pg, None, None, dejavu(pg, gui))
    assert fonts.runs("a ➤ b️", 22) == [(False, "a "), (True, "➤"), (False, " b")]
    for text in ["a ➤ b", "➤➤", "plain", "é ⌫"]:
        drawn = fonts.render(text, 22, pg.Color("white"))
        assert drawn.get_width() == fonts.width(text, 22)
        assert drawn.get_height() == fonts.font(22).get_height()
    assert fonts.missing("➤") == []


def test_an_unreadable_emoji_font_is_as_if_none(pg, gui, tmp_path):
    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"not a font")
    fonts = gui.Fonts(pg, None, None, str(broken))
    assert fonts.runs("a🐾", 22) == [(False, "a🐾")] and fonts.missing("🐾") == ["🐾"]


def test_the_window_tells_what_is_cut_and_missing(screen, gui):
    layout = gui.check_layout({"name": "x", "size": [400, 300], "widgets": [
        {"id": "fits", "type": "label", "pos": [0, 0], "size": [200, 40], "text": "ok"},
        {"id": "long", "type": "button", "pos": [0, 50], "size": [40, 40], "text": "far too long"},
        {"id": "short", "type": "label", "pos": [0, 100], "size": [200, 8], "text": "low"},
        {"id": "lines", "type": "text", "pos": [0, 120], "size": [200, 30], "text": "a\nb\nc\nd"},
        {"id": "art", "type": "canvas", "pos": [210, 0], "size": [60, 30], "text": "#" * 40},
        {"id": "typed", "type": "input", "pos": [210, 50], "size": [40, 30], "text": "x" * 50},
        {"id": "wide", "type": "list", "pos": [210, 100], "size": [60, 60], "items": ["y" * 30]}]})
    screen.fonts = gui.Fonts(screen.pg, None, None, None)
    told = screen.answer({"cmd": "layout", "layout": layout})
    assert told == {"ok": True, "cut": ["long", "short", "lines", "art", "wide"]}
    assert screen.answer({"cmd": "update", "changes": {"fits": {"text": "➤ 🐾"}}}) == {
        "ok": True, "missing": "➤🐾", "cut": ["long", "short", "lines", "art", "wide"]}
    screen.draw()


def test_show_and_update_pass_on_what_did_not_draw(gui):
    layout = {"name": "w", "size": [200, 100], "widgets": [
        {"id": "a", "type": "label", "pos": [0, 0], "size": [40, 30], "text": "a long label"}]}
    assert gui.show(Disk(**{"/w.json": layout}), "/w.json") == {"window": "w", "cut": ["a"]}
    assert gui.update("w", '{"a": {"text": "ok"}}') == {"ok": True}
    told = gui.update("w", '{"a": {"text": "\\ud83d\\udc3e"}}')     # 🐾, as JSON escapes it
    assert told["ok"] is True and set(told) <= {"ok", "missing"}    # missing unless an emoji
                                                                    # font is installed


def test_the_canvas_draws_what_its_font_lacks_with_the_others(screen, gui):
    fonts = gui.Fonts(screen.pg, None, None, None)
    screen.fonts = fonts
    screen.answer({"cmd": "update", "changes": {"art": {"text": "a➤🐾"}}})
    screen.draw()                                     # nothing raises; the glyphs are cached
    assert any(key[0] == "➤" for key in screen.glyphs)
