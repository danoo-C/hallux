# Handoff: drag and drop, after step 4

**Written on 2026-10-10,** at the end of the session that built steps 1 to 4. It replaces
the handoff of addon agents, which is merged into `main` (pull request #9); that note is
still in the history: `git show d0cbe1f:handoff.md`. It is a working note for picking the
work up again, not a place that holds status. The status is in the table of the
[plan's README](docs/user-addition/drag-and-drop/README.md), and each step's file says
under "As built" what was decided while building it. Delete this file before the pull
request if you don't want it there.

## Where things stand

- **What it is:** files dragged onto the terminal window are copied into the shell's
  directory, from a new Files tab of the Ctrl+F12 panel. The AI takes no part in the copy.
- **Branch:** `drag-and-drop`, made from `main` after `addon-agents` was merged into it.
- **Built:** steps 1 to 4 of 7. **Nothing changes for a user yet:** everything up to here
  is the machinery, and nothing can reach it until the tab of step 5.
- **Everything is committed,** this note too. The working tree is clean.
- **Pushed:** the plan and steps 1 and 2 (`7760e85`); the user pushed and set the upstream.
  **Not pushed:** three commits: step 3, step 4, and this note's.
- **Tests:** 1749, all pass, in about two minutes: `.venv/bin/python -m pytest -q`.
- **No model was called,** and no step of this plan needs a paid check.

| Step | What | Commit |
|---|---|---|
| | The plan: a README with the design and the decisions, and seven step files | `7760e85` |
| 1 | Reading a drop: `read_drop`, `from_windows`, `NotADrop` | `7760e85` |
| 2 | The tree: `look`, `Tree`, `Line`, `Counts`; `Disk.place`; `statusbar.size` | `7760e85` |
| 3 | The copy: `carry_out`, `Result`; `copy_whole` in `hallux/disk.py` | `fe46bd3` |
| 4 | The machine's side: `Imports`, `Seen`; `machine.imports` | `7742822` |

Nearly all of it is in `hallux/importing.py`. The table names what is elsewhere; besides
that, the `Terminal` protocol and the scripted terminal got a `refresh`.

## What comes next: step 5, the Files tab

[The step's file](docs/user-addition/drag-and-drop/05-files-tab.md). It makes
`hallux/panel_tabs/files.py` and `tests/test_panel_files.py`, and changes `hallux/panel.py`,
`hallux/app.py` and `tests/test_panel.py`. **From this step on the user can import.**

- **It is the first step that draws on the terminal.** It ends with a check of the drawn
  screen in tmux, which the step writes out under "Before the user tries it": the real
  `Machine`, `Terminal` and `Panel` with a pretend model, and `tmux paste-buffer -p` as
  the drop. A test on a pipe isn't enough for it.
- **Steps 5 and 6 don't depend on each other.** Step 6 changes `hallux/prompt.md`, which
  the user edits too: look at the working tree before touching it.
- **I can't run Windows Terminal.** The real drag is the user's try, in step 7.

**What it builds on, as step 4 really built it:**

| What | How it is |
|---|---|
| The six functions the tab is given | `machine.imports.watch`, `drop`, `reads`, `start`, `stop`, `clear` |
| `watch()` | Returns a `Seen`: `state`, `into`, `names`, `lines`, `counts`, `refused`, `through`, `result`. A snapshot, which the tab may keep |
| The states | `EMPTY`, `LOOKING`, `READY`, `COPYING`, `DONE`, constants in `hallux/importing.py` |
| `drop(text)` | Returns `None` when it took the text, otherwise the words for the foot |
| Where they are called | `drop` and `start` in the event loop, as a key's handler is: they start a thread that reports back into that loop |
| Who draws | The terminal's `refresh` is called for what a thread changes. What a call of the tab changes, the tab draws itself |
| Enter does something | When `seen.counts.to_copy` isn't 0 |
| The question is asked | When `seen.counts.marks` has `EXISTS` |
| A line of the tree | `Line`: `depth`, `name`, `kind`, `size`, `files`, `mark`. `kind` is `MORE` for `… 6 more` and `… and more`. `mark` is the text to draw; `SKIPPED` names the five marks that aren't copied |
| A size | `size()` in `hallux/statusbar.py`: `340 kB`, `2.3 MB` |
| A refusal | A long text is cut at its front and keeps its end, where a path has its name |

## Decided by the user

- **The drop is taken in the panel, in a tab of its own,** and what would be copied is
  shown as a tree that scrolls, before it is copied.
- **A refusal shows the end of a long text,** not its start ("keep the end").
- **The check before the build** was the user's, in both terminals: Windows Terminal sends
  a drop as a paste in brackets, VS Code's terminal types it.

## Open, for the user

| | What | My recommendation |
|---|---|---|
| 1 | Three commits aren't pushed: steps 3 and 4, and this note's | The push and the pull request are yours |
| 2 | The go for step 5 | Say "continue" |
| 3 | The decision table of the plan's README. Its first two rows are yours; the rest is my proposal, and steps 1 to 4 were built by it | Read it before step 5: the rows on the tab's name and keys are what step 5 builds |
| 4 | The branch's name, `drag-and-drop`, which I chose | Keep it |
| 5 | How a path with a space, and a file from `C:`, really arrive in the two terminals. Step 1 reads the forms I expect, and reads them rightly from the real `/mnt/c` | Drag one of each onto the `cat -v` check of the README, or wait for step 7's try |
| 6 | What steps 1 to 4 decided beyond the plan, below | Read the list. Say so if one is unwanted |

**Decided beyond the plan in steps 1 to 4.** Each is in its step's "As built":

- **A path of this distribution is never given to `wslpath`.** The rule's answer is the only
  one there is, and `wslpath` says the same.
- **`file://` with another computer's name in it** is no file of this computer.
- **The marks are looked for in a slightly other order:** `can't go there` first, and a
  pipe or a socket is `not copied` also when its name is taken.
- **The counts are of everything the walk came to,** whatever its mark. So the tab's
  `14 files · 2 can't be copied` means two of the fourteen, and the copy counts what it is
  through with, copied or not.
- **The tree has a fifth thing, `stopped`,** so that a tree which was cut short can't be
  taken for a whole one.
- **`copy_whole` replaces a file and nothing else.** A folder or a link that has the name
  by then stays, and the file fails with `File exists`.
- **A folder that can't be made is in `failed`, and so is every thing in it.**
- **A file whose name is longer than about 238 bytes can't be copied:** there is no room
  for the longer name of the file beside it.
- **A walk and a copy run in a daemon thread of their own,** not in asyncio's pool, so that
  a copy which hangs can't keep Hallux from quitting. Each has its own stop.
- **An error that a thread doesn't expect** is in the log, and the tab is told of it in
  place of waiting for ever.

**What was seen that the user may want to know:**

- **A folder of the Windows drive is slow to look at:** about 3 ms a file, where the Linux
  disk takes 0.16 ms. Ten thousand files from `C:` count for about half a minute before
  the tree is there. The counts grow in the tab meanwhile.

## How the work is done here

The user's rules, as in the plans before:

- **One step at a time, and only when asked.**
- **A commit only when asked.** "Continue" alone isn't "commit": in this session steps 3
  and 4 stayed uncommitted until the user said so, and then went in as one commit a step.
- **Before a step:** read the plan's README and the step's file.
- **A step is done** when its tests pass with all the old ones, its "Done when" holds, the
  README's table says so, and its file has an "As built".
- **Say what could not be checked,** and what was decided beyond the plan.

**What this session did at every step,** and the next should too:

- **Break the code to check new tests.** Each step's code was broken one way at a time, in
  a copy of the package, and every way had to fail a test: 48, 70, 59 and 58 ways. A way
  that passes is a test that is missing, or a line that does nothing. Both were found.
- **Check with the real thing beyond the tests:** the real `wslpath`, the user's real
  folder, a real thread, a real event loop. Each step's "As built" says what was run.
- **Set the line references of the unbuilt steps again** after a step that moved them, and
  before the commit. Step 6's were set after step 4.
- **Add files to a commit by name,** never `git add -A`. Inside a sandboxed session the
  root shows untracked placeholders (`.bashrc`, `.gitconfig`, `.claude/…`) that are
  nobody's work.
- **Give pytest a `TMPDIR`** when a script starts it: without one it makes a
  `pytest-of-dano/` in the repository's root.
- **Stay in the repository's root in the shell.**

## Where the session's throwaways are

Nowhere that lasts. The scripts that broke the code, and the ones that ran the real
checks, were in the session's temporary folder, and part of it was gone before the session
ended. Nothing in the plan depends on them: what each one did and showed is in its step's
"As built".

## Where to read more

| | |
|---|---|
| The plan, its decisions, its status | [docs/user-addition/drag-and-drop/README.md](docs/user-addition/drag-and-drop/README.md) |
| Step 1 as built | [01-reading-a-drop.md](docs/user-addition/drag-and-drop/01-reading-a-drop.md) |
| Step 2 as built | [02-tree.md](docs/user-addition/drag-and-drop/02-tree.md) |
| Step 3 as built | [03-copy.md](docs/user-addition/drag-and-drop/03-copy.md) |
| Step 4 as built, with what step 5 needs of it | [04-imports.md](docs/user-addition/drag-and-drop/04-imports.md) |
| Step 5, the next | [05-files-tab.md](docs/user-addition/drag-and-drop/05-files-tab.md) |
| The panel's design, which the tab joins | [docs/config-panel.md](docs/config-panel.md) |

## To pick up

Say, for example: "Read handoff.md and continue." Nothing waits to be committed, so that
builds step 5, the Files tab.
