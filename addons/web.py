"""Web pages in windows of their own: apps the AI writes in HTML, CSS and JavaScript.

This file is both sides of the addon, like addons/gui.py. Imported by Hallux, it's the
addon: it talks to one child process, started when it's first needed. Run as
`python web.py --child`, it's that child: one Qt application that holds every web window.
The two exchange one line of JSON per message, over the child's stdin and stdout. A line
from the child that answers no question is an event.

Qt stays in the child, never in Hallux: Hallux only checks that PySide6 is installed. The
design is in docs/web-addon/, the plan in docs/plans/web-addon/. Hallux's own code knows
nothing of this addon: it uses only what every addon has.

Nothing here calls the built-in open().
"""
import contextlib
import importlib.util
import json
import os
import posixpath
import queue
import subprocess
import sys
import tempfile
import threading
import time

if importlib.util.find_spec("PySide6") is None:
    raise ModuleNotFoundError("No module named 'PySide6'")

CHILD = [sys.executable, os.path.abspath(__file__), "--child"]
START_SECONDS = 9.0                    # for the child to say hello; Hallux gives a call 10
ANSWER_SECONDS = 2.0                   # for the child to answer one message
CRASH_LINE_MAX = 200                   # characters of the child's last line, in an error
SYSTEM_FONTS = "/etc/fonts/fonts.conf"

# A second wall, under the child's interceptor: some connections never pass it (a
# preconnect opens a socket and sends nothing). Every connection Chromium opens goes to a
# SOCKS5 proxy that isn't there, loopback included, and SOCKS5 leaves names to the proxy, so
# none is looked up; WebRTC may use no UDP of its own. They go through the environment:
# Chromium ignored them on the application's command line.
CHROMIUM_WALL = ["--proxy-server=socks5://127.0.0.1:1", "--proxy-bypass-list=<-loopback>",
                 "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"]

# Qt, Chromium and Mesa print much; it goes to a file (see _Link), and these keep it small.
# The flags replace any the user set: none of theirs can turn a wall off.
QUIET = {
    "QT_LOGGING_RULES": "*.debug=false;*.info=false;*.warning=false",
    "QTWEBENGINE_CHROMIUM_FLAGS": " ".join(["--log-level=3", *CHROMIUM_WALL]),
    "EGL_LOG_LEVEL": "fatal",
    "LIBGL_DEBUG": "quiet",
}


def prompt() -> str:
    return """\
Web pages in windows of their own on the user's desktop: apps you write in HTML, CSS and
JavaScript. Not ready yet: for now nothing can be opened.

THE FUNCTIONS
- stop(): closes every web window. Nothing happens if none is open.
"""


class WebError(Exception):
    """What the AI is told when the web engine can't do what was asked."""


# ---------------------------------------------------------------- the addon (inside Hallux)

def stop() -> dict:
    """Close every web window. Nothing happens if none is open."""
    global _link
    with _lock:
        if _link is not None:
            _link.close()
            _link = None
    return {"ok": True}


EXPOSED = [stop]


def connect(emit) -> None:
    """Hallux hands over emit: what happens in a page goes through it."""
    global _emit
    _emit = emit


_lock = threading.Lock()               # one question at a time
_link = None                           # the pipe to the child, once something needed it
_emit = None                           # where events go, once Hallux has connected


def _child() -> "_Link":
    """The link to the child: started by the first call that needs it, and started again
    if it died. Called with _lock held."""
    global _link
    if _link is not None and not _link.alive():
        _link.close()
        _link = None
    if _link is None:
        _link = _Link()
    return _link


def child_env() -> dict:
    """The environment the child runs in: Hallux's, made quiet, with the system's fonts."""
    env = os.environ | QUIET
    if "FONTCONFIG_FILE" not in env and os.path.exists(SYSTEM_FONTS):
        # Chromium in the PySide6 wheel may not know where the system keeps fontconfig's
        # file ("Cannot load default config file" in the check); this tells it.
        env["FONTCONFIG_FILE"] = SYSTEM_FONTS
    return env


class _Link:
    """The addon's end of the pipe to the child: it starts the child and talks to it."""

    def __init__(self) -> None:
        self.errors = tempfile.TemporaryFile()        # whatever the child, Qt or Chromium print
        self.process = subprocess.Popen(
            CHILD, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors, text=True,
            env=child_env())
        self.answers: queue.Queue = queue.Queue()     # dictionaries; None once the child is gone
        self.asked = 0
        self.reader = threading.Thread(target=self._read, name="web child", daemon=True)
        self.reader.start()
        try:
            hello = self._answer(0, START_SECONDS)    # the child speaks first
        except WebError as e:
            self.close()
            raise WebError(str(e).replace("stopped", "didn't start")) from None
        if "error" in hello:
            self.close()
            raise WebError(hello["error"])

    def _read(self) -> None:
        for line in self.process.stdout:
            with contextlib.suppress(ValueError):
                message = json.loads(line)
                if isinstance(message, dict) and "seq" in message:
                    self.answers.put(message)
                elif isinstance(message, dict) and _emit is not None:
                    _emit(message)                    # no question asked: something happened
        self.answers.put(None)

    def alive(self) -> bool:
        return self.process.poll() is None

    def ask(self, message: dict, seconds: float = ANSWER_SECONDS) -> dict:
        self.asked += 1
        try:
            self.process.stdin.write(json.dumps(message | {"seq": self.asked}) + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError):                 # the pipe broke, or is closed
            raise WebError(self._why_stopped()) from None
        return self._answer(self.asked, seconds)

    def _answer(self, seq: int, seconds: float) -> dict:
        """The answer to message `seq`. One that arrives after its question gave up is dropped."""
        deadline = time.monotonic() + seconds
        while True:
            try:
                answer = self.answers.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                if seq == 0:
                    raise WebError("the web engine didn't start") from None
                raise WebError("the web engine doesn't answer") from None
            if answer is None:
                self.answers.put(None)                # it stays gone for the next question
                raise WebError(self._why_stopped())
            if answer.get("seq") == seq:
                return {key: value for key, value in answer.items() if key != "seq"}

    def _why_stopped(self) -> str:
        """The child ended: if it crashed, the last thing it printed says why."""
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.process.wait(1)
        self.errors.seek(0)
        printed = self.errors.read().decode("utf-8", "replace").strip().splitlines()
        stopped = "the web engine stopped"
        if self.process.returncode in (0, None) or not printed:
            return stopped
        return f"{stopped}: it crashed ({printed[-1].strip()[:CRASH_LINE_MAX]})"

    def close(self) -> None:
        if self.alive():
            with contextlib.suppress(OSError, ValueError):
                self.process.stdin.write('{"cmd": "quit"}\n')
                self.process.stdin.flush()
        with contextlib.suppress(OSError, ValueError):
            self.process.stdin.close()                # the child also quits when this closes
        try:
            self.process.wait(3)                      # Chromium's processes take a moment
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.reader.join(1)
        self.process.stdout.close()
        self.errors.close()


# ---------------------------------------------------------------- the engine (the child)

SCHEME = "hallux"
FREE_SCHEMES = ("data", "blob")        # made by the page itself; they reach no network
CONTENT_TYPES = {"html": "text/html", "htm": "text/html", "css": "text/css",
                 "js": "text/javascript", "mjs": "text/javascript", "svg": "image/svg+xml",
                 "json": "application/json", "txt": "text/plain", "md": "text/markdown"}
BLOCKED_KEPT = 50                      # blocked addresses a window remembers, for report
BLOCKED_LOGGED = 5                     # of them, written to the child's log
CONSOLE_KEPT = 200                     # lines of a page's console a window remembers
DEFAULT_SIZE = (900, 650)


def content_type(path: str) -> str:
    """The type a file is served with, from its extension; text/plain for the rest."""
    kind = CONTENT_TYPES.get(path.rpartition(".")[2].lower(), "text/plain")
    return f"{kind}; charset=utf-8"


def file_key(path: str) -> str:
    """The file a decoded URL path names, as an app lists it: "/a/../b.js" is "b.js". It never
    climbs out of the app: the path is made absolute before .. is taken away."""
    key = posixpath.normpath("/" + path).lstrip("/")
    return "index.html" if key in ("", ".") else key


def child_main() -> int:
    """The child process: one Qt application, for every web window, until Hallux goes away."""
    line_out = os.fdopen(os.dup(1), "w")              # the line to Hallux
    os.dup2(2, 1)                                     # a library that prints can't garble it

    def say(message: dict) -> None:
        line_out.write(json.dumps(message) + "\n")
        line_out.flush()

    for key, value in child_env().items():            # when started by hand, too
        os.environ.setdefault(key, value)

    from PySide6 import QtWebEngineWidgets  # noqa: F401  (Qt wants it before the application)
    from PySide6.QtCore import QBuffer, QByteArray, QObject, Signal, Slot, QUrl
    from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
                                         QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestJob,
                                         QWebEngineUrlScheme, QWebEngineUrlSchemeHandler)
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    scheme = QWebEngineUrlScheme(SCHEME.encode())     # before the application, as Qt demands
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme
                    | QWebEngineUrlScheme.Flag.FetchApiAllowed
                    | QWebEngineUrlScheme.Flag.CorsEnabled)
    QWebEngineUrlScheme.registerScheme(scheme)

    app = QApplication(["hallux-web"])
    app.setQuitOnLastWindowClosed(False)              # windows come and go; Hallux decides
    attribute = QWebEngineSettings.WebAttribute
    OFF = (attribute.LocalContentCanAccessRemoteUrls, attribute.LocalContentCanAccessFileUrls,
           attribute.JavascriptCanOpenWindows, attribute.PluginsEnabled,
           attribute.DnsPrefetchEnabled, attribute.AllowRunningInsecureContent,
           attribute.JavascriptCanAccessClipboard)

    class Wall(QWebEngineUrlRequestInterceptor):
        """Sees every request of one window, navigation included: only its own app passes."""

        def __init__(self, window) -> None:
            super().__init__()
            self.window = window

        def interceptRequest(self, info) -> None:
            url = info.requestUrl()
            if not self.window.allows(url):
                info.block(True)
                self.window.blocked_one(url)

    class Files(QWebEngineUrlSchemeHandler):
        """Serves one window's app from the files the addon sent: hallux://<app>/<path>."""

        def __init__(self, window) -> None:
            super().__init__()
            self.window = window

        def requestStarted(self, job) -> None:
            url = job.requestUrl()
            key = file_key(url.path(QUrl.ComponentFormattingOption.FullyDecoded))
            files = self.window.files
            if url.host() != self.window.app:
                job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)
                return
            if key not in files and f"{key}/index.html" in files:
                key = f"{key}/index.html"
            if key not in files:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return
            body = QBuffer(job)                       # lives as long as the job
            body.setData(QByteArray(files[key].encode("utf-8")))
            job.reply(content_type(key).encode(), body)

    class Page(QWebEnginePage):
        def __init__(self, profile, window) -> None:
            super().__init__(profile)
            self.window = window

        def createWindow(self, kind):                 # window.open, target=_blank: nothing
            return None

        def acceptNavigationRequest(self, url, kind, main_frame) -> bool:
            if self.window.allows(url):
                return True
            self.window.blocked_one(url)
            return False

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            self.window.console.append({"level": level.name, "message": message[:500],
                                        "line": line, "source": source[:200]})
            del self.window.console[:-CONSOLE_KEPT]

    class Window:
        """One app in a window of its own, with a profile of its own: nothing it stores
        outlives it, and no app sees another's."""

        def __init__(self, app_name: str, files: dict, title: str, size) -> None:
            self.app, self.files = app_name, files
            self.blocked, self.blocked_urls, self.console = 0, [], []
            self.profile = QWebEngineProfile()        # no storage name: off the record
            self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
            self.profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            for setting in OFF:
                self.profile.settings().setAttribute(setting, False)
            self.wall, self.handler = Wall(self), Files(self)
            self.profile.setUrlRequestInterceptor(self.wall)
            self.profile.installUrlSchemeHandler(SCHEME.encode(), self.handler)
            self.profile.downloadRequested.connect(lambda item: item.cancel())
            self.page = Page(self.profile, self)
            self.page.permissionRequested.connect(lambda permission: permission.deny())
            self.page.fullScreenRequested.connect(lambda request: request.reject())
            self.page.renderProcessTerminated.connect(self._crashed)
            self.page.loadFinished.connect(self._loaded)
            self.view = QWebEngineView()
            self.view.setPage(self.page)
            self.view.setWindowTitle(title)
            self.view.resize(*size)
            self.view.show()
            self.page.load(QUrl(f"{SCHEME}://{app_name}/"))

        def allows(self, url) -> bool:
            if url.scheme() in FREE_SCHEMES:
                return True
            return url.scheme() == SCHEME and url.host() == self.app

        def blocked_one(self, url) -> None:
            self.blocked += 1
            shown = url.toString()[:200]
            if len(self.blocked_urls) < BLOCKED_KEPT:
                self.blocked_urls.append(shown)
            if self.blocked <= BLOCKED_LOGGED:
                print(f"web {self.app}: blocked {shown}", file=sys.stderr, flush=True)

        def _loaded(self, ok: bool) -> None:
            if ok:
                say({"event": "loaded", "page": self.app})
            else:
                say({"event": "failed", "page": self.app, "why": "the page didn't load"})

        def _crashed(self, status, code: int) -> None:
            if status == QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
                return
            say({"event": "failed", "page": self.app,
                 "why": f"the page's process ended ({status.name}, {code})"})

        def report(self) -> dict:
            return {"blocked": self.blocked, "blocked_urls": self.blocked_urls,
                    "console": self.console, "off_the_record": self.profile.isOffTheRecord()}

        def close(self) -> None:
            self.page.loadFinished.disconnect(self._loaded)       # closing is no failure
            self.page.renderProcessTerminated.disconnect(self._crashed)
            self.view.close()
            self.view.setPage(None)
            self.page.deleteLater()                   # the page before its profile, always
            self.view.deleteLater()
            self.profile.deleteLater()

    windows: dict = {}                                # app name: its Window

    class Engine(QObject):
        """Answers Hallux, in Qt's own thread: messages arrive through a signal."""
        arrived = Signal(object)

        @Slot(object)
        def take(self, message) -> None:
            if message is None or message.get("cmd") == "quit":
                for window in windows.values():
                    window.close()
                app.quit()
                return
            try:
                answer = self.answer(message)
            except Exception as e:                    # a bug of ours: tell it, keep running
                answer = {"error": f"the web engine failed: {type(e).__name__}: {e}"[:300]}
            say(answer | {"seq": message.get("seq")})

        def answer(self, message: dict) -> dict:
            command, name = message.get("cmd"), message.get("app")
            if command == "ping":
                return {"ok": True}
            if command == "open":                     # the addon checked what it sends
                if name in windows:
                    windows.pop(name).close()
                windows[name] = Window(name, message["files"], message.get("title", name),
                                       message.get("size", DEFAULT_SIZE))
                return {"ok": True}
            if command in ("close", "report") and name not in windows:
                return {"error": f"no page called {str(name)[:40]} is open"}
            if command == "close":
                windows.pop(name).close()
                return {"ok": True}
            if command == "report":                   # what a window saw; for tests and the log
                return windows[name].report()
            return {"error": f"the web engine doesn't know {str(command)[:40]}"}

    engine = Engine()
    engine.arrived.connect(engine.take)               # queued: from the reader to Qt's thread

    def listen() -> None:
        # Read the descriptor itself: a thread stuck inside sys.stdin can crash Python's exit.
        waiting = b""
        while chunk := os.read(0, 65536):
            *lines, waiting = (waiting + chunk).split(b"\n")
            for line in lines:
                with contextlib.suppress(ValueError):
                    message = json.loads(line)
                    if isinstance(message, dict):
                        engine.arrived.emit(message)
        engine.arrived.emit(None)                     # Hallux is gone

    threading.Thread(target=listen, daemon=True).start()
    say({"seq": 0, "ok": True})
    return app.exec()


if __name__ == "__main__":
    if "--child" not in sys.argv:
        sys.exit("web.py is a Hallux addon. Hallux starts its engine itself, with --child.")
    sys.exit(child_main())
