"""The music addon's manual: what addon_help("music") returns. The AI writes its scores from
this text alone, so every example in it is taken out here and run, and what it says about
names, functions and limits is held against the code."""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="numpy isn't installed (pip install -e '.[music]')")
pytestmark = pytest.mark.skipif(importlib.util.find_spec("pygame") is None,
                                reason="pygame isn't installed (pip install -e '.[music]')")

from music_engine import expr, limits, render, score, song  # noqa: E402
from music_engine.score import Change, Notes, Placement, Plus  # noqa: E402

from hallux import addons, app  # noqa: E402

DESIGN = Path(__file__).resolve().parent.parent / "docs" / "addon-music.md"
SCORES = Path(__file__).parent / "scores"
MANUAL_CHARS = 8500                           # every boot that uses the addon reads all of it
SECTIONS = ["A WHOLE SCORE", "THE FILE", "EVENTS", "PATTERNS AND THE SONG", "INSTRUMENTS",
            "RECIPES", "WHAT PLAY AND CHECK RETURN", "WRITING WELL", "LIMITS"]


@pytest.fixture(scope="module")
def addon():
    [loaded], skipped = addons.load(app.ADDONS_FOLDER, only=["music"])
    assert skipped == {}
    yield loaded
    module = sys.modules.pop("hallux_addon_music")
    module.stop()


@pytest.fixture(scope="module")
def manual(addon):
    return addon.manual


def section(manual, title):
    """The text of one section, from the line after its title to the next title."""
    assert f"\n\n{title}\n" in manual, title
    rest = manual.split(f"\n\n{title}\n", 1)[1]
    following = [rest.index(f"\n\n{other}\n") for other in SECTIONS if f"\n\n{other}\n" in rest]
    return rest[:min(following)] if following else rest


def blocks(text):
    """The examples of a text: what stands between two lines of three backticks."""
    return re.findall(r"```\n(.*?)```", text, re.S)


def play(text):
    read = score.read(text)
    return read, render.render(read, song.unfold(read))


def in_a_song(lines):
    """The lines of an example as the song of a score that declares what they name. The
    manual shows them at the left edge."""
    return AROUND + "".join(f"    {line}\n" for line in lines.splitlines())


# ---------------------------------------------------------------- the text as a whole

def test_the_manual_is_under_its_size_limit(manual):
    assert 5000 < len(manual) <= MANUAL_CHARS
    assert max(len(line) for line in manual.splitlines()) <= 100
    assert manual.isascii()                               # nothing the pipe could garble


def test_it_has_the_parts_of_the_plan_in_their_order(manual):
    places = [manual.index(f"\n\n{title}\n") for title in SECTIONS]
    assert places == sorted(places)
    first = manual[:places[0]]
    for part in ("play(path, loop)", "stop()", "check(path, loop)", '{"event": "finished"}',
                 "addon_listen", "The addon defines no command", "nano", "the way a player would",
                 "compose(request, folder, edit)"):
        assert part in first, part


def test_every_example_stands_in_a_block_that_is_checked_here(manual):
    counts = {title: len(blocks(section(manual, title))) for title in SECTIONS}
    assert counts == {"A WHOLE SCORE": 1, "THE FILE": 0, "EVENTS": 1, "PATTERNS AND THE SONG": 1,
                      "INSTRUMENTS": 2, "RECIPES": 1, "WHAT PLAY AND CHECK RETURN": 0,
                      "WRITING WELL": 0,
                      "LIMITS": 0}
    assert manual.count("```") == 12


def test_the_manual_has_two_parts_and_the_composer_reads_the_second(addon, manual):
    """The first part is for the one that can call every function. The second says how a
    score is written, and the composer reads it too: it has check, and neither play nor
    stop nor compose. So the second part tells nobody to call one of those."""
    music = sys.modules["hallux_addon_music"]
    assert manual == f"{music.FUNCTIONS}\n\n{music.WRITING}"
    assert music.WRITING.startswith("A WHOLE SCORE\n") and music.WRITING.endswith("the song.")
    assert all(f"\n\n{title}\n" in f"\n\n{music.WRITING}" for title in SECTIONS)
    assert not any(title in music.FUNCTIONS for title in SECTIONS)
    composer = addon.agent.prompt
    assert composer == f"{music.COMPOSER}\n\n{music.WRITING}\n\n{music.CHECKING}"
    for told_to_call in ("play(", "stop()", "compose(", "play again", "Print what play",
                         "addon_listen", '{"event": "finished"}'):
        assert told_to_call not in composer, told_to_call
    assert "Fix them all, then try again." in music.WRITING
    for part in ("check(path, loop)", "set_status", "lowercase\n  with dashes", ".score",
                 "between 50 and 100, or after four rounds", "WHAT PLAY AND CHECK RETURN"):
        assert part in composer, part
    assert composer.isascii() and max(len(line) for line in composer.splitlines()) <= 100


def test_what_the_manual_says_of_compose(manual):
    said = manual.split("- compose(request, folder, edit)")[1].split("\n- ")[0]
    for part in ("write a song into that folder", "change the\n  scores listed in edit",
                 "returns a pid at once", "the song isn't there yet", "never wait\n  for it or "
                 "imagine it", "as an event with the files it wrote", "addon_listen\n  brings it "
                 "at once", "must exist", "can't be a home folder itself"):
        assert part in said, part


def test_it_is_what_addon_help_returns(addon, manual):
    assert manual == sys.modules["hallux_addon_music"].prompt()
    assert addon.summary == "A sound card: plays score files with bytebeat instruments."


# ---------------------------------------------------------------- the whole score

def test_the_whole_score_plays_and_uses_every_part(manual):
    [text] = blocks(section(manual, "A WHOLE SCORE"))
    read, rendered = play(text)
    assert rendered.report() == {"seconds": 8.5, "peak": 92}         # nothing loud, or clipped
    assert read.bpm == 120 and read.variables == {"VOL": 255}       # a setting, and a variable
    assert list(read.instruments) == ["pad", "pluck"]               # two instruments,
    assert read.instruments["pad"].tail == 20000 and list(read.instruments["pad"].parts) == ["env"]
    [riff] = read.patterns.values()                                  # a pattern
    assert any(isinstance(line, Notes) and len(line.keys) == 3 for line in riff.lines)   # a chord
    assert any(isinstance(line.start, Plus) for line in riff.lines)  # +
    placed = [line for line in read.song if isinstance(line, Placement)]
    assert {line.transpose for line in placed} == {0, -5}           # transposing
    assert max(line.times for line in placed) == 2                  # repeats
    assert Change(22, 96, 32, "VOL", 0) in read.song                # and a glide
    assert "# " in text                                              # with comments in both places


def test_what_writing_well_says_about_that_score_is_true(manual):
    [text] = blocks(section(manual, "A WHOLE SCORE"))
    read, rendered = play(text)
    velocities = {line.instrument: line.velocity
                  for line in read.patterns["riff"].lines if isinstance(line, Notes)}
    assert velocities == {"pad": 50, "pluck": 130}
    assert ("three pad notes at 50 under a pluck at 130 give 92" in section(manual, "WRITING WELL")
            and rendered.peak == 92)


# ---------------------------------------------------------------- events and placements

AROUND = """\
BPM = 120
VOL = 255

INSTRUMENT lead:
    sin(p) * vel >> 8

INSTRUMENT pad:
    sin(p) * vel >> 8

PATTERN riff 32:
    (0, 8, A4, lead)

SONG:
"""


def test_the_events_of_the_manual_read_as_it_says(manual):
    [text] = blocks(section(manual, "EVENTS"))
    read = score.read(in_a_song(text))
    assert [type(line).__name__ for line in read.song] == ["Notes"] * 5 + ["Change"] * 2
    full, quiet, chord, after, rest, jump, glide = read.song
    assert (full.keys, full.duration, full.velocity) == ((69,), 16, 255)   # at full velocity
    assert quiet.velocity == 75 and chord.keys == (48, 52, 55) and chord.velocity == 60
    assert after.start == Plus(0) and rest.start == Plus(4)
    assert (jump.start, jump.duration, jump.value) == (8, 0, 128)
    assert (glide.start, glide.duration, glide.value) == (8, 8, 0)   # from step 8 to step 16
    assert all(line.strip().startswith("(") and "# " in line for line in text.splitlines())
    assert "(start, duration, value, target, velocity)" in section(manual, "EVENTS")


def test_the_placements_of_the_manual_read_as_it_says(manual):
    [text] = blocks(section(manual, "PATTERNS AND THE SONG"))
    read = score.read(in_a_song(text))
    assert [(line.start, line.pattern, line.transpose, line.times) for line in read.song] == [
        (0, "riff", 0, 1), (32, "riff", -5, 1), (64, "riff", 0, 4)]
    assert song.unfold(read).end == song.sample_of(64 + 4 * 32, read)    # one after the other


# ---------------------------------------------------------------- instruments

def test_the_names_and_functions_are_those_of_the_reader(manual):
    """Neither can change without the other."""
    names, functions = blocks(section(manual, "INSTRUMENTS"))
    assert [line.split()[0] for line in names.splitlines()] == list(expr.NAMES)
    listed = {}
    for line in functions.splitlines():
        for name, args in re.findall(r"([a-z]+)\(([^)]*)\)", re.split(r" {3,}", line)[0]):
            listed[name] = len(args.split(","))
    assert listed == expr.FUNCTIONS


def test_the_operators_are_those_of_the_reader(manual):
    [line] = [line for line in section(manual, "INSTRUMENTS").splitlines()
              if line.startswith("- Operators:")]
    listed = line.removeprefix("- Operators:").split(", with")[0].replace(" and a ? b : c", "")
    assert set(listed.split()) == set(expr.LEVELS) | set(expr.SIGNS)
    assert "a ? b : c" in line and "C's precedence" in line
    for refused in ("&&", "||", "!", "**", "0.5"):
        assert refused in section(manual, "INSTRUMENTS")
        with pytest.raises(expr.ExprError):
            expr.read(f"1 {refused} 2" if refused != "!" else "!t", expr.NAMES)


@pytest.mark.parametrize("text", ["x * vel * VOL >> 16", "x * vel >> 8 * VOL >> 8",
                                  "(p & 65535) - 32768", "decay(t - dur, h)",
                                  "sin(t * 8) >> 2"])
def test_the_expressions_in_its_sentences_read(manual, text):
    assert text in section(manual, "INSTRUMENTS")
    assert expr.read(text, expr.NAMES + ("x", "VOL", "h"))


def test_what_it_says_about_a_note_is_true(manual):
    said = section(manual, "INSTRUMENTS")
    assert "2 and 5 ms" in said
    assert (round(render.FADE_IN / 44.1), round(render.FADE_OUT / 44.1)) == (2, 5)
    assert "INSTRUMENT pad 20000:" in said and "-32768 to 32767" in " ".join(said.split())
    assert "tail of 0.8 seconds" in section(manual, "RECIPES") and 35280 / 44100 == 0.8
    assert "A4 is 440 Hz" in section(manual, "EVENTS") and "C0 to B9" in section(manual, "EVENTS")
    assert score.key_of("A4") == 69 and "69 for A4" in said


# ---------------------------------------------------------------- the recipes

def recipes(manual):
    [text] = blocks(section(manual, "RECIPES"))
    return text


def test_every_recipe_computes_without_clipping_at_full_velocity(manual):
    notes = {"kick": "A1", "snare": "G3", "hat": "C6"}             # as the manual says to play them
    read = score.read("BPM = 120\n" + recipes(manual) + "SONG:\n    (0, 1, A4, lead)\n")
    assert list(read.instruments) == ["kick", "snare", "hat", "pad", "lead", "pluck", "bell",
                                      "piano"]
    for name in read.instruments:
        for note in {notes.get(name, "A4"), "C2", "C7"}:
            _, rendered = play(f"BPM = 120\n{recipes(manual)}SONG:\n    (0, 16, {note}, {name})\n")
            assert rendered.clipped == [] and rendered.turned_down_to is None, (name, note)
            assert rendered.peak > 20, (name, note)                  # and it sounds


def test_the_recipes_are_the_ones_that_were_heard(manual):
    """Recipes that nobody has heard aren't in it: every line is one of the design's."""
    design = DESIGN.read_text(encoding="utf-8")
    lines = [line.strip() for line in recipes(manual).splitlines()
             if line.startswith("    ")]
    assert len(lines) == 11
    for line in lines:
        assert line in design, line
    for name, note in (("kick", "A1"), ("snare", "G3")):
        assert f"# {name}: play it at {note}" in recipes(manual)
    assert "A drum bar is kick on steps 0 and 16, snare on 8 and 24" in section(manual, "RECIPES")
    beat = score.read((SCORES / "drum-beat.score").read_text()).patterns["beat"].lines
    assert [line.start for line in beat if line.instrument == "kick"] == [0, 16]
    assert [line.start for line in beat if line.instrument == "snare"] == [8, 24]
    assert {line.duration for line in beat} == {4}


def test_what_it_says_about_their_loudness_is_true(manual):
    said = "Alone, at velocity 255, each peaks at 45 to 100 percent."
    assert said in section(manual, "RECIPES")
    notes = {"kick": "A1", "snare": "G3", "hat": "C6"}
    peaks = {}
    for name in ("kick", "snare", "hat", "pad", "lead", "pluck", "bell", "piano"):
        _, rendered = play(f"BPM = 120\n{recipes(manual)}SONG:\n"
                           f"    (0, 16, {notes.get(name, 'A4')}, {name})\n")
        peaks[name] = rendered.peak
    assert peaks == {"kick": 98, "snare": 95, "hat": 83, "pad": 71, "lead": 46, "pluck": 98,
                     "bell": 99, "piano": 99}


def test_what_it_says_about_patterns_and_loops_is_true(manual):
    said = " ".join(section(manual, "PATTERNS AND THE SONG").split())
    for sentence in ("(start, pattern, transpose, times)",
                     "Transposing also moves the patterns placed inside: the amounts add up.",
                     "A loop starts again there, with its variables reset."):
        assert sentence in said
    # riff holds one A4. Placed 3 up inside a pattern that is placed 4 up, it is 7 up.
    inside = AROUND.replace("SONG:\n", "PATTERN outer 32:\n    (0, riff, 3)\n\nSONG:\n")
    assert [note.key for note in song.unfold(score.read(inside + "    (0, outer, 4)\n")).notes] == [
        69 + 3 + 4]
    # A loop is one sound played again and again, so a glide starts over with every round.
    fades = AROUND.replace("sin(p) * vel >> 8", "sin(p) * vel * VOL >> 16", 1)
    read = score.read(fades + "    (0, riff)\n    (0, 8, 0, VOL)\n")
    looped = render.render(read, song.unfold(read), loop=True)
    assert looped.again is None and looped.first[500] != 0 and looped.first[-500] == 0


# ---------------------------------------------------------------- written from the manual alone

@pytest.mark.parametrize("name, report", [
    ("tune", {"seconds": 16.8, "peak": 64}),
    ("beat", {"seconds": 17.5, "peak": 77}),
    ("own", {"seconds": 10.7, "peak": 55}),
])
def test_scores_that_a_reader_of_the_manual_wrote_play(name, report):
    """Three scores written on 2026-10-02 by a model that had read the manual and nothing
    else, each in one go and untested: a tune, drums with a bass that fades, and a piece with
    its own instruments. All three played on the first try. They are kept as they came."""
    _, rendered = play((SCORES / f"from-the-manual-{name}.score").read_text())
    assert rendered.report() == report                    # between 50 and 100, as it advises


def test_the_score_in_the_readme_plays():
    readme = (Path(__file__).resolve().parent.parent / "README.MD").read_text(encoding="utf-8")
    music = readme[readme.index("### The music addon"):readme.index("### Writing an addon")]
    [text] = [block for block in re.findall(r"```text\n(.*?)```", music, re.S)
              if block.startswith("BPM")]
    read, rendered = play(text)
    assert rendered.report() == {"seconds": 8.0, "peak": 58}
    assert list(read.instruments) == ["pluck"] and len(read.song) == 3
    assert 'pip install -e ".[music]"' in music and "tests/music_play.py" in music


# ---------------------------------------------------------------- what play returns, the limits

def test_the_answer_it_shows_is_a_real_one(manual):
    said = section(manual, "WHAT PLAY AND CHECK RETURN")
    _, rendered = play((SCORES / "drum-beat.score").read_text())
    assert json.dumps({"ok": True} | rendered.report()) in said     # the drum beat's
    _, loud = play("BPM = 300\nINSTRUMENT lead:\n    sin(p) * 2\nSONG:\n    (0, 4, A4 C5, lead)\n")
    assert set(loud.report()) == {"seconds", "peak", "turned_down_to", "clipped"}
    assert '"turned_down_to": 61' in said and '"clipped": ["lead"]' in said
    assert loud.clipped == ["lead"]


def test_every_limit_it_states_is_the_number_in_the_code(manual):
    music = sys.modules["hallux_addon_music"]
    expected = (
        f"A song of {limits.SONG_SECONDS} seconds with its tails. "
        f"A file of {limits.SCORE_BYTES // 1024} KB. "
        f"{limits.EVENTS} notes and changes once the patterns are unfolded. "
        f"Patterns {limits.PATTERN_DEPTH} deep. "
        f"An expression of {limits.EXPRESSION_CHARS} characters, nested "
        f"{limits.EXPRESSION_DEPTH} deep. "
        f"{limits.PARTS} named parts. "
        f"A tail of {limits.TAIL_SAMPLES} samples. "
        f"{limits.VOICES} notes sounding at once. "
        f"BPM {limits.BPM_MIN} to {limits.BPM_MAX}, STEPS {limits.STEPS_MIN} to "
        f"{limits.STEPS_MAX}. "
        f"A render that takes over {music.RENDER_SECONDS:g} seconds fails: shorten the song.")
    assert " ".join(section(manual, "LIMITS").split()) == expected
    assert music.SCORE_KB == limits.SCORE_BYTES // 1024
