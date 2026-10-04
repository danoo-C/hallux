# Plan: addon agents

**Status:** written on 2026-10-04. Nothing is built. The design it follows is
[addon-agents.md](../../addon-agents.md), in which no question is open. The decisions this
plan takes on its own are in a table below. They are my proposals, and the user hasn't
confirmed them yet. The [config panel](../config-panel/README.md) is built first, and one
check with a real model has to happen before step 9; both are under
[Before the build](#before-the-build).

**Reviewed on 2026-10-04:** [plans-review-2026-10-04.md](../../plans-review-2026-10-04.md).
It found four things that would have gone wrong and a list of gaps. The user accepted a fix
for each, and they are in the steps. [After the review](#after-the-review) lists them.

**How this plan is laid out.** Like the plans for the music addon and the config panel. This
file holds what the steps share: how the parts fit, the decisions, where the code goes, and
the status. Every step has a file of its own in this folder. A step is built and merged by
itself, so whoever builds one reads this file and that step's file.

## In short

1. **Whole-file writes:** a file is never seen half-written.
2. **`check`:** the music addon renders a score without sound, in a child that opens no
   sound card.
3. **The six settings** in `config.toml`. The panel shows them from step 10 on.
4. **The fenced disk:** one folder, the names and files a job may write, private copies.
5. **The landing:** a job's work is put in place when it ends well, and never over a change
   someone else made.
6. **The declaration:** `agent()`, the `spawn` parameter, a list as an argument.
7. **The jobs,** with a stand-in worker: the process table, a job's life, its end as an
   event.
8. **The caps:** how many jobs, what they may cost, how long they may run. The machine gets
   its `Jobs` here.
9. **A job's real session:** a Claude session of its own, with its rules and its tools.
10. **The main agent's side:** `spawn` wired up, `list_processes`, `kill_process`, the event
    at the shell, the prompt.
11. **A job's end in a full-screen program.**
12. **The status bar, the costs** and `@wait jobs`.
13. **The composer:** `compose`, its agent and its prompt. The scripted run and the first
    live run.
14. **Keeping a screen:** a full-screen program is put aside and comes back as it was.
15. **Job control:** `<suspend>`, `<resume>`, `<forget>`, Ctrl-Z, `jobs`.
16. **The panel's two tabs:** Agents lists the jobs and the idle agents, Details shows one
    job live. A job can be killed from there.
17. **The documentation and the live run.**

Until step 10 no machine can start a job. Before that a running machine changes in two
places: step 1 changes how every file is written, and step 2 gives the music addon `check`.
The first job a user can start is a composition, in step 13.

---

## How the parts fit

```text
 main session ── music.compose(request, folder, edit) ──► addons.call()
      ▲                                                       │ spawn(brief, folder, edit)
      │  list_processes, kill_process                         ▼
      │  <events> job … </events>                  Jobs  (hallux/agents.py)
      │                                              │  the table, the caps, the events
      │                                              │
      │                                 JobDisk  (hallux/jobdisk.py)
      │                                    the fence, the private copies, the landing
      │                                              │
      └────────── Machine ◄── ends, events ──── a worker per job
                                                     │
                                          a Claude session of its own
                                          tools: 4 file tools, set_status, the addon's `tools`
```

**One job, from start to end:**

1. The main agent calls `compose` of the music addon. Hallux runs the function in a thread
   and hands it `spawn` (step 6).
2. `spawn` asks `Jobs` for a job. `Jobs` checks the caps (step 8), builds the job's fenced
   disk, which checks the folder and the list of files (step 4), notes a row in the table
   and returns the pid (step 7). The function returns `{"pid": 30001}`.
3. In Hallux's event loop a worker starts for the job: a Claude session with the worker's
   rules, the addon's prompt and the job's tools (step 9).
4. The worker writes files, into private copies (step 4), and calls `check`, which reads
   those copies through the job's disk handle (steps 2 and 4).
5. Meanwhile the main agent reads the table with `list_processes` (step 10), and the bar
   shows the job (step 12).
6. The session ends. The copies land in the folder (step 5), the row says `done` with what
   the job cost, and Hallux makes the event (step 7).
7. The event reaches the main agent: at once if it listens, or in front of its next
   message (steps 10 and 11).

All the while the user can open Hallux's panel and watch: the job's row, and its tool calls
as they happen (step 16). That is beside the machine, not part of it.

---

## Decisions this plan takes

**From the design.** The plan follows its decision tables.

**What the design leaves open, decided here.** These are my proposals. The user hasn't gone
through this table, apart from what the review settled.

| Topic | Decision | Why |
|---|---|---|
| Who makes `Jobs` | The machine, when it is made itself, in step 8. `Jobs` gets the machine's disk, a function for the settings as they are, and a function that makes workers. It learns the event loop when it is started | The disk, the live settings and what the boot has spent are the machine's, and Hallux builds its parts before the event loop runs. A scripted run makes a machine of its own and gets its `Jobs` with it |
| A job's limits | They travel with the job: its dollar cap, its turns and its time, read from the settings when it starts | Steps 8 and 9 then never have to settle who passes them |
| The jobs' dollars | A sum of their own, beside the main session's | An event's turn is measured as the change of the main session's sum |
| A brief that is too long | `EMSGSIZE` | `E2BIG` is taken by a list of more than 8 files |
| Addon events and job events that wait together | One `<events>` block, the addons' first | The AI knows one block |
| The tag for a kept screen that is gone | `<gone job="1"/>` | The design says Hallux tells the AI, and not how |
| A job number in a tag | Digits only. Anything else is ignored, with a line in the log | Hallux keeps screens under it |
| What a resumed program has spent on ticks | It is restored with the screen | A suspend isn't a way around the tick budget |
| How many rounds of `check` the composer makes | Until it is clean and the peak is between 50 and 100, at most four | The design leaves it to the composer's prompt |
| Where the code lives | `hallux/agents.py` holds the table, the jobs and a job's session. The fenced disk is a file of its own, `hallux/jobdisk.py` | The design names one new file. The fenced disk is about 300 lines with no session and no table in it, and it is tested by itself |
| The job's disk | A `JobDisk` has the methods of `Disk` that a job needs, with the same names. The disk handle is built on it unchanged; the job's file tools have a builder of their own that shares the main agent's wrapper | A job's tools are then the main agent's tools on another disk, not a second set |
| How the landing writes | Each file through the whole-file write of step 1, not by moving the copy | One way to put a file in place, and the copy and the folder needn't be on the same file system |
| A worker | `Jobs` drives a worker through three things: run, stop, and what it reports. Step 7 has a stand-in, step 9 the real one | The table, the caps and the events are built and tested before any session exists |
| When a tool call begins and ends | Hallux's own tool functions say so. Every tool of a job runs inside Hallux | No guessing from the session's messages |
| Refusing a start | `spawn` raises `Refused`, a class of Hallux's. The call wrapper answers `{"error": "EAGAIN"}`, or `{"error": "ENOENT", "path": …}` for a file | An addon imports nothing from Hallux, so only Hallux can raise it |
| The errors a job gets | `EACCES` outside the fence or for a file it may not write, `EDQUOT` over its limits, `ESTALE` from a handle whose job has ended | The names a real machine has for these |
| `kill_process` of a pid that isn't there | `ESRCH` | What `kill` says |
| `agent_max_running = 0` | Every start is refused with `EAGAIN`. The addon and its functions stay | The design says 0 turns addon agents off, and not how it looks |
| The prompt's new section | A file of its own, `hallux/prompt_jobs.md`, added to the system prompt on a machine that has an addon with an agent | The main prompt is one constant today. Lines that only some machines get don't belong in the middle of it |
| The worker's rules | `hallux/agent.md`, with the agent's and the addon's name filled in | The design's draft says "the composer of its music addon" |
| The music manual's limit | It goes from 8000 to 8500 characters | The manual is 7987 long. The lines on `check` and `compose` need about 400 |
| What the composer reads | Its role, the part of the manual on writing a score, and `check`. Not the lines on `play`, `stop` and `compose` | It can't call those |
| The names for kept screens | `suspend_form`, `resume_form`, `forget_form` on the terminal | `keep_form` is taken by the config panel's plan, for something else |
| A kept screen that is gone | Hallux tells the AI at once, in a message of its own, and the AI draws the program again | The user typed `fg` and waits. The design says "with the next message" |
| A ninth kept screen | The oldest is dropped | The design gives the limit, 8, and not what happens at it |
| What the panel's tabs read | One function of `Jobs`, `watch()`: the rows, the idle agents, each job's activity, the total | The tabs then know nothing of how `Jobs` keeps it, and the tests give them a `Jobs` with stand-in workers |
| A line of activity | A time, a kind and a text of at most 500 characters, cleaned when it is kept. 200 lines per job | The design gives the 200. A text that is cleaned once can't be shown uncleaned by a tab that forgets to |
| The order of the Agents tab | Running jobs, then ended ones, then idle agents; the newest on top in each | What needs attention is at the top |
| When the tabs step is built | Any time after step 10. It is step 16 only because job control doesn't need it | Before step 13 it helps with the composer's first live run |

---

## Before the build

| What | Who | Before | Why |
|---|---|---|---|
| The config panel, by [its plan](../config-panel/README.md) | | Step 3 | The settings are checked and typed the panel's way (its step 1) and become rows in its Config tab (its step 5). The budget per boot is Hallux's own check (its step 3), and jobs count towards it. A program can go on without an answer, and its wait can be started again (its steps 3 and 7), which a job's end in a full-screen program needs. The panel's tab system (its step 5) takes the two tabs of step 16 |
| A check with a real model, a few cents | Whoever builds step 9, when the user says go | Step 9 | Three things the design leaves to a run, below |

**The check before step 9,** with a throwaway script, as for the design:

| Question | What it decides |
|---|---|
| Does the result that follows `interrupt()` hold the session's cost? | Whether a killed job's dollars are read. If not, it counts with its full cap, and its row says that the cost isn't known |
| Where do the tokens of a running turn come from: each model message, or the stream? | Whether a job's session is opened with the stream on |
| Does the session's dollar cap end a job in the middle of a turn, or after it? | By how much a job can pass `agent_job_budget_usd` |

---

## Where the code goes

| File | What | Step |
|---|---|---|
| `hallux/disk.py` | Every write of a whole file writes beside it and renames | 1 |
| `addons/music_engine/__main__.py`, `addons/music.py` | The child's mode without the mixer; `check` | 2 |
| `hallux/config.py` | The six settings | 3 |
| `hallux/jobdisk.py` (new) | The fence, the names, the list of files, the private copies | 4 |
| `hallux/jobdisk.py` | The landing, the conflict, dropping the copies | 5 |
| `hallux/addons.py`, `hallux/tools.py` | `agent()`, `spawn`, `list[str]`, `Refused`, an agent counts as events | 6 |
| `hallux/config.py` | The five effort names move to `addons.py`, and are taken from there | 6 |
| `hallux/agents.py` (new) | The table, a job's life, the job events | 7 |
| `hallux/agents.py`, `hallux/machine.py` | The machine makes its `Jobs`; the caps and the budgets, and what fills them again; the jobs' sum; jobs end with a boot | 8 |
| `hallux/agents.py`, `hallux/agent.md` (new), `hallux/tools.py`, `hallux/machine.py`, `hallux/sandbox.py`, `pyproject.toml` | A job's session, its rules, its tools; the options both kinds of session share | 9 |
| `hallux/machine.py`, `hallux/tools.py`, `hallux/app.py`, `hallux/prompt_jobs.md` (new), `pyproject.toml` | `spawn` wired up, the two tools, the event at the shell, the table on a tick | 10 |
| `hallux/config.py`, `hallux/panel_tabs/config.py` | The six rows in the panel's Config tab | 10 |
| `hallux/machine.py`, `hallux/blockmode.py`, `hallux/terminal.py`, `hallux/script.py`, `hallux/prompt_jobs.md` | A job's end wakes a full-screen program | 11 |
| `hallux/statusbar.py`, `hallux/terminal.py`, `hallux/machine.py`, `hallux/script.py` | Jobs on the bar, `~$`, the total with the jobs, `@wait jobs` | 12 |
| `addons/music.py` | `agent()`, `compose`, the composer's prompt, the manual | 13 |
| `hallux/blockmode.py`, `hallux/terminal.py`, `hallux/script.py` | A form is put aside and put back | 14 |
| `hallux/protocol.py`, `hallux/machine.py`, `hallux/blockmode.py`, `hallux/tools.py`, `hallux/prompt.md`, `hallux/prompt_jobs.md` | The three tags, Ctrl-Z, `list_processes` on every machine | 15 |
| `hallux/panel_tabs/agents.py`, `hallux/panel_tabs/details.py` (new), `hallux/app.py` | The panel's two tabs | 16 |
| `hallux/agents.py` | What each job has been doing, the ended jobs, why an agent can't start | 7, 8, 9, 16 |
| `README.MD`, `docs/` | The settings, the `~`, the tabs, the old sketch in addons.md, the roadmap | 17 |
| `tests/test_jobdisk.py`, `tests/test_agents.py` | New | 4 to 9 |
| `tests/test_panel_jobs.py` | New | 16 |
| The other test files | More tests in each | 1 to 15 |

**The line numbers** in the steps are the code's of 2026-10-04. The config panel is built
first and moves them, so each reference also names what stands there.

---

## The steps

Each step can be merged by itself. A step needs the ones named beside it. "Panel" means a
step of the config panel's plan.

| Step | File | Needs | Status |
|---|---|---|---|
| 1. Whole-file writes | [01-whole-file-writes.md](01-whole-file-writes.md) | | Not built |
| 2. `check` | [02-check.md](02-check.md) | | Not built |
| 3. The six settings | [03-settings.md](03-settings.md) | Panel 1 | Not built |
| 4. The fenced disk | [04-fence.md](04-fence.md) | 1 | Not built |
| 5. The landing | [05-landing.md](05-landing.md) | 4 | Not built |
| 6. The declaration | [06-declaration.md](06-declaration.md) | | Not built |
| 7. The jobs | [07-jobs.md](07-jobs.md) | 3, 5, 6 | Not built |
| 8. The caps | [08-caps.md](08-caps.md) | 7, panel 3 | Not built |
| 9. A job's real session | [09-session.md](09-session.md) | 6, 7 | Not built |
| 10. The main agent's side | [10-main-agent.md](10-main-agent.md) | 8, 9, panel 5 | Not built |
| 11. A job's end in a full-screen program | [11-wake.md](11-wake.md) | 10, panel 3 and 7 | Not built |
| 12. The status bar and the costs | [12-bar.md](12-bar.md) | 10 | Not built |
| 13. The composer | [13-composer.md](13-composer.md) | 2, 11, 12 | Not built |
| 14. Keeping a screen | [14-kept-screens.md](14-kept-screens.md) | | Not built |
| 15. Job control | [15-job-control.md](15-job-control.md) | 10, 14 | Not built |
| 16. The panel's two tabs | [16-panel-tabs.md](16-panel-tabs.md) | 10, panel 5 to 7 | Not built |
| 17. The documentation and the live run | [17-live-run.md](17-live-run.md) | 13, 15, 16 | Not built |

Steps 1, 2 and 6 need nothing and can come in any order. Step 14 needs nothing of this plan,
but it changes the files the config panel changes, so it comes after the panel. Step 16 can
come any time after step 10. This table is the only place that holds the status.

---

## After the review

What the review of 2026-10-04 changed in the steps. The user accepted all of it.

| Step | What changed |
|---|---|
| 1 | What a user can notice is said. A folder that takes no new file falls back to writing in place. The helper takes bytes too |
| 2 | A check child doesn't load the player module at all. Every child is started with colours off |
| 3 | Two new kinds of value, a whole number and seconds. A budget per job larger than the budget for all jobs is refused. The panel's rows moved to step 10 |
| 4 | One lock. A copy goes by the file itself, and is bytes |
| 5 | Every place is checked before anything is written |
| 6 | A `spawn` works for one call. The effort names move, so that two files don't import each other. A hint is compared by `==` |
| 7 | It needs step 6. What `Jobs` is given, and when it learns the event loop. The rules for a kill against a natural end. A job carries its limits. Which argument is the file in `tool` |
| 8 | The machine makes its `Jobs` here, and jobs end with a boot here. The jobs' dollars have a sum of their own. A reboot fills the jobs' budget |
| 9 | "Well" means no error in the result. No fallback model. A stop before the session is open. A job's tools have a builder of their own |
| 10 | An event is told when its message has gone out. One question decides waking and taking. The table on a tick is escaped. The six rows of the panel. The log line for a capped effort |
| 11 | A job's end during an answer wakes too. A program with fields keeps what was typed, also when the wake fails |
| 12 | The total is two sums. A kill's pid on the bar. One timer. The scripted summary |
| 13 | Two places of the manual are reworded for a reader without `play` |
| 14 | It comes after the panel. The fake terminals get `kept_forms()` |
| 15 | A screen that was shown while written is taken back at a `<resume>`. The tool counts in two tests |
| 16 | A tab shows another tab through the host. What `watch()` holds of an idle agent |
| 17 | The README's "Safety and privacy" |

---

## Risks

- **Nobody has run a composer at high effort.** What it costs and how long it takes decide
  the budgets and the timeout. The first live run is in step 13, and the numbers are set
  again there.
- **With the default budgets a second job fits only while nothing was spent.** A running
  job counts with its full cap of $1.00 against $2.00 for all jobs. That is the design, and
  step 13 says whether $2.00 is the right number.
- **A second session may slow the first.** Both share the account's rate limits. The check
  for the design ran Haiku, where both were quick.
- **Three things about the SDK are still unknown,** and step 9 can't be built well without
  them. The check under "Before the build" is a few cents.
- **The fenced disk is a second way to reach files.** A mistake in it reaches the user's
  folder. It is built first, without a model, and its tests name every way out I could
  think of: `..`, a link, a folder that is replaced while the job runs, a name with a dot.
- **A `check` has 8 seconds from the start of its child.** A song that needs all 8 to
  render passes `play` and fails `check`. Step 2 measures how long the child takes to
  start.
- **The bar has to move while the prompt waits,** and that draws on the screen while the
  user types. Step 12 builds it, and the live run says whether it disturbs.
- **I can't see a real terminal, and I can't hear.** Kept screens, the bar and the composer's
  songs each end with something for the user to try.
- **This plan and the config panel's change the same files.** The panel comes first.
