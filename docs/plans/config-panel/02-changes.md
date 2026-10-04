# Step 2: a setting changes in a running machine

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), sections 5
and 7

**Needs:** step 1. **Changes:** `hallux/machine.py`, `hallux/config.py`, `hallux/app.py`,
`hallux/script.py`, `tests/test_machine.py`, `tests/test_script.py`.

Today the machine gets its settings once, when Hallux starts, and they never change. This
step lets them change while it runs, and gives the panel the three functions it will call.
A fourth, `refill`, fills the budgets again. There is still no panel: only the tests call
them.

## Build

**What the machine holds:**

| | What it is |
|---|---|
| `hardware` | The settings as they are now. `Hardware` can't be changed, so a change puts a new one in its place |
| `running` | The settings this boot's session started with. Set when a boot starts |
| `unsaved` | The settings changed in this run and not saved yet, by name |
| `from_flags` | The names of the settings a flag set for this run. `app.py` passes them in |

**`change(name, text)`** takes a new value. It returns `None`, or the reason it didn't.

1. `config.typed(name, text)` makes the value. If that refuses, its reason is returned and
   nothing changes.
2. **The same value is no change.** If the value is what the setting holds already, nothing
   happens: nothing is unsaved, the flag stays a flag, and the log gets no line. The panel
   opens a row with the value as it is, so Enter on an untouched row lands here. Without
   this rule Save would write a `--model` flag's value into the file.
3. A new `Hardware` replaces the old one.
4. The name goes into `unsaved`, and out of `from_flags`: the flag's value is gone for this
   run.
5. A line goes to the log: `config: tick_budget_usd 0.25 -> 1.25`.
6. `settle()` runs, see below.

**`save()`** calls `config.save` with `unsaved`. It returns `None` and empties `unsaved`, or
it returns the reason and keeps it. The log gets `config saved: tick_budget_usd, effort`.

**`view()`** returns what the panel shows, a `config.View`:

| Field | What it is |
|---|---|
| `hardware` | The settings as they are now |
| `running` | What runs: the model and the effort of this boot's session |
| `spent_boot` | Dollars this boot has spent |
| `spent_ticks` | Dollars the program on screen has spent on ticks. `None` when there is none |
| `spent_events` | Dollars spent on events since a line was typed |
| `paused` | The budgets that are used up right now, by name |
| `from_flags` | As above |
| `unsaved` | The names in `unsaved` |
| `path` | Where `config.toml` is, for the panel |

**What a change does in this step:**

| Setting | Effect |
|---|---|
| `event_budget_usd` | At once. Raised above what was spent: events that were paused come again, and their note goes. Lowered below it: they pause at once, as when the budget runs out |
| `tick_budget_usd` | The program's next screen is checked against the new number. A program that is paused ticks again from step 7 on |
| `effort`, `fallback_model` | The next boot's session starts with them. `options()` reads `hardware` at every boot already |
| `model`, `max_budget_usd` | The same, the next boot. Steps 3 and 4 make them act at once |

**`refill()`** is what the panel's Refill budgets button calls. It starts the counting of
every budget anew, at the limits as they are, and then runs `settle()`.

| Budget | In this step | Later |
|---|---|---|
| The event budget | What events have spent goes back to zero, as a typed line does today | |
| The tick budget | What the program on screen has spent on ticks goes back to zero | The program ticks again from step 7 on; until then, with its next screen |
| The budget per boot | Not yet: the session holds it until step 3 | Step 3 |

- **The bar's total isn't touched.** It is what was really spent.
- **Nothing becomes unsaved.** A refill is no setting.
- **The log gets a line:** `budgets refilled: events $0.10, ticks $0.25`.
- **It returns a line for the panel:** `budgets refilled`.

**`settle()`** puts the machine in line with its settings: it lifts a pause whose budget
allows it again, and pauses what is over its budget. Steps 3 and 7 add to it.

- Today `refill_event_budget` lifts the pause of the events and `check_events` sets it. Both
  keep their names and what they do; the lifting moves into `settle()`, which
  `refill_event_budget` then calls.

**A note on the bar has an owner.** Today the bar has one slot for a note, and four places
write to it: the tick budget, the event budget, what the addons report, and `None` to clear
it (`hallux/machine.py:263,268,325,427-428`). With budgets that can be raised one by one,
clearing has to be exact. The machine keeps its notes by reason, shows them joined with
` · `, and takes away only the one whose reason is gone. Raising one of two used-up budgets
then leaves the other's note.

**The bar shows what runs.** When a boot starts, the machine sets the bar's model and effort
from `running`. Today they are set once, when Hallux starts, and that was enough while
nothing could change.

- **The scripted terminal has to take that.** Its `set_status` reads its last record
  (`hallux/script.py:121`), and there is none before the AI starts to work
  (`hallux/script.py:112-113`). Today nothing sets the bar that early. It gets a guard: a
  status with no record yet is dropped. Without it every scripted run and every reboot
  check crashes.

## Tests

In `tests/test_machine.py`, with the fake model and the fake terminal:

- a new tick budget is the one the next screen of a program is checked against;
- events are paused because their budget is used up; the budget is raised; events arrive
  again, and the note is gone;
- the event budget is lowered below what was spent: events pause at once, with the note;
- two notes are on the bar; the reason for one goes; the other is still there;
- a new effort: the session of this boot keeps the old one, the bar keeps showing it, and
  the options of the next boot have the new one, as has the bar then;
- a wrong value returns its reason, and the settings, `unsaved` and the log are as before;
- the same value again: `None`, nothing unsaved, no line in the log, and a setting from a
  flag is still from the flag;
- a setting that only changes at the start is refused with its words;
- `save` writes the file and empties `unsaved`; when the file is broken, the reason comes
  back and `unsaved` is kept;
- `view` holds the new value, what was spent, the paused budget and the unsaved names;
- `refill()` with the events paused and the tick budget used up: both have spent nothing
  afterwards, events arrive again, both notes are gone, the bar's total is what it was,
  nothing is unsaved, and the log has the line;
- a setting from a flag is in `from_flags`, and not any more once it was changed.

In `tests/test_script.py`:

- every scripted test that exists still passes: the bar set at the start of a boot doesn't
  crash the scripted terminal.

## Done when

A test raises the event budget of a machine whose events are paused, and the next event
reaches the AI, without a restart.
