# Plan: the config panel

**Status:** written on 2026-10-04, and **built: all eight steps, with the live run, on
2026-10-05.** The user declared it built that day. What each step built is in the table
under [The steps](#the-steps), and two things are left for later: the Refill budgets button
has not been pressed in a real run, and Esc has not been tried over ssh
([step 8](08-live-run.md)). The design it follows is
[config-panel.md](../../config-panel.md), in which no question is open. The decisions this
plan takes on its own are in a table below. They are my proposals, and the user hasn't
confirmed them yet. The two checks that had to happen before parts of the build are both
done; they are under [Before the build](#before-the-build).

**Reviewed on 2026-10-04:** [plans-review-2026-10-04.md](../../plans-review-2026-10-04.md).
It found four things that would have gone wrong and a list of gaps. The user accepted a fix
for each, and they are in the steps. [After the review](#after-the-review) lists them.

**How this plan is laid out.** Like the music addon's plan. This file holds what the steps
share: how the parts fit, the decisions, where the code goes, and the status. Every step has
a file of its own in this folder. A step is built and merged by itself, so whoever builds one
reads this file and that step's file.

## In short

1. **Checking and saving a setting:** one setting can be checked by itself, and `config.toml`
   can be changed line by line.
2. **A setting changes in a running machine:** the machine takes a new value, tells the
   panel what to show, and can fill its budgets again.
3. **The budget per boot:** Hallux checks it itself, so it can be raised without a restart.
4. **Switching the model:** a running session goes on with another model. This step starts
   with a live check.
5. **The panel by itself:** the host with its tab system, and the Config tab with its rows,
   changing one, Save and Close. Tried on a pipe.
6. **The panel at the shell:** Ctrl+F12 at the prompt and while the AI answers, the
   alternate screen, and what the AI writes meanwhile is kept.
7. **The panel over a full-screen program:** a layer over the program, and ticks that wait.
8. **The bar, the documentation and the live run.**

Until step 6 nobody can open a panel, and a running machine behaves as today. The one
exception is step 3: from there, a boot that has used its budget holds messages back, where
today the SDK ends the answer with an error. Ctrl-D still leaves such a machine, at the
shell. In a full-screen program the hard exit is the only way out until step 7.

---

## How the parts fit

```text
 keyboard ─► Terminal ── Ctrl+F12 ──► Panel  (hallux/panel.py)
                │                       │  the tab row, switching, open and close
                │                       ▼
                │                    Config tab  (hallux/panel_tabs/config.py)
                │                       │  view()              what to show
                │                       │  change(name, text)  a new value, or why not
                │                       │  save()              write config.toml
                │                       │  refill()            fill every budget again
                │                       ▼
                │                    Machine ──► config.typed(), config.save()
                │                       ├─ hardware   the settings as they are now
                │                       ├─ running    what this boot's session started with
                │                       └─ unsaved    what Save would write
                ▼
        the AI's text: printed, or kept while the panel is open at the shell
```

**One change, from start to end.** A player runs full screen, and its live updates are
paused because the tick budget is used up.

1. You press Ctrl+F12. In a full-screen program block mode has the keyboard, and it puts the
   panel over the program as a layer (step 7).
2. The panel opens on its Config tab. The tab asks `view()` and shows the rows, with what
   was spent beside each budget (steps 2 and 5).
3. You pick "Tick budget", type `1.25` and press Enter. The tab calls
   `change("tick_budget_usd", "1.25")`.
4. The machine turns the text into a value and checks it (step 1). It replaces its settings,
   notes the change as unsaved, and writes a line to the log (step 2).
5. You press Esc. The layer goes, and the program is as it was. Its clock starts again, so
   it ticks (step 7).
6. Later you open the panel again and press Save. The machine calls `config.save()`, which
   replaces one line of `config.toml` (step 1).

**The one rule for the machine:** an answer of the AI isn't finished, for the machine, until
the visit to the panel is over: the panel is gone, the bar is back, and what was kept is
printed. The answer's cost goes onto the bar at once. Everything that follows an answer
waits: the next prompt, a new screen, a halt, a reboot.

---

## Decisions this plan takes

**From the design.** The plan follows its decision tables. The first row below began as a
difference from the design; after the review the design was changed to say the same.

**What the design leaves open, decided here.** These are my proposals. The user hasn't gone
through this table, apart from what the review settled.

| Topic | Decision | Why |
|---|---|---|
| A new screen while the panel covers a program | It is shown when the panel closes, not put under it | The panel covers the program, so the only thing to see is the old screen for a moment after the panel closes. And block mode's `show()`, which replaces the layout and takes the focus, needn't change |
| The AI's answer ends while the panel is open | The end of the answer waits for the whole visit to the panel. Its cost is put on the bar before that | One place to wait, and all that follows an answer waits with it. Checked: if the machine goes on instead, the panel gets no keys, and keys for the next prompt are lost |
| Keys that were typed for the next prompt | The terminal takes them out before the panel runs and puts them back after | Every prompt_toolkit app feeds itself the stored keys when it starts. An Enter among them would press a button in the panel |
| Typing in the panel over a program with vi keys | The app edits the plain way while the panel is open | The editing keys belong to the whole app, and a model name would run as vi commands |
| A scripted run that reaches its cap | It halts | Nobody is at a script's keyboard to raise the cap, and a held line would be glued to the next |
| The notes on the bar | The machine keeps them by reason and takes away only the one whose reason is gone | The bar has one slot, and two budgets can be used up at once |
| What a tab can ask of the host | Three things, handed over once: show another tab, close the panel, the picked job | A tab is built before the panel exists, and the Agents tab has to show Details |
| Where a setting is checked | `config.check(name, value)`, and `load` uses it for every setting | One set of rules and words for the file and for the panel |
| What the Config tab calls | Four functions it is given: `view`, `change`, `save`, `refill`. The machine provides them | The tab knows nothing of the machine, and its tests pass fakes |
| How a refill counts the budget per boot | The machine notes what the boot had spent at the refill, and the cap counts from there | The session's own running total can't be set back: each answer's cost is worked out from it |
| A refill, step by step | It fills the event and tick budgets from step 2, the budget per boot from step 3, and makes a paused program tick again from step 7 | Each step adds the budget it makes Hallux's own |
| What the host asks of a tab | Nine things, listed in step 5: its title, its part of the screen, its keys, its hint line, whether it is typing, whether it is disabled, whether the panel should open on it, what Esc leaves, and a call when it is shown | The design says what a tab is. The plan gives each part a name |
| The tab row with one tab | It is drawn: `[ Config ]` | The screen has the same shape before and after addon agents add their two tabs |
| Two tabs with the same first letter | The host refuses the list when it is built | A mistake in the code should be loud, not a key that picks the wrong tab |
| Which tab the panel opens on | The first that asks to be first, otherwise the last in the row. Config never asks and is last | The host then needn't know what a job is |
| Who holds the changes that aren't saved | The machine, in `unsaved` | It holds the settings already |
| What the bar shows | The model and the effort of the running session. The machine sets them at each boot and at a model switch | The design, section 5: the bar shows what runs |
| The writer's safety check | The new text has to parse to exactly the old settings plus the changes. If it doesn't, nothing is written | It catches a value over several lines, and anything else the change line by line gets wrong, without code for each |
| A message held back by the budget, in a full-screen program | The action is dropped, the program goes on taking keys, and its fields count as not yet seen by the AI | Showing the same form again would put the AI's text over what you typed |
| How the model is switched | The new name is set aside, and the session is switched just before the next message goes out | That is "from the next answer", and nothing reaches into an answer that is being written |
| An event while the panel is open at the prompt | It is remembered. When the panel closes, the prompt ends the way an event ends it today | Otherwise the machine asks a hundred times a second whether the prompt is up |
| The key's name in the code | `OPEN_KEY = "c-f12"`, beside `POWER_CUT_KEY` in `hallux/blockmode.py` | The panel, the terminal and block mode all need both keys. In the panel's file, block mode and the panel would import each other |
| A window too short for the panel | The rows scroll. The buttons and the foot stay | A panel that can't be closed on a small window would be a trap |
| A number in `config.toml` | Written as Python prints it: `1.25`, `2.0` | |

---

## Checked before the plan

With throwaway scripts: prompt_toolkit 3.0.53 on a pipe, no model call. The first six points
are in the design's status. The last one I checked while writing this plan.

- Ctrl+F12 arrives as one key, `c-f12`.
- While the AI works, a second full-screen app takes the keyboard and gives it back.
- If the AI's answer ends and the machine moves on while that app is open, the app is deaf.
  If the end of the answer waits for it, all is well.
- At the prompt, a key can end the prompt, the panel can run, and the typed line comes back.
- Esc closes after 0.05 seconds when the wait is set to that, and an arrow key stays an
  arrow.
- A layer over a full-screen program gets the keys, also in a raw-mode program. While the AI
  is busy with the screen, block mode holds every key, and the layer gets none: step 7
  changes that.
- The other way to let an answer end under the panel also works: the answer's keyboard
  reader is handed to the panel and taken off when it closes. The plan doesn't use it. The
  wait is simpler.

---

## Before the build

| Check | Who | Before | What it decides | Status |
|---|---|---|---|---|
| Run `cat -v`, press Ctrl+F12: `^[[24;5~` should appear | The user, in the terminal Hallux runs in | Step 6 | The key. If nothing arrives, another key takes its place, and only `OPEN_KEY` changes | **Done on 2026-10-04:** `^[[24;5~` appeared. The key is Ctrl+F12 |
| Switch the model of a running session, with a model call | Whoever builds step 4, when the user says go. A few cents | Step 4 | Whether the model changes at once or at the next reboot, and what happens with Haiku | **Done on 2026-10-05:** it changes with the next answer, also to and from Haiku. The check cost $0.22. The numbers are in step 4's file |

---

## Where the code goes

| File | What | Step |
|---|---|---|
| `hallux/config.py` | `check`, `typed`, `save`, the table of when a setting takes effect | 1 |
| `hallux/config.py` | `View`: what the panel is shown | 2 |
| `hallux/machine.py` | `view`, `change`, `save`, `refill`; `running` and `unsaved`; the bar at each boot | 2 |
| `hallux/app.py` | Tells the machine which settings came from flags | 2 |
| `hallux/script.py` | The scripted terminal takes a status before it has a record | 2 |
| `hallux/machine.py` | The budget per boot checked before a message goes out; Ctrl-D halts a machine that is over it | 3 |
| `hallux/blockmode.py`, `hallux/terminal.py` | `keep_form`: a program goes on without an answer | 3 |
| `hallux/script.py` | It says that nobody is at its keyboard, so a scripted run halts at its cap; an empty `keep_form` | 3 |
| `hallux/config.py` | `max_budget_usd` moves to `now` in the table of when a setting takes effect | 3 |
| `hallux/machine.py` | The model switched before the next message | 4 |
| `hallux/config.py` | `model` moves to `now`, if the check passes | 4 |
| `hallux/panel.py` (new) | The host: the tab row, switching, opening and closing | 5 |
| `hallux/panel_tabs/config.py` (new) | The Config tab. One file per tab; addon agents add two more later | 5 |
| `hallux/config.py` | The three model names the Config tab offers | 5 |
| `hallux/terminal.py` | Ctrl+F12 at the prompt and while the AI works; the alternate screen; what is written kept; the wait | 6 |
| `hallux/machine.py` | An answer's cost onto the bar while the answer still counts as running | 6 |
| `hallux/app.py` | Builds the panel and hands it to the terminal | 6 |
| `hallux/blockmode.py` | The two key names, side by side | 5 |
| `hallux/blockmode.py` | The layer; its keys while the AI is busy; plain typing over vi keys; ticks that wait; `set_tick` | 7 |
| `hallux/machine.py` | The tick a program asked for, so that it can tick again | 7 |
| `hallux/statusbar.py`, `hallux/machine.py` | The key in the idle hint, and in the note of a used-up budget per boot | 8 |
| `README.MD`, `docs/` | The panel, what changes when, the status lines, the roadmap | 8 |
| `tests/test_config.py`, `test_machine.py`, `test_terminal.py`, `test_blockmode.py`, `test_statusbar.py`, `test_script.py` | More tests in each | 1 to 8 |
| `tests/test_panel.py`, `tests/test_panel_config.py` | New | 5 |

`hallux/script.py` also gets an empty `set_tick` in step 7: a scripted run has no panel.
The fake terminals of the tests get the same empty methods.

**The line numbers** in the steps are the code's of 2026-10-04. Every step moves them for
the next one, so each reference also names what stands there.

---

## The steps

Each step can be merged by itself. A step needs the ones named beside it.

| Step | File | Needs | Status |
|---|---|---|---|
| 1. Checking and saving a setting | [01-saving.md](01-saving.md) | | Built on 2026-10-05 |
| 2. A setting changes in a running machine | [02-changes.md](02-changes.md) | 1 | Built on 2026-10-05 |
| 3. The budget per boot | [03-budget.md](03-budget.md) | 2 | Built on 2026-10-05 |
| 4. Switching the model | [04-model.md](04-model.md) | 2 | Built on 2026-10-05, after step 5 |
| 5. The panel by itself | [05-panel.md](05-panel.md) | 2 | Built on 2026-10-05 |
| 6. The panel at the shell | [06-shell.md](06-shell.md) | 5 | Built on 2026-10-05, and tried by the user: "now it works perfectly" |
| 7. The panel over a full-screen program | [07-full-screen.md](07-full-screen.md) | 3, 6 | Built on 2026-10-05, and tried by the user: "this is really working nicely" |
| 8. The bar, the documentation and the live run | [08-live-run.md](08-live-run.md) | 4, 7 | Built on 2026-10-05, and the live run is done: the user went through every point. One small thing no real run has shown yet, the Refill budgets button, is named in the step's file |

Steps 3, 4 and 5 don't depend on each other, and any of them can come first. This table is
the only place that holds the status.

---

## After the review

What the review of 2026-10-04 changed in the steps. The user accepted all of it.

| Step | What changed |
|---|---|
| 1 | The file is read and written with its own line endings. A number has to be finite. What the safety check catches is said as it is |
| 2 | The same value is no change. The scripted terminal takes a status before it has a record. A note on the bar has an owner. A lowered budget pauses at once |
| 3 | Ctrl-D on an empty line halts a machine that is over its cap. A scripted run halts at its cap. The check comes before a password is looked at. `send` itself never holds a message back |
| 4 | A switch that fails is a note on the bar, not the bar's error. The Effort row says `none` on a model without efforts |
| 5 | The host hands every tab three things: show another tab, close, the picked job. The container is without the bar. Esc acts at once. The two key names sit side by side in block mode's file |
| 6 | The type-ahead is taken out before the panel runs. The end of an answer waits for the whole visit. The password prompt forgets that it was erased |
| 7 | Typing in the panel is plain typing over a program with vi keys. A full-screen app that dies takes the panel with it |
| 8 | The power-off keys come first in the hint. Three more places in the documentation |

---

## Risks

- **The key reaches Hallux in the user's terminal:** checked on 2026-10-04. Another terminal
  program may keep the chord for itself. Then only `OPEN_KEY` changes.
- **A wrong model name that is saved ends Hallux at the next boot,** and at every start after
  it, until the file is edited or `--model` is passed. Nothing in Hallux knows which names
  exist. The Model row says so.
- **The model switch works,** also to and from Haiku: checked on 2026-10-05 (step 4). The
  first answer on the new model costs more, once: it reads the whole conversation of the
  boot at the full price.
- **I can't see a real terminal.** Every test here runs on a pipe, with an output that goes
  nowhere. Whether the shell's screen is back exactly, with its scrollback and the pinned
  bar, shows only in the live run (step 8). Full-screen programs come and go that way today,
  so I expect it.
- **Three readers of one keyboard, and now a fourth.** The prompt, the reader that runs
  while the AI works, block mode, and the panel. The checks showed that the order in which
  they let go matters. The rule above, that an answer's end waits for the panel, keeps that
  order, and steps 6 and 7 each test it.
- **The budget per boot is checked between answers.** One answer can go over it. How far is
  measured in the live run.
- **A wrong model name isn't switched to.** The session refuses it, the bar says
  `model not switched`, and the answers go on from the model that ran. Saved, it still ends
  Hallux at the next boot.
- **This plan and the plan for addon agents change the same files:** `terminal.py`,
  `blockmode.py`, `statusbar.py`, `config.py` and `machine.py`. They are built one after the
  other, this one first.
