# Step 2: `check`

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 4

**Needs:** nothing. **Changes:** `addons/music_engine/__main__.py`, `addons/music.py`,
`tests/test_music_child.py`, `tests/test_addon_music.py`, `tests/test_music_manual.py`.

The composer needs to know whether its score works and how it sounds in numbers, without
making a sound. `check` renders a score and returns what `play` returns. It is a function of
the music addon like the others, so the main agent gets it too: for a score the user edited
in nano. This step has nothing of agents in it.

## Build

**A second way to start the child.** Today the child opens pygame's mixer before it says
anything (`addons/music_engine/__main__.py:42`). Started for a check, it:

- doesn't load pygame, and opens no sound card. Not opening the mixer isn't enough: the
  child loads its player module with the others (`addons/music_engine/__main__.py:39`), and
  that module loads pygame at once (`addons/music_engine/player.py:14`). A check child
  doesn't load the player at all. The render needs nothing of it;
- reads one score from its input, renders it, writes one line of JSON and ends;
- answers what `play` answers: `{"ok": true, "seconds": 8.0, "peak": 98}`, with
  `turned_down_to` and `clipped` when they apply, or `{"error": …}` with every problem and
  its line.

**`check(disk, path)`** in `addons/music.py`:

1. It reads the file through the disk handle, as `play` does, with the same limit of 64 KB.
2. It starts a child for this one render.
3. It waits up to 8 seconds, from the start of the child to its answer.
4. It returns the answer, or raises `MusicError` with the child's error.

- **It never touches the child that plays.** It doesn't take that child's lock, so a
  `check` doesn't wait for a `play` and doesn't replace a song.
- **`stop` doesn't know about it.** A check child ends by itself.
- **After 8 seconds** the child is ended, and `check` fails with the words `play` has: `the
  song took too long to render`. Hallux would cut the call at 10 seconds with a bare
  `timed out`.
- **Every child is started with colours off,** the playing one too. With `FORCE_COLOR` set
  in the user's shell, Python colours a child's traceback, and the addon's "it crashed (…)"
  message carries the escape codes to the AI. Two tests fail in such a shell today, one of
  them the music addon's. (The window addon has the same flaw; it isn't this step's.)
- **`EXPOSED`** becomes `[play, stop, check]`.
- **The manual** gets a line on `check`. The manual is 7987 characters and its limit is
  8000, so the limit goes to 8500 in this step (`tests/test_music_manual.py:23`).

**To measure in this step:** how long a check child takes from its start to the answer for
an empty song. By the music plan's measurement numpy loads in 0.25 seconds on this
computer. If the start takes much more than that, the 8 seconds leave too little for long
songs. The number is written into this file when the step is built, and it answers the
design's "Still to find out".

## Tests

In `tests/test_music_child.py`:

- the child started for a check answers for a good score what the playing child answers;
- a score with mistakes: the answer holds every problem, as for `play`;
- **no sound device at all:** with SDL pointed at a driver that doesn't exist, the check
  still answers. The playing child fails there;
- pygame isn't loaded in a check child: checked in the child itself;
- a child that crashes, with `FORCE_COLOR` set: the message has no escape code in it.

In `tests/test_addon_music.py`:

- the tool's schema has `path` and no `disk`;
- `check` of the drum beat file returns the numbers `play` returns for it, and no sound
  file is written by the disk driver;
- a missing file, a path outside the root, a file that is too big: as for `play`;
- while a long song plays, `check` returns, and the song plays on;
- `stop` during a `check`: the check still answers;
- a stand-in child that stays silent: `took too long` after the limit, and the child is
  gone.

## Done when

`check` of the design's drum beat returns `{"ok": true, "seconds": 8.0, "peak": 98}` on a
computer with the sound server switched off.

## As built

Built on 2026-10-05, on the branch `addon-agents`. 19 new tests, 1099 in all. Three old
tests changed, all in this step's files: the two that list the addon's functions, and the
manual's limit. Decided while building:

- **The second way to start the child is one word:** `python -m music_engine check`.
- **The score comes in as one message,** `{"text": "..."}`, like every message to the child
  that plays. JSON is plain ASCII on the pipe, so no encoding can garble a score. The answer
  is one line without an `id`: there is one question.
- **A check child always ends well, with one line.** A score with mistakes is an answer. So
  is a bug in the render: `addon bug: …`, with the traceback on its error output, as from
  the child that plays. So is an input that is no message: `addon bug: check takes a text`.
- **For the addon, a child that ends badly has no answer,** whatever it printed first:
  `the check stopped: it crashed (…)`. One that ends well without an answer:
  `the check stopped`.
- **`CHECK_SECONDS`** is a number of its own, 8.0, beside `RENDER_SECONDS`. After it the
  child is ended, and the words are `play`'s.
- **Colours off is three things** in a child's environment: `FORCE_COLOR` is taken out, and
  `NO_COLOR=1` and `PYTHON_COLORS=0` are set. Both children are started that way.
- **The test of the colours is with the addon's tests,** not with the child's as this file
  has it above. The message is made by the addon, and the addon is what starts a child with
  colours off. With `FORCE_COLOR` set in the shell, one test fails now where two did: the
  window addon's.
- **`play` and `check` read the file through one function,** so the limit of 64 KB and its
  words are the same.
- **The manual's line** is two lines, 145 characters. The manual is 8132 characters, and
  368 are left under the new limit for step 13.

**`check` takes `loop`, as `play` does:** `check(path, loop)`. This file has it above as
`check(disk, path)`. For most songs it makes no difference. A loop whose tails ring past
its end is rendered with those tails mixed into its later rounds, and `play` then reports
one round's length and a higher peak. Tried: a note of 0.1 seconds with a ringing tail
gives `0.2 s, peak 78` once, and `0.1 s, peak 148, turned down to 67` as a loop. Without
`loop`, a composer that checks a song meant to loop would see the wrong peak. It was added
on 2026-10-05, after the step was built and committed: I recommended it, and the user
answered "okay". Two more tests hold it, 1101 in all.

**Measured on 2026-10-05,** on this computer, ten runs each, from the start of the child to
its answer:

| | Median | Slowest |
|---|---|---|
| Python alone | 0.02 s | 0.04 s |
| Python and numpy | 0.14 s | 0.17 s |
| A check of the smallest song | 0.15 s | 0.16 s |
| A check of the design's drum beat, 8 seconds of sound | 0.17 s | 0.21 s |

One run of the heaviest song in the child's tests, 64 voices for 30 seconds: 1.47 s.

So the start costs about 0.15 of the 8 seconds, nearly all of it numpy, and less than the
0.25 the music plan measured. That answers the design's "How long a check child takes to
start".

**The "Done when" holds:** with SDL pointed at a sound driver that doesn't exist, `check`
of the drum beat returns `{"ok": true, "seconds": 8.0, "peak": 98}`, and `play` fails there.

**Not tried:** the main agent using `check`. It has the tool and the manual's line from
this step on; whether it reaches for it shows only with a real model.
