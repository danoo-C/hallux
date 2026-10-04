# Step 16: the panel's two tabs

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 17,
and [config-panel.md](../../config-panel.md), section 4

**Needs:** step 10, and steps 5 to 7 of the
[config panel's plan](../config-panel/README.md). **Makes:**
`hallux/panel_tabs/agents.py`, `hallux/panel_tabs/details.py`, `tests/test_panel_jobs.py`.
**Changes:** `hallux/app.py`, `hallux/agents.py`, `tests/test_agents.py`.

The user watches the jobs in Hallux's own panel: a list of all agents and jobs, and for one
of them what it is doing right now. Both are tabs of the panel that the config panel's plan
builds, each a file of its own. They cost no model call, and the main agent never learns of
them.

**This step can come any time after step 10.** Built before step 13, the Details tab is
there for the composer's first live run, which is where it is wanted most.

## Build

**What `Jobs` gives the tabs.** Steps 7, 8 and 9 keep it; this step adds one function that
hands it out, `Jobs.watch()`:

| | What |
|---|---|
| The rows | Every running job, and the last 32 that have ended since Hallux started |
| The agents | Every agent an attached addon declares, with whether it could start now and, if not, why (step 8). And what the Details tab shows of an idle one: its addon, its instructions, its tools, the effort it asks for, and the model and effort it gets (step 3's helpers) |
| The activity of a job | Its last 200 lines (steps 7 and 9) |
| The total | What the jobs have cost in this boot |

**The Agents tab,** `hallux/panel_tabs/agents.py`, as the design's sketch:

| Row | Columns |
|---|---|
| A job | Pid, addon, agent, state, time, tokens, cost once it has ended, status line. For an ended job the status column says how it ended |
| An idle agent | No pid. `ready · effort high`, or `can't start:` and the reason |

- **The order:** running jobs first, newest on top; then ended ones, newest on top; then
  idle agents.
- **Under the list:** how many run, how many have ended, and the total.

| Key | What it does |
|---|---|
| ↑ ↓, or a click on a row | Picks a row. The pick is the one thing the host shares between tabs |
| Enter | Shows the Details tab for that row, with `host.show`, which the host hands every tab (the panel's step 5) |
| `k` | On a running job: asks `kill 30005? y/n` in the foot. `y` kills, anything else doesn't |
| `i` | Hides the idle agents, or shows them. They are shown when the panel opens |

- **It wants to be first** while a job runs, so the panel opens on it then (the host's rule
  in the panel's step 5).
- **While the question is asked,** the tab counts as typing, so `y` and `n` aren't taken for
  anything else.

**The Details tab,** `hallux/panel_tabs/details.py`:

| The pick is | It shows |
|---|---|
| A job | A head with the row's facts, the folder and the files it may change. Under it the job's activity, newest at the bottom |
| An idle agent | Its addon, its instructions, its tools, the effort it asks for, the model and effort it gets |
| Nothing | The first row of the Agents tab is picked |

| Key | What it does |
|---|---|
| ↑ ↓, PageUp, PageDown, the wheel | Scroll. At the bottom, the view follows new lines again |
| ← → | The row before or after, in the Agents tab's order |
| `k` | As in the Agents tab |
| Esc | Back to the Agents tab, with `host.show`. That is the tab's `leave()`, so the panel stays open |

**A line of activity** has a time, counted from the job's start, a kind and a text:
`status`, the tool's name, `→` for its short result, `says`, and one line for how the job
ended. The lines come from `Jobs` already cleaned and cut; the tab only draws them.

**Killing** calls the same `kill` as `kill_process` (step 7). The main agent gets the event
with `"state": "killed", "why": "kill"`, when the panel closes.

**Moving by itself.** Both tabs read from `Jobs.watch()` at every redraw. The panel is
drawn again when a job reports, and once a second while a job runs, for the times. The beat
is the terminal's one timer, which step 12 makes for the bar. If this step is built before
step 12, it makes the timer, and step 12 uses it.

**Disabled.** On a machine where no attached addon has an agent, both tabs say so, and the
host draws them grey: `no attached addon has an agent`.

**`app.py`** builds the panel with three tabs, Agents, Details and Config, where it built it
with one.

## Tests

In `tests/test_agents.py`:

- `watch()` has a running job, an ended one after the main agent has read the table, and an
  idle agent with `ready`;
- an agent whose start would be refused has the reason, for each cap;
- the 33rd ended job pushes the oldest out.

In `tests/test_panel_jobs.py`, on a pipe, in a real panel, with a `Jobs` that has stand-in
workers:

- the Agents tab's text: a running job, an ended one with its cost, a killed one with its
  reason, an idle agent, one that can't start, and the line under the list;
- `i` hides the idle agents and shows them again;
- a job reports a new status while the tab is open: the row has it without a key;
- down and Enter show the Details tab for that job;
- the Details tab's text: the head, and the lines in order with their kinds;
- a new line arrives while the tab is open and is drawn; after scrolling up, the view stays
  where it is; back at the bottom, it follows again;
- ← and → show the next row;
- Details of an idle agent shows its instructions and tools;
- `k`, then `y`: the job is killed, and the row says so; `k`, then `n`: nothing happens;
  while the question is asked, `d` doesn't switch the tab;
- `k` on an ended job or an idle agent does nothing;
- a line with an escape code in a job's text is drawn without it;
- the panel opens on Agents while a job runs, and on Config when none does;
- on a machine without an agent addon both tabs are grey, and `a` puts the reason in the
  foot;
- Esc in Details goes back to Agents; Esc there closes the panel.

## Done when

On a pipe, with a stand-in job running: Ctrl+F12 opens the panel on Agents, Enter shows the
job's lines arriving, `k` and `y` kill it, and after Esc the main session's next message
starts with the job's event, `killed`.
