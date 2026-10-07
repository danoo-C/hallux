# Handoff: addon agents, after step 14

**Written on 2026-10-07,** at the end of the session that ran the paid check and built
steps 9 to 12, 14 and 16, and the code of step 13. It replaces the handoff written after
step 8. It is a working note for picking the work up again, not a place that holds status.
The status is in the table of the [plan's README](docs/plans/addon-agents/README.md), and
each step's file says under "As built" what was decided while building it. Delete this
file before the pull request if you don't want it there.

## Where things stand

- **Branch:** `addon-agents`, made from `main`.
- **Built:** the check of the plan, steps 1 to 12, 14 and 16, and the code of step 13.
  Step 13 itself isn't done: the user ran a first composition, and five points of its
  live run are still to try.
- **Everything is committed,** this note too. The working tree is clean.
- **Pushed up to step 16:** the user pushed on 2026-10-07, and `origin/addon-agents` is at
  `51f6392`. **Not pushed:** three commits: the code of step 13 (`d530812`), step 14
  (`25defe1`), and this note's.
- **Tests:** 1543, all pass. Run them with
  `env -u FORCE_COLOR .venv/bin/python -m pytest -q`. With `FORCE_COLOR` set, one fails:
  the window addon's, which isn't in this plan.
- **My own model calls so far: $0.108,** all on Haiku, all in step 9: $0.085 for the check
  and $0.023 for the step's own two real jobs. Nothing I built since has made one.
- **A user can start a job now.** The music addon has its agent, the composer, and
  `compose` starts it. The user ran it for real on 2026-10-07, on Opus: it works. That run
  cost $1.13, of which the composition was $0.78.

| | What | Commit |
|---|---|---|
| Part 2 | The plan checked against the code; its fixes written | `5dda488`, `5d541e6` |
| 1 | Whole-file writes | `518eb77` |
| 2 | `check`, and `loop` for it | `5c02910`, `4c11deb` |
| 3 | The six settings, their rows in the Config tab hidden | `a93a9fe` |
| 4 | The fenced disk, `hallux/jobdisk.py` | `24e89c4` |
| 5 | The landing | `39ef07e` |
| 6 | The declaration: `agent()`, `spawn`, `list[str]` | `15c4c29` |
| 7 | The jobs, `hallux/agents.py`, with stand-in workers | `f12e952` |
| | The user's own section in the prompt, with `prompt.bak.md` | `67592cf` |
| 8 | The caps; the machine has its `Jobs` | `916be8e` |
| | The write-up of the progress after step 7 | `83d27b7` |
| 9 | A job's real session, after the paid check | `faed39f` |
| 10 | The main agent's side | `ebf723b` |
| 11 | A job's end wakes a full-screen program | `fa87065` |
| 12 | The status bar and the costs | `50a4ea9` |
| 16 | The panel's Agents and Details tabs | `51f6392` |
| 13 | The composer: its code, and the write-up of the user's first live run | `d530812` |
| 14 | Keeping a screen, and two lines for the composer's prompt | `25defe1` |

## What the paid check answered

All three questions, for $0.085. What was seen for each is in
[step 9's file](docs/plans/addon-agents/09-session.md), under "As built".

| Question | Answer |
|---|---|
| Does the result after `interrupt()` hold the cost? | Yes. It can be short by the one model message the kill cut |
| Do the tokens come with each model message? | No, with the stream. A job's session is opened with it on |
| Does the dollar cap end a job in the middle of a turn? | No, after each model message. A job can pass its cap by one message |

## What comes next: step 15

[Job control](docs/plans/addon-agents/15-job-control.md): `<suspend>`, `<resume>` and
`<forget>` in the AI's answers, Ctrl-Z in a full-screen program, and `jobs`, `fg` and `bg`
at the shell. It is what calls the four things step 14 built. `list_processes` then
exists on every machine and lists the kept screens too.

- **No paid check comes before it.**
- **It ends with a check on a pseudo-terminal** before the user tries it.
- **It changes the main prompt** (`hallux/prompt.md`, REPLY FORMAT), which the user edits
  too: look at the working tree before touching it, and add files to the commit by name.

**What it builds on, as step 14 really built it:**

| Where | What is there |
|---|---|
| `hallux/terminal.py` | `suspend_form(job)` and `resume_form(job)`, both awaited; `forget_form(job)`, and without a number all of them; `suspended_forms()`, the numbers, oldest first |
| `hallux/blockmode.py` | `suspend(name)`, `resume(name)`, `forget(name)`, and `suspended`. A resume takes the place of whatever is on screen: who wants that kept suspends it first. At most 8 are kept. A name given again is the newest |
| `hallux/machine.py` | The four are in the `Terminal` protocol. `block_mode()` handles the action `wake`; `leave_block_mode()` ends a program; `send()` carries waiting job events in front of a message |
| `hallux/script.py` | The scripted terminal's four do nothing: its `resume_form` says no |
| `tests/test_machine.py` | The fake terminal's four work: they keep the program under its number and show it again |
| The scratchpad's screen check | A small script played the machine for step 14: an editor, Ctrl-Z, thirty lines at the shell, `fg`. Step 15's check is that with the real machine. The script was a throwaway; step 14's "As built" says what the screen showed |

## The rest of step 13

Step 13's code is built and committed. Its runs:

| Part | Who | State |
|---|---|---|
| The scripted run | Me, when the user says go. It costs money | Not run. Its three proofs are in the log of the user's live run. Whether it is still wanted is the user's to say |
| The first live run | The user | **A first run on 2026-10-07:** a drum solo for $0.78 in 265 seconds, written up in the step's file. Points 4 to 8 of its list are still to try |
| The two lines for the composer's prompt | Me | Built with step 14. Whether a real composer follows them shows in the next composition: in the panel's Details tab, the first line should be a `status` within seconds, and the edits of a round should share one time |

## After step 15

Step 17, the documentation and the last live run. It has two lines for the README from
step 9's check, noted in its file: a job can pass its cap by one model message, and a
killed job's cost can be short by one.

**What only a live run can show,** carried from the steps before:

- what a real model answers to a wake in a full-screen program: a patch, or bash's `Done`
  line, which would end the program (step 11);
- whether the bar's redraw once a second disturbs typing (step 12);
- how the tabs look on a real terminal, and the mouse in them (step 16);
- whether the composer sets a status line first, and makes its changes in one turn
  (step 14).

## Open, for the user

| | What | My recommendation |
|---|---|---|
| 1 | Three commits aren't pushed: the code of step 13, step 14, and this note's | The push and the pull request are yours |
| 2 | The go for step 15 | Say "continue" |
| 3 | Whether step 13's scripted run is still wanted. The user's live run has shown its three proofs on the real model | Drop it, or run it on Haiku for `@wait jobs` alone, the job capped at $0.25 and the boot at $0.50 |
| 4 | The default cap per job. The first composition used $0.78 of its $1.00 | $2.00 a job and $4.00 for all jobs; the timeout stays 600 seconds |
| 5 | The rest of step 13's live run: points 4 to 8 of its list, and a look at whether the composer now sets a status line first and makes its changes in one turn | Yours, whenever you like. The step's file has the points |
| 6 | `failed` with `why: disk`, when a write fails in the middle of a landing. Built and tested as a proposal; the design's tables don't have it. Asked twice, not answered | Take it. I then add it to the design |
| 7 | `check` got `loop` on an "okay" that may have meant something else | Keep it |
| 8 | Three things in the wording of the prompt's own new section, reported on 2026-10-05: it doesn't say that the message goes on the screen, a rule or a card can switch it off, and its list of sources leaves out the prompt and the rules | Yours to decide. It is committed as you wrote it |
| 9 | What steps 9 to 14 and 16 decided beyond the plan, below | Read the list. Say so if one is unwanted |

**Decided beyond the plan in steps 9 to 14 and 16.** Each is in its step's "As built":

- **A job's one message names its folder,** as well as the files it may change.
- **Every session is closed in the background.** A job's end doesn't wait for Claude Code
  to go; the end of a boot does, about a second.
- **A job's dollars are rounded to a hundredth of a cent in its row.** The sums keep the
  number as it came.
- **`set_status` shows in a job's activity as its status line only,** not also as a tool
  call.
- **The larger token count stands at a job's end,** the worker's own sum or the result's.
  The plan said the result's replaces it; after a cap or a kill the result's is short.
- **A tick's body is `{"jobs": [...]}`,** the shape `list_processes` returns, not the bare
  rows.
- **An `<events>` message carries every job event that waits,** also one that couldn't
  have gone out by itself.
- **The prompt's section says what an event's fields mean:** `files`, `conflict`, `why`.
- **A wake that reaches a program with fields is never sent,** whoever asked for it. Block
  mode refuses such a wake, and the machine looks at its fields once more.
- **The addons' own events aren't taken into a wake.** They wait until the program ends,
  as before.
- **`@wait jobs` can be written without seconds,** and then waits as long as a job runs.
- **After a `@wait jobs` the machine looks for what ended,** so a listening AI hears of the
  job by itself before the script's next line.
- **A wait is a record in a script's transcript, and no round trip in its summary.** The
  summary keeps its plain `$`.
- **The Agents tab's columns stand close together.** On 80 columns the status has 21
  characters, and `can't start: jobs budget used` is cut there; the Details tab has it
  whole.
- **The Details tab wraps a long line** under its own text, and says `waiting in check`
  with the call's name alone.
- **The machine tells the terminal at every report of a job,** so the Details tab shows a
  new line at once and not at the next beat.
- **The manual's lines on `compose` are four,** shorter than the plan's list: the main
  prompt's section on jobs says the rest.
- **The composer's role says two things more than the plan's draft:** a score it was given
  is changed in its own file, and it uses nothing of the format that its manual doesn't
  name.
- **A resume takes the place of whatever is on screen.** It doesn't keep that program; who
  wants it kept suspends it first. Step 15 decides when.
- **`forget_form()` without a number drops every kept screen,** for the end of a boot.
- **Step 14 got a check on a pseudo-terminal,** though the plan asks for none there: it
  changes what reaches the screen.

**One thing a run couldn't settle:** what a cut model message costs. Two kills disagreed.
One left the cut message out of the cost, the other seems to have counted it. Both stay
inside "short by one message at most".

## How the work is done here

These are the user's rules, from the build order. They held all session.

- **One step at a time, and only when asked.** The rhythm is "commit please and continue":
  the finished step is committed, then the next one is built and left uncommitted.
- **Before a step:** read the build order, the plan's README and the step's file.
- **A step is done** when its tests pass with all the old ones, its "Done when" holds, the
  README's table says so, and its file has an "As built".
- **A paid check waits for the user's go.**
- **Say what could not be checked,** and what was decided beyond the plan.

**What the sessions learned the hard way:**

- **Add files to a commit by name.** The user edits files in the same working tree while a
  step is built. Never `git add -A`.
- **A built step moves lines.** The unbuilt steps cite `file:line`. After a step, map each
  changed file's old lines to its new ones (Python's `difflib` on `git show HEAD:file`
  against the file) and set every reference in the unbuilt steps' files again. Do it
  before the commit, while `HEAD` is still the old code.
- **Stay in the repo's root in the shell.** A `cd` elsewhere makes the sandbox leave
  placeholders there. They are untracked, and nobody's work.
- **A run with a real model works from inside the sandbox,** with `api.anthropic.com`
  allowed for the command. The script drops the `CLAUDE*` variables of the session it is
  started from, names `claude-haiku-4-5` itself, and keeps a small ledger file so that
  several runs stay under one cap. Those scripts were throwaways and are gone.
- **A test with fakes never lets the event loop turn by itself.** A job's worker runs only
  while something really waits: `Pause`, `bench.settled()`, or a step in the fake model's
  answer that awaits.
- **Break the code to check new tests.** For step 10, eight wrong versions of the event
  handling were tried one at a time, and each had to fail a test. A wrong version that
  passes is a test that is missing: in step 14 a focus that wasn't kept passed, because
  every test had one field.
- **The files in `edit` are paths of the machine:** absolute, or relative to the shell's
  working directory, not to the job's folder. Step 13's `compose` passes them on.
- **For a screen check,** `pyte` goes into the scratchpad with `pip install --target`,
  never into the project's venv. The real `Terminal` runs in a pseudo-terminal, and its
  bytes are replayed through the emulator. Run it once with the new thing switched off
  too, to see that the check can fail.
- **The check has to answer like a real terminal.** prompt_toolkit asks for the cursor's
  position (`ESC[6n`) at a prompt. Unanswered, it prints a warning after two seconds and
  draws its prompt a row lower, which looks like a bug of Hallux's and isn't. The check
  answers from where the emulator has the cursor.

## Where the session's throwaways are

They are in the scratchpad of the session that wrote this note, a folder under `/tmp`. A
new session has another scratchpad, and `/tmp` may be emptied; nothing in the plan depends
on them. If the folder is still there, it saves writing them again:

`/tmp/claude-1000/-home-dano-IT-hallux/ddb8fcb7-9671-42dc-9f55-96b0fbf8c418/scratchpad/`

| What | Files |
|---|---|
| The screen checks of steps 11, 12, 14 and 16, each a script for the pseudo-terminal and one that runs inside it | `pty11.py`, `pty12.py`, `pty14.py`, `pty16.py`, and their `_child.py` |
| The terminal emulator they use | `pylib/`, with `pyte` |
| The world of the user's first composition, with its `hallux.log` and the song | `world-compose/`. Its budgets were raised in the panel and saved: $10 a job, $20 for all jobs |

What each check did and showed is in its step's "As built", and what the composition's log
showed is in step 13's file. Step 15's screen check can start from `pty14.py` and
`pty16.py`.

## Where to read more

| | |
|---|---|
| The order of the steps, and the rules | [docs/plans/build-order.md](docs/plans/build-order.md) |
| The plan, its decisions, its status | [docs/plans/addon-agents/README.md](docs/plans/addon-agents/README.md) |
| The design | [docs/addon-agents.md](docs/addon-agents.md) |
| The check's answers, and step 9 as built | [docs/plans/addon-agents/09-session.md](docs/plans/addon-agents/09-session.md) |
| Step 10 as built | [docs/plans/addon-agents/10-main-agent.md](docs/plans/addon-agents/10-main-agent.md) |
| Step 11 as built, with its screen check | [docs/plans/addon-agents/11-wake.md](docs/plans/addon-agents/11-wake.md) |
| Step 12 as built, with its screen check | [docs/plans/addon-agents/12-bar.md](docs/plans/addon-agents/12-bar.md) |
| Step 16 as built, with its screen check | [docs/plans/addon-agents/16-panel-tabs.md](docs/plans/addon-agents/16-panel-tabs.md) |
| Step 13: its code as built, and its two runs | [docs/plans/addon-agents/13-composer.md](docs/plans/addon-agents/13-composer.md) |
| Step 14 as built, with its screen check | [docs/plans/addon-agents/14-kept-screens.md](docs/plans/addon-agents/14-kept-screens.md) |
| What the check of the plan found | [docs/addon-agents-plan-check-2026-10-05.md](docs/addon-agents-plan-check-2026-10-05.md) |
| The progress after step 7 | [docs/addon-agents-progress-2026-10-05.md](docs/addon-agents-progress-2026-10-05.md) |

## To pick up

Say, for example: "Read handoff.md and continue." Nothing waits to be committed, so that
builds step 15, job control. The cap per job and the scripted run of step 13 wait for an
answer of their own.
