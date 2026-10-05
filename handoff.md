# Handoff: addon agents, after step 8

**Written on 2026-10-06,** at the end of the session that checked the plan and built steps
1 to 8. It is a working note for picking the work up again, not a place that holds status.
The status is in the table of the [plan's README](docs/plans/addon-agents/README.md), and
each step's file says under "As built" what was decided while building it. Delete this file
before the pull request if you don't want it there.

## Where things stand

- **Branch:** `addon-agents`, made from `main`. 13 commits and this note, not pushed. The
  working tree is clean.
- **Built:** the check of the plan, and steps 1 to 8 of 17.
- **Tests:** 1383, all pass. Run them with
  `env -u FORCE_COLOR .venv/bin/python -m pytest -q`. With `FORCE_COLOR` set, one fails:
  the window addon's, which isn't in this plan.
- **No model call was made so far,** and nothing built so far draws on a terminal.
- **No machine can start a job yet.** The machine has its `Jobs` since step 8, and nothing
  reaches it before step 10.

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

## What comes next: step 9, and it starts with a paid check

Step 9 is [a job's real session](docs/plans/addon-agents/09-session.md): a Claude session
of its own for each job. **Before it, a throwaway script has to run with a real model, and
that needs the user's go.** It was asked for at the end of the last session and not
answered yet.

The three questions, and what each answer decides:

| Question | If yes | If no |
|---|---|---|
| Does the result that follows `interrupt()` hold the session's cost? | A killed job's dollars are read from it | A killed job counts with its full cap for good, and its row says `unknown`. The code for that is built and tested already |
| Do the tokens of a running turn come with each model message? | They are taken from there | The session is opened with the stream on, and they are counted from it |
| Does the session's dollar cap end a job in the middle of a turn? | `agent_job_budget_usd` is close to exact | A job can pass it by one turn, and the README says so |

**My proposal for the check:** run it on Haiku, with a cap of $0.25 on the whole check. The
panel's check was planned at a few cents and cost $0.22, because one answer ran on Opus.

**How I would write the script,** so the next session needn't work it out again. One
session per question, each with Hallux's own kind of options: no built-in tools, one
in-process tool, `setting_sources=[]`.

1. **The cost after `interrupt()`:** a tool that sleeps a few seconds. Call
   `client.interrupt()` while the model is inside it, then read on to the `ResultMessage`.
   Look at `total_cost_usd`, `usage`, `subtype`, `is_error` and `terminal_reason`. The plan
   expects `aborted_tools` or `aborted_streaming` there.
2. **The tokens:** a task of three or four tool calls. For every `AssistantMessage`, print
   its `usage`. Run it once with `include_partial_messages` off and once on, and compare
   with the `usage` of the result.
3. **The dollar cap:** `max_budget_usd` of a fraction of a cent and a task of several
   turns. See whether the result is `error_max_budget_usd`, after how many turns, and how
   far `total_cost_usd` went over.

The answers go into step 9's file under "As built". No file of the project changes for the
check.

**Then step 9 itself.** What it has to build is in its file. What it builds on, as it was
really built:

| Where | What is there |
|---|---|
| `hallux/agents.py` | `Jobs`, `Job`, `Outcome(ok, why, cost_usd, tokens, turns, last)`, `Limits(budget_usd, turns, seconds)`, and `Worker`: `run()` comes back with an `Outcome`, `stop()` only asks. A worker reports through its `Job`: `set_status`, `tool_began(name, args)`, `tool_ended()`, `tokens_so_far(n)`. Step 9 adds `says` and a tool's short result |
| `hallux/machine.py` | `Machine(…, worker_factory=NoWorker)`. Step 9 makes the real worker the default, so neither `app.py` nor a scripted run passes one |
| `hallux/config.py` | `agent_model(hardware, running)` and `agent_effort(hardware, asked, model)` |
| `hallux/jobdisk.py` | `JobDisk`, with `list_dir`, `read_file`, `write_file(path, content, append)`, `edit_file`. A job's four file tools are built on these |
| `hallux/addons.py`, `hallux/tools.py` | `addon.agent` holds the declaration. `call(function, args, disk, spawn)` takes a `JobDisk` as the disk as it is |
| The tests | `StandIn` and `World` in `tests/test_agents.py`; `Bench`, `PatientTerminal` and `Pause` in `tests/test_machine.py`. The machine's tests have a fake client that hands out scripted messages; step 9's tests need one like it for a job's session |

## After step 9

In the order of [the build order](docs/plans/build-order.md): 10, 11, 12, 16, 13, 14, 15,
17. Steps 11, 12, 15 and 16 each end with a check on a pseudo-terminal before the user
tries them. Step 13 has the scripted run and the first live run; step 17 has the last one.

## Open, for the user

| | What | My recommendation |
|---|---|---|
| 1 | The go for the paid check | Go, on Haiku, capped at $0.25 |
| 2 | `failed` with `why: disk`, when a write fails in the middle of a landing. Built and tested as a proposal; the design's tables don't have it. Asked twice, not answered | Take it. I then add it to the design |
| 3 | `check` got `loop` on an "okay" that may have meant something else | Keep it |
| 4 | Three things in the wording of the prompt's new section, reported in the chat on 2026-10-05: it doesn't say that the message goes on the screen, a rule or a card can switch it off, and its list of sources leaves out the prompt and the rules | Yours to decide. It is committed as you wrote it |
| 5 | Nothing is pushed | The push and the pull request are yours |

## How the work is done here

These are the user's rules, from the build order. They held all session.

- **One step at a time, and only when asked.** The rhythm was: "commit, and continue". The
  finished step is committed, then the next one is built and left uncommitted.
- **Before a step:** read the build order, the plan's README and the step's file.
- **A step is done** when its tests pass with all the old ones, its "Done when" holds, the
  README's table says so, and its file has an "As built".
- **A paid check waits for the user's go.**
- **Say what could not be checked,** and what was decided beyond the plan.

Three things this session learned the hard way:

- **Add files to a commit by name.** The user edits files in the same working tree while a
  step is built: `hallux/prompt.md` changed that way. Never `git add -A`.
- **A built step moves lines.** The later steps cite `file:line`. After a step that changes
  `machine.py`, `addons.py`, `disk.py` or `prompt.md`, set the references in the unbuilt
  steps again, and the design's.
- **Stay in the repo's root in the shell.** A `cd` into `addons/` made the sandbox leave
  placeholders there, `addons/.claude/` and `addons/.mcp.json`. They are untracked, like
  the ones in the root, and nobody's work.

## Where to read more

| | |
|---|---|
| The order of the steps, and the rules | [docs/plans/build-order.md](docs/plans/build-order.md) |
| The plan, its decisions, its status | [docs/plans/addon-agents/README.md](docs/plans/addon-agents/README.md) |
| The design | [docs/addon-agents.md](docs/addon-agents.md) |
| What the check of the plan found | [docs/addon-agents-plan-check-2026-10-05.md](docs/addon-agents-plan-check-2026-10-05.md) |
| The progress after step 7, with what each step decided | [docs/addon-agents-progress-2026-10-05.md](docs/addon-agents-progress-2026-10-05.md) |

## To pick up

Say, for example: "Read handoff.md. Go for the check of step 9, on Haiku." Or, to wait with
the check: "Read handoff.md. Build what of step 9 doesn't need the check." That second way
is possible for the job's tools, its rules and its first message; the part that reads the
session's messages waits for the answers.
