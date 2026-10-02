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
