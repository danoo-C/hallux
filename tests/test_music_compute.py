"""Computing an instrument's expression: addons/music_engine/compute.py. The sentences in
quotes are the rules of docs/addon-music.md, section 3, that a test checks."""
import contextlib
import importlib.util
import io
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="numpy isn't installed (pip install -e '.[music]')")

from music_engine import compute, expr  # noqa: E402

# The arithmetic wraps around and divides by zero on purpose: numpy must never warn about it.
pytestmark = pytest.mark.filterwarnings("error")

REFERENCE = Path(__file__).resolve().parent.parent / "docs/plans/addon-music/reference"
RATE = 44100
LOWEST = -2 ** 63                             # the smallest 64-bit number


def run(text, **values):
    """Compute an expression whose names are the values given."""
    return compute.compute(expr.read(text, list(values)), values)


def one(text, **values):
    """The single number an expression without arrays gives."""
    [number] = run(text, **values).tolist()
    return number


def step_of(key):
    """How far p moves per sample, as 65536ths of a cycle times 65536."""
    return round(440.0 * 2 ** ((key - 69) / 12) * 2 ** 32 / RATE)


def phase(key, count, start=0):
    t = np.arange(start, start + count, dtype=np.int64)
    return t, t * step_of(key) >> 16


def instrument(*lines, variables=()):
    """An instrument as the score reader will hand it over: its named parts as trees, in
    their order, and its last line. A part may use the parts above it."""
    names, parts = list(expr.NAMES) + list(variables), {}
    for line in lines[:-1]:
        name, _, text = line.partition(" = ")
        parts[name] = expr.read(text, names)
        names.append(name)
    return parts, expr.read(lines[-1], names)


def note(played, key=69, vel=255, dur=RATE, tail=0, size=None, **variables):
    """Every sample of one note, computed in pieces of `size` samples, or in one piece.
    Returns the samples, and whether any piece was clipped."""
    parts, sample = played
    pieces, clipped = [], False
    for start, stop, more in compute.blocks(dur + tail, size or dur + tail):
        t, p = phase(key, stop + more - start, start)
        values = {"t": t, "p": p, "vel": vel, "dur": dur, "key": key}
        values |= {name: value[start:stop + more] for name, value in variables.items()}
        samples, was_clipped = compute.compute_instrument(parts, sample, values, more)
        pieces.append(samples)
        clipped |= was_clipped
    return np.concatenate(pieces), clipped


# ---------------------------------------------------------------- the arithmetic

def test_numbers_wrap_around_at_64_bits():
    """64-bit whole numbers that wrap around."""
    assert one("(1 << 62) * 4") == 0
    assert one("9223372036854775807 + 1") == LOWEST
    assert one("0 - 9223372036854775807 - 2") == 2 ** 63 - 1
    assert one("-(0 - 9223372036854775807 - 1)") == LOWEST          # it has no positive twin
    assert one("a * b", a=2 ** 62, b=4) == 0                         # two plain numbers too
    assert run("t * 4611686018427387904", t=np.arange(5)).tolist() == [0, 2 ** 62, LOWEST,
                                                                      -2 ** 62, 0]


def test_a_sample_times_a_velocity_times_two_variables_fits():
    """A 16-bit sample times a velocity times two variables doesn't fit 32 bits, and with 64
    nobody has to count."""
    assert one("32767 * 255 * 255 * 255 >> 24") == 32767 * 255 ** 3 >> 24 == 32384


def test_division_rounds_toward_zero():
    """/ and % round toward zero: -7 / 2 is -3, and -7 % 2 is -1."""
    assert one("-7 / 2") == -3 and one("-7 % 2") == -1
    assert one("7 / -2") == -3 and one("7 % -2") == 1
    assert one("-7 / -2") == 3 and one("-7 % -2") == -1
    assert one("7 / 2") == 3 and one("7 % 2") == 1
    x = np.arange(-9, 10)
    assert run("x / 4", x=x).tolist() == [int(n / 4) for n in x]
    assert run("x % 4", x=x).tolist() == [int(n - int(n / 4) * 4) for n in x]
    assert run("100 / x", x=x).tolist() == [int(100 / n) if n else 0 for n in x]
    assert run("x * 7 / (x - 3)", x=x).tolist() == [int(n * 7 / (n - 3)) if n != 3 else 0
                                                    for n in x]


def test_division_at_the_edge_of_64_bits():
    assert one("a / 2", a=LOWEST) == -2 ** 62 and one("a / -2", a=LOWEST) == 2 ** 62
    assert one("a / 1", a=LOWEST) == LOWEST
    assert one("a / -1", a=LOWEST) == LOWEST and one("a % -1", a=LOWEST) == 0   # it wraps
    assert one("a / a", a=LOWEST) == 1 and one("7 / a", a=LOWEST) == 0
    assert one("9223372036854775807 / a", a=LOWEST) == 0
    assert one("9223372036854775807 % a", a=LOWEST) == 2 ** 63 - 1


def test_dividing_by_zero_gives_zero():
    """Dividing by zero gives 0, with / and with %."""
    assert one("5 / 0") == 0 and one("5 % 0") == 0 and one("0 / 0") == 0
    assert one("-5 / 0") == 0 and one("-5 % 0") == 0
    assert run("t / (t - 2)", t=np.arange(5)).tolist() == [0, -1, 0, 3, 2]
    assert run("7 % (t - 2)", t=np.arange(5)).tolist() == [1, 0, 0, 0, 1]


def test_shifting_right_keeps_the_sign():
    """>> keeps the sign, so -128 >> 1 is -64."""
    assert one("-128 >> 1") == -64 and one("-1 >> 60") == -1 and one("128 >> 1") == 64
    assert run("x >> 4", x=np.array([-32768, -1, 0, 32767])).tolist() == [-2048, -1, 0, 2047]


def test_a_shift_uses_the_low_six_bits_of_its_count():
    """A shift uses the low 6 bits of its count, so x << 64 is x."""
    assert one("x << 64", x=5) == 5 and one("x >> 64", x=5) == 5
    assert one("x << 65", x=5) == 10 and one("x >> 65", x=-128) == -64
    assert one("1 << 63") == LOWEST and one("1 << -1") == LOWEST         # -1 & 63 is 63
    assert run("1 << t", t=np.array([0, 1, 62, 64, 66])).tolist() == [1, 2, 2 ** 62, 1, 4]


def test_a_comparison_gives_one_or_zero():
    """A comparison gives 1 or 0."""
    t = np.arange(4)
    for text, gives in [("t < 2", [1, 1, 0, 0]), ("t <= 2", [1, 1, 1, 0]), ("t > 2", [0, 0, 0, 1]),
                        ("t >= 2", [0, 0, 1, 1]), ("t == 2", [0, 0, 1, 0]),
                        ("t != 2", [1, 1, 0, 1]),
                        ("(t > 0) + (t > 1) * 10", [0, 1, 11, 11])]:
        assert run(text, t=t).tolist() == gives, text
    assert run("t", t=t).dtype == run("t < 2", t=t).dtype == np.int64


def test_the_other_operators():
    assert one("12 & 10") == 8 and one("12 | 10") == 14 and one("12 ^ 10") == 6
    assert one("~5") == -6 and one("-5") == -5 and one("- -5") == 5 and one("~-1") == 0
    assert one("7 - 10") == -3 and one("7 + 10 * 2") == 27 and one("0xFF & -1") == 255


def test_a_choice_takes_one_side_for_each_sample():
    t = np.arange(6)
    assert run("t < 3 ? t * 10 : 0 - t", t=t).tolist() == [0, 10, 20, -3, -4, -5]
    assert run("t & 1 ? 7 : 9", t=t).tolist() == [9, 7, 9, 7, 9, 7]
    assert one("0 ? 1 : 2") == 2 and one("-5 ? 1 : 2") == 1           # anything but 0 is yes
    # Both sides are computed, and a division by zero on the side not taken is only a 0.
    assert run("t ? 60 / t : 99", t=t).tolist() == [99, 60, 30, 20, 15, 12]


def test_the_precedence_traps_compute_as_the_design_says():
    """x * vel >> 8 * VOL >> 8 shifts by 8 * VOL; p & 65535 - 32768 is p & 32767."""
    assert one("x * vel >> 8 * VOL >> 8", x=30000, vel=255, VOL=2) == 30000 * 255 >> 16 >> 8
    assert one("x * vel * VOL >> 16", x=30000, vel=255, VOL=255) == 30000 * 255 * 255 >> 16
    p = np.array([0, 40000, 65535, 70000])
    assert run("p & 65535 - 32768", p=p).tolist() == (p & 32767).tolist()
    assert run("(p & 65535) - 32768", p=p).tolist() == [-32768, 7232, 32767, -28304]


def test_a_result_has_one_number_per_sample():
    t = np.arange(5)
    assert run("vel * 2", vel=100, t=t).tolist() == [200] * 5       # nothing in it changes
    assert run("7").tolist() == [7]                                  # and no sample at all
    same = run("t", t=t)
    same[0] = 99                                                     # the result is the caller's
    assert t[0] == 0


def test_the_longest_and_the_deepest_expression_compute():
    t = np.arange(3)
    assert run("t" + "+t" * 249, t=t).tolist() == [0, 250, 500]     # 499 characters, 250 deep
    assert run("-" * 40 + "t", t=t).tolist() == [0, 1, 2]
    assert run("(" * 40 + "t" + ")" * 40, t=t).tolist() == [0, 1, 2]
    assert run("t ? 1 : " * 40 + "7", t=t).tolist() == [7, 1, 1]


def test_a_value_is_the_same_as_a_number_and_as_an_array():
    t, p = phase(69, 1000)
    tree = expr.read("sin(p) * vel * VOL >> 16", ["p", "vel", "VOL"])
    still = compute.compute(tree, {"p": p, "vel": 200, "VOL": 180})
    array = compute.compute(tree, {"p": p, "vel": np.full(1000, 200), "VOL": np.full(1000, 180)})
    assert (still == array).all() and still.any()


# ---------------------------------------------------------------- the functions

def test_sin_is_a_table_of_one_cycle():
    """A sine, -32767 to 32767. x is a position in 65536ths of a cycle, and only its low 16
    bits count."""
    assert [one(f"sin({x})") for x in (0, 16384, 32768, 49152)] == [0, 32767, 0, -32767]
    assert one("sin(65536 + 16384)") == 32767 and one("sin(-49152)") == 32767
    assert one("sin(x)", x=2 ** 40 + 16384) == 32767
    cycle = run("sin(t)", t=np.arange(65536))
    assert cycle.max() == 32767 and cycle.min() == -32767
    assert cycle[8192] == round(32767 * 2 ** -0.5) == 23170
    assert (cycle[1:32768] == -cycle[32769:]).all()                  # the second half mirrors


def test_tri_at_the_corners_of_its_cycle():
    """A triangle, -32767 to 32767. It starts at 0 and rises first, like the sine, but in
    straight lines."""
    assert [one(f"tri({x})") for x in (0, 16384, 32768, 49152, 65536)] == [0, 32767, 0, -32767, 0]
    assert one("tri(8192)") == 16384 and one("tri(24576)") == 16384
    assert one("tri(40960)") == -16383 and one("tri(57344)") == -16383   # it rounds toward 32767
    cycle = run("tri(t)", t=np.arange(65536))
    assert cycle.max() == 32767 and cycle.min() == -32767
    assert set(np.diff(cycle).tolist()) <= {-2, -1, 1, 2}             # straight lines, no jump


def test_square_at_the_corners_of_its_cycle():
    """A square wave: 32767 for the first half of the cycle and -32767 for the second."""
    assert [one(f"square({x})") for x in (0, 1, 16384, 32767)] == [32767] * 4
    assert [one(f"square({x})") for x in (32768, 49152, 65535)] == [-32767] * 3
    assert one("square(65536)") == 32767 and one("square(-1)") == -32767


def test_saw_rises_over_the_cycle():
    """A saw, -32767 to 32767: it rises over the cycle and jumps back down at its end."""
    assert [one(f"saw({x})") for x in (0, 32768, 65535, 65536)] == [-32767, 0, 32766, -32767]
    still = run("saw(x)", x=np.full(10, 16384))                      # x doesn't move: no jump
    assert still.tolist() == [-16384] * 10
    backwards = run("saw(0 - p)", p=phase(69, 500)[1])               # nor is one rounded off
    assert backwards.tolist() == [round((2 * (-p & 65535) / 65536 - 1) * 32767)
                                  for p in phase(69, 500)[1].tolist()]


def test_saw_and_square_are_rounded_off_at_their_jump():
    """The addon rounds the jump off over the two samples next to it."""
    t, p = phase(69, RATE)                                            # A4, for a second
    saw, raw = run("saw(p)", p=p), run("(p & 65535) - 32768", p=p)
    ph, d = (p & 65535) / 65536, np.diff(p, append=2 * p[-1] - p[-2]) / 65536
    away = (ph >= d) & (ph <= 1 - d)
    assert (saw[away] == np.round((2 * ph[away] - 1) * 32767)).all()  # elsewhere: the plain saw
    assert (~away).sum() == 880                                      # 440 jumps, 2 samples each
    assert np.abs(np.diff(raw)).max() > 64000                        # the raw saw falls at once,
    assert np.abs(np.diff(saw)).max() < 50000                        # this one in smaller steps
    square = run("square(p)", p=p)
    assert square[10] == 32767 and square[60] == -32767 and square.max() == 32767
    assert np.abs(np.diff(square)).max() < 50000
    assert square[0] == 0                                            # x = 0 is in mid-jump


def off_the_harmonics(samples, hz):
    """The energy that isn't on a harmonic of the note against the energy that is, in dB."""
    spectrum = np.abs(np.fft.rfft(samples * np.blackman(len(samples)))) ** 2
    at = np.fft.rfftfreq(len(samples), 1 / RATE)
    harmonic = (np.abs(at - np.round(at / hz) * hz) < 6) & (np.round(at / hz) >= 1)
    return 10 * np.log10(spectrum[~harmonic & (at > 20)].sum() / spectrum[harmonic].sum())


@pytest.mark.parametrize("key, hz, raw_db, saw_db", [
    (45, 110.0, -25, -41), (69, 440.0, -19, -35), (84, 1046.5, -15, -32), (96, 2093.0, -12, -28)])
def test_saw_folds_back_far_less_than_the_raw_saw(key, hz, raw_db, saw_db):
    """Measured for the saw: the energy that isn't on a harmonic of the note, against the
    energy that is. The numbers are the table's."""
    t, p = phase(key, RATE)
    raw, saw = (off_the_harmonics(run(text, p=p), hz) for text in ("(p & 65535) - 32768", "saw(p)"))
    assert round(raw) == raw_db and round(saw) == saw_db
    assert saw < raw - 10
    assert off_the_harmonics(run("square(p)", p=p), hz) < raw - 10


def test_saw_reads_how_fast_its_value_moves():
    """It reads how fast x moves from one sample to the next, so saw(p * 2) and
    saw(p + (p >> 8)) work as well as saw(p)."""
    t, p = phase(57, RATE)                                            # A3: p * 2 sounds as A4
    assert off_the_harmonics(run("saw(p * 2)", p=p), 440.0) < -30
    assert off_the_harmonics(run("saw(p + (p >> 8))", p=p), 220.0 * (1 + 1 / 256)) < -30


def noise_by_hand(x):
    z = x % 2 ** 64                                                  # x as an unsigned number
    z = z * 0x9E3779B97F4A7C15 % 2 ** 64
    z ^= z >> 29
    z = z * 0xBF58476D1CE4E5B9 % 2 ** 64
    z ^= z >> 32
    return (z & 65535) - 32768


def test_noise_is_one_fixed_formula():
    """The same x always gives the same value, so a song sounds the same every time."""
    first = [-32768, 2169, -7354, 21991, 31223, 8870, 20189, -9365]
    assert run("noise(t)", t=np.arange(8)).tolist() == first        # fixed here, on purpose
    assert run("noise(t)", t=np.arange(-3, 0)).tolist() == [-2747, -23594, 4587]
    spread = np.array([0, 1, 44100, 2 ** 40, -1, LOWEST, 2 ** 63 - 1])
    assert run("noise(x)", x=spread).tolist() == [noise_by_hand(x) for x in spread.tolist()]
    assert run("noise(t >> 3)", t=np.arange(16)).tolist() == [first[0]] * 8 + [first[1]] * 8
    second = run("noise(t)", t=np.arange(RATE))
    assert second.min() >= -32768 and second.max() <= 32767 and abs(second.mean()) < 300
    assert len(set(second.tolist())) > 30000                         # it looks random


def test_decay_halves_every_h_samples():
    """A level that halves every h samples: 65536 while x is 0 or less, 32768 at x = h, 16384
    at x = 2 * h. An h of 0 or less gives 0, as dividing by zero does."""
    assert [one(f"decay({x}, 900)") for x in (0, 900, 1800, 2700)] == [65536, 32768, 16384, 8192]
    assert one("decay(-50, 900)") == 65536 and one("decay(450, 900)") == round(65536 * 2 ** -0.5)
    assert one("decay(5, 0)") == 0 and one("decay(5, -3)") == 0 and one("decay(0, 0)") == 0
    assert one("decay(x, 1)", x=2 ** 62) == 0                        # long gone, and no warning
    t = np.arange(-2, 4) * 900
    assert run("decay(t, 900)", t=t).tolist() == [65536, 65536, 65536, 32768, 16384, 8192]
    assert run("decay(900, h)", h=np.array([-1, 0, 450, 900])).tolist() == [0, 0, 16384, 32768]


def test_min_max_and_abs():
    t = np.arange(-2, 3)
    assert run("min(t, 0)", t=t).tolist() == [-2, -1, 0, 0, 0]
    assert run("max(t, 0)", t=t).tolist() == [0, 0, 0, 1, 2]
    assert run("abs(t)", t=t).tolist() == [2, 1, 0, 1, 2]
    assert one("min(3, 4)") == 3 and one("max(3, 4)") == 4 and one("abs(-7)") == 7


def test_every_function_of_the_reader_can_be_computed():
    assert list(compute.FUNCTIONS) == list(expr.FUNCTIONS)
    assert set(compute.BINARY) == set(expr.LEVELS)


# ---------------------------------------------------------------- an instrument

def test_a_result_outside_16_bits_is_clipped_and_reported():
    """A result outside -32768 to 32767 is clipped to that range."""
    samples, clipped = note(instrument("sin(p) * 2"), dur=1000)
    assert clipped and samples.max() == 32767 and samples.min() == -32768
    sine = run("sin(p)", p=phase(69, 1000)[1])
    fits = np.abs(sine) < 16384
    assert (samples[fits] == sine[fits] * 2).all()                   # the rest is untouched
    samples, clipped = note(instrument("sin(p)"), dur=1000)
    assert not clipped and (samples == sine).all()
    samples, clipped = note(instrument("(p & 65535) - 32768"), dur=1000)   # the edges still fit
    assert not clipped and samples.min() == -32768


def test_a_named_part_is_computed_once(monkeypatch):
    """A part is computed once per sample, however often the lines below it use it."""
    calls = []
    real = compute.FUNCTIONS["noise"]
    monkeypatch.setitem(compute.FUNCTIONS, "noise", lambda x: calls.append(len(x)) or real(x))
    samples, _ = note(instrument("hiss = noise(t) >> 2", "(hiss + hiss + hiss) / 3"), dur=500)
    assert calls == [500]
    assert (samples == run("noise(t) >> 2", t=np.arange(500))).all()


def test_a_part_may_use_the_parts_above_it():
    bell = instrument("env = decay(t, 14000)",
                      "mod = sin(p * 7 >> 1) * decay(t, 9000) >> 16",
                      "sin(p + mod) * env * vel >> 24")
    whole = instrument("sin(p + (sin(p * 7 >> 1) * decay(t, 9000) >> 16)) * decay(t, 14000) "
                       "* vel >> 24")
    assert (note(bell, vel=200)[0] == note(whole, vel=200)[0]).all()


def test_the_sample_too_many_is_dropped_and_not_judged():
    tree = expr.read("t * 20000", ["t"])
    samples, clipped = compute.compute_instrument({}, tree, {"t": np.arange(3)}, more=1)
    assert samples.tolist() == [0, 20000] and not clipped            # 40000 was the third
    samples, clipped = compute.compute_instrument({}, tree, {"t": np.arange(3)})
    assert samples.tolist() == [0, 20000, 32767] and clipped


# ---------------------------------------------------------------- blocks

def test_the_pieces_of_a_note():
    assert list(compute.blocks(0)) == []
    assert list(compute.blocks(5)) == [(0, 5, 0)]
    assert list(compute.blocks(16384)) == [(0, 16384, 0)]
    assert list(compute.blocks(16385)) == [(0, 16385, 0)]            # never one sample alone
    assert list(compute.blocks(16386)) == [(0, 16384, 1), (16384, 16386, 0)]
    assert list(compute.blocks(40000)) == [(0, 16384, 1), (16384, 32768, 1), (32768, 40000, 0)]
    assert list(compute.blocks(7, 2)) == [(0, 2, 1), (2, 4, 1), (4, 7, 0)]
    assert compute.BLOCK == 16384


RAMP = np.arange(70000) * 255 // 69999                               # a variable that glides
# The instruments of the design's three scores, the pad with a tail and the bell, each with a
# note that is longer than a block.
INSTRUMENTS = {
    "pad": (instrument("sin(p) * vel >> 8"), dict(key=48, vel=60, dur=52920)),
    "lead": (instrument("(saw(p) + sin(p)) * vel >> 9"), dict(key=72, vel=140, dur=26460)),
    "pad with VOL": (instrument("sin(p) * vel * VOL >> 16", variables=["VOL"]),
                     dict(key=48, vel=40, dur=52920, VOL=RAMP)),
    "lead with BRIGHT": (
        instrument("(saw(p) * BRIGHT + sin(p) * (255 - BRIGHT)) * vel * VOL >> 24",
                   variables=["VOL", "BRIGHT"]),
        dict(key=67, vel=130, dur=39690, VOL=RAMP[::-1].copy(), BRIGHT=RAMP)),
    "kick": (instrument("sin(p + (65536 - decay(t, 900)) * 5) * decay(t, 5000) * vel >> 24"),
             dict(key=33, vel=255, dur=33075)),
    "snare": (instrument("body = sin(p + (65536 - decay(t, 500)) * 2) * decay(t, 1500)",
                         "hiss = noise(t) * decay(t, 2200)",
                         "(body + hiss) * vel >> 25"), dict(key=55, vel=230, dur=33075)),
    "hat": (instrument("(noise(t) - noise(t - 1)) * decay(t, 600) * vel >> 25"),
            dict(key=84, vel=150, dur=33075)),
    "pad with a tail": (
        instrument("env = min(t, 4000) * decay(t - dur, 6000) >> 12",
                   "(saw(p) + saw(p + (p >> 8)) + saw(p - (p >> 8))) * env * vel >> 26"),
        dict(key=52, vel=110, dur=13230, tail=35280)),
    "bell": (instrument("env = decay(t, 14000)",
                        "mod = sin(p * 7 >> 1) * decay(t, 9000) >> 16",
                        "sin(p + mod) * env * vel >> 24"), dict(key=81, vel=200, dur=44100)),
    "square": (instrument("square(p + (p >> 8)) * vel >> 9"), dict(key=93, vel=255, dur=32769)),
}


@pytest.mark.parametrize("name", INSTRUMENTS)
def test_a_note_in_blocks_is_the_note_in_one_piece(name):
    """A note computed in blocks has to give exactly the samples of the same note computed
    in one piece."""
    played, how = INSTRUMENTS[name]
    whole, clipped = note(played, **how)
    assert not clipped and np.abs(whole).max() > 1000                # it sounds, and it fits
    for size in (16384, 1000, 4097, 32768, 37):                     # 37: many ends at a jump
        assert list(compute.blocks(len(whole), size))[-1][1] == len(whole)
        pieces, clipped = note(played, size=size, **how)
        assert (pieces == whole).all() and not clipped, size


def test_a_last_piece_is_never_one_sample():
    played, how = INSTRUMENTS["square"]                              # 32769 samples: 2 * 16384 + 1
    assert [stop - start for start, stop, _ in compute.blocks(how["dur"])] == [16384, 16385]
    assert (note(played, size=16384, **how)[0] == note(played, **how)[0]).all()


# ---------------------------------------------------------------- the render that was heard

@pytest.fixture(scope="module")
def reference():
    """The throwaway render whose samples the user listened to. Loading it renders them."""
    spec = importlib.util.spec_from_file_location("reference_scores", REFERENCE / "scores.py")
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("theirs, lines, variables", [
    ("pad", ["sin(p) * vel >> 8"], []),
    ("lead", ["(saw(p) + sin(p)) * vel >> 9"], []),
    ("pad2", ["sin(p) * vel * VOL >> 16"], ["VOL"]),
    ("lead2", ["(saw(p) * BRIGHT + sin(p) * (255 - BRIGHT)) * vel * VOL >> 24"],
     ["VOL", "BRIGHT"]),
    ("kick", ["sin(p + (65536 - decay(t, 900)) * 5) * decay(t, 5000) * vel >> 24"], []),
    ("snare", ["body = sin(p + (65536 - decay(t, 500)) * 2) * decay(t, 1500)",
               "hiss = noise(t) * decay(t, 2200)",
               "(body + hiss) * vel >> 25"], []),
    ("hat", ["(noise(t) - noise(t - 1)) * decay(t, 600) * vel >> 25"], []),
    ("pad_tail", ["env = min(t, 4000) * decay(t - dur, 6000) >> 12",
                  "(saw(p) + saw(p + (p >> 8)) + saw(p - (p >> 8))) * env * vel >> 26"], []),
])
def test_the_instruments_give_the_samples_that_were_heard(reference, theirs, lines, variables):
    """The formulas are the ones in reference/scores.py, which were listened to."""
    played = instrument(*lines, variables=variables)
    for key, vel, dur, tail in [(33, 255, 5512, 0), (48, 60, 52920, 0), (69, 140, 26460, 35280),
                                (96, 230, 20000, 0)]:
        t, p = phase(key, dur + tail)
        glide = {name: RAMP[:dur + tail] for name in variables}
        heard = getattr(reference, theirs)(t, p, vel, dur, key, glide)
        ours, _ = note(played, key=key, vel=vel, dur=dur, tail=tail, size=16384, **glide)
        assert (ours == np.clip(heard, -32768, 32767)).all(), (key, vel, dur)


def test_the_tables_and_waves_are_the_reference_s(reference):
    t, p = phase(72, 30000)
    assert (compute.SIN == reference.SIN).all()
    assert (run("saw(p)", p=p) == reference.saw(p)).all()
    assert (run("noise(t - 100)", t=t) == reference.noise(t - 100)).all()
    assert (run("decay(t - 500, 900)", t=t) == reference.decay(t - 500, 900)).all()


# ---------------------------------------------------------------- the kick

def test_the_kicks_pitch_falls_to_its_note():
    """A kick played at A1 (55 Hz) starts at 223 Hz and is close to the note after a tenth
    of a second. The pitch is how fast the position in the wave moves."""
    t, p = phase(33, RATE)                                            # A1
    position = run("p + (65536 - decay(t, 900)) * 5", t=t, p=p)

    def hz(first, last):
        return (position[last] - position[first]) / (last - first) * RATE / 65536

    assert round(hz(0, 1)) == 223                                    # the first sample
    assert round(hz(882 - 44, 882 + 44)) == 141                      # 20 ms in, over 2 ms
    assert round(hz(4410 - 44, 4410 + 44)) == 61                     # 100 ms in
    assert round(hz(RATE - 2000, RATE - 1)) == 55                    # and then the note itself
