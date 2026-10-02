"""An instrument's expression, from a tree to samples (docs/addon-music.md, section 3).

All of the design's arithmetic is here, so that there is one place to check it against the
design: 64-bit whole numbers that wrap around, / and % that round toward zero, and the
functions. The formulas of the functions are the definition of how the addon sounds. They
are those of the render that was listened to (docs/plans/addon-music/reference/scores.py).

Every value is a numpy array of int64: one number per sample, or a single number for what is
the same in every sample. numpy wraps such an array around without a warning, which it
doesn't do for a plain number.
"""
from __future__ import annotations

from typing import Callable, Iterator, Mapping

import numpy as np

from music_engine import expr

BLOCK = 16384                                 # samples computed at a time: the memory stays flat
LOW, HIGH = -32768, 32767                     # a sample has 16 bits

Values = Mapping[str, "np.ndarray | int"]     # what each name of an expression stands for

SIN = np.round(np.sin(np.arange(65536) * 2 * np.pi / 65536) * 32767).astype(np.int64)


def compute(tree: expr.Node, values: Values) -> np.ndarray:
    """One whole number per sample. `values` gives every name the tree uses: an array for
    what changes from sample to sample, a plain number for what doesn't."""
    known = _arrays(values)
    return np.array(np.broadcast_to(_walk(tree, known), (_count(known),)))


def compute_instrument(parts: Mapping[str, expr.Node], sample: expr.Node, values: Values,
                       more: int = 0) -> tuple[np.ndarray, bool]:
    """The samples of an instrument: its named parts in their order, each computed once, then
    its last line, clipped to 16 bits. Returns the samples, and whether that changed any.

    `more` is 1 when the values hold one sample more than is wanted (see blocks)."""
    known = _arrays(values)
    count = _count(known)
    for name, tree in parts.items():
        known[name] = _walk(tree, known)
    unclipped = np.broadcast_to(_walk(sample, known), (count,))[:count - more]
    samples = np.clip(unclipped, LOW, HIGH)
    return samples, bool((samples != unclipped).any())


def blocks(length: int, size: int = BLOCK) -> Iterator[tuple[int, int, int]]:
    """The pieces in which a note of `length` samples is computed. For each: its first
    sample, the one after its last, and how many samples more its values have to hold.

    saw and square need the sample after every one they compute, so that is 1. At the note's
    end there is no such sample: it is 0, and they use the step from the sample before. That
    is why the last piece is never a single sample."""
    start = 0
    while start < length:
        stop = start + size
        if length - stop <= 1:
            stop = length
        yield start, stop, int(stop < length)
        start = stop


def _arrays(values: Values) -> dict[str, np.ndarray]:
    return {name: np.atleast_1d(np.asarray(value, dtype=np.int64))
            for name, value in values.items()}


def _count(known: Mapping[str, np.ndarray]) -> int:
    return max((len(value) for value in known.values()), default=1)


def _walk(node: expr.Node, known: Mapping[str, np.ndarray]) -> np.ndarray:
    match node:
        case expr.Number(value):
            return np.array([value], dtype=np.int64)
        case expr.Name(name):
            return known[name]
        case expr.Unary("-", value):
            return -_walk(value, known)
        case expr.Unary("~", value):
            return ~_walk(value, known)
        case expr.Binary(op, left, right):
            return BINARY[op](_walk(left, known), _walk(right, known))
        case expr.Choice(condition, then, otherwise):
            # Both sides are computed, and each sample takes one. Nothing has a side effect,
            # and a division by zero on the side that isn't taken is only a 0.
            return np.where(_walk(condition, known) != 0,
                            _walk(then, known), _walk(otherwise, known))
        case expr.Call(function, args):
            return FUNCTIONS[function](*(_walk(arg, known) for arg in args))
    raise TypeError(f"not a node of an expression: {node!r}")


# ---------------------------------------------------------------- the operators

def _divide(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a / b, rounded toward zero, and 0 where b is 0. numpy rounds down, and warns about a
    zero, so the sizes are divided without their signs and the sign is put back."""
    zero = b == 0
    sizes = np.abs(a).view(np.uint64) // np.abs(np.where(zero, 1, b)).view(np.uint64)
    quotient = sizes.view(np.int64)
    return np.where(zero, 0, np.where((a < 0) != (b < 0), -quotient, quotient))


def _remainder(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a % b: what a / b leaves over, with the sign of a. 0 where b is 0."""
    return np.where(b == 0, 0, a - _divide(a, b) * b)


def _comparison(compare: Callable) -> Callable:
    """A comparison gives 1 or 0."""
    return lambda a, b: compare(a, b).astype(np.int64)


BINARY: dict[str, Callable] = {
    "*": np.multiply, "/": _divide, "%": _remainder,
    "+": np.add, "-": np.subtract,
    "<<": lambda a, b: a << (b & 63),         # a shift uses the low 6 bits of its count,
    ">>": lambda a, b: a >> (b & 63),         # and >> keeps the sign
    "<": _comparison(np.less), "<=": _comparison(np.less_equal),
    ">": _comparison(np.greater), ">=": _comparison(np.greater_equal),
    "==": _comparison(np.equal), "!=": _comparison(np.not_equal),
    "&": np.bitwise_and, "^": np.bitwise_xor, "|": np.bitwise_or,
}


# ---------------------------------------------------------------- the functions

def _sin(x: np.ndarray) -> np.ndarray:
    return SIN[x & 65535]


def _ramp(x: np.ndarray) -> np.ndarray:
    """A saw as fractions from -1 to 1, with its jump rounded off over the two samples next
    to it (polyBLEP). How far x moves in one sample says how wide that is."""
    step = np.zeros(len(x), dtype=np.int64)
    if len(x) > 1:
        step[:-1] = x[1:] - x[:-1]
        step[-1] = step[-2]                   # no sample after the last: the step before it
    d = step / 65536.0                        # how far it moves in one sample, in cycles
    ph = (x & 65535) / 65536.0                # where in the cycle, 0 to 1
    y = 2 * ph - 1
    smooth = (d > 0) & (d <= 0.5)             # standing still, backwards or too fast: as it is
    after = smooth & (ph < d)                 # the sample just after the jump
    u = ph[after] / d[after]
    y[after] -= u + u - u * u - 1
    before = smooth & (ph > 1 - d)            # and the one just before it
    u = (ph[before] - 1) / d[before]
    y[before] -= u * u + u + u + 1
    return y


def _saw(x: np.ndarray) -> np.ndarray:
    return np.round(_ramp(x) * 32767).astype(np.int64)


def _square(x: np.ndarray) -> np.ndarray:
    """Two saws, half a cycle apart, so both of its jumps are rounded off."""
    return np.round((_ramp(x + 32768) - _ramp(x)) * 32767).astype(np.int64)


def _tri(x: np.ndarray) -> np.ndarray:
    q = (x + 16384) & 65535
    return 32767 - np.abs(q - 32768) * 32767 // 16384


def _noise(x: np.ndarray) -> np.ndarray:
    """The same x always gives the same value, on every computer: x as an unsigned number,
    mixed up by two multiplications that wrap around."""
    z = x.view(np.uint64) * np.uint64(0x9E3779B97F4A7C15)
    z ^= z >> np.uint64(29)
    z *= np.uint64(0xBF58476D1CE4E5B9)
    z ^= z >> np.uint64(32)
    return (z & np.uint64(65535)).astype(np.int64) - 32768


def _decay(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    """A level that halves every h samples, from 65536 down. 0 where h is 0 or less."""
    halves = h > 0
    level = np.round(65536 * 2.0 ** (-np.maximum(x, 0) / np.where(halves, h, 1)))
    return np.where(halves, level.astype(np.int64), 0)


FUNCTIONS: dict[str, Callable] = {
    "sin": _sin, "saw": _saw, "square": _square, "tri": _tri, "noise": _noise,
    "decay": _decay, "min": np.minimum, "max": np.maximum, "abs": np.abs,
}
