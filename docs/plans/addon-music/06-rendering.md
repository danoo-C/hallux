# Step 6: rendering

[The plan](README.md) · the design: [addon-music.md](../../addon-music.md), sections 1, 3
and 6

**Needs:** steps 3 and 5. **Makes:** `addons/music_engine/render.py`,
`tests/test_music_render.py`. **Changes:** `limits.py`, and section 6 of the design.

The notes of a `Song` become one mixed song, ready to play, with what `play` reports about
it. This is the step whose output the user has already heard: the reference render. It also
times a whole render for the first time, and sets the limits.

## Build

**`render(score, song, loop)`** returns:

| Part | What |
|---|---|
| `first` | The samples to play, 16-bit. For a loop it is the first round |
| `again` | For a loop whose tails ring past the end: the later rounds. Otherwise nothing |
| `seconds` | The length: of the whole song with its tails, or of one round of a loop |
| `peak` | The loudest point of the mix as written, in percent of full scale |
| `turned_down_to` | Only when the mix was too loud: the percent it was turned down to |
| `clipped` | Only when it happened: the instruments whose expression left 16 bits |

**One note:**
1. It lasts its duration plus its instrument's tail.
2. It is computed in blocks of 16,384 samples (step 3). For each block, `t` counts on, `p`
   is `t × step >> 16`, and `vel`, `dur` and `key` are plain numbers.
3. `step` is `round(frequency × 2³² / 44100)`, and the frequency of note number `key` is
   `440 × 2^((key - 69) / 12)`. For A4 the step is 42,852,281.
4. Every variable gets its values for that block from its list of changes. One that doesn't
   change within the block is passed as a plain number.
5. The result is clipped to 16 bits, and the instrument is noted if that changed anything.
6. The note is faded in over its first 90 samples and out over its last 220. Sample `i` of
   the fade-in is multiplied by `i` and divided by 90. The last 220 are multiplied by 220
   down to 1 and divided by 220. Both round down.
7. A note shorter than 310 samples gets both fades shorter in proportion: 90/310 of its
   length in, 220/310 out.
8. It is added into the mix at its first sample.

**A variable over time:**
- It has its declared value until its first change.
- A change with no length is a jump. A longer one is a glide: at sample `s` between its
  first sample `a` and its last `b`, the value is `from + (to - from) × (s - a) / (b - a)`,
  rounded down, and `to` from `b` on.
- `from` is whatever the value is at `a`. So a change that starts while another glides takes
  over from where that one got to.

**The mix:**
- **32-bit numbers,** one per sample. The limit on voices keeps their sum far inside 32 bits.
- **The peak** is the largest sample, positive or negative, as a percent of 32,767, rounded
  to the nearest whole number. A mix that is turned down never reads less than 101.
- **Too loud:** when the largest sample is over 32,767, every sample is multiplied by 32,767
  and divided by the largest. `turned_down_to` is `32767 × 100 / largest`, rounded down.
- **A loop:** the mix is cut at the song's end. What rings past it is added onto the start
  of a copy, and that copy is `again`. Overflow longer than a whole round wraps again. The
  peak is taken over both rounds, and both are turned down together.

**The reference.** [reference/scores.py](reference/scores.py) renders the three scores of the
design, and the pad with a tail, without a parser. The user listened to exactly those
samples. A test loads that file and compares:

| Score | Samples | Largest sample | `seconds` | `peak` |
|---|---|---|---|---|
| Chords and a melody | 423,360 | 31,227 | 9.6 | 95 |
| The same with automation | 423,360 | 30,825 | 9.6 | 94 |
| The drum beat | 352,800 | 31,949 | 8.0 | 98 |
| The pad with a tail, two chords | 174,195 | 28,190 | 4.0 | 86 |

## Timing, and the limits

Nobody has timed a whole render. This step does, with a script kept beside the tests, on
three kinds of score:

| Score | What it stresses |
|---|---|
| The longest song allowed, with 8 voices that sound all the time, each a `saw` with two gliding variables | The sample maths, and the memory |
| The most events allowed, all of them short drum notes | What every single note costs before its first sample |
| The three scores of the design | The ordinary case |

For each it prints the seconds spent reading, unfolding, rendering, and turning the mix into
16-bit samples.

**The rule for the limits:** each stress score renders in under 4 seconds on this computer.
That is half of what the addon allows (step 8), so that a computer half as fast still fits.

**The first numbers,** to be changed by what the timing shows:

| Limit | First number |
|---|---|
| Song length, with its tails | 300 seconds |
| File size | 64 KB |
| Events, once unfolded | 10,000 |
| Patterns inside patterns | 8 deep |
| An expression | 500 characters, nested 40 deep |
| Named parts of an instrument | 16 |
| A tail | 441,000 samples, which is 10 seconds |
| Voices at once | 64 |
| Problems reported by one `play` | 20 |
| `BPM` | 20 to 400 |
| `STEPS` | 1 to 96 |

**If many short notes turn out slow,** a note that was already computed can be used again:
same instrument, number, velocity and length, and an expression that names no variable. A
bar of drums played 64 times is then computed once. It is built only if the timing asks for
it.

## Tests

- the four rows of the reference table: the same samples, one for one;
- a single sine note equals the table of `sin`, times its velocity, with the two fades;
- the fades alone: the exact multipliers, and a note shorter than 310 samples;
- a glide at chosen samples; a jump; a change that takes over a glide;
- a variable that stands still gives the same samples whether passed as a number or as an
  array;
- a block size of 1000 gives the same samples as 16,384;
- a mix that is too loud: `peak` over 100, `turned_down_to`, and the largest sample is
  32,767;
- an instrument that leaves 16 bits is in `clipped`, and only that one;
- a loop of the pad with a tail: `again` is `first` with the overflow added onto its start,
  and a loop without tails has no `again`;
- `seconds` of a song that plays once counts the tail, and of a loop it doesn't.

## Done when

- The real renderer gives the samples of the reference, one for one, for all four rows.
- The timing table is filled in, and the limits follow the rule.
- Section 6 of the design has the numbers, and its "Still to find out" section is gone.

## As built

Built on 2026-10-02. The renderer gives the samples of the reference, one for one, for all
four rows, with one thing to know about the second:

- **The reference's second score kept the pad of the first.** Its lead followed `VOL` and
  `BRIGHT`, but its pads were `sin(p) * vel >> 8` and didn't fade with `VOL`. In the design
  both instruments name `VOL`. The test renders the score the way the reference did and gets
  its samples exactly. The score as the design has it differs from what was heard in the
  pads only: by at most 60 levels in the middle, and by the fade itself in the first 0.6
  seconds and the last 1.2. Its largest sample is 30,766, not 30,825, and its peak is 94.

**The timing,** from `tests/music_timing.py`, on this computer (an i5-11400H, one core, numpy
2.5.3), best of three, in seconds:

| Score | Notes | Length | Reading | Unfolding | Rendering | To 16 bits | Total |
|---|---|---|---|---|---|---|---|
| The longest song, 8 voices with `saw` and two gliding variables | 8 | 300 s | 0.000 | 0.000 | 2.291 | 0.019 | 2.31 |
| The most events, short drum notes | 9984 | 156 s | 0.001 | 0.023 | 1.945 | 0.031 | 2.00 |
| The same with automation | 24 | 9.6 s | 0.000 | 0.000 | 0.021 | 0.000 | 0.02 |
| Chords and a melody | 24 | 9.6 s | 0.000 | 0.000 | 0.016 | 0.000 | 0.02 |
| The drum beat | 40 | 8.0 s | 0.000 | 0.000 | 0.011 | 0.000 | 0.01 |

- **Both stress scores are under 4 seconds, so the first numbers of the limits stand.** They
  are in `limits.py`, and section 6 of the design has them.
- **A drum note costs about 0.2 ms,** nearly all of it sample maths. Using a computed note
  again wasn't needed, and it isn't built.
- **The limits don't bound the length and the voices together.** 64 voices that all sound
  for 300 seconds take 18.4 seconds here. The addon's 8 seconds catch that
  (step 8). A limit on the notes' lengths added up would say it before the render; it isn't
  in the design, and it isn't built.

Decided while building:

- **`render` returns a `Rendered`,** with the six parts of the table above and `report()`,
  which gives what `play` tells the AI.
- **A voice is 32 bits wide in the mix,** and 64 only while a mix that is too loud is turned
  down, a million samples at a time.
- **Turning down rounds down,** like the fades and the glides.
- **`seconds` is rounded to the nearest tenth,** with a half rounded up: the pad with a tail
  is 3.95 seconds and reads 4.0.
- **An instrument only gets the variables it names.** The others aren't worked out for it.
- **A variable is kept as its changes.** For a block in which it stands still it is one
  number, and otherwise only that block's values are made.
- **A sample of -32768 counts as too loud:** the largest is taken without its sign, and
  32,768 is over full scale. The peak then reads 101 and the mix is turned down to 99.

## For the user

A WAV file of the three scores, made by the real renderer from the three score files. It
should sound exactly like the one of 2026-10-02.

**Heard on 2026-10-02.** The file is `test-music/step6-scores.wav`, in a folder that git
ignores: the three scores and the pad with a tail, as the real renderer makes them from the
score files. The user listened to it: it "sounds great". That includes the second score as
the design has it, with pads that fade with `VOL`.
