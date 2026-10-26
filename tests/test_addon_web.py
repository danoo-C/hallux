"""The web addon, addons/web.py. No test needs a display: Qt runs offscreen.

Skipped without PySide6 (pip install -e '.[web]'), except the test that the addon is then
skipped cleanly."""
import importlib.util
import http.server
import json
import posixpath
import re
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from hallux import addons, app, tools

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
    assert list(addon.functions) == ["open_page", "reload", "close_page", "reply", "tell", "stop"]
    assert addon.stop is addon.functions["stop"] and addon.has_events


@needs_qt
def test_the_functions_are_tools(addon):
    built = {t.name: t for t in tools.build_addon_tools(addon)}
    assert built["open_page"].input_schema["required"] == ["folder"]   # disk is never shown
    assert built["reload"].input_schema["required"] == ["page"]
    assert built["close_page"].input_schema["required"] == ["page"]
    assert all(t.description for t in built.values())
    assert "app.json" in addon.manual and 'addon_listen("web")' in addon.manual


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
    assert env["QTWEBENGINE_CHROMIUM_FLAGS"].startswith("--log-level=3 --proxy-server=")
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")
    assert "--no-sandbox" not in web.child_env()["QTWEBENGINE_CHROMIUM_FLAGS"]
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


# ---------------------------------------------------------------- the walls

@pytest.fixture
def trap():
    """A server on 127.0.0.1 that records every request that gets out of a page."""
    hits = []

    class Trap(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(("GET", self.path))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"leak")

        def do_POST(self):
            hits.append(("POST", self.path))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    class Server(http.server.ThreadingHTTPServer):
        def verify_request(self, request, address):
            hits.append(("CONNECT", address[1]))  # a socket opened, with or without a request
            return True

    server = Server(("127.0.0.1", 0), Trap)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", hits
    server.shutdown()


def open_app(web, name: str, files: dict) -> None:
    assert ask(web, {"cmd": "open", "app": name, "files": files}) == {"ok": True}


def results(web, name: str, seconds: float = 40) -> dict:
    """What the page logged as "RESULT <key> <value>", once it logged "RESULT done"."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        report = ask(web, {"cmd": "report", "app": name})
        found = dict(line["message"].removeprefix("RESULT ").split(" ", 1)
                     for line in report["console"] if line["message"].startswith("RESULT "))
        if "done" in found:
            return found | {"report": report}
        time.sleep(0.2)
    raise AssertionError(f"the page never finished: {report}")


HOSTILE = """
const R = (k, v) => console.log("RESULT " + k + " " + v);
const tryit = async (k, f) => { try { await f(); R(k, "ALLOWED"); } catch (e) { R(k, "blocked"); } };
const T = "TRAP";
(async () => {
  await tryit("fetch-local", () => fetch(T + "/fetch"));
  await tryit("fetch-https", () => fetch("https://example.com/"));
  await tryit("fetch-file", () => fetch("file:///etc/passwd"));
  await tryit("fetch-other-app", () => fetch("hallux://other/x.js"));
  await tryit("xhr", () => new Promise((ok, no) => { const x = new XMLHttpRequest();
    x.open("GET", T + "/xhr"); x.onload = ok; x.onerror = no; x.send(); }));
  await tryit("websocket", () => new Promise((ok, no) => { const w = new WebSocket(
    T.replace("http", "ws") + "/ws"); w.onopen = ok; w.onerror = no; }));
  await tryit("beacon", async () => { if (!navigator.sendBeacon(T + "/beacon", "x")) throw 0; });
  await tryit("eventsource", () => new Promise((ok, no) => { const e = new EventSource(T + "/es");
    e.onopen = ok; e.onerror = () => { e.close(); no(); }; }));
  await tryit("worker", () => new Promise((ok, no) => { const w = new Worker(T + "/worker.js");
    w.onerror = no; setTimeout(ok, 500); }));
  R("window-open", String(window.open(T + "/popup")));
  const a = document.createElement("a"); a.href = T + "/blank"; a.target = "_blank";
  document.body.append(a); a.click();
  await new Promise(ok => setTimeout(ok, 500));
  location = T + "/location";
  await new Promise(ok => setTimeout(ok, 500));
  document.getElementById("form").submit();
  await new Promise(ok => setTimeout(ok, 500));
  const meta = document.createElement("meta"); meta.httpEquiv = "refresh";
  meta.content = "0; url=" + T + "/refresh"; document.head.append(meta);
  await new Promise(ok => setTimeout(ok, 1500));
  R("still-here", location.href);
  R("done", "yes");
})();
"""


@needs_qt
def test_a_hostile_page_gets_nothing_out(web, trap):
    address, hits = trap
    page = f"""<!doctype html><html><head><meta charset=utf-8>
<link rel=prefetch href="{address}/prefetch"><link rel=preconnect href="{address}/preconnect">
<link rel=dns-prefetch href="//leak.example.com">
<style>body {{ background: url({address}/css) }}</style></head>
<body><img src="{address}/img"><iframe src="{address}/iframe"></iframe>
<form id=form action="{address}/form" method=post><input name=a value=1></form>
<script src="hostile.js"></script></body></html>"""
    open_app(web, "evil", {"index.html": page, "hostile.js": HOSTILE.replace("TRAP", address)})
    found = results(web, "evil")
    tried = ["fetch-local", "fetch-https", "fetch-file", "fetch-other-app", "xhr", "websocket",
             "eventsource", "worker"]            # a beacon only queues: the wall stops it later
    assert {key: found[key] for key in tried} == dict.fromkeys(tried, "blocked")
    assert found["window-open"] == "null"
    assert found["still-here"] == "hallux://evil/"
    time.sleep(0.5)
    assert hits == []
    blocked = " ".join(found["report"]["blocked_urls"])
    for path in ("/img", "/css", "/iframe", "/fetch", "/xhr", "/beacon", "/es", "/location",
                 "/form", "/refresh"):
        assert address + path in blocked, path
    assert found["report"]["blocked"] >= 10


@needs_qt
def test_a_pages_own_files_are_served_and_nothing_else(web):
    files = {
        "index.html": "<!doctype html><link rel=stylesheet href='css/style.css'>"
                      "<h1>hi</h1><img id=icon src='/icons/cat.svg'><script src='app.js'></script>",
        "css/style.css": "h1 { color: rgb(255, 99, 71) }",
        "icons/cat.svg": "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>",
        "data/msg.json": '{"hi": "there"}',
        "sub/index.html": "sub",
        "app.js": """
const R = (k, v) => console.log("RESULT " + k + " " + v);
const status = async (path) => { try { return (await fetch(path)).status; } catch (e) { return "error"; } };
window.onload = async () => {
  R("color", getComputedStyle(document.querySelector("h1")).color.replaceAll(" ", ""));
  R("svg", document.getElementById("icon").naturalWidth);
  R("json", (await (await fetch("data/msg.json")).json()).hi);
  R("absolute", await status("/data/msg.json"));
  R("dotdot", await status("../../data/msg.json"));
  R("dotdot-encoded", await status("/%2e%2e/%2e%2e/data/msg.json"));
  R("escape", await status("../../../etc/passwd"));
  R("missing", await status("nothing.js"));
  R("folder", await (await fetch("sub/")).text());
  R("type", (await fetch("data/msg.json")).headers.get("content-type").replaceAll(" ", ""));
  R("data-url", await status("data:text/plain,hi"));
  R("done", "yes");
};"""}
    open_app(web, "own", files)
    found = results(web, "own")
    assert found["color"] == "rgb(255,99,71)" and found["svg"] == "10" and found["json"] == "there"
    assert (found["absolute"], found["dotdot"], found["dotdot-encoded"]) == ("200", "200", "200")
    assert (found["escape"], found["missing"]) == ("404", "404")
    assert found["folder"] == "sub" and found["type"] == "application/json;charset=utf-8"
    assert found["data-url"] == "200"
    assert found["report"]["blocked"] == 0 and found["report"]["off_the_record"] is True


@needs_qt
def test_one_app_never_sees_anothers_files(web):
    open_app(web, "other", {"index.html": "other", "secret.js": "var secret = 1"})
    open_app(web, "mine", {"index.html": "<script src='hallux://other/secret.js'></script>"
                                         "<script>console.log('RESULT secret ' + typeof secret);"
                                         "console.log('RESULT done yes')</script>"})
    found = results(web, "mine")
    assert found["secret"] == "undefined"
    assert "hallux://other/secret.js" in found["report"]["blocked_urls"]


@needs_qt
def test_storage_is_gone_when_the_window_closes(web):
    page = {"index.html": "<script>console.log('RESULT before ' + localStorage.getItem('x'));"
                          "localStorage.setItem('x', 'kept'); document.cookie = 'c=1';"
                          "console.log('RESULT done yes')</script>"}
    open_app(web, "store", page)
    assert results(web, "store")["before"] == "null"
    assert ask(web, {"cmd": "close", "app": "store"}) == {"ok": True}
    open_app(web, "store", page)
    assert results(web, "store")["before"] == "null"


@needs_qt
def test_a_preconnect_opens_no_socket(web, trap):
    """A preconnect never passes the interceptor: the proxy that isn't there stops it."""
    address, hits = trap
    open_app(web, "pre", {"index.html": f"<link rel=preconnect href='{address}/'>"
                                        f"<link rel=dns-prefetch href='{address}/'>"
                                        "<script>setTimeout(() => console.log('RESULT done yes'), 2000)"
                                        "</script>"})
    results(web, "pre")
    assert hits == []


@needs_qt
def test_closing_a_window_is_no_failure(web):
    heard = []
    web.connect(heard.append)
    open_app(web, "bye", {"index.html": "<script>console.log('RESULT done yes')</script>"})
    results(web, "bye")
    assert ask(web, {"cmd": "close", "app": "bye"}) == {"ok": True}
    assert ask(web, {"cmd": "ping"}) == {"ok": True}
    time.sleep(1)
    assert heard == [{"event": "loaded", "page": "bye"}]


# ---------------------------------------------------------------- apps and windows

class Disk:
    """A stand-in for the disk handle: the machine's files, in a dictionary."""

    def __init__(self, **files):
        self.files = {path: json.dumps(f) if isinstance(f, dict) else f
                      for path, f in files.items()}

    def read_text(self, path):
        if path not in self.files:
            raise FileNotFoundError(2, "No such file", path)
        if self.files[path] is None:
            raise ValueError("binary file")
        return self.files[path]


def app_disk(name="chat", folder="/home/user/chat", **files):
    files = {"index.html": "<script>console.log('RESULT done yes')</script>"} | files
    listed = {"name": name, "title": name.title(), "files": list(files)}
    return Disk(**{f"{folder}/app.json": listed}, **{f"{folder}/{p}": t for p, t in files.items()})


def events(heard, kind, seconds=30):
    """Wait until an event of this kind was heard; all heard so far."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if any(e.get("event") == kind for e in heard):
            return heard
        time.sleep(0.1)
    raise AssertionError(f"no {kind} event: {heard}")


@needs_qt
def test_a_good_app_json_gets_its_defaults(web):
    assert web.check_app({"name": "chat", "files": ["index.html"]}) == {
        "name": "chat", "title": "chat", "size": [800, 600], "files": ["index.html"]}


@needs_qt
def test_every_problem_of_app_json_is_told_at_once(web):
    with pytest.raises(web.WebError) as e:
        web.check_app({"name": "no spaces", "title": "", "size": [100, 5000], "colour": 1,
                       "files": ["/etc/passwd", "../up.js", "a/../b.js", "app.json", "x.js",
                                 "x.js", 7]})
    told = str(e.value)
    assert told.startswith("app.json has 11 problems: unknown key 'colour'; name must be")
    for part in ("title must be", "size must be", "/etc/passwd: must be relative",
                 "../up.js: .. leaves", "a/../b.js: .. leaves", "app.json: not a plain path",
                 "every file must be a path", "files must have index.html", "twice: x.js"):
        assert part in told, part


@needs_qt
def test_app_json_limits(web):
    with pytest.raises(web.WebError, match="files must list 1 to 200"):
        web.check_app({"name": "a", "files": [f"f{i}.js" for i in range(201)]})
    with pytest.raises(web.WebError, match="files must list"):
        web.check_app({"name": "a", "files": []})
    with pytest.raises(web.WebError, match="must be a JSON object"):
        web.check_app(["index.html"])


@needs_qt
def test_a_file_that_cant_be_read_is_one_error_and_no_window(web):
    disk = app_disk(**{"app.js": "1"})
    del disk.files["/home/user/chat/app.js"]
    with pytest.raises(web.WebError, match="^/home/user/chat/app.js: ENOENT$"):
        web.open_page(disk, "/home/user/chat")
    disk.files["/home/user/chat/app.js"] = None
    with pytest.raises(web.WebError, match="app.js: not text$"):
        web.open_page(disk, "/home/user/chat/")
    with pytest.raises(web.WebError, match="^/nowhere/app.json: ENOENT$"):
        web.open_page(disk, "/nowhere")
    assert web._link is None                          # nothing was started for it


@needs_qt
def test_an_app_of_more_than_10_mb_is_refused(web):
    big = "x" * (900 * 1024)
    disk = app_disk(**{f"part{i}.js": big for i in range(12)})
    with pytest.raises(web.WebError, match="more than 10 MB in all"):
        web.open_page(disk, "/home/user/chat")


@needs_qt
def test_open_page_returns_at_once_and_loaded_follows(web):
    heard = []
    web.connect(heard.append)
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat"}
    assert events(heard, "loaded") == [{"event": "loaded", "page": "chat"}]
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat", "open": "already"}


# A window slow to come (docs/plans/web-addon/fixes/01): the first one starts Chromium, which
# can take longer than open_page waits.

def slow_child(web, monkeypatch, tmp_path, delay: float, answer: dict | None,
               closed_first: bool = False):
    """A child that makes its window in `delay` seconds and then answers `answer` (None: never),
    with a loaded event after an ok; closed_first sends a closed event just before that answer.
    It writes every message it gets to a file, and returns what it got."""
    fake_child(web, monkeypatch, tmp_path, f"""
        import time
        got = open(sys.argv[1], "a")
        print(json.dumps({{"seq": 0, "ok": True}}), flush=True)
        for line in sys.stdin:
            message = json.loads(line)
            got.write(line)
            got.flush()
            if message["cmd"] == "quit":
                break
            if message["cmd"] != "open":
                print(json.dumps({{"seq": message["seq"], "ok": True}}), flush=True)
                continue
            time.sleep({delay!r})
            if {closed_first!r}:
                print(json.dumps({{"event": "closed", "page": message["app"]}}), flush=True)
            if {answer!r} is not None:
                print(json.dumps({{"seq": message["seq"], **{answer!r}}}), flush=True)
                if "ok" in {answer!r}:
                    print(json.dumps({{"event": "loaded", "page": message["app"]}}), flush=True)
    """)
    got = tmp_path / "got.jsonl"
    monkeypatch.setattr(web, "CHILD", web.CHILD + [str(got)])
    monkeypatch.setattr(web, "OPEN_SECONDS", 0.3)
    return lambda: [json.loads(line)["cmd"] for line in got.read_text().splitlines()]


def failures(heard):
    return [e for e in heard if e.get("event") == "failed"]


@needs_qt
def test_a_slow_window_is_starting_and_opens(web, monkeypatch, tmp_path):
    heard = []
    web.connect(heard.append)
    sent = slow_child(web, monkeypatch, tmp_path, delay=1.5, answer={"ok": True})
    starting = {"page": "chat", "starting": True}
    assert web.open_page(app_disk(), "/home/user/chat") == starting
    assert web.open_page(app_disk(), "/home/user/chat") == starting   # asks nothing
    for call in (lambda: web.reply("chat", 1, "{}"), lambda: web.tell("chat", "{}"),
                 lambda: web.reload(app_disk(), "chat"), lambda: web.close_page("chat")):
        with pytest.raises(web.WebError,
                           match="^the page chat is still opening: wait for its loaded event$"):
            call()
    events(heard, "loaded", 10)
    assert web._link.opening == {} and web._link.pages == {"chat": "/home/user/chat"}
    assert web.tell("chat", "{}") == {"ok": True}
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat", "open": "already"}
    assert sent() == ["open", "tell", "raise"]
    assert failures(heard) == []


@needs_qt
def test_a_slow_window_that_fails_is_a_failed_event(web, monkeypatch, tmp_path):
    heard = []
    web.connect(heard.append)
    slow_child(web, monkeypatch, tmp_path, delay=1.0, answer={"error": "no display"})
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat", "starting": True}
    events(heard, "failed", 10)
    assert failures(heard) == [{"event": "failed", "page": "chat", "why": "no display"}]
    assert web._link.pages == {} and web._link.opening == {}


@needs_qt
def test_a_window_that_never_comes_fails_out_loud(web, monkeypatch, tmp_path):
    heard = []
    web.connect(heard.append)
    sent = slow_child(web, monkeypatch, tmp_path, delay=0.0, answer=None)
    monkeypatch.setattr(web, "OPENING_SECONDS", 1.0)
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat", "starting": True}
    events(heard, "failed", 10)
    assert failures(heard) == [{"event": "failed", "page": "chat",
                                "why": "the window didn't open within 1 seconds"}]
    assert web._link.pages == {} and web._link.opening == {}
    time.sleep(0.3)
    assert sent() == ["open", "close"]                # in case it comes after all
    with pytest.raises(web.WebError, match="^no page called chat is open$"):
        web.tell("chat", "{}")


@needs_qt
def test_a_window_the_user_closes_while_it_opens_is_no_failure(web, monkeypatch, tmp_path):
    heard = []
    web.connect(heard.append)
    slow_child(web, monkeypatch, tmp_path, delay=0.8, answer={"ok": True}, closed_first=True)
    monkeypatch.setattr(web, "OPENING_SECONDS", 1.0)
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat", "starting": True}
    events(heard, "closed", 10)
    time.sleep(1.5)                                   # past OPENING_SECONDS: the timer stopped
    assert failures(heard) == []
    assert web._link.pages == {} and web._link.opening == {}


@needs_qt
def test_an_answer_that_comes_as_the_wait_ends_is_not_lost(web, monkeypatch, tmp_path):
    fake_child(web, monkeypatch, tmp_path, """
        print(json.dumps({"seq": 0, "ok": True}), flush=True)
        for line in sys.stdin:
            message = json.loads(line)
            print(json.dumps({"seq": message["seq"], "pong": True}), flush=True)
    """)
    with web._lock:
        link = web._child()
    real = link._answer

    def too_late(seq, seconds, waits=True):           # the answer is queued, but the wait ended
        if not waits:
            return real(seq, seconds, waits)
        while link.answers.empty():
            time.sleep(0.01)
        raise web._NoAnswer("the web engine doesn't answer")

    monkeypatch.setattr(link, "_answer", too_late)
    handed = []
    assert link.ask_or_later({"cmd": "ping"}, 0.1, later=handed.append) == {"pong": True}
    assert handed == [] and link.late == {}


@needs_qt
def test_the_manual_says_what_starting_means(addon):
    assert '"starting": true: the web engine is still starting' in addon.manual


# The engine started at boot (docs/plans/web-addon/fixes/02).

def boot_child(web, monkeypatch, tmp_path, hello_after: float = 0.0):
    """A child that says hello after `hello_after` seconds and answers everything ok. Every
    child started writes its process number to one file, and what it got to another."""
    fake_child(web, monkeypatch, tmp_path, f"""
        import os, time
        pids, got = open(sys.argv[1], "a"), open(sys.argv[2], "a")
        pids.write(f"{{os.getpid()}}\\n")
        pids.flush()
        time.sleep({hello_after!r})
        print(json.dumps({{"seq": 0, "ok": True}}), flush=True)
        for line in sys.stdin:
            message = json.loads(line)
            got.write(line)
            got.flush()
            if message["cmd"] == "quit":
                break
            print(json.dumps({{"seq": message["seq"], "ok": True}}), flush=True)
    """)
    pids, got = tmp_path / "pids", tmp_path / "got.jsonl"
    monkeypatch.setattr(web, "CHILD", web.CHILD + [str(pids), str(got)])
    monkeypatch.setattr(web, "_can_show", lambda: True)
    monkeypatch.setattr(web, "_early", None)

    def started():
        return [int(p) for p in pids.read_text().split()] if pids.exists() else []

    def sent():
        return [json.loads(l)["cmd"] for l in got.read_text().splitlines()] if got.exists() else []
    return started, sent


def alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def wait_for(condition, seconds=10):
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "it never happened"
        time.sleep(0.05)


@needs_qt
def test_connect_starts_the_engine_and_warms_it(web, monkeypatch, tmp_path):
    started, sent = boot_child(web, monkeypatch, tmp_path)
    web.connect(lambda event: None)
    wait_for(lambda: sent() == ["warm"])
    link = web._link
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat"}
    assert web._link is link and len(started()) == 1 and sent() == ["warm", "open"]
    assert link.late == {}                            # the warm's answer was taken


@needs_qt
def test_stop_while_the_engine_starts_keeps_nothing(web, monkeypatch, tmp_path):
    started, sent = boot_child(web, monkeypatch, tmp_path, hello_after=1.0)
    web.connect(lambda event: None)
    wait_for(lambda: started())
    began = time.monotonic()
    web.stop()
    assert time.monotonic() - began < 0.5             # it didn't wait for the hello
    web._early.join(10)
    assert web._link is None and sent() == ["quit"]  # the child it made, closed: no warm
    wait_for(lambda: not alive(started()[0]))


@needs_qt
def test_a_call_during_the_start_at_boot_leaves_one_engine(web, monkeypatch, tmp_path):
    started, sent = boot_child(web, monkeypatch, tmp_path, hello_after=1.0)
    web.connect(lambda event: None)
    wait_for(lambda: started())
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat"}
    web._early.join(10)
    first, second = started()
    assert web._link.process.pid == second             # the call's own engine is kept
    assert sorted(sent()) == ["open", "quit"]           # the early one: closed, never warmed
    wait_for(lambda: not alive(first))


@needs_qt
def test_nothing_starts_at_boot_without_a_display_or_with_the_setting_off(web, monkeypatch,
                                                                         tmp_path):
    started, _ = boot_child(web, monkeypatch, tmp_path)
    monkeypatch.setitem(web._config, "start_engine_at_boot", False)
    web.connect(lambda event: None)
    assert web._early is None
    monkeypatch.setitem(web._config, "start_engine_at_boot", True)
    monkeypatch.setattr(web, "_can_show", lambda: False)
    web.connect(lambda event: None)
    assert web._early is None
    time.sleep(0.3)
    assert started() == []


@needs_qt
def test_a_window_can_be_shown_only_in_a_terminal_on_a_display(web, monkeypatch):
    class Tty:
        def __init__(self, tty):
            self.tty = tty

        def isatty(self):
            return self.tty

    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(sys, "stdin", Tty(True))
    monkeypatch.setattr(sys, "stdout", Tty(True))
    assert web._can_show()
    monkeypatch.setattr(sys, "stdout", Tty(False))    # pytest, or hallux --script - | ...
    assert not web._can_show()
    monkeypatch.setattr(sys, "stdout", Tty(True))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    assert not web._can_show()
    monkeypatch.delenv("QT_QPA_PLATFORM")
    monkeypatch.delenv("WAYLAND_DISPLAY")
    assert not web._can_show()
    monkeypatch.setenv("DISPLAY", ":0")
    assert web._can_show()


@needs_qt
def test_the_real_engine_warms_and_its_windows_work_as_before(web, trap):
    _, hits = trap
    heard = []
    web.connect(heard.append)
    assert ask(web, {"cmd": "warm"}) == {"ok": True}
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat"}
    found = results(web, "chat")
    assert found["done"] == "yes" and found["report"]["blocked"] == 0
    assert [e["event"] for e in heard] == ["loaded"]  # nothing for the warm page
    assert hits == []


@needs_qt
def test_a_real_window_slow_to_come_opens_all_the_same(web, monkeypatch):
    heard = []
    web.connect(heard.append)
    monkeypatch.setattr(web, "OPEN_SECONDS", 0.001)   # no real window comes this fast
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat", "starting": True}
    assert events(heard, "loaded") == [{"event": "loaded", "page": "chat"}]
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat", "open": "already"}
    assert results(web, "chat")["done"] == "yes"


@needs_qt
def test_a_third_page_is_refused_and_close_page_makes_room(web):
    for name in ("one", "two"):
        web.open_page(app_disk(name, f"/apps/{name}"), f"/apps/{name}")
    with pytest.raises(web.WebError, match=r"2 pages are open already \(one, two\)"):
        web.open_page(app_disk("three", "/apps/three"), "/apps/three")
    assert web.close_page("one") == {"ok": True}
    assert web.open_page(app_disk("three", "/apps/three"), "/apps/three") == {"page": "three"}
    with pytest.raises(web.WebError, match="no page called one is open"):
        web.close_page("one")
    web.stop()
    with pytest.raises(web.WebError, match="no page called two is open"):
        web.reload(Disk(), "two")


@needs_qt
def test_reload_shows_a_changed_file(web):
    disk = app_disk(**{"index.html": "<script src=app.js></script>",
                       "app.js": "console.log('RESULT v one'); console.log('RESULT done yes')"})
    web.open_page(disk, "/home/user/chat")
    assert results(web, "chat")["v"] == "one"
    disk.files["/home/user/chat/app.js"] = "console.log('RESULT v two')"
    assert web.reload(disk, "chat") == {"ok": True}
    deadline = time.monotonic() + 20
    while "RESULT v two" not in [c["message"] for c in ask(web, {"cmd": "report", "app": "chat"})["console"]]:
        assert time.monotonic() < deadline, "the change never showed"
        time.sleep(0.1)


@needs_qt
def test_the_window_has_its_title_and_size(web):
    disk = app_disk(**{"index.html": "<script>console.log('RESULT size ' + innerWidth + 'x' "
                                     "+ innerHeight); console.log('RESULT done yes')</script>"})
    listed = json.loads(disk.files["/home/user/chat/app.json"]) | {"size": [640, 480]}
    disk.files["/home/user/chat/app.json"] = json.dumps(listed)
    web.open_page(disk, "/home/user/chat")
    assert results(web, "chat")["size"] == "640x480"
    assert ask(web, {"cmd": "report", "app": "chat"})["title"] == "Chat \u2014 hallux"


@needs_qt
def test_the_user_closing_a_window_is_an_event(web):
    heard = []
    web.connect(heard.append)
    web.open_page(app_disk(), "/home/user/chat")
    events(heard, "loaded")
    assert ask(web, {"cmd": "as_user", "app": "chat"}) == {"ok": True}
    assert events(heard, "closed")[-1] == {"event": "closed", "page": "chat"}
    assert "chat" not in web._link.pages
    assert web.open_page(app_disk(), "/home/user/chat") == {"page": "chat"}   # opens anew


@needs_qt
def test_a_crashed_engine_fails_every_page_and_starts_again(web):
    heard = []
    web.connect(heard.append)
    for name in ("one", "two"):
        web.open_page(app_disk(name, f"/apps/{name}"), f"/apps/{name}")
    old = web._link.process
    old.kill()
    deadline = time.monotonic() + 10
    while len([e for e in heard if e["event"] == "failed"]) < 2:
        assert time.monotonic() < deadline, heard
        time.sleep(0.1)
    failed = sorted(e["page"] for e in heard if e["event"] == "failed")
    assert failed == ["one", "two"]
    assert all(e["why"].startswith("the web engine stopped") for e in heard if e["event"] == "failed")
    assert web.open_page(app_disk("one", "/apps/one"), "/apps/one") == {"page": "one"}
    assert web._link.process is not old and list(web._link.pages) == ["one"]


@needs_qt
def test_links_between_an_apps_pages_work(web):
    disk = app_disk(**{
        "index.html": "<a id=go href='settings.html'>settings</a>"
                      "<script>setTimeout(() => document.getElementById('go').click(), 300)</script>",
        "settings.html": "<script>console.log('RESULT where ' + location.pathname);"
                         "console.log('RESULT done yes')</script>"})
    web.open_page(disk, "/home/user/chat")
    assert results(web, "chat")["where"] == "/settings.html"


@needs_qt
def test_a_refused_navigation_is_no_failure(web, trap):
    address, hits = trap
    heard = []
    web.connect(heard.append)
    disk = app_disk(**{"index.html": f"<script>setTimeout(() => location = '{address}/x', 300);"
                                     "setTimeout(() => console.log('RESULT done yes'), 1500)</script>"})
    web.open_page(disk, "/home/user/chat")
    results(web, "chat")
    assert [e["event"] for e in heard] == ["loaded"] and hits == []


# ---------------------------------------------------------------- the bridge

def bridge_app(web, heard, script: str, seconds_timeout: int = 120):
    """Open an app whose index.html runs `script`, with R() and done() to report."""
    web.connect(heard.append)
    web._config["ask_timeout_seconds"] = seconds_timeout
    page = ("<script>const R = (k, v) => console.log('RESULT ' + k + ' ' + v);"
            "const done = () => R('done', 'yes');</script><script>" + script + "</script>")
    web.open_page(app_disk(**{"index.html": page}), "/home/user/chat")


def first(heard, kind, seconds=30):
    events(heard, kind, seconds)
    return next(e for e in heard if e.get("event") == kind)


@pytest.fixture
def quick(web, monkeypatch):
    """The addon, with web.toml's time limit put back after the test."""
    monkeypatch.setitem(web._config, "ask_timeout_seconds", 120)
    return web


@needs_qt
def test_a_page_asks_and_the_ai_replies(quick):
    web, heard = quick, []
    bridge_app(web, heard, "hallux.ask({q: 'six times seven'})"
                           ".then(r => { R('answer', JSON.stringify(r)); done(); })")
    asked = first(heard, "ask")
    assert asked == {"event": "ask", "page": "chat", "id": 1, "data": {"q": "six times seven"}}
    assert web.reply("chat", 1, '{"a": 42}') == {"ok": True}
    assert results(web, "chat")["answer"] == '{"a":42}'
    with pytest.raises(web.WebError, match="no ask 1 of chat waits"):
        web.reply("chat", 1, '"again"')
    with pytest.raises(web.WebError, match="no ask 99 of chat waits"):
        web.reply("chat", 99, "1")


@needs_qt
def test_an_unanswered_ask_fails_at_its_time_limit(quick):
    web, heard = quick, []
    bridge_app(web, heard, "hallux.ask('hello?').catch(e => { R('failed', e.message); done(); })",
               seconds_timeout=1)
    asked = first(heard, "ask")
    assert results(web, "chat")["failed"] == "hallux: no answer in 1 seconds"
    with pytest.raises(web.WebError, match="timed out"):
        web.reply("chat", asked["id"], '"too late"')


@needs_qt
def test_emit_and_tell_both_ways_and_early_calls_are_not_lost(quick):
    web, heard = quick, []
    # Called at once, before the channel is ready: they wait for it.
    bridge_app(web, heard, "hallux.on('message', d => { R('told', JSON.stringify(d)); done(); });"
                           "hallux.emit({clicked: 'send'});")
    assert first(heard, "page") == {"event": "page", "page": "chat", "data": {"clicked": "send"}}
    assert web.tell("chat", '{"news": [1, 2]}') == {"ok": True}
    assert results(web, "chat")["told"] == '{"news":[1,2]}'


@needs_qt
def test_one_ask_a_second(quick):
    web, heard = quick, []
    bridge_app(web, heard, """
        hallux.ask(1);
        hallux.ask(2).catch(e => { R('second', e.message); });
        setTimeout(() => hallux.ask(3).then(() => {}, e => R('third', e.message)), 1100);
        setTimeout(done, 1600);""")
    found = results(web, "chat")
    assert found["second"] == "hallux: too many requests: one ask a second"
    assert "third" not in found                       # a second later, it went through
    assert [e["data"] for e in heard if e["event"] == "ask"] == [1, 3]


@needs_qt
def test_one_emit_a_second(quick):
    web, heard = quick, []
    bridge_app(web, heard, "hallux.emit(1); hallux.emit(2).catch(e => { R('second', e.message);"
                           "done(); });")
    assert results(web, "chat")["second"] == "hallux: too many events: one emit a second"
    assert [e["data"] for e in heard if e["event"] == "page"] == [1]


@needs_qt
def test_the_eleventh_waiting_ask_fails(quick, monkeypatch):
    web, heard = quick, []
    bridge_app(web, heard, """
        let n = 0;
        const next = () => { n += 1; hallux.ask(n).catch(e => { R('refused', n + ' ' + e.message);
            done(); }); if (n < 11) setTimeout(next, 1050); };
        next();""")
    assert results(web, "chat", seconds=60)["refused"] == "11 hallux: 10 asks wait already"
    assert len([e for e in heard if e["event"] == "ask"]) == 10


@needs_qt
def test_data_too_big_or_not_json_is_refused(quick):
    web, heard = quick, []
    bridge_app(web, heard, """
        hallux.ask('x'.repeat(4000)).catch(e => R('big', e.message));
        hallux.emit(() => 1).catch(e => R('function', e.message));
        setTimeout(done, 300);""")
    found = results(web, "chat")
    assert found["big"] == "hallux: data is more than 3800 characters of JSON"
    assert found["function"] == "hallux: data must be JSON"
    with pytest.raises(web.WebError, match="data isn't JSON"):
        web.tell("chat", "{nope")
    with pytest.raises(web.WebError, match="more than 3800"):
        web.tell("chat", json.dumps("y" * 4000))


@needs_qt
def test_an_uncaught_error_arrives_with_its_file_and_line(quick):
    web, heard = quick, []
    web.connect(heard.append)
    page = "<script src=app.js></script>"
    script = "\n\nfunction go() { nothing.here(); }\nsetTimeout(go, 100);\nsetTimeout(go, 200);\n"
    web.open_page(app_disk(**{"index.html": page, "app.js": script}), "/home/user/chat")
    error = first(heard, "error")
    assert error["page"] == "chat" and error["file"] == "app.js" and error["line"] == 3
    assert "nothing is not defined" in error["message"]
    time.sleep(0.5)
    assert len([e for e in heard if e["event"] == "error"]) == 1   # one a second


@needs_qt
def test_reply_and_tell_need_an_open_page(quick):
    with pytest.raises(quick.WebError, match="no page called ghost is open"):
        quick.reply("ghost", 1, "1")
    with pytest.raises(quick.WebError, match="no page called ghost is open"):
        quick.tell("ghost", "1")


@needs_qt
def test_an_ask_nobody_hears_fails_at_its_time_limit(quick):
    web, heard = quick, []
    bridge_app(web, heard, "hallux.ask('anyone?').catch(e => { R('failed', e.message); done(); })",
               seconds_timeout=1)
    web.connect(lambda event: None)                   # Hallux drops it: nobody listens
    assert results(web, "chat")["failed"] == "hallux: no answer in 1 seconds"


# ---------------------------------------------------------------- web.toml

@needs_qt
def test_web_toml(web, tmp_path):
    missing = tmp_path / "none.toml"
    assert web.read_config(str(missing)) == {"ask_timeout_seconds": 120,
                                             "start_engine_at_boot": True}
    good = tmp_path / "good.toml"
    good.write_text("ask_timeout_seconds = 300\n")
    assert web.read_config(str(good)) == {"ask_timeout_seconds": 300,
                                          "start_engine_at_boot": True}
    good.write_text("start_engine_at_boot = false\n")
    assert web.read_config(str(good)) == {"ask_timeout_seconds": 120,
                                          "start_engine_at_boot": False}
    for text, told in (("ask_timeout_seconds = 5", "from 10 to 3600"),
                       ("ask_timeout_seconds = 3601", "from 10 to 3600"),
                       ("ask_timeout_seconds = 12.5", "whole number"),
                       ("ask_timeout_seconds = true", "whole number"),
                       ("start_engine_at_boot = 1", "must be true or false"),
                       ('start_engine_at_boot = "yes"', "must be true or false"),
                       ("colour = 1", "unknown key colour"),
                       ("this isn't toml", "can't be read")):
        bad = tmp_path / "bad.toml"
        bad.write_text(text)
        with pytest.raises(web.WebError, match=told):
            web.read_config(str(bad))


@needs_qt
def test_a_bad_web_toml_stops_the_addon_from_loading(tmp_path):
    folder = tmp_path / "addons"
    folder.mkdir()
    (folder / "web.py").write_text((app.ADDONS_FOLDER / "web.py").read_text())
    (folder / "web.toml").write_text("ask_timeout_seconds = 1\n")
    loaded, skipped = addons.load(folder, only=["web"])
    assert loaded == []
    assert skipped == {"web": "WebError: addons/web.toml: ask_timeout_seconds must be a whole "
                              "number from 10 to 3600"}


# ---------------------------------------------------------------- the manual

def manual_example(manual: str) -> tuple[str, dict]:
    """The example app of the manual: its folder, and its files by path."""
    example = manual.split("\nEXAMPLE\n", 1)[1]
    files, current = {}, None
    for line in example.splitlines():
        if line.startswith("  ") and current:
            files[current].append(line[2:])
        elif line.endswith(":") and " " not in line:
            current = line[:-1]
            files[current] = []
        else:
            current = None
    app_json = next(path for path in files if path.endswith("/app.json"))
    folder = posixpath.dirname(app_json)
    return folder, {(path if path.startswith("/") else f"{folder}/{path}"): "\n".join(lines)
                    for path, lines in files.items()}


@needs_qt
def test_the_manuals_example_works_as_it_says(quick, addon):
    web, heard, manual = quick, [], addon.manual
    folder, files = manual_example(manual)
    assert f'open_page("{folder}")' in manual
    listed = json.loads(files[f"{folder}/app.json"])
    assert {f"{folder}/{p}" for p in listed["files"]} == set(files) - {f"{folder}/app.json"}
    # The user's click, and a watch on what the page shows, added for the test.
    files[f"{folder}/index.html"] += (
        "<script>greet.click(); const seen = new Set();"
        "setInterval(() => { const t = out.textContent; if (seen.has(t)) return; seen.add(t);"
        " console.log('RESULT shows' + seen.size + ' ' + t);"
        " if (t === 'Hello!') console.log('RESULT done yes'); }, 20)</script>")
    web.connect(heard.append)
    assert web.open_page(Disk(**files), folder) == {"page": "hello"}
    asked = first(heard, "ask")
    told = re.search(r"A click brings\n(\{.*\}), and", manual, re.S).group(1)
    assert asked == json.loads(told.replace("\n", " "))
    page, number, data = re.search(r"reply\(\"(\w+)\", (\d+), '(.*?)'\)", manual).groups()
    assert web.reply(page, int(number), data) == {"ok": True}
    shown = results(web, "hello")
    assert shown["shows1"] == "thinking..." and shown["shows2"] == "Hello!"

