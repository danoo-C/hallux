# Step 10: the live run, and the documentation

[The plan](README.md) · the design: [addon-music.md](../../addon-music.md)

**Needs:** step 9. **Changes:** `README.MD` and `docs/`.

Everything before this step is tested without a model and without sound. This step is the
first time the AI writes a score and the user hears it.

## The live run

It needs the user: the sound comes out of their speakers.

1. **Create a program.** The addon brings functions, not commands:

   ```text
   user@hallux:~$ hallux install a program called play: "play FILE" plays a score file
   with the music addon, "play -l FILE" loops it, "play stop" stops the sound
   ```

2. **Play a score that is known to be good.** Put the drum beat of the design into the
   machine as `beat.score`, with `nano`, and run `play beat.score`.
   - It sounds like the beat of 2026-10-02.
   - The program prints the length and the peak.
3. **Loop it and stop it:** `play -l beat.score`, then `play stop`.
   - The loop has no gap. The sound stops at once.
4. **Let the AI compose:** `hallux write a short tune with a bass, chords and a melody to
   tune.score`, then `play tune.score`.
   - Count in `hallux.log` how many times `play` failed its check before it worked.
   - Listen: is it music?
5. **Break a score.** Change a name in `beat.score` with `nano` and play it.
   - The program prints the problem with its line, the way a player would.
6. **The end of a song.** Create a program that plays two files one after the other, which
   has to listen for `finished`.
   - The second song starts when the first has ended, with nobody typing.
7. **Power.** Start a loop, then `reboot`. Start one again, then `poweroff`. Start one
   again, then Ctrl+Shift+Del.
   - The sound stops each time, and no child process is left behind.
8. **After a reboot,** `play beat.score` works again: the file and the program card are
   still there, and the manual is read again.

**The `--script` run.** A script with the commands of 2, 3 and 5 runs without a keyboard.
Afterwards `hallux.log` has to show `addon_help` and the tool `mcp__music__play` for each
`play` line. A `play` that printed a length without that tool call was imagined, and that
is the thing this run looks for.

**What to write down afterwards,** in this plan's status:

| What | Why |
|---|---|
| How many tries the AI needed for `tune.score` | It says whether the manual and the problem messages are good enough |
| What reading the manual cost | It is paid at every boot that uses the addon |
| How long `play` took for the user, from Enter to sound | The user waits for it |
| What sounded wrong | It goes back into the manual's recipes, or into the design |

## The documentation

- **[addon-music.md](../../addon-music.md):** the status line says what is built. The
  recipes that the live run proved are marked as heard.
- **[addons.md](../../addons.md):** its status line, and section 7.
- **`README.MD`:** a part on the music addon in the "Addons" section: what it is, the
  install line `pip install -e ".[music]"`, and one short score.
- **The roadmap:** the music addon moves from "Later" to done.
- **This plan:** the status table in [README.md](README.md).

## Done when

The user has heard a tune that the AI wrote, played by a program the user created, and the
log shows that every `play` was a real call.

## As run

Done on 2026-10-02 and 2026-10-03. The user has heard tunes that the AI wrote, played by a
program the user created, and the log shows that every `play` was a real call.

**The live run wasn't the list above.** The user ran their own, in the world `test-hallux`,
with real sound: they asked Hallux for an app, `kittymusic`, with a prompt screen, and a
now-playing screen with an album cover in ASCII art, the song's name and a progress bar.
Hallux read the manual and wrote the program card in 23 seconds. Then the user asked for
songs by their vibe. The numbers below are from that world's `hallux.log`.

| What | Result |
|---|---|
| Songs the AI composed | 7, of 1.5 to 5.3 KB: techno with a cello and a violin, a dubstep drop, metal, an "angelic" air and others. Five of them have instruments the AI wrote itself |
| Tries for a new score | **1, for all seven.** Every first version played on the first `play` |
| `play` calls in all | 19. 18 worked |
| The one that failed | A score the AI had edited on request: the edit had cut out two instruments that the patterns still used. The error named the six lines. The AI fixed them, and the next `play`, 9 seconds later, worked |
| From Enter to sound, a new song | 17 to 63 seconds, 43 in the middle. Nearly all of it is the AI writing the score: a render takes 0.3 seconds |
| From Enter to sound, a song from the library | 11 to 29 seconds |
| What reading the manual costs | About $0.045 once per boot: a turn that read it cost $0.069, and the same turn without it $0.024. Afterwards it is in every turn of that boot, at the price of cached text |
| Plays that were imagined | None. The player screen was opened 17 times, and each time a `play` call followed |
| What sounded wrong | Nothing was reported. The user: "it sounds good", "look how good it looks" |

**The `--script` run,** on 2026-10-03, in a new world, with a real model and SDL's disk
driver in place of the sound card: 7 round trips, 44 seconds, $0.18.

```text
user@hallux:~$ hallux install a program called play: "play FILE" plays a score file with
the music addon, "play -l FILE" loops it, "play stop" stops the sound
hallux: installed /usr/local/bin/play (play FILE, play -l FILE, play stop)
user@hallux:~$ play beat.score
beat.score: 8.0 s, peak 98%
user@hallux:~$ play -l beat.score
beat.score: 8.0 s, peak 98% (looping)
user@hallux:~$ play stop
user@hallux:~$ play broken.score
play: broken.score: line 16: unknown instrument or variable: kik
```

Its log shows `addon_help` before the first `play`, then `mcp__music__play` with
`loop: False`, with `loop: True`, `mcp__music__stop`, and a `play` that raised for the
broken score. Every line was a real call, and the problem came back with its line, the way
a player would print it.

**What the live run taught:**

- **The sound starts before a full-screen program is on screen.** Hallux shows such a screen
  only when the AI has written all of it, and the AI called `play` first and drew the album
  cover after. The player appeared 10 seconds into the song, and its bar counted from there.
  The user had the program changed: draw the player first, and call `play` on the first
  tick. That worked, 15 times.
- **`finished` never reached that program.** An event waits until a full-screen program
  ends, and the player is one. Its bar ended on the time instead, from `seconds`. Events
  inside full-screen programs are on the roadmap's "Later" list.
- **A progress bar is a model call per step.** A tick turn takes about 2.5 seconds and costs
  a cent or two, and the next tick comes 2 seconds after it: the bar moves every 4 to 5
  seconds. The tick budget of $0.25 covered about 100 seconds of song; the user raised it to
  $1.25 for that world.
- **A second program used the addon unasked.** Another program of that machine wrote a song
  and played it. The addon is hardware, and any program can reach it.

**What of the list above wasn't done:**

- **A loop on real speakers.** The scripted run looped on the disk driver. Whether a loop is
  heard without a gap is still for the user's ears: `tests/music_play.py --loop`.
- **A program that waits for `finished`** (6). The tests cover the event up to the prompt,
  with a fake model. No real model has acted on it.
- **`reboot`, `poweroff` and Ctrl+Shift+Del while a song plays** (7). The user powered the
  machine off once, after stopping the song. The tests cover the hooks.
- **The drum beat of the design through real speakers.** The user heard it as a WAV file.
