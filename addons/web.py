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
import errno
import importlib.util
import json
import os
import posixpath
import queue
import re
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
OPEN_SECONDS = 5.0                     # to send an app of up to 10 MB and make its window
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


APP_FILE = "app.json"
APP_KEYS = {"name", "title", "size", "files"}
NAME = re.compile(r"[A-Za-z0-9_-]{1,30}")
TITLE_MAX = 100
SIZE_MIN, SIZE_MAX, SIZE_DEFAULT = (200, 150), (1600, 1000), [800, 600]
FILES_MAX = 200
FILE_PATH_MAX = 200
APP_BYTES_MAX = 10 * 1024 * 1024       # all of an app's files together; one file: the handle's 1 MB
PAGES_MAX = 2                          # windows open at a time; each takes some 700 MB
ENTRY = "index.html"
PROBLEMS_MAX = 1500                    # characters of the error that lists app.json's problems


def prompt() -> str:
    return """\
Web pages in windows of their own on the user's desktop: apps you write in HTML, CSS and
JavaScript. An app is a folder on the machine's disk, with an app.json that lists its files.

THE FUNCTIONS
- open_page(folder): opens the app in that folder in a window of its own. Returns
  {"page": name} at once; the page being ready arrives later as an event. If it is open
  already, its window comes to the front, unchanged: reload shows changes.
- reload(page): reads the app's files again and loads the page again.
- close_page(page): closes one window. stop(): closes them all.
At most 2 pages are open at a time.

APP.JSON
{"name": "chat", "title": "Kitty chat", "size": [800, 600],
 "files": ["index.html", "style.css", "app.js", "icons/send.svg"]}
- name: letters, digits, _ and -, at most 30; it is how the functions name the page.
- files: every file of the app, relative to its folder, index.html among them. A file not
  listed doesn't exist for the page. At most 200 files, 1 MB each, 10 MB in all, text only.
- The page starts at index.html and reaches its other files by relative paths.

EVENTS (call addon_listen("web") first)
{"event": "loaded", "page": name}, {"event": "failed", "page": name, "why": ...} and
{"event": "closed", "page": name} when the user closed the window.
"""


class WebError(Exception):
    """What the AI is told when the web engine can't do what was asked."""


# ---------------------------------------------------------------- the addon (inside Hallux)

def open_page(disk, folder: str) -> dict:
    """Open the app in this folder, which has an app.json, in a window of its own. Returns
    {"page": name} at once; "loaded" or "failed" arrives as an event."""
    app, files = read_app(disk, folder)
    name = app["name"]
    with _lock:
        link = _child()
        if name in link.pages:
            answer = link.ask({"cmd": "raise", "app": name})
            if "error" not in answer:
                return {"page": name, "open": "already"}
            link.pages.pop(name, None)                # the user closed it a moment ago
        if len(link.pages) >= PAGES_MAX:
            raise WebError(f"{PAGES_MAX} pages are open already "
                           f"({', '.join(sorted(link.pages))}): close one first")
        answer = link.ask({"cmd": "open", "app": name, "files": files,
                           "title": f"{app['title']} \u2014 hallux", "size": app["size"]},
                          OPEN_SECONDS)
        if "error" in answer:
            raise WebError(answer["error"])
        link.pages[name] = folder
    return {"page": name}


def reload(disk, page: str) -> dict:
    """Read the app's folder again, and load the page again: how it shows a change, or data
    you saved for it."""
    with _lock:
        folder = _folder_of(page)
    app, files = read_app(disk, folder)
    if app["name"] != page:
        raise WebError(f"the app in {folder} is called {app['name']} now, not {page}: "
                       f"close_page it and open_page it again")
    with _lock:
        link = _child()
        _folder_of(page)                              # still open
        answer = link.ask({"cmd": "reload", "app": page, "files": files}, OPEN_SECONDS)
        if "error" in answer:
            link.pages.pop(page, None)
            raise WebError(answer["error"])
    return {"ok": True}


def close_page(page: str) -> dict:
    """Close one page's window."""
    with _lock:
        _folder_of(page)
        link = _link
        link.pages.pop(page, None)
        answer = link.ask({"cmd": "close", "app": page})
    if "error" in answer:
        raise WebError(f"no page called {page[:40]} is open")
    return {"ok": True}


def stop() -> dict:
    """Close every web window. Nothing happens if none is open."""
    global _link
    with _lock:
        if _link is not None:
            _link.close()
            _link = None
    return {"ok": True}


EXPOSED = [open_page, reload, close_page, stop]


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
        _link.reader.join(3)                          # it tells the pages' failure first
        _link.close()
        _link = None
    if _link is None:
        _link = _Link()
    return _link


def _folder_of(page: str) -> str:
    """The folder of an open page. Called with _lock held."""
    link = _link if _link is not None and _link.alive() else None
    if link is None or page not in link.pages:
        raise WebError(f"no page called {str(page)[:40]} is open")
    return link.pages[page]


def _tell(event: dict) -> None:
    if _emit is not None:
        _emit(event)


def read_app(disk, folder: str) -> tuple[dict, dict]:
    """The app in this folder: its checked app.json, and the text of every file it lists."""
    if not isinstance(folder, str) or not folder.strip():
        raise WebError("folder must be the path of the app's folder")
    folder = folder.rstrip("/") or "/"
    app_path = posixpath.join(folder, APP_FILE)
    text = _read(disk, app_path)
    try:
        app = json.loads(text)
    except ValueError as e:
        raise WebError(f"{app_path} isn't JSON: {e}") from None
    app = check_app(app)
    files, total = {}, 0
    for path in app["files"]:
        files[path] = _read(disk, posixpath.join(folder, path))
        total += len(files[path].encode("utf-8"))
        if total > APP_BYTES_MAX:
            raise WebError(f"the app's files are more than {APP_BYTES_MAX // 1024 // 1024} MB "
                           f"in all")
    return app, files


def _read(disk, path: str) -> str:
    """One file, or an error that names it: ENOENT, EFBIG, not text."""
    try:
        return disk.read_text(path)
    except OSError as e:
        raise WebError(f"{path}: {errno.errorcode.get(e.errno, 'EIO')}") from None
    except ValueError:
        raise WebError(f"{path}: not text") from None


def check_app(app: object) -> dict:
    """app.json checked, with its defaults: every problem told at once."""
    if not isinstance(app, dict):
        raise WebError(f"{APP_FILE} must be a JSON object")
    problems = [f"unknown key {key[:30]!r}" for key in app if key not in APP_KEYS]
    name = app.get("name")
    if not (isinstance(name, str) and NAME.fullmatch(name)):
        problems.append("name must be 1 to 30 letters, digits, _ or -")
    title = app.get("title", name)
    if not (isinstance(title, str) and 0 < len(title) <= TITLE_MAX):
        problems.append(f"title must be text of 1 to {TITLE_MAX} characters")
    size = app.get("size", SIZE_DEFAULT)
    if not (isinstance(size, list) and len(size) == 2
            and all(isinstance(n, int) and not isinstance(n, bool) for n in size)
            and all(low <= n <= high for n, low, high in zip(size, SIZE_MIN, SIZE_MAX))):
        problems.append(f"size must be [width, height], from {SIZE_MIN[0]} x {SIZE_MIN[1]} "
                        f"to {SIZE_MAX[0]} x {SIZE_MAX[1]}")
    files = app.get("files")
    if not (isinstance(files, list) and 0 < len(files) <= FILES_MAX):
        problems.append(f"files must list 1 to {FILES_MAX} paths")
        files = []
    for path in files:
        if problem := _path_problem(path):
            problems.append(problem)
    if [f for f in files if isinstance(f, str)].count(ENTRY) == 0 and files:
        problems.append(f"files must have {ENTRY}: the page starts there")
    doubles = sorted({f for f in files if isinstance(f, str) and files.count(f) > 1})
    if doubles:
        problems.append(f"files lists twice: {', '.join(doubles)[:200]}")
    if problems:
        told = f"{APP_FILE} has {len(problems)} problem{'s' if len(problems) > 1 else ''}: "
        raise WebError((told + "; ".join(problems))[:PROBLEMS_MAX])
    return {"name": name, "title": title, "size": size, "files": files}


def _path_problem(path: object) -> str | None:
    if not isinstance(path, str) or not path:
        return "every file must be a path"
    shown = path[:60]
    if len(path) > FILE_PATH_MAX:
        return f"{shown}...: longer than {FILE_PATH_MAX} characters"
    if path.startswith("/") or "\\" in path:
        return f"{shown}: must be relative to the app's folder, with /"
    if ".." in path.split("/"):
        return f"{shown}: .. leaves the app's folder"
    if posixpath.normpath(path) != path or path == APP_FILE:
        return f"{shown}: not a plain path of a file"
    return None


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
        self.pages: dict = {}                         # name: its folder, for every open window
        self.closing = False                          # we end it: no page failed
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
                elif isinstance(message, dict):       # no question asked: something happened
                    if message.get("event") == "closed":
                        self.pages.pop(message.get("page"), None)
                    _tell(message)
        self.answers.put(None)
        if not self.closing and self.pages:           # it crashed: every window went with it
            why = self._why_stopped()
            for page in list(self.pages):
                _tell({"event": "failed", "page": page, "why": why})
            self.pages.clear()

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
        self.closing = True
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
    from PySide6.QtCore import QBuffer, QByteArray, QObject, Qt, Signal, Slot, QUrl
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
            if main_frame:
                self.window.refused = True            # Qt calls the load failed: it isn't
            return False

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            self.window.console.append({"level": level.name, "message": message[:500],
                                        "line": line, "source": source[:200]})
            del self.window.console[:-CONSOLE_KEPT]

    action = QWebEnginePage.WebAction
    LEAVING = (action.OpenLinkInNewWindow, action.OpenLinkInNewTab,
               action.OpenLinkInNewBackgroundTab, action.SavePage, action.ViewSource,
               action.DownloadLinkToDisk, action.DownloadImageToDisk,
               action.DownloadMediaToDisk, action.InspectElement)

    class View(QWebEngineView):
        """A window with no address bar and no menu; its right-click menu keeps nothing that
        leaves the page."""

        def __init__(self, window) -> None:
            super().__init__()
            self.window = window

        def contextMenuEvent(self, event) -> None:
            menu = self.createStandardContextMenu()
            for leaving in LEAVING:
                menu.removeAction(self.page().action(leaving))
            menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            menu.popup(event.globalPos())

        def closeEvent(self, event) -> None:
            super().closeEvent(event)
            if not self.window.closing:               # the user closed it
                windows.pop(self.window.app, None)
                say({"event": "closed", "page": self.window.app})
                self.window.close()

    class Window:
        """One app in a window of its own, with a profile of its own: nothing it stores
        outlives it, and no app sees another's."""

        def __init__(self, app_name: str, files: dict, title: str, size) -> None:
            self.app, self.files, self.closing, self.refused = app_name, files, False, False
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
            self.view = View(self)
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
            if not ok and self.refused:               # a navigation away, refused: still here
                self.refused = False
                return
            self.refused = False
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
                    "console": self.console, "off_the_record": self.profile.isOffTheRecord(),
                    "title": self.view.windowTitle()}

        def close(self) -> None:
            if self.closing:
                return
            self.closing = True
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
            if command not in ("close", "report", "raise", "reload", "as_user"):
                return {"error": f"the web engine doesn't know {str(command)[:40]}"}
            if name not in windows:
                return {"error": f"no page called {str(name)[:40]} is open"}
            window = windows[name]
            if command == "raise":
                window.view.showNormal()
                window.view.raise_()
                window.view.activateWindow()
                return {"ok": True}
            if command == "reload":
                window.files = message["files"]
                window.page.triggerAction(QWebEnginePage.WebAction.ReloadAndBypassCache)
                return {"ok": True}
            if command == "as_user":                  # for the tests: what the user's click does
                window.view.close()
                return {"ok": True}
            if command == "close":
                windows.pop(name).close()
                return {"ok": True}
            return window.report()                    # what a window saw; for tests and the log

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
