"""The web addon, addons/web.py. No test needs a display: Qt runs offscreen.

Skipped without PySide6 (pip install -e '.[web]'), except the test that the addon is then
skipped cleanly."""
import importlib.util
import json
import subprocess
import sys
import textwrap
import time

import pytest

from hallux import addons, app

HAS_QT = importlib.util.find_spec("PySide6") is not None
needs_qt = pytest.mark.skipif(not HAS_QT, reason="PySide6 isn't installed (pip install -e '.[web]')")


@pytest.fixture
def addon(monkeypatch):
    """The addon as Hallux loads it, with an engine that runs offscreen."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    [loaded], skipped = addons.load(app.ADDONS_FOLDER, only=["web"])
    assert skipped == {}
    yield loaded
    loaded.stop()
    del sys.modules["hallux_addon_web"]


@pytest.fixture
def web(addon):
    """The addon's module: its functions and what's behind them."""
    return sys.modules["hallux_addon_web"]


def ask(web, message: dict) -> dict:
    with web._lock:
        return web._child().ask(message)


def fake_child(web, monkeypatch, tmp_path, body: str) -> None:
    """Put a small script in the place of the Qt child, to try the pipe on its own."""
    script = tmp_path / "child.py"
    script.write_text("import json, sys\n" + textwrap.dedent(body))
    monkeypatch.setattr(web, "CHILD", [sys.executable, str(script)])


# ---------------------------------------------------------------- loading

@needs_qt
def test_the_file_passes_every_check_of_the_loader(addon):
    assert addon.name == "web"
    assert addon.summary.startswith("Web pages in windows of their own")
    assert list(addon.functions) == ["stop"]
    assert addon.stop is addon.functions["stop"] and addon.has_events


def test_hallux_itself_never_imports_qt():
    check = ("import sys; from hallux import addons, app; "
             "loaded, skipped = addons.load(app.ADDONS_FOLDER, only=['web']); "
             "print(len(loaded) + len(skipped), any(m.startswith('PySide6') for m in sys.modules))")
    done = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True)
    assert done.stdout == "1 False\n", done.stderr     # loaded, or skipped without PySide6


def test_without_pyside6_the_addon_is_skipped_cleanly():
    check = ("import sys; sys.modules['PySide6'] = None; from hallux import addons, app; "
             "loaded, skipped = addons.load(app.ADDONS_FOLDER, only=['web']); "
             "print(loaded, skipped)")
    done = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True)
    assert done.stdout == "[] {'web': \"No module named 'PySide6'\"}\n", done.stderr


# ---------------------------------------------------------------- the child

@needs_qt
def test_the_child_says_hello_answers_and_quits(web):
    assert ask(web, {"cmd": "ping"}) == {"ok": True}
    assert "doesn't know dance" in ask(web, {"cmd": "dance"})["error"]
    process = web._link.process
    web.stop()
    assert process.returncode == 0 and web._link is None


@needs_qt
def test_the_child_quits_when_its_stdin_closes(monkeypatch, web):
    child = subprocess.Popen(web.CHILD, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, env=web.child_env())
    assert json.loads(child.stdout.readline()) == {"seq": 0, "ok": True}
    child.stdin.close()
    assert child.wait(5) == 0


@needs_qt
def test_a_child_that_died_is_started_again(web):
    ask(web, {"cmd": "ping"})
    first = web._link.process
    first.kill()
    first.wait()
    assert ask(web, {"cmd": "ping"}) == {"ok": True}
    assert web._link.process is not first


@needs_qt
def test_stop_with_nothing_running_is_fine(web):
    assert web.stop() == {"ok": True} and web.stop() == {"ok": True}


@needs_qt
def test_the_environment_is_quiet_and_has_the_systems_fonts(web, monkeypatch):
    monkeypatch.delenv("FONTCONFIG_FILE", raising=False)
    env = web.child_env()
    assert env["QTWEBENGINE_CHROMIUM_FLAGS"] == "--log-level=3"
    assert "*.warning=false" in env["QT_LOGGING_RULES"]
    assert env.get("FONTCONFIG_FILE") == (web.SYSTEM_FONTS if web.os.path.exists(web.SYSTEM_FONTS)
                                          else None)
    monkeypatch.setenv("FONTCONFIG_FILE", "/mine.conf")
    assert web.child_env()["FONTCONFIG_FILE"] == "/mine.conf"   # the user's own wins


# ---------------------------------------------------------------- the pipe, with a stand-in

@needs_qt
def test_much_printed_to_stderr_never_garbles_the_line(web, monkeypatch, tmp_path):
    fake_child(web, monkeypatch, tmp_path, """
        for _ in range(2000):
            print("MESA: warning: something long and noisy " * 3, file=sys.stderr)
        print(json.dumps({"seq": 0, "ok": True}), flush=True)
        for line in sys.stdin:
            message = json.loads(line)
            if message.get("cmd") == "quit":
                break
            print("noise " * 50, file=sys.stderr, flush=True)
            print(json.dumps({"seq": message["seq"], "pong": True}), flush=True)
    """)
    assert [ask(web, {"cmd": "ping"}) for _ in range(3)] == [{"pong": True}] * 3


@needs_qt
def test_a_child_that_crashes_is_reported_with_its_last_line(web, monkeypatch, tmp_path):
    fake_child(web, monkeypatch, tmp_path, """
        print("loading the engine", file=sys.stderr)
        print("qt.qpa.plugin: Could not load the Qt platform plugin", file=sys.stderr)
        sys.exit(1)
    """)
    with pytest.raises(web.WebError) as e:
        ask(web, {"cmd": "ping"})
    assert str(e.value) == ("the web engine didn't start: it crashed "
                            "(qt.qpa.plugin: Could not load the Qt platform plugin)")
    assert web._link is None


@needs_qt
def test_a_child_that_never_says_hello_fails_in_time(web, monkeypatch, tmp_path):
    fake_child(web, monkeypatch, tmp_path, "import time; time.sleep(30)\n")
    monkeypatch.setattr(web, "START_SECONDS", 0.5)
    started = time.monotonic()
    with pytest.raises(web.WebError, match="^the web engine didn't start$"):
        ask(web, {"cmd": "ping"})
    assert time.monotonic() - started < 5


@needs_qt
def test_a_crash_after_the_start_is_reported(web, monkeypatch, tmp_path):
    fake_child(web, monkeypatch, tmp_path, """
        print(json.dumps({"seq": 0, "ok": True}), flush=True)
        sys.stdin.readline()
        print("Segmentation fault in the renderer", file=sys.stderr)
        sys.exit(139)
    """)
    with pytest.raises(web.WebError, match=r"stopped: it crashed \(Segmentation fault"):
        ask(web, {"cmd": "ping"})


@needs_qt
def test_a_line_that_answers_nothing_is_an_event(web, monkeypatch, tmp_path):
    heard = []
    web.connect(heard.append)
    fake_child(web, monkeypatch, tmp_path, """
        print(json.dumps({"seq": 0, "ok": True}), flush=True)
        message = json.loads(sys.stdin.readline())
        print(json.dumps({"event": "loaded", "page": "chat"}), flush=True)
        print(json.dumps({"seq": message["seq"], "ok": True}), flush=True)
        sys.stdin.readline()
    """)
    assert ask(web, {"cmd": "ping"}) == {"ok": True}
    assert heard == [{"event": "loaded", "page": "chat"}]
