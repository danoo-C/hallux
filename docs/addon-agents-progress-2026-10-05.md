# Addon agents: progress on 2026-10-05

**What this is:** a snapshot of how far the build of addon agents is, written at the user's
request after step 7. It holds no status of its own. The table in the
[plan's README](plans/addon-agents/README.md) stays the one place that says what is built,
and each step's file says under "As built" what was decided while building it.

## In short

- **The check of the plan is done,** and 7 of the 17 steps are built, all on 2026-10-05.
- **No machine can start a job yet.** What is built is the ground the jobs stand on. The
  first step in which a machine can start one is step 10, and the first job a user can
  start is a composition, in step 13.
- **All 1360 tests pass.** There were 1066 before; 294 are new. No model call was made, and
  no step so far needed a real terminal.
- **The work is on the branch `addon-agents`,** made from `main`: nine commits, not pushed.
  Step 7 is built and not committed yet.

---

## What was done, in order

| | What | Commit | New tests |
|---|---|---|---|
| Part 2 | The plan read against the code after the config panel and the three fixes of Hallux's report. 21 findings, seven questions; the user took every recommendation. [The report](addon-agents-plan-check-2026-10-05.md) | `5dda488` | |
| | The fixes written into the plan, the design and the build order | `5d541e6` | |
| Step 1 | Whole-file writes: a file is written beside the old one and renamed over it | `518eb77` | 14 |
| Step 2 | `check`: the music addon renders a score without a sound, in a child that opens no sound card | `5c02910` | 19 |
| | `check` takes `loop`, as `play` does | `4c11deb` | 2 |
| Step 3 | The six settings, their checks, and their rows in the Config tab, hidden | `a93a9fe` | 91 |
| Step 4 | The fenced disk: one folder, the files a job may write, private copies | `24e89c4` | 51 |
| Step 5 | The landing: a job's work is put in place, never over someone else's change | `39ef07e` | 24 |
| Step 6 | The declaration: `agent()`, the `spawn` parameter, `list[str]` as an argument | `15c4c29` | 52 |
| Step 7 | The jobs: the process table, a job's life, its end as an event, with a stand-in worker | not committed | 41 |

In lines: about 1350 of new code in `hallux/` and `addons/`, and about 2500 of tests. Two
files are new: `hallux/jobdisk.py` and `hallux/agents.py`.

---

## What a running machine has of this today

| | From | What you can notice |
|---|---|---|
| Files are written whole | Step 1 | A saved file keeps its mode, and its folder's time of change moves. Nobody reads a half-written file any more: tried with a reader in a second thread, 0 half-written reads of 12,654, where the old code gave 18,006 of 20,158 |
| `check` | Step 2 | The main agent has one more tool of the music addon, and the manual has two lines on it. Whether it reaches for it shows only with a real model |
| The six settings | Step 3 | They can be written into `config.toml`, and a wrong value stops Hallux at the start with its words. Nothing reads them yet, and the panel doesn't show them |

Everything else is built and tested, and nothing in a running machine reaches it yet:

```text
 addons.py     agent(), spawn, Refused, list[str]             step 6
 config.py     the six settings, the model and effort of an agent      step 3
 jobdisk.py    JobDisk: the fence, the copies, land()          steps 4 and 5
 agents.py     Jobs: spawn, the table, kill, the events        step 7
                    │
                    └── run by a stand-in worker; the real one is step 9
```

---

## What is left

In the order of [the build order](plans/build-order.md), which has step 16 before step 13.

| Step | What it brings | What it waits for |
|---|---|---|
| 8. The caps | How many jobs, what they may cost, what fills the budgets again. The machine gets its `Jobs` | |
| 9. A job's real session | A Claude session of its own for each job, with its rules and its tools | **A paid check,** a few cents, with three questions about the SDK. It needs the user's go |
| 10. The main agent's side | `spawn` wired up, `list_processes`, `kill_process`, the event at the shell, the prompt's new section, the six rows shown | |
| 11. A job's end in a full-screen program | It wakes a program that has no fields | A check on a pseudo-terminal before the user's try |
| 12. The status bar and the costs | Jobs on the bar, `~$`, `@wait jobs` | The same |
| 16. The panel's two tabs | Agents and Details | The same |
| 13. The composer | `compose`, its agent and its prompt | The scripted run costs a little. **The first live run is the user's,** and sets the budgets again |
| 14. Keeping a screen | A full-screen program is put aside and comes back as it was | |
| 15. Job control | `<suspend>`, `<resume>`, `<forget>`, Ctrl-Z, `jobs` | A check on a pseudo-terminal, then the user's try |
| 17. The documentation and the live run | | **The live run is the user's** |

**What changes from here on.** Steps 1 to 7 added parts beside the machine. Steps 8, 10 and
11 change the machine's own loop in `hallux/machine.py`, step 9 opens a real session, and
steps 11, 12, 14, 15 and 16 draw on the terminal. Those are where the check of part 2 found
most of what would have gone wrong.

---

## How the plan held

**No step had to be designed again.** Each needed a few decisions the plan hadn't taken, and
they are in the steps' files. The ones worth knowing without opening them:

| Step | Decided while building |
|---|---|
| 1 | A file Hallux may not write is still refused: a rename would have got around its mode. Where a write has to go in place, the log says so |
| 2 | `check` takes `loop`. A loop whose tails ring past its end reports another peak than the song played once |
| 3 | A refusal of the two budgets has short words in the panel, so that it fits a row at 80 columns. `save` checks the pair once, on the file as it would be |
| 4 | The fence is a `Disk` of its own, so a link that is swapped after the check still can't lead out. A given file of more than 1 MB is refused at the start |
| 5 | The landing ends the disk whatever happened. A folder that was deleted and made again isn't the same place |
| 6 | Ending a `spawn` takes a lock that a start also takes: once the AI was told `timed out`, no job can start |
| 7 | A kill is final at once: the row, the event and the dropping of the copies. Only the cost comes later, and if it never comes the row says `unknown` |

**What the check of part 2 saved.** Two of its findings were met exactly where it said:
step 3 would have broken a test of the panel, and Save would have refused a valid pair of
budgets. Both were built the way the check proposed, and both are tests now.

---

## Open, for the user

| | What | My recommendation |
|---|---|---|
| 1 | Step 7 is built and not committed | Commit it |
| 2 | A job whose landing fails on a write, because the disk is full, ends as `failed` with `why: disk`. It is my proposal, and the design's tables don't have it | Take it, and I add it to the design |
| 3 | `check` got `loop` on an "okay" that may have meant something else. It is a commit of its own, `4c11deb` | Keep it |
| 4 | The paid check before step 9 | Say go when step 8 is done. The three answers decide how the real worker is built |
| 5 | Nothing is pushed | The push and the pull request are yours |

**Also in the working tree, and not mine:** `hallux/prompt.md` has a new section,
"SIMULATION BOUNDARIES AND DEBUGGING", between MEMORY and PROGRAMS, and
`hallux/prompt.bak.md` holds the prompt as it is committed. Both appeared while step 7 was
built. I left them alone and won't put them into a commit of mine. All 1360 tests pass with
the change in place. If it stays, the plan's references into `prompt.md` below line 244
move by 26 lines, and I would set them again before step 10, which is the first step that
adds to the prompt.

---

## Not checked so far

- **Nothing was run with a real model.** Every test uses the fakes. That the main agent
  uses `check` is untried.
- **Nothing was looked at on a real terminal,** because nothing built so far draws on one.
  The six rows of the Config tab were drawn on a pipe at 80 columns and looked at; a real
  terminal shows them from step 10 on.
- **With `FORCE_COLOR` set in the shell one test fails:** the window addon's. Step 2 mended
  the music addon's; the window's isn't in this plan.
