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

# Qt, Chromium and Mesa print much; it goes to a file (see _Link), and these keep it small.
QUIET = {
    "QT_LOGGING_RULES": "*.debug=false;*.info=false;*.warning=false",
    "QTWEBENGINE_CHROMIUM_FLAGS": "--log-level=3",        # Chromium: fatal errors only
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
    from PySide6.QtCore import QObject, Signal, Slot
    from PySide6.QtWidgets import QApplication

    app = QApplication(["hallux-web"])
    app.setQuitOnLastWindowClosed(False)              # windows come and go; Hallux decides

    class Engine(QObject):
        """Answers Hallux, in Qt's own thread: messages arrive through a signal."""
        arrived = Signal(object)

        @Slot(object)
        def take(self, message) -> None:
            if message is None or message.get("cmd") == "quit":
                app.quit()
                return
            try:
                answer = self.answer(message)
            except Exception as e:                    # a bug of ours: tell it, keep running
                answer = {"error": f"the web engine failed: {type(e).__name__}: {e}"[:300]}
            say(answer | {"seq": message.get("seq")})

        def answer(self, message: dict) -> dict:
            command = message.get("cmd")
            if command == "ping":
                return {"ok": True}
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
