# Step 8: the caps

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 6

**Needs:** step 7, and step 3 of the [config panel's plan](../config-panel/README.md).
**Changes:** `hallux/agents.py`, `hallux/machine.py`, `tests/test_agents.py`,
`tests/test_machine.py`.

A job is a second model session, and it spends while the user does something else. This
step puts the limits of the six settings in front of `spawn`. Each refusal is `EAGAIN`, the
way a failed `fork` reads. It is also the step in which the machine gets its `Jobs`,
because the budgets need what only the machine knows: when the user did something, and what
the boot has spent.

## Build

**The machine makes its `Jobs`,** when it is made itself. It gives it what step 7 asks for,
and one thing more:

| `Jobs` gets | From the machine |
|---|---|
| The disk | The machine's own (`hallux/machine.py:116`) |
| The settings | A function that returns `hardware` as it is at that moment. The panel replaces `hardware` with every change |
| What makes a worker | An argument of the machine, as the client's class is today. Until step 9 there is no real one, and nothing can call `spawn` before step 10. From step 9 on the real worker is the argument's default |
| What to call when a job reports or ends | A function of the machine. Here it looks at the boot's budget when a job has ended, see below. Steps 12 and 16 use it to draw the bar and the panel again |
| Whether the boot is over its budget | The machine's own check, `over_budget()` (`hallux/machine.py:381-384`), which counts the jobs from this step on. `spawn` asks it in the addon's thread; it only reads numbers |

- **The machine starts `Jobs` when it starts to run,** inside the event loop, so `Jobs`
  learns the loop there.
- **A scripted run needs nothing new:** `hallux/script.py:170` makes a machine, and the
  machine makes its `Jobs`.
- **At the end of a boot** the machine has every job killed, before the addons' `stop()`
  hooks run (`hallux/machine.py:301-304`). Since the fixes of Hallux's report that place
  first leaves a program that is still on screen; the jobs are killed after that. No event
  is made. The hard exit needs nothing new: it ends every child process Hallux has, and
  each job's Claude Code is one.

**`spawn` refuses** when any of these holds:

| The cap | Refused when |
|---|---|
| `agent_max_running` | That many jobs are running. With 0, always |
| One job per addon | The addon's agent has a job running |
| `agent_budget_usd` | The new job's full cap doesn't fit any more, see below |
| `max_budget_usd` | The boot is over its budget, see below |

**The budget for all jobs** counts three things:

| | Counts with |
|---|---|
| A job that has ended since the budget was filled | What it cost |
| A job that is running, or was killed and has no cost yet | Its full cap, `agent_job_budget_usd` |
| The job that asks to start | Its full cap |

A job starts only if the sum is at most `agent_budget_usd`. So the budget is never passed.
With the defaults, 1.00 and 2.00, two jobs fit while nothing was spent, and one after that.

**What fills it again:** `Jobs.refill()` sets what the ended jobs cost back to nothing. The
machine calls it:

| When | Today, for the event budget |
|---|---|
| A line is typed at the shell | The same (`hallux/machine.py:290,295`) |
| A key or an action arrives in a full-screen program | Not filled: this is new, and for the jobs' budget only |
| A boot starts | The same (`hallux/machine.py:427`, called at `:234`) |
| The panel's Refill budgets button is pressed | The machine's `refill()` fills every budget (the panel's step 2). It learns the jobs' budget here |

A tick and an event don't fill it: nobody is at the keyboard then.

- **A line or an action that is held back fills nothing.** While the boot is over its
  budget, what the user types doesn't go out (the panel's step 3), and the event budget
  isn't filled by it either. The jobs' budget follows that.

**The jobs' dollars are kept apart** from the main session's.

| Sum | What is in it | Who uses it |
|---|---|---|
| The main session's, this boot and in all | As today (`hallux/machine.py:647-650`) | The event budget, which measures one turn as the change of this sum (`hallux/machine.py:332-334`) |
| The jobs', this boot and in all | Each job when it has ended | The budget per boot; the bar's total, from step 12 |

Kept in one number, a job that ends while an event's turn runs would be charged to the
event budget.

**The budget per boot** is Hallux's own check since the panel's step 3. It now counts the
jobs:

- what a boot has spent is the main session's sum plus the jobs' sum for this boot. A job
  that a reboot killed counts in the boot it ran in;
- after a refill, the cap counts what both have spent since the refill (the panel's step 3
  counts the main session that way already);
- over the cap, `spawn` is refused, as no message goes to the AI.
- **A running job isn't counted until it has ended.** A boot that is one cent under its cap
  can still start jobs, and they spend their caps. So a boot can pass its cap by what the
  running jobs spend. That has a limit: the budget for all jobs, $2.00 with the defaults,
  since the caps of the running jobs never add up to more. (Whether a job can pass its own
  cap by a turn is one of step 9's questions.) The panel's live run measured the same for
  the main session, where one answer went $0.004 over. The README says it (step 17).
- **A job's end can put the budget's note up.** The note of a used-up budget per boot comes
  up before the user types, because the loop asks `hold()` each time it comes round (the
  panel's step 3). A job can end while the machine sits at the prompt, and nothing asks
  then. So the machine asks `hold()` when a job has ended and its cost is known, through
  the function `Jobs` calls.

**The time per job** is step 7's timeout, read from `agent_timeout_seconds`. The dollar cap
and the 60 turns travel with the job (step 7); a stand-in worker says "my budget ran out"
when its script tells it to, and the real one hands both to its session (step 9).

**Why an agent can't start.** `Jobs` can say, for an addon's agent, whether a start would
be refused now, and by which cap, in words: `already running`, `too many jobs`,
`jobs budget used`, `boot budget used`, `agents are off`. It is the same check `spawn`
makes, without starting anything. The panel's Agents tab shows it beside an idle agent
(step 16).

- **`agents are off`** is said for `agent_max_running = 0` and for `agent_budget_usd = 0`.
  Both turn the agents off, and `jobs budget used` would send the user looking for
  something to refill.

## Tests

In `tests/test_agents.py`, with stand-in workers:

- two jobs of two addons run; a third is `EAGAIN`; when one ends, the third starts;
- `agent_max_running = 0`: every start is `EAGAIN`;
- a second job of the same addon is `EAGAIN` while the first runs, and starts after it;
- the budget, with the defaults: two jobs start; both end at $0.30; the next one starts
  (0.60 + 1.00); one more is `EAGAIN` (0.60 + 1.00 + 1.00);
- after `refill()` it starts;
- a job that was killed counts with its full cap until its cost arrives, then with what it
  cost;
- a refusal leaves no row and no folder in `.hallux/jobs`;
- a change of a setting acts on the next `spawn`;
- for each cap: the question "could this agent start" gives the cap's words when `spawn`
  would be refused, and nothing when it wouldn't;
- with `agent_budget_usd = 0` the words are `agents are off`.

In `tests/test_machine.py`:

- a machine has a `Jobs`, also one made for a scripted run, and its settings are the ones
  the machine has after a `change`;
- a typed line fills the jobs' budget again;
- a key in a raw-mode program and an action in a program with fields fill it; a tick and an
  event don't;
- a line that is held back because the boot is over its budget doesn't fill it;
- a reboot fills it;
- the machine's `refill()` fills it: a job that was refused starts, and the budget per boot
  counts the jobs from there;
- the event budget is filled by a typed line and a boot only, as before;
- a boot over its budget: `spawn` is `EAGAIN`; the cap is raised, and it starts;
- a job's cost is part of what the boot has spent, once the job has ended;
- a job ends while the machine waits at the prompt, and its cost takes the boot over its
  cap: the bar's note is up before a line is typed;
- a job ends during an event's turn: the event budget is charged for the turn alone;
- `reboot` with a job running: the job is killed before the addons' hooks, and the new
  boot's table is empty.

## Done when

With the default settings, a test starts jobs until one is refused, types a line, and the
next one starts.
