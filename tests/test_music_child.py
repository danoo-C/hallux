"""The music addon's child, python -m music_engine, and its player. No test makes a sound:
SDL's "disk" driver writes what would go to the sound card into a file. It runs at the speed
of real sound, so the songs here are shorter than half a second."""
import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="numpy isn't installed (pip install -e '.[music]')")
pytestmark = pytest.mark.skipif(importlib.util.find_spec("pygame") is None,
                                reason="pygame isn't installed (pip install -e '.[music]')")

from music_engine import render, score, song  # noqa: E402

ADDONS = Path(__file__).resolve().parent.parent / "addons"

# At 300 BPM a step is 1102.5 samples, so 4 steps are a tenth of a second.
BEEP = """\
BPM = 300

INSTRUMENT beep:
    sin(p) * vel >> 8

INSTRUMENT ring 3000:
    sin(p) * decay(t - dur, 800) * vel >> 24

SONG:
"""
SHORT = BEEP + "    (0, 4, A4, beep, 200)\n    (4, 4, E5, beep, 200)\n"        # 0.2 seconds
LONG = BEEP + "    (0, 16, C4 E4 G4, beep, 80)\n"                               # 0.4 seconds
RINGS = BEEP + "    (0, 4, A4, ring, 200)\n"                                    # 0.1 s, and a tail


def rendered(text, loop=False):
    read = score.read(text)
    return render.render(read, song.unfold(read), loop)


class Child:
    """The child on SDL's disk driver, and the line to it."""

    def __init__(self, folder, driver="disk", cwd=ADDONS, env=()):
        self.file = folder / "sound.raw"
        self.errors = folder / "errors.txt"
        with open(self.errors, "w") as errors:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "music_engine"], cwd=cwd, text=True,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                env=os.environ | {"SDL_AUDIODRIVER": driver, "SDL_DISKAUDIOFILE": str(self.file)}
                | dict(env))
        self.lines: queue.Queue = queue.Queue()          # every line of its output; None at its end
        self.events, self.asked = [], 0
        threading.Thread(target=self.read, daemon=True).start()
        self.hello = self.line()

    def read(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def line(self, seconds=10.0):
        """The next line of the child, as the message it has to be."""
        line = self.lines.get(timeout=seconds)
        return None if line is None else json.loads(line)

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def ask(self, **message):
        """Send a question, and return its answer. Events that come before it are kept."""
        self.asked += 1
        self.send(message | {"id": self.asked})
        while True:
            answer = self.line()
            if answer is not None and "id" not in answer:
                self.events.append(answer)
                continue
            assert answer is not None and answer.pop("id") == self.asked
            return answer

    def event(self, seconds=3.0):
        """The next event, or nothing if none comes in that time."""
        if self.events:
            return self.events.pop(0)
        try:
            return self.line(seconds)
        except queue.Empty:
            return None

    def quit(self):
        """End the child. Returns what it would have played, once the file is complete."""
        if self.process.poll() is None:
            self.send({"cmd": "quit"})
        self.process.stdin.close()
        assert self.process.wait(5) == 0
        return np.fromfile(self.file, dtype=np.int16)

    def kill(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()


@pytest.fixture
def child(tmp_path):
    started = Child(tmp_path)
    assert started.hello == {"id": 0, "ok": True}
    yield started
    started.kill()


def heard(sound, stream):
    """How many samples of `stream` the file holds from its first sound on, and what came
    after them. Both start with silence, so the first sample that isn't 0 lines them up."""
    assert sound.any(), "the file holds only silence"
    start = int(np.flatnonzero(sound)[0]) - int(np.flatnonzero(stream)[0])
    played = sound[start:start + len(stream)]
    different = np.flatnonzero(played != stream[:len(played)])
    count = int(different[0]) if len(different) else len(played)
    return count, sound[start + count:]


# ---------------------------------------------------------------- playing

def test_a_song_arrives_as_the_samples_that_were_rendered(child):
    song_ = rendered(SHORT)
    assert child.ask(cmd="play", text=SHORT, loop=False) == {"ok": True, "seconds": 0.2, "peak": 78}
    assert child.event() == {"event": "finished"}
    assert child.event(0.3) is None                                  # once
    count, rest = heard(child.quit(), song_.first)
    assert count == len(song_.first) == 8820                         # one for one
    assert not rest.any()                                            # and then silence


def test_loop_is_false_when_it_isnt_said(child):
    assert child.ask(cmd="play", text=SHORT) == {"ok": True, "seconds": 0.2, "peak": 78}
    assert child.event() == {"event": "finished"}


def test_a_loop_with_a_tail_goes_on_without_a_gap(child):
    """A song that loops is two sounds when tails ring past the end: the first round, and the
    later rounds with those tails mixed into their start."""
    loop = rendered(RINGS, loop=True)
    assert len(loop.first) == len(loop.again) == 4410 and (loop.first != loop.again).any()
    assert child.ask(cmd="play", text=RINGS, loop=True) == {"ok": True} | loop.report()
    time.sleep(1.3)                               # longer than what is queued at the start
    assert child.ask(cmd="stop") == {"ok": True}
    assert child.event(0.3) is None                                  # a loop never finishes
    stream = np.concatenate([loop.first] + [loop.again] * 400)
    count, rest = heard(child.quit(), stream)
    assert count >= len(loop.first) + 10 * len(loop.again)          # first, again, again, ...
    assert not rest.any()                                            # until it was stopped


def test_a_loop_without_tails_repeats_one_sound(child):
    once = rendered(SHORT)
    assert rendered(SHORT, loop=True).again is None
    child.ask(cmd="play", text=SHORT, loop=True)
    time.sleep(0.7)
    assert child.event(0.1) is None
    count, rest = heard(child.quit(), np.tile(once.first, 50))       # quit stops it too
    assert count >= 3 * len(once.first) and not rest.any()


def test_stop_cuts_the_song(child):
    whole = rendered(LONG)
    child.ask(cmd="play", text=LONG)
    time.sleep(0.1)
    assert child.ask(cmd="stop") == {"ok": True}
    assert child.ask(cmd="stop") == {"ok": True}                     # with nothing playing too
    assert child.event(0.6) is None                                  # stopped isn't finished
    count, rest = heard(child.quit(), whole.first)
    assert 1000 < count < len(whole.first) and not rest.any()


def test_a_new_play_replaces_the_song_that_is_playing(child):
    old, new = rendered(LONG), rendered(SHORT)
    child.ask(cmd="play", text=LONG)
    time.sleep(0.1)
    child.ask(cmd="play", text=SHORT)
    assert child.event() == {"event": "finished"}                    # of the new one only
    assert child.event(0.4) is None
    sound = child.quit()
    count, rest = heard(sound, old.first)
    assert 1000 < count < len(old.first)                             # the old one, cut off,
    assert (rest[:len(new.first)] == new.first).all()                # and the new one at once
    assert not rest[len(new.first):].any()


def test_the_old_song_plays_on_while_a_new_one_is_rendered(child):
    """A loop's next round has to be queued in time, also while the child is busy with a
    render that takes longer than what was queued when the loop started."""
    loop = rendered(RINGS, loop=True)
    notes = " ".join(f"{name}{octave}" for octave in range(1, 7)
                     for name in ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"))
    heavy = ("BPM = 120\nINSTRUMENT level:\n    saw(p) * 0 + 500\n"
             f"SONG:\n    (0, 480, {' '.join(notes.split()[:64])}, level)\n")     # 64 voices, 30 s
    child.ask(cmd="play", text=RINGS, loop=True)
    started = time.monotonic()
    assert child.ask(cmd="play", text=heavy) == {"ok": True, "seconds": 30.0, "peak": 98}
    took = time.monotonic() - started
    time.sleep(0.2)                               # the new song gets to sound
    child.ask(cmd="stop")
    count, rest = heard(child.quit(), np.concatenate([loop.first] + [loop.again] * 400))
    assert took > 0.8, "the render was too quick to show anything"
    assert count >= int((took - 0.3) * 44100)                        # no gap for all that time
    assert rest[:90].tolist() == [64 * (500 * i // 90) for i in range(90)]   # then the new one
    assert set(rest[90:2000].tolist()) == {32000}


def test_a_score_that_fails_its_check_changes_nothing(child):
    whole = rendered(LONG)
    child.ask(cmd="play", text=LONG)
    bad = BEEP + "    (0, 4, A4, beeb)\n    (4, 4, H5, beep)\n"
    assert child.ask(cmd="play", text=bad) == {
        "error": "line 10: unknown instrument or variable: beeb\n"
                 "line 11: beep is an instrument: its value is a note such as A4, not H5"}
    assert child.ask(cmd="play", text=BEEP + "    (0, 4, 0, nothing)\n")["error"].startswith(
        "line 10: unknown instrument")
    assert child.event() == {"event": "finished"}                    # what was playing played on
    count, rest = heard(child.quit(), whole.first)
    assert count == len(whole.first) and not rest.any()


def test_what_play_reports_about_a_loud_song(child):
    loud = BEEP.replace("sin(p) * vel >> 8", "sin(p) * 2") + "    (0, 4, A4 C5, beep)\n"
    assert child.ask(cmd="play", text=loud) == {
        "ok": True, "seconds": 0.1, "peak": 200, "turned_down_to": 49, "clipped": ["beep"]}


# ---------------------------------------------------------------- checking

def check(text, env=(), cwd=ADDONS, message=None, **more):
    """Start the child for a check of this score. Returns its one line as the answer it has
    to be, and the ended process: a check child ends by itself."""
    done = subprocess.run(
        [sys.executable, "-m", "music_engine", "check"], cwd=cwd, text=True, timeout=30,
        input=json.dumps({"text": text} | more) if message is None else message, capture_output=True,
        env=os.environ | {"SDL_AUDIODRIVER": "disk"} | dict(env))
    assert done.returncode == 0 and done.stdout.count("\n") == 1, (done.stdout, done.stderr)
    return json.loads(done.stdout), done


def test_a_check_answers_what_play_answers(child):
    loud = BEEP.replace("sin(p) * vel >> 8", "sin(p) * 2") + "    (0, 4, A4 C5, beep)\n"
    for text in (SHORT, LONG, RINGS, loud):
        assert check(text)[0] == child.ask(cmd="play", text=text), text
    assert check(SHORT)[0] == {"ok": True, "seconds": 0.2, "peak": 78}       # and no id
    assert check(loud)[0] == {
        "ok": True, "seconds": 0.1, "peak": 200, "turned_down_to": 49, "clipped": ["beep"]}


def test_a_check_of_a_loop_answers_what_play_answers_for_the_loop(child):
    once, loop = rendered(RINGS).report(), rendered(RINGS, loop=True).report()
    assert once != loop                                              # the tails are mixed in
    assert check(RINGS)[0] == check(RINGS, loop=False)[0] == {"ok": True} | once
    assert check(RINGS, loop=True)[0] == {"ok": True} | loop
    assert check(RINGS, loop=True)[0] == child.ask(cmd="play", text=RINGS, loop=True)
    child.ask(cmd="stop")


def test_a_check_of_a_score_with_mistakes_has_every_problem(child):
    bad = BEEP + "    (0, 4, A4, beeb)\n    (4, 4, H5, beep)\n"
    assert check(bad)[0] == child.ask(cmd="play", text=bad) == {
        "error": "line 10: unknown instrument or variable: beeb\n"
                 "line 11: beep is an instrument: its value is a note such as A4, not H5"}


def test_a_check_needs_no_sound_device_and_opens_none(tmp_path):
    answer, _ = check(SHORT, env={"SDL_AUDIODRIVER": "nosuchdriver"})
    assert answer == {"ok": True, "seconds": 0.2, "peak": 78}        # where a play can't start
    check(SHORT, env={"SDL_DISKAUDIOFILE": str(tmp_path / "sound.raw")})
    assert not (tmp_path / "sound.raw").exists()                     # nothing went to a card


def test_a_check_child_never_loads_pygame(tmp_path):
    """Checked in the child itself: there, whoever asks for pygame gets an error."""
    (tmp_path / "sitecustomize.py").write_text(
        "import sys\n\n\nclass NoPygame:\n"
        "    def find_spec(self, name, path, target=None):\n"
        "        if name.split('.')[0] == 'pygame':\n"
        "            raise ImportError('this child must not load pygame')\n"
        "        return None\n\n\nsys.meta_path.insert(0, NoPygame())\n")
    answer, done = check(SHORT, env={"PYTHONPATH": str(tmp_path)})
    assert answer == {"ok": True, "seconds": 0.2, "peak": 78} and done.stderr == ""
    playing = Child(tmp_path, env={"PYTHONPATH": str(tmp_path)})     # the child that plays does
    try:
        assert playing.hello is None and playing.process.wait(5) == 1
        assert "this child must not load pygame" in playing.errors.read_text()
    finally:
        playing.kill()


def test_a_check_of_what_is_no_message_is_an_answer():
    for message in ("", "not a message", "[1, 2]", '{"text": 5}', '{"score": "BPM = 120"}',
                    '{"text": "BPM = 120", "loop": "yes"}'):
        assert check("", message=message)[0] == {
            "error": "addon bug: check takes a text, and true or false for loop"}


def test_a_bug_in_a_check_is_an_answer_and_not_a_crash(tmp_path):
    shutil.copytree(ADDONS / "music_engine", tmp_path / "music_engine")
    with open(tmp_path / "music_engine" / "render.py", "a") as broken:
        broken.write("\n\ndef render(*args):\n    raise RuntimeError('the mixer melted')\n")
    answer, done = check(SHORT, cwd=tmp_path)
    assert answer == {"error": "addon bug: RuntimeError: the mixer melted"}
    assert "Traceback" in done.stderr                                # for whoever looks


def test_a_check_keeps_its_line_clear_of_what_a_library_prints(tmp_path):
    (tmp_path / "sitecustomize.py").write_text(
        "import os, sys\n\n\nclass Chatty:\n"
        "    def find_spec(self, name, path, target=None):\n"
        "        if name == 'numpy':\n"
        "            print('a library says hello', flush=True)\n"
        "            os.write(1, b'and so does its C code\\n')\n"
        "        return None\n\n\nsys.meta_path.insert(0, Chatty())\n")
    answer, done = check(SHORT, env={"PYTHONPATH": str(tmp_path)})
    assert answer == {"ok": True, "seconds": 0.2, "peak": 78}        # the one line, unharmed
    assert "a library says hello" in done.stderr and "and so does its C code" in done.stderr


# ---------------------------------------------------------------- the messages

def test_no_sound_device(tmp_path):
    child = Child(tmp_path, driver="nosuchdriver")
    assert child.hello == {"id": 0, "error": "no sound device: Audio target 'nosuchdriver' "
                                             "not available"}
    assert child.process.wait(5) == 1 and child.line() is None


def test_a_message_the_child_doesnt_know_is_an_error(child):
    assert child.ask(cmd="rewind") == {"error": "unknown message: rewind"}
    assert child.ask(command="play") == {"error": "unknown message: None"}
    assert child.ask(cmd="play") == {
        "error": "addon bug: play takes a text, and true or false for loop"}
    assert child.ask(cmd="play", text=SHORT, loop="yes")["error"].startswith("addon bug: play")
    child.send("not a message")                                      # neither is an answer
    child.process.stdin.write("{nor is this\n")
    assert child.ask(cmd="stop") == {"ok": True}                     # and the child lives on


def test_a_bug_in_the_chain_is_an_answer_and_not_a_crash(tmp_path):
    shutil.copytree(ADDONS / "music_engine", tmp_path / "music_engine")
    with open(tmp_path / "music_engine" / "render.py", "a") as broken:
        broken.write("\n\ndef render(*args):\n    raise RuntimeError('the mixer melted')\n")
    child = Child(tmp_path, cwd=tmp_path)
    try:
        assert child.ask(cmd="play", text=SHORT) == {
            "error": "addon bug: RuntimeError: the mixer melted"}
        assert child.ask(cmd="stop") == {"ok": True}                 # it lives on
        child.quit()
        assert "Traceback" in child.errors.read_text()               # for whoever looks
    finally:
        child.kill()


def test_quit_ends_the_child_and_so_does_closing_its_input(tmp_path):
    for end in ("quit", "close"):
        folder = tmp_path / end
        folder.mkdir()
        child = Child(folder)
        child.ask(cmd="play", text=LONG, loop=True)
        time.sleep(0.3)
        if end == "quit":
            child.send({"cmd": "quit"})
        else:
            child.process.stdin.close()                              # Hallux went away
        assert child.process.wait(5) == 0 and child.line() is None
        sound = np.fromfile(child.file, dtype=np.int16)
        count, rest = heard(sound, np.tile(rendered(LONG).first, 20))
        assert 1000 < count < 44100 and not rest.any()               # the sound stopped with it


def test_what_a_library_prints_cant_garble_the_line(tmp_path):
    """The child keeps its own copy of the output for the messages, and points the ordinary
    output at the error output."""
    (tmp_path / "sitecustomize.py").write_text(
        "import os, sys\n\n\nclass Chatty:\n"
        "    def find_spec(self, name, path, target=None):\n"
        "        if name == 'pygame':\n"
        "            print('a library says hello', flush=True)\n"
        "            os.write(1, b'and so does its C code\\n')\n"
        "        return None\n\n\nsys.meta_path.insert(0, Chatty())\n")
    child = Child(tmp_path, env={"PYTHONPATH": str(tmp_path)})
    try:
        assert child.hello == {"id": 0, "ok": True}                  # the first line, unharmed
        assert child.ask(cmd="stop") == {"ok": True}
        child.quit()
        assert child.line() is None                                  # nothing else came
        printed = child.errors.read_text()
        assert "a library says hello" in printed and "and so does its C code" in printed
    finally:
        child.kill()
