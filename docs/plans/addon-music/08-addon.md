# Step 8: the addon

[The plan](README.md) · the design: [addon-music.md](../../addon-music.md), section 1, and
[addons.md](../../addons.md)

**Needs:** steps 1 and 7. **Makes:** `addons/music.py`, `tests/test_addon_music.py`.

The file that Hallux loads. It is the bridge and nothing more: it reads the score file,
talks to the child, and turns the child's answers into what the AI gets. From this step on,
a machine has the music addon.

## Build

**The file,** as the loader wants it:

| Part | What |
|---|---|
| The docstring's first line | `A sound card: plays score files with bytebeat instruments.` |
| `prompt()` | The manual. In this step it is short: what `play` and `stop` do. Step 9 writes the real one |
| `play(disk, path: str, loop: bool = False)` | Plays the score at that path |
| `stop()` | Stops the sound and ends the child. It never fails, and it is Hallux's hook as well |
| `connect(emit)` | Keeps `emit`, for `finished` |
| `EXPOSED` | `[play, stop]` |

- **When numpy or pygame is missing,** the file raises `ModuleNotFoundError` while it is
  imported, without importing either. The loader then skips the addon, and the status bar
  shows `addon music skipped: No module named 'numpy'`.
- **Hallux never imports numpy or pygame.** Only the child does.

**What `play` does:**
1. It reads the file with `disk.read_text(path)` (step 1). A missing file is `ENOENT`, as
   for the disk tools.
2. A file over the limit fails here: `the score is bigger than 64 KB`.
3. It starts the child if none is running, in the `addons/` folder, and waits up to 8
   seconds for its first line.
4. It sends the text and waits up to 8 seconds for the answer.
5. It returns the answer, or raises `MusicError` with the child's error.

**What can go wrong,** and what the AI is told:

| Case | Error |
|---|---|
| The score fails its check | `MusicError: line 7: unknown name CUTOF` and the other lines |
| The file isn't there, or the jail refuses it | `ENOENT`, `EACCES`, as the disk tools say it |
| No sound device | `MusicError: no sound device: …` |
| The answer takes longer than 8 seconds | `MusicError: the song took too long to render`. The child is ended, and the sound with it |
| The child crashed | `MusicError: the sound card stopped: it crashed (…its last line…)`. The next `play` starts a new child |

**The link to the child** is the window addon's, with the same rules: one question at a
time, a number on every question, an answer that comes too late is dropped, what the child
prints goes to a temporary file. A line without a number goes to `emit`.

Two addons then hold nearly the same link. It stays two copies in this step: an addon is
one file, and nothing shared exists for addons to import. Taking it out into Hallux is a
change to the addon system, and can follow when a third addon wants it.

## Tests

With the real child on SDL's disk driver, and with stand-in children for what a real one
doesn't do on demand:

- the file passes every check of the loader, and has events;
- Hallux never imports numpy or pygame: checked in a fresh process, as for the window;
- the tool's schema has `path`, an optional `loop`, and no `disk`;
- `play` of the drum beat file in a test world returns
  `{"ok": true, "seconds": 8.0, "peak": 98}`, and the disk driver's file holds the beat;
- a relative path follows the machine's working directory;
- a missing file, a path outside the root, a file that is too big;
- a score with mistakes: the error holds every line;
- a stand-in child that stays silent: `took too long`, and the child is gone afterwards;
- a stand-in child that dies: `the sound card stopped`, and the next `play` works;
- `finished` reaches `emit`, and an event line between a question and its answer doesn't
  disturb the answer;
- `stop()` twice, `stop()` with nothing playing, and `stop_all` of the addon system;
- numpy missing: the addon is skipped with the reason.

## Done when

In a test world, `play` of the drum beat file returns its length and its peak through the
tool the AI would use, and SDL's file holds the beat.

## For the user

Start Hallux and look at the status bar: no note about a skipped addon. `list_addons` in the
log shows `music`.
