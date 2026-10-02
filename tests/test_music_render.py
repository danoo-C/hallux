"""Rendering a song: addons/music_engine/render.py. The first tests compare with the throwaway
render whose samples the user listened to (docs/plans/addon-music/reference/scores.py)."""
import contextlib
import importlib.util
import io
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="numpy isn't installed (pip install -e '.[music]')")

import music_timing  # noqa: E402
from music_engine import compute, limits, render, score, song  # noqa: E402

pytestmark = pytest.mark.filterwarnings("error")      # numpy must never warn

SCORES = Path(__file__).parent / "scores"
REFERENCE = Path(__file__).resolve().parent.parent / "docs/plans/addon-music/reference"

# The pad with a tail of the design's section 3, as two chords: the fourth thing that was heard.
PAD = """\
BPM = 100

INSTRUMENT pad 35280:
    env = min(t, 4000) * decay(t - dur, 6000) >> 12
    (saw(p) + saw(p + (p >> 8)) + saw(p - (p >> 8))) * env * vel >> 26

SONG:
    (0, 20, C3 E3 G3, pad, 110)
    (22, 20, A2 C3 E3, pad, 110)
"""
# Eight lines to build on: a level that is the same in every sample, and a variable.
HEAD = """\
BPM = 120
X = 0

INSTRUMENT level:
    20000

INSTRUMENT follows:
    X
"""


def play(text, loop=False):
    read = score.read(text)
    return render.render(read, song.unfold(read), loop)


def tune(*lines, head=HEAD, loop=False):
    return play(head + "SONG:\n" + "".join(f"    {line}\n" for line in lines), loop)


def at(step):
    """The sample of a step at 120 BPM."""
    return (2 * step * 11025 + 4) // 8


def largest(samples):
    return int(np.abs(samples.astype(np.int64)).max())


# ---------------------------------------------------------------- the render that was heard

@pytest.fixture(scope="module")
def reference():
    spec = importlib.util.spec_from_file_location("reference_scores", REFERENCE / "scores.py")
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    return module


def as_it_was_heard(name):
    """The text of a score as the reference rendered it. Its second score kept the pad of the
    first: the lead followed VOL and BRIGHT, and the pads didn't fade with VOL."""
    if name == "pad":
        return PAD
    text = (SCORES / f"{name}.score").read_text()
    if name == "automation":
        heard = text.replace("    sin(p) * vel * VOL >> 16", "    sin(p) * vel >> 8")
        assert heard != text
        return heard
    return text


@pytest.mark.parametrize("name, theirs, samples, loudest, seconds, peak", [
    ("chords-and-melody", "s1", 423_360, 31_227, 9.6, 95),
    ("automation", "s2", 423_360, 30_825, 9.6, 94),
    ("drum-beat", "s3", 352_800, 31_949, 8.0, 98),
    ("pad", "s4", 174_195, 28_190, 4.0, 86),
])
def test_the_renderer_gives_the_samples_that_were_heard(reference, name, theirs, samples,
                                                        loudest, seconds, peak):
    rendered = play(as_it_was_heard(name))
    heard = getattr(reference, theirs)
    assert len(rendered.first) == len(heard) == samples
    assert (rendered.first == heard).all()                           # one for one
    assert rendered.first.dtype == np.int16 and rendered.again is None
    assert largest(rendered.first) == loudest
    assert rendered.report() == {"seconds": seconds, "peak": peak}


def test_the_second_score_fades_its_pads_too(reference):
    """As the design has it, both instruments name VOL. What was heard differs from that in
    the pads alone, and only while VOL glides: the first 0.6 seconds and the last 1.2."""
    rendered = play((SCORES / "automation.score").read_text())
    assert rendered.report() == {"seconds": 9.6, "peak": 94} and largest(rendered.first) == 30_766
    apart = np.abs(rendered.first.astype(np.int64) - reference.s2)
    assert apart[26_460:370_440].max() <= 60                         # 255 / 256 of the pads
    assert apart[:26_460].max() > 10_000 and apart[370_440:].max() > 10_000


def test_blocks_of_any_size_give_the_same_samples(monkeypatch):
    whole = [play(as_it_was_heard(name)).first for name in ("automation", "pad")]
    blocks = compute.blocks
    for size in (1000, 4097, 100_000):
        monkeypatch.setattr(compute, "blocks", lambda length, size=size: blocks(length, size))
        for name, same in zip(("automation", "pad"), whole):
            assert (play(as_it_was_heard(name)).first == same).all(), size


# ---------------------------------------------------------------- one note

def test_the_step_of_a_note():
    """p is t times step, shifted by 16. For A4 the step is 42,852,281."""
    assert render.step_of(69) == 42_852_281
    assert render.step_of(81) == round(880 * 2 ** 32 / 44100)       # an octave up: twice as far
    assert render.step_of(57) == round(220 * 2 ** 32 / 44100)


def test_a_sine_note_is_the_table_times_its_velocity_with_two_fades():
    rendered = play("BPM = 120\nINSTRUMENT sine:\n    sin(p) * vel >> 8\n"
                    "SONG:\n    (0, 8, A4, sine, 200)\n")
    count = 22050                                                    # 8 steps at 120 BPM
    t = np.arange(count, dtype=np.int64)
    sine = compute.SIN[(t * 42_852_281 >> 16) & 65535] * 200 >> 8
    assert len(rendered.first) == count
    assert (rendered.first[90:-220] == sine[90:-220]).all()
    assert (rendered.first[:90] == sine[:90] * np.arange(90) // 90).all()
    assert (rendered.first[-220:] == sine[-220:] * np.arange(220, 0, -1) // 220).all()
    assert rendered.first[0] == 0 and abs(int(rendered.first[-1])) <= 32767 // 220 + 1
    assert rendered.report() == {"seconds": 0.5, "peak": 78}        # 200 / 256 of full


def test_the_fades_and_how_they_round():
    """In over 90 samples and out over 220. Both round down."""
    up = tune("(0, 8, A4, level)").first
    assert up[:90].tolist() == [20000 * i // 90 for i in range(90)]
    assert up[-220:].tolist() == [20000 * k // 220 for k in range(220, 0, -1)]
    assert set(up[90:-220].tolist()) == {20000}
    assert (up[0], up[1], up[89], up[-220], up[-1]) == (0, 222, 19777, 20000, 90)
    down = tune("(0, 8, A4, level)", head=HEAD.replace("20000", "0 - 20000")).first
    assert down[:90].tolist() == [-20000 * i // 90 for i in range(90)]     # -222.2 is -223
    assert down[-220:].tolist() == [-20000 * k // 220 for k in range(220, 0, -1)]
    assert (down[1], down[-1]) == (-223, -91)


def test_a_note_shorter_than_both_fades_gets_both_shorter():
    """A note that is shorter than both together gets both made shorter in the same
    proportion: 90/310 of its length in, 220/310 out."""
    fastest = HEAD.replace("120", "400").replace("X = 0", "STEPS = 96")
    short = tune("(0, 1, A4, level)", head=fastest.replace("    X\n", "    0\n")).first
    assert len(short) == 69                                          # a step of 68.9 samples
    fade_in, fade_out = 69 * 90 // 310, 69 * 220 // 310
    assert (fade_in, fade_out) == (20, 48)
    assert short[:20].tolist() == [20000 * i // 20 for i in range(20)]
    assert short[20:21].tolist() == [20000]                          # one sample at its level
    assert short[21:].tolist() == [20000 * k // 48 for k in range(48, 0, -1)]
    exact = tune("(0, 9, A4, level)", "(100, 1, A4, level)",
                 head=fastest.replace("    X\n", "    0\n")).first
    assert exact[:620].tolist()[89:91] == [20000 * 89 // 90, 20000]  # 620 samples: full fades


def test_a_tail_sounds_after_the_note_and_the_fade_is_at_its_end():
    head = HEAD.replace("INSTRUMENT level:", "INSTRUMENT level 1000:")
    rendered = tune("(0, 8, A4, level)", head=head)
    assert len(rendered.first) == at(8) + 1000
    assert set(rendered.first[90:-220].tolist()) == {20000}          # through the note's end
    assert rendered.first[-1] == 90
    held = tune("(0, 8, A4, level)", head=head.replace("20000", "t < dur ? 20000 : 5000"))
    assert held.first[at(8) - 1] == 20000 and held.first[at(8)] == 5000


def test_the_names_of_a_note():
    notes = "BPM = 120\nINSTRUMENT shows:\n    {}\nSONG:\n    (8, 4, C4, shows, 77)\n"
    here = at(8) + 500                                               # 500 samples into the note
    assert play(notes.format("vel * 100")).first[here] == 7700
    assert play(notes.format("key * 100")).first[here] == 6000
    assert play(notes.format("dur")).first[here] == at(4)            # 11025, in samples
    assert play(notes.format("t")).first[here] == 500                # t starts with the note
    assert play(notes.format("p >> 4")).first[here] == (500 * render.step_of(60) >> 16) >> 4
    assert play(notes.format("t")).first[500] == 0                   # nothing before it


# ---------------------------------------------------------------- variables over time

def test_a_variable_glides_jumps_and_is_taken_over():
    rendered = tune("(0, 64, A4, follows)",
                    "(8, 8, 1000, X)",         # a glide from 0
                    "(24, 0, 50, X)",          # a jump
                    "(32, 16, 2050, X)",       # a glide from 50 ...
                    "(40, 8, 0, X)")           # ... that this one takes over halfway
    x = rendered.first
    assert set(x[90:at(8)].tolist()) == {0}                          # its declared value
    long = at(16) - at(8)
    assert [int(x[at(8) + k]) for k in (0, 1, 1000, long - 1)] == [
        0, 1000 * 1 // long, 1000 * 1000 // long, 1000 * (long - 1) // long]   # rounded down
    assert x[at(16)] == 1000 and x[at(24) - 1] == 1000 and x[at(24)] == 50
    assert x[at(32)] == 50 and x[at(36)] == 50 + 2000 * (at(36) - at(32)) // (at(48) - at(32))
    halfway = 50 + 2000 * (at(40) - at(32)) // (at(48) - at(32))
    assert x[at(40)] == halfway == 1050                              # from where it got to
    assert x[at(44)] == halfway - halfway * (at(44) - at(40)) // (at(48) - at(40)) == 525
    assert x[at(48)] == 0 and x[at(60)] == 0


def test_a_glide_down_rounds_down_too():
    rendered = tune("(0, 32, A4, follows)", "(8, 8, -1000, X)")
    long = at(16) - at(8)
    assert [int(rendered.first[at(8) + k]) for k in (1, 7, long - 1)] == [
        -1000 * 1 // long, -1000 * 7 // long, -1000 * (long - 1) // long]
    assert rendered.first[at(8) + 1] == -1                           # -0.09 is -1


def test_a_variable_is_shared_and_follows_the_song_not_the_note():
    rendered = tune("(16, 16, A4, follows)", "(0, 32, 1000, X)")
    assert rendered.first[at(16) + 100] == 1000 * (at(16) + 100) // at(32)
    two = tune("(16, 16, A4 C5, follows)", "(0, 32, 1000, X)")       # both voices see the same
    assert two.first[at(16) + 100] == 2 * rendered.first[at(16) + 100]


def test_a_variable_that_stands_still_is_a_plain_number():
    glides = (song.Glide(100, 200, 50), song.Glide(300, 300, 7))
    variable = render._Variable(3, glides)
    assert [variable.at(sample) for sample in (0, 99, 100, 150, 199, 200, 299, 300, 9999)] == [
        3, 3, 3, 26, 49, 50, 50, 7, 7]
    assert variable.values(0, 100) == 3 and variable.values(200, 300) == 50
    assert variable.values(300, 500) == 7 and isinstance(variable.values(0, 100), int)
    whole = variable.values(0, 400)
    assert whole.tolist() == [variable.at(sample) for sample in range(400)]
    for first, stop in [(50, 150), (150, 250), (199, 201), (99, 101), (250, 350), (100, 200)]:
        assert variable.values(first, stop).tolist() == whole[first:stop].tolist()
    assert render._Variable(9, ()).values(0, 10 ** 9) == 9


# ---------------------------------------------------------------- the mix

def test_the_voices_are_added_and_the_peak_is_a_percent_of_full_scale():
    one = tune("(0, 8, A4, level)")
    assert largest(one.first) == 20000 and one.report() == {"seconds": 0.5, "peak": 61}
    two = tune("(0, 8, A4, level)", "(4, 8, C5, level)", head=HEAD.replace("20000", "10000"))
    assert (two.first[at(2)], two.first[at(6)], two.first[at(10)]) == (10000, 20000, 10000)
    quiet = tune("(0, 8, A4, level)", head=HEAD.replace("20000", "6553"))
    assert quiet.report() == {"seconds": 0.5, "peak": 20}


def test_a_mix_that_is_too_loud_is_turned_down_and_never_clipped():
    """When peak is over 100, the addon turns the whole song down until the loudest point
    just fits, and says so."""
    loud = tune("(0, 8, C4 E4 G4 B4, level)", "(16, 8, C4, level)")
    assert loud.report() == {"seconds": 1.5, "peak": 244, "turned_down_to": 40}
    assert largest(loud.first) == 32767                              # 80000, turned down
    assert set(loud.first[90:at(8) - 220].tolist()) == {32767}
    assert set(loud.first[at(16) + 90:-220].tolist()) == {20000 * 32767 // 80000}   # all of it


def test_a_mix_that_just_fits_isnt_turned_down():
    fits = tune("(0, 8, A4, level)", head=HEAD.replace("20000", "32767"))
    assert fits.report() == {"seconds": 0.5, "peak": 100} and largest(fits.first) == 32767
    over = tune("(0, 8, A4, level)", head=HEAD.replace("20000", "0 - 32768"))
    assert over.report() == {"seconds": 0.5, "peak": 101, "turned_down_to": 99}   # never 100
    assert largest(over.first) == 32767 and over.first.min() == -32767


def test_an_instrument_that_leaves_16_bits_is_named():
    """A voice that is too loud by itself is clipped, and play names its instrument."""
    head = ("BPM = 120\nINSTRUMENT fine:\n    sin(p) * vel >> 9\n"
            "INSTRUMENT loud:\n    sin(p) * 2\nINSTRUMENT louder:\n    40000\n")
    assert tune("(0, 8, A4, fine)", "(8, 8, A4, loud, 1)", head=head).report() == {
        "seconds": 1.0, "peak": 101, "turned_down_to": 99, "clipped": ["loud"]}
    assert tune("(0, 8, A4, louder)", "(0, 8, A4, fine)", "(8, 8, A4, loud)",
                head=head).clipped == ["loud", "louder"]             # in the order of the file
    assert "clipped" not in tune("(0, 8, A4, fine)", head=head).report()


# ---------------------------------------------------------------- once, and in a loop

def test_a_song_that_plays_once_rings_out():
    once = play(PAD)
    assert len(once.first) == 138_915 + 35_280 and once.again is None
    assert once.seconds == 4.0                                       # the tail counts


def test_a_loop_is_cut_at_its_end_and_its_tails_start_the_next_round():
    """A song that loops starts again at that step. A tail that is still sounding is mixed
    into the start of the next round, so the rhythm doesn't break."""
    once, loop = play(PAD), play(PAD, loop=True)
    end = 138_915                                                    # step 42 at 100 BPM
    assert len(loop.first) == len(loop.again) == end
    assert (loop.first == once.first[:end]).all()
    rings = once.first[end:].astype(np.int64)
    assert len(rings) == 35_280 and np.abs(rings).max() > 1000
    assert (loop.again[:35_280] == loop.first[:35_280] + rings).all()
    assert (loop.again[35_280:] == loop.first[35_280:]).all()
    assert loop.seconds == 3.2 and loop.peak >= once.peak            # one round; both rounds


def test_a_loop_without_tails_is_one_sound():
    once = play((SCORES / "drum-beat.score").read_text())
    loop = play((SCORES / "drum-beat.score").read_text(), loop=True)
    assert loop.again is None and (loop.first == once.first).all()
    assert loop.report() == once.report() == {"seconds": 8.0, "peak": 98}


def test_tails_longer_than_a_round_wrap_again():
    head = HEAD.replace("INSTRUMENT level:", "INSTRUMENT level 30000:").replace("20000", "1000")
    once = tune("(0, 4, A4, level)", head=head)
    loop = tune("(0, 4, A4, level)", head=head, loop=True)
    end = at(4)                                                      # 11025: the tail is 2.7 rounds
    assert len(once.first) == end + 30000 and len(loop.first) == len(loop.again) == end
    expected = once.first[:end].astype(np.int64)
    for start in range(end, len(once.first), end):
        piece = once.first[start:start + end]
        expected[:len(piece)] += piece
    assert (loop.again == expected).all()
    assert (loop.first[5000], loop.again[5000], loop.again[9000]) == (1000, 4000, 3000)
    assert loop.peak == 12 and once.peak == 3                        # the peak is of both rounds


def test_a_loop_is_turned_down_as_a_whole():
    head = HEAD.replace("INSTRUMENT level:", "INSTRUMENT level 11025:")
    loop = tune("(0, 4, A4, level)", head=head, loop=True)           # the tail doubles round two
    assert largest(loop.again) == 32767 and loop.turned_down_to == 81      # 32767 / 40000
    assert largest(loop.first) == 20000 * 32767 // 40000             # the first round as well
    assert loop.peak == 122


# ---------------------------------------------------------------- the limits

def test_the_limits_are_the_numbers_that_were_timed():
    assert (limits.SONG_SECONDS, limits.SCORE_BYTES, limits.EVENTS) == (300, 65536, 10_000)
    assert (limits.PATTERN_DEPTH, limits.EXPRESSION_CHARS, limits.EXPRESSION_DEPTH) == (
        8, 500, 40)
    assert (limits.PARTS, limits.TAIL_SAMPLES, limits.VOICES, limits.PROBLEMS) == (
        16, 441_000, 64, 20)
    assert (limits.BPM_MIN, limits.BPM_MAX, limits.STEPS_MIN, limits.STEPS_MAX) == (
        20, 400, 1, 96)


def test_the_stress_scores_of_the_timing_are_as_big_as_the_limits_allow():
    longest = song.unfold(score.read(music_timing.longest_song()))
    assert longest.length == limits.SONG_SECONDS * 44100 and len(longest.notes) == 8
    assert {note.length for note in longest.notes} == {longest.length}     # all the time
    most = song.unfold(score.read(music_timing.most_events()))
    assert limits.EVENTS - 128 < len(most.notes) <= limits.EVENTS
    assert most.length <= limits.SONG_SECONDS * 44100
