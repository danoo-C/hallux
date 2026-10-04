# Step 3: the six settings

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 6

**Needs:** step 1 of the [config panel's plan](../config-panel/README.md).
**Changes:** `hallux/config.py`, `tests/test_config.py`.

What addon agents may cost is decided in `config.toml`, like the rest of the machine's
hardware. This step adds the settings and their checks. Nothing reads them yet, and the
panel doesn't show them yet: its rows come in step 10, when a job can start.

## Build

**In `Hardware`:**

| Setting | Default | The check |
|---|---|---|
| `agent_model` | none: the machine's `model` | A model name, or left out |
| `agent_max_effort` | `"high"` | One of the five efforts |
| `agent_max_running` | `2` | A whole number, 0 or more |
| `agent_job_budget_usd` | `1.00` | A number, more than 0 |
| `agent_budget_usd` | `2.00` | A number, 0 or more |
| `agent_timeout_seconds` | `600` | A number, more than 0 |

- **Each goes through `config.check`,** which the panel's plan makes the one place for the
  rules and their words (its step 1). A wrong value in the file stops Hallux at the start
  with a readable message, as for the other settings.
- **Two settings are checked together:** a budget per job that is larger than the budget
  for all jobs. No job could ever start. `load` refuses it with a message that names both:
  `agent_job_budget_usd (3.0) must not be more than agent_budget_usd (2.0)`. A budget for
  all jobs of 0 is allowed with any budget per job: it turns the agents off.
- **`config.typed` learns them,** and with them two kinds of value it doesn't have yet:

  | Kind | What is typed | For |
  |---|---|---|
  | A whole number | Digits only | `agent_max_running` |
  | Seconds | A number, 0 or more; an `s` at the end is fine | `agent_timeout_seconds` |

  The check of two settings together runs there too, against the settings as they are.
- **`config.WHEN`** has all six under `now`: every job is a new session, so a change acts
  from the next job.

**Two helpers** that later steps use:

| Helper | What it gives |
|---|---|
| The model of an agent | `agent_model`, or the machine's `model` |
| The effort of an agent | The lower of what the addon asks and `agent_max_effort`. Without an ask: the machine's own effort, capped the same way. On Haiku: none, as for the machine (`hallux/config.py:34`) |

## Tests

In `tests/test_config.py`:

- the defaults;
- each setting read from a file;
- each wrong value with its words: a negative count, a count that isn't whole, a budget per
  job of 0, an effort that doesn't exist, a time of 0;
- a budget per job above the budget for all jobs is refused, and both are named; with a
  budget for all jobs of 0 it loads;
- `typed` for each: `3`, `2.5` and `-1` for the count; `600`, `90s` and `0` for the time;
- `typed` refuses a budget per job that would pass the budget for all jobs as it is now;
- `save` writes one of them;
- the model of an agent, with and without `agent_model`;
- the effort of an agent: an ask above the cap, below it, no ask, and on Haiku.

## Done when

A `config.toml` with all six settings loads, and one with `agent_max_running = -1` stops
with a message that names the setting.
