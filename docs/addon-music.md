# The music addon

**Status:** a proposal as discussed. Nothing here is implemented, and no code exists for it yet.
What an addon is, and how Hallux loads one, is in [addons.md](addons.md). The open questions
are at the end, with my recommendations.

## In short

1. **The addon is a bridge to the sound card.** It has two functions, `play(path)` and
   `stop()`.
2. **A song is one score file on the machine's disk.** It holds the sample rate, the tempo, the
   variables, the instruments, the patterns and the song.
3. **An instrument is a bytebeat expression:** an integer formula of `t`, `note` and `vel` that
   returns one sample from 0 to 255.
4. **Everything that happens is an event,** `(start, duration, value, target, velocity)`. A
   note and a change to a variable have the same shape.
5. **A pattern holds events that repeat, and the song places patterns in time,** transposed if
   wanted. The song can hold single events too.
6. **The AI writes the score, and real code plays it.** The sound is real; the player around
   it is imagined.

---

## 1. The functions

| Function | What it does |
|---|---|
| `play(path)` | Reads the score at that path on the machine's disk, checks it, starts playing and returns at once |
| `stop()` | Stops whatever is playing. Hallux also calls it on halt, reboot and the hard exit |

- **`play` doesn't wait for the song.** It returns a short result, such as
  `{"ok": true, "seconds": 42}`, and the sound goes on by itself.
- **A score that fails a check isn't played.** `play` returns the line and the reason, such as
  `{"error": "line 7: unknown name CUTOF"}`, and the AI prints that the way a player would.
- **The path is a path inside the machine.** The addon reads it through Hallux's path jail and
  never opens it by itself. That depends on open question 4 in [addons.md](addons.md).

**How a song gets played:**
1. The AI reads the manual with `addon_help("music")`, once per boot.
2. A score file is written to the disk. The AI writes it with the normal disk tools, or the
   user writes or edits it in nano.
3. The AI calls `play` with the path.
4. The addon reads and checks the file, and starts the sound.
5. The AI prints what a player would print.

The song survives a reboot, and playing it again costs one call and no writing.

---

## 2. The score file

A sketch. The exact syntax isn't decided (see the open questions); this shows the parts.

```text
RATE = 8000
BPM = 120
VOL = 255

INSTRUMENT lead:
    (((sin(t * note >> 8) - 128) * vel >> 8) * VOL >> 8) + 128

INSTRUMENT bass:
    ((t * note >> 8 & 255) + sin(t * note >> 9)) >> 1

PATTERN riff:
    (0, 8, A4, lead)
    (8, 8, C5, lead, 75)

SONG:
    (0,  riff)
    (16, riff, 3)
    (0,  32, A2, bass)
    (24,  8, 0,  VOL)
```

| Part | Example | Meaning |
|---|---|---|
| Sample rate | `RATE = 8000` | Samples per second. The default is 8000, the classic bytebeat rate. Only a short list of rates is allowed |
| Tempo | `BPM = 120` | Quarter notes per minute. It sets how long a 32nd note lasts |
| Variables | `VOL = 255` | A name and its starting value. A name must be declared before an expression or an event may use it |
| Instruments | `INSTRUMENT lead:` | A name and one expression (section 3) |
| Patterns | `PATTERN riff:` | A name and a list of events, timed from the pattern's own start (section 4) |
| The song | `SONG:` | What plays and when: patterns placed in time, and single events (section 4) |
| Comments | `# bar 1: C major` | A line that starts with `#` is skipped. A comment can't follow an event on the same line, because sharps use `#` too (`C#3`) |

**The sample rate is part of the song.** The same expression sounds higher or lower at another
rate, so the rate is saved with the score.

---

## 3. Instruments

An instrument is one expression. The addon evaluates it once per sample for every note that
sounds, and the low 8 bits of the result are the sample: 0 to 255, with 128 as silence.

**The names an expression can use:**

| Name | What it is |
|---|---|
| `t` | The sample counter. It starts at 0 when the note starts and rises by 1 per sample. It never folds back: the expression does its own wrapping, with `& 255` and the like |
| `note` | The pitch, as a phase step: how far the wave moves per sample, where 65536 is one full cycle. The addon computes it as `frequency × 65536 / RATE`. At 8000 Hz, A4 (440 Hz) is 3604 and C4 is 2143 |
| `vel` | The note's velocity, 0 to 255, fixed for the whole note. 255 is full |
| A declared variable | Its value at that moment (section 4) |

**What an expression can contain:**
- **Operators:** `+ - * / % & | ^ ~ << >>`, the comparisons, `? :`, and brackets.
- **Whole numbers.**
- **One function, `sin(x)`.** `x` is a position in 256ths of a cycle, and only its low 8 bits
  count. The result is 0 to 255, with 128 in the middle.

Nothing else is accepted. The addon reads the expression with its own small parser, and there
is no `eval`.

**The arithmetic:**
- **32-bit whole numbers that wrap around,** as in C. `t << t` can't grow without limit.
- **Dividing by zero gives 0,** with `/` and with `%`.
- **`>>` keeps the sign,** so `-128 >> 1` is `-64`.
- **The precedence is C's:** `*` binds tighter than `+`, `+` tighter than `>>`, and `>>`
  tighter than `&`. So `x * vel >> 8 * VOL >> 8` shifts by `8 * VOL`. Write
  `((x * vel >> 8) * VOL) >> 8`.

**Recipes.** `t * note` is the position in the wave; `>> 8` cuts it down to 256 steps per
cycle.

| Sound | Expression |
|---|---|
| Saw | `t * note >> 8 & 255` |
| Sine | `sin(t * note >> 8)` |
| Sine, one octave lower | `sin(t * note >> 9)` |
| Saw and sine, half each | `((t * note >> 8 & 255) + sin(t * note >> 8)) >> 1` |
| Sine with velocity | `((sin(t * note >> 8) - 128) * vel >> 8) + 128` |
| Sine that fades out by itself, in half a second at 8000 Hz | `((sin(t * note >> 8) - 128) * ((t >> 4) > 255 ? 0 : 255 - (t >> 4)) >> 8) + 128` |

- **Scale around the middle.** Silence is 128, so loudness is applied to `sample - 128`, and
  128 is added back afterwards. `sin(…) * vel >> 8` alone would push the wave off-centre.
- **Velocity is 0 to 255, not MIDI's 0 to 127.** It matches `>> 8` and the variables. A
  velocity of 75 is about 29% of full.
- **`vel` is only a number.** An instrument can use it for loudness, or for something else,
  such as the balance between the saw and the sine.
- **A long note is safe.** `t * note` wraps around after a minute or two, but wrapping doesn't
  change the low bits, and those are the ones these expressions use.

---

## 4. Events, patterns and the song

### Events

Everything that happens is an event, `(start, duration, value, target, velocity)`:

| Field | Meaning |
|---|---|
| `start` | When it happens, in 32nd notes |
| `duration` | How long it lasts, in 32nd notes |
| `value` | A note name (`A4`, `C#3`) when the target is an instrument; a number when the target is a variable |
| `target` | The name of an instrument or of a variable |
| `velocity` | Optional, for notes only. 0 to 255; the default is 255 |

At 120 BPM, one 32nd note lasts 62.5 ms, which is 500 samples at 8000 Hz.

| Event | What it does |
|---|---|
| `(0, 16, A4, lead)` | A4 on `lead` for a half note, at full velocity |
| `(0, 16, A4, lead, 75)` | The same note, at velocity 75 |
| `(8, 0, 128, VOL)` | `VOL` jumps to 128 at step 8 |
| `(8, 8, 0, VOL)` | `VOL` glides from its current value to 0 between steps 8 and 16 |

**Variables are how a song changes over time.** An expression uses a variable by name, and
events change its value:
- **A duration of 0 is a jump.**
- **A longer duration is a glide** from the current value to the new one, which gives fades
  and sweeps without a click.
- **A new change takes over** from one that is still gliding.
- **Two changes to one variable at the same step are refused,** because it's unclear which
  should win.
- **A variable is shared.** Every instrument that names it sees the same value. What differs
  from note to note is `vel`.

**Several notes can sound at once.** Each note is a voice with its own `t`. The voices are
centred on 128, added together and clipped to 0–255.

### Patterns

A pattern is a named list of events that the song can use more than once.

- **Times count from the pattern's own start.** Step 0 is wherever the song places it.
- **A pattern holds notes, changes to variables, or both.** A sweep that belongs to a riff
  can live in the riff.
- **A pattern can't contain another pattern.** See the open questions.

### The song

`SONG:` says what plays and when. It has two kinds of line:

| Line | Meaning |
|---|---|
| `(start, pattern)` | The pattern plays from that step |
| `(start, pattern, transpose)` | The same, with every note moved by that many semitones. A negative number moves them down |
| `(start, duration, value, target, velocity)` | A single event, for what happens once, such as a fade over the whole song |

- **Patterns placed at the same step play together.** A bass line, the chords and a melody can
  each be written once and arranged separately.
- **Transposing moves the notes only.** Changes to variables in the pattern stay as written.
- **The order of the lines doesn't matter.** The start times do.

---

## 5. Two complete scores

Both are written by hand and checked by calculation. Nothing can play them yet, so nobody has
heard them.

### Chords and a melody

Four bars: C, G, A minor and F on a soft sine, with a melody on top.

```text
RATE = 8000
BPM = 100

INSTRUMENT pad:
    ((sin(t * note >> 8) - 128) * vel >> 8) + 128

INSTRUMENT lead:
    (((((t * note >> 8 & 255) + sin(t * note >> 8)) >> 1) - 128) * vel >> 8) + 128

# C major, held for a bar
PATTERN major:
    (0, 32, C3, pad, 60)
    (0, 32, E3, pad, 60)
    (0, 32, G3, pad, 60)

# A minor, held for a bar
PATTERN minor:
    (0, 32, A2, pad, 60)
    (0, 32, C3, pad, 60)
    (0, 32, E3, pad, 60)

# root, fifth, octave: it fits a major and a minor chord
PATTERN riff:
    (0,   8, C4, lead, 140)
    (8,   8, G4, lead, 140)
    (16, 16, C5, lead, 140)

SONG:
    # bar 1: C major
    (0,  major)
    (0,  riff)
    # bar 2: G major, five semitones down
    (32, major, -5)
    (32, riff, -5)
    # bar 3: A minor
    (64, minor)
    (64, riff, -3)
    # bar 4: F major, seven semitones down
    (96, major, -7)
    (96, riff, -7)
```

- **A bar is 32 steps.** 8 is a quarter note and 16 is a half note. At 100 BPM the piece lasts
  9.6 seconds.
- **A chord is three events with the same start.** Each one is its own voice on `pad`, held
  for the whole bar.
- **Nine events are written and 24 are played.** `major` serves three chords: moved down five
  semitones it is G major, and moved down seven it is F major. `riff` serves all four bars.
- **The velocities are low on purpose.** Four voices sound at once and are added together.
  Three pads at 60 and the lead at 140 reach 125 from the middle at most, inside the 127 that
  fits.

### The same piece with automation

Two variables: `VOL` fades the piece in and out, and `BRIGHT` moves the lead between a sine
and a saw.

```text
RATE = 8000
BPM = 100
VOL = 0
BRIGHT = 0

INSTRUMENT pad:
    (((sin(t * note >> 8) - 128) * vel >> 8) * VOL >> 8) + 128

INSTRUMENT lead:
    (((((t * note >> 8 & 255) * BRIGHT + sin(t * note >> 8) * (255 - BRIGHT) >> 8) - 128) * vel >> 8) * VOL >> 8) + 128

# C major, held for a bar
PATTERN major:
    (0, 32, C3, pad, 40)
    (0, 32, E3, pad, 40)
    (0, 32, G3, pad, 40)

# A minor, held for a bar
PATTERN minor:
    (0, 32, A2, pad, 40)
    (0, 32, C3, pad, 40)
    (0, 32, E3, pad, 40)

PATTERN riff:
    # the tone opens up over three beats and closes again on the fourth
    (0,  24, 255, BRIGHT)
    (24,  8,   0, BRIGHT)
    (0,   8, C4, lead, 130)
    (8,   8, G4, lead, 130)
    (16, 16, C5, lead, 130)

SONG:
    # fade in over the first quarter note, and out over the last half note
    (0,    8, 255, VOL)
    (112, 16,   0, VOL)
    # bar 1: C major
    (0,  major)
    (0,  riff)
    # bar 2: G major
    (32, major, -5)
    (32, riff, -5)
    # bar 3: A minor
    (64, minor)
    (64, riff, -3)
    # bar 4: F major
    (96, major, -7)
    (96, riff, -7)
```

- **A variable starts at its declared value.** `VOL = 0` means the piece begins silent, and
  the first event glides it up to 255.
- **Automation in a pattern repeats with it.** The two `BRIGHT` events are part of `riff`, so
  the lead opens and closes once in every bar. Transposing the riff doesn't change them.
- **Automation for the whole song is a single event in `SONG`.** The two `VOL` fades happen
  once, so they aren't in a pattern.
- **The expression decides what a variable means.** In `lead`, `BRIGHT` is the share of saw
  and `255 - BRIGHT` the share of sine. `VOL` scales both instruments, because both
  expressions name it.
- **The velocities differ from the first score.** The lead is now a full-strength wave, not
  half saw and half sine, so the pads are at 40 and the lead at 130. Together they reach 125
  from the middle at most.

---

## 6. Playing, and the limits

**How the sound is made:**
- **Block by block, while it plays.** The song is never built whole in memory first.
- **With array operations** over a block of `t` values, not one sample at a time in Python.
  At 8000 Hz that's light work.

**The limits.** The AI writes every part of a score, possibly led by text it read in a file,
so the addon treats all of it as untrusted. The numbers are to be chosen when it's built.

| What | Limited to |
|---|---|
| Sample rate | A short list, for example 8000, 11025, 22050 and 44100 |
| Song length | A maximum number of seconds |
| File size | A maximum number of bytes |
| Events, once the patterns are unfolded | A maximum number |
| An expression | A maximum length and nesting depth |
| Whole numbers | What fits in 32 bits |
| Names | Only `t`, `note`, `vel`, `sin` and the declared variables |
| Voices at once | A maximum number |

---

## 7. What it can't do

- **Effects that need memory.** A filter, an echo and a reverb depend on earlier output, and an
  expression only sees the current `t`. Those would have to be features of the addon itself.
- **Triplets.** 32nd notes are whole numbers, which keeps the score simple, but three notes
  don't fit evenly into a beat.
- **Listen.** The AI writes music it can't hear. The manual should carry a few recipes that are
  known to sound right, like the table in section 3.

---

## 8. Costs and risks

- **Writing the score is the slow part.** The AI writes it one character at a time, and the
  user waits. Patterns keep it short: what repeats is written once. Playing a score again
  costs one call.
- **Audio from WSL** goes through WSLg's PulseAudio, which has to work on the host. Whether
  Python can make a sound here at all is the first thing to check.
- **It needs two libraries Hallux doesn't have today:** one for arrays (numpy) and one that
  opens the sound device.
- **Testing stays cheap.** The parser and the sample maths are plain Python: an expression
  and a score go in, and an array of numbers comes out, which a test can compare without any
  sound and without a model call.

---

## Open questions

1. **Samples from 0 to 255, or signed around 0?** Signed samples would make loudness simpler
   (`x * vel >> 8`, with no `- 128` and `+ 128`). My recommendation: 0 to 255, as written
   above. It's what every classic bytebeat formula produces, so known formulas work unchanged.
2. **The syntax of the file.** The sketch in section 2 is line-based: settings, instruments,
   patterns, then the song. My recommendation: keep that shape, and settle the details when
   the parser is written.
3. **Patterns inside patterns?** My recommendation: no. The parser stays simple, and a small
   file can't unfold into a huge song.
4. **Should there be a second counter for the whole song?** `t` restarts with every note, which
   is what lets an expression shape a note. My recommendation: only `t` at first.
5. **What does `play` do while a song is playing?** My recommendation: the new song replaces
   the old one.
6. **Where do the two libraries come from?** My recommendation: an optional install,
   `pip install -e ".[music]"`. Without them the loader skips the addon, like any other addon
   that fails a check.

## Order of work

1. Check that Python can make a sound on this computer.
2. The expression parser and its limits, with tests against known values.
3. The score reader, unfolding the patterns and turning a score into samples, with tests that
   compare arrays.
4. Sound output, `play` and `stop`.
5. The manual that `prompt()` returns.
6. A `--script` run that checks the machine calls `play` instead of imagining it.
