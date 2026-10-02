# Step 9: the manual

[The plan](README.md) · the design: [addon-music.md](../../addon-music.md), all of it

**Needs:** step 8. **Changes:** `prompt()` in `addons/music.py`. **Makes:**
`tests/test_music_manual.py`.

The manual is what `addon_help("music")` returns. The AI reads it once per boot, and then
writes scores from it alone: it never sees the design document. So the manual decides how
many tries a score takes, and how good it sounds.

## Build

**What it holds,** in this order:

| Part | What | Taken from the design's |
|---|---|---|
| What this is | A sound card. `play(path, loop)`, `stop()`, the `finished` event. The addon defines no command | Section 1 |
| A whole score | One short score that uses every part: a setting, a variable, two instruments, a pattern, a chord, `+`, a placement with transposing and repeats, a glide | Sections 2 and 5 |
| The rules of the file | One thing per line, what is indented, what is declared above, comments | Section 2 |
| Events | The five fields, a chord, `+` and `+4`, a jump and a glide | Section 4 |
| Patterns and the song | A length, placing, transposing, repeating, where the song ends | Section 4 |
| Instruments | The names, the operators with the two traps, the functions, clipping, the tail, named parts | Section 3 |
| Recipes | Only ones that were heard: the kick, the snare, the hat, the pad with a tail, the lead, the plucked sine, the bell, the electric piano | Section 3 |
| What `play` returns | `seconds` and `peak`; what `turned_down_to` and `clipped` mean and what to do about each | Section 1 |
| When a score fails | Every problem comes with its line. Fix them all, then play again | Section 1 |
| Writing well | Keep it short: what repeats is a pattern. Velocities so that the peak lands between 50 and 100 | Sections 5 and 8 |
| The limits | The numbers of step 6 | Section 6 |

**The rules for writing it:**
- **It says what to write, not why.** The reasons stay in the design.
- **Every example is a real one.** No example in the manual is made up for it without being
  run: a test takes each one out of the text and checks it.
- **Recipes that nobody has heard aren't in it.** A wrong recipe is worse than none, because
  the AI can't hear that it is wrong.
- **It has a size limit:** 8000 characters. Every boot that uses the addon pays for reading
  it. The step measures what one `addon_help` costs, from `hallux.log`.

**What the manual says about the machine around it,** in two or three lines: how the sound
card shows inside the machine is the AI's choice, a score is an ordinary file that `nano`
can edit, and what `play` returns is printed the way a player would print it.

## Tests

- every score in the manual reads, unfolds and renders without a problem;
- every recipe in it computes without clipping at full velocity;
- every function and every name the manual lists exists in `expr.py`, and every one that
  exists is listed: neither can change without the other;
- every limit it states is the number in `limits.py`;
- it is under its size limit;
- the loader still takes the file.

## Done when

The tests pass, and the manual's size and the cost of reading it are written into this
plan's status.

## As built

Built on 2026-10-02. The manual is 7987 characters, in the nine parts of the table above
after a short start. Every example in it stands in a block, and a test takes each block out
and runs it.

**It was tried on a reader.** A model that had read the manual and nothing else wrote three
scores, each in one go and untested: a tune with a bass, chords and a melody, eight bars of
drums over a bass that fades through a variable, and a piece with three instruments of its
own, two tails and a pattern inside a pattern inside a pattern. **All three played on the
first try,** with peaks of 64, 77 and 55. They are kept as they came, in `tests/scores/`, and
a test plays them. Rendered, they are `test-music/step9-written-from-the-manual.wav`.

The reader also listed what it had to guess. The manual it read was 7718 characters; what
it asked for and what fit was added afterwards, and other sentences were shortened to make
room:

- the fields of a placement, `(start, pattern, transpose, times)`, and that `PATTERN riff
  32:` is how a length is written;
- that a `+` below a repeated pattern starts after all the repeats;
- that transposing adds up through patterns placed in patterns;
- that a named part belongs to its instrument, that case counts, and that a comment may be
  indented;
- that a glide is a straight line, that a note ends at its duration, that `>>` keeps the
  sign, and that `p` never folds back;
- one more bit for each doubling of the waves that are added up;
- vibrato, with `sin(t * 8) >> 2` from the design;
- how loud each recipe is alone, and that `seconds` counts the tails;
- that a loop starts with its variables reset.

Left out, for the room: what a render costs, and what happens to an event that runs past a
pattern's length. The second isn't a mistake anyone can make: it just rings on.

Decided while building:

- **The examples are in blocks between lines of three backticks.** The AI reads them as
  what they are, and the tests can find them.
- **The limits are numbers in the text.** The addon can't import the child's `limits.py`
  without importing its package. A test builds the same sentence from `limits.py` and
  compares.
- **The answer it shows is a real one:** `{"ok": true, "seconds": 8.0, "peak": 98}` is what
  the drum beat of the design returns.
- **It doesn't say what it can't do** (no echo, no filter, one channel). There was no room,
  and a score that asks for those can't be written anyway.
- **What reading it costs wasn't measured.** That needs a real session, and its
  `hallux.log`. From its size it should be about 2500 tokens. Step 10 measures it.

## For the user

Read the manual once. It is the one text here that the AI learns the addon from, and it is
short enough to read in a few minutes.
