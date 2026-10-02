# Step 5: unfolding a score

[The plan](README.md) · the design: [addon-music.md](../../addon-music.md), section 4

**Needs:** step 4. **Makes:** `addons/music_engine/song.py`, `tests/test_music_song.py`.

A `Score` still has patterns, chords and `+`. This step turns it into what the renderer
needs: every note and every change, each with its place in samples. It needs no numpy.

## Build

**`unfold(score)`** returns a `Song`, or raises `ScoreError` with the problems, in the same
shape as step 4.

**A `Song` holds:**

| Part | What |
|---|---|
| `notes` | Every note: its first sample, its length in samples, its number (`key`), its instrument, its velocity |
| `changes` | For every variable its changes in order: the first sample, the last, the new value |
| `end` | The sample at which the song ends, and a loop starts again |
| `length` | The samples a song that plays once needs: up to the end of the last tail |

**How it unfolds:**
- **`+` first.** In every block, a `+` becomes the end of the line directly above it, plus
  its distance. The end of an event is its start plus its duration. The end of a placement
  is its start plus the pattern's length times the repeats.
- **Then the placements,** from the song down. A placed pattern's lines move by the
  placement's start, its notes by the transposition, and a repeat adds the pattern's length
  each time. A pattern placed inside a pattern adds both starts and both transpositions.
- **A chord** becomes one note per name.
- **It stops early.** The count of unfolded events is checked while unfolding, not after, so
  a small file can't make Hallux build a million notes first.

**Steps become samples in whole numbers.** A minute is 2,646,000 samples, so step `s` starts
at sample `(2 * s * 2646000 + BPM * STEPS) / (2 * BPM * STEPS)`, rounded down. That is the
nearest sample, with a half rounded up. A note's length is the sample of its end minus the
sample of its start. Nothing is added up along the way, so a long song can't drift.

**Where the song ends:** at the latest step that anything reaches. For an event that is its
start plus its duration. For a placement it is its start plus the length times the repeats,
or, for a pattern without a length, the end of what is in it.

**Problems that only show here,** each with the line of the event, and of the placement that
put it there:

| Problem | Message |
|---|---|
| A note that leaves C0 to B9 by transposing | `line 20: riff moved up by 40 puts C5 (line 12) above B9` |
| Two different changes to a variable at one step | `line 14 and line 31: two different changes to VOL at step 8` |
| More unfolded events than the limit | `line 25: the song has more than N events` |
| Patterns nested deeper than the limit | `line 9: patterns are nested more than N deep` |
| More voices at once than the limit | `line 12: more than N notes sound at step 64` |
| A song longer than the limit | `the song is 14 minutes long, and the limit is N` |

- **Two changes that are the same count as one,** so a pattern with automation can play on
  top of itself.
- **A change that starts while another still glides takes over.** That isn't a problem; the
  renderer handles it (step 6).
- **Voices at once** are counted with the tails, because a tail still sounds.

## Tests

- the first score of the design gives 24 notes. The riff's C4 starts at sample 0 and lasts
  26,460 samples (8 steps at 100 BPM). In bar 2 the pad's notes are G2, B2 and D3;
- the drum beat gives 40 notes and ends at sample 352,800, which is 8 seconds;
- the nested example of section 4 gives 128 notes;
- no drift: at 120 BPM step 1 is sample 2756, step 4 is sample 11,025, and step 4000 is
  exactly 1000 times step 4;
- `STEPS = 24`: three notes of 8 steps fill one beat;
- a `+` chain, `+4` as a rest, a number that starts a new count, `+` after a placement;
- transposing moves the notes and leaves the changes to variables alone;
- the end of a song whose last note stops before its pattern's length is the pattern's end;
- `length` is longer than `end` by the tail of the last notes;
- every row of the problems table.

## Done when

The three scores unfold to 24, 24 and 40 notes at the right samples, and each problem of the
table is reported with its lines.
