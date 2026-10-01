# The music addon

**Status:** a proposal as discussed. Nothing of the music addon is implemented. The addon
system it would run on is built, except the handle through which `play(path)` reads a file
of the machine (step 7 of [plans/addons-plan.md](plans/addons-plan.md)). What an addon is, and
how Hallux loads one, is in [addons.md](addons.md).

**Revised on 2026-10-01,** after a review of the first version. Two requirements came from the
user: sound at 44100 Hz, and samples finer than 8 bits. The other changes were my
recommendations, and they were accepted together. The table under Decisions lists all of
them. What I added while writing this version, and nobody has confirmed, is in open questions
5 to 7.

## In short

1. **The addon is a bridge to the sound card.** It has two functions, `play(path, loop)` and
   `stop()`, and one event, `finished`.
2. **A song is one score file on the machine's disk.** It holds the tempo, the variables, the
   instruments, the patterns and the song.
3. **The sound is 16-bit at 44100 Hz.** A sample is a whole number from -32768 to 32767, and
   0 is silence.
4. **An instrument is an expression in the style of bytebeat:** an integer formula of `t`,
   `p`, `vel` and `dur` that returns one sample.
5. **Everything that happens is an event,** `(start, duration, value, target, velocity)`. A
   note and a change to a variable have the same shape.
6. **A pattern holds events that repeat, and the song places patterns in time,** transposed
   and repeated if wanted. The song can hold single events too.
7. **The AI writes the score, and real code plays it.** The sound is real; the player around
   it is imagined. The AI can't listen, so the addon tells it what it measured.

---

## 1. The functions

| Function | What it does |
|---|---|
| `play(path, loop)` | Reads the score at that path on the machine's disk, checks it, renders it, starts playing and returns. `loop` is optional and false by default; with `true` the song starts again when it ends, until something stops it |
| `stop()` | Stops whatever is playing. Hallux also calls it on halt, reboot and the hard exit |

- **`play` doesn't wait for the song to end.** It returns when the song is rendered and the
  sound has started, and the sound goes on by itself.
- **The result says what the addon measured,** such as
  `{"ok": true, "seconds": 9.6, "peak": 98}`:
  - `seconds` is the length of the song;
  - `peak` is the loudest point of the mix as it was written, in percent of full scale. A
    song that peaks at 20 is quiet, and its velocities can go up.
- **A mix that is too loud is turned down, never clipped.** When `peak` is over 100, the addon
  turns the whole song down until the loudest point just fits, and says so:
  `{"ok": true, "seconds": 9.6, "peak": 163, "turned_down_to": 61}`.
- **A score that fails a check isn't played.** `play` returns every problem it found, not
  only the first, each with its line:
  `{"error": "line 7: unknown name CUTOF\nline 12: two different changes to VOL at step 8"}`.
  The AI prints that the way a player would.
- **The path is a path inside the machine.** The addon reads it through Hallux's path jail and
  never opens it by itself. That depends on open question 4 in [addons.md](addons.md).

**The event.** The addon reports one event (see [addon-events.md](addon-events.md)):

| Event | When |
|---|---|
| `{"event": "finished"}` | A song reached its end by itself |

- **It isn't sent when something stopped the song:** `stop()`, a new `play`, a halt or a
  reboot. A song that loops never ends by itself, so it never sends it.
- **The AI hears it only after `addon_listen("music")`,** like any other event. With it, an
  imagined player can print its last line, or start the next song of a list.

**How a song gets played:**
1. The AI reads the manual with `addon_help("music")`, once per boot.
2. A score file is written to the disk. The AI writes it with the normal disk tools, or the
   user writes or edits it in nano.
3. The AI calls `play` with the path.
4. The addon reads and checks the file, renders the song and starts the sound.
5. The AI prints what a player would print.

The song survives a reboot, and playing it again costs one call and no writing.

---

## 2. The score file

A sketch. The exact syntax isn't decided (see the open questions); this shows the parts.

```text
BPM = 120
VOL = 255

INSTRUMENT lead:
    sin(p) * vel * VOL >> 16

INSTRUMENT bass:
    ((p & 65535) - 32768 + sin(p >> 1)) >> 1

PATTERN riff 16:
    (0, 8, A4, lead)
    (8, 8, C5, lead, 75)

SONG:
    (0,  riff)
    (16, riff, 3)
    (0,  32, A2, bass)    # one long note under both riffs
    (24,  8, 0,  VOL)
```

| Part | Example | Meaning |
|---|---|---|
| Tempo | `BPM = 120` | Quarter notes per minute |
| Steps | `STEPS = 8` | Steps per quarter note. The default is 8, so a step is a 32nd note (section 4) |
| Variables | `VOL = 255` | A name and its starting value. A name must be declared before an expression or an event may use it |
| Instruments | `INSTRUMENT lead:` | A name and one expression (section 3) |
| Patterns | `PATTERN riff 16:` | A name, a length in steps if the pattern is to be repeated, and a list of events timed from the pattern's own start (section 4) |
| The song | `SONG:` | What plays and when: patterns placed in time, and single events (section 4) |
| Comments | `# bar 1: C major` | A `#` at the start of a line, or after the closing `)` of an event, starts a comment. Inside the brackets a `#` is a sharp (`C#3`) |

**There is one sample rate, 44100 Hz.** The score has no setting for it, so `t` counts the
same in every score.

**Note names** are a letter from `A` to `G`, an optional `#` or `b`, and the octave: `A4`
(440 Hz), `C#3`, `Bb3`.

**All names share one namespace.** A variable, an instrument and a pattern can't have the same
name, and a name can be declared only once. These are taken: `t`, `p`, `vel`, `dur`, `sin`,
`noise`, `BPM`, `STEPS`, and anything shaped like a note name, so a variable can't be called
`A4`. Upper and lower case differ.

---

## 3. Instruments

An instrument is one expression. The addon evaluates it once per sample for every note that
sounds, and the result is the sample: -32768 to 32767, with 0 as silence.

**The names an expression can use:**

| Name | What it is |
|---|---|
| `t` | The sample counter. It starts at 0 when the note starts and rises by 1 per sample, 44100 per second. It's for what depends on time, such as a fade |
| `p` | The position in the wave, in 65536ths of a cycle. It starts at 0 when the note starts and never folds back: after one cycle it is 65536, after two 131072. It's for what depends on pitch. The expression does its own wrapping, with `& 65535` |
| `vel` | The note's velocity, 0 to 255, fixed for the whole note. 255 is full |
| `dur` | The note's length in samples, fixed for the whole note |
| A declared variable | Its value at that moment (section 4) |

**`p` is `t` scaled to the note's pitch, and the addon computes it.** It is
`t × step >> 16`, where `step` is `frequency × 2³² / 44100`, rounded. For A4 the step is
42,852,281. That keeps every note in tune to less than a thousandth of a cent, and the
product can't wrap around within a song.

**What an expression can contain:**
- **Operators:** `+ - * / % & | ^ ~ << >>`, the comparisons, `? :`, and brackets.
- **Whole numbers.**
- **Two functions:**
  - `sin(x)`: `x` is a position in 65536ths of a cycle, and only its low 16 bits count. The
    result is -32767 to 32767.
  - `noise(x)`: a value from -32768 to 32767 that looks random. The same `x` always gives the
    same value, so a song sounds the same every time. `noise(t)` changes with every sample;
    `noise(t >> 3)` holds each value for 8 samples and sounds darker.

Nothing else is accepted. The addon reads the expression with its own small parser, and there
is no `eval`.

**The arithmetic.** These rules are the addon's own. "As in C" isn't enough: C leaves some of
these cases undefined, and array libraries round differently from C.
- **64-bit whole numbers that wrap around.** A 16-bit sample times a velocity times two
  variables doesn't fit 32 bits, and with 64 nobody has to count.
- **`/` and `%` round toward zero:** `-7 / 2` is `-3`, and `-7 % 2` is `-1`.
- **Dividing by zero gives 0,** with `/` and with `%`.
- **`>>` keeps the sign,** so `-128 >> 1` is `-64`.
- **A shift uses the low 6 bits of its count,** so `x << 64` is `x`.
- **A comparison gives 1 or 0.**
- **The precedence is C's:** `*` binds tighter than `+`, `+` tighter than `>>`, `>>` tighter
  than the comparisons, and those tighter than `&`. Two traps:
  - `x * vel >> 8 * VOL >> 8` shifts by `8 * VOL`. Write `x * vel * VOL >> 16`.
  - `p & 65535 - 32768` is `p & 32767`. Write `(p & 65535) - 32768`.
- **A result outside -32768 to 32767 is clipped** to that range (open question 5).

**Recipes.** Nobody has heard these yet.

| Sound | Expression |
|---|---|
| Sine | `sin(p)` |
| Sine, one octave lower | `sin(p >> 1)` |
| Sine, one octave higher | `sin(p << 1)` |
| Saw | `(p & 65535) - 32768` |
| Saw and sine, half each | `((p & 65535) - 32768 + sin(p)) >> 1` |
| Sine with velocity | `sin(p) * vel >> 8` |
| Sine that fades out over the note's length | `sin(p) * (dur - t) / dur` |
| Sine that fades out by itself, in half a second | `sin(p) * (t > 22050 ? 0 : 22050 - t) / 22050` |
| Noise that fades out over the note's length | `noise(t) * (dur - t) / dur` |

- **Loudness is a multiplication.** Silence is 0, so `x * vel >> 8` scales a wave and keeps it
  centred.
- **Velocity is 0 to 255, not MIDI's 0 to 127.** It matches `>> 8` and the variables. A
  velocity of 75 is about 29% of full.
- **`vel` is only a number.** An instrument can use it for loudness, or for something else,
  such as the balance between the saw and the sine.
- **A quiet voice keeps its detail.** A pad at velocity 60 still has about 15,000 levels. With
  8-bit samples it would have 60.
- **A classic 8-bit bytebeat formula needs wrapping.** Put `t * 80 / 441` where the formula
  has `t`, because it was written for 8000 Hz, and turn its result into a 16-bit sample:
  `((formula & 255) - 128) << 8`. It then sounds as it did, with 8-bit detail.
- **Drums need recipes that somebody has heard.** `noise` is there for them, but a kick and a
  snare that sound right have to be found by ear first (the order of work, step 2).

### The edges of a note

A wave that starts or stops anywhere but at 0 makes a click. A saw starts at -32768.

- **The addon fades every note in and out,** over a few thousandths of a second. It does that
  after the expression, so no instrument has to. The lengths are open question 7.
- **`dur` is for a shape the instrument wants itself.** `dur - t` is the number of samples
  left, so `sin(p) * (dur - t) / dur` is a note that dies away like a plucked string.
- **Multiply first, then divide.** These are whole numbers: `(dur - t) / dur` on its own is 1
  for the first sample and 0 for all the others, so `sin(p) * ((dur - t) / dur)` is silent.
- **A note ends at its duration.** Nothing sounds after it.

---

## 4. Events, patterns and the song

### Events

Everything that happens is an event, `(start, duration, value, target, velocity)`:

| Field | Meaning |
|---|---|
| `start` | When it happens, in steps |
| `duration` | How long it lasts, in steps |
| `value` | A note name (`A4`, `C#3`, `Bb3`) when the target is an instrument; a number when the target is a variable |
| `target` | The name of an instrument or of a variable |
| `velocity` | Optional, for notes only. 0 to 255; the default is 255 |

**A step is a 32nd note, unless `STEPS` says otherwise.** `STEPS` is the number of steps in a
quarter note, and the default is 8. `STEPS = 24` makes triplets possible: a 32nd note is then
3 steps, a 16th note 6, and an eighth-note triplet 8.

**A step isn't a whole number of samples.** At 120 BPM a 32nd note lasts 62.5 ms, which is
2756.25 samples. The addon works out each event's first sample from its step, and never adds
lengths up, so a long song can't drift.

| Event | What it does |
|---|---|
| `(0, 16, A4, lead)` | A4 on `lead` for a half note, at full velocity |
| `(0, 16, A4, lead, 75)` | The same note, at velocity 75 |
| `(8, 0, 128, VOL)` | `VOL` jumps to 128 at step 8 |
| `(8, 8, 0, VOL)` | `VOL` glides from its current value to 0 between steps 8 and 16 |

**Variables are how a song changes over time.** An expression uses a variable by name, and
events change its value:
- **A duration of 0 is a jump.**
- **A longer duration is a glide** from the current value to the new one, sample by sample,
  which gives fades and sweeps without a click.
- **A new change takes over** from one that is still gliding.
- **Two different changes to one variable at the same step are refused,** because it's unclear
  which should win. Two that are the same count as one. A pattern that changes a variable can
  then be played on top of itself, such as a riff and the same riff four semitones up.
- **A variable is shared.** Every instrument that names it sees the same value. What differs
  from note to note is `vel`.

**Several notes can sound at once.** Each note is a voice with its own `t` and `p`. The voices
are added together. If the sum is too loud anywhere, the whole song is turned down (section 1).

### Patterns

A pattern is a named list of events that the song can use more than once.

- **Times count from the pattern's own start.** Step 0 is wherever the song places it.
- **A pattern holds notes, changes to variables, or both.** A sweep that belongs to a riff
  can live in the riff.
- **A pattern can have a length,** in steps: `PATTERN riff 32:`. The length says where the
  next repeat starts. A note may ring past it.
- **A pattern can place patterns that are declared above it,** with the same lines the song
  uses. A verse can then be built from bars, and a bar from beats. Because only patterns from
  above can be used, a pattern can never contain itself.

```text
PATTERN beat 8:
    (0, 2, C2, kick)
    (4, 1, C6, hat)

PATTERN bar 32:
    (0, beat, 0, 4)

SONG:
    (0, bar, 0, 16)
```

Two events, one line in `bar` and one in `SONG` give 16 bars: 128 notes. (The instruments
`kick` and `hat` aren't shown.)

### The song

`SONG:` says what plays and when. It has two kinds of line:

| Line | Meaning |
|---|---|
| `(start, pattern)` | The pattern plays from that step |
| `(start, pattern, transpose)` | The same, with every note moved by that many semitones. A negative number moves them down |
| `(start, pattern, transpose, times)` | The same, played that many times, each one starting where the one before ended |
| `(start, duration, value, target, velocity)` | A single event, for what happens once, such as a fade over the whole song |

- **The second field tells the two kinds apart.** In a placement it is a pattern's name; in an
  event it is a number.
- **Repeating needs the pattern's length.** A repeat count on a pattern without a length
  fails the check.
- **Patterns placed at the same step play together.** A bass line, the chords and a melody can
  each be written once and arranged separately.
- **Transposing moves the notes only.** Changes to variables in the pattern stay as written.
  When a transposed pattern places another pattern, the two numbers add up.
- **The order of the lines doesn't matter.** The start times do.

---

## 5. Two complete scores

Both are written by hand and checked by calculation. Nothing can play them yet, so nobody has
heard them.

### Chords and a melody

Four bars: C, G, A minor and F on a soft sine, with a melody on top.

```text
BPM = 100

INSTRUMENT pad:
    sin(p) * vel >> 8

INSTRUMENT lead:
    ((p & 65535) - 32768 + sin(p)) * vel >> 9

# C major, held for a bar
PATTERN major 32:
    (0, 32, C3, pad, 60)
    (0, 32, E3, pad, 60)
    (0, 32, G3, pad, 60)

# A minor, held for a bar
PATTERN minor 32:
    (0, 32, A2, pad, 60)
    (0, 32, C3, pad, 60)
    (0, 32, E3, pad, 60)

# root, fifth, octave: it fits a major and a minor chord
PATTERN riff 32:
    (0,   8, C4, lead, 140)
    (8,   8, G4, lead, 140)
    (16, 16, C5, lead, 140)

SONG:
    (0,  major)        # bar 1: C major
    (0,  riff)
    (32, major, -5)    # bar 2: G major, five semitones down
    (32, riff, -5)
    (64, minor)        # bar 3: A minor
    (64, riff, -3)
    (96, major, -7)    # bar 4: F major, seven semitones down
    (96, riff, -7)
```

- **A bar is 32 steps.** 8 is a quarter note and 16 is a half note. At 100 BPM the piece lasts
  9.6 seconds.
- **A chord is three events with the same start.** Each one is its own voice on `pad`, held
  for the whole bar.
- **Nine events are written and 24 are played.** `major` serves three chords: moved down five
  semitones it is G major, and moved down seven it is F major. `riff` serves all four bars.
- **The lead is half saw and half sine.** `>> 9` is the halving and the velocity's `>> 8` in
  one shift.
- **The velocities are chosen to fit.** Four voices sound at once and are added together.
  Three pads at 60 and the lead at 140 reach 98% of full scale at most, so nothing is turned
  down. With higher velocities the piece would still play, only turned down as a whole.

### The same piece with automation

Two variables: `VOL` fades the piece in and out, and `BRIGHT` moves the lead between a sine
and a saw.

```text
BPM = 100
VOL = 0
BRIGHT = 0

INSTRUMENT pad:
    sin(p) * vel * VOL >> 16

INSTRUMENT lead:
    (((p & 65535) - 32768) * BRIGHT + sin(p) * (255 - BRIGHT)) * vel * VOL >> 24

# C major, held for a bar
PATTERN major 32:
    (0, 32, C3, pad, 40)
    (0, 32, E3, pad, 40)
    (0, 32, G3, pad, 40)

# A minor, held for a bar
PATTERN minor 32:
    (0, 32, A2, pad, 40)
    (0, 32, C3, pad, 40)
    (0, 32, E3, pad, 40)

PATTERN riff 32:
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
    (0,  major)        # bar 1: C major
    (0,  riff)
    (32, major, -5)    # bar 2: G major
    (32, riff, -5)
    (64, minor)        # bar 3: A minor
    (64, riff, -3)
    (96, major, -7)    # bar 4: F major
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
- **One shift at the end is enough.** The lead multiplies by three numbers up to 255
  (`BRIGHT`, `vel` and `VOL`), so it shifts by 24 once. The product reaches 543 billion, which
  is why the numbers are 64 bits wide.
- **The velocities differ from the first score.** The lead is now a full-strength wave, not
  half saw and half sine, so the pads are at 40 and the lead at 130. Together they reach 97%
  of full scale at most.

---

## 6. Playing, and the limits

**How the sound is made:**
- **In a child process,** like the window of [addons/window.py](../addons/window.py). numpy
  is only imported there. Hallux itself only checks that it is installed, so it doesn't slow
  the start. The child can be ended when a render takes too long, and nothing it prints can
  land on the machine's screen.
- **The child hands the samples to PulseAudio itself.** It calls the system's
  `libpulse-simple` through `ctypes`: open a stream, write samples, wait until they are
  played, close. That's about 40 lines in the addon, and no Python sound package. WSLg's sound
  server is PulseAudio, so nothing is in between.
- **The child writes the song in small pieces.** It always knows where the song is. So it can
  start again at the end of a song that loops, stop in the middle, and report `finished` when
  the last piece has been played.
- **The addon reads the score, not the child.** It reads the file through Hallux's handle and
  passes the text on. The child never opens a file of the machine.
- **The whole song is rendered first, then played.** That is what lets `play` report the
  length and the peak, and turn down a mix that is too loud. Five minutes are 13.2 million
  samples, about 26 MB.
- **With array operations** over many `t` values at once, not one sample at a time in Python.
- **A song that loops starts again from the top,** with every variable back at its declared
  value.
- **`stop()` ends the sound at once.** The child throws away what the server hasn't played
  yet. On the hard exit the child goes away with Hallux.

**The limits.** The AI writes every part of a score, possibly led by text it read in a file,
so the addon treats all of it as untrusted. The numbers are to be chosen when it's built.

| What | Limited to |
|---|---|
| Song length | A maximum number of seconds, short enough that rendering fits well inside the 10 seconds Hallux gives a call |
| File size | A maximum number of bytes |
| Events, once the patterns are unfolded | A maximum number. It also bounds repeats and patterns inside patterns |
| Patterns inside patterns | A maximum depth |
| An expression | A maximum length and nesting depth |
| Whole numbers | What fits in 64 bits |
| Notes | C0 to B9, after transposing |
| Names | Only `t`, `p`, `vel`, `dur`, `sin`, `noise` and the declared variables |
| Voices at once | A maximum number |
| Problems reported by one `play` | A maximum number, so the result stays small |

---

## 7. What it can't do

- **Effects that need memory.** A filter, an echo and a reverb depend on earlier output, and an
  expression only sees the current `t`. Those would have to be features of the addon itself.
- **Pitch bends and vibrato.** A note's pitch is fixed for the whole note. Because the addon
  computes `p`, a bend can be added later without changing the scores that exist.
- **A sound after the end of a note.** A note stops at its duration, with the short fade.
- **Listen.** The AI writes music it can't hear. `play` gives it numbers, the length and the
  peak, and the manual should carry recipes that are known to sound right.

---

## 8. Costs and risks

- **Writing the score is the slow part.** The AI writes it one character at a time, and the
  user waits. Patterns and repeats keep it short: what repeats is written once. Playing a
  score again costs one call.
- **Rendering takes time, and nobody has measured it.** My guess is a few seconds for a few
  minutes of music. The sound starts only after that, and the call has to finish within
  Hallux's 10 seconds. The limit on a song's length has to come from a measurement.
- **Audio from WSL** goes through WSLg's PulseAudio, which has to work on the host. On this
  computer a probe opened a stream at 44100 Hz, 16-bit, one channel, through
  `libpulse-simple`, and the server took the samples with a delay of 10 ms. The probe wrote
  only silence, so nobody has heard a sound yet.
- **It works on Linux and WSL only,** where the sound server is PulseAudio, or PipeWire
  speaking PulseAudio's protocol. On another system the loader skips the addon and says why.
- **It needs one Python library and one system library:** numpy for the arrays, which would
  be new, and `libpulse-simple` for the sound (the package `libpulse0` on Debian and Ubuntu).
  It is installed on this computer.
- **The addon owns its link to the sound server.** The `ctypes` declarations have to match
  the C functions exactly, and a test without a sound server can't check that. The API is
  small, five or six functions, and has been stable for many years.
- **Testing stays cheap.** The parser and the sample maths need no sound and no model call: an
  expression and a score go in, and an array of numbers comes out, which a test can compare.

---

## Decisions

Settled on 2026-10-01. The first two are the user's requirements; the rest were my
recommendations.

| Question | Decision | Why |
|---|---|---|
| The sample rate | 44100 Hz, and only that. The first version had 8000 Hz and a `RATE` setting | Required. With one rate, `t` counts the same in every score |
| The samples | Signed 16-bit, silence at 0. The first version had 0 to 255, around 128 | Required: 8 bits aren't enough for good music. Loudness also becomes one multiplication |
| The width of the numbers | 64 bits. The first version had 32 | A 16-bit sample times three numbers up to 255 doesn't fit 32 bits |
| Pitch | `p`, computed by the addon. The first version had `t * note >> 8` | At 44100 Hz a whole-number `note` puts A2 5 cents flat. `p` is exact, and shorter to write |
| The edges of a note | `dur`, and a short fade by the addon | Otherwise every note starts and ends with a click |
| When the song is rendered | Whole, before it plays. The first version had block by block | The AI can't listen, so `play` reports the length and the peak |
| A mix that is too loud | The whole song is turned down, and the result says so | Nothing clips, and the AI doesn't have to add up velocities |
| Problems in a score | All reported at once | Each round trip makes the user wait |
| Two changes at the same step | Refused only when they differ | A pattern with automation can be played on top of itself |
| Repeating | A pattern's length, and a repeat count in the placement | A bar of drums played 64 times is one line |
| Patterns inside patterns | Yes, those declared above. The first version said no | A song is built from parts. No pattern can contain itself, and the limit on unfolded events keeps a small file small |
| Comments | Allowed after an event's `)` | The AI writes them out of habit |
| Flats | `Bb3` is accepted | The AI writes them out of habit |
| Triplets | A `STEPS` setting | Whole steps stay, and three notes fit into a beat |
| Functions | `sin(x)` and `noise(x)` | Drums need noise |
| The arithmetic | The addon's own written rules | C leaves cases undefined, and array libraries round differently |
| Names | One namespace, with note names taken | A variable called `A4` would be read as a note |
| Looping | `play(path, loop)` | Music for a game costs nothing after the first call |
| The end of a song | A `finished` event | An imagined player can end by itself |
| Where the sound is made | A child process | It keeps numpy out of Hallux, as the window addon does with pygame, and it can be ended |
| How the sound gets out | The child hands the samples to PulseAudio itself, through `libpulse-simple` and `ctypes` | WSLg's sound server is PulseAudio, so nothing is in between, and no Python sound package is needed. Two others were looked at. pygame's mixer is a 37 MB game library for playing one buffer. The `sounddevice` package reaches the same server through three more layers, and printed 94 lines of warnings here while starting |

## Open questions

1. **The syntax of the file.** The sketch in section 2 is line-based: settings, instruments,
   patterns, then the song. My recommendation: keep that shape, and settle the details when
   the parser is written.
2. **Should there be a second counter for the whole song?** `t` restarts with every note, which
   is what lets an expression shape a note. My recommendation: only `t` at first.
3. **What does `play` do while a song is playing?** My recommendation: the new song replaces
   the old one.
4. **Where do the two libraries come from?** My recommendation: numpy as an optional install,
   `pip install -e ".[music]"`, and `libpulse-simple` from the system. Without either one the
   loader skips the addon and names what is missing, like any other addon that fails a check.
5. **A voice whose expression gives more than 16 bits: clipped or wrapped?** Classic bytebeat
   keeps the low bits, which turns a wave that is slightly too loud into noise. My
   recommendation: clipped, as section 3 says. An expression that wants wrapping does it
   itself, with `& 65535`.
6. **Does `note` stay as a name?** The first version had it, as the step of the wave per
   sample. My recommendation: no. `p` does its work, and two names for pitch in different
   units would be confusing.
7. **How long are the fades at the edges of a note?** My recommendation: about 2 ms in and
   5 ms out (90 and 220 samples), chosen by ear once something plays. A note that is shorter
   than both together gets shorter fades.

## Order of work

The handle for the machine's files (step 7 of [plans/addons-plan.md](plans/addons-plan.md))
has to exist before step 5.

1. Check that Python can make a real sound on this computer: a tone through `libpulse-simple`
   at 44100 Hz and 16 bits. A silent probe already works (section 8).
2. A throwaway script that renders the two scores of section 5 to a WAV file. It's for
   listening to the instruments and for timing the render, before the syntax is settled.
3. The expression parser, its arithmetic and its limits, with tests against known values.
4. The score reader, unfolding the patterns and turning a score into samples, with tests that
   compare arrays.
5. The child process, the sound output, `play`, `stop`, looping and the `finished` event.
6. The manual that `prompt()` returns.
7. A `--script` run that checks the machine calls `play` instead of imagining it.
