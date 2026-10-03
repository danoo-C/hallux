# Plan: the config panel

**Status:** written on 2026-10-04. Nothing is built. The design it follows is
[config-panel.md](../../config-panel.md), in which no question is open. The decisions this
plan takes on its own are in a table below. They are my proposals, and the user hasn't
confirmed them yet. Two checks have to happen before parts of the build; they are under
[Before the build](#before-the-build).

**How this plan is laid out.** Like the music addon's plan. This file holds what the steps
share: how the parts fit, the decisions, where the code goes, and the status. Every step has
a file of its own in this folder. A step is built and merged by itself, so whoever builds one
reads this file and that step's file.

## In short

1. **Checking and saving a setting:** one setting can be checked by itself, and `config.toml`
   can be changed line by line.
2. **A setting changes in a running machine:** the machine takes a new value, and tells the
   panel what to show.
3. **The budget per boot:** Hallux checks it itself, so it can be raised without a restart.
4. **Switching the model:** a running session goes on with another model. This step starts
   with a live check.
5. **The panel by itself:** the rows, changing one, Save and Close, tried on a pipe.
6. **The panel at the shell:** Ctrl+F12 at the prompt and while the AI answers, the
   alternate screen, and what the AI writes meanwhile is kept.
7. **The panel over a full-screen program:** a layer over the program, and ticks that wait.
8. **The bar, the documentation and the live run.**

Until step 6 nobody can open a panel, and a running machine behaves as today. The one
exception is step 3: from there, a boot that has used its budget holds messages back, where
today the SDK ends the answer with an error.

---

## How the parts fit

```text
 keyboard ─► Terminal ── Ctrl+F12 ──► Panel  (hallux/panel.py)
                │                       │  view()              what to show
                │                       │  change(name, text)  a new value, or why not
                │                       │  save()              write config.toml
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

1. You press Ctrl+F12. The terminal sees that a full-screen program is on, and block mode
   puts the panel over it as a layer (step 7).
2. The panel asks `view()` and shows the rows, with what was spent beside each budget
   (steps 2 and 5).
3. You pick "Tick budget", type `1.25` and press Enter. The panel calls
   `change("tick_budget_usd", "1.25")`.
4. The machine turns the text into a value and checks it (step 1). It replaces its settings,
   notes the change as unsaved, and writes a line to the log (step 2).
5. You press Esc. The layer goes, and the program is as it was. Its clock starts again, so
   it ticks (step 7).
6. Later you open the panel again and press Save. The machine calls `config.save()`, which
   replaces one line of `config.toml` (step 1).

**The one rule for the machine:** an answer of the AI isn't finished, for the machine, until
the panel is closed. The answer's cost goes onto the bar at once. Everything that follows an
answer waits: the next prompt, a new screen, a halt, a reboot.

---

## Decisions this plan takes

**From the design.** The plan follows its decision tables, with one difference in how, not
in what you see: the first row below.

**What the design leaves open, decided here.** These are my proposals. Not confirmed yet.

| Topic | Decision | Why |
|---|---|---|
| A new screen while the panel covers a program | It is shown when the panel closes. The design says it goes under the panel while that is open | You can't see the difference: the panel covers the program. And block mode's `show()`, which replaces the layout and takes the focus, needn't change |
| The AI's answer ends while the panel is open | The end of the answer waits for the panel. Its cost is put on the bar before that | One place to wait, and all that follows an answer waits with it. Checked on 2026-10-03: if the machine goes on instead, the panel gets no keys |
| Where a setting is checked | `config.check(name, value)`, and `load` uses it for every setting | One set of rules and words for the file and for the panel |
| What the panel calls | Three functions it is given: `view`, `change`, `save`. The machine provides them | The panel knows nothing of the machine, and its tests pass fakes |
| Who holds the changes that aren't saved | The machine, in `unsaved` | It holds the settings already |
| What the bar shows | The model and the effort of the running session. The machine sets them at each boot and at a model switch | The design, section 5: the bar shows what runs |
| The writer's safety check | The new text has to parse to exactly the old settings plus the changes. If it doesn't, nothing is written | It catches a value over several lines, a setting that is there twice and a table, without code for each |
| A message held back by the budget, in a full-screen program | The action is dropped, the program goes on taking keys, and its fields count as not yet seen by the AI | Showing the same form again would put the AI's text over what you typed |
| How the model is switched | The new name is set aside, and the session is switched just before the next message goes out | That is "from the next answer", and nothing reaches into an answer that is being written |
| An event while the panel is open at the prompt | It is remembered. When the panel closes, the prompt ends the way an event ends it today | Otherwise the machine asks a hundred times a second whether the prompt is up |
| The key's name in the code | `OPEN_KEY = "c-f12"`, in `hallux/panel.py` | The terminal and block mode both need it |
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

| Check | Who | Before | What it decides |
|---|---|---|---|
| Run `cat -v`, press Ctrl+F12: `^[[24;5~` should appear | The user, in the terminal Hallux runs in | Step 6 | The key. If nothing arrives, another key takes its place, and only `OPEN_KEY` changes |
| Switch the model of a running session, with a model call | Whoever builds step 4, when the user says go. A few cents | Step 4 | Whether the model changes at once or at the next reboot, and what happens with Haiku |

---

## Where the code goes

| File | What | Step |
|---|---|---|
| `hallux/config.py` | `check`, `typed`, `save`, the table of when a setting takes effect | 1 |
| `hallux/config.py` | `View`: what the panel is shown | 2 |
| `hallux/machine.py` | `view`, `change`, `save`; `running` and `unsaved`; the bar at each boot | 2 |
| `hallux/app.py` | Tells the machine which settings came from flags | 2 |
| `hallux/machine.py` | The budget per boot checked before a message goes out | 3 |
| `hallux/blockmode.py`, `hallux/terminal.py` | `keep_form`: a program goes on without an answer | 3 |
| `hallux/machine.py` | The model switched before the next message | 4 |
| `hallux/panel.py` (new) | The panel | 5 |
| `hallux/config.py` | The three model names the panel offers | 5 |
| `hallux/terminal.py` | Ctrl+F12 at the prompt and while the AI works; the alternate screen; what is written kept; the wait | 6 |
| `hallux/machine.py` | An answer's cost onto the bar while the answer still counts as running | 6 |
| `hallux/app.py` | Builds the panel and hands it to the terminal | 6 |
| `hallux/blockmode.py` | The layer; its keys while the AI is busy; ticks that wait; `set_tick` | 7 |
| `hallux/machine.py` | The tick a program asked for, so that it can tick again | 7 |
| `hallux/statusbar.py`, `hallux/machine.py` | The key in the idle hint, and in the note of a used-up budget per boot | 8 |
| `README.MD`, `docs/` | The panel, what changes when, the status lines, the roadmap | 8 |
| `tests/test_config.py`, `test_machine.py`, `test_terminal.py`, `test_blockmode.py`, `test_statusbar.py` | More tests in each | 1 to 8 |
| `tests/test_panel.py` | New | 5 |

`hallux/script.py` gets two empty methods, `keep_form` (step 3) and `set_tick` (step 7): a
scripted run has no panel, and the fake terminals of the tests get the same two.

---

## The steps

Each step can be merged by itself. A step needs the ones named beside it.

| Step | File | Needs | Status |
|---|---|---|---|
| 1. Checking and saving a setting | [01-saving.md](01-saving.md) | | Not built |
| 2. A setting changes in a running machine | [02-changes.md](02-changes.md) | 1 | Not built |
| 3. The budget per boot | [03-budget.md](03-budget.md) | 2 | Not built |
| 4. Switching the model | [04-model.md](04-model.md) | 2 | Not built |
| 5. The panel by itself | [05-panel.md](05-panel.md) | 2 | Not built |
| 6. The panel at the shell | [06-shell.md](06-shell.md) | 5 | Not built |
| 7. The panel over a full-screen program | [07-full-screen.md](07-full-screen.md) | 3, 6 | Not built |
| 8. The bar, the documentation and the live run | [08-live-run.md](08-live-run.md) | 4, 7 | Not built |

Steps 3, 4 and 5 don't depend on each other, and any of them can come first. This table is
the only place that holds the status.

---

## Risks

- **The key may not reach Hallux.** Some terminals keep key chords for themselves. The check
  under "Before the build" is ten seconds of the user's time, and it comes before step 6.
- **The model switch may not work,** or not with Haiku. Then the model changes at the next
  reboot, as the design says, and step 4 shrinks to a few lines.
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
- **A wrong model name shows late:** as "model failed" on the bar, with the next answer.
  Nothing in Hallux knows which names exist.
- **This plan and the plan for addon agents change the same files:** `terminal.py`,
  `blockmode.py`, `statusbar.py`, `config.py` and `machine.py`. They are built one after the
  other, this one first.
