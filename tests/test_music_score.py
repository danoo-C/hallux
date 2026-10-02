"""Reading a score file: addons/music_engine/score.py. Nothing here is unfolded or timed, and
nothing needs numpy."""
import re
from pathlib import Path

import pytest
from music_engine import expr, limits, score
from music_engine.score import Change, Notes, Placement, Plus, ScoreError

SCORES = Path(__file__).parent / "scores"
DESIGN = Path(__file__).resolve().parent.parent / "docs" / "addon-music.md"

# Twelve lines that every test below can build on: what follows starts on line 13.
HEAD = """\
BPM = 120
VOL = 255

INSTRUMENT lead:
    sin(p) * vel >> 8

PATTERN riff 16:
    (0, 8, A4, lead)

PATTERN free:
    (0, 8, A4, lead)

"""
PLAYS = "SONG:\n    (0, riff)\n"


def song(*lines):
    """HEAD and a song of these lines: SONG: is line 13, and the first of them line 14."""
    return HEAD + "SONG:\n" + "".join(f"    {line}\n" for line in lines)


def problems(text):
    with pytest.raises(ScoreError) as raised:
        score.read(text)
    shown = str(raised.value).split("\n")[:limits.PROBLEMS]
    assert shown == raised.value.problems[:limits.PROBLEMS]
    return raised.value.problems


def design_blocks(start, end):
    """The text blocks of the design between two of its headings."""
    text = DESIGN.read_text(encoding="utf-8")
    return re.findall(r"```text\n(.*?)```", text[text.index(start):text.index(end)], re.S)


# ---------------------------------------------------------------- the design's scores

def test_the_score_files_are_the_scores_of_the_design():
    blocks = design_blocks("## 5. Three complete scores", "## 6. Playing")
    files = ["chords-and-melody.score", "automation.score", "drum-beat.score"]
    assert [(SCORES / name).read_text(encoding="utf-8") for name in files] == blocks


def test_chords_and_a_melody_reads():
    read = score.read((SCORES / "chords-and-melody.score").read_text())
    assert (read.bpm, read.steps, read.variables) == (100, 8, {})
    assert list(read.instruments) == ["pad", "lead"]
    assert list(read.patterns) == ["major", "minor", "riff"]
    assert len(read.song) == 8
    pad = read.instruments["pad"]
    assert (pad.name, pad.line, pad.tail, pad.parts) == ("pad", 3, 0, {})
    assert pad.sample == expr.read("sin(p) * vel >> 8", expr.NAMES)
    major, riff = read.patterns["major"], read.patterns["riff"]
    assert (major.name, major.line, major.length) == ("major", 10, 32)
    assert major.lines == (Notes(11, 0, 32, "pad", (48, 52, 55), 60),)       # C3 E3 G3
    assert riff.lines == (Notes(19, 0, 8, "lead", (60,), 140),               # C4
                          Notes(20, Plus(0), 8, "lead", (67,), 140),         # G4
                          Notes(21, Plus(0), 16, "lead", (72,), 140))        # C5
    assert read.song[:4] == (Placement(24, 0, "major", 0, 1), Placement(25, 0, "riff", 0, 1),
                             Placement(26, 32, "major", -5, 1), Placement(27, 32, "riff", -5, 1))
    assert [(line.start, line.pattern, line.transpose) for line in read.song[4:]] == [
        (64, "minor", 0), (64, "riff", -3), (96, "major", -7), (96, "riff", -7)]


def test_the_same_piece_with_automation_reads():
    read = score.read((SCORES / "automation.score").read_text())
    assert read.variables == {"VOL": 0, "BRIGHT": 0}
    assert read.instruments["lead"].sample == expr.read(
        "(saw(p) * BRIGHT + sin(p) * (255 - BRIGHT)) * vel * VOL >> 24",
        expr.NAMES + ("VOL", "BRIGHT"))
    assert read.patterns["riff"].lines[:3] == (
        Change(21, 0, 24, "BRIGHT", 255), Change(22, Plus(0), 8, "BRIGHT", 0),
        Notes(23, 0, 8, "lead", (60,), 130))                # a number starts a new count
    assert read.song[:2] == (Change(29, 0, 8, "VOL", 255), Change(30, 112, 16, "VOL", 0))
    assert len(read.song) == 10


def test_the_drum_beat_reads():
    read = score.read((SCORES / "drum-beat.score").read_text())
    assert (read.bpm, list(read.instruments)) == (120, ["kick", "snare", "hat"])
    snare = read.instruments["snare"]
    assert list(snare.parts) == ["body", "hiss"]
    assert snare.parts["hiss"] == expr.read("noise(t) * decay(t, 2200)", expr.NAMES)
    assert snare.sample == expr.read("(body + hiss) * vel >> 25", expr.NAMES + ("body", "hiss"))
    beat = read.patterns["beat"]
    assert beat.length == 32 and len(beat.lines) == 10
    assert beat.lines[0] == Notes(16, 0, 4, "kick", (33,), 255)              # A1, at full
    assert beat.lines[1] == Notes(17, 4, 4, "hat", (84,), 150)               # C6
    assert read.song == (Placement(28, 0, "beat", 0, 4),)


def test_the_sketch_of_the_file_reads():
    [sketch] = design_blocks("## 2. The score file", "| Part | Example |")
    read = score.read(sketch)
    assert (read.bpm, read.steps, read.variables) == (120, 8, {"VOL": 255})
    assert list(read.instruments) == ["lead", "bass"] and read.patterns["riff"].length == 16
    assert read.patterns["riff"].lines[1] == Notes(12, Plus(0), 8, "lead", (72,), 75)
    assert read.song == (Placement(15, 0, "riff", 0, 1), Placement(16, 16, "riff", 3, 1),
                         Notes(17, 0, 32, "bass", (45,), 255), Change(18, 24, 8, "VOL", 0))


def test_patterns_inside_patterns_read():
    [nested] = design_blocks("### Patterns", "### The song")
    read = score.read("BPM = 120\nINSTRUMENT kick:\n    sin(p)\nINSTRUMENT hat:\n    noise(t)\n"
                      + nested)
    assert read.patterns["bar"].lines == (Placement(11, 0, "beat", 0, 4),)
    assert read.song == (Placement(14, 0, "bar", 0, 16),)


# ---------------------------------------------------------------- the parts of the file

def test_note_names_become_numbers():
    assert [score.key_of(note) for note in ("A4", "C4", "C0", "B9", "C#3", "Bb3", "A1")] == [
        69, 60, 12, 131, 49, 58, 33]
    assert score.key_of("E#4") == score.key_of("F4") and score.key_of("Cb4") == score.key_of("B3")
    assert [score.key_of(text) for text in ("H4", "a4", "A", "4", "A#b4", "A4x", "")] == [None] * 7


def test_events_in_every_shape():
    read = score.read(song("(0, 16, A4, lead)", "(0, 16, A4, lead, 75)",
                           "(0, 32, C3 E3 G3, lead, 60)", "(+, 8, G4, lead)",
                           "(+4, 8, C#3, lead)", "(+ 4, 8, Bb3, lead, 0)", "(8, 0, 128, VOL)",
                           "(8, 8, 0, VOL)", "(+, 8, -5, VOL)", "( 0 ,8,A4,lead )"))
    assert read.song == (
        Notes(14, 0, 16, "lead", (69,), 255), Notes(15, 0, 16, "lead", (69,), 75),
        Notes(16, 0, 32, "lead", (48, 52, 55), 60), Notes(17, Plus(0), 8, "lead", (67,), 255),
        Notes(18, Plus(4), 8, "lead", (49,), 255), Notes(19, Plus(4), 8, "lead", (58,), 0),
        Change(20, 8, 0, "VOL", 128), Change(21, 8, 8, "VOL", 0),
        Change(22, Plus(0), 8, "VOL", -5), Notes(23, 0, 8, "lead", (69,), 255))


def test_placements_in_every_shape():
    read = score.read(song("(0, riff)", "(16, riff, 3)", "(32, riff, -12, 4)", "(+, riff)",
                           "(+8, free, 7)", "(0, free, 0, 1)"))
    assert read.song == (
        Placement(14, 0, "riff", 0, 1), Placement(15, 16, "riff", 3, 1),
        Placement(16, 32, "riff", -12, 4), Placement(17, Plus(0), "riff", 0, 1),
        Placement(18, Plus(8), "free", 7, 1), Placement(19, 0, "free", 0, 1))
    assert (read.patterns["riff"].length, read.patterns["free"].length) == (16, None)


def test_steps_and_a_tail_and_named_parts():
    read = score.read("STEPS = 24\nBPM = 90\nDEPTH = -3\n\nINSTRUMENT pad 35280:\n"
                      "    env = min(t, 4000) * decay(t - dur, 6000) >> 12\n"
                      "    wide = saw(p) + saw(p + (p >> DEPTH))\n"
                      "    wide * env * vel >> 26\nSONG:\n    (0, 8, A4, pad)\n")
    assert (read.bpm, read.steps, read.variables) == (90, 24, {"DEPTH": -3})
    pad = read.instruments["pad"]
    assert pad.tail == 35280 and list(pad.parts) == ["env", "wide"]
    assert pad.sample == expr.read("wide * env * vel >> 26", expr.NAMES + ("env", "wide"))
    tight = score.read("BPM=20\nSTEPS=96\nINSTRUMENT a 0:\n sin(p)\nSONG:\n (0,1,C0,a)\n")
    assert (tight.bpm, tight.steps, tight.song[0].keys) == (20, 96, (12,))


def test_two_instruments_may_each_have_a_part_of_one_name():
    read = score.read("BPM = 120\nINSTRUMENT a:\n    env = decay(t, 900)\n"
                      "    sin(p) * env >> 16\n"
                      "INSTRUMENT b:\n    env = decay(t, 5000)\n    saw(p) * env >> 16\n"
                      "SONG:\n    (0, 8, A4, a)\n    (0, 8, A4, b)\n")
    assert read.instruments["a"].parts != read.instruments["b"].parts


def test_comments_in_every_place_the_design_allows():
    read = score.read("# a tune\nBPM = 120\n\n# the lead\nINSTRUMENT lead:\n    # one sine\n"
                      "    sin(p)\n\t# with a tab\nSONG:\n    (0, 8, C#3, lead)    # a sharp\n"
                      "    (+, 8, A4, lead)# (and) a, comma\n#the end\n")
    assert read.song == (Notes(10, 0, 8, "lead", (49,), 255),
                         Notes(11, Plus(0), 8, "lead", (69,), 255))


def test_tabs_and_windows_line_ends_and_a_mark_at_the_start():
    text = ("BPM = 120\nINSTRUMENT lead:\n\tsin(p) * vel >> 8\nSONG:\n\t(0, 8, A4, lead)\n"
            "  \t (+, 8, B4, lead)\n")
    plain = score.read(text)
    assert plain.song == (Notes(5, 0, 8, "lead", (69,), 255),
                          Notes(6, Plus(0), 8, "lead", (71,), 255))
    assert score.read(text.replace("\n", "\r\n")) == plain
    assert score.read("\ufeff" + text) == plain
    assert score.read(text.rstrip("\n")) == plain and score.read(text + "\n\n   \n") == plain


def test_everything_is_declared_above_the_line_that_uses_it():
    late = ("BPM = 120\nINSTRUMENT lead:\n    sin(p) * VOL >> 8\nVOL = 255\nSONG:\n"
            "    (0, 8, A4, lead)\n")
    assert problems(late) == ["line 3: unknown name VOL"]
    assert problems("BPM = 120\nSONG:\n    (0, 8, A4, lead)\n") == [
        "line 3: unknown instrument or variable: lead"]
    below = "INSTRUMENT lead:\n    sin(p)\nBPM = 120\nSONG:\n    (0, 8, A4, lead)\n"
    assert score.read(below).bpm == 120                  # a setting is used by no line


# ---------------------------------------------------------------- the problems

@pytest.mark.parametrize("text, expected", [
    # a line that fits nothing
    (HEAD + "what is this\n" + PLAYS, ["line 13: can't read this line"]),
    (HEAD + "(0, 8, A4, lead)\n" + PLAYS,
     ["line 13: this line must be indented: it belongs to a PATTERN or to SONG:"]),
    (HEAD + "pattern x 8:\n    (0, 8, A4, lead)\n" + PLAYS,
     ["line 13: the keywords are in upper case: write PATTERN"]),
    (song("(0, riff)", "0, 8, A4, lead"),
     ["line 15: can't read this line: an event is (start, duration, value, target, velocity), "
      "in brackets"]),
    (song("(0, 8, A4, lead"), ["line 14: the ) is missing"]),
    (song("(0, 8, A4, lead) loud"),
     ["line 14: only a comment, with a # in front, can follow the )"]),
    # an indented line with no block above it
    ("BPM = 120\n    sin(p)\nINSTRUMENT lead:\n    sin(p)\nSONG:\n    (0, 8, A4, lead)\n",
     ["line 2: this line belongs to nothing: it is indented, and no INSTRUMENT, PATTERN or SONG "
      "is above it"]),
    # the settings
    ("BPM = 100\n" + HEAD + PLAYS, ["line 2: BPM is set twice"]),
    (HEAD.replace("VOL = 255", "STEPS = 8\nSTEPS = 8") + PLAYS, ["line 3: STEPS is set twice"]),
    (HEAD.replace("120", "401") + PLAYS, ["line 1: BPM must be between 20 and 400"]),
    (HEAD.replace("120", "19") + PLAYS, ["line 1: BPM must be between 20 and 400"]),
    (HEAD.replace("VOL = 255", "STEPS = 0") + PLAYS, ["line 2: STEPS must be between 1 and 96"]),
    (HEAD.replace("VOL = 255", "STEPS = 97") + PLAYS, ["line 2: STEPS must be between 1 and 96"]),
    (HEAD.replace("120", "fast") + PLAYS, ["line 1: BPM is a whole number, not fast"]),
    (HEAD.replace("255", "0.5") + PLAYS, ["line 2: the value of VOL is a whole number, not 0.5"]),
    (HEAD.replace("255", "0xFF") + PLAYS, ["line 2: the value of VOL is a whole number, not 0xFF"]),
    (HEAD.replace("255", "") + PLAYS, ["line 2: the value of VOL is a whole number, not nothing"]),
    (HEAD.replace("255", "9223372036854775808") + PLAYS,
     ["line 2: the number 9223372036854775808 doesn't fit 64 bits"]),
    (HEAD.replace("255", "1" * 30) + PLAYS,
     [f"line 2: the number {'1' * 30} doesn't fit 64 bits"]),
    (HEAD.replace("BPM = 120", "bpm = 120") + PLAYS, ["the file has no BPM"]),
    # names
    (HEAD + "sin = 5\n" + PLAYS, ["line 13: sin is a taken name"]),
    (HEAD + "t = 5\n" + PLAYS, ["line 13: t is a taken name"]),
    (HEAD + "SONG = 5\n" + PLAYS, ["line 13: SONG is a taken name"]),
    (HEAD + "INSTRUMENT key:\n    sin(p)\n" + PLAYS, ["line 13: key is a taken name"]),
    (HEAD + "PATTERN BPM:\n    (0, riff)\n" + PLAYS, ["line 13: BPM is a taken name"]),
    (HEAD + "A4 = 3\n" + PLAYS, ["line 13: A4 is a note name, and can't be declared"]),
    (HEAD + "INSTRUMENT Bb3:\n    sin(p)\n" + PLAYS,
     ["line 13: Bb3 is a note name, and can't be declared"]),
    (HEAD + "C10 = 3\n" + PLAYS, ["line 13: C10 is a note name, and can't be declared"]),
    (HEAD + "INSTRUMENT lead:\n    sin(p)\n" + PLAYS,
     ["line 13: lead is declared twice (first on line 4)"]),
    (HEAD + "VOL = 3\n" + PLAYS, ["line 13: VOL is declared twice (first on line 2)"]),
    (HEAD + "PATTERN lead:\n    (0, riff)\n" + PLAYS,
     ["line 13: lead is declared twice (first on line 4)"]),
    (HEAD + "riff = 1\n" + PLAYS, ["line 13: riff is declared twice (first on line 7)"]),
    (HEAD + "2nd = 1\n" + PLAYS,
     ["line 13: 2nd isn't a name: a name is letters, digits and _, and starts with a letter"]),
    (HEAD + "INSTRUMENT my-lead:\n    sin(p)\n" + PLAYS,
     ["line 13: my-lead isn't a name: a name is letters, digits and _, and starts with a letter"]),
    # instruments
    (HEAD + "INSTRUMENT pad:\n" + PLAYS, ["line 13: INSTRUMENT pad has no expression"]),
    (HEAD + "INSTRUMENT pad:\n    env = decay(t, 900)\n" + PLAYS,
     ["line 13: INSTRUMENT pad has no expression"]),
    (HEAD + "INSTRUMENT pad:\n    sin(p) * CUTOF >> 8\n" + PLAYS, ["line 14: unknown name CUTOF"]),
    (HEAD + "INSTRUMENT pad:\n    env = decay(t)\n    sin(p) * env >> 16\n" + PLAYS,
     ["line 14: decay takes 2 values, not 1"]),
    (HEAD + "INSTRUMENT pad:\n    sin(p) * 0.5\n" + PLAYS,
     ["line 14: whole numbers only: multiply first, then divide"]),
    (HEAD + "INSTRUMENT pad:\n    sin(p)   # a sine\n" + PLAYS,
     ["line 14: a comment can't follow an expression: put it on a line of its own"]),
    (HEAD + "INSTRUMENT pad:\n    env = decay(t, 900)  # dies\n    sin(p) * env >> 16\n" + PLAYS,
     ["line 14: a comment can't follow an expression: put it on a line of its own"]),
    (HEAD + "INSTRUMENT pad:  # soft\n    sin(p)\n" + PLAYS,
     ["line 13: a comment can't follow this line: put it on a line of its own"]),
    (HEAD + "CUT = 9  # bright\n" + PLAYS,
     ["line 13: a comment can't follow this line: put it on a line of its own"]),
    (HEAD + "INSTRUMENT pad:\n    sin(p)\n    saw(p)\n" + PLAYS,
     ["line 15: the expression on line 14 has to be the last line of INSTRUMENT pad"]),
    (HEAD + "INSTRUMENT pad:\n    sin(p)\n    env = decay(t, 900)\n" + PLAYS,
     ["line 15: the expression on line 14 has to be the last line of INSTRUMENT pad"]),
    (HEAD + "INSTRUMENT pad:\n    env = 1\n    env = 2\n    env\n" + PLAYS,
     ["line 15: env is declared twice (first on line 14)"]),
    (HEAD + "INSTRUMENT pad:\n    VOL = 1\n    VOL\n" + PLAYS,
     ["line 14: VOL is declared twice (first on line 2)"]),
    (HEAD + "INSTRUMENT pad:\n    vel = 1\n    vel\n" + PLAYS, ["line 14: vel is a taken name"]),
    (HEAD + "INSTRUMENT pad:\n    A4 = 1\n    A4\n" + PLAYS,
     ["line 14: A4 is a note name, and can't be declared"]),
    (HEAD + "INSTRUMENT pad:\n    late + 1\n    late = 3\n" + PLAYS,
     ["line 14: unknown name late",
      "line 15: the expression on line 14 has to be the last line of INSTRUMENT pad"]),
    (HEAD + "INSTRUMENT pad\n    sin(p)\n" + PLAYS,
     ["line 13: INSTRUMENT needs a : at the end of its line"]),
    (HEAD + "INSTRUMENT:\n    sin(p)\n" + PLAYS,
     ["line 13: an instrument starts with INSTRUMENT name: or INSTRUMENT name tail:"]),
    (HEAD + "INSTRUMENT soft pad 100:\n    sin(p)\n" + PLAYS,
     ["line 13: an instrument starts with INSTRUMENT name: or INSTRUMENT name tail:"]),
    (HEAD + "INSTRUMENT pad 441001:\n    sin(p)\n" + PLAYS,
     ["line 13: a tail is 0 to 441000 samples"]),
    (HEAD + "INSTRUMENT pad -1:\n    sin(p)\n" + PLAYS, ["line 13: a tail is 0 to 441000 samples"]),
    (HEAD + "INSTRUMENT pad long:\n    sin(p)\n" + PLAYS,
     ["line 13: a tail is a whole number, not long"]),
    # events
    (song("(0, 8, A4)"), ["line 14: an event is (start, duration, value, target, velocity)"]),
    (song("(0, 8, A4, lead, 100, 3)"),
     ["line 14: an event is (start, duration, value, target, velocity)"]),
    (song("(0)"), ["line 14: an event is (start, duration, value, target, velocity)"]),
    (song("()"), ["line 14: an event is (start, duration, value, target, velocity)"]),
    (song("(0, 8, , lead)"), ["line 14: an event is (start, duration, value, target, velocity)"]),
    (song("(0, A4, lead)"), ["line 14: an event is (start, duration, value, target, velocity)"]),
    (song("(0, lead, A4)"), ["line 14: an event is (start, duration, value, target, velocity)"]),
    (song("(0, 8.5, A4, lead)"),
     ["line 14: the second field is a duration or a pattern's name, not 8.5"]),
    (song("(0, 8, A4, laed)"), ["line 14: unknown instrument or variable: laed"]),
    (song("(0, 8, A4, riff)"), ["line 14: riff is a pattern: place it with (0, riff)"]),
    (song("(0, 8, A4, VOL)"), ["line 14: VOL is a variable: its value is a number, not A4"]),
    (song("(0, 8, 128, lead)"),
     ["line 14: lead is an instrument: its value is a note such as A4, not 128"]),
    (song("(0, 8, a4, lead)"),
     ["line 14: lead is an instrument: its value is a note such as A4, not a4"]),
    (song("(0, 8, C3 E G3, lead)"),
     ["line 14: lead is an instrument: its value is a note such as A4, not C3 E G3"]),
    (song("(0, 8, 1 2, VOL)"), ["line 14: a change to a variable has one value"]),
    (song("(0, 8, 5, VOL, 100)"), ["line 14: a change to a variable has one value"]),
    (song("(0, 8, A4, lead, 256)"), ["line 14: a velocity is 0 to 255"]),
    (song("(0, 8, A4, lead, -1)"), ["line 14: a velocity is 0 to 255"]),
    (song("(0, 8, A4, lead, loud)"), ["line 14: a velocity is a whole number, not loud"]),
    (song("(0, 8, C10, lead)"), ["line 14: C10 is outside C0 to B9"]),
    (song("(0, 8, C3 B#9, lead)"), ["line 14: B#9 is outside C0 to B9"]),
    (song("(0, 8, Cb0, lead)"), ["line 14: Cb0 is outside C0 to B9"]),
    (song("(0, 8, C-1, lead)"), ["line 14: C-1 is outside C0 to B9"]),
    (song("(0, 0, A4, lead)"), ["line 14: a note needs a duration of 1 or more"]),
    (song("(0, -8, A4, lead)"), ["line 14: a note needs a duration of 1 or more"]),
    (song("(0, -8, 3, VOL)"), ["line 14: a duration is 0 or more"]),
    (song("(-1, 8, A4, lead)"), ["line 14: a start is 0 or more"]),
    (song("(x, 8, A4, lead)"), ["line 14: a start is a whole number or +, not x"]),
    (song("(0, 8, 1.5, VOL)"), ["line 14: VOL is a variable: its value is a number, not 1.5"]),
    # +
    (song("(+, 8, A4, lead)"), ["line 14: + has no line above it to count from"]),
    (song("(+4, riff)"), ["line 14: + has no line above it to count from"]),
    (song("(0, free)", "(+, 8, A4, lead)"),
     ["line 15: + can't count from free: that pattern has no length"]),
    (song("(0, free, 5)", "(+2, riff)"),
     ["line 15: + can't count from free: that pattern has no length"]),
    # placements
    (HEAD + "PATTERN verse:\n    (0, chorus)\nPATTERN chorus:\n    (0, riff)\n" + PLAYS,
     ["line 14: chorus isn't declared above this line"]),
    (song("(0, rif)"), ["line 14: rif isn't declared above this line"]),
    (HEAD + "PATTERN verse:\n    (0, riff)\n    (16, verse)\n" + PLAYS,
     ["line 15: verse can't be placed inside itself"]),
    (song("(0, free, 0, 2)"), ["line 14: free has no length, so it can't be repeated"]),
    (song("(0, riff, 0, 0)"), ["line 14: a pattern is placed 1 time or more"]),
    (song("(0, riff, 1, 2, 3)"), ["line 14: a placement is (start, pattern, transpose, times)"]),
    (song("(0, riff, up)"), ["line 14: a transposition is a whole number, not up"]),
    (song("(0, riff, 0, twice)"), ["line 14: the number of times is a whole number, not twice"]),
    (HEAD + "PATTERN bar 0:\n    (0, riff)\n" + PLAYS,
     ["line 13: a pattern's length is 1 or more"]),
    (HEAD + "PATTERN bar long:\n    (0, riff)\n" + PLAYS,
     ["line 13: a pattern's length is a whole number, not long"]),
    (HEAD + "PATTERN a b c:\n    (0, riff)\n" + PLAYS,
     ["line 13: a pattern starts with PATTERN name: or PATTERN name length:"]),
    # the song, and empty blocks
    (HEAD, ["the file has no SONG:"]),
    (HEAD + PLAYS + PLAYS, ["line 15: SONG: is declared twice (first on line 13)"]),
    (HEAD + PLAYS + "PATTERN late:\n    (0, riff)\n", ["line 15: SONG: must be the last block"]),
    (HEAD + PLAYS + "INSTRUMENT late:\n    sin(p)\n", ["line 15: SONG: must be the last block"]),
    (HEAD + PLAYS + "LATE = 1\n", ["line 15: SONG: must be the last block"]),
    (HEAD + "SONG main:\n    (0, riff)\n", ["line 13: SONG: has no name"]),
    (HEAD + "SONG\n    (0, riff)\n", ["line 13: SONG needs a : at the end of its line"]),
    (HEAD + "SONG:\n", ["line 13: SONG: is empty"]),
    (HEAD + "SONG:\n    # nothing yet\n", ["line 13: SONG: is empty"]),
    (HEAD + "PATTERN nothing 8:\n" + PLAYS, ["line 13: PATTERN nothing is empty"]),
    ("", ["the file has no BPM", "the file has no SONG:"]),
    ("# only a comment\n\n", ["the file has no BPM", "the file has no SONG:"]),
])
def test_a_problem_has_its_line_and_says_what_to_write(text, expected):
    assert problems(text) == expected


def test_an_event_cant_change_a_named_part():
    text = HEAD.replace("    sin(p) * vel >> 8",
                        "    env = decay(t, 900)\n    sin(p) * env >> 16")
    assert problems(text + "SONG:\n    (0, 8, 5, env)\n") == [
        "line 15: env is a named part of an instrument: an event can't change it"]


def test_an_instrument_may_have_sixteen_named_parts():
    def instrument(parts):
        lines = "".join(f"    part{n} = {n}\n" for n in range(parts))
        return f"BPM = 120\nINSTRUMENT many:\n{lines}    part0\nSONG:\n    (0, 8, A4, many)\n"

    assert len(score.read(instrument(16)).instruments["many"].parts) == 16 == limits.PARTS
    assert problems(instrument(17)) == ["line 19: INSTRUMENT many has more than 16 named parts"]


def test_three_mistakes_come_back_as_three_problems_in_order():
    text = (HEAD.replace("sin(p) * vel >> 8", "sin(p) * CUTOF >> 8")
            + "SONG:\n    (0, 8, A4, laed)\n    (0, riff)\n    (0, 8, A4, lead, 300)\n")
    assert problems(text) == ["line 5: unknown name CUTOF",
                              "line 14: unknown instrument or variable: laed",
                              "line 16: a velocity is 0 to 255"]
    with pytest.raises(ScoreError, match="^line 5: unknown name CUTOF\nline 14: unknown instr"):
        score.read(text)


def test_a_line_has_one_problem_at_most():
    assert problems(song("(-1, 0, H4, laed, 999) junk")) == [
        "line 14: only a comment, with a # in front, can follow the )"]
    assert problems(HEAD + "INSTRUMENT sin 9999999: # x\n    sin(p)\n" + PLAYS) == [
        "line 13: a comment can't follow this line: put it on a line of its own"]


def test_one_mistake_doesnt_make_the_lines_below_it_wrong():
    # A part, an instrument and a pattern with a problem are still declared, an instrument
    # with a bad header still has its lines read, and + counts on after a bad line.
    text = ("BPM = 120\nINSTRUMENT lead:\n    env = decay(t)\n    sin(p) * env >> 16\n"
            "INSTRUMENT sin:\n    saw(p) * CUTOF\nPATTERN riff x:\n    (0, 8, A4, lead)\n"
            "SONG:\n    (0, 8, A4, lead)\n    (0, 8, H4, lead)\n    (+, riff)\n")
    assert problems(text) == ["line 3: decay takes 2 values, not 1",
                              "line 5: sin is a taken name",
                              "line 6: unknown name CUTOF",
                              "line 7: a pattern's length is a whole number, not x",
                              "line 11: lead is an instrument: its value is a note such as A4, "
                              "not H4"]


def test_more_problems_than_the_limit_end_with_how_many_more():
    bad = [f"(0, 8, A4, nobody{n})" for n in range(27)]
    found = problems(song(*bad))
    assert len(found) == 27 and limits.PROBLEMS == 20
    with pytest.raises(ScoreError) as raised:
        score.read(song(*bad))
    lines = str(raised.value).split("\n")
    assert lines[:20] == found[:20] and lines[20:] == ["… and 7 more"]
    assert "more" not in "\n".join(problems(song(*bad[:20])))        # exactly the limit: all


def test_a_long_problem_is_cut_short():
    long_name = "x" * 400
    with pytest.raises(ScoreError) as raised:
        score.read(song(f"(0, 8, A4, {long_name})"))
    assert len(str(raised.value)) == limits.PROBLEM_CHARS == 160
    assert str(raised.value).startswith("line 14: unknown instrument or variable: xxxx")
    assert str(raised.value).endswith("xxx…")
    assert raised.value.problems == [f"line 14: unknown instrument or variable: {long_name}"]


def test_a_file_that_is_too_big_isnt_read():
    assert limits.SCORE_BYTES == 65536
    fits = HEAD + PLAYS + "#" * (65536 - len(HEAD + PLAYS))
    assert score.read(fits).bpm == 120
    assert problems(fits + "#") == ["the score is bigger than 65536 bytes"]
    assert problems("é" * 40000) == ["the score is bigger than 65536 bytes"]    # in bytes


def test_the_taken_names_are_the_designs():
    assert score.TAKEN == {"t", "p", "vel", "dur", "key", "sin", "saw", "square", "tri", "noise",
                           "decay", "min", "max", "abs", "BPM", "STEPS", "INSTRUMENT", "PATTERN",
                           "SONG"}
