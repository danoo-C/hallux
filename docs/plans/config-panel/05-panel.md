# Step 5: the panel by itself

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), sections 3
and 4

**Needs:** step 2, for `config.View`. **Makes:** `hallux/panel.py`,
`hallux/panel_tabs/__init__.py`, `hallux/panel_tabs/config.py`, `tests/test_panel.py`,
`tests/test_panel_config.py`. **Changes:** `hallux/config.py`, `hallux/blockmode.py`.

The panel as a thing that can be shown and used. It has two parts: the host, which owns the
screen and knows nothing of settings, and the Config tab, which is a file of its own.
Nothing in Hallux opens the panel yet. The tab knows nothing of the machine: it is given
four functions, and the tests pass fakes for them.

## Build: the host

**`Panel(tabs, bar, power_cut, ctrl_c)`,** in `hallux/panel.py`:

| It is given | What it is |
|---|---|
| `tabs` | The tabs, in the order of the tab row. In this step: one, Config |
| `bar` | Hallux's status bar, for the last row. May be none |
| `power_cut()`, `ctrl_c()` | The hard exit, and the count of Ctrl-C that leads to it |

| It offers | What it is |
|---|---|
| `container`, `bindings` | Its part of a screen and its keys, for whoever shows it. The container is without the bar's row: block mode has its own (step 7) |
| `open()`, `close()` | Open starts fresh: on the tab it should open on, with no message. Closing twice does nothing the second time |
| `is_open`, `wait_closed()` | Whether it is open, and a wait for the key that closes it. The terminal's own wait covers more: step 6 |
| `run(input, output)` | Shows it in a full-screen app of its own until it is closed: the alternate screen, the mouse on, the wait after Esc at 0.05 seconds, the container with the bar under it. The app doesn't take Ctrl-C's signal for itself, as block mode's doesn't (`hallux/blockmode.py:243`): that belongs to the answer that is running |
| `invalidate()` | Draw again |

**The key's name,** `OPEN_KEY = "c-f12"`, sits beside `POWER_CUT_KEY` in
`hallux/blockmode.py`. The panel and the terminal take both from there. Block mode never
imports the panel: it is handed one (step 7). So no two files import each other.

**What the host draws:** the tab row, the tab that is shown under it, and the foot with that
tab's hint line. In `run()` the bar is the row under that.

**The tab row:**

- every tab's title, with the first letter underlined; the tab that is shown has brackets;
- a disabled tab is dark grey;
- with one tab the row is drawn all the same: `[ Config ]`.

**The host's keys,** in every tab:

| Key | What it does |
|---|---|
| The first letter of a tab, or a click on its title | Shows that tab. The letters do nothing while the shown tab is typing; the click always works |
| A disabled tab's letter, or a click on it | Nothing changes, and the foot says the tab's reason |
| Esc | Asks the shown tab first. If the tab has nothing to leave, the panel closes. It is bound to act at once: without that, Esc waits a second while a text row has the focus, because the editing keys have bindings that start with Esc |
| Ctrl+F12 | Closes, from anywhere |
| Ctrl+Shift+Del | The hard exit |
| Ctrl-C | Counts for the hard exit. Nothing else |

**Which tab it opens on:** the first tab that says it wants to be first, otherwise the last
in the row. Config never asks, and it is last. So the panel opens on Config until a tab of
addon agents says that a job is running.

**A tab** is a class in a file of its own in `hallux/panel_tabs/`. The host asks this of it:

| A tab has | What it is |
|---|---|
| `title` | `Config`. Its first letter, in lowercase, is its key |
| `container` | Its part of the screen |
| `bindings` | Its keys. They act only while it is shown |
| `hint()` | The keys the foot shows for it |
| `typing` | True while a row is open for typing. The host then leaves the letters to it |
| `disabled()` | `None`, or the reason it can't be chosen |
| `wants_first()` | Whether the panel should open on it |
| `leave()` | Called for Esc. True if the tab had something to leave, such as an open row |
| `shown()` | Called when it becomes the shown tab, to start fresh |

- **Two tabs with the same first letter** are a mistake in the code. The host refuses the
  list when it is built, with the two titles in the message.

**What the host hands every tab,** once, when the panel is built: `attach(host)`. Through
it a tab can do three things:

| | What it is |
|---|---|
| `host.show(title)` | Show another tab. The Agents tab will show Details that way, and Details will go back |
| `host.close()` | Close the panel. The Config tab's Close button uses it |
| `host.pick` | The one thing tabs share: which job is picked. No tab uses it in this step |

So a tab is built before the panel exists, and needs nothing of it until it is attached.

## Build: the Config tab

**`ConfigTab(view, change, save, refill)`,** in `hallux/panel_tabs/config.py`:

| It is given | What it is |
|---|---|
| `view()` | What to show: a `config.View` (step 2) |
| `change(name, text)` | A new value. Returns `None`, or why not |
| `save()` | Write the file. Returns `None`, or why not |
| `refill()` | Fill every budget again (step 2). Returns a line to show |

The Close button calls `host.close()`.

**What it draws** is the sketch of the design's section 4:

- the path of `config.toml`;
- three groups, by `config.WHEN`: "Changes now", "Changes at the machine's next reboot",
  "Set when Hallux starts (edit config.toml)". A setting that moves in `WHEN` moves here;
- a row per setting: its label, its value, and a note beside it;
- the buttons Refill budgets, Save and Close, and how many changes aren't saved, or what a
  button answered.

**The rows:**

| Setting | Label | Value as shown | The note beside it |
|---|---|---|---|
| `model` | Model | The name | `running now: …`, while another model runs |
| `max_budget_usd` | Budget per boot | `$2.00`, or `none` | `spent in this boot: $1.42`. After a refill: `spent since the refill: $0.10 · this boot: $1.52` |
| `tick_budget_usd` | Tick budget | `$0.25` | `spent by this program: $0.25`, only while a program is on screen |
| `event_budget_usd` | Event budget | `$0.25` | `spent since you typed: $0.00` |
| `effort` | Effort | The effort | `running now: low`, while another one runs; `running now: none` on a model without efforts |
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
- **The text comes from one function** that takes the view and the tab's state, so the
  tests read it as text.

**Its keys and the mouse:**

| Key | What it does |
|---|---|
| ↑ ↓, Tab, Shift+Tab | Move over the six rows that change and the three buttons |
| Enter, or a click | On a row: open it for a change. On a button: press it |
| Typing, in an open row | A name or a number, in a line that starts with the value as it is |
| ↑ ↓, in an open Effort or Model row | Pick from the list |
| Enter, in an open row | Take the value: `change(name, text)`. A reason comes back: it is shown, and the row stays open |
| Esc, in an open row | Leave the row as it was. That is the tab's `leave()` |

- **Effort** is picked from its five values. Nothing is typed.
- **Model and Fallback model** are typed, with a list to pick from: the three names in
  Hallux's help (Opus 5.5, Sonnet 5.5, Haiku 4.5), the model that runs and the one in the
  settings. `config.py` holds the three names. The Fallback model's list starts with
  `none`.
- **An empty line** means none, for the budget per boot and the fallback model.
- **A wrong model name can't be told from a right one here.** The row's note says what a
  wrong one does: `a wrong name fails the next answer`, or, for a name that only acts at a
  boot, `a wrong name ends Hallux at the next boot`.
- **Save** calls `save()`. The tab then says `saved`, or the reason.
- **Refill budgets** calls `refill()` and shows the line it returns. It asks no question,
  and it changes nothing that Save would write: the count of unsaved changes stays.
- **A window too short** for all of it: the rows scroll with the row you are on. The buttons
  and the foot stay.

## Tests

With the keys from a pipe and an output that goes nowhere, as the terminal's tests.

In `tests/test_panel.py`, the host with stand-in tabs:

- the tab row: every title, the brackets on the shown one, and with one tab too;
- a letter shows its tab, and so does a click on its title;
- while the shown tab is typing, a letter goes to the tab and the tab stays;
- a disabled tab is grey; its letter and a click change nothing, and the foot has its
  reason;
- a tab's keys act while it is shown and not after another tab was chosen;
- the panel opens on the tab that wants to be first, and on the last one when none does;
- two tabs that start with the same letter are refused, with both titles;
- Esc with a tab that has something to leave: the tab is asked, and the panel stays open;
- Esc otherwise closes, Ctrl+F12 closes from anywhere, and `wait_closed` returns each time;
- Esc and Ctrl+F12 pressed one right after the other close it once, without an error;
- Esc alone closes within a fifth of a second, and an arrow key doesn't close;
- a tab calls `host.show` with another tab's title, and that tab is shown; `host.close`
  closes the panel;
- the hard exit key calls `power_cut`; Ctrl-C calls `ctrl_c` and doesn't close;
- the foot shows the hint line of the shown tab.

In `tests/test_panel_config.py`, the Config tab in a real panel. `view`, `change`, `save`
and `refill` are fakes that note their calls:

- the text: the three groups, each value as the table says, the notes, a paused budget, a
  setting from a flag, the count of unsaved changes;
- a setting whose `WHEN` is changed is drawn in the other group;
- down, Enter, a number, Enter: `change` gets the name and the text, and the row closes;
- a refused value: the reason is on the row, the row is still open, Esc leaves it within a
  fifth of a second and the panel stays open, and `change` wasn't called again;
- Effort: Enter, down, Enter gives the next of the five;
- Model: a name picked from the list, and a name typed, with an `a` in it;
- an empty budget per boot gives `change("max_budget_usd", "")`;
- Save calls `save` once, and the tab says `saved`, or the reason it returned;
- Refill budgets calls `refill` once and shows its line; `change` and `save` weren't called,
  and the count of unsaved changes is as before;
- the budget per boot's note has one number without a refill, and both after one;
- the Close button closes the panel;
- a click on a row opens it;
- on a window of ten rows, the row you are on and the buttons are both drawn.

## Done when

On a pipe: the panel opens on Config, the tick budget is changed to 1.25, Save is pressed
and Esc closes it. The fakes got exactly `change("tick_budget_usd", "1.25")` and one
`save()`. And a stand-in tab, added to the list in a test, is in the tab row and can be
chosen with its letter.
