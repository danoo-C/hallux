# Step 16: the panel's two tabs

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 17,
and [config-panel.md](../../config-panel.md), section 4

**Needs:** step 10, and steps 5 to 7 of the
[config panel's plan](../config-panel/README.md). **Makes:**
`hallux/panel_tabs/agents.py`, `hallux/panel_tabs/details.py`, `tests/test_panel_jobs.py`.
**Changes:** `hallux/app.py`, `hallux/agents.py`, `hallux/panel.py`, `tests/test_agents.py`,
`tests/test_panel.py`.

The user watches the jobs in Hallux's own panel: a list of all agents and jobs, and for one
of them what it is doing right now. Both are tabs of the panel that the config panel's plan
built, each a file of its own. They cost no model call, and the main agent never learns of
them.

**This step can come any time after step 10.** Built before step 13, the Details tab is
there for the composer's first live run, which is where it is wanted most.

## Build

**What the panel gives a tab,** as it was built (`hallux/panel.py`):

| | What |
|---|---|
| What a tab is | A subclass of `Tab`. The host asks it nine things: its title, its part of the screen, its keys, its hint, whether it is typing, whether it is disabled, whether the panel should open on it, what Esc leaves, and a call when it is shown |
| What a tab can ask of the host | `host.show(title)` shows another tab, `host.close()` closes the panel, and `host.pick` is the one thing tabs share |
| What a tab knows of the machine | Nothing. The Config tab is given four functions. These two are given two: `watch`, which is `Jobs.watch`, and `kill`. Their tests pass a `Jobs` with stand-in workers |

- **Each tab draws from one function,** which makes the whole tab as text from what `watch`
  returns and where the user is, as the Config tab's `draw()` does. That function is
  tested without a pipe.
- **The row the cursor is on is shown in reverse,** as in the Config tab, with no mark in
  front of it.

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
| ↑ ↓, or a click on a row | Picks a row. The pick is `host.pick` |
| Enter | Shows the Details tab for that row, with `host.show` |
| `k` | On a running job: asks `kill 30005? y/n`. `y` kills, anything else doesn't |
| `i` | Hides the idle agents, or shows them |

- **It wants to be first** while a job runs, so the panel opens on it then (the host's
  rule).
- **The question is the tab's own hint.** While it is asked, the tab counts as typing. The
  host then shows the hint alone in the foot and takes no letter for itself, so `y`, `n`
  and `d` are the tab's. The host's own message in the foot can't carry it: a tab can't set
  it, and it fades after four seconds (`hallux/panel.py:28`).
- **What drops the question:** any typed key but `y`, Esc, a click on another row, and the
  panel closing. A move of the mouse doesn't: tried on 2026-10-05 in the real panel, a
  tab's catch-all key sees typed keys only.
- **The idle agents are shown whenever the tab is shown.** The host calls a tab's `shown()`
  when the panel opens and at every switch of the tab (`hallux/panel.py:159-162`), and a
  tab can't tell the two apart.
- **With a job running the panel opens here, also when the bar says
  `raise it: ctrl+f12`** for a used-up budget. Config is one key away, and it stays so.

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

- **A tab says what Esc does there.** The host adds `Esc close` to every tab's hint today
  (`hallux/panel.py:201-210`). Tried on 2026-10-05 with a stand-in Details tab, the foot
  read `Esc back · a d c tabs · Esc close`. So `Tab` gets a tenth thing: the word for Esc,
  `close` unless the tab says otherwise. Details says `back`, and the host writes that.

**A line of activity** has a time, counted from the job's start, a kind and a text:
`status`, the tool's name, `→` for its short result, `says`, and one line for how the job
ended. The lines come from `Jobs` already cleaned and cut; the tab only draws them.

**Killing** calls the same `kill` as `kill_process` (step 7). The main agent gets the event
with `"state": "killed", "why": "kill"`, when the panel closes.

**Moving by itself.** Both tabs read from `watch` at every redraw. The panel is drawn again
when a job reports, and once a second while a job runs, for the times.

- **The redraw goes through the terminal,** by the one function step 12 opens for it. It
  draws the panel's own app at the shell, and block mode's app when the panel is a layer
  over a full-screen program. `Panel.invalidate()` alone draws nothing in the second case.
- The beat is the terminal's one timer, which step 12 makes for the bar. If this step is
  built before step 12, it makes the timer and opens the function, and step 12 uses them.

**Disabled.** On a machine where no attached addon has an agent, both tabs say so, and the
host draws them grey: `no attached addon has an agent`.

**`app.py`** builds the panel with three tabs, Agents, Details and Config, where it built it
with one (`hallux/app.py:80-85`).

## Tests

In `tests/test_agents.py`:

- `watch()` has a running job, an ended one after the main agent has read the table, and an
  idle agent with `ready`;
- an agent whose start would be refused has the reason, for each cap;
- the 33rd ended job pushes the oldest out.

In `tests/test_panel.py`:

- a tab that says `back` for Esc: the foot has `Esc back` once, and no `Esc close`; a tab
  that says nothing has `Esc close`, as before.

In `tests/test_panel_jobs.py`, on a pipe, in a real panel, with a `Jobs` that has stand-in
workers. The tests type with the helper of `tests/test_panel.py`, which waits until the
panel has drawn again: a fixed wait failed once there, on a busy computer.

- the Agents tab's text: a running job, an ended one with its cost, a killed one with its
  reason, an idle agent, one that can't start, and the line under the list;
- `i` hides the idle agents and shows them again;
- a job reports a new status while the tab is open: the row has it without a key;
- the same with the panel as a layer over a full-screen program;
- down and Enter show the Details tab for that job;
- the Details tab's text: the head, and the lines in order with their kinds;
- a new line arrives while the tab is open and is drawn; after scrolling up, the view stays
  where it is; back at the bottom, it follows again;
- ← and → show the next row;
- Details of an idle agent shows its instructions and tools;
- `k`: the foot shows the question alone; `y`: the job is killed, and the row says so;
- `k`, then `n`: nothing happens; while the question is asked, `d` doesn't switch the tab;
- `k`, then a move of the mouse: the question is still there; `k`, then a click on another
  row: it is gone, and nothing was killed;
- `k` on an ended job or an idle agent does nothing;
- a line with an escape code in a job's text is drawn without it;
- the panel opens on Agents while a job runs, and on Config when none does;
- on a machine without an agent addon both tabs are grey, and `a` puts the reason in the
  foot;
- Esc in Details goes back to Agents; Esc there closes the panel.

## Before the user tries it

A check on a pseudo-terminal, with a terminal emulator drawing the screen, as for the
panel's steps 6 and 7: the panel opened at the shell and over a full-screen program, with a
stand-in job running. The rows move, the bar is on the last row only, and after Esc the
screen under the panel is as it was.

## Done when

On a pipe, with a stand-in job running: Ctrl+F12 opens the panel on Agents, Enter shows the
job's lines arriving, `k` and `y` kill it, and after Esc the main session's next message
starts with the job's event, `killed`.

## As built

Built on 2026-10-06, on the branch `addon-agents`, before step 13, as the build order has
it. 29 new tests, 1518 in all. Decided while building:

**What `Jobs` hands out**

- **`Jobs.watch()` returns a `Watched`:** the jobs, the agents, and what the jobs cost in
  this boot. A job is a `Seen`: its row, the files it may change, its lines, and how it
  ended. An agent is a `Declared`.
- **`Jobs` is given the attached addons and the model that runs,** by the machine. Until
  now it knew an addon only from the job it started.
- **Every declared agent is in `watch()`,** also one whose job runs: its reason is
  `already running`. The tabs list as idle the ones that aren't.
- **`Job.ended_as` is how a job ended, in words:** the files that landed, or the reason.
  The Agents tab shows it in the status column of an ended job.

**The Agents tab**

- **The columns stand close together,** so that the status has room: 21 characters on a
  window of 80 columns. `can't start: jobs budget used` is cut there, to
  `can't start: jobs bu…`; from about 90 columns it is whole, and the Details tab has it
  whole at any width.
- **A name longer than 12 characters is cut,** an addon's or an agent's.
- **The cost column** has `·` while a job runs and `?` for a cost that isn't known.
- **The pick is a job's pid, or an idle agent's addon.** With nothing picked, the first
  row counts as picked, in both tabs.
- **`k` stays in the hint on every row,** and does nothing where there is nothing to kill.

**The Details tab**

- **The head says `waiting in check`,** with the call's name. The file is in the lines.
- **A long line is wrapped to the window,** under its own text. A tool's result stands
  under its call, with `→` and no time.
- **The view is a window that scrolls to its cursor.** While it follows, the cursor is on
  the newest line. Scrolled up, the tab holds the first line in view.
- **PageUp and PageDown move a screenful less one line, the wheel three lines.**
- **An idle agent's details:** a head of two lines, its tools, and its instructions.

**Shared by both tabs,** in `hallux/panel_tabs/agents.py`: the rows in their order, which
one is picked, and the question before a kill (`Asking`). How a time, tokens and a cost are
written is the bar's: `clock()`, `tokens()` and `spent()` in `hallux/statusbar.py`.

**Drawing again**

- **The machine tells the terminal at every report of a job,** also one that changes
  nothing on the bar, such as a line the model wrote. The terminal draws again each time,
  so the Details tab shows the line at once and not at the next beat. Step 12 told it only
  when the bar had changed.
- **The beat and the redraw work without a bar too.** The panel exists on a machine whose
  `status_bar` is off.

**A tab's word for Esc** is `Tab.esc`, `close` unless the tab says otherwise.

**Old tests that changed:** the two that look at the panel `app.py` builds. It has three
tabs now, and their stand-in machines have a `jobs`.

**The "Done when" is a test,** with the real terminal on a pipe, the machine, the panel
with its three tabs, a pretend model and a stand-in worker: Ctrl+F12 with half a line
typed opens the panel on Agents, Enter shows the job's lines and two more as they arrive,
`k` and `y` kill it, and after Esc, Esc and Enter the line's message starts with the job's
event, `killed`.

**How I checked the tests themselves:** eleven wrong versions, one at a time: a busy agent
listed as idle too, any key killing, a click on another row keeping the question, the
panel never opening on Agents, the tabs never grey, `k` asking on an ended job, a view
that never follows again, Esc in Details closing the panel, the jobs oldest first, every
tab's Esc saying `close`, and no redraw for a report that changes nothing on the bar. Each
fails a test.

**The check on a pseudo-terminal, before the user tries it.** The real machine with the
real terminal, its bar and the panel as `app.py` builds it, 24 rows by 80 columns, with a
pretend model and a stand-in worker that works for fifteen seconds. The bytes were replayed
through a terminal emulator (`pyte`).

| Run | What the screen showed |
|---|---|
| At the shell, with `ls -l` typed and no Enter | Ctrl+F12 opened the panel on Agents: the job's row, the idle agent under it, the line under the list, the foot on row 23 and the bar on row 24 only |
| Two seconds on, no key pressed | The row's time went from `0:00` to `0:02`, and the bar's with it. When the job set a new status, the row had it and `48k` tokens |
| Enter | The Details tab: the head, the two lines in order, and `Esc back` in the foot |
| Esc, Esc | Every row under the panel as it was, the cursor behind `ls -l`, the bar on the last row and still showing the job |
| The same over a full-screen program | The same rows and the same moving. After Esc, Esc the program's screen was as it was |
| Over a program, drawing through the panel alone | The row stood still, and so did the bar. So the check can fail, and the finding of 2026-10-05 holds: the redraw has to go through the terminal |

**What I couldn't check**

- **A real terminal:** how the tabs look while they change, and the mouse. Clicks and the
  wheel are tested on a pipe, with the bytes a terminal sends for them.
- **The Details tab with a real composer.** Its lines come from a real session only from
  step 13 on; that live run is where the tab is wanted most.
- **A very long run:** a job's lines stop at 200, and a view that is scrolled up then
  moves by a line with each new one.
