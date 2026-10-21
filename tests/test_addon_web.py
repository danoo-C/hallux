"""The web addon, addons/web.py. No test needs a display: Qt runs offscreen.

Skipped without PySide6 (pip install -e '.[web]'), except the test that the addon is then
skipped cleanly."""
import importlib.util
import http.server
import json
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
    assert list(addon.functions) == ["open_page", "reload", "close_page", "stop"]
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

