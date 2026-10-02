# Plan: the music addon

**Status:** all ten steps are done. A machine has the music addon: `play` and `stop`, the
`finished` event, and a manual of 7987 characters from which the AI writes scores. In the
live run a real model composed seven songs, and each played on the first try. Reading the
manual costs about $0.045 once per boot. What the live run didn't cover is at the end of
[10-live-run.md](10-live-run.md). The design it follows is [addon-music.md](../../addon-music.md), in
which no question is open. Two checks from the design's order of work are done: a real sound
came out of pygame's mixer on this computer, and the three scores of the design were rendered
by a throwaway script and heard.

**How this plan is laid out.** This file holds what the steps share: how the parts fit, the
decisions, where the code goes, and the status. Every step has a file of its own in this
folder. A step is built and merged by itself, so whoever builds one reads this file and that
step's file. The other three plans are one file each. This one would be about three times
their length, which is why it is a folder.

## In short

1. **The disk handle:** an addon function can read a file of the machine through the path
   jail. It's the step the addon system still lacks.
2. **Reading an expression:** the text of an instrument becomes a checked tree.
3. **Computing an expression:** the tree becomes samples, with the design's own arithmetic.
4. **Reading a score:** the file becomes instruments, patterns and a song, or a list of
   problems with their lines.
5. **Unfolding a score:** patterns, chords and `+` become a flat list of notes and changes,
   timed in samples.
6. **Rendering:** the notes become one mixed song, with its length and its peak. This step
   also times a whole render and sets the limits.
7. **The child:** a process that takes a score, renders it and plays it through pygame's
   mixer.
8. **The addon:** `addons/music.py`, with `play` and `stop` and the `finished` event.
9. **The manual:** what the AI reads before it writes its first score.
10. **The live run,** and the documentation.

Until step 8 a running machine doesn't change, apart from step 1, which changes the addon
system and no machine's behavior.

---

## How the parts fit

```text
+--------------------------------+                   +-------------------------------+
| Hallux process                 |   JSON, one line  | child process                 |
|                                |   per message     | python -m music_engine        |
|  addons/music.py, imported:    |  ---- stdin --->  |                               |
|    play()  stop()              |                   |  reads and checks the score   |
|    reads the score file        |  <--- stdout ---  |  renders it with numpy        |
|    through the disk handle     |                   |  plays it with pygame's mixer |
+--------------------------------+                   +-------------------------------+
```

**One `play`, from start to end:**

1. The AI calls `play("/home/user/beat.score")`.
2. The addon reads the file through the disk handle (step 1) and sends its text to the child.
3. The child reads and checks the text (steps 2 and 4). If it finds problems, it answers with
   all of them, and nothing else happens.
4. The child unfolds the song (step 5), renders it (steps 3 and 6) and starts the sound
   (step 7).
5. The child answers with what it measured, and the addon returns that to the AI (step 8).
6. When the song ends by itself, the child says so, and the addon reports `finished`.

**The modules of the child,** each with one job:

| Module | Job | Needs numpy |
|---|---|---|
| `expr.py` | Text of an expression to a tree | No |
| `compute.py` | A tree, and the values of its names, to samples | Yes |
| `score.py` | Text of a score to instruments, patterns and the song, or problems | No |
| `song.py` | Those to a flat list of notes and changes, timed in samples | No |
| `render.py` | The notes to the mixed song | Yes |
| `player.py` | The mixed song to the sound card | pygame |
| `limits.py` | Every limit of section 6 of the design, as a named number | No |
| `__main__.py` | The child: the messages, and the loop | |

---

## Decisions this plan takes

**From the design.** The plan follows all three of its decision tables.

**What the design leaves open, decided here.** I proposed these thirteen, and they were
confirmed on 2026-10-02:

| Topic | Decision | Why |
|---|---|---|
| Where the code lives | `addons/music.py` is the addon, one file as the rule says. The child is a package beside it, `addons/music_engine/`. The loader only looks at `.py` files directly in `addons/`, so it never sees the package | The child is about 1200 lines: a parser, sample maths and a player. In one file with the addon it would be three times the biggest file in the repo, and its parts couldn't be tested by themselves |
| Who checks the score | The child. The addon only reads the file and passes the text on | A score is untrusted text. Reading it in the child keeps a slow or broken score from stalling Hallux, and keeps the reader in one place |
| How an expression is computed | It is read into a tree once, and the tree is walked for every block of samples, with numpy doing each step for the whole block | No `eval` and no generated code. The walk costs a few microseconds per block, against milliseconds of sample maths |
| The life of the child | It starts with the first `play`, stays for the next ones, and ends with `stop()` | Starting it takes about half a second here (numpy 0.25 s, pygame 0.16 s). `stop()` leaves nothing behind, which is what Hallux expects of the hook |
| The old song while a new one is prepared | It plays on until the new one starts. A new score that fails its check changes nothing | Silence while the new song renders would be a gap of up to seconds. A player that is given a broken file keeps playing |
| A render that takes too long | The addon waits 8 seconds, then ends the child, and `play` fails with `the song took too long to render` | Hallux cuts every call at 10 seconds with a bare `timed out`. The addon's own limit comes first and says why |
| No sound device | `play` fails with `no sound device: …` and SDL's reason | Checked here: without a sound server, pygame's mixer refuses to open. It doesn't fall back to a silent driver, so nothing has to guess |
| Rounding inside the addon | A step becomes a sample by rounding half up, in whole numbers. The fades and the glides round down | The design fixes the rounding of `/` in expressions, not of these. Rounding down is what the render that was listened to did |
| The noise | One fixed formula, written out in step 3: the one the hi-hat and the snare were heard with | "The same `x` always gives the same value" needs one formula, on every computer |
| The first numbers of the limits | A table in step 6, to be confirmed by timing a whole render there | The design leaves them to a measurement |
| What a problem looks like to the AI | `{"error": "MusicError: line 7: unknown name CUTOF\nline 12: …"}` | The addon system puts the error's name in front, as with `WindowError`. The design's example shows the text without it |
| Problems that teach | `&&`, `||`, `!`, `**` and a number like `0.5` each get a message that says what to write instead | The AI writes them out of habit, and every wrong try makes the user wait |
| Tests without a sound card | SDL's "disk" driver writes what would be played into a file. The tests compare that file | Tried on 2026-10-02: the mixer passed the samples on bit for bit, and a queued sound followed without a gap |

---

## The reference render

The folder [reference/](reference/) holds the throwaway scripts of 2026-10-02. They aren't
part of the addon, and nothing imports them but tests.

| File | What it is |
|---|---|
| `scores.py` | Renders the three scores of the design, and the pad with a tail, in the design's arithmetic but without a parser. **The user listened to exactly these samples and accepted them.** Step 6 is done when the real renderer gives the same samples |
| `demo.py` | The instruments the user heard first: the fades, the saws, the bell, the electric piano, the vibrato, the drums, the pad |
| `bench.py` | The timing behind section 8 of the design, and the measurement of the saw's aliasing |
| `pg_disk.py` | The test of pygame's mixer with SDL's disk driver |
| `play_pg.py` | Plays the drum beat through pygame's mixer on the real sound card |

They need numpy, and the last two need pygame. `scores.py` and `demo.py` write a WAV file
beside themselves when run by hand.

---

## Where the code goes

| File | What | Step |
|---|---|---|
| `hallux/addons.py` | The disk handle; a `disk` parameter in `schema_for` and `call` | 1 |
| `hallux/tools.py`, `hallux/machine.py` | The machine's disk reaches the addon tools | 1 |
| `tests/test_addons.py` | The tests of the handle | 1 |
| `pyproject.toml` | `music = ["numpy", "pygame"]` under the optional installs | 2 |
| `addons/music_engine/__init__.py`, `limits.py`, `expr.py` | New | 2 |
| `addons/music_engine/compute.py` | New | 3 |
| `addons/music_engine/score.py` | New | 4 |
| `addons/music_engine/song.py` | New | 5 |
| `addons/music_engine/render.py` | New | 6 |
| `addons/music_engine/player.py`, `__main__.py` | New | 7 |
| `addons/music.py` | New | 8, 9 |
| `tests/test_music_*.py`, one per module | New | 2 to 9 |
| `tests/scores/*.score` | The three scores of the design, as files | 4 |
| `README.MD`, `docs/` | The status lines, the roadmap, a section on the music addon | 10 |

The tests of steps 2 to 9 are skipped when numpy or pygame isn't installed, like the window
addon's tests.

---

## The steps

Each step can be merged by itself. A step needs the ones named beside it.

| Step | File | Needs | Status |
|---|---|---|---|
| 1. The disk handle | [01-disk-handle.md](01-disk-handle.md) | | Built on 2026-10-02 |
| 2. Reading an expression | [02-expression-reading.md](02-expression-reading.md) | | Built on 2026-10-02 |
| 3. Computing an expression | [03-expression-computing.md](03-expression-computing.md) | 2 | Built on 2026-10-02 |
| 4. Reading a score | [04-score-reading.md](04-score-reading.md) | 2 | Built on 2026-10-02 |
| 5. Unfolding a score | [05-score-unfolding.md](05-score-unfolding.md) | 4 | Built on 2026-10-02 |
| 6. Rendering | [06-rendering.md](06-rendering.md) | 3, 5 | Built on 2026-10-02, and heard: "sound great" |
| 7. The child | [07-child.md](07-child.md) | 6 | Built on 2026-10-02; the user still has to hear it |
| 8. The addon | [08-addon.md](08-addon.md) | 1, 7 | Built on 2026-10-02 |
| 9. The manual | [09-manual.md](09-manual.md) | 8 | Built on 2026-10-02 |
| 10. The live run, and the documentation | [10-live-run.md](10-live-run.md) | 9 | Done on 2026-10-03 |

Steps 1 and 2 don't depend on each other, and either can come first. This table is the only
place that holds the status.

---

## Risks

- **The AI may need several tries for a score.** Every failed check is a round trip, and the
  user waits. The problems have to say what to write, not only what is wrong (steps 2 and
  4). In the live run it needed one try for each of seven new scores, and one more after an
  edit of its own that went wrong (step 10).
- **The manual is long, and it is read at every boot that uses the addon.** It is 7987
  characters, under its limit of 8000. Reading it cost about $0.045 in the live run.
- **A score inside every limit can still render too slowly.** Step 6 timed whole renders, and
  the limits stand: the two stress scores take 2.3 and 2.0 seconds. But 64 voices that all
  sound for 300 seconds take about 18 (measured: 18.4). The addon's 8 seconds catch that
  (step 8).
- **I can't hear, and I can't reach the sound card.** My sandbox doesn't let the socket to the
  sound server through. Every test here runs without sound, and each step that changes what
  is heard ends with something for the user to listen to.
- **Samples have to be the same on every computer.** `decay` and the smoothed waves go
  through floating-point numbers before they are rounded. The reference render is the check
  on this computer; another computer could differ by one level in rare samples.
- **The AI may imagine instead of calling.** It didn't: in the live run and in the scripted
  run every `play` on the screen was a call in the log.
