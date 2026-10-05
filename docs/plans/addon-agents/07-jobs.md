# Step 7: the jobs

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), sections 7, 8
and 9

**Needs:** steps 3, 5 and 6. **Makes:** `hallux/agents.py`, `tests/test_agents.py`.

The middle of the feature: the process table, a job's life from `spawn` to its end, and the
event Hallux makes of that end. There is still no Claude session in it. A job is run by a
worker, and in this step the worker is a stand-in that follows a script. So everything here
is tested without a model.

## Build

**`Jobs`:** one for a run of Hallux. It holds the table and the job events.

**What it is given** when it is made. In this step the tests give it; in step 8 the machine
does.

| | What |
|---|---|
| The machine's disk | A job's folder is a path of the machine, and a path without `/` in front starts at the machine's working directory, as for every tool |
| The settings, as a function | They are read when they are needed, since the config panel can change them |
| What makes a worker | A function. The tests pass one that makes stand-ins; step 9 makes the real one |

- **It learns the event loop when it is started,** from inside the running loop. It can't be
  given one when it is made: Hallux builds its parts before the loop runs
  (`hallux/app.py:59-76`).

**`spawn(addon, brief, folder, edit)`** returns a pid, or raises `Refused` (step 6). `addon`
is the loaded addon with its declaration, which step 6 put there.

- It is called in the addon's own thread. So it only checks, notes the row under a lock, and
  hands the start of the worker to Hallux's event loop with `call_soon_threadsafe`, as the
  machine wakes its prompt from an addon's thread today (`hallux/machine.py:226`).
- **The checks,** in this step: the brief is text of at most 2000 characters, or
  `EMSGSIZE`; and the job's disk accepts the folder and the list (step 4). The caps come in
  step 8.
- **Pids count up from 30001 for as long as Hallux runs.** A reboot doesn't start them
  again.
- **A job carries its limits:** its dollar cap, its turns and its time. They are read from
  the settings when it starts and handed to the worker with it. So a later step never has to
  ask who passes them.

**A worker** is what runs one job. `Jobs` asks three things of it:

| | What it is |
|---|---|
| Run | Do the job, and come back with how it ended: well, or failed and why; the tokens, the dollars and the turns; its last message |
| Stop | End now, and still say what the job cost |
| Report | While it runs: a tool call began or ended, the tokens so far |

`Jobs` is given the function that makes a worker. The tests pass one that makes stand-ins;
step 9 makes the real one.

**A row** is what the design's section 7 shows. `Jobs` writes all of it but `status`:

| Field | When it changes |
|---|---|
| `state` | `running`, and `waiting` while the job is inside a tool call; then `done`, `failed` or `killed` |
| `status` | It starts as the declaration's `status`, or the agent's name without one |
| `tool` | The function, and a file's name: the first text argument that names, on the job's disk, a file it was given or has created. No other argument |
| `tokens` | When the worker reports them: input and output together, cached input included, added up over the job's turns |
| `seconds` | Counted from the start, and fixed at the end |
| `cost_usd`, `why` | At the end |

**`set_status(pid, text)`** is the one thing a job writes into its row:

- one line, cut at 80 characters;
- control characters, escape codes and the control pictures that the terminal turns into
  escape codes are taken out;
- it returns the line as kept.

**How a job ends:**

| What happened | State | What Hallux does |
|---|---|---|
| The worker came back, well | `done` | The landing (step 5). The event has `files`, and `conflict` if there was one |
| The folder was gone at the landing | `failed`, `why: folder` | The copies are dropped |
| The worker came back, failed | `failed`, with its `why` | The copies are dropped |
| `kill(pid)` | `killed`, `why: kill` | The row is marked at once. The worker is stopped, its cost goes into the row when it arrives, the copies are dropped |
| `agent_timeout_seconds` passed | `killed`, `why: timeout` | The same |
| The worker says its budget or its turns ran out | `killed`, `why: budget` or `turns` | The copies are dropped |

- **In every case** the job's disk is closed, so a handle that is still out there is dead,
  and the log gets one line: the pid, how it ended, turns, seconds, tokens, dollars.

**A kill against a natural end.** The two can cross, and the rules are:

| The case | What happens |
|---|---|
| The row is `killed`, and the worker then comes back well | Nothing lands. `killed` stands |
| A kill before the worker has started | The job is ended without a worker to stop. It cost nothing |
| A kill of a pid that is in the table but has ended | `ESRCH`, as for a pid that isn't there |
| A job that was killed, until its cost arrives | It counts as running for the caps of step 8, with its full cap |
| The cost never arrives: the worker's stop gives none | The row says that the cost isn't known, and the job counts with its full cap |
- **The event** is built from the row and the landing, nothing else:
  `{"event": "job", "pid": …, "agent": …, "state": …, "seconds": …}`, with `files`, or
  with `why` and `written` for a job that didn't end well. The worker's last message goes to
  the log and nowhere else.

**The job events** wait in a list of `Jobs`' own, with the addon's name on each. They
aren't in the hub of the addons' events, which drops what nobody listens to. `Jobs` hands
them out oldest first, and calls a function it was given whenever one arrives; step 10
uses that to wake the prompt.

**The table** as the main agent gets it: the rows as dictionaries. A job that has ended
stays until the main agent has seen it once, in the table or in an event. At most 32 rows;
the oldest ended ones go first.

**For the user's panel** (step 16), `Jobs` keeps two more things. The main agent gets
neither.

| | What |
|---|---|
| The activity of each job | A list of lines: a time counted from the job's start, a kind, a text. At most 200 per job; the oldest go first |
| The jobs that have ended | The last 32 since Hallux started, with their rows and their activity. They stay after the main agent's table has dropped them |

- **What writes a line in this step:** a status that was set, a tool call that began, and
  how the job ended. Step 9 adds a tool's short result and what the model says.
- **Every text is cleaned before it is kept,** like a status line: control characters,
  escape codes and control pictures are taken out, and it is cut at 500 characters.

**The end of a boot:** every running job is killed, with no event. `Jobs` waits a few
seconds for their costs, then the table and the list of events are empty: an event that
hadn't reached the main agent by then is gone, also one of a job that landed. The pids go
on, and so does what is kept for the panel.

## Tests

In `tests/test_agents.py`, with stand-in workers that follow a script: set a status, report
a tool call, write a file through the job's disk, wait until the test lets them go, end
well, fail.

- `spawn` returns 30001 at once, while the worker hasn't started; the next is 30002;
- `spawn` from another thread: the worker runs in the event loop;
- a brief that is too long (`EMSGSIZE`), a refused folder, a refused file: `Refused`, and no
  row;
- a relative folder starts at the machine's working directory;
- the row starts with the declaration's status line, and with the agent's name without one;
- a worker is handed the job's dollar cap, turns and time as the settings had them at the
  start;
- the row through a job's life: `running`, `waiting` with the tool's name, `running`, `done`;
- `tool` shows a file's name only for one of the job's own files;
- `set_status`: a long line is cut, an escape code and a control picture are gone, and the
  answer is the line as kept;
- a job that ends well: its file is in the folder, the event has `files`, and the row has
  the cost;
- a conflict at the landing: `conflict` and the `.new` path are in the event;
- the folder deleted while the job ran: `failed`, `why: folder`, nothing written;
- a worker that fails: the folder is as it was, and the event has `why` and `written`;
- `kill`: the row says `killed` at once, the cost arrives after it, the folder is as it was;
- a kill, and the worker then comes back well: nothing lands, and the row stays `killed`;
- a kill right after `spawn`, before the worker has started: the job ends, and no worker was
  made;
- a kill of an ended job: `ESRCH`;
- a stop that gives no cost: the row says the cost isn't known;
- the timeout: `killed`, `why: timeout`;
- after any end, the job's disk handle raises `ESTALE`;
- the events come out oldest first, and the function is called for each;
- an ended job leaves the table once it was read, and 33 jobs leave 32 rows;
- the end of a boot with a job running: no event, an empty table, and the next pid is one
  higher, not 30001;
- a job's activity holds its status lines, its tool calls and its end, in order, each with
  its time;
- the 201st line pushes the first out; a text with an escape code is kept without it;
- an ended job is still among the kept ones after the main agent has read the table, and
  after a reboot.

## Done when

A stand-in worker writes a score into a test world, ends, and the test reads the event:
`done`, the file's path, and the file is in the folder.
