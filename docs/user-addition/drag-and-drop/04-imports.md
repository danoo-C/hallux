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

## As built

Built on 2026-10-10, on the branch `drag-and-drop`. 27 new tests (24 in
`tests/test_importing.py`, 3 in `tests/test_machine.py`), 1749 in all. Two old test files
changed, as the step says: the tests' `FakeTerminal` got its empty `refresh`, and a test of
the scripted terminal got a line for its own. The whole suite takes 123 seconds, as before;
the 24 new tests take about one. Still nobody can reach an import: the tab is step 5.

**Where it differs from the text above:**

- **A thread of its own, not `asyncio.to_thread`.** A daemon thread, as an addon's function
  gets one (`call` in `hallux/addons.py`, for the same reason). asyncio waits for the
  threads of its pool when the loop ends, so a copy that hangs on a drive that doesn't
  answer would keep Hallux from quitting. `close()` still stops what runs and waits for
  it, for two seconds at most (`CLOSE_SECONDS`). After that it says so in the log and goes
  on, and the thread ends with Hallux.
- **One `threading.Event` for each walk and each copy, not one for all.** With one, a walk
  that is replaced by a new drop would have to be waited for before the event could be
  cleared for the next. Now the old walk is stopped and the new one begins at once. For a
  moment both run, and both only read. What the old one still reports, and what it ends
  with, reaches nobody.
- **`changed` is called for what a thread changes:** how far a walk or a copy is, ten times
  a second at most, and its end, always. What a call of the tab changes (`drop`, `clear`,
  `start`), the tab draws itself, as it draws after any key.
- **`drop` returns `None` when it took the text,** and otherwise the words.

**Decided while building,** where the text above leaves it open:

- **`Seen`** has the state, `into`, `names` (what was dropped, in its order), the tree's
  `lines`, `counts` and `refused`, `through` and `result`. In `empty`, `into` is where a
  drop would go now. In `looking`, `counts` is how far the walk has come. In `copying`,
  `through` is how far the copy is, of `counts`.
- **"Something in it would be copied"** is `counts.to_copy`: how many things have no mark
  that skips them. A file that exists counts: it is copied if the user says so.
- **A walk that was stopped** leaves the state `ready`, with a tree that is refused as
  `stopped`. It can't be copied, and one more drop looks at everything again. Only `stop()`
  does that, and the tab has no key for it while a walk runs.
- **A destination that is gone doesn't refuse the drop.** The tree does: `ready`, refused,
  as the table of states has it. **A destination behind the fence** doesn't either: every
  line of its tree says `can't go there`.
- **Two things of one name in one drop** are refused, like a second one for the list.
- **A mistake in a thread,** an error that the walk or the copy doesn't expect, is in the
  log with its traceback. The tab gets a tree that is refused,
  `couldn't be looked at: ` and the error, or a result that ended, `failed: ` and the
  error. Without that the tab would say `counting…` for ever.
- **The first word of every walk and every copy is drawn at once,** and then no more than
  ten a second.
- **The log's line** is `import into /home/user/Music: 2 files, 1 folders, 8 bytes; 0
  skipped, 0 failed`, with `; stopped` or what else ended it. The copy's own thread writes
  it, so a copy that Hallux's end stopped has its line too.
- **The machine asks its terminal to draw when a thread reports,** not before. A terminal
  that is `None`, which one old test builds a machine with, never gets that far.

**For step 5:**

- **The six functions** are `machine.imports.watch`, `drop`, `reads`, `start`, `stop` and
  `clear`.
- **`drop` and `start` have to be called in the event loop,** as a key's handler is. They
  start a thread that reports back into that loop.
- **Enter does something** when `seen.counts.to_copy` isn't 0. **The question is asked**
  when `seen.counts.marks` has `exists`.
- **`reads` and `drop` may ask `wslpath`,** which takes a few milliseconds, and two seconds
  at most if it hangs.

**Checked beyond the tests,** in a real event loop, with a task beside it that measures
how long the loop is held:

- **A big folder:** the repository's `.venv`, 6,196 files, was looked at in 1.2 seconds.
  The tab would have seen the files grow: 0, 468, 649, 1,053, and on. A new drawing was
  asked for 12 times, and the loop was never held longer than 5 ms.
- **A copy:** the repository's `docs`, a package of 686 files and one file of 300 MB, 764
  files and 324 MB in all, in half a second. The tab would have seen `61 files, 904 kB`,
  `130 files, 1.8 MB` and on to the end. Six drawings, the loop never held longer than
  1 ms, and what arrived is the same as its source.
- **Stopped in the middle of a file that it replaced:** the result says `stopped`, the old
  file is whole, and nothing with `.hallux-` in its name is left. After `close()` no
  thread is left.
- **The code was broken in 58 ways,** one at a time, and a test noticed each. At the first
  go seven of sixty went unnoticed. The lines among them that turned out to do nothing are
  gone, and the others have their tests now.
