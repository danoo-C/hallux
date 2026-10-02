"""Unfolding a score: addons/music_engine/song.py. Patterns, chords and + become notes and
changes, timed in samples. Nothing here needs numpy, apart from the one test that loads the
reference render."""
import contextlib
import importlib.util
import io
from pathlib import Path

import pytest
from music_engine import limits, score, song
from music_engine.score import ScoreError
from music_engine.song import Glide, Note

SCORES = Path(__file__).parent / "scores"
REFERENCE = Path(__file__).resolve().parent.parent / "docs/plans/addon-music/reference"

# Nine lines that the tests below build on: what follows starts on line 10.
HEAD = """\
BPM = 120
VOL = 255

INSTRUMENT lead:
    sin(p) * vel >> 8

INSTRUMENT pad 35280:
    sin(p) * decay(t - dur, 6000) * vel >> 24

"""


def unfold(text):
    return song.unfold(score.read(text))


def tune(*lines, head=HEAD):
    """HEAD and a song of these lines: SONG: is line 10, and the first of them line 11."""
    return unfold(head + "SONG:\n" + "".join(f"    {line}\n" for line in lines))


def problems(text):
    with pytest.raises(ScoreError) as raised:
        unfold(text)
    return raised.value.problems


def names(notes):
    return [score.name_of(note.key) for note in notes]


STEP = 11025 // 4                             # a step at 120 BPM is 2756.25 samples


def at(step):
    """The sample of a step at 120 BPM and 8 steps to the quarter note."""
    return (2 * step * 11025 + 4) // 8


# ---------------------------------------------------------------- the design's scores

def test_chords_and_a_melody_unfolds_to_24_notes():
    read = score.read((SCORES / "chords-and-melody.score").read_text())
    unfolded = song.unfold(read)
    assert len(unfolded.notes) == 24 and unfolded.changes == {}
    lead = [note for note in unfolded.notes if note.instrument == "lead"]
    assert lead[0] == Note(0, 26460, 60, "lead", 140)                # C4: 8 steps at 100 BPM
    assert names(lead) == ["C4", "G4", "C5", "G3", "D4", "G4", "A3", "E4", "A4", "F3", "C4", "F4"]
    assert [note.length for note in lead] == [26460, 26460, 52920] * 4
    assert [note.start for note in lead[:4]] == [0, 26460, 52920, 105840]
    bars = [[note for note in unfolded.notes if note.instrument == "pad" and note.start == start]
            for start in (0, 105840, 211680, 317520)]
    assert [names(bar) for bar in bars] == [["C3", "E3", "G3"], ["G2", "B2", "D3"],
                                           ["A2", "C3", "E3"], ["F2", "A2", "C3"]]
    assert {(note.length, note.velocity) for bar in bars for note in bar} == {(105840, 60)}
    assert unfolded.end == unfolded.length == 423360                 # 9.6 seconds


def test_the_same_piece_with_automation_unfolds():
    unfolded = unfold((SCORES / "automation.score").read_text())
    assert len(unfolded.notes) == 24
    assert unfolded.changes["VOL"] == (Glide(0, 26460, 255), Glide(370440, 423360, 0))
    bright = unfolded.changes["BRIGHT"]                              # twice in each of four bars
    assert bright[:2] == (Glide(0, 79380, 255), Glide(79380, 105840, 0)) and len(bright) == 8
    assert [glide.first for glide in bright[::2]] == [0, 105840, 211680, 317520]
    assert {glide.value for glide in bright[1::2]} == {0}            # transposing left them alone
    assert unfolded.end == unfolded.length == 423360


def test_the_drum_beat_unfolds_to_40_notes():
    unfolded = unfold((SCORES / "drum-beat.score").read_text())
    assert len(unfolded.notes) == 40
    assert unfolded.end == unfolded.length == 352800                 # 8 seconds
    assert unfolded.notes[0] == Note(0, 11025, 33, "kick", 255)
    kicks = [note.start for note in unfolded.notes if note.instrument == "kick"]
    assert kicks == [beat * 44100 for beat in range(8)]              # every second beat, at 120
    hats = {note.velocity for note in unfolded.notes if note.instrument == "hat"}
    assert hats == {90, 150}


def test_the_scores_unfold_to_the_notes_that_were_heard():
    """The throwaway render placed its notes by hand: the same notes, at the same samples."""
    pytest.importorskip("numpy")
    spec = importlib.util.spec_from_file_location("reference_scores", REFERENCE / "scores.py")
    reference = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(reference)

    def theirs(notes, bpm):
        samples_per_step = 44100 * 60 / bpm / 8
        found = []
        for start, duration, note, instrument, velocity in notes:
            first = int(round(start * samples_per_step))
            last = int(round((start + duration) * samples_per_step))
            key = reference.key(note) if isinstance(note, str) else note
            found.append((first, last - first, key, instrument.__name__, velocity))
        return sorted(found)

    def ours(name):
        return sorted((note.start, note.length, note.key, note.instrument, note.velocity)
                      for note in unfold((SCORES / name).read_text()).notes)

    assert ours("chords-and-melody.score") == theirs(reference.song1(reference.lead, 60, 140), 100)
    assert ours("drum-beat.score") == theirs(reference.place(reference.beat, 0, 0, 4), 120)


def test_patterns_inside_patterns_unfold():
    """Two events, one line in bar and one in SONG give 16 bars: 128 notes."""
    unfolded = unfold("BPM = 120\nINSTRUMENT kick:\n    sin(p)\nINSTRUMENT hat:\n    noise(t)\n"
                      "PATTERN beat 8:\n    (0, 2, C2, kick)\n    (4, 1, C6, hat)\n"
                      "PATTERN bar 32:\n    (0, beat, 0, 4)\nSONG:\n    (0, bar, 0, 16)\n")
    assert len(unfolded.notes) == 128
    kicks = [note.start for note in unfolded.notes if note.instrument == "kick"]
    assert kicks == [beat * 22050 for beat in range(64)]             # on every beat
    assert unfolded.end == unfolded.length == 16 * 32 * 11025 // 4   # the song ends on the bar


# ---------------------------------------------------------------- steps and samples

def test_a_step_is_worked_out_from_itself_so_nothing_drifts():
    """A step isn't a whole number of samples. At 120 BPM a 32nd note is 2756.25 samples."""
    read = score.read(HEAD + "SONG:\n    (0, 8, A4, lead)\n")
    assert [song.sample_of(step, read) for step in (0, 1, 2, 3, 4)] == [0, 2756, 5513, 8269, 11025]
    assert song.sample_of(4000, read) == 1000 * song.sample_of(4, read) == 11_025_000
    assert [at(step) for step in (1, 2, 3, 4, 4000)] == [2756, 5513, 8269, 11025, 11_025_000]


def test_a_notes_length_is_its_end_minus_its_start():
    unfolded = tune("(0, 1, A4, lead)", "(1, 1, A4, lead)", "(2, 1, A4, lead)", "(3, 1, A4, lead)")
    assert [(note.start, note.length) for note in unfolded.notes] == [
        (0, 2756), (2756, 2757), (5513, 2756), (8269, 2756)]         # together: a quarter beat
    assert unfolded.end == 11025


def test_a_half_is_rounded_up():
    # At 100 BPM a step is 3307.5 samples.
    unfolded = tune("(1, 2, A4, lead)", "(3, 1, A4, lead)", head=HEAD.replace("120", "100"))
    assert [(note.start, note.length) for note in unfolded.notes] == [(3308, 6615), (9923, 3307)]


def test_steps_of_24_make_triplets():
    """STEPS = 24 makes triplets possible: an eighth-note triplet is 8 steps."""
    unfolded = tune("(0, 8, C4, lead)", "(+, 8, E4, lead)", "(+, 8, G4, lead)",
                    head=HEAD.replace("VOL = 255", "STEPS = 24"))
    assert [(note.start, note.length) for note in unfolded.notes] == [
        (0, 7350), (7350, 7350), (14700, 7350)]                      # three in one beat
    assert unfolded.end == 22050


def test_the_slowest_and_the_fastest_song():
    slowest = HEAD.replace("120", "20").replace("VOL = 255", "STEPS = 1")
    slow = tune("(0, 1, A4, lead)", head=slowest)
    assert slow.notes == (Note(0, 132300, 69, "lead", 255),)         # one beat: three seconds
    fastest = HEAD.replace("120", "400").replace("VOL = 255", "STEPS = 96")
    fast = tune("(1, 1, A4, lead)", head=fastest)
    assert fast.notes == (Note(69, 69, 69, "lead", 255),)            # a step of 68.9 samples


# ---------------------------------------------------------------- + and patterns

def test_plus_counts_from_the_end_of_the_line_above():
    unfolded = tune("(0, 8, C4, lead)",        # 0 to 8
                    "(+, 8, D4, lead)",        # 8 to 16
                    "(+4, 8, E4, lead)",       # a rest of 4: 20 to 28
                    "(+, 4, F4, lead, 75)",    # 28 to 32
                    "(64, 8, G4, lead)",       # a number starts a new count
                    "(+, 8, A4, lead)",        # 72 to 80
                    "(+0, 8, 0, VOL)",         # a change counts too: 80 to 88
                    "(+, 8, B4, lead)")        # 88 to 96
    assert [(note.start, note.length) for note in unfolded.notes] == [
        (at(0), at(8)), (at(8), at(8)), (at(20), at(8)), (at(28), at(4)), (at(64), at(8)),
        (at(72), at(8)), (at(88), at(8))]
    assert names(unfolded.notes) == ["C4", "D4", "E4", "F4", "G4", "A4", "B4"]
    assert unfolded.changes == {"VOL": (Glide(at(80), at(88), 0),)}
    assert unfolded.end == at(96)


def test_plus_counts_from_a_placed_patterns_length_times_its_repeats():
    unfolded = unfold(HEAD + "PATTERN riff 16:\n    (0, 4, C4, lead)\n    (+, 4, E4, lead)\n"
                      "SONG:\n    (0, riff, 0, 3)\n    (+, 8, G4, lead)\n    (+8, riff, 12)\n")
    assert [(note.start, score.name_of(note.key)) for note in unfolded.notes] == [
        (at(0), "C4"), (at(4), "E4"), (at(16), "C4"), (at(20), "E4"), (at(32), "C4"),
        (at(36), "E4"), (at(48), "G4"), (at(64), "C5"), (at(68), "E5")]
    assert unfolded.end == at(80)


def test_a_chord_is_one_note_for_each_name():
    unfolded = tune("(0, 32, C3 E3 G3, pad, 60)")
    assert unfolded.notes == tuple(Note(0, at(32), key, "pad", 60) for key in (48, 52, 55))


def test_transposing_moves_the_notes_and_leaves_the_changes():
    unfolded = unfold(HEAD + "PATTERN riff 16:\n    (0, 8, A4, lead)\n    (0, 8, 128, VOL)\n"
                      "SONG:\n    (0, riff)\n    (16, riff, -12)\n    (32, riff, 7)\n")
    assert names(unfolded.notes) == ["A4", "A3", "E5"]
    assert unfolded.changes == {"VOL": (Glide(at(0), at(8), 128), Glide(at(16), at(24), 128),
                                        Glide(at(32), at(40), 128))}


def test_a_pattern_placed_in_a_pattern_adds_both_starts_and_both_transpositions():
    unfolded = unfold(HEAD + "PATTERN note:\n    (2, 4, C4, lead)\n"
                      "PATTERN pair 16:\n    (0, note, 4)\n    (8, note, 7)\n"
                      "SONG:\n    (32, pair, 12)\n    (64, pair, -12, 2)\n")
    assert [(note.start, score.name_of(note.key)) for note in unfolded.notes] == [
        (at(34), "E5"), (at(42), "G5"), (at(66), "E3"), (at(74), "G3"), (at(82), "E3"),
        (at(90), "G3")]
    assert unfolded.end == at(96)


def test_a_pattern_without_a_length_ends_where_what_is_in_it_ends():
    unfolded = unfold(HEAD + "PATTERN free:\n    (0, 8, A4, lead)\n    (8, 4, B4, lead)\n"
                      "SONG:\n    (100, free)\n")
    assert unfolded.end == at(112)


def test_the_order_of_the_lines_doesnt_matter():
    forwards = tune("(0, 8, C4, lead)", "(8, 8, D4, lead)", "(16, 8, 0, VOL)", "(32, 0, 9, VOL)")
    backwards = tune("(32, 0, 9, VOL)", "(16, 8, 0, VOL)", "(8, 8, D4, lead)", "(0, 8, C4, lead)")
    assert forwards == backwards
    assert [note.start for note in forwards.notes] == [0, at(8)]     # by their first sample
    assert forwards.changes["VOL"] == (Glide(at(16), at(24), 0), Glide(at(32), at(32), 9))


# ---------------------------------------------------------------- where the song ends

def test_the_song_ends_at_the_last_step_that_anything_reaches():
    """A bar of drums whose last note ends early still ends on the bar."""
    unfolded = unfold(HEAD + "PATTERN bar 32:\n    (0, 4, A4, lead)\nSONG:\n    (0, bar)\n")
    assert unfolded.notes == (Note(0, at(4), 69, "lead", 255),)
    assert unfolded.end == unfolded.length == at(32)
    rings = unfold(HEAD + "PATTERN bar 32:\n    (28, 16, A4, lead)\nSONG:\n    (0, bar)\n")
    assert rings.end == at(44)                                       # a note may ring past it
    fades = tune("(0, 8, A4, lead)", "(8, 24, 0, VOL)")
    assert fades.end == at(32)                                       # a glide reaches too


def test_a_song_that_plays_once_goes_on_until_the_last_tail_is_over():
    unfolded = tune("(0, 8, A4, pad)")                               # pad has a tail of 35280
    assert unfolded.end == at(8) and unfolded.length == at(8) + 35280
    early = tune("(0, 8, A4, pad)", "(0, 32, A4, lead)")             # the tail ends before the end
    assert early.end == early.length == at(32)
    assert tune("(0, 8, A4, pad)", "(0, 8, A4, lead)").length == at(8) + 35280


def test_every_variable_has_its_changes_even_if_none():
    assert tune("(0, 8, A4, lead)").changes == {"VOL": ()}
    assert tune("(0, 8, A4, lead)", "(4, 0, 7, VOL)").changes == {"VOL": (Glide(at(4), at(4), 7),)}


def test_two_changes_that_are_the_same_count_as_one():
    """A pattern that changes a variable can then be played on top of itself, such as a riff
    and the same riff four semitones up."""
    unfolded = unfold(HEAD + "PATTERN riff 16:\n    (0, 8, A4, lead)\n    (0, 8, 128, VOL)\n"
                      "SONG:\n    (0, riff)\n    (0, riff, 4)\n")
    assert names(unfolded.notes) == ["A4", "C#5"]
    assert unfolded.changes == {"VOL": (Glide(0, at(8), 128),)}


def test_a_change_may_start_while_another_still_glides():
    unfolded = tune("(0, 8, A4, lead)", "(0, 16, 0, VOL)", "(8, 8, 200, VOL)")
    assert unfolded.changes == {"VOL": (Glide(0, at(16), 0), Glide(at(8), at(16), 200))}


# ---------------------------------------------------------------- the problems

def test_a_note_cant_leave_c0_to_b9_by_transposing():
    riff = HEAD + "PATTERN riff 16:\n    (0, 8, C5, lead)\n    (8, 8, C1, lead)\n"
    assert unfold(riff + "SONG:\n    (0, riff, 59)\n").notes[0].key == 131      # B9 itself
    assert problems(riff + "SONG:\n    (0, riff, 40)\n    (16, riff, 60)\n") == [
        "line 15: riff moved up by 60 puts C5 (line 11) above B9"]
    assert unfold(riff + "SONG:\n    (0, riff, -12)\n").notes[1].key == 12      # C0 itself
    assert problems(riff + "SONG:\n    (0, riff, -13)\n") == [
        "line 14: riff moved down by 13 puts C1 (line 12) below C0"]
    nested = (riff + "PATTERN verse 32:\n    (0, riff, 30)\n"
              "SONG:\n    (0, verse)\n    (32, verse, 30)\n")              # 30 and 30 add up
    assert problems(nested) == ["line 14: riff moved up by 60 puts C5 (line 11) above B9"]


def test_two_different_changes_to_a_variable_at_one_step():
    """Two different changes to one variable at the same step are refused, because it's
    unclear which should win."""
    plays = HEAD + "SONG:\n    (0, 8, A4, lead)\n    (8, 8, 0, VOL)\n"
    assert problems(plays + "    (8, 8, 255, VOL)\n") == [
        "line 12 and line 13: two different changes to VOL at step 8"]
    assert problems(plays + "    (8, 0, 0, VOL)\n") == [                # a glide and a jump
        "line 12 and line 13: two different changes to VOL at step 8"]
    riff = HEAD + "PATTERN riff 16:\n    (0, 8, A4, lead)\n    (4, 8, 128, VOL)\n"
    assert problems(riff + "SONG:\n    (4, 8, 0, VOL)\n    (0, riff)\n    (16, riff)\n") == [
        "line 12 and line 14: two different changes to VOL at step 4"]


def test_the_song_has_a_most_of_events(monkeypatch):
    monkeypatch.setattr(limits, "EVENTS", 12)
    riff = HEAD + "PATTERN riff 16:\n    (0, 8, C4 E4 G4, lead)\n    (0, 8, 128, VOL)\n"
    assert len(unfold(riff + "SONG:\n    (0, riff, 0, 3)\n").notes) == 9          # 12 events
    assert problems(riff + "SONG:\n    (0, riff, 0, 3)\n    (48, 8, A4, lead)\n") == [
        "line 15: the song has more than 12 events"]
    assert problems(riff + "SONG:\n    (0, riff, 0, 2)\n    (32, riff, 0, 2)\n") == [
        "line 15: the song has more than 12 events"]


def test_a_small_file_cant_make_a_million_notes():
    """The count of unfolded events is checked while unfolding, not after."""
    assert limits.EVENTS == 10_000
    huge = HEAD + ("PATTERN a 8:\n    (0, 8, A4, lead)\nPATTERN b 80:\n    (0, a, 0, 10)\n"
                   "PATTERN c 800:\n    (0, b, 0, 10)\nSONG:\n    (0, c, 0, 1000000000000)\n")
    assert problems(huge) == ["line 17: the song has more than 10000 events"]
    assert len(unfold(huge.replace("1000000000000", "5")).notes) == 500


def test_patterns_have_a_deepest_nesting():
    def nest(depth):
        text = HEAD + "PATTERN p1 8:\n    (0, 8, A4, lead)\n"
        for level in range(2, depth + 1):
            text += f"PATTERN p{level} 8:\n    (0, p{level - 1})\n"
        return text + f"SONG:\n    (0, p{depth})\n"

    assert limits.PATTERN_DEPTH == 8 and len(unfold(nest(8)).notes) == 1
    assert problems(nest(9)) == ["line 27: patterns are nested more than 8 deep"]
    assert problems(nest(12)) == ["line 27: patterns are nested more than 8 deep"]   # said once


def test_only_so_many_notes_sound_at_once(monkeypatch):
    monkeypatch.setattr(limits, "VOICES", 3)
    assert len(tune("(0, 8, C4 E4 G4, lead)", "(8, 8, C4 E4 G4, lead)").notes) == 6
    assert problems(HEAD + "SONG:\n    (0, 8, C4 E4 G4, lead)\n    (7, 8, C5, lead)\n") == [
        "line 12: more than 3 notes sound at step 7"]
    assert problems(HEAD + "SONG:\n    (16, 8, C5, lead)\n    (0, 32, C4 E4 G4 B4, lead)\n") == [
        "line 12: more than 3 notes sound at step 0"]
    # A tail still sounds, so it counts: pad rings for 35280 samples after its 8 steps.
    assert problems(HEAD + "SONG:\n    (0, 8, C4 E4 G4, pad)\n    (20, 8, C5, lead)\n") == [
        "line 12: more than 3 notes sound at step 20"]
    assert len(tune("(0, 8, C4 E4 G4, pad)", "(21, 8, C5, lead)").notes) == 4
    assert limits.VOICES == 3


def test_a_song_has_a_longest_length():
    assert limits.SONG_SECONDS == 300 and limits.VOICES == 64
    assert tune("(0, 4800, A4, lead)").length == 300 * 44100          # five minutes, at 120 BPM
    assert problems(HEAD + "SONG:\n    (0, 4801, A4, lead)\n") == [
        "the song is 301 seconds long, and the limit is 300"]
    assert problems(HEAD + "SONG:\n    (0, 8, A4, lead)\n    (13440, 0, 0, VOL)\n") == [
        "the song is 840 seconds long, and the limit is 300"]
    assert problems(HEAD + "SONG:\n    (0, 4800, A4, pad)\n") == [   # the tail counts
        "the song is 301 seconds long, and the limit is 300"]
    assert problems(HEAD + "SONG:\n    (9000000000000000000, 8, A4, lead)\n")[0].startswith(
        "the song is ")


def test_a_song_needs_a_note():
    assert problems(HEAD + "SONG:\n    (0, 8, 0, VOL)\n") == ["the song has no notes"]


def test_the_problems_come_in_the_order_of_their_lines():
    text = (HEAD + "PATTERN riff 16:\n    (0, 8, C5, lead)\n    (0, 8, 128, VOL)\n"
            "SONG:\n    (0, 8, 0, VOL)\n    (16, riff, 70)\n    (0, riff)\n")
    assert problems(text) == ["line 12 and line 14: two different changes to VOL at step 0",
                              "line 15: riff moved up by 70 puts C5 (line 11) above B9"]
    with pytest.raises(ScoreError, match="^line 12 and line 14: two diff.*\nline 15: riff moved"):
        unfold(text)
