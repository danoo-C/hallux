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

### The check, on 2026-10-06

A throwaway script, six sessions on Haiku (`claude-haiku-4-5`) with Hallux's kind of
options: no built-in tools, one in-process tool, `setting_sources=[]`, no transcript. SDK
0.2.163 with its own Claude Code 2.1.286. **It cost $0.085** of the $0.25 it was allowed.

| Question | Answer | What was seen |
|---|---|---|
| Does the result that follows `interrupt()` hold the session's cost? | **Yes, up to the message that was cut** | Interrupted inside a tool: the result came 0.01 s later with `total_cost_usd` $0.0049, `terminal_reason` `aborted_tools`, `subtype` `error_during_execution`, `is_error` set. The tool's handler was cancelled. Interrupted while the model wrote: `aborted_streaming`, and the cost was $0.0010 where the cut message alone had sent 3,558 tokens: **the model message that is being written when the kill comes isn't in the cost** |
| Do the tokens of a running turn come with each model message? | **No. They come with the stream** | A model message arrives as one `AssistantMessage` per block, each with the same id and the same `usage`. Its input is right; its output is the number from the message's start: 1 to 6 where the message really had 82 to 122. With the stream on, the `message_delta` at a message's end holds its whole usage, and the five of them added up to the result's number exactly: 19,790 |
| Does the session's dollar cap end a job in the middle of a turn? | **No. It is looked at after each model message** | Ten short turns under a cap of $0.012: ended after the third model message at $0.0138, 1.15 times the cap, and the tool that message asked for got no answer. One long answer under a cap of $0.006: all 1,533 tokens of it were written, and the result came after it at $0.0122, 2.04 times the cap. Both: `subtype` `error_max_budget_usd`, `terminal_reason` `budget_exhausted`, `is_error` set |

**What follows for the build:**

- **A killed job's dollars are read from the result.** They are short by at most the one
  model message that was cut. Hallux has no prices to add it, so the README says it
  (step 17).
- **A job's session is opened with the stream on,** as the main session is. The tokens are
  taken from the stream: a message's input when it starts, its output when it ends. A
  message that is cut then still counts with its input.
- **A job can pass `agent_job_budget_usd` by one model message,** and the README says so
  (step 17). With many short turns that is little; one long answer near the cap can double
  it.

**Four more things the check showed,** which nobody had asked:

- **The result's `usage` is short after a cap or a kill.** After the cap it lacked the last
  model message (two of three), or held nothing at all (the one long answer), while
  `total_cost_usd` had everything. So the result's number must not replace a larger sum of
  the worker's own. This step's "the result's own number replaces the sum" becomes: the
  larger of the two stands.
- **Claude Code asks a question of its own in every session,** on Haiku whatever the
  session's model: about 900 tokens in and 11 out, a tenth of a cent. It is in
  `total_cost_usd` and in `model_usage`, and not in `usage`.
- **Every model message of a job carries about 3,400 tokens of Claude Code's own.** A
  system prompt of two lines with one tool sent 3,551. On Haiku nothing is cached below
  4,096 tokens.
- **Other messages arrive that a worker has to pass over:** `SystemMessage` of the kinds
  `status`, `thinking_tokens` and `commands_changed`, a `RateLimitEvent`, and a
  `ThinkingBlock` in front of each answer, on Haiku too.

**Times:** opening a session took 0.5 s (the design's check had two), closing it 0.5 to
1.3 s. `num_turns` was 3 after a kill in the first tool call and 2 after a kill in the
first answer, so after a kill it isn't the number of model messages.

### The step

Built on 2026-10-06, on the branch `addon-agents`. 34 new tests, 1417 in all; no old test
changed. Decided while building:

**The shapes**

- **`Session(job, running, client_factory)`** in `hallux/agents.py` is the real worker.
  `running` says which model the machine's own session really runs on. The client is made
  by the machine's `client_factory`, so that one argument makes both kinds of session.
- **The machine's `worker_factory` is empty by default,** and then the machine makes a
  `Session` for each job (`Machine.session`). `NoWorker` stays as what a `Jobs` falls back
  to when it is made without a machine.
- **`shared_options(hw, hidden)`** in `hallux/agents.py` holds the seven options both kinds
  of session get, and `Machine.options()` uses it. The stream is among them.
- **`build_job_servers(addon, disk, job)`** in `hallux/tools.py` makes a job's tools. It
  returns the servers, and the tools by the names the session allows. `Session.tools` keeps
  those, and the tests' fake Claude calls them.
- **`rules(addon)` and `task(job)`** make the system prompt and the job's one message.

**What the worker does with its session's messages**

- **The tokens come from the stream:** what a model message read when it starts, what it
  wrote when it ends. At the end the larger number stands, the worker's sum or the
  result's.
- **Every text the model writes goes to the log in full,** as `job 30001 says: …`, and to
  the panel as a `says` line, cleaned and cut at 500 characters. The last message is in
  the log once: `Outcome.last` is empty when it is the text that was just logged.
- **A tool call's line in the log has all its arguments,** as the main agent's has: what a
  job wrote can be read there.
- **A tool's short result is a line of the kind `→`,** cut at 160 characters: about two
  lines of the panel. A read gives a whole file back.
- **`set_status` isn't reported as a tool call.** Its status line is its line.
- **Why a job failed** is worded as the machine words a model error: the result's errors,
  or its text, or its kind, with the HTTP status. For a session that broke it is the
  error's name and words.
- **A session that ends without a result is a failed job.**
- **A session that doesn't open cost nothing. One that breaks after the brief went out has
  a cost nobody knows,** and counts with its full cap.

**Stopping**

- **After the interrupt the worker waits 3 seconds for the result,** then comes back
  without a cost. `Jobs` gives it 5.
- **A stop while the session opens ends the opening.** The SDK closes what it had opened
  when its `connect()` is ended (`claude_agent_sdk/client.py`, the `except` around
  `_connect_inner`), so nothing is left to close.
- **Three more moments are handled:** a stop before the worker ran, one in the moment the
  session is open, and one after the worker has come back. None asks the model anything.

**Closing**

- **Every session is closed in the background,** also one that ended by itself. A job's
  end, and the landing of its files, don't wait for Claude Code to go.
- **`Jobs.finish_later()` holds that work, and the end of a boot waits for it,** 5 seconds
  at most. So a boot's end can take about a second longer after a job: 0.5 and 1.0 seconds
  in the two real runs.

**Beyond the plan**

- **The job's one message names its folder too:** `Your folder is /home/user/Music.` The
  files it may change are listed as paths of the machine.
- **The sandbox's start script is written when it isn't there or isn't what it should
  be,** and then beside itself and renamed. That is less than once per run: a script that
  is right stays as it is over many runs.
- **A job's dollars are rounded to a hundredth of a cent in its row.** A real result said
  `0.012790900000000001`. The sums keep the number as it came.
- **The rules call the machine "hallux",** as the main prompt does. They are the five
  points of the design and nothing more.

**The lines of `machine.py` moved by two.** The references into it in steps 10, 11 and 15
are set again.

**The "Done when"**

- **With the fake Claude it is a test:** a job writes a score, sets its status, ends, and
  the file lands.
- **With a real model, by hand, on Haiku:** a job of an agent with an empty `tools` list
  wrote `hello.txt` with three lines into a test world. It took 13 seconds, two model
  messages, 9,470 tokens and $0.0128. The log had `job 30001: tool set_status {…}` and
  `job 30001: tool write_file {'path': '/home/user/Notes/hello.txt', 'content':
  'one\ntwo\nthree\n'}`, and the file landed.
- **A second real job was killed** 0.7 seconds after its first model message had ended.
  The row said `killed` at once, its cost arrived 0.01 seconds later, nothing was left in
  `.hallux/jobs`, and the session was closed a second after.
- **The two runs cost $0.023.** With the check, step 9 spent $0.108 on real model calls,
  all on Haiku.

**What I couldn't check**

- **What a cut message costs.** In the check, a kill in the middle of an answer left that
  message out of the cost. In the second real job the cost was $0.0106 where one message
  and Claude Code's own question come to about $0.0062, so there the message that hadn't
  started to arrive seems to have been counted. Two runs, two answers; the bound holds in
  both: short by one message at most.
- **A job under `os_sandbox`.** Bubblewrap doesn't run inside my own sandbox. The script's
  test uses a fake.
- **A job on a model with an effort.** Only Haiku ran, which has none.
- **A real result for used-up turns.** Its kind, `error_max_turns`, is from the SDK's
  source. The one for the dollars was seen in the check.
- **A real session that breaks:** Claude Code dying under a job.

**Nothing here draws on a terminal.** No machine can start a job before step 10.
