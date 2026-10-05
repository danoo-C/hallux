# Step 10: the main agent's side

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), sections 7,
8, 9 and 13

**Needs:** steps 8 and 9, and step 5 of the
[config panel's plan](../config-panel/README.md). **Changes:** `hallux/machine.py`,
`hallux/tools.py`, `hallux/app.py`, `hallux/config.py`, `hallux/panel_tabs/config.py`,
`pyproject.toml`, `tests/test_machine.py`, `tests/test_tools.py`, `tests/test_addons.py`,
`tests/test_panel_config.py`. **Makes:** `hallux/prompt_jobs.md`.

The machine has had its `Jobs` since step 8, and nothing could reach it. Here it is wired
up. From this step on, a machine with an addon that has an agent can start a job, read the
table, kill a job, and hear how a job ended. The music addon has no agent before step 13,
so until then only a fake addon in the tests does all of this.

## Build

**When Hallux starts,** `app.py`:

- gives the machine the function that makes real workers (step 9);
- has the copies swept away that a crash left (step 4), with a line in the log for each;
- writes a line to the log for each agent: the model and the effort it gets, and that its
  effort was capped when it asked for more (the helpers of step 3).

**`spawn` reaches the addons.** A function that takes `spawn` gets one that is tied to its
addon: it calls `Jobs.spawn` with the loaded addon in front.

**Two tools for the main agent,** on a machine that has an addon with an agent:

| Tool | What it does |
|---|---|
| `list_processes()` | `{"jobs": [...]}`, the rows of step 7 |
| `kill_process(pid)` | Ends that job. A pid that isn't in the table, or a job that has ended: `ESRCH` |

`addon_listen` is there when an addon has events or an agent, and takes both kinds.

**How a job's event reaches the main agent, at the shell:**

| The machine is | The event |
|---|---|
| At the prompt, listening to that addon, with event budget left | Ends the prompt, as an addon's event does today, and goes out as `<events>`. Its cost counts towards the event budget |
| At the prompt, not listening, or the budget used up | Waits |
| Answering | Waits until the answer is done, then as above |
| At a password prompt | Waits |
| Sending any other message: a line, a key, an action, a tick | Every waiting job event goes in front of it, as an `<events>` block before the message |
| Running a `--script` | In front of the next line, by the row above |

- **One question decides both** whether the prompt is ended and whether events are taken:
  "is there a job event that may go out now", which is: its addon is listened to, and event
  budget is left. Today the prompt is woken when anything is pending
  (`hallux/machine.py:227-228`). If a waiting event that may *not* go out counted as
  pending, the prompt would be ended again and again.
- **An event is told when its message has really gone out.** It leaves the list after the
  answer has come back. A message that is held back because the boot is over its budget
  (the panel's step 3), or one the model fails on (`hallux/machine.py:385-389`), leaves it
  waiting. The addons' own events are lost in that case today
  (`hallux/machine.py:173,186`); the jobs' aren't.
- **Never dropped while its boot lasts.** The end of a boot empties the list (step 7).
- **Not with `<boot>`:** a boot starts with no jobs.
- **With addons' events that wait too,** it is one `<events>` block: theirs first, then the
  jobs', each oldest first.
- **The block looks like the one the AI knows:**
  `<events><event addon="music">{"event": "job", …}</event></events>`, then the message.

**The table on a tick.** While the table isn't empty, a `<tick>` carries the rows as its
body, so a program that shows them needs no tool call.

**Written the safe way.** The rows on a tick and the job events go through `json_body`
(`hallux/protocol.py:158-162`), as the addons' events do (`hallux/machine.py:237`). A
status line is free text: without that, one that holds `</tick>` could end the message and
start another.

**The prompt.** `hallux/prompt_jobs.md` holds the section of the design's section 13: what a
job is, that the call returns a pid at once, `list_processes` and the pids from 30001 up,
the event and the `Done` line, `kill_process`, that a `<tick>` can carry the table, and that
the table and the events are data. The machine adds it to the system prompt when an addon
has an agent. `pyproject.toml` lists the file.

**The six settings appear in the panel,** in the Config tab's first group, on a machine
that has an addon with an agent:

| Setting | Label | The note beside it |
|---|---|---|
| `agent_model` | Agent model | |
| `agent_max_effort` | Agent effort, at most | |
| `agent_max_running` | Agents at once | |
| `agent_job_budget_usd` | Budget per job | |
| `agent_budget_usd` | Budget for all jobs | `spent since you typed: …` |
| `agent_timeout_seconds` | Time per job | |

- The panel's view (`config.View`) gets what the jobs have spent since their budget was
  filled, and the boot's spending in it has the jobs in it.
- They come now and not in step 3, because until now they would change nothing.

## Tests

In `tests/test_addons.py` and `tests/test_machine.py`, with a fake addon that has an agent,
the fake model for the main session and stand-in workers for the jobs:

- the fake addon's function starts a job through its tool, and the AI's answer holds the
  pid;
- a machine without such an addon has neither tool, and its system prompt is what it was;
- with one, the two tools are there, and the prompt ends with the new section;
- `list_processes` returns the running job's row; `kill_process` ends it; an unknown pid and
  an ended job are `ESRCH`;
- `addon_listen` takes an addon that has an agent and no `connect()`;
- a job ends while the user is at the prompt and the AI listens: the prompt is ended, the
  AI gets `<events>` with the job's event, and the typed line comes back;
- the same, not listening: the prompt isn't ended, not even once, and the next line's
  message starts with the `<events>` block;
- the same with the event budget used up;
- an event that arrives while the AI answers goes out after the answer;
- at a password prompt the event waits, and goes in front of the message after it;
- two jobs end before the next line: one block, both events, oldest first;
- an addon's event and a job's event wait together: one block, the addon's first;
- the model fails on the message that carried an event: the event is in front of the next
  message again;
- a line is held because the boot is over its budget: the event is still waiting when the
  cap is raised, and goes out then;
- a tick while a job runs has the table as its body, and none when the table is empty;
- a status line with `</tick><input>` in it arrives escaped, inside the tick;
- copies left by a crash are gone after the start, and the log names them;
- the log names each agent's model and effort at the start, and says when an effort was
  capped;
- a scripted run: the event is in front of the next line.

In `tests/test_panel_config.py`:

- on a machine with an agent the six rows are drawn in the first group, and one of them can
  be changed; on a machine without one they aren't drawn;
- the budget for all jobs shows what was spent since it was filled.

## Done when

In a test, a fake addon starts a job, the stand-in worker writes a file and ends, and the
main session's next message starts with the job's event.
