# Step 9: a job's real session

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), sections 2, 5,
6 and 13

**Needs:** steps 6 and 7. **Changes:** `hallux/agents.py`, `hallux/tools.py`,
`hallux/machine.py`, `hallux/sandbox.py`, `pyproject.toml`. **Makes:** `hallux/agent.md`.

The real worker: a Claude session of its own for each job, opened when the job starts and
closed when it ends. It gets the worker's rules, the addon's prompt, the job's tools and
nothing else. No machine can start one yet; that is step 10.

## The check, first

A throwaway script with a real model, a few cents. **The user says go before it runs.** The
design's own check showed that two sessions run side by side in one process, each with its
own tools, and that `interrupt()` ends a job at once. Three things are still unknown:

| Question | If yes | If no |
|---|---|---|
| Does the result that follows `interrupt()` hold the session's cost? | A killed job's dollars are read from it | Hallux has no prices to work them out from tokens. A killed job then counts with its full cap in the budgets, and its row says that the cost isn't known |
| Do the tokens of a running turn come with each model message? | They are taken from there | The session is opened with the stream on, and they are counted from it |
| Does the session's dollar cap end a job in the middle of a turn? | `agent_job_budget_usd` is close to exact | A job can pass it by one turn, and the README says so |

The answers go into "As built" at the end of this file.

## Build

**The options of a job's session:**

| Option | For a job |
|---|---|
| The system prompt | Hallux's rules for a worker, then the addon's `prompt` from its declaration |
| The model and the effort | The two helpers of step 3. The model's helper is given the model the main session runs on, for a machine without `agent_model` |
| The turns and the dollar cap | The job's own, which it carries since step 7: 60 turns, and `agent_job_budget_usd` as it was when the job started. The cap is the SDK's own for a session. The main session has none of the SDK's since the panel's step 3: Hallux checks its budget itself |
| The fallback model | None. The main session has the machine's (`hallux/machine.py:218`); a job fails before it runs on a model nobody chose for it |
| The tools | Three groups, below. Claude Code's own tools are off |
| Everything else | As for the main session: no settings of yours, no MCP servers of yours, no transcript, the OS sandbox if it is set |

- **What both kinds of session share** moves into one function, and `Machine.options()`
  uses it. The main session's options are the same afterwards. A dollar cap isn't among
  what they share.
- **The real worker is the default of the machine's argument** (step 8), as the SDK's
  client is the default of `client_factory` (`hallux/machine.py:114`). So `app.py` passes
  nothing, and a scripted run, which builds its own machine (`hallux/script.py:170`), makes
  real workers too. The tests pass stand-ins.
- **The sandbox's start script is written once per run.** Today it is written again
  whenever options are built (`hallux/sandbox.py:45`). With sessions that start at
  different times, a session could start while the script is half-written.

**The rules,** `hallux/agent.md`: the five points of the design's section 13, with the
agent's and the addon's name filled in. `pyproject.toml` lists the file beside `prompt.md`,
or an installed Hallux doesn't have it.

**The job's one message** is the brief. Under it, Hallux adds what the job may change:
the given files by name, or one line saying that it can only create files.

**The tools of a job:**

| Group | Tools | Built on |
|---|---|---|
| `hallux` | `list_dir`, `read_file`, `write_file`, `edit_file` | The job's disk (step 4). `write_file` has no `parents` |
| `hallux` | `set_status` | The job's row (step 7) |
| The addon's name | The functions in the declaration's `tools` | The addon's call wrapper, with a disk handle on the job's disk |

- There is no `stat`, `find`, `make_dir`, `chdir`, `remove`, `move`, `copy`, no memory tool
  and no addon tool of the main agent's.
- **A job's tools have a builder of their own.** The main agent's are all made in one
  function, each from a method of the disk (`hallux/tools.py:91-142`). A job's five are made
  the same way from the job's disk, with `write_file`'s schema lacking `parents`. What the
  two share is the wrapper that turns a method's answer or error into a tool's result.
- **Each tool says when it begins and ends,** so the row shows `waiting` and the tool's
  name without guessing from the session's messages.

**What the worker reads from its session:**

| It sees | It does |
|---|---|
| A tool call | A line in the log, with the pid in front |
| Tokens | Reports them to the row |
| The result | Comes back: well, or failed with the reason; the turns, the tokens, the dollars |
| A result that says the turns or the dollars ran out | Comes back as `turns` or `budget` |
| The session failing | Comes back as failed, with the reason |

- **"Well" is a result of the kind `success` that carries no error.** A call to the API that
  failed arrives as `success` with `is_error` set
  (`claude_agent_sdk/_errors.py:78-80`). The machine tests the flag for its own answers
  (`hallux/machine.py:689`); the worker has to as well, or the half-done work of a failed
  job lands.
- **A result after a kill** says so: its `terminal_reason` is `aborted_streaming` or
  `aborted_tools` (`claude_agent_sdk/types.py:1363-1371`). So the worker can tell a job
  that was stopped from one that ended.
- **Tokens** are counted as step 7 says: input and output of each model message, added up.
  The result's own number replaces the sum at the end.

- **The last message of the job** goes to the log, and never to the main agent.
- **For the user's panel** the worker adds two kinds of line to the job's activity (step 7):
  the text the model writes between two tool calls, as `says`, and a tool's short result
  when the call ends: its answer or its error, as one or two lines. The model's thinking
  isn't taken.
- **Stop:** `interrupt()`, then the worker reads on until the result arrives, at most a few
  seconds, and comes back with the cost. The session is closed after that, in the
  background: closing took up to 3.4 seconds in the design's check.
- **Stop before the session is open.** Opening takes about two seconds, and until then
  `interrupt()` raises "Not connected" (`claude_agent_sdk/client.py:308-312`). A stop in
  that time ends the opening, closes what was opened, and comes back with no cost: nothing
  was asked of the model.

## Tests

In `tests/test_agents.py`, with a fake client like the one the machine's tests have, which
hands out scripted messages and calls the job's real tools:

- the options: the prompt starts with the rules and holds the addon's prompt; the model and
  the effort are the helpers'; 60 turns; the dollar cap; no built-in tools; only the job's
  tools are allowed;
- the main session's options are what they were before this step;
- a machine that is made without a worker argument makes real workers, also one made for a
  scripted run;
- on a machine whose `model` setting is a name the session refused, a job without
  `agent_model` gets the model that runs;
- the first message holds the brief and the list of files, or the line for none;
- a scripted job writes a file with `write_file`, calls `set_status` and ends: the file is
  in the job's copies, the row had the status, and the worker comes back well with its cost;
- an addon function in `tools` reads the job's own version of a file through its handle;
- `write_file` with `parents` isn't in the schema; a tool that isn't a job's is refused;
- a result with the turns used up, and one with the dollars used up;
- a session that fails: the worker comes back failed, with the reason;
- a result of the kind `success` with the error flag set: the worker comes back failed, and
  nothing lands;
- the options have no fallback model, also when the machine has one;
- a stop while the session is still opening: no `interrupt` is sent, the worker comes back
  with no cost, and nothing is left open;
- the job's activity has the model's text as `says`, and each tool's short result after its
  call, a long one cut;
- stop: `interrupt` is called, the result after it is read, and the cost is in what comes
  back; a session that never answers after `interrupt` doesn't hold the worker for long;
- the start script is written once for two sessions.

In `tests/test_sandbox.py`: the script isn't written again when it is there and right.

## Done when

With the fake client, a job started through `Jobs` writes a score, ends, and its file lands.
With a real model, by hand: one job with an empty `tools` list writes a file of three lines
into a test world, and the log shows its tool calls with the pid in front.

## As built

Not built. The check hasn't run.
