"""A sound card: plays score files with bytebeat instruments.

The addon is a bridge and nothing more: it reads the score file through Hallux's disk handle,
hands the text to a child process, and turns the child's answers into what the AI gets. The
child, the package music_engine beside this file, checks the score, renders it with numpy and
plays it through pygame's mixer (docs/addon-music.md).

Hallux never imports numpy or pygame; it only checks that they are installed. The child
starts with the first play(), stays for the next ones, and ends with stop(). The two exchange
one line of JSON per message, over the child's stdin and stdout, as addons/window.py does. A
line from the child that answers no question is an event: a song has ended by itself.
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

for _needed in ("numpy", "pygame"):
    if importlib.util.find_spec(_needed) is None:
        raise ModuleNotFoundError(f"No module named '{_needed}'")

FOLDER = os.path.dirname(os.path.abspath(__file__))   # the child finds its package here
CHILD = [sys.executable, "-m", "music_engine"]
START_SECONDS = 8.0                    # for the child to load numpy and open the mixer
RENDER_SECONDS = 8.0                   # for a song to be rendered and started: less than the
                                       # 10 seconds Hallux gives a call, so this one says why
QUIT_SECONDS = 2.0                     # for the child to end by itself, before it is ended
SCORE_KB = 64                          # the biggest score file (music_engine/limits.py)


def prompt() -> str:
    return """\
A real sound card. It plays score files: text files on the machine's disk that describe a
song with bytebeat instruments.
- play(path, loop) checks the score at that path, renders it and starts the sound. It returns
  at once and the sound goes on by itself. A song that is playing is replaced. With loop=true
  the song starts again when it ends, until something stops it.
- stop() stops the sound.
play returns what it measured: seconds, the length of the song, and peak, its loudest point
in percent of full scale. A score with mistakes isn't played: the error has every problem
with its line. Print it the way a player would.
The sound card reports one event, once you listen to it with addon_listen:
- {"event": "finished"}: a song that plays once reached its end by itself. It isn't sent
  after stop(), after a new play(), or for a song that loops."""


class MusicError(Exception):
    """What the AI is told when a song can't be played."""


def play(disk, path: str, loop: bool = False) -> dict:
    """Play the score file at this path on the machine's disk. A song that is playing is
    replaced. loop=true plays it again and again."""
    text = disk.read_text(path)
    if len(text.encode("utf-8")) > SCORE_KB * 1024:
        raise MusicError(f"the score is bigger than {SCORE_KB} KB")
    with _lock:
        link = _open()
        try:
            answer = link.ask({"cmd": "play", "text": text, "loop": loop}, RENDER_SECONDS)
        except _TooSlow:
            _close()                                  # the sound goes with it
            raise MusicError("the song took too long to render") from None
        except MusicError:
            _close()                                  # the next play starts a new child
            raise
    if "error" in answer:
        raise MusicError(answer["error"])
    return answer


def stop() -> dict:
    """Stop the sound. Nothing happens if nothing is playing."""
    link = _link
    if not _lock.acquire(timeout=0.2):                # a play is waiting for its render:
        if link is not None:                          # end that, and it lets go of the lock
            link.end()
        _lock.acquire()
    try:
        _close()
    finally:
        _lock.release()
    return {"ok": True}


EXPOSED = [play, stop]


def connect(emit) -> None:
    """Hallux hands over emit: what the sound card reports by itself goes through it."""
    global _emit
    _emit = emit


_lock = threading.Lock()               # one question at a time
_link = None                           # the pipe to the child, while there is one
_emit = None                           # where events go, once Hallux has connected


def _open() -> "_Link":
    """The link to the child, starting one if none is running."""
    global _link
    if _link is None or not _link.alive():
        _close()
        _link = _Link()
    return _link


def _close() -> None:
    global _link
    link, _link = _link, None
    if link is not None:
        link.close()


class _TooSlow(Exception):
    """The child didn't answer in time."""


class _Link:
    """The addon's end of the pipe: it starts one child and talks to it."""

    def __init__(self) -> None:
        self.errors = tempfile.TemporaryFile()        # whatever the child or SDL prints
        self.ended = False                            # by us, not by a crash
        self.process = subprocess.Popen(
            CHILD, cwd=FOLDER, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.errors, text=True,
            env=os.environ | {"PYGAME_HIDE_SUPPORT_PROMPT": "1"})
        self.answers: queue.Queue = queue.Queue()     # dictionaries; None once the child is gone
        self.asked = 0
        self.reader = threading.Thread(target=self._read, name="music answers", daemon=True)
        self.reader.start()
        try:
            hello = self._answer(0, START_SECONDS)    # the child speaks first
        except _TooSlow:
            self.close()
            raise MusicError("the sound card didn't start") from None
        except MusicError:
            self.close()
            raise
        if "error" in hello:                          # "no sound device: ..."
            self.close()
            raise MusicError(hello["error"])

    def _read(self) -> None:
        for line in self.process.stdout:
            with contextlib.suppress(ValueError):
                message = json.loads(line)
                if isinstance(message, dict) and "id" in message:
                    self.answers.put(message)
                elif isinstance(message, dict) and _emit is not None:
                    _emit(message)                    # no question asked: something happened
        self.answers.put(None)

    def alive(self) -> bool:
        return self.process.poll() is None

    def ask(self, message: dict, seconds: float) -> dict:
        self.asked += 1
        try:
            self.process.stdin.write(json.dumps(message | {"id": self.asked}) + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError):                 # the pipe broke, or is closed
            raise MusicError(self._why_stopped()) from None
        return self._answer(self.asked, seconds)

    def _answer(self, id: int, seconds: float) -> dict:
        """The answer to message `id`. One that arrives after its question gave up is dropped."""
        deadline = time.monotonic() + seconds
        while True:
            try:
                answer = self.answers.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                raise _TooSlow from None
            if answer is None:
                self.answers.put(None)                # it stays gone for the next question
                raise MusicError(self._why_stopped())
            if answer.get("id") == id:
                return {key: value for key, value in answer.items() if key != "id"}

    def _why_stopped(self) -> str:
        """The child is gone. If it crashed, the last thing it printed says why."""
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.process.wait(1)
        self.errors.seek(0)
        printed = self.errors.read().decode("utf-8", "replace").strip().splitlines()
        if self.ended or self.process.returncode in (0, None) or not printed:
            return "the sound card stopped"
        return f"the sound card stopped: it crashed ({printed[-1].strip()[:200]})"

    def end(self) -> None:
        """End the child at once, without asking it to."""
        self.ended = True
        with contextlib.suppress(OSError):
            self.process.kill()

    def close(self) -> None:
        self.ended = True
        if self.alive():
            with contextlib.suppress(OSError, ValueError):
                self.process.stdin.write('{"cmd": "quit"}\n')
                self.process.stdin.flush()
        with contextlib.suppress(OSError, ValueError):
            self.process.stdin.close()                # the child also quits when this closes
        try:
            self.process.wait(QUIT_SECONDS)
        except subprocess.TimeoutExpired:             # still rendering, or stuck
            self.process.kill()
            self.process.wait()
        self.reader.join(1)
        self.process.stdout.close()
        self.errors.close()
