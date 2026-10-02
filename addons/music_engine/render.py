"""A song, rendered (docs/addon-music.md, sections 1, 3 and 6).

render() turns the notes of a Song into one mixed song, ready to play, with what play reports
about it: its length, its peak, and whether anything was too loud. The whole song is rendered
before a sample of it is played.

Every note is computed in blocks, faded in and out, and added into the mix at its first
sample. The fades, the glides of the variables and the turning down all round down, as the
render that was listened to did (docs/plans/addon-music/reference/scores.py).
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field

import numpy as np

from music_engine import compute, expr
from music_engine.score import Instrument, Score
from music_engine.song import RATE, Glide, Note, Song

FULL = 32767                                  # full scale: the loudest a sample can be
FADE_IN, FADE_OUT = 90, 220                   # samples: 2 ms and 5 ms, against clicks
CHUNK = 1 << 20                               # samples turned down at a time


@dataclass
class Rendered:
    first: np.ndarray                         # the samples to play, 16-bit; of a loop, round one
    again: np.ndarray | None                  # of a loop whose tails ring past its end: the
                                              # later rounds, with those tails at their start
    seconds: float                            # of the whole song, or of one round of a loop
    peak: int                                 # the loudest point as written, in percent
    turned_down_to: int | None = None         # in percent, when the mix was too loud
    clipped: list[str] = field(default_factory=list)   # instruments that left 16 bits

    def report(self) -> dict:
        """What play tells the AI about the song."""
        found = {"seconds": self.seconds, "peak": self.peak}
        if self.turned_down_to is not None:
            found["turned_down_to"] = self.turned_down_to
        if self.clipped:
            found["clipped"] = self.clipped
        return found


def render(score: Score, song: Song, loop: bool = False) -> Rendered:
    """The mixed song. With `loop`, it is cut at the song's end, and what rings past that is
    mixed into the start of the later rounds."""
    variables = {name: _Variable(score.variables[name], song.changes[name])
                 for name in score.variables}
    used = {name: _names(instrument) & variables.keys()
            for name, instrument in score.instruments.items()}
    mix = np.zeros(song.length, dtype=np.int32)   # a voice has 16 bits, so their sum fits 32
    too_loud = set()
    for note in song.notes:
        instrument = score.instruments[note.instrument]
        samples, clipped = _voice(note, instrument,
                                  {name: variables[name] for name in used[note.instrument]})
        mix[note.start:note.start + len(samples)] += samples
        if clipped:
            too_loud.add(note.instrument)

    first, again, length = mix, None, song.length
    if loop:
        first, rest, length = mix[:song.end], mix[song.end:], song.end
        if len(rest):
            again = first.copy()
            for start in range(0, len(rest), song.end):   # tails longer than a round wrap again
                tail = rest[start:start + song.end]
                again[:len(tail)] += tail
    largest = max(_largest(first), 0 if again is None else _largest(again))
    peak = (largest * 200 + FULL) // (2 * FULL)   # in percent, to the nearest
    return Rendered(
        first=_to_16_bits(first, largest),
        again=None if again is None else _to_16_bits(again, largest),
        seconds=(length * 20 + RATE) // (2 * RATE) / 10,   # to the nearest tenth
        peak=max(peak, 101) if largest > FULL else peak,
        turned_down_to=FULL * 100 // largest if largest > FULL else None,
        clipped=[name for name in score.instruments if name in too_loud])


def step_of(key: int) -> int:
    """How far a note's position in the wave moves per sample, times 65536. p is t times this,
    shifted down by 16, which keeps a note in tune to less than a thousandth of a cent."""
    return round(440.0 * 2 ** ((key - 69) / 12) * 2 ** 32 / RATE)


def _voice(note: Note, instrument: Instrument,
           variables: dict[str, _Variable]) -> tuple[np.ndarray, bool]:
    """One note: its samples, tail and fades included, and whether its expression left 16
    bits."""
    length, step = note.length + instrument.tail, step_of(note.key)
    samples, clipped = np.empty(length, dtype=np.int32), False
    for start, stop, more in compute.blocks(length):
        t = np.arange(start, stop + more, dtype=np.int64)
        values = {"t": t, "p": t * step >> 16,
                  "vel": note.velocity, "dur": note.length, "key": note.key}
        for name, variable in variables.items():
            values[name] = variable.values(note.start + start, note.start + stop + more)
        samples[start:stop], was_clipped = compute.compute_instrument(
            instrument.parts, instrument.sample, values, more)
        clipped |= was_clipped
    _fade(samples)
    return samples, clipped


def _fade(samples: np.ndarray) -> None:
    """Fade a note in and out, in place. A wave that starts or stops anywhere but at 0 makes
    a click. A note shorter than both fades gets both shorter in the same proportion."""
    length = len(samples)
    fade_in, fade_out = FADE_IN, FADE_OUT
    if length < FADE_IN + FADE_OUT:
        fade_in = length * FADE_IN // (FADE_IN + FADE_OUT)
        fade_out = length * FADE_OUT // (FADE_IN + FADE_OUT)
    if fade_in:
        samples[:fade_in] = samples[:fade_in] * np.arange(fade_in) // fade_in
    if fade_out:
        samples[length - fade_out:] = (samples[length - fade_out:]
                                       * np.arange(fade_out, 0, -1) // fade_out)


def _names(instrument: Instrument) -> set[str]:
    """Every name the lines of an instrument use."""
    found: set[str] = set()

    def walk(node: expr.Node) -> None:
        match node:
            case expr.Name(name):
                found.add(name)
            case expr.Unary(_, value):
                walk(value)
            case expr.Binary(_, left, right):
                walk(left)
                walk(right)
            case expr.Choice(condition, then, otherwise):
                walk(condition)
                walk(then)
                walk(otherwise)
            case expr.Call(_, args):
                for arg in args:
                    walk(arg)

    for tree in (*instrument.parts.values(), instrument.sample):
        walk(tree)
    return found


def _largest(mix: np.ndarray) -> int:
    return max(int(mix.max()), -int(mix.min())) if len(mix) else 0


def _to_16_bits(mix: np.ndarray, largest: int) -> np.ndarray:
    """The mix as the sound card takes it. One that is too loud is turned down as a whole,
    until its loudest point just fits: it is never clipped."""
    if largest <= FULL:
        return mix.astype(np.int16)
    quiet = np.empty(len(mix), dtype=np.int16)
    for start in range(0, len(mix), CHUNK):   # in pieces: the product needs 64 bits
        piece = mix[start:start + CHUNK].astype(np.int64)
        quiet[start:start + CHUNK] = piece * FULL // largest
    return quiet


def _wrap(value: int) -> int:
    """A whole number as the 64 bits it has in an expression."""
    return (value + 2 ** 63) % 2 ** 64 - 2 ** 63


class _Variable:
    """A variable over the whole song. It is kept as its list of changes, not as one number
    per sample, and works out its values for the block that is being rendered."""

    def __init__(self, initial: int, glides: tuple[Glide, ...]):
        self.initial = initial
        self.firsts: list[int] = []           # of the changes, in order
        self.changes: list[tuple[int, int, int, int]] = []   # first, last, from, to
        for glide in glides:
            # From whatever the value is there: a change that starts while another still
            # glides takes over from where that one got to.
            self.changes.append((glide.first, glide.last, self.at(glide.first), glide.value))
            self.firsts.append(glide.first)

    def at(self, sample: int) -> int:
        """The value at one sample."""
        index = bisect_right(self.firsts, sample) - 1
        if index < 0:
            return self.initial
        first, last, start, end = self.changes[index]
        if sample >= last:
            return end
        return _wrap(start + (end - start) * (sample - first) // (last - first))

    def values(self, first: int, stop: int) -> np.ndarray | int:
        """The values from one sample up to another: a plain number if it is the same in all
        of them, which is most of the time."""
        low = bisect_right(self.firsts, first) - 1
        high = bisect_right(self.firsts, stop - 1) - 1
        if low == high and (low < 0 or first >= self.changes[low][1]):
            return self.at(first)
        values = np.empty(stop - first, dtype=np.int64)
        for index in range(low, high + 1):
            here = first if index == low else self.firsts[index]
            there = stop if index == high else self.firsts[index + 1]
            if index < 0:
                values[:there - first] = self.initial
                continue
            start_at, last, start, end = self.changes[index]
            glides_to = max(here, min(there, last))          # from here on it stands still
            samples = np.arange(here, glides_to, dtype=np.int64)
            values[here - first:glides_to - first] = start + (
                _wrap(end - start) * (samples - start_at) // max(last - start_at, 1))
            values[glides_to - first:there - first] = end
        return values
