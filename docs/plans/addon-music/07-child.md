# Step 7: the child

[The plan](README.md) · the design: [addon-music.md](../../addon-music.md), sections 1 and 6

**Needs:** step 6. **Makes:** `addons/music_engine/player.py`, `__main__.py`,
`tests/test_music_child.py`.

The child is a program of its own: `python -m music_engine`, started in the `addons/`
folder. It gets scores as text on its input, plays them, and answers on its output. Nothing
of Hallux is in it, so it can be run and tried by hand.

## Build

**`player.py`,** the only module that touches pygame:

| What | How |
|---|---|
| Opening | `pygame.mixer.init(44100, -16, 1, buffer=1024, allowedchanges=0)`: 44100 Hz, 16-bit, one channel, and no other format accepted. Only the mixer is started, not the display |
| Playing once | One `Sound` made of `first`, and `play()` |
| A loop without `again` | The same `Sound`, with `play(loops=-1)` |
| A loop with `again` | `first` is played, and `again` is queued behind it. Whenever the queue is empty, `again` is queued once more |
| Stopping | `stop()` on the channel. What wasn't played is thrown away |
| The end | The player is asked every 50 ms. When a song that plays once is no longer busy, it says so, once |
| A new song over an old one | The old one is stopped in the moment the new one starts |

**`__main__.py`,** the child itself. It follows `addons/window.py`: one line of JSON per
message, a number on every question, and a line without a number is an event.

| Hallux sends | The child answers |
|---|---|
| Nothing: the child speaks first | `{"id": 0, "ok": true}` once numpy is loaded and the mixer is open, or `{"id": 0, "error": "no sound device: …"}` |
| `{"cmd": "play", "text": "…", "loop": false, "id": 1}` | `{"ok": true, "seconds": 9.6, "peak": 98, "id": 1}`, with `turned_down_to` and `clipped` when they apply |
| The same, with a score that fails its check | `{"error": "line 7: unknown name CUTOF\nline 12: …", "id": 1}` |
| `{"cmd": "stop", "id": 2}` | `{"ok": true, "id": 2}` |
| `{"cmd": "quit"}` | Nothing; it exits |
| Nothing | `{"event": "finished"}`, when a song ends by itself |

- **A `play` runs the whole chain:** `score.read`, `song.unfold`, `render`, then the player.
  The answer goes out when the sound has started.
- **A score that fails its check changes nothing.** What was playing plays on.
- **`finished` isn't sent** for a song that was stopped, replaced, or that loops.
- **A bug in the chain is an answer, not a crash:** `{"error": "addon bug: …", "id": 1}`, and
  the child lives on. The traceback goes to its error output.
- **What a library prints can't garble the line.** The child keeps its own copy of the
  output for the messages and points the ordinary output at the error output, as the window
  does. SDL prints warnings when a sound server is missing.
- **When Hallux goes away,** the child sees its input close, stops the sound and exits.
- **While it renders, the child answers nothing else.** A `stop` sent meanwhile waits its
  turn. The addon's 8 seconds are the way out (step 8).

## Tests

No test makes a sound. They set `SDL_AUDIODRIVER=disk` and `SDL_DISKAUDIOFILE`, and SDL
writes what it would play into that file. The driver runs at the speed of real sound, so the
test songs are shorter than half a second.

- a short song arrives in the file as the samples `render` gave, one for one;
- a loop with a tail arrives as `first`, `again`, `again`, with not one sample between them;
- a loop without tails repeats `first`;
- `stop` cuts the song: the file holds less than the song;
- `finished` comes after a song that plays once, and not after `stop`, not after a new
  `play`, and not for a loop;
- a new `play` replaces the old song;
- a score with two mistakes answers with both lines, and the old song plays on;
- `SDL_AUDIODRIVER` set to a driver that can't open answers `no sound device`;
- an unknown message answers with an error;
- `quit` ends the child, and so does closing its input;
- a line that a library prints doesn't reach the output.

## Done when

The tests pass, and this plays the drum beat on the speakers, typed by hand in the `addons/`
folder:

```text
python -m music_engine
{"cmd": "play", "text": "…the drum beat, with \n for its line ends…", "loop": true, "id": 1}
{"cmd": "stop", "id": 2}
```

## As built

Built on 2026-10-02. The tests pass on SDL's disk driver: a song arrives in the file as the
samples `render` gave, and a loop with a tail as `first`, `again`, `again`, with not one
sample between them. **Nobody has heard it yet:** my sandbox can't reach the sound card, and
there the child answers `no sound device: ALSA: Couldn't open audio device: Connection
refused`, as planned. Decided while building:

- **A render has a thread of its own.** While it runs, the main loop goes on asking the
  player every 50 ms. Without that, a loop with a tail would fall silent during a long
  render: its next round is queued by that asking. A test renders for more than a second
  over such a loop and finds no gap. The child still answers nothing else meanwhile.
- **A short round is queued several at once.** A queued sound is at least half a second
  long, made of whole rounds, so that 50 ms are always enough to queue the next one. A loop
  of one step would otherwise run dry.
- **`stop` and a new `play` throw away what was queued.** Tried with the disk driver:
  pygame's `stop()` doesn't start the queued sound, and a new `play()` on the channel starts
  on the next sample and drops it.
- **A `play` without `loop` plays once.** One whose `text` isn't text, or whose `loop` isn't
  true or false, answers `addon bug: play takes a text, and true or false for loop`.
- **An unknown message** answers `unknown message: rewind`. A line that isn't JSON is
  ignored, as the window does.
- **A bug's answer is cut at 200 characters.**
- **`tests/music_play.py`** is the small script for the run by hand, below.

## For the user

Run this, and listen:

```text
.venv/bin/python tests/music_play.py tests/scores/drum-beat.score
.venv/bin/python tests/music_play.py --loop tests/scores/drum-beat.score
```

It prints what the child answers, and Enter stops the sound. The first should play the beat
once and then print `{"event": "finished"}`. The second should go round without a gap.

My sandbox can't reach the sound card, so only the user can say whether the loop is heard
without a gap.
