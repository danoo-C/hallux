# Step 5: the panel by itself

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), sections 3
and 4

**Needs:** step 2, for `config.View`. **Makes:** `hallux/panel.py`, `tests/test_panel.py`.
**Changes:** `hallux/config.py`.

The panel as a thing that can be shown and used: its rows, changing one, Save and Close.
Nothing in Hallux opens it yet. It knows nothing of the machine: it is given three
functions, and the tests pass fakes for them.

## Build

**`Panel(view, change, save, bar, power_cut, ctrl_c)`:**

| It is given | What it is |
|---|---|
| `view()` | What to show: a `config.View` (step 2) |
| `change(name, text)` | A new value. Returns `None`, or why not |
| `save()` | Write the file. Returns `None`, or why not |
| `bar` | Hallux's status bar, for the last row. May be none |
| `power_cut()`, `ctrl_c()` | The hard exit, and the count of Ctrl-C that leads to it |

| It offers | What it is |
|---|---|
| `OPEN_KEY` | `"c-f12"`, for the terminal and block mode |
| `container`, `bindings` | Its part of a screen and its keys, for whoever shows it |
| `open()`, `close()` | Open starts fresh: the first row, no message |
| `is_open`, `wait_closed()` | For the code that has to wait for it |
| `run(input, output)` | Shows it in a full-screen app of its own until it is closed: the alternate screen, the mouse on, the wait after Esc at 0.05 seconds, the bar on the last row |
| `invalidate()` | Draw again |

**What it draws** is the sketch of the design's section 4:

- the title, and the path of `config.toml` on the right;
- three groups, by `config.WHEN`: "Changes now", "Changes at the machine's next reboot",
  "Set when Hallux starts (edit config.toml)". A setting that moves in `WHEN` moves here;
- a row per setting: its label, its value, and a note beside it;
- the buttons Save and Close;
- the foot: the keys, and how many changes aren't saved, or what Save answered.

**The rows:**

| Setting | Label | Value as shown | The note beside it |
|---|---|---|---|
| `model` | Model | The name | `running now: …`, while another model runs |
| `max_budget_usd` | Budget per boot | `$2.00`, or `none` | `spent in this boot: $1.42` |
| `tick_budget_usd` | Tick budget | `$0.25` | `spent by this program: $0.25`, only while a program is on screen |
| `event_budget_usd` | Event budget | `$0.25` | `spent since you typed: $0.00` |
| `effort` | Effort | The effort | `running now: low`, while another one runs |
| `fallback_model` | Fallback model | The name, or `none` | |
| `status_bar` | Status bar | `on` or `off` | |
| `addons` | Addons | The names, or `all that loaded` | |
| `keep_transcripts` | Transcripts | `on` or `off` | |
| `os_sandbox` | OS sandbox | `on` or `off` | |

- A budget that is used up has `(paused)` after its note.
- A setting from a flag has `from --model, for this run` as its note.
- A value that was refused has the reason as its note, in red, until the row is left.
- **What is shown is read from `view()` at every redraw,** so the spent amounts move while
  the AI works.
- **The text comes from one function** that takes the view and the panel's state, so the
  tests read it as text.

**Keys and the mouse:**

| Key | What it does |
|---|---|
| ↑ ↓, Tab, Shift+Tab | Move over the six rows that change and the two buttons |
| Enter, or a click | On a row: open it for a change. On a button: press it |
| Typing, in an open row | A name or a number, in a line that starts with the value as it is |
| ↑ ↓, in an open Effort or Model row | Pick from the list |
| Enter, in an open row | Take the value: `change(name, text)`. A reason comes back: it is shown, and the row stays open |
| Esc | In an open row: leave the row as it was. Otherwise: close the panel |
| Ctrl+F12 | Close, from anywhere |
| Ctrl+Shift+Del | The hard exit |
| Ctrl-C | Counts for the hard exit. Nothing else |

- **Effort** is picked from its five values. Nothing is typed.
- **Model and Fallback model** are typed, with a list to pick from: the three names in
  Hallux's help (Opus 5.5, Sonnet 5.5, Haiku 4.5), the model that runs and the one in the
  settings. `config.py` holds the three names.
- **An empty line** means none, for the budget per boot and the fallback model.
- **Save** calls `save()`. The foot then says `saved`, or the reason.
- **A window too short** for all of it: the rows scroll with the row you are on. The buttons
  and the foot stay.

## Tests

In `tests/test_panel.py`, with the keys from a pipe and an output that goes nowhere, as the
terminal's tests. `view`, `change` and `save` are fakes that note their calls.

- the text: the three groups, each value as the table says, the notes, a paused budget, a
  setting from a flag, the count of unsaved changes;
- a setting whose `WHEN` is changed is drawn in the other group;
- down, Enter, a number, Enter: `change` gets the name and the text, and the row closes;
- a refused value: the reason is on the row, the row is still open, Esc leaves it, and
  `change` wasn't called again;
- Effort: Enter, down, Enter gives the next of the five;
- Model: a name picked from the list, and a name typed;
- an empty budget per boot gives `change("max_budget_usd", "")`;
- Save calls `save` once, and the foot says `saved`, or the reason it returned;
- Esc closes, Ctrl+F12 closes also from an open row, the Close button closes, and
  `wait_closed` returns each time;
- Esc alone closes within a fifth of a second, and an arrow key doesn't close;
- the hard exit key calls `power_cut`; Ctrl-C calls `ctrl_c` and doesn't close;
- a click on a row opens it, and a click on Close closes;
- on a window of ten rows, the row you are on and the buttons are both drawn.

## Done when

On a pipe: the panel opens, the tick budget is changed to 1.25, Save is pressed and Esc
closes it. The fakes got exactly `change("tick_budget_usd", "1.25")` and one `save()`.
