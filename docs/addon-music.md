# The music addon

**Status:** a proposal as discussed. Nothing of the music addon is implemented. The addon
system it would run on is built, with the handle through which `play(path)` reads a file
of the machine (step 7 of [plans/addons-plan.md](plans/addons-plan.md)). What an addon is, and
how Hallux loads one, is in [addons.md](addons.md). The plan for building it is in
[plans/addon-music/](plans/addon-music/README.md).

**Revised on 2026-10-01,** after a review of the first version. Two requirements came from the
user: sound at 44100 Hz, and samples finer than 8 bits. The other changes were my
recommendations, and they were accepted together. The first table under Decisions lists all
of them.

**Revised again on 2026-10-02,** after a second review that asked two things: can it be more
efficient, and can an instrument do more. Rendering was timed for the first time (section 8).
The new ideas for instruments were rendered to a WAV file, and the user listened to it, liked
its drum beat and accepted the additions together. The second table under Decisions lists
them. The third score of section 5 is new.

**The open questions were answered on 2026-10-02.** There were ten: four from the first
version, and six details that I had settled while writing and nobody had confirmed. Each had
a recommendation. The user read them all and accepted every one. The answers are now part of
the sections, and the third table under Decisions lists them. What nobody knows yet is under
Still to find out.

**Later on 2026-10-02** the user listened to the first two scores ("they sound good"), and
changed how the sound gets out. It no longer matters that it goes straight to PulseAudio; it
has to be a Python library that installs into the venv, and it has to be heard. I chose
pygame's mixer for that (section 6). The user ran it on this computer, heard the drum beat
through it, and said "it works".

## In short

1. **The addon is a bridge to the sound card.** It has two functions, `play(path, loop)` and
   `stop()`, and one event, `finished`.
2. **A song is one score file on the machine's disk.** It holds the tempo, the variables, the
   instruments, the patterns and the song.
3. **The sound is 16-bit at 44100 Hz.** A sample is a whole number from -32768 to 32767, and
   0 is silence.
4. **An instrument is an expression in the style of bytebeat:** an integer formula of `t`,
   `p`, `vel`, `dur` and `key` that returns one sample. It can use a few built-in waves, a
   level that dies away, and named parts.
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
| `play(path, loop)` | Reads the score at that path on the machine's disk, checks it, renders it, starts playing and returns. A song that is playing is replaced. `loop` is optional and false by default; with `true` the song starts again when it ends, until something stops it |
| `stop()` | Stops whatever is playing. Hallux also calls it on halt, reboot and the hard exit |

- **`play` doesn't wait for the song to end.** It returns when the song is rendered and the
  sound has started, and the sound goes on by itself.
- **The result says what the addon measured,** such as
  `{"ok": true, "seconds": 9.6, "peak": 98}`:
  - `seconds` is the length of the song, up to the end of its last tail. For a song that
    loops it is the length of one round (section 4);
  - `peak` is the loudest point of the mix as it was written, in percent of full scale. A
    song that peaks at 20 is quiet, and its velocities can go up.
- **A mix that is too loud is turned down, never clipped.** When `peak` is over 100, the addon
  turns the whole song down until the loudest point just fits, and says so:
  `{"ok": true, "seconds": 9.6, "peak": 163, "turned_down_to": 61}`.
- **A voice that is too loud by itself is clipped, and `play` names its instrument.** That
  is a different case from a loud mix: one expression gave a sample outside -32768 to 32767
  (section 3). The AI can't hear that, so the result says it:
  `{"ok": true, "seconds": 9.6, "peak": 98, "clipped": ["lead"]}`.
- **A new `play` replaces the song that is playing.** The old song stops and sends no
  `finished`. It's what a player does when another file is opened, and it saves a `stop`
  call.
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

The file is read line by line. This example has every part:

```text
BPM = 120
VOL = 255

INSTRUMENT lead:
    sin(p) * vel * VOL >> 16

INSTRUMENT bass:
    (saw(p) + sin(p >> 1)) >> 1

PATTERN riff 16:
    (0, 8, A4, lead)
    (+, 8, C5, lead, 75)

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
| Instruments | `INSTRUMENT lead:` | A name, a tail if wanted, and one expression, with named parts above it if wanted (section 3) |
| Patterns | `PATTERN riff 16:` | A name, a length in steps if the pattern is to be repeated, and a list of events timed from the pattern's own start (section 4) |
| The song | `SONG:` | What plays and when: patterns placed in time, and single events (section 4) |
| Comments | `# bar 1: C major` | A `#` at the start of a line, indented or not, or after the closing `)` of an event, starts a comment. Inside the brackets a `#` is a sharp (`C#3`) |

**The rules of the syntax:**
- **One thing per line.** Blank lines and comment lines can stand anywhere.
- **A line that isn't indented starts something:** `NAME = number`, `INSTRUMENT name:`,
  `PATTERN name:` or `SONG:`. The indented lines below it belong to it, and the amount of
  indentation doesn't matter.
- **The keywords are in upper case.** A name is letters, digits and `_`, and starts with a
  letter.
- **Everything is declared above the line that uses it.** There is exactly one `SONG:`, and
  it is the last block.
- **Numbers are whole and decimal.** An expression also takes hexadecimal, such as `0xFFFF`:
  bytebeat formulas use it for masks, and the AI writes it out of habit.
- **An expression is one line.** A long instrument uses named parts (section 3).
- **A line that fits none of this fails the check,** with its line number.

**There is one sample rate, 44100 Hz.** The score has no setting for it, so `t` counts the
same in every score.

**Note names** are a letter from `A` to `G`, an optional `#` or `b`, and the octave: `A4`
(440 Hz), `C#3`, `Bb3`.

**All names share one namespace.** A variable, an instrument and a pattern can't have the same
name, and a name can be declared only once. These are taken: `t`, `p`, `vel`, `dur`, `key`,
`sin`, `saw`, `square`, `tri`, `noise`, `decay`, `min`, `max`, `abs`, `BPM`, `STEPS`, and
anything shaped like a note name, so a variable can't be called `A4`. Upper and lower case
differ. The one exception is a named part of an instrument, which belongs to its instrument
(section 3).

---

## 3. Instruments

An instrument is one expression, with named parts above it if wanted. The addon evaluates it
once per sample for every note that sounds, and the result is the sample: -32768 to 32767,
with 0 as silence.

**The names an expression can use:**

| Name | What it is |
|---|---|
| `t` | The sample counter. It starts at 0 when the note starts and rises by 1 per sample, 44100 per second. It's for what depends on time, such as a fade |
| `p` | The position in the wave, in 65536ths of a cycle. It starts at 0 when the note starts and never folds back: after one cycle it is 65536, after two 131072. It's for what depends on pitch. The wave functions fold it back by themselves; an expression that uses `p` directly does it with `& 65535` |
| `vel` | The note's velocity, 0 to 255, fixed for the whole note. 255 is full |
| `dur` | The note's length in samples, fixed for the whole note. A tail isn't counted in it |
| `key` | The note's number, fixed for the whole note: 69 for A4 and one more for every semitone up, so C4 is 60. Transposing is already in it. It's for what changes with the pitch, such as a high note that dies away sooner |
| A declared variable | Its value at that moment (section 4) |
| A named part | The value of a line above it in the same instrument (see Named parts) |

**`p` is `t` scaled to the note's pitch, and the addon computes it.** It is
`t × step >> 16`, where `step` is `frequency × 2³² / 44100`, rounded. For A4 the step is
42,852,281. That keeps every note in tune to less than a thousandth of a cent, and the
product can't wrap around within a song.

**What an expression can contain:**
- **Operators:** `+ - * / % & | ^ ~ << >>`, the comparisons, `? :`, and brackets.
- **Whole numbers,** decimal or hexadecimal: `65535` and `0xFFFF` are the same.
- **These functions:**

| Function | What it gives |
|---|---|
| `sin(x)` | A sine, -32767 to 32767. `x` is a position in 65536ths of a cycle, and only its low 16 bits count |
| `saw(x)` | A saw, -32767 to 32767: it rises over the cycle and jumps back down at its end. `x` is as for `sin` |
| `square(x)` | A square wave: 32767 for the first half of the cycle and -32767 for the second. `x` is as for `sin` |
| `tri(x)` | A triangle, -32767 to 32767. It starts at 0 and rises first, like the sine, but in straight lines. `x` is as for `sin` |
| `noise(x)` | A value from -32768 to 32767 that looks random. The same `x` always gives the same value, so a song sounds the same every time. `noise(t)` changes with every sample; `noise(t >> 3)` holds each value for 8 samples and sounds darker |
| `decay(x, h)` | A level that halves every `h` samples: 65536 while `x` is 0 or less, 32768 at `x = h`, 16384 at `x = 2 * h`. Multiply by it, then shift by 16. An `h` of 0 or less gives 0, as dividing by zero does |
| `min(a, b)`, `max(a, b)` | The smaller and the larger of two values |
| `abs(x)` | `x` without its sign |

Nothing else is accepted. The addon reads the expression with its own small parser, and there
is no `eval`.

**`decay` is how most real instruments die away.** A string, a bell and a drum lose half of
their level in a fixed time, again and again: fast at first, then slowly. A straight line,
`(dur - t) / dur`, sounds the other way round: the note seems to hold, and then it drops.
`sin(p) * decay(t, 5000) >> 16` is a plucked note.

**`saw` and `square` are smoothed at their jump.** A wave that jumps holds tones above half
the sample rate. At 44100 Hz those fold back as tones that don't belong to the note, and a
high note sounds gritty. The addon rounds the jump off over the two samples next to it (the
method is called polyBLEP). It reads how fast `x` moves from one sample to the next, so
`saw(p * 2)` and `saw(p + (p >> 8))` work as well as `saw(p)`. Measured for the saw: the
energy that isn't on a harmonic of the note, against the energy that is.

| Note | `(p & 65535) - 32768` | `saw(p)` |
|---|---|---|
| A2 | -25 dB | -41 dB |
| A4 | -19 dB | -35 dB |
| C6 | -15 dB | -32 dB |
| C7 | -12 dB | -28 dB |

The raw form is still allowed, for the rough sound of classic bytebeat. `tri` has no jump, so
it isn't smoothed.

### Named parts

An instrument can have lines of `name = expression` above its last line. The last line is the
sample.

```text
INSTRUMENT bell:
    env = decay(t, 14000)
    mod = sin(p * 7 >> 1) * decay(t, 9000) >> 16
    sin(p + mod) * env * vel >> 24
```

- **A part can use the parts above it,** and everything else an expression can use.
- **A part's name belongs to its instrument.** Two instruments can both have an `env`. It
  can't be a name that is taken or declared in the score, and an event can't change it.
- **A part is computed once per sample,** however often the lines below it use it.
- **A part is a value, as if it had brackets around it.** That keeps a long instrument
  readable, and it avoids the two precedence traps below.

### The arithmetic

These rules are the addon's own. "As in C" isn't enough: C leaves some of these cases
undefined, and array libraries round differently from C.
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
- **A result outside -32768 to 32767 is clipped** to that range, and `play` names the
  instrument (section 1). Classic bytebeat keeps the low bits instead, which turns a wave
  that is slightly too loud into noise. An expression that wants that wrapping does it
  itself, with `& 65535`.

### Recipes

Those marked "heard" were in a throwaway render that the user listened to on 2026-10-02. The
drums were liked. Nothing was said about the others, and nobody has heard the unmarked ones.

| Sound | Expression | |
|---|---|---|
| Sine | `sin(p)` | |
| Sine, one octave lower | `sin(p >> 1)` | |
| Sine, one octave higher | `sin(p << 1)` | |
| Saw | `saw(p)` | heard |
| Raw saw, as in classic bytebeat | `(p & 65535) - 32768` | heard |
| Square, triangle | `square(p)`, `tri(p)` | |
| Saw and sine, half each | `(saw(p) + sin(p)) >> 1` | |
| Three saws, a little out of tune with each other | `(saw(p) + saw(p + (p >> 8)) + saw(p - (p >> 8))) / 3` | |
| Sine with velocity | `sin(p) * vel >> 8` | |
| Sine that fades out in a straight line over the note's length | `sin(p) * (dur - t) / dur` | heard |
| Sine that fades out in a straight line by itself, in half a second | `sin(p) * max(22050 - t, 0) / 22050` | |
| Plucked sine: it halves every 5000 samples | `sin(p) * decay(t, 5000) * vel >> 24` | heard |
| The same, dying away sooner on high notes | `sin(p) * decay(t, 3000 + (96 - key) * 60) * vel >> 24` | |
| Sine with vibrato that sets in over half a second | `sin(p + (sin(t * 8) * min(t, 22050) / 22050 >> 2)) * vel >> 8` | heard |
| Bell | `sin(p + (sin(p * 7 >> 1) * decay(t, 9000) >> 16)) * decay(t, 14000) * vel >> 24` | heard |
| Electric piano | `sin(p + (sin(p) * decay(t, 3000 + (96 - key) * 60) * vel >> 25)) * decay(t, 16000) * vel >> 24` | heard |
| Kick, played at A1 | `sin(p + (65536 - decay(t, 900)) * 5) * decay(t, 5000) * vel >> 24` | heard |
| Snare, played at G3 | `(noise(t) * decay(t, 2200) + sin(p + (65536 - decay(t, 500)) * 2) * decay(t, 1500)) * vel >> 25` | heard |
| Hi-hat, at any note | `(noise(t) - noise(t - 1)) * decay(t, 600) * vel >> 25` | heard |
| Noise that dies away | `noise(t) * decay(t, 2200) >> 16` | |
| Pad with a tail | See The tail | heard |

- **Loudness is a multiplication.** Silence is 0, so `x * vel >> 8` scales a wave and keeps it
  centred.
- **Velocity is 0 to 255, not MIDI's 0 to 127.** It matches `>> 8` and the variables. A
  velocity of 75 is about 29% of full.
- **`vel` is only a number.** An instrument can use it for loudness, or for something else,
  such as the balance between the saw and the sine. The electric piano uses it twice: a
  harder note is louder and brighter.
- **A quiet voice keeps its detail.** A pad at velocity 60 still has about 15,000 levels. With
  8-bit samples it would have 60.
- **A classic 8-bit bytebeat formula needs wrapping.** Put `t * 80 / 441` where the formula
  has `t`, because it was written for 8000 Hz, and turn its result into a 16-bit sample:
  `((formula & 255) - 128) << 8`. It then sounds as it did, with 8-bit detail.
- **A difference makes noise brighter.** `noise(t) - noise(t - 1)` takes the low part out of
  the noise, which is the hi-hat. An average, `(noise(t) + noise(t - 1)) >> 1`, makes it
  darker.
- **The drums are the first recipes somebody has heard.** They are the third score of
  section 5.

### What adding to `p` does

`p` is a position in the wave, so `sin(p + x)` is the same sine pushed along by `x`, and
65536 is one whole cycle. What `x` does over time decides what is heard:

| `x` is | What is heard | Where |
|---|---|---|
| A wave at the note's own speed | Another tone. The wider `x` swings, the brighter | `sin(p + (sin(p) >> 1))` |
| The same, shrinking with `decay` | A tone that starts bright and turns soft, as a struck string or bell does | The electric piano, the bell |
| A wave at a speed that isn't a whole multiple, such as `p * 7 >> 1` | Overtones that don't fit the note, as in metal | The bell |
| A slow wave | Vibrato | `sin(t * 8)` swings 5.4 times a second, and `>> 2` makes it about 5 Hz to each side |
| A number that grows and then stays | A pitch that starts high and falls to the note | The kick, the snare |
| `p >> 8` | The same note, 6.7 cents higher. Two or three such waves together sound wide | The three saws |

- **The kick's pitch falls the way its level does.** `(65536 - decay(t, h)) * n` starts the
  note about `n × 30,600 / h` Hz too high and halves that gap every `h` samples. With
  `h = 900` and `n = 5`, a kick played at A1 (55 Hz) starts at 223 Hz, is at 139 Hz after
  20 ms and at 62 Hz after 100 ms.
- **Vibrato made this way is the same number of Hz at every pitch,** so it's wider on a low
  note than on a high one.
- **It works with every wave,** not only the sine: `saw(p + x)`.

### The edges of a note

A wave that starts or stops anywhere but at 0 makes a click. A raw saw starts at -32768.

- **The addon fades every note in and out:** in over 90 samples and out over 220, which is
  2 ms and 5 ms. It does that after the expression, so no instrument has to. A note that is
  shorter than both together gets both made shorter in the same proportion. The render of
  2026-10-02 used these lengths, and the kick kept its attack.
- **`dur` is for a shape the instrument wants itself.** `dur - t` is the number of samples
  left, so `sin(p) * (dur - t) / dur` is a note that dies away like a plucked string.
- **Multiply first, then divide.** These are whole numbers: `(dur - t) / dur` on its own is 1
  for the first sample and 0 for all the others, so `sin(p) * ((dur - t) / dur)` is silent.
- **A note ends at its duration,** unless its instrument has a tail.

### The tail

A piano string and a pad go on sounding after the key is let go. An instrument that wants
that says how long, with a number after its name:

```text
INSTRUMENT pad 35280:
    env = min(t, 4000) * decay(t - dur, 6000) >> 12
    (saw(p) + saw(p + (p >> 8)) + saw(p - (p >> 8))) * env * vel >> 26
```

- **The number is the tail, in samples.** 35280 is 0.8 seconds. A note sounds for its
  duration, and then for the tail. It's in samples, like `t` and `dur`, because it belongs to
  the sound and shouldn't change with the tempo.
- **`dur` stays the written length,** so `t - dur` counts the samples since the note was let
  go. `decay(t - dur, 6000)` is 65536 while the note is held, and halves every 6000 samples
  after that.
- **The expression has to bring the sound down itself.** Without something like that
  `decay`, a tail is only a longer note. In this pad the level is at 1.7% when the tail ends.
  The addon's short fade comes at the very end of the tail.
- **A tail sounds over the notes that follow.** Every note is its own voice (section 4).
- **An instrument without the number has no tail.**

This pad was in the render of 2026-10-02, as two chords.

---

## 4. Events, patterns and the song

### Events

Everything that happens is an event, `(start, duration, value, target, velocity)`:

| Field | Meaning |
|---|---|
| `start` | When it happens, in steps. A `+` means where the line above ended |
| `duration` | How long it lasts, in steps |
| `value` | A note name (`A4`, `C#3`, `Bb3`) when the target is an instrument, or several with spaces between them for a chord; a number when the target is a variable |
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
| `(0, 32, C3 E3 G3, pad, 60)` | A chord: three notes with the same start, duration and velocity |
| `(+, 8, G4, lead)` | A note that starts where the line above ended |
| `(+4, 8, G4, lead)` | A note that starts 4 steps after that: a rest |
| `(8, 0, 128, VOL)` | `VOL` jumps to 128 at step 8 |
| `(8, 8, 0, VOL)` | `VOL` glides from its current value to 0 between steps 8 and 16 |

**A chord is several notes in one event.** Each note is its own voice. It's for notes only: a
change to a variable has one value, and more than one fails the check.

**`+` saves the adding up.** A melody is one note after another. With numbers only, the AI has
to add every duration to the start before it, and a wrong sum is a wrong rhythm that no check
can find.
- **`+` is the end of the line directly above:** its start plus its duration. When that line
  places a pattern, it is the start plus the pattern's length, times the repeats.
- **`+4` is 4 steps after that,** which is how a rest is written.
- **A number starts a new count.** The lines below it can go on with `+`.
- **It fails the check where there is nothing to count from:** on the first line of a pattern
  or of the song, and after a line that places a pattern without a length.

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
- **`start` can be `+` in both kinds,** in the song and in a pattern.
- **Repeating needs the pattern's length.** A repeat count on a pattern without a length
  fails the check.
- **Patterns placed at the same step play together.** A bass line, the chords and a melody can
  each be written once and arranged separately.
- **Transposing moves the notes only.** Changes to variables in the pattern stay as written.
  When a transposed pattern places another pattern, the two numbers add up.
- **The order of the lines doesn't matter.** The start times do. The one exception is a `+`,
  which counts from the line above it.
- **The song ends at the last step that anything reaches:** the end of the last event, or of
  the last placed pattern's length, whichever is later. A bar of drums whose last note ends
  early still ends on the bar.
  - A song that plays once goes on until the last tail is over. `seconds` counts that, and
    `finished` comes after it.
  - A song that loops starts again at that step. A tail that is still sounding is mixed into
    the start of the next round, so the rhythm doesn't break.

---

## 5. Three complete scores

All three are written by hand. Nothing can play a score file yet. On 2026-10-02 a throwaway
script rendered their notes, in the arithmetic of section 3 but without a parser, and the
peaks below come from it. The user has heard all three: the drum beat was liked, and the
first two "sound good".

### Chords and a melody

Four bars: C, G, A minor and F on a soft sine, with a melody on top.

```text
BPM = 100

INSTRUMENT pad:
    sin(p) * vel >> 8

INSTRUMENT lead:
    (saw(p) + sin(p)) * vel >> 9

# C major, held for a bar
PATTERN major 32:
    (0, 32, C3 E3 G3, pad, 60)

# A minor, held for a bar
PATTERN minor 32:
    (0, 32, A2 C3 E3, pad, 60)

# root, fifth, octave: it fits a major and a minor chord
PATTERN riff 32:
    (0,  8, C4, lead, 140)
    (+,  8, G4, lead, 140)
    (+, 16, C5, lead, 140)

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
- **A chord is one event with three notes.** Each note is its own voice on `pad`, held for
  the whole bar.
- **Five events are written and 24 notes are played.** `major` serves three chords: moved
  down five semitones it is G major, and moved down seven it is F major. `riff` serves all
  four bars.
- **The riff counts with `+`.** Each note starts where the one above it ended, at steps 0, 8
  and 16.
- **The lead is half saw and half sine.** `>> 9` is the halving and the velocity's `>> 8` in
  one shift.
- **The velocities are chosen to fit.** Four voices sound at once and are added together.
  Three pads at 60 and the lead at 140 can reach 98% of full scale at most. In the render the
  peak was 95%, so nothing is turned down. With higher velocities the piece would still play,
  only turned down as a whole.

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
    (saw(p) * BRIGHT + sin(p) * (255 - BRIGHT)) * vel * VOL >> 24

# C major, held for a bar
PATTERN major 32:
    (0, 32, C3 E3 G3, pad, 40)

# A minor, held for a bar
PATTERN minor 32:
    (0, 32, A2 C3 E3, pad, 40)

PATTERN riff 32:
    # the tone opens up over three beats and closes again on the fourth
    (0, 24, 255, BRIGHT)
    (+,  8,   0, BRIGHT)
    (0,  8, C4, lead, 130)
    (+,  8, G4, lead, 130)
    (+, 16, C5, lead, 130)

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
  half saw and half sine, so the pads are at 40 and the lead at 130. Together they can reach
  97% of full scale at most. In the render the peak was 94%.
- **A number starts a new count in the riff.** The two `BRIGHT` events are one count, and the
  `0` of the first note starts the next.

### A drum beat

The beat the user heard and liked on 2026-10-02. It was two bars there, and it is four here.

```text
BPM = 120

INSTRUMENT kick:
    sin(p + (65536 - decay(t, 900)) * 5) * decay(t, 5000) * vel >> 24

INSTRUMENT snare:
    body = sin(p + (65536 - decay(t, 500)) * 2) * decay(t, 1500)
    hiss = noise(t) * decay(t, 2200)
    (body + hiss) * vel >> 25

INSTRUMENT hat:
    (noise(t) - noise(t - 1)) * decay(t, 600) * vel >> 25

# one bar: the kick on beats 1 and 3, the snare on 2 and 4, a hat on every other eighth note
PATTERN beat 32:
    (0,  4, A1, kick)
    (4,  4, C6, hat, 150)
    (8,  4, G3, snare, 230)
    (8,  4, C6, hat, 90)
    (12, 4, C6, hat, 150)
    (16, 4, A1, kick)
    (20, 4, C6, hat, 150)
    (24, 4, G3, snare, 230)
    (24, 4, C6, hat, 90)
    (28, 4, C6, hat, 150)

SONG:
    (0, beat, 0, 4)
```

- **One bar is written and four are played:** 10 events, 40 notes, 8 seconds at 120 BPM.
- **The kick is a sine whose pitch falls.** It is played at A1, 55 Hz. It starts at 223 Hz and
  is close to the note after a tenth of a second (section 3).
- **The snare has two named parts:** a short tone that falls, and noise that dies away a
  little more slowly.
- **The hat doesn't use its note.** Its expression has no `p`, so any note will do. An event
  on an instrument still has to name one.
- **The velocities make the rhythm.** The hats between the beats are at 150, and the ones
  that share a step with the snare are at 90.
- **Every sound dies away by itself, with `decay`.** The kick is the slowest: when its 4 steps
  end, it is still at about a fifth of its level, and the addon's short fade cuts it there. A
  longer duration lets it ring.
- **The peak is 98% of full scale,** and that is the kick alone. Nothing else sounds on its
  step.

---

## 6. Playing, and the limits

**How the sound is made:**
- **In a child process,** like the window of [addons/window.py](../addons/window.py). numpy
  and pygame are only imported there. Hallux itself only checks that they are installed, so
  it doesn't slow the start. The child can be ended when a render takes too long, and nothing
  it prints can land on the machine's screen.
- **The child plays the samples with pygame's mixer.** pygame is a Python library that pip
  installs into the venv. Its package brings SDL and its sound drivers along, so nothing has
  to be installed on the system, and the window addon uses it already. The child opens the
  mixer at 44100 Hz, 16-bit, one channel, and accepts no other format (`allowedchanges=0`).
  It makes one sound of the rendered samples and plays it.
- **The mixer passes the samples on unchanged.** Tested on 2026-10-02 with SDL's "disk"
  driver, which writes what would go to the sound card into a file: what came out was what
  went in, bit for bit.
- **The child asks the mixer whether the song is still playing,** a few times a second. When
  it isn't, the child reports `finished`.
- **A song that loops is one sound, played again and again,** which the mixer does without a
  gap. When tails ring past the end it is two sounds: the first round, and the later rounds
  with those tails mixed into their start. The second is queued behind the first, and then
  behind itself. In the same test a queued sound followed the one before it without a gap of
  a single sample.
- **The addon reads the score, not the child.** It reads the file through Hallux's handle and
  passes the text on. The child never opens a file of the machine.
- **The whole song is rendered first, then played.** That is what lets `play` report the
  length and the peak, and turn down a mix that is too loud. Five minutes are 13.2 million
  samples, about 26 MB.
- **With array operations, in blocks of about 16,000 samples.** Not one sample at a time in
  Python, and not a whole note at once either. Every step of an expression makes an array of
  8 bytes per sample. For a note of five minutes that is 106 MB, and an expression has a
  dozen steps. Blocks keep the memory flat, and they were three times as fast (section 8).
- **A variable is kept as its list of changes,** not as one array for the whole song. The
  addon works out its values for the block it is rendering.
- **A song that loops starts again from the top,** with every variable back at its declared
  value. A tail that is still sounding is mixed into the start of the next round
  (section 4).
- **`stop()` ends the sound at once.** The child stops the mixer's channel, and what hasn't
  been played yet is thrown away. On the hard exit the child goes away with Hallux.

**The limits.** The AI writes every part of a score, possibly led by text it read in a file,
so the addon treats all of it as untrusted. The numbers are to be chosen when it's built.

| What | Limited to |
|---|---|
| Song length | A maximum number of seconds, short enough that rendering fits well inside the 10 seconds Hallux gives a call |
| File size | A maximum number of bytes |
| Events, once the patterns are unfolded | A maximum number. It also bounds repeats and patterns inside patterns |
| Patterns inside patterns | A maximum depth |
| An expression | A maximum length and nesting depth |
| An instrument | A maximum number of named parts |
| A tail | A maximum number of samples |
| Whole numbers | What fits in 64 bits |
| Notes | C0 to B9, after transposing |
| Names | Only the names and functions of section 3, the declared variables, and an instrument's own named parts |
| Voices at once | A maximum number |
| Problems reported by one `play` | A maximum number, so the result stays small |

---

## 7. What it can't do

- **Effects that need memory.** A filter, an echo and a reverb depend on earlier output, and an
  expression only sees the current `t`. Those would have to be features of the addon itself.
  An echo would be cheap to add later, because the whole song is rendered before it plays. A
  filter wouldn't be: numpy has nothing that feeds its own output back, sample by sample.
- **A slide from one note to the next.** An instrument can move its own pitch by adding to
  `p`, which gives vibrato and the falling pitch of a kick (section 3). But every note has one
  pitch, so nothing slides from one written note into the next. Because the addon computes
  `p`, that can be added later without changing the scores that exist.
- **Stereo.** The sound has one channel. A place between left and right for each instrument
  would be a feature of the addon, and cheap to add later.
- **Listen.** The AI writes music it can't hear. `play` gives it numbers, the length and the
  peak, and the manual should carry recipes that are known to sound right. So far those are
  the drums, and the pad and the lead of the first two scores of section 5.

---

## 8. Costs and risks

- **Writing the score is the slow part.** The AI writes it one character at a time, and the
  user waits. Patterns and repeats keep it short: what repeats is written once. Playing a
  score again costs one call.
- **Rendering is fast, as far as it was measured.** On 2026-10-02, on this computer (an
  i5-11400H, one core), with numpy 2.5:
  - The heaviest expression of this document then, the `lead` of the second score with the
    raw saw and both variables gliding, took 0.015 seconds for one minute of one voice in
    blocks of 16,384 samples, and 0.044 seconds as one array.
  - Five minutes with eight voices sounding all the time would then take about 0.6 seconds.
  - `saw(p)` costs 4.4 ns per sample, and the raw form 0.9 ns. With `saw` in that `lead`, the
    same five minutes come to about 1 second by these numbers.
  - Only the expression was timed. Reading the score, mixing, the fades and handing the
    samples over weren't, so the limit on a song's length still has to come from a
    measurement of the whole thing. The sound starts only after the render, and the call has
    to finish within Hallux's 10 seconds.
- **pygame's mixer makes a real sound on this computer.** On 2026-10-02 the user ran a
  throwaway script that played the drum beat of section 5 through it, at 44100 Hz, 16-bit,
  one channel, with SDL's PulseAudio driver and WSLg's sound server. The user heard it. I
  can't run that test myself: my sandbox doesn't let the socket to the sound server through.
- **It should work wherever pygame has a package:** Linux, WSL, macOS and Windows. It has
  been tried on this computer only, under WSL.
- **It needs two Python libraries, and nothing from the system:** numpy for the arrays and
  pygame for the sound.
  - Both are an optional install, `pip install -e ".[music]"`. Only addons need them, so
    Hallux itself doesn't require them.
  - pygame is in this venv already, for the window addon. numpy isn't yet.
  - Without either one the loader skips the addon and names what is missing, like any other
    addon that fails a check.
- **pygame is big for what it does here:** about 37 MB, to play one buffer. Where the window
  addon is installed too, it costs nothing more.
- **Testing stays cheap.** The parser and the sample maths need no sound and no model call: an
  expression and a score go in, and an array of numbers comes out, which a test can compare.
  The child's output can be tested without a sound card too, with SDL's disk driver.

---

## Decisions

**Settled on 2026-10-01.** The first two are the user's requirements; the rest were my
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
| How the sound gets out | The child hands the samples to PulseAudio itself, through `libpulse-simple` and `ctypes`. Replaced on 2026-10-02: see the last table | WSLg's sound server is PulseAudio, so nothing is in between, and no Python sound package is needed. Two others were looked at. pygame's mixer is a 37 MB game library for playing one buffer. The `sounddevice` package reaches the same server through three more layers, and printed 94 lines of warnings here while starting |

**Settled on 2026-10-02.** All were my recommendations, accepted together after the user had
listened to the render.

| Question | Decision | Why |
|---|---|---|
| How a sound dies away | `decay(x, h)`, a level that halves every `h` samples | Real instruments die away like that, and the drums are built on it. Before, a straight line was the only envelope. It also gives a pitch that falls, for a kick |
| Waves | `saw(x)`, `square(x)` and `tri(x)`, smoothed at the jump. The raw form stays allowed | A raw saw at 44100 Hz folds tones back into a high note: -15 dB at C6, against -32 dB smoothed. `saw(p)` is also shorter to write, and has no precedence trap |
| Long instruments | Named parts: lines of `name = expression` above the last line | A long instrument stays readable, and a part that is used twice is written and computed once |
| A sound after the end of a note | A tail, declared by the instrument. The first revision said a note stops at its duration | A pad or a plucked string otherwise stops as if cut off |
| The note's number | `key` | A high note can die away sooner, or be softer |
| Small functions | `min`, `max` and `abs` | Shorter and clearer than `? :` |
| Chords | Several notes in one event | Three lines become one |
| Start times | `+` for the end of the line above | The AI doesn't have to add up, and a wrong sum is a mistake that no check can find |
| Vibrato | Possible already, by adding to `p`. The first revision said it wasn't | `sin(p + x)` with a slow `x` is vibrato. Only a slide between two notes is missing |
| How the render works | In blocks of about 16,000 samples, with each variable kept as its list of changes | Three times as fast as whole arrays, and the memory stays flat |
| Echo, stereo, a filter | Not now | They are outside the expression. Echo and stereo are cheap to add later. A filter isn't |

**The open questions, answered on 2026-10-02.** All ten were settled as I had recommended.
The first four had been open since the first version. The other six were details that I had
settled while writing, and nobody had confirmed them until then.

| Question | Decision | Why |
|---|---|---|
| The exact syntax of the file | The syntax of sections 2 to 5, with the rules in section 2. One `SONG:`, as the last block. Hexadecimal numbers in expressions | The sketch had become the syntax: three scores, the recipes and the manual depend on it. Left until the parser is written, the parser would have decided the details by accident |
| A second counter, for the whole song | No, only `t` | It would be used for a sweep or a fade across many notes, and a variable with a glide does that already, written in steps and not in samples. It can be added when a score needs it |
| `play` while a song is playing | The new song replaces the old one, which sends no `finished` | It's what a player does when another file is opened. Refusing would cost a `stop` call first. Playing both would need two streams and a peak check over their sum |
| Where the two libraries come from | numpy as an optional install, `libpulse-simple` from the system. Without either one the loader skips the addon and says what is missing. Replaced the same day: see the last table | Only this addon needs numpy. `libpulse-simple` is there wherever PulseAudio is |
| A voice whose expression gives more than 16 bits | Clipped, and `play` names the instrument in `clipped` | Wrapping turns a wave that is slightly too loud into noise; clipping only flattens its top. The AI can't hear either, so the result has to say it |
| `note` as a name | Dropped. The first version had it, as the step of the wave per sample | `p` does its work, and two names for pitch in different units would be confusing. `key` is something else: the number of the note |
| The fades at the edges of a note | 90 samples in and 220 out, shorter in proportion for a very short note | The render of 2026-10-02 used them, and the drums sounded right. They change only if somebody hears a click or a soft attack |
| How the tail is written | A number after the instrument's name, in samples | Samples are the unit of `t` and `dur`, so an instrument counts in one unit. A tail in steps would change with the tempo |
| What `+` counts from | The end of the line directly above, whatever that line is. `+4` is a rest of 4 steps. On the first line of a pattern or of the song it fails the check | One rule without exceptions is easier for the AI than one for each kind of line. A `+` with nothing above it is a mistake, and is reported, not read as 0 |
| Where a song ends | At the last step that anything reaches. Played once, the tails ring out. In a loop they are mixed into the next round | A bar of drums has to loop on the bar. A loop that waited for a tail would break the rhythm |

**Changed later on 2026-10-02.** The requirement is the user's: "a python lib that can play
music and can be installed in venv". Which library was my choice. The user then heard it play
on this computer and confirmed it.

| Question | Decision | Why |
|---|---|---|
| How the sound gets out | pygame's mixer, in the child. Until then it was `libpulse-simple` through `ctypes` | Required: a Python library that pip installs into the venv. On 2026-10-01 pygame was turned down as not direct enough; now the way doesn't matter, as long as the sound can be heard. pygame's package brings its own sound drivers, so nothing comes from the system, and the window addon needs it anyway. In a test its mixer passed the samples on unchanged, and a queued sound followed without a gap. `sounddevice` was looked at again: on Linux its package has no PortAudio inside, so it would need a system library |
| Where the two libraries come from | numpy and pygame, both from pip, as the optional install `.[music]` | Nothing has to come from the system |

## Still to find out

No question about the design is open. One thing needs a measurement, not a decision:

- **The numbers of the limits** in section 6. They have to come from timing a whole render,
  not only the expression (section 8).

The handle through which `play` reads a file of the machine is built. It belongs to the
addon system, not to this design (step 7 of [plans/addons-plan.md](plans/addons-plan.md)).

## Order of work

**The step-by-step plan is in [plans/addon-music/](plans/addon-music/README.md),** written on
2026-10-02: an overview, and one file for each of its ten steps. The list below is the
outline that the plan grew from, and the plan is what counts where the two differ.

The handle for the machine's files (step 7 of [plans/addons-plan.md](plans/addons-plan.md))
has to exist before step 5. It is step 1 of the plan, and it is built.

1. Check that the child's way of making sound works on this computer: a real sound through
   pygame's mixer at 44100 Hz and 16 bits. Done on 2026-10-02: the user heard the drum beat
   through it (section 8).
2. A throwaway script that renders the scores of section 5 to a WAV file. It's for listening
   to the instruments and for timing the render. Partly done on 2026-10-02, in a scratch
   folder outside the repository: the expressions were timed, and the instruments and the
   three scores were rendered to WAV files. The user listened to all of them. What's left is
   timing a whole render.
3. The expression parser with its functions and named parts, its arithmetic and its limits,
   with tests against known values.
4. The score reader, unfolding the patterns and turning a score into samples, with tests that
   compare arrays.
5. The child process, the sound output, `play`, `stop`, looping and the `finished` event.
6. The manual that `prompt()` returns.
7. A `--script` run that checks the machine calls `play` instead of imagining it.
