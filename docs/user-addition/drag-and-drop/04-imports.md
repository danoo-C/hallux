# Step 4: the machine's side

[The plan](README.md)

**Needs:** step 3. **Changes:** `hallux/importing.py`, `hallux/machine.py`,
`hallux/script.py`, `tests/test_importing.py`, `tests/test_machine.py`.

The machine gets one `Imports`: one list of what was dropped, one walk, one copy at a time,
and what the tab is shown of them. The tab of step 5 knows nothing else. Still nobody can
reach it.

## Build

**`Imports(disk, changed=None)`** in `hallux/importing.py`. `changed` is called, in the
event loop, whenever what `watch()` returns has changed: the terminal draws the panel again
with it.

**What it is asked:**

| | What |
|---|---|
| `watch() -> Seen` | Everything the tab shows, as it is now |
| `drop(text) -> str` | Adds what the text names to the list. Returns nothing, or why not, in words for the foot |
| `reads(text) -> bool` | Whether the text is a drop at all. For a tab that isn't shown (step 5) |
| `start(overwrite)` | Starts the copy. `overwrite` as in step 3 |
| `stop()` | Stops the walk or the copy that runs |
| `clear()` | Empties the list, or forgets the last result |
| `close()` | Hallux ends: stops what runs, and waits for it |

**Its states,** in `Seen.state`:

| State | What is there | What it takes |
|---|---|---|
| `empty` | Nothing | A drop |
| `looking` | The sources, and counts that grow | A drop, `clear`, `stop` |
| `ready` | The whole tree | A drop, `start`, `clear` |
| `copying` | The tree, and how far the copy is | `stop` |
| `done` | The result of the last copy | A drop, which starts a new list; `clear` |

- **A drop** in `empty` or `done` notes the destination: `disk.cwd` at that moment. In
  `looking` and `ready` it adds to the list, and the walk starts again over all sources.
- **A drop is refused** with words: while a copy runs (`a copy is running`); when its path
  is in the list already (`already in the list: ` and the name); when another source has
  its name (`two things named ` and the name); when the destination is the dropped folder
  or inside it (`would be copied into itself: ` and the name, by the same check as step 2's);
  and with what `NotADrop` says. A refused drop leaves the list as it was.
- **`start`** does nothing unless the state is `ready`, the tree isn't `refused`, and
  something in it would be copied.

**`Seen`:** the state, the destination, the tree's lines and counts, why the tree is
refused, how far the copy is (files and bytes, done and in all), and the result. It is a
snapshot: the tab may keep it between two redraws.

**The two threads.** The walk and the copy each run with `asyncio.to_thread`, one at a time.
They share one `threading.Event` for stopping. What they report (`tell`) is put into the
`Imports` under its lock, and `changed` is asked for with `loop.call_soon_threadsafe`, at
most ten times a second.

**In the machine** (`hallux/machine.py`):

- `self.imports = Imports(self.disk, changed=...)`, beside `self.jobs`. `changed` is the
  terminal's `refresh` (`hallux/terminal.py:343`), which draws Hallux's own part of the
  screen again, wherever it is: the panel at the shell, or block mode's screen with the
  panel as its layer. The scripted terminal (`ScriptTerminal`, `hallux/script.py:59`) and
  the tests' terminal (`FakeTerminal`, `tests/test_machine.py:105`, which the others extend)
  get an empty `refresh`: they have no panel.
- `run()` (`hallux/machine.py:288`) calls `self.imports.close()` in its `finally`. Without
  it, Hallux would wait at its end until a copy is through: the loop waits for its threads.
- A reboot touches nothing: a copy goes on over it.
- Every copy that ends writes one line to the log: the destination, the counts, why it
  ended.

## Tests

With a real `Disk` on a temporary folder, and real threads:

- `empty` → a drop → `looking` → `ready`: the tree is there, and `changed` was called.
- A second drop while `ready`: both are in the tree.
- The destination is the directory of the first drop, also when `disk.cwd` changes before
  `start`.
- Each refusal: a copy runs; the same path again; a second thing of the same name; a folder
  that holds the destination; a text that is no drop. The list is as it was after each.
- `start(None)` → `copying` → `done`: the files are there, the result is in `Seen`.
- `start` while `looking`, and with a tree that is `refused`: nothing happens.
- `stop` while a slow copy runs (a stand-in `copy_whole` that waits): `done`, and the
  result says `stopped`.
- `clear` while `looking` stops the walk: `empty`.
- `close` while a slow copy runs returns within a second, and no thread is left.
- A drop in `done` starts a new list, with the destination of that moment.
- In `tests/test_machine.py`: the machine has an `Imports` on its disk, and a machine that
  halts while a copy runs ends.

## Done when

The tests pass, and the whole suite is as fast as before: no test waits on a real walk
longer than a moment.
