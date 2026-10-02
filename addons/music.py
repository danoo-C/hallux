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
song with bytebeat instruments, at 44100 Hz and 16 bits.
- play(path, loop) checks the score at that path, renders it and starts the sound, then
  returns: the sound goes on by itself. A song that is playing is replaced. loop=true starts
  the song again when it ends, until something stops it.
- stop() stops the sound.
- {"event": "finished"} is reported, once you listen with addon_listen, when a song that
  plays once ended by itself: not after stop() or a new play(), and never for a loop.
The addon defines no command: how the sound card shows inside the machine is your choice. A
score is an ordinary file: you write it, or the user does in nano. Print what play returns,
and its errors, the way a player would.

A WHOLE SCORE
```
BPM = 120
VOL = 255

INSTRUMENT pad 20000:
    env = min(t, 4000) * decay(t - dur, 6000) >> 12
    saw(p) * env * vel * VOL >> 32

INSTRUMENT pluck:
    sin(p) * decay(t, 5000) * vel >> 24

# one bar: 32 steps
PATTERN riff 32:
    (0, 8, C4, pluck, 130)
    (+, 8, G4, pluck, 130)
    (+, 16, C5, pluck, 130)
    (0, 32, C3 E3 G3, pad, 50)

SONG:
    (0, riff, 0, 2)    # two bars in C
    (+, riff, -5)      # one in G: 5 semitones down
    (+, riff)
    (96, 32, 0, VOL)   # the pads fade out over the last bar
```

THE FILE
- One thing per line. A line that isn't indented starts something: NAME = number,
  INSTRUMENT name:, PATTERN name: or SONG:. The indented lines below it belong to it.
- BPM is required. STEPS is the number of steps in a quarter note: 8 unless you set it, so a
  step is a 32nd note and a bar has 32. STEPS = 24 allows triplets. Any other NAME = number
  is a variable and its starting value.
- Everything is declared above the line that uses it. SONG: comes once, and last.
- Keywords are in upper case, and case counts. A name is letters, digits and _, starts with a
  letter and is declared once. Taken: an instrument's names and functions, BPM, STEPS, and
  note names. A named part belongs to its instrument: two can both have an env.
- A comment is a line that starts with #, indented or not, or follows the ) of an event.

EVENTS
(start, duration, value, target, velocity), counted in steps:
```
(0, 16, A4, lead)            # A4 on lead for 16 steps, at full velocity
(0, 16, A4, lead, 75)        # the same at velocity 75, of 0 to 255
(0, 32, C3 E3 G3, pad, 60)   # a chord: a voice for each note
(+, 8, G4, lead)             # + starts where the line above ended
(+4, 8, G4, lead)            # 4 steps after that: a rest
(8, 0, 128, VOL)             # VOL jumps to 128 at step 8
(8, 8, 0, VOL)               # VOL glides to 0 from step 8 to 16
```
- A note is a letter A to G, # or b if wanted, and the octave: C0 to B9. A4 is 440 Hz.
- A variable is a whole number, shared by all instruments that name it. A glide is a
  straight line. Two different changes to one variable at the same step are refused. A
  change that starts while another glides takes over.

PATTERNS AND THE SONG
A pattern's events count from its own start. PATTERN riff 32: gives it a length of 32 steps:
where a repeat, or a + after it, starts. Without a length it can't be repeated. A pattern
can place patterns declared above it. SONG: takes the same lines, and both take
(start, pattern, transpose, times):
```
(0, riff)           # the pattern, from step 0
(32, riff, -5)      # 5 semitones down; changes to variables stay as written
(64, riff, 0, 4)    # 4 times in a row; a + below starts after them
```
- Transposing also moves the patterns placed inside: the amounts add up.
- The order of the lines doesn't matter, the starts do. Lines at one step play together.
- The song ends at the last step anything reaches: an event's end, or a placed pattern's
  length. Tails ring out after it. A loop starts again there, with its variables reset.

INSTRUMENTS
One expression, computed for every sample of every note. Its result is the sample: -32768 to
32767, 0 is silence. Lines of name = expression above it are named parts, for the lines
below them. What it can use, beside declared variables:
```
t     samples since the note started, 44100 a second
p     the position in the wave, 65536 a cycle of the note's pitch; it never folds back
vel   the note's velocity, 0 to 255
dur   the note's length in samples, without its tail
key   the note's number: 69 for A4, one more per semitone
```
```
sin(x) saw(x) square(x) tri(x)   waves from -32767 to 32767; x is a position like p
noise(x)      looks random, -32768 to 32767; noise(t) is hiss
decay(x, h)   65536 while x is 0 or less, halving every h samples after that
min(a, b) max(a, b) abs(x)
```
- Operators: + - * / % & | ^ ~ << >> < <= > >= == != and a ? b : c, with C's precedence.
- Whole 64-bit numbers only: no 0.5, and no &&, ||, ! or **. / rounds toward zero, x / 0 is
  0, and >> keeps the sign.
- Multiply first, then shift or divide: >> 8 for each factor of 0 to 255, >> 16 for a decay,
  and 1 more for each doubling of the waves you add up.
- Two traps: >> binds looser than * and +, and & looser than -. Write x * vel * VOL >> 16,
  not x * vel >> 8 * VOL >> 8, and (p & 65535) - 32768.
- The sound card fades every note in and out, 2 and 5 ms: no clicks.
- A note ends at its duration. A number after the name is a tail, in samples:
  INSTRUMENT pad 20000: rings that long after it. The expression has to bring it down:
  decay(t - dur, h) is full while the note is held and halves every h samples after it.
- Adding to p bends the pitch: a wave makes the tone brighter, a decay makes it fall, and a
  slow sine, sin(t * 8) >> 2, is vibrato.

RECIPES
All were listened to. Alone, at velocity 255, each peaks at 45 to 100 percent.
```
# kick: play it at A1
INSTRUMENT kick:
    sin(p + (65536 - decay(t, 900)) * 5) * decay(t, 5000) * vel >> 24
# snare: play it at G3
INSTRUMENT snare:
    body = sin(p + (65536 - decay(t, 500)) * 2) * decay(t, 1500)
    hiss = noise(t) * decay(t, 2200)
    (body + hiss) * vel >> 25
# hi-hat: any note
INSTRUMENT hat:
    (noise(t) - noise(t - 1)) * decay(t, 600) * vel >> 25
# pad with a tail of 0.8 seconds
INSTRUMENT pad 35280:
    env = min(t, 4000) * decay(t - dur, 6000) >> 12
    (saw(p) + saw(p + (p >> 8)) + saw(p - (p >> 8))) * env * vel >> 26
# lead: half saw, half sine
INSTRUMENT lead:
    (saw(p) + sin(p)) * vel >> 9
# plucked sine
INSTRUMENT pluck:
    sin(p) * decay(t, 5000) * vel >> 24
# bell
INSTRUMENT bell:
    sin(p + (sin(p * 7 >> 1) * decay(t, 9000) >> 16)) * decay(t, 14000) * vel >> 24
# electric piano
INSTRUMENT piano:
    sin(p + (sin(p) * decay(t, 3000 + (96 - key) * 60) * vel >> 25)) * decay(t, 16000) * vel >> 24
```
A drum bar is kick on steps 0 and 16, snare on 8 and 24, hats between, each 4 steps.

WHAT PLAY RETURNS
{"ok": true, "seconds": 8.0, "peak": 98}: the length with its tails (of a loop, one round),
and the loudest point in percent of full scale. Under 50 is quiet: raise the velocities.
- "turned_down_to": 61: the mix was too loud, so the whole song was turned down to 61
  percent. Nothing is distorted. Lower the velocities for the balance you meant.
- "clipped": ["lead"]: that instrument's expression left 16 bits and was cut off: it
  distorts. Shift it further, or lower its velocity.
An error has every problem of the score, each with its line. Fix them all, then play again.

WRITING WELL
- Keep the file short: what repeats is a pattern, repeated and transposed.
- Voices that sound together add up, tails too. Choose velocities so that peak lands between
  50 and 100. In the score above, three pad notes at 50 under a pluck at 130 give 92.

LIMITS
A song of 300 seconds with its tails. A file of 64 KB. 10000 notes and changes once the
patterns are unfolded. Patterns 8 deep. An expression of 500 characters, nested 40 deep.
16 named parts. A tail of 441000 samples. 64 notes sounding at once. BPM 20 to 400, STEPS 1
to 96. A render that takes over 8 seconds fails: shorten the song."""


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
