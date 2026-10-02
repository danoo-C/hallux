# Step 4: reading a score

[The plan](README.md) · the design: [addon-music.md](../../addon-music.md), sections 2 and 4

**Needs:** step 2. **Makes:** `addons/music_engine/score.py`, `tests/test_music_score.py`,
`tests/scores/*.score`.

The text of a score file becomes its parts, or a list of everything that is wrong with it.
Nothing is unfolded or timed yet: a pattern stays a pattern.

## Build

**`read(text)`** returns a `Score`, or raises `ScoreError` with every problem it found.

**A `Score` holds:**

| Part | What |
|---|---|
| `bpm`, `steps` | The two settings. `steps` is 8 when the file doesn't set it |
| `variables` | Each name with its starting value |
| `instruments` | Each name with its tail in samples, its named parts as trees, and its last line as a tree |
| `patterns` | Each name with its length in steps, or none, and its lines |
| `song` | The lines of `SONG:` |

**A line of a pattern or of the song** is one of two things, and both keep the number of
their line in the file:

| Kind | Fields |
|---|---|
| An event | The start (a number, or `+` with its distance), the duration, the target, and either the notes with a velocity or the number for a variable |
| A placement | The start, the pattern, the transposition, the repeats |

**How the file is read,** by the rules of the design's section 2:
- Line by line. A blank line and a comment line are skipped.
- A line that isn't indented starts a block or sets a value. The indented lines below it
  belong to it.
- An instrument's lines go to `expr.read` (step 2), with the names that line may use.
- In an event, a `#` inside the brackets is a sharp. After the closing bracket it starts a
  comment.
- A note name becomes its number: `12 * (octave + 1)` plus the semitone, so A4 is 69.

**Every problem is collected, each with its line.** The reader goes on after a bad line, and
reports at most one problem per line. They come out in the order of the lines, up to the
limit, and then `… and 7 more`.

| Problem | Message |
|---|---|
| A line that fits nothing | `line 3: can't read this line` |
| An indented line with no block above it | `line 2: this line belongs to nothing: it is indented, and no INSTRUMENT, PATTERN or SONG is above it` |
| A setting given twice, or out of its range | `line 2: BPM is set twice`, `line 1: BPM must be between 20 and 400` |
| A name that is taken | `line 5: sin is a taken name` |
| A name shaped like a note | `line 3: A4 is a note name, and can't be declared` |
| A name declared twice | `line 9: lead is declared twice (first on line 4)` |
| An instrument without an expression | `line 6: INSTRUMENT lead has no expression` |
| A problem in an expression | `line 7: unknown name CUTOF` |
| A comment after an expression | `line 7: a comment can't follow an expression: put it on a line of its own` |
| An event with the wrong number of fields | `line 12: an event is (start, duration, value, target, velocity)` |
| A target that isn't declared above | `line 12: unknown instrument or variable: laed` |
| A number where a note belongs, or a note where a number belongs | `line 14: VOL is a variable: its value is a number, not A4` |
| A chord, or a velocity, on a variable | `line 15: a change to a variable has one value` |
| A velocity outside 0 to 255 | `line 16: a velocity is 0 to 255` |
| A note outside C0 to B9 | `line 17: C10 is outside C0 to B9` |
| A note with no length, or a negative start or duration | `line 18: a note needs a duration of 1 or more` |
| `+` with nothing to count from | `line 10: + has no line above it to count from` |
| `+` after a pattern without a length | `line 11: + can't count from riff: that pattern has no length` |
| A pattern that isn't declared above | `line 20: riff isn't declared above this line` |
| Repeats on a pattern without a length | `line 21: riff has no length, so it can't be repeated` |
| No `SONG:`, two of them, or a block after it | `the file has no SONG:`, `line 30: SONG: must be the last block` |
| An empty block | `line 22: SONG: is empty` |
| A file that is too big | `the score is bigger than N bytes` |

## Tests

- the three scores of the design's section 5, copied into `tests/scores/`, read without a
  problem. Their parts are counted: the first has 2 instruments, 3 patterns and 8 lines in
  the song;
- the sketch of section 2, and the nested `beat` and `bar` example of section 4;
- every row of the problems table, with its line number;
- three mistakes on three lines come back as three problems, in order;
- more problems than the limit end with `… and N more`;
- comments in every place the design allows: a line of their own, indented, after an event;
- `C#3`, `Bb3`, `+`, `+4`, a chord, a negative transposition, `STEPS = 24`;
- a tab as indentation, and Windows line ends.

## Done when

The three scores read clean, and a score with three mistakes comes back with three lines
that say what to write.

## Not in this step

Anything that needs the patterns unfolded: a note that leaves C0 to B9 only after
transposing, two different changes to a variable at one step, the limits on events and on
voices. Those are in step 5.
