# Step 3: the six settings

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 6

**Needs:** steps 1 and 5 of the [config panel's plan](../config-panel/README.md).
**Changes:** `hallux/config.py`, `hallux/machine.py`, `hallux/panel_tabs/config.py`,
`tests/test_config.py`, `tests/test_machine.py`, `tests/test_panel_config.py`.

What addon agents may cost is decided in `config.toml`, like the rest of the machine's
hardware. This step adds the settings, their checks, and their rows in the panel's Config
tab. Nothing reads them yet, and the panel doesn't show them yet: the rows are built here
and stay hidden until step 10, when a job can start.

## Build

**In `Hardware`:**

| Setting | Default | The check |
|---|---|---|
| `agent_model` | none: the model the machine runs on | A model name, or left out |
| `agent_max_effort` | `"high"` | One of the five efforts |
| `agent_max_running` | `2` | A whole number, 0 or more |
| `agent_job_budget_usd` | `1.00` | A number, more than 0 |
| `agent_budget_usd` | `2.00` | A number, 0 or more |
| `agent_timeout_seconds` | `600` | A number, more than 0 |

- **Each goes through `config.check`,** which the panel's plan made the one place for the
  rules and their words (its step 1). A wrong value in the file stops Hallux at the start
  with a readable message, as for the other settings.
- **`config.typed` learns them,** and with them two kinds of value it doesn't have yet:

  | Kind | What is typed | For |
  |---|---|---|
  | A whole number | Digits only | `agent_max_running` |
  | Seconds | A number, 0 or more; an `s` at the end is fine | `agent_timeout_seconds` |

- **`config.WHEN`** has all six under `now`: every job is a new session, so a change acts
  from the next job. One test pins which settings change now (`tests/test_config.py:149`)
  and changes with it.

**Two settings are checked together:** a budget per job that is larger than the budget for
all jobs. No job could ever start. The message names both:
`agent_job_budget_usd (3.0) must not be more than agent_budget_usd (2.0)`. A budget for all
jobs of 0 is allowed with any budget per job: it turns the agents off.

That check is a function of its own in `config.py`. It takes the settings and returns the
words, or nothing. Three places call it:

| Who | When |
|---|---|
| `load` | After its check of each setting. A wrong file stops Hallux at the start |
| `Machine.change` | On the settings as they would be with the new value (`hallux/machine.py:157-172`). The row of the panel shows the words, and nothing changes |
| `config.save` | Once, on the file as it would be after all its changes. If it fails, nothing is written |

- **It is not part of the check that `save` runs after each single change**
  (`hallux/config.py:142-151`). `save` writes the changes in the order the settings were
  first touched, and one of them alone can be wrong against the value the file still has
  for the other. Tried on 2026-10-05, with the pair checked where `load` checks a file: the
  budget per job set to 0.5, the budget for all jobs to 10, the budget per job to 5. Each
  was taken, and Save answered `can't change agent_job_budget_usd safely`.
- **`config.typed` can't make the check.** It is given a name and a text, not the settings
  (`hallux/config.py:109`).

**Two helpers** that later steps use:

| Helper | What it gives |
|---|---|
| The model of an agent | `agent_model`. Without it: the model the main session really runs on, which the machine keeps beside its settings (`hallux/machine.py:118`). The helper is given both |
| The effort of an agent | The lower of what the addon asks and `agent_max_effort`. Without an ask: the `effort` setting as it is now, capped the same way. On Haiku: none, as for the machine (`hallux/config.py:50`) |

- **Why the model that runs, and not the `model` setting.** The two are the same unless the
  setting holds a name that is no model. A running session refuses such a name and stays
  on its old model, with a note on the bar. A session that starts on it fails its first
  message (the panel's step 4, as built). Every job is a new session, so with the setting
  every job would fail.
- **Why the `effort` setting, and not the effort that runs.** A change of `effort` reaches
  the machine at its next reboot, because its session is open. A job's session is new, so
  it needn't wait.

**The rows in the Config tab.** They are built here with everything a row needs:

| Setting | Label | Shown | Typed | The list | The hint |
|---|---|---|---|---|---|
| `agent_model` | Agent model | The name, or `same as Model` | A name, or nothing for none | `none`, then the models the Model row offers | type a name, or ↑ ↓ pick |
| `agent_max_effort` | Max agent effort | The name | Picked only | The five efforts | ↑ ↓ pick |
| `agent_max_running` | Agents at once | `2` | Digits | | type a whole number |
| `agent_job_budget_usd` | Budget per job | `$1.00` | Dollars | | type the dollars |
| `agent_budget_usd` | Budget, all jobs | `$2.00` | Dollars | | type the dollars |
| `agent_timeout_seconds` | Time per job | `600s` | Seconds | | type the seconds |

- **Hidden until the tab is told.** The tab takes one more thing when it is built: whether
  the machine has an addon with an agent. Without it the six rows aren't drawn, and the
  arrow keys don't stop on them. Nothing tells it before step 10. The addons are attached
  when Hallux starts and never change in a run (`hallux/app.py:60`), so this needn't go
  through the view.
- **Why the rows can't wait for step 10.** A test of the panel holds that every setting has
  a row (`tests/test_panel_config.py:82`). Six settings without rows fail it.
- **A label is at most 18 characters.** The values start 19 characters after the label
  does (`LABEL_WIDTH`), and a longer label runs into its value. Tried on 2026-10-05 with
  this plan's first labels: `Agent effort, at mosthigh` and `Budget for all jobs2.0`. A
  test holds the length for every label.
- **A kind of value has code in eight places** of `hallux/panel_tabs/config.py`: `LABELS`,
  `BUDGETS`, `NAMES`, `shown()`, `entered()`, `choices()`, `hint()`, and the condition for
  a row that is typed into. Each of the six is in every one that applies to it. With the
  labels alone, every row's hint says "type the dollars" and no row offers a list.
- **The Agent model row has a warning of its own** while it is open:
  `a wrong name fails every job`. Today's warning is tied to the Model row
  (`hallux/panel_tabs/config.py:185-191`), and its words aren't true of an agent.
- **The note beside the budget for all jobs** comes in step 10, with the numbers it shows.

## Tests

In `tests/test_config.py`:

- the defaults;
- each setting read from a file;
- each wrong value with its words: a negative count, a count that isn't whole, a budget per
  job of 0, an effort that doesn't exist, a time of 0;
- a budget per job above the budget for all jobs is refused by `load`, and both are named;
  with a budget for all jobs of 0 it loads;
- the pair's function by itself: the words for a wrong pair, nothing for a right one;
- `typed` for each: `3`, `2.5` and `-1` for the count; `600`, `90s` and `0` for the time;
- `save` writes one of them;
- `save` with the three changes above, in that order: both lines are written;
- `save` of a change that would leave the file with a wrong pair: refused, both are named,
  and nothing is written;
- the model of an agent: with `agent_model`; without it, the model that runs, also when
  the `model` setting says another name;
- the effort of an agent: an ask above the cap, below it, no ask, and on Haiku.

In `tests/test_machine.py`:

- `change` refuses a budget per job that would pass the budget for all jobs as it is now,
  and a budget for all jobs below the budget per job; the settings stay as they were.

In `tests/test_panel_config.py`:

- every setting has a row, as before;
- a tab that wasn't told draws none of the six, and the arrow keys pass over them;
- a tab that was told draws them in the first group, each with its label and its value as
  the table has it;
- no label is longer than 18 characters;
- each row opens with its own hint, and the two rows with a list offer it;
- the Agent model row shows `same as Model` when it isn't set, and its warning when open;
- a refusal of the pair is shown in the row.

## Done when

A `config.toml` with all six settings loads, one with `agent_max_running = -1` stops with a
message that names the setting, and the panel's tests pass with the six rows hidden.
