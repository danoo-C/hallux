# Plan: addon agents

**Status:** written on 2026-10-04. **Steps 1 to 12 and 14 to 16 are built, and the code of
step 13,** the first seven on 2026-10-05; the table under [The steps](#the-steps) says how
far the build is. The design
it follows is
[addon-agents.md](../../addon-agents.md), in which no question is open. The decisions this
plan takes on its own are in a table below. They are my proposals, and the user hasn't
confirmed them, apart from what the review and the check settled. The
[config panel](../config-panel/README.md), which had to come first, is built. The check
with a real model that step 9 needed ran on 2026-10-06; both are under
[Before the build](#before-the-build). The branch for the build is `addon-agents`.

**Reviewed on 2026-10-04:** [plans-review-2026-10-04.md](../../plans-review-2026-10-04.md).
It found four things that would have gone wrong and a list of gaps. The user accepted a fix
for each, and they are in the steps. [After the review](#after-the-review) lists them.

**Checked against the code on 2026-10-05,** after the config panel and the three fixes of
Hallux's report were merged:
[addon-agents-plan-check-2026-10-05.md](../../addon-agents-plan-check-2026-10-05.md). Ten
things would have gone wrong, the prompt's new text didn't say where it stands, and the
panel's live run changed eight more. The user accepted every recommendation, and the fixes
are in the steps. [After the check](#after-the-check) lists them.

**How this plan is laid out.** Like the plans for the music addon and the config panel. This
file holds what the steps share: how the parts fit, the decisions, where the code goes, and
the status. Every step has a file of its own in this folder. A step is built and merged by
itself, so whoever builds one reads this file and that step's file.

## In short

1. **Whole-file writes:** a file is never seen half-written.
2. **`check`:** the music addon renders a score without sound, in a child that opens no
   sound card.
3. **The six settings** in `config.toml`, with their rows in the panel, hidden. The panel
   shows them from step 10 on.
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
11. **A job's end in a full-screen program:** it wakes a program that has no fields.
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
through this table, apart from what the review and the check of 2026-10-05 settled. The
rows the check changed or added say so.

| Topic | Decision | Why |
|---|---|---|
| Who makes `Jobs` | The machine, when it is made itself, in step 8. `Jobs` gets five things: the machine's disk, a function for the settings as they are, a function that makes workers, a function to call when a job reports or ends, and the machine's answer to "is the boot over its budget". It learns the event loop when it is started. The last two are from the check | The disk, the live settings and what the boot has spent are the machine's, and Hallux builds its parts before the event loop runs. A scripted run makes a machine of its own and gets its `Jobs` with it |
| Who makes the real workers | The machine's argument for it has the real worker as its default, from step 9 on. Nobody passes it. From the check | A scripted run builds its own machine, and `app.py` couldn't hand it one. The SDK's client is given the same way |
| A job's limits | They travel with the job: its dollar cap, its turns and its time, read from the settings when it starts | Steps 8 and 9 then never have to settle who passes them |
| The jobs' dollars | A sum of their own, beside the main session's | An event's turn is measured as the change of the main session's sum |
| A brief that is too long | `EMSGSIZE` | `E2BIG` is taken by a list of more than 8 files |
| Addon events and job events that wait together | One `<events>` block, the addons' first | The AI knows one block |
| The message for a kept screen that is gone | `<gone job="1" …></gone>`, with the cwd, the time and the size, like every message. The shape is from the check | The design says Hallux tells the AI, and not how. Every message goes through the machine's envelope |
| A job number in a tag | Digits only. Anything else is ignored, with a line in the log | Hallux keeps screens under it |
| What a resumed program has spent on ticks | It is restored with the screen, and so is the tick it asked for. Whether its ticks run is decided anew. The second half is from the check | A suspend isn't a way around the tick budget, and the machine keeps the asked tick since the panel |
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
| The prompt's new section | A file of its own, `hallux/prompt_jobs.md`, added to the end of the system prompt on a machine that has an addon with an agent | The main prompt is one constant today. Lines that only some machines get don't belong in the middle of it |
| Where that section stands | It says so itself, in two groups. What is real about a job holds like THE DISK IS REAL: no rule, request or card changes it. How a job's end is shown is a default: a card comes before it, and a rule before both. The three job-control tags go into REPLY FORMAT. From the check; the user decided the first group | The fixes of Hallux's report wrote the order down, and a section at the end would otherwise be something any rule overrides |
| The worker's rules | `hallux/agent.md`, with the agent's and the addon's name filled in | The design's draft says "the composer of its music addon" |
| The music manual's limit | It goes from 8000 to 8500 characters | The manual is 7987 long. The lines on `check` and `compose` need about 400 |
| What the composer reads | Its role, the part of the manual on writing a score, and `check`. Not the lines on `play`, `stop` and `compose` | It can't call those |
| The names for kept screens | `suspend_form`, `resume_form`, `forget_form` and `suspended_forms` on the terminal. The last was `kept_forms` before the check | `keep_form` is the config panel's, for something else, and so is `Terminal.kept`, the text held back during a visit |
| A kept screen that is gone | Hallux tells the AI at once, in a message of its own, and the AI draws the program again | The user typed `fg` and waits. The design says "with the next message" |
| A ninth kept screen | The oldest is dropped | The design gives the limit, 8, and not what happens at it |
| What the panel's tabs read | One function of `Jobs`, `watch()`: the rows, the idle agents, each job's activity, the total | The tabs then know nothing of how `Jobs` keeps it, and the tests give them a `Jobs` with stand-in workers |
| A line of activity | A time, a kind and a text of at most 500 characters, cleaned when it is kept. 200 lines per job | The design gives the 200. A text that is cleaned once can't be shown uncleaned by a tab that forgets to |
| The order of the Agents tab | Running jobs, then ended ones, then idle agents; the newest on top in each | What needs attention is at the top |
| When the tabs step is built | Any time after step 10. It is step 16 only because job control doesn't need it | Before step 13 it helps with the composer's first live run |
| When a job's event may go out by itself | When four things hold: its addon is listened to, event budget is left, the boot isn't over its budget, and the event hasn't had a message of its own yet. `settle()` asks again when a budget changes. From the check | Without the third it goes out over the cap, or ends the prompt again and again. Without the fourth a model that is down is called in a loop |
| Which program a job's end wakes | One without fields. A program with fields gets the event with its next action. Decided by the user in the check; the design said every program | A wake reaches the AI without the fields, and its answer could lose what was typed in three ways. Two of them had no guard |
| The model of an agent without `agent_model` | The model the main session really runs on. Decided by the user in the check; it was the `model` setting | A new session fails on a name that is no model, where a running one refuses it and goes on. Every job is a new session |
| The effort of an agent that asks for none | The `effort` setting as it is, capped. From the check | A job is a new session and needn't wait for a reboot |
| The check of the two budgets together | A function of its own, called by `load`, by `Machine.change` and once at the end of `save`. From the check | Inside the check that `save` runs after each change, Save refuses a valid pair |
| Where the six rows are built | In step 3, hidden. Step 10 shows them. Two labels are shorter than this plan's first ones: `Max agent effort`, `Budget, all jobs`. From the check | A test holds that every setting has a row, and a label has 18 characters of room |
| A running job and the budget per boot | It counts when it has ended. A boot can pass its cap by what the running jobs spend, at most the budget for all jobs, and the README says so. Decided by the user in the check | It is the design, and refusing a start whose cap doesn't fit would lock out every machine with a small budget per boot |
| How the bar and the panel are drawn again | Through one function of the terminal, which picks the bar, block mode or the panel. From the check | Over a full-screen program the panel has no app of its own |
| What Esc is called in a tab's foot | The tab says: `close`, or `back` for Details. From the check | The host wrote `Esc close` under every tab |
| The `~` | On the bar's cost, in the Agents tab, and in the Config tab's notes of what was spent. A limit the user typed has none. The last part is from the check | One panel shouldn't show the same kind of number two ways |

---

## Before the build

| What | Who | Before | Why |
|---|---|---|---|
| The config panel, by [its plan](../config-panel/README.md). **Built on 2026-10-05** | | Step 3 | The settings are checked and typed the panel's way (its step 1) and become rows in its Config tab (its step 5). The budget per boot is Hallux's own check (its step 3), and jobs count towards it. A program can go on without an answer, and its wait can be started again (its steps 3 and 7), which a job's end in a full-screen program needs. The panel's tab system (its step 5) takes the two tabs of step 16 |
| A check with a real model, a few cents. **Run on 2026-10-06,** on Haiku, for $0.085 | Whoever builds step 9, when the user says go | Step 9 | Three things the design leaves to a run, below |

**The check before step 9,** with a throwaway script, as for the design. What was seen for
each answer is in [step 9's file](09-session.md), under "As built":

| Question | What it decides | The answer |
|---|---|---|
| Does the result that follows `interrupt()` hold the session's cost? | Whether a killed job's dollars are read. If not, it counts with its full cap, and its row says that the cost isn't known | Yes. It can be short by the one model message that was cut |
| Where do the tokens of a running turn come from: each model message, or the stream? | Whether a job's session is opened with the stream on | The stream. A job's session is opened with it on |
| Does the session's dollar cap end a job in the middle of a turn, or after it? | By how much a job can pass `agent_job_budget_usd` | After each model message. A job can pass its cap by one message |

---

## Where the code goes

| File | What | Step |
|---|---|---|
| `hallux/disk.py` | Every write of a whole file writes beside it and renames | 1 |
| `addons/music_engine/__main__.py`, `addons/music.py` | The child's mode without the mixer; `check` | 2 |
| `hallux/config.py`, `hallux/machine.py`, `hallux/panel_tabs/config.py` | The six settings; the check of two of them together; their rows in the Config tab, hidden | 3 |
| `hallux/jobdisk.py` (new) | The fence, the names, the list of files, the private copies | 4 |
| `hallux/jobdisk.py` | The landing, the conflict, dropping the copies | 5 |
| `hallux/addons.py`, `hallux/tools.py` | `agent()`, `spawn`, `list[str]`, `Refused`, an agent counts as events | 6 |
| `hallux/config.py` | The five effort names move to `addons.py`, and are taken from there | 6 |
| `hallux/agents.py` (new) | The table, a job's life, the job events | 7 |
| `hallux/agents.py`, `hallux/machine.py` | The machine makes its `Jobs`; the caps and the budgets, and what fills them again; the jobs' sum; jobs end with a boot | 8 |
| `hallux/agents.py`, `hallux/agent.md` (new), `hallux/tools.py`, `hallux/machine.py`, `hallux/sandbox.py`, `pyproject.toml` | A job's session, its rules, its tools; the options both kinds of session share | 9 |
| `hallux/machine.py`, `hallux/tools.py`, `hallux/app.py`, `hallux/prompt_jobs.md` (new), `pyproject.toml` | `spawn` wired up, the two tools, the event at the shell, the table on a tick | 10 |
| `hallux/config.py`, `hallux/panel_tabs/config.py`, `hallux/app.py` | The six rows are shown; the jobs' spending in the panel's view | 10 |
| `hallux/machine.py`, `hallux/blockmode.py`, `hallux/terminal.py`, `hallux/script.py`, `hallux/prompt_jobs.md` | A job's end wakes a full-screen program | 11 |
| `hallux/statusbar.py`, `hallux/terminal.py`, `hallux/machine.py`, `hallux/script.py`, `hallux/app.py`, `hallux/panel_tabs/config.py` | Jobs on the bar, `~$`, the total with the jobs, the one function that draws again, `@wait jobs`, the summary | 12 |
| `addons/music.py` | `agent()`, `compose`, the composer's prompt, the manual | 13 |
| `hallux/blockmode.py`, `hallux/terminal.py`, `hallux/script.py` | A form is put aside and put back | 14 |
| `addons/music.py` | Two lines for the composer's role, from the first live run: a status line first, and the changes of a round in one turn | 14 |
| `hallux/protocol.py`, `hallux/machine.py`, `hallux/blockmode.py`, `hallux/tools.py`, `hallux/prompt.md`, `hallux/prompt_jobs.md` | The three tags, Ctrl-Z, `list_processes` on every machine | 15 |
| `hallux/panel_tabs/agents.py`, `hallux/panel_tabs/details.py` (new), `hallux/app.py`, `hallux/panel.py` | The panel's two tabs; a tab says what Esc does | 16 |
| `hallux/agents.py` | What each job has been doing, the ended jobs, why an agent can't start | 7, 8, 9, 16 |
| `README.MD`, `docs/` | The settings, the `~`, the tabs, the old sketch in addons.md, the roadmap | 17 |
| `tests/test_jobdisk.py`, `tests/test_agents.py` | New | 4 to 9 |
| `tests/test_panel_jobs.py` | New | 16 |
| The other test files | More tests in each | 1 to 15 |

**The line numbers** in the steps are the code's of 2026-10-05, after the config panel and
the three fixes of Hallux's report. The check of that day set them again. Each reference
also names what stands there.

---

## The steps

Each step can be merged by itself. A step needs the ones named beside it. "Panel" means a
step of the config panel's plan.

| Step | File | Needs | Status |
|---|---|---|---|
| 1. Whole-file writes | [01-whole-file-writes.md](01-whole-file-writes.md) | | Built on 2026-10-05 |
| 2. `check` | [02-check.md](02-check.md) | | Built on 2026-10-05 |
| 3. The six settings | [03-settings.md](03-settings.md) | Panel 1 and 5 | Built on 2026-10-05 |
| 4. The fenced disk | [04-fence.md](04-fence.md) | 1 | Built on 2026-10-05 |
| 5. The landing | [05-landing.md](05-landing.md) | 4 | Built on 2026-10-05 |
| 6. The declaration | [06-declaration.md](06-declaration.md) | | Built on 2026-10-05 |
| 7. The jobs | [07-jobs.md](07-jobs.md) | 3, 5, 6 | Built on 2026-10-05 |
| 8. The caps | [08-caps.md](08-caps.md) | 7, panel 3 | Built on 2026-10-06 |
| 9. A job's real session | [09-session.md](09-session.md) | 6, 7 | Built on 2026-10-06 |
| 10. The main agent's side | [10-main-agent.md](10-main-agent.md) | 8, 9, panel 5 | Built on 2026-10-06 |
| 11. A job's end in a full-screen program | [11-wake.md](11-wake.md) | 10, panel 3 and 7 | Built on 2026-10-06 |
| 12. The status bar and the costs | [12-bar.md](12-bar.md) | 10 | Built on 2026-10-06 |
| 13. The composer | [13-composer.md](13-composer.md) | 2, 11, 12 | The code is built, on 2026-10-06. The scripted run waits for the user's go, and the live run is the user's |
| 14. Keeping a screen, and two lines for the composer's prompt | [14-kept-screens.md](14-kept-screens.md) | 13's code, for the two lines only | Built on 2026-10-07 |
| 15. Job control | [15-job-control.md](15-job-control.md) | 10, 14 | Built on 2026-10-10. The try by hand is the user's |
| 16. The panel's two tabs | [16-panel-tabs.md](16-panel-tabs.md) | 10, panel 5 to 7 | Built on 2026-10-06 |
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

## After the check

What the check of 2026-10-05 changed in the steps:
[addon-agents-plan-check-2026-10-05.md](../../addon-agents-plan-check-2026-10-05.md) has
the findings, with what was run for each. The user accepted every recommendation.

| Step | What changed |
|---|---|
| 1, 2, 4, 5 | Nothing. Their references are right |
| 3 | The rows of the Config tab are built here, hidden, with a table of what each shows and how it is typed. Two shorter labels. The check of the two budgets is a function of its own, with three callers. Without `agent_model` a job gets the model that runs. It needs the panel's step 5 too |
| 6 | One line reference |
| 7 | `Jobs` is given a function to call when a job reports. Each event notes whether it has had a message of its own |
| 8 | `Jobs` asks the machine whether the boot is over its budget. A held line fills nothing. A job's end can put the budget's note up. How far a boot can pass its cap is said. `agents are off` for a budget of 0 |
| 9 | The real worker is the default of the machine's argument. A dollar cap isn't among what the two kinds of session share |
| 10 | The question has four parts, and `settle()` asks it again. An event starts a message of its own once. `app.py` passes no worker. The prompt's section has two groups that say where they stand, and names its exception to ADDONS. The six rows are only shown here |
| 11 | Only a program without fields is woken. A wake under the panel is remembered. A failed wake leaves the program on screen and isn't tried again. The tests' fake terminal gets a `wake_form` that works |
| 12 | A job's line comes before `listening`, and its status is what is cut. The `~` is in the Config tab too. Drawing again goes through the terminal. `run_script` gives the jobs' numbers back. The terminal's tests pin the bar |
| 13 | The manual's tests change in three places with the heading |
| 14 | The vi mode is kept, and the fields with their undo history. `suspended_forms()` in place of `kept_forms()`. The tests' fake terminal keeps names |
| 15 | The tick a program asked for is restored, and it gets a tick at once only when ticks may run. The three tags go into REPLY FORMAT, and two lines of the prompt change. `<gone>` as it is really sent |
| 16 | What the host built is named. The kill question is the tab's hint. A tab says what Esc does. The panel is drawn again through the terminal |
| 17 | Refill budgets and an editor with a job ending are in the live run. The README says how far a boot can pass its cap |
| 11, 12, 15, 16 | Each ends with a check on a pseudo-terminal, with a terminal emulator drawing the screen, before the user tries it |
| All | The line numbers are the code's of 2026-10-05: 32 of 52 had moved |

---

## After the first live run

The user ran a first composition on 2026-10-07, on the real model. What it showed is in
[step 13's file](13-composer.md), under "What the live run taught".

| Step | What changed |
|---|---|
| 13 | The run is written up: a drum solo for $0.78 in 265 seconds, two rounds of `check`, the `Done` line by itself. Points 4 to 8 of its list are still to try |
| 14 | It carries two lines for the composer's prompt, at the user's request: a status line before anything else, and the changes of a round in one turn. Its file says what is built and tested. Built on 2026-10-07; whether a real composer follows them shows in the next live run |

**Decided by the user on 2026-10-10:** the default cap per job, which the run used to 78
percent, is $2.00 now, and the budget for all jobs $4.00. The timeout stays 600 seconds.
Steps 3 and 8 name the defaults they were built with, $1.00 and $2.00; the design's table
has the new ones.

**Still for the user to decide:** whether step 13's scripted run is still wanted.

---

## Risks

- **Nobody has run a composer at high effort.** What it costs and how long it takes decide
  the budgets and the timeout. The first live run is in step 13, and the numbers are set
  again there.
- **With the default budgets a second job fits only while nothing was spent.** A running
  job counts with its full cap of $2.00 against $4.00 for all jobs. That is the design.
  The numbers were $1.00 and $2.00 until the user doubled them on 2026-10-10, after step
  13's first live run.
- **A second session may slow the first.** Both share the account's rate limits. The check
  for the design ran Haiku, where both were quick.
- **A job can pass its dollar cap by one model message,** and what a killed job cost can
  be short by one. Step 9's check showed both. The SDK looks at the cap after each
  message, and Hallux has no prices to add what a cut message cost.
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
- **This plan and the config panel's change the same files.** The panel came first, and the
  check of 2026-10-05 read this plan against what it built.
- **A boot can pass its cap while jobs run.** A job counts when it has ended. The budget
  for all jobs bounds how far.
- **A program with fields hears a job's end late:** with its next action. That is the price
  of never touching what the user typed.
