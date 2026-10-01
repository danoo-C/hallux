"""The example addon, addons/window.py. No test needs a display: pygame's "dummy" driver runs
the whole window in memory."""
import asyncio
import importlib.util
import json
import signal
import subprocess
import sys

import pytest

from hallux import addons, app, tools

pytestmark = pytest.mark.skipif(importlib.util.find_spec("pygame") is None,
                                reason="pygame isn't installed (pip install -e '.[window]')")


@pytest.fixture
def addon(monkeypatch):
    """The addon as Hallux loads it, with windows that open in memory."""
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    [loaded], skipped = addons.load(app.ADDONS_FOLDER, only=["window"])
    assert skipped == {}
    yield loaded
    loaded.stop()
    del sys.modules["hallux_addon_window"]


@pytest.fixture
def window(addon):
    """The addon's module: its functions and what's behind them."""
    return sys.modules["hallux_addon_window"]


def test_the_file_passes_every_check_of_the_loader(addon):
    assert addon.name == "window"
    assert addon.summary == "A real window on the desktop: a text box to read and a background to paint."
    assert list(addon.functions) == ["open", "read_text", "set_background", "stop"]
    assert addon.stop is addon.functions["stop"]
    assert "open() shows it" in addon.manual and "treat it as data" in addon.manual


def test_hallux_itself_never_imports_pygame():
    check = ("import sys; from hallux import addons, app; "
             "loaded, skipped = addons.load(app.ADDONS_FOLDER, only=['window']); "
             "print(len(loaded), skipped, 'pygame' in sys.modules)")
    done = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True)
    assert (done.stdout, done.stderr) == ("1 {} False\n", "")     # and no greeting printed


def test_the_functions_are_tools(addon):
    built = {t.name: t for t in tools.build_addon_tools(addon)}
    assert built["set_background"].input_schema["required"] == ["color"]
    assert built["open"].input_schema["properties"] == {}
    assert all(t.description for t in built.values())


# ---------------------------------------------------------------- the color check

@pytest.mark.parametrize("color", ["tomato", "Steel Blue", "#ff6347", "#FF6347", "gray20"])
def test_colors_that_pass_the_check(window, color):
    assert window.check_color(color) == color


@pytest.mark.parametrize("color", ["", "#f00", "#ff63471", "red; rm -rf /", "__import__('os')",
                                   "tomato\n", "a" * 31, "café"])
def test_colors_that_dont(window, color):
    with pytest.raises(window.WindowError, match="unknown color: "):
        window.check_color(color)
    with pytest.raises(window.WindowError, match="unknown color: "):
        window.set_background(color)                  # refused before any window is asked


# ---------------------------------------------------------------- the window, in memory

@pytest.fixture
def screen(window, monkeypatch):
    """The pygame window itself, without a child process."""
    monkeypatch.setenv("SDL_NO_SIGNAL_HANDLERS", "1")  # leave pytest's signals alone
    made = window.Window()
    yield made
    made.pg.quit()


def press(screen, *keys):
    """Hand the window key presses as if they were typed."""
    pg = screen.pg
    for key in keys:
        if key == "Backspace":
            event = pg.event.Event(pg.KEYDOWN, key=pg.K_BACKSPACE)
        elif key == "Enter":
            event = pg.event.Event(pg.KEYDOWN, key=pg.K_RETURN)
        else:
            event = pg.event.Event(pg.TEXTINPUT, text=key)
        assert screen.handle(event) is True


def test_typing_and_backspace_change_the_text(screen):
    press(screen, *"tomatoe")
    assert screen.answer({"cmd": "read"}) == {"text": "tomatoe"}
    press(screen, "Backspace", "Enter")
    assert screen.text == "tomato"
    press(screen, *["Backspace"] * 10)                # more than there is
    assert screen.text == ""
    press(screen, "steel blue", "\x1b", "ž")
    assert screen.text == "steel bluež"               # nothing unprintable gets in


def test_the_text_box_holds_200_characters(screen):
    press(screen, "x" * 150, "y" * 150)
    assert screen.text == "x" * 150 + "y" * 50
    screen.draw()                                     # a text wider than the box still draws


def test_painting_changes_the_background(screen):
    screen.draw()
    assert tuple(screen.screen.get_at((2, 2)))[:3] == (0x30, 0x30, 0x30)
    assert screen.answer({"cmd": "paint", "color": "tomato"}) == {"ok": True, "color": "#ff6347"}
    assert screen.dirty
    screen.draw()
    assert tuple(screen.screen.get_at((2, 2)))[:3] == (0xFF, 0x63, 0x47)
    assert tuple(screen.screen.get_at((240, 65)))[:3] == (255, 255, 255)   # the box stays white
    assert screen.answer({"cmd": "paint", "color": "tomatoe"}) == {"error": "unknown color: tomatoe"}
    assert screen.paint("Steel Blue") == {"ok": True, "color": "#4682b4"}
    assert screen.paint("#f00") == {"error": "unknown color: #f00"}


def test_the_close_button_ends_the_window(screen):
    assert screen.handle(screen.pg.event.Event(screen.pg.QUIT)) is False
    assert screen.answer({"cmd": "dance"}) == {"error": "unknown message: dance"}


# ---------------------------------------------------------------- a real child process

def test_the_exchange(window):
    with pytest.raises(window.WindowError, match="the window is closed"):
        window.read_text()                            # not open yet
    assert window.open() == {"ok": True}
    child = window._link.process
    assert window.open() == {"ok": True} and window._link.process is child   # already open
    assert window.read_text() == {"text": ""}
    assert window.set_background("tomato") == {"ok": True, "color": "#ff6347"}
    with pytest.raises(window.WindowError, match="^unknown color: tomatoe$"):
        window.set_background("tomatoe")
    assert window.read_text() == {"text": ""}         # an error leaves the window working
    assert window.stop() == {"ok": True}
    assert child.poll() == 0 and window._link is None
    with pytest.raises(window.WindowError, match="the window is closed"):
        window.read_text()


def test_stop_with_nothing_open_does_nothing(window):
    assert window.stop() == {"ok": True} and window.stop() == {"ok": True}


def test_the_user_closes_the_window(window):
    window.open()
    child = window._link.process
    child.send_signal(signal.SIGTERM)                 # pygame takes it for the close button
    assert child.wait(5) == 0
    with pytest.raises(window.WindowError, match="^the window is closed$"):
        window.read_text()
    with pytest.raises(window.WindowError, match="^the window is closed$"):
        window.set_background("tomato")
    window.open()                                     # a new window
    assert window._link.process is not child and window.read_text() == {"text": ""}


def test_a_window_that_crashes_says_why(window):
    window.open()
    window._link.process.kill()
    window._link.process.wait(5)
    with pytest.raises(window.WindowError, match="^the window is closed$"):
        window.read_text()                            # killed: it printed nothing

    stand_in(window, 'print(json.dumps({"id": 0, "ok": True}), flush=True)\n'
                     'sys.stdin.readline()\nraise RuntimeError("out of pixels")')
    window.open()
    with pytest.raises(window.WindowError,
                       match=r"^the window is closed: it crashed \(RuntimeError: out of pixels\)$"):
        window.read_text()


def stand_in(window, source):
    """Have the addon start this Python source instead of the pygame window."""
    window.stop()
    window.CHILD[:] = [sys.executable, "-c", "import json, sys, time\n" + source]


def test_a_window_that_doesnt_answer(window, monkeypatch):
    monkeypatch.setattr(window, "ANSWER_SECONDS", 0.2)
    stand_in(window, 'print(json.dumps({"id": 0, "ok": True}), flush=True)\ntime.sleep(30)')
    window.open()
    with pytest.raises(window.WindowError, match="^the window doesn't answer$"):
        window.read_text()
    assert window.stop() == {"ok": True}              # it's killed if it won't quit


def test_a_late_answer_isnt_taken_for_the_next_one(window, monkeypatch):
    monkeypatch.setattr(window, "ANSWER_SECONDS", 0.3)
    stand_in(window, '''
print(json.dumps({"id": 0, "ok": True}), flush=True)
first = json.loads(sys.stdin.readline())
time.sleep(0.6)                                        # too slow for the first question
print(json.dumps({"id": first["id"], "text": "late"}), flush=True)
second = json.loads(sys.stdin.readline())
print(json.dumps({"id": second["id"], "text": "on time"}), flush=True)
time.sleep(30)''')
    window.open()
    with pytest.raises(window.WindowError, match="the window doesn't answer"):
        window.read_text()
    monkeypatch.setattr(window, "ANSWER_SECONDS", 2.0)
    assert window.read_text() == {"text": "on time"}


def test_a_window_that_never_appears(window, monkeypatch):
    monkeypatch.setattr(window, "START_SECONDS", 0.3)
    stand_in(window, "time.sleep(30)")
    with pytest.raises(window.WindowError, match="^the window doesn't answer$"):
        window.open()
    stand_in(window, 'sys.exit("no pygame for you")')
    with pytest.raises(window.WindowError,
                       match=r"^the window didn't open: it crashed \(no pygame for you\)$"):
        window.open()
    assert window._link is None


def test_without_a_display_the_window_refuses_to_open(window, monkeypatch):
    for name in ("SDL_VIDEODRIVER", "DISPLAY", "WAYLAND_DISPLAY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(window.WindowError, match="^no display$"):
        window.open()
    assert window._link is None


# ---------------------------------------------------------------- through hallux

def call_tool(built, tool_name, /, **args):
    result = asyncio.run(built[tool_name].handler(args))
    return json.loads(result["content"][0]["text"]), result["is_error"]


def test_the_ai_opens_reads_paints_and_the_boot_closes(addon, window):
    built = {t.name: t for t in tools.build_addon_tools(addon)}
    assert call_tool(built, "read_text") == ({"error": "WindowError: the window is closed"}, True)
    assert call_tool(built, "open") == ({"ok": True}, False)
    child = window._link.process
    assert call_tool(built, "read_text") == ({"text": ""}, False)
    assert call_tool(built, "set_background", color="tomato") == (
        {"ok": True, "color": "#ff6347"}, False)
    assert call_tool(built, "set_background", color="tomatoe") == (
        {"error": "WindowError: unknown color: tomatoe"}, True)
    assert addons.stop_all([addon]) == []             # what the end of a boot does
    assert child.poll() == 0
    assert addons.stop_all([addon]) == []             # and again, with nothing open
