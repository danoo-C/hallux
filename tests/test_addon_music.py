"""The music addon, addons/music.py: the bridge between Hallux and the child that plays. No
test makes a sound: the real child runs on SDL's "disk" driver, which writes what would go to
the sound card into a file, and stand-in children do what a real one doesn't do on demand."""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import jsonschema
import pytest

np = pytest.importorskip("numpy", reason="numpy isn't installed (pip install -e '.[music]')")
pytestmark = pytest.mark.skipif(importlib.util.find_spec("pygame") is None,
                                reason="pygame isn't installed (pip install -e '.[music]')")

from music_engine import limits, render, score, song  # noqa: E402

from hallux import addons, app, tools  # noqa: E402
from hallux.config import Hardware  # noqa: E402
from hallux.disk import Disk  # noqa: E402

SCORES = Path(__file__).parent / "scores"
BEAT = (SCORES / "drum-beat.score").read_text()
# A song of a fifth of a second, for what has to play to its end.
SHORT = ("BPM = 300\n\nINSTRUMENT beep:\n    sin(p) * vel >> 8\n\n"
         "SONG:\n    (0, 4, A4, beep, 200)\n    (4, 4, E5, beep, 200)\n")
HELLO = 'print(json.dumps({"id": 0, "ok": True}), flush=True)\n'


@pytest.fixture
def sound(monkeypatch, tmp_path):
    """The file that SDL's disk driver writes instead of making a sound."""
    monkeypatch.setenv("SDL_AUDIODRIVER", "disk")
    monkeypatch.setenv("SDL_DISKAUDIOFILE", str(tmp_path / "sound.raw"))
    return tmp_path / "sound.raw"


@pytest.fixture
def hub():
    return addons.Events()


@pytest.fixture
def addon(sound, hub):
    """The addon as Hallux loads it."""
    [loaded], skipped = addons.load(app.ADDONS_FOLDER, only=["music"], events=hub)
    assert skipped == {}
    yield loaded
    loaded.stop()
    del sys.modules["hallux_addon_music"]


@pytest.fixture
def music(addon):
    """The addon's module: its functions and what's behind them."""
    return sys.modules["hallux_addon_music"]


@pytest.fixture
def world(tmp_path):
    """A machine's folder with two scores in a home directory, and its disk."""
    home = tmp_path / "world" / "home" / "user"
    home.mkdir(parents=True)
    (home / "beat.score").write_text(BEAT)
    (home / "short.score").write_text(SHORT)
    return Disk(tmp_path / "world")


@pytest.fixture
def play(addon, world):
    """The addon's tools as the AI calls them, on that world."""
    built = {tool.name: tool for tool in tools.build_addon_tools(addon, world)}

    def call(tool_name, **args):
        jsonschema.validate(args, built[tool_name].input_schema)
        result = asyncio.run(built[tool_name].handler(args))
        return json.loads(result["content"][0]["text"]), result["is_error"]

    call.tools = built
    return call


def stand_in(music, source):
    """Have the addon start this Python source instead of the real child."""
    music.stop()
    music.CHILD[:] = [sys.executable, "-c", "import json, sys, time\n" + source]


def wait_for(condition, seconds=5):
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "it never happened"
        time.sleep(0.01)


def beginning_of(sound_file, text):
    """How many samples of a score's render the file holds, from its first sound on."""
    read = score.read(text)
    wanted = render.render(read, song.unfold(read)).first
    got = np.fromfile(sound_file, dtype=np.int16)
    assert got.any(), "the file holds only silence"
    start = int(np.flatnonzero(got)[0]) - int(np.flatnonzero(wanted)[0])
    played = got[start:start + len(wanted)]
    different = np.flatnonzero(played != wanted[:len(played)])
    return int(different[0]) if len(different) else len(played)


# ---------------------------------------------------------------- the file

def test_the_file_passes_every_check_of_the_loader(addon):
    assert addon.name == "music"
    assert addon.summary == "A sound card: plays score files with bytebeat instruments."
    assert list(addon.functions) == ["play", "stop", "check"]
    assert addon.stop is addon.functions["stop"]          # the hook is the tool
    assert addon.has_events                               # it has connect(emit)
    for part in ("play(path, loop)", "stop()", "check(path)", '{"event": "finished"}',
                 "addon_listen"):
        assert part in addon.manual


def test_hallux_itself_never_imports_numpy_or_pygame():
    check = ("import sys; from hallux import addons, app; "
             "loaded, skipped = addons.load(app.ADDONS_FOLDER, only=['music']); "
             "print(len(loaded), skipped, [name for name in ('numpy', 'pygame', 'music_engine') "
             "if name in sys.modules])")
    done = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True)
    assert (done.stdout, done.stderr) == ("1 {} []\n", "")


def test_the_tools_are_play_stop_and_check_and_the_ai_never_sees_the_disk(play):
    assert list(play.tools) == ["play", "stop", "check"]
    assert play.tools["play"].input_schema == {
        "type": "object", "properties": {"path": {"type": "string"}, "loop": {"type": "boolean"}},
        "required": ["path"], "additionalProperties": False}
    assert play.tools["stop"].input_schema["properties"] == {}
    assert play.tools["check"].input_schema == {
        "type": "object", "properties": {"path": {"type": "string"}},
        "required": ["path"], "additionalProperties": False}
    assert all(tool.description for tool in play.tools.values())
    for tool in ("play", "check"):
        with pytest.raises(jsonschema.ValidationError):
            play(tool, disk="/", path="/home/user/beat.score")


def test_without_numpy_the_addon_is_skipped_with_the_reason(monkeypatch, tmp_path):
    find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *more: None if name == "numpy" else find_spec(name, *more))
    assert addons.load(app.ADDONS_FOLDER, only=["music"]) == (
        [], {"music": "No module named 'numpy'"})
    (tmp_path / "world").mkdir()
    loaded, notes = app.attach(tmp_path / "world", Hardware(addons=("music",)), app.ADDONS_FOLDER)
    assert loaded == [] and notes == ["addon music skipped: No module named 'numpy'"]
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *more: None if name == "pygame" else find_spec(name, *more))
    assert addons.load(app.ADDONS_FOLDER, only=["music"])[1] == {
        "music": "No module named 'pygame'"}


def test_the_addons_limit_is_the_childs():
    source = (app.ADDONS_FOLDER / "music.py").read_text()
    assert "SCORE_KB = 64 " in source and limits.SCORE_BYTES == 64 * 1024


# ---------------------------------------------------------------- playing

def test_play_returns_what_was_measured_and_the_sound_starts(play, music, sound):
    assert play("play", path="/home/user/beat.score") == (
        {"ok": True, "seconds": 8.0, "peak": 98}, False)
    child = music._link.process
    time.sleep(0.4)
    assert play("stop") == ({"ok": True}, False)
    assert child.poll() == 0 and music._link is None      # stop ends the child
    assert 5000 < beginning_of(sound, BEAT) < 60000       # the beat, until it was stopped


def test_a_relative_path_follows_the_machines_working_directory(play, world):
    assert play("play", path="beat.score") == ({"error": "ENOENT"}, True)
    world.chdir("/home/user")
    assert play("play", path="beat.score", loop=True) == (
        {"ok": True, "seconds": 8.0, "peak": 98}, False)
    assert play("play", path="../user/short.score")[0] == {"ok": True, "seconds": 0.2, "peak": 78}


def test_the_child_stays_for_the_next_play(play, music):
    play("play", path="/home/user/beat.score", loop=True)
    child = music._link.process
    assert play("play", path="/home/user/short.score")[1] is False   # it replaces the beat
    assert music._link.process is child and child.poll() is None


def test_a_file_the_jail_refuses_never_reaches_the_child(play, music, world, tmp_path):
    (tmp_path / "secret.score").write_text(SHORT)
    (world.root / "out.score").symlink_to(tmp_path / "secret.score")
    (world.root / "big.score").write_text(SHORT + "#" * (64 * 1024))
    (world.root / "huge.score").write_text("#" * (1024 * 1024 + 1))
    (world.root / "fits.score").write_text(SHORT + "#" * (64 * 1024 - len(SHORT)))
    for path, error in [("/nowhere.score", "ENOENT"), ("/out.score", "EACCES"),
                        ("/home", "EISDIR"), ("/.hallux/memory.md", "ENOENT"),
                        ("/big.score", "MusicError: the score is bigger than 64 KB"),
                        ("/huge.score", "EFBIG")]:
        assert play("play", path=path) == ({"error": error}, True), path
    assert music._link is None                            # no child was started for those
    assert play("play", path="/fits.score")[1] is False   # exactly 64 KB is fine


def test_a_score_with_mistakes_comes_back_with_every_line(play, music, world):
    (world.root / "bad.score").write_text(
        "BPM = 120\nINSTRUMENT lead:\n    sin(p) * CUTOF >> 8\nSONG:\n    (0, 8, H4, lead)\n")
    assert play("play", path="/home/user/beat.score", loop=True)[1] is False
    assert play("play", path="/bad.score") == (
        {"error": "MusicError: line 3: unknown name CUTOF\n"
                  "line 5: lead is an instrument: its value is a note such as A4, not H4"}, True)
    assert music._link.alive()                            # and the beat plays on


def test_the_loudness_report_reaches_the_ai(play, world):
    (world.root / "loud.score").write_text(
        "BPM = 300\nINSTRUMENT loud:\n    sin(p) * 2\nSONG:\n    (0, 4, A4 C5, loud)\n")
    assert play("play", path="/loud.score") == (
        {"ok": True, "seconds": 0.1, "peak": 200, "turned_down_to": 49, "clipped": ["loud"]},
        False)


def test_no_sound_device(play, music, monkeypatch):
    monkeypatch.setenv("SDL_AUDIODRIVER", "nosuchdriver")
    assert play("play", path="/home/user/short.score") == (
        {"error": "MusicError: no sound device: Audio target 'nosuchdriver' not available"}, True)
    assert music._link is None
    monkeypatch.setenv("SDL_AUDIODRIVER", "disk")         # the sound card is plugged in
    assert play("play", path="/home/user/short.score")[1] is False


# ---------------------------------------------------------------- stopping

def test_stop_with_nothing_playing_does_nothing(music, addon):
    assert music.stop() == {"ok": True} and music.stop() == {"ok": True}
    assert addons.stop_all([addon]) == []                 # what the end of a boot does


def test_the_end_of_a_boot_stops_the_sound(play, music, addon):
    play("play", path="/home/user/beat.score", loop=True)
    child = music._link.process
    assert addons.stop_all([addon]) == [] and child.poll() == 0
    assert addons.stop_all([addon]) == [] and music._link is None


def test_stop_ends_a_render_that_is_still_going(music, world, monkeypatch):
    stand_in(music, HELLO + "time.sleep(30)")
    failed = []

    def a_long_play():
        try:
            music.play(addons.DiskHandle(world), "/home/user/beat.score")
        except music.MusicError as problem:
            failed.append(str(problem))

    playing = threading.Thread(target=a_long_play)
    playing.start()
    wait_for(lambda: music._link is not None and music._link.asked == 1)
    started = time.monotonic()
    assert music.stop() == {"ok": True}
    playing.join(5)
    assert time.monotonic() - started < 2 and failed == ["the sound card stopped"]
    assert music._link is None


# ---------------------------------------------------------------- when the child misbehaves

def test_a_render_that_takes_too_long(play, music, monkeypatch):
    monkeypatch.setattr(music, "RENDER_SECONDS", 0.3)
    stand_in(music, HELLO + "time.sleep(30)")
    started = time.monotonic()
    assert play("play", path="/home/user/beat.score") == (
        {"error": "MusicError: the song took too long to render"}, True)
    assert time.monotonic() - started < 4
    assert music._link is None                            # the child is gone, and the sound


def test_a_child_that_dies_says_why_and_the_next_play_starts_a_new_one(play, music):
    real = list(music.CHILD)
    stand_in(music, HELLO + 'sys.stdin.readline()\nraise RuntimeError("out of notes")')
    assert play("play", path="/home/user/short.score") == (
        {"error": "MusicError: the sound card stopped: it crashed (RuntimeError: out of notes)"},
        True)
    assert music._link is None
    stand_in(music, HELLO + "sys.stdin.readline()\nsys.exit(0)")
    assert play("play", path="/home/user/short.score") == (
        {"error": "MusicError: the sound card stopped"}, True)
    music.CHILD[:] = real
    assert play("play", path="/home/user/short.score")[1] is False


def test_a_child_that_never_starts(play, music, monkeypatch):
    monkeypatch.setattr(music, "START_SECONDS", 0.3)
    stand_in(music, "time.sleep(30)")
    assert play("play", path="/home/user/short.score") == (
        {"error": "MusicError: the sound card didn't start"}, True)
    stand_in(music, 'sys.exit("no numpy for you")')
    assert play("play", path="/home/user/short.score") == (
        {"error": "MusicError: the sound card stopped: it crashed (no numpy for you)"}, True)
    assert music._link is None


def test_a_crash_is_told_without_colours(play, music, monkeypatch):
    """With FORCE_COLOR set in the shell, Python colours a child's traceback, and its last line
    is what the AI is told. Every child is started with colours off."""
    monkeypatch.setenv("FORCE_COLOR", "1")
    stand_in(music, HELLO + 'sys.stdin.readline()\nraise RuntimeError("out of notes")')
    assert play("play", path="/home/user/short.score") == (
        {"error": "MusicError: the sound card stopped: it crashed (RuntimeError: out of notes)"},
        True)
    assert play("check", path="/home/user/short.score") == (
        {"error": "MusicError: the check stopped: it crashed (RuntimeError: out of notes)"}, True)


# ---------------------------------------------------------------- checking

def test_check_returns_what_play_returns_and_makes_no_sound(play, music, sound):
    assert play("check", path="/home/user/beat.score") == (
        {"ok": True, "seconds": 8.0, "peak": 98}, False)
    assert play("check", path="/home/user/short.score") == (
        {"ok": True, "seconds": 0.2, "peak": 78}, False)
    assert not sound.exists()                             # the disk driver was never opened
    assert music._link is None                            # and no child stays behind
    assert play("play", path="/home/user/short.score") == (
        {"ok": True, "seconds": 0.2, "peak": 78}, False)   # the same numbers, with the sound


def test_check_needs_no_sound_device(play, monkeypatch):
    monkeypatch.setenv("SDL_AUDIODRIVER", "nosuchdriver")
    assert play("play", path="/home/user/beat.score")[1] is True      # no sound can get out
    assert play("check", path="/home/user/beat.score") == (
        {"ok": True, "seconds": 8.0, "peak": 98}, False)


def test_check_follows_the_machines_working_directory(play, world):
    assert play("check", path="beat.score") == ({"error": "ENOENT"}, True)
    world.chdir("/home/user")
    assert play("check", path="beat.score") == ({"ok": True, "seconds": 8.0, "peak": 98}, False)


def test_check_refuses_the_files_play_refuses(play, music, world, tmp_path):
    (tmp_path / "secret.score").write_text(SHORT)
    (world.root / "out.score").symlink_to(tmp_path / "secret.score")
    (world.root / "big.score").write_text(SHORT + "#" * (64 * 1024))
    (world.root / "huge.score").write_text("#" * (1024 * 1024 + 1))
    (world.root / "fits.score").write_text(SHORT + "#" * (64 * 1024 - len(SHORT)))
    started = []
    monkeypatch_run, music.subprocess.run = music.subprocess.run, (
        lambda *args, **more: started.append(args) or monkeypatch_run(*args, **more))
    try:
        for path, error in [("/nowhere.score", "ENOENT"), ("/out.score", "EACCES"),
                            ("/home", "EISDIR"), ("/.hallux/memory.md", "ENOENT"),
                            ("/big.score", "MusicError: the score is bigger than 64 KB"),
                            ("/huge.score", "EFBIG")]:
            assert play("check", path=path) == ({"error": error}, True), path
        assert started == []                              # no child was started for those
        assert play("check", path="/fits.score")[1] is False     # exactly 64 KB is fine
        assert len(started) == 1
    finally:
        music.subprocess.run = monkeypatch_run


def test_check_of_a_score_with_mistakes_has_every_line(play, world):
    (world.root / "bad.score").write_text(
        "BPM = 120\nINSTRUMENT lead:\n    sin(p) * CUTOF >> 8\nSONG:\n    (0, 8, H4, lead)\n")
    told = ({"error": "MusicError: line 3: unknown name CUTOF\n"
                      "line 5: lead is an instrument: its value is a note such as A4, not H4"}, True)
    assert play("check", path="/bad.score") == told
    assert play("play", path="/bad.score") == told        # word for word what play says


def test_the_loudness_report_of_a_check(play, world):
    (world.root / "loud.score").write_text(
        "BPM = 300\nINSTRUMENT loud:\n    sin(p) * 2\nSONG:\n    (0, 4, A4 C5, loud)\n")
    assert play("check", path="/loud.score") == (
        {"ok": True, "seconds": 0.1, "peak": 200, "turned_down_to": 49, "clipped": ["loud"]},
        False)


def test_check_leaves_a_song_that_plays_alone(play, music, sound):
    play("play", path="/home/user/beat.score", loop=True)
    child = music._link.process
    assert play("check", path="/home/user/short.score") == (
        {"ok": True, "seconds": 0.2, "peak": 78}, False)
    assert music._link.process is child and child.poll() is None     # the same child, alive
    time.sleep(0.3)
    play("stop")
    assert beginning_of(sound, BEAT) > 5000               # and the beat went on meanwhile


def test_check_doesnt_wait_for_a_play_that_is_rendering(music, world):
    """A play holds the lock of the child that plays for as long as its render takes."""
    with music._lock:
        started = time.monotonic()
        assert music.check(addons.DiskHandle(world), "/home/user/short.score") == {
            "ok": True, "seconds": 0.2, "peak": 78}
        assert time.monotonic() - started < 5


def test_stop_during_a_check_doesnt_end_it(music, world):
    stand_in(music, 'sys.stdin.read()\ntime.sleep(0.6)\n'
                    'print(json.dumps({"ok": True, "seconds": 1.5, "peak": 50}), flush=True)')
    answers = []
    checking = threading.Thread(target=lambda: answers.append(
        music.check(addons.DiskHandle(world), "/home/user/short.score")))
    checking.start()
    time.sleep(0.2)                                       # the check's child is running
    assert music.stop() == {"ok": True}
    checking.join(5)
    assert answers == [{"ok": True, "seconds": 1.5, "peak": 50}]


def test_a_check_that_takes_too_long(play, music, monkeypatch, tmp_path):
    monkeypatch.setattr(music, "CHECK_SECONDS", 0.5)
    monkeypatch.setenv("CHILD_SAYS_WHO", str(tmp_path / "pid"))
    stand_in(music, 'import os\nopen(os.environ["CHILD_SAYS_WHO"], "w").write(str(os.getpid()))\n'
                    'time.sleep(30)')
    started = time.monotonic()
    assert play("check", path="/home/user/beat.score") == (
        {"error": "MusicError: the song took too long to render"}, True)     # play's words
    assert time.monotonic() - started < 4
    with pytest.raises(ProcessLookupError):               # the child is gone
        os.kill(int((tmp_path / "pid").read_text()), 0)


def test_a_check_child_that_ends_without_an_answer(play, music):
    stand_in(music, "sys.exit(0)")
    assert play("check", path="/home/user/short.score") == (
        {"error": "MusicError: the check stopped"}, True)
    stand_in(music, 'print("not an answer")\nsys.exit("no numpy for you")')
    assert play("check", path="/home/user/short.score") == (
        {"error": "MusicError: the check stopped: it crashed (no numpy for you)"}, True)
    stand_in(music, 'print(json.dumps([1, 2]))')          # a line of JSON, and no answer
    assert play("check", path="/home/user/short.score") == (
        {"error": "MusicError: the check stopped"}, True)


# ---------------------------------------------------------------- the event

def test_finished_reaches_emit_and_only_for_a_song_that_ends_by_itself(play, music):
    reported = []
    music.connect(reported.append)
    play("play", path="/home/user/short.score")
    wait_for(lambda: reported)
    assert reported == [{"event": "finished"}]
    play("play", path="/home/user/beat.score")
    play("stop")                                          # stopped isn't finished
    play("play", path="/home/user/short.score", loop=True)
    time.sleep(0.6)                                       # nor is a loop, ever
    play("stop")
    assert reported == [{"event": "finished"}]


def test_an_event_between_a_question_and_its_answer_doesnt_disturb_it(play, music):
    reported = []
    music.connect(reported.append)
    stand_in(music, HELLO + '''
question = json.loads(sys.stdin.readline())
print(json.dumps({"event": "finished"}), flush=True)             # of the song before
print(json.dumps({"id": question["id"], "ok": True, "seconds": 1.5, "peak": 50}), flush=True)
time.sleep(30)''')
    assert play("play", path="/home/user/short.score") == (
        {"ok": True, "seconds": 1.5, "peak": 50}, False)
    assert reported == [{"event": "finished"}]


def test_finished_reaches_hallux_only_while_it_listens(play, music, hub):
    play("play", path="/home/user/short.score")
    wait_for(lambda: hub.reset() == {"music": 1})         # nobody listened
    hub.listen("music")
    play("play", path="/home/user/short.score")
    wait_for(hub.pending)
    assert hub.take() == [("music", {"event": "finished"})]


def test_a_finished_song_wakes_the_machine(sound, tmp_path):
    """The real addon, a real child and the machine, with a fake model and terminal: the AI
    plays a short song and listens, and hears of its end at the prompt."""
    from test_machine import FakeModel, FakeTerminal, Typing, result, screen

    from hallux.machine import Machine

    (tmp_path / "world").mkdir()
    (tmp_path / "world" / "short.score").write_text(SHORT)
    hub = addons.Events()
    [loaded], _ = addons.load(app.ADDONS_FOLDER, only=["music"], events=hub)
    module = sys.modules["hallux_addon_music"]
    machine = Machine(tmp_path / "world", Hardware(), None, addons=[loaded], events=hub)
    played = []

    def the_ai_plays():
        played.append(module.play(addons.DiskHandle(machine.disk), "/short.score"))
        hub.listen("music")

    model = FakeModel(screen("boot\n"), [the_ai_plays] + result(screen("playing\n")),
                      screen("that was the song\n"), screen("", prompt="", tail="<halt/>"))
    machine.terminal = FakeTerminal("play short.score", Typing("ls"), "exit")
    machine.client_factory = model
    try:
        asyncio.run(asyncio.wait_for(machine.run(), 20))
        assert module._link is None                       # the halt stopped the sound card
    finally:
        loaded.stop()
        del sys.modules["hallux_addon_music"]
    assert played == [{"ok": True, "seconds": 0.2, "peak": 78}]
    assert '<event addon="music">{"event": "finished"}</event>' in model.sessions[0][2]
    assert machine.terminal.screen == "boot\nplaying\nthat was the song\n"
    assert "mcp__music__play" in model.options[0].allowed_tools
