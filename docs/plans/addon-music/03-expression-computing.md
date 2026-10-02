# Step 3: computing an expression

[The plan](README.md) · the design: [addon-music.md](../../addon-music.md), section 3

**Needs:** step 2. **Makes:** `addons/music_engine/compute.py`,
`tests/test_music_compute.py`.

The tree of step 2 becomes samples. All of the design's arithmetic lives in this one module,
so that there is one place to check it against the design.

## Build

**`compute(tree, values)`** walks the tree and returns one whole number per sample, as a
numpy array of 64-bit numbers. `values` gives every name the tree uses: an array for what
changes per sample (`t`, `p`, a variable that is gliding), a plain number for what doesn't
(`vel`, `dur`, `key`, a variable that stands still).

**`compute_instrument(instrument, values)`** computes the named parts in their order, each
once, then the last line. It clips the result to -32768 to 32767 and returns the samples and
whether anything was clipped.

**The arithmetic,** as the design's section 3 has it:

| Rule | In numpy |
|---|---|
| 64-bit whole numbers that wrap around | `int64` arrays wrap by themselves. A plain number times a plain number has to wrap too, and must not raise a warning |
| `/` and `%` round toward zero | numpy rounds down, so both are made from the absolute values and the signs |
| Dividing by zero gives 0 | The zeros of the divisor are replaced before dividing, and the result is set to 0 there |
| `>>` keeps the sign | numpy's `>>` on `int64` does |
| A shift uses the low 6 bits of its count | The count is masked with 63 first |
| A comparison gives 1 or 0 | The result is turned into `int64` |
| `a ? b : c` | Both sides are computed, and each sample takes one. Nothing has side effects, and a division by zero on the side not taken is 0 |

**The functions.** These formulas are the definition. They are the ones in
[reference/scores.py](reference/scores.py), which were listened to.

- **`sin(x)`:** a table of 65536 values, `round(sin(2π · i / 65536) · 32767)`, read at
  `x & 65535`.
- **`saw(x)`:** smoothed with polyBLEP.

  ```text
  ph = (x & 65535) / 65536           where in the cycle, 0 to 1
  d  = (the next x - this x) / 65536   how far it moves in one sample
  y  = 2 * ph - 1
  where ph < d:        u = ph / d          y = y - (2*u - u*u - 1)
  where ph > 1 - d:    u = (ph - 1) / d    y = y - (u*u + 2*u + 1)
  saw = round(y * 32767)
  ```

  For the last sample of a note, `d` is the step from the sample before. Where `d` is 0 or
  less, or more than half a cycle, nothing is smoothed.
- **`square(x)`:** made of two saws before the rounding, `y(x + 32768) - y(x)`, so both jumps
  are smoothed. It is 32767 in the first half of the cycle.
- **`tri(x)`:** whole numbers only. With `q = (x + 16384) & 65535`, it is
  `32767 - abs(q - 32768) * 32767 / 16384`.
- **`noise(x)`:** `x` as an unsigned 64-bit number `z`, with every step wrapping:

  ```text
  z = z * 0x9E3779B97F4A7C15
  z = z ^ (z >> 29)
  z = z * 0xBF58476D1CE4E5B9
  z = z ^ (z >> 32)
  noise = (z & 65535) - 32768
  ```
- **`decay(x, h)`:** `round(65536 · 2^(-max(x, 0) / h))`, and 0 where `h` is 0 or less.
- **`min`, `max`, `abs`:** numpy's.

**Blocks.** The renderer (step 6) computes a note in blocks of 16,384 samples. `saw` and
`square` look one sample ahead, so a block is handed one sample more than it returns. A note
computed in blocks has to give exactly the samples of the same note computed in one piece.

## Tests

- every rule of the arithmetic, with the design's own examples: `-7 / 2` is `-3`, `-7 % 2` is
  `-1`, `x / 0` is 0, `-128 >> 1` is `-64`, `x << 64` is `x`, and `(1 << 62) * 4` is 0;
- `sin` at 0, 16384, 32768 and 49152 is 0, 32767, 0 and -32767; only the low 16 bits count;
- `tri` and `square` at the corners of their cycle;
- `saw(p)` for A4: the energy off the harmonics is at least 10 dB below the raw saw's (the
  design measured -35 dB against -19 dB);
- the first values of `noise`, fixed in the test, so that the formula can't change by
  accident;
- `decay(0, h)` is 65536, `decay(h, h)` is 32768, `decay(x, 0)` is 0, and a negative `x`
  gives 65536;
- a result outside 16 bits is clipped, and reported;
- a named part that is used twice is computed once;
- every instrument of the design's three scores, in blocks of 16,384, of 1000 and in one
  piece: the same samples each time;
- the kick of the design, played at A1: its pitch is 223 Hz at the start and 62 Hz after
  100 ms, measured from the phase.

## Done when

The instruments of the three scores compute to the same samples in blocks as in one piece,
and every rule of the arithmetic has a test that names the sentence of the design it checks.

## As built

Built on 2026-10-02. Every instrument of the three scores, and the pad with a tail, gives
exactly the samples of the functions in [reference/scores.py](reference/scores.py), computed
in blocks. Decided while building:

- **`compute_instrument(parts, sample, values, more)`** takes the named parts and the last
  line, not an instrument: the score reader of step 4 doesn't exist yet, and this module
  doesn't need it. `more` is 1 when the values hold the one sample more that `saw` and
  `square` look ahead to. That sample is dropped, and it doesn't count as clipped.
- **`blocks(length, size)`** gives the pieces of a note: the first sample of each, the one
  after its last, and whether it needs the sample more. The renderer of step 6 uses it.
- **The last piece of a note is never a single sample.** The last sample of a note takes
  its `d` from the sample before, so that sample has to be in the same piece. A piece that
  would leave one sample over takes it along: a note of 16,385 samples is one piece.
- **A plain number is an array of one number.** numpy wraps an array around in silence. For
  a plain number it warns. The tests run with every warning as an error.
- **`/` divides the sizes as unsigned numbers** and puts the sign back. With `abs` alone the
  lowest number, -2^63, has no size, and half of it would come out positive.
- **`tri` isn't mirrored exactly.** Its formula rounds toward 32767, so `tri(8192)` is 16384
  and `tri(40960)` is -16383. The formula above is the definition, and it stays.
- **The kick's pitch, measured:** 223 Hz in its first sample, 141 Hz after 20 ms and 61 Hz
  after 100 ms. The design said 139 Hz and 62 Hz. Those two were estimates, and the design
  now has the measured numbers.
- **The saw's table of the design is a test:** -25, -19, -15 and -12 dB for the raw saw
  against -41, -35, -32 and -28 dB for `saw(p)`, at A2, A4, C6 and C7.
- **Timed here:** one voice for one minute, the lead of the second score with `saw` and two
  gliding variables, in blocks of 16,384: 0.09 s.

## Not in this step

The fades, the tail and the mix. They belong to the note, not to the expression, and they
are in step 6.
