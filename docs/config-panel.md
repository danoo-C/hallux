# The config panel

**Status:** designed on 2026-10-03, and built on 2026-10-05 in the eight steps of
[plans/config-panel](plans/config-panel/README.md). Each step's file says under "As built"
where the code went another way than this page. The user went through the live run in
their own terminal the same day; what it showed is in the plan's
[step 8](plans/config-panel/08-live-run.md) and under
[Still to find out](#still-to-find-out). The idea is the user's: a
panel inside Hallux that changes the machine's settings while it runs, saves them, and gives
the screen back exactly as the AI made it. The user also chose the key, how the panel
closes, and that it takes the mouse. The rest was my proposal, and the user accepted all of
it. The answers are part of the sections, and [Decisions](#decisions) lists them with what
was turned down.

**Tabs, decided on 2026-10-04.** The panel became a screen with three tabs: Agents, Details
and Config. This document has the tab system and the Config tab (section 4). The other two
show the jobs of addon agents. They are described in
[addon-agents.md](addon-agents.md), section 17, and are added when that feature is built.
Until then the panel has one tab. The document kept its name.

**What I checked on 2026-10-03,** with two throwaway scripts (prompt_toolkit 3.0.53 on a
pipe, the way the tests drive it; no model call, nothing written):
- **Ctrl+F12 arrives as one key,** `c-f12`. prompt_toolkit maps its sequence already.
- **While the AI works, a second full-screen app takes the keyboard,** and the keyboard goes
  back when it closes.
- **If the AI's answer ends while that app is open, and Hallux moves on, the app is deaf.**
  It gets no key any more, not even the one that closes it. So the machine has to wait for
  the panel.
- **At the shell prompt** a key can end the prompt, the panel can run, and the line that was
  being typed comes back.
- **Esc alone** closes after 0.5 seconds by default, and after 0.05 seconds when the wait is
  set to that. An arrow key, which starts with Esc, was still read as an arrow.
- **A layer over a full-screen program gets the keys,** also in a raw-mode program, where
  every key goes to the AI today. The text typed into the program's field was still there
  afterwards, and nothing was sent to the AI.
- **Block mode holds every key while the AI is busy with a program's screen,** and a new
  screen from the AI replaces the layout and takes the focus. The first has to change; the
  second is avoided (section 8).

**Reviewed on 2026-10-04,** with the plan:
[plans-review-2026-10-04.md](plans-review-2026-10-04.md). The fixes are in the sections, and
[Decisions](#decisions) has what the user decided then.

**What the user checked on 2026-10-04:** Ctrl+F12 reaches a program in their terminal. They
ran `cat -v` and pressed it, and `^[[24;5~` appeared: the sequence prompt_toolkit maps.

**What was checked with model calls on 2026-10-05:** switching the model of a running
session. It works, also to and from Haiku. The numbers are in the plan's
[step 4](plans/config-panel/04-model.md).

What is still open is in [Still to find out](#still-to-find-out).

## In short

1. **Ctrl+F12 opens a panel that belongs to Hallux,** like the status bar. The AI is never
   told about it, can't open it and can't draw on it.
2. **It opens everywhere:** at the shell prompt, while the AI answers, and in a full-screen
   program.
3. **It shows the machine's settings,** grouped by when a change takes effect: now, at the
   machine's next reboot, or only when Hallux starts.
4. **A change counts when you make it.** Save writes it to `config.toml`. Esc, the Close
   button or Ctrl+F12 leave the panel.
5. **The budgets and the model change while the machine runs.** The effort changes at the
   next reboot: nothing can change it in a running session.
6. **The screen comes back as the AI made it.** At the shell the panel uses the terminal's
   alternate screen, and what the AI writes meanwhile is kept and printed afterwards. In a
   full-screen program the panel is a layer over the program.
7. **While the panel is open, nothing new is sent to the AI.** What it is doing, it finishes.
8. **Saving keeps your file.** Only the lines of the settings you changed are touched.
9. **The panel has tabs,** and each tab is a file of its own in the code. Config is the tab
   for the settings. Agents and Details come with addon agents.
10. **One button fills every budget again.** The counting starts anew at the same limits,
    and what was paused goes on. The total on the bar keeps counting.

---

## 1. What it's for, and what it isn't

Today a setting changes in two steps: edit `<world>/.hallux/config.toml`, then start Hallux
again. The session is gone then, and with it everything the machine had in its RAM.

In the live run of the music addon the tick budget of $0.25 ran out after about 100 seconds
of song, and the player stopped moving. The user raised the budget in the file for that
world. With the panel it is Ctrl+F12, a new number, Esc, and the player moves again.

- **It isn't part of the machine.** It is no command and no program. The prompt doesn't
  mention it, and the AI never learns that it was open.
- **It isn't a second place for settings.** It shows what `config.toml` and the flags
  decided, checks a value by the same rules, and saves to the same file.
- **It doesn't make everything live.** A session gets its effort when it starts, so a new
  effort waits for the next reboot. The panel says so on the row.

---

## 2. The model: the settings window of a virtual machine

| On a real computer | In Hallux |
|---|---|
| The case: a power button and a light | The hard exit and the status bar |
| The settings window of a virtual machine, opened with a host key | The config panel, on Ctrl+F12 |
| The guest system can't open that window or change what is in it | The AI can't |
| The guest runs on while the window is open | The AI finishes what it is doing |
| Some settings need a reboot of the guest | The effort and the fallback model |
| Some need the whole program to start again | The status bar and the addons |
| The settings are stored outside the guest's disk | `/.hallux/config.toml`, which the machine can't see |
| The window goes away and the guest's picture is as it was | The screen is the AI's again, unchanged |

---

## 3. Opening and closing

- **Ctrl+F12 opens it.** Esc, the Close button, or Ctrl+F12 again close it.
- **Why this key.** F1 to F12 belong to the machine: at the shell they go to the AI
  (`hallux/terminal.py:54`), and programs like htop and mc use them. No program needs
  Ctrl+F12, and prompt_toolkit already maps its sequence, `\x1b[24;5~`.
- **The bar names the key.** The idle hint becomes
  `power off: ctrl+shift+del · config: ctrl+f12 · ctrl+c ×3`. The power-off keys come first:
  on a narrow window the hint loses its last parts, and the way out must be the last to go.
- **The mouse works in the panel:** a click picks a row or presses a button. At the shell
  the mouse is off again when the panel closes, so your terminal's own text selection and
  wheel stay as they are.
- **The hard exit works inside the panel:** Ctrl+Shift+Del, and Ctrl-C three times. One
  Ctrl-C does nothing there.
- **Esc is quick.** prompt_toolkit waits after Esc, to tell it from the start of an arrow
  key. The panel sets that wait to 0.05 seconds, and binds Esc so that it acts at once also
  while a row is open for typing; otherwise it would wait a second there.
- **Which tab it opens on:** Agents while a job of an addon agent runs, otherwise Config.

**Where the machine is when you press it:**

| The machine is | The panel | The machine meanwhile |
|---|---|---|
| At the shell prompt | Opens. When it closes, the line you were typing is back | Waits. Events from addons wait too |
| Answering, at the shell | Opens at once | The answer goes on. What it writes is kept, and printed when the panel closes. The next prompt waits |
| In a full-screen program, waiting for you | Opens over the program | Ticks wait |
| In a full-screen program, the AI busy with it | Opens over the program | The answer goes on. The new screen is shown when the panel closes |
| At a password prompt | Opens. What was typed of the password is dropped | Waits |
| Running a `--script` | There is none: a script has no keyboard | |

---

## 4. What the panel shows

**The tabs.** The top row names them, and the tab that is shown has brackets:

```text
 Hallux                                         Agents   Details  [ Config ]
```

| Tab | What it shows | Described in |
|---|---|---|
| Agents | The jobs of addon agents, and the agents that are idle | [addon-agents.md](addon-agents.md), section 17 |
| Details | One job, live: what it is doing | The same |
| Config | The machine's settings | Below |

- **The first letter of each tab is its key,** and is underlined: `a`, `d`, `c`. Underlined,
  not bold: bold looks like plain text in some terminal fonts. A click on a tab's name
  does the same.
- **The letters don't act while you type.** In the Config tab you type model names, so `a`
  can't jump to Agents then. They act when no row is open for typing.
- **A tab can be disabled.** It is then dark grey, and choosing it puts the reason in the
  foot. On a machine without an addon that has an agent, Agents and Details are disabled:
  `no attached addon has an agent`.
- **Until addon agents are built, Config is the only tab.** The grey tabs arrive with that
  feature, so nobody sees two tabs that can never work.

**A tab is a file of its own,** like a component:

```text
hallux/panel.py               the host: the tab row, switching, opening and closing,
                              the foot, the status bar's row
hallux/panel_tabs/config.py   the Config tab
hallux/panel_tabs/agents.py   the Agents tab    (with addon agents)
hallux/panel_tabs/details.py  the Details tab   (with addon agents)
```

| A tab has | What it is |
|---|---|
| A title | `Config`. Its first letter is its key |
| Its part of the screen | What it draws under the tab row |
| Its keys | They act only while it is the tab that is shown |
| A hint line | The keys the foot shows for it |
| Whether it is typing | While it is, the host leaves the letters to it |
| Whether it is disabled, and why | For the grey tabs |
| The functions it is given | Its data and what it can do. Config gets four: what to show, change a value, save, refill the budgets |
| What the host hands it | Three things: show another tab, close the panel, and the job that is picked |

- **The host knows nothing of what a tab shows.** It gets a list of tabs and draws their
  titles. A new tab is a new file and one more entry in that list.
- **What tabs share lives in the host.** That is one thing: which job is picked. Agents
  picks it, and Details shows it.
- **What every tab gets from the host:** Esc and Ctrl+F12 close, the hard exit works, the
  bar is on the last row.

**The Config tab,** a sketch. The last row is Hallux's status bar, which stays where it is.

```text
 Hallux                                         Agents   Details  [ Config ]

  test-hallux/.hallux/config.toml

  Changes now
    Model              claude-opus-5-5
    Budget per boot    $2.00          spent in this boot: $1.42
    Tick budget        $0.25          spent by this program: $0.25 (paused)
    Event budget       $0.25          spent since you typed: $0.00

  Changes at the machine's next reboot
    Effort             high           running now: low
    Fallback model     none

  Set when Hallux starts (edit config.toml)
    Status bar         on
    Addons             music, window
    Transcripts        off
    OS sandbox         off

    [ Refill budgets ]   [ Save ]   [ Close ]      2 changes not saved

 ↑ ↓ move · Enter change · a d c tabs · Esc close
 ⠹ thinking…                                    opus 5.5 · low · $1.42 · 0.8s
```

**The rows:**

| Row | Setting in `config.toml` | What you enter |
|---|---|---|
| Model | `model` | A model name: free text, with a short list to pick from |
| Budget per boot | `max_budget_usd` | Dollars, more than 0. Empty means no cap |
| Tick budget | `tick_budget_usd` | Dollars, 0 or more |
| Event budget | `event_budget_usd` | Dollars, 0 or more |
| Effort | `effort` | One of low, medium, high, xhigh, max |
| Fallback model | `fallback_model` | A model name, or empty for none |
| Status bar, Addons, Transcripts, OS sandbox | `status_bar`, `addons`, `keep_transcripts`, `os_sandbox` | Shown, not changed here |

- **The rows are grouped by when a change takes effect.** That is the honest answer to
  "live": you see before you change a value whether it acts now.
- **What was spent stands beside each budget.** You raise a budget because it ran out, so
  the panel shows how far it is.
- **Changing a row:** Enter or a click opens it. A name or a number is typed, the effort is
  picked from its five values. Enter takes the value, Esc leaves the row as it was.
- **A wrong value isn't taken,** and the row says why, with the words `config.toml` would
  get: "must be a number, 0 or more". The checks are the ones in `hallux/config.py:58`.
- **A model name can't be checked in the row.** Any name is taken. The list holds the three
  names Hallux's help names, the model that runs and the one in the settings.
- **A wrong name isn't switched to.** The check of 2026-10-05 showed it: the session refuses
  a name that is no model, and goes on answering from the model it had. The bar says
  `model not switched: Model '…' not found`, and the Model row keeps `running now:` beside
  the name.
- **A wrong name that is saved is worse.** A boot that starts on it fails, and that ends
  Hallux, at every start, until the file is edited or `--model` is passed. The row says so.
- **A row that a flag set says so:** "from --model, for this run".

---

## 5. When a change takes effect

| Setting | Takes effect | Why |
|---|---|---|
| `tick_budget_usd`, `event_budget_usd` | At once | They are Hallux's own counters, read at each use (`hallux/machine.py:250,323`) |
| `max_budget_usd` | At once | Hallux checks it itself (section 6). Today the session gets it when it starts |
| `model` | From the next answer | The SDK switches a running session: `set_model()`. Run on 2026-10-05 |
| `effort`, `fallback_model` | At the machine's next reboot | The session gets them when it starts (`hallux/machine.py:131-132`), and the SDK has no way to change them later |
| `status_bar`, `addons`, `keep_transcripts`, `os_sandbox` | When Hallux starts | The bar and the addons are wired once, at the start (`hallux/app.py:60,68`). The other two could act at a reboot, but this version doesn't change them |

**The budgets:**
- **Raising a budget that is used up lifts its pause.** Events come again at once. A program
  whose live updates were paused ticks again when the panel closes.
- **Lowering a budget below what was spent** pauses at once, as if it had run out.

**Refill budgets,** the button beside Save and Close:

- **It starts the counting of every budget anew,** at the limits as they are:

  | Budget | What starts at zero again |
  |---|---|
  | The budget per boot | What the boot has spent, as the cap counts it |
  | The tick budget | What the program on screen has spent on ticks |
  | The event budget | What events have spent since a line was typed |
  | The budget for all jobs of addon agents, once those exist | What the jobs have spent since it was last filled |

- **What was paused goes on:** events come again at once, a paused program ticks again when
  the panel closes, and a held message can be sent.
- **It doesn't forget the money.** The total on the bar keeps counting, and the row of the
  budget per boot shows both numbers: `spent since the refill: $0.10 · this boot: $1.52`.
- **Why it is there.** Hallux fills budgets by itself already: a typed line fills the event
  budget, leaving a program fills its ticks, a reboot fills the boot's. The button does all
  of that at once, without typing, leaving or rebooting. In a player whose ticks ran out,
  the other way is to raise the tick budget, and then to remember not to save the higher
  number.
- **It asks no question.** One refill allows at most one more round of each budget, and the
  panel shows what was spent beside each.
- **It is an action, not a setting.** Nothing becomes "unsaved", and Save never writes it.
  The log gets a line with what each budget had spent.

**The model:**
- **It switches between two answers.** If the AI is answering, the switch waits for the end
  of that answer.
- **The first answer on the new model costs more, once.** A model has its own cache, so it
  reads the whole conversation of the boot at the full price.
- **How much more:** in the check, the first line on Haiku after a switch cost $0.021, and
  the same line without a switch $0.0015. One line on Opus after a switch cost $0.10. That
  session was three lines old.
- **Haiku is a special case.** It gets no effort (`hallux/config.py:34`). A session that
  started with an effort switches to Haiku and back, and has its effort again afterwards. A
  session that started on Haiku was given no effort, and the bar shows none after a switch
  to another model either.

**The effort:**
- **The panel shows both:** the effort you set, and the one that runs now.
- **The status bar shows what runs.** It changes at the reboot, not when you set the value.
- **The panel doesn't reboot the machine.** A reboot is the machine's own: you type `reboot`.

**The log** gets a line for each change, with the old and the new value, and a line for
each save, with the names of the settings that were written.

---

## 6. The budget per boot becomes Hallux's own check

"Max prices" were the first thing the user named, and `max_budget_usd` is the largest of
them. Today it can't change while the machine runs: Hallux hands it to the session when the
boot starts (`hallux/machine.py:133`), and the SDK ends a query with an error once it is
used up.

**What changes:** Hallux doesn't hand it over any more. It checks the cap itself. It already
knows what the boot has spent after every answer (`hallux/machine.py:476-479`).

- **Before a message goes to the AI,** Hallux compares what the boot has spent with the cap.
- **When the cap is reached, the message isn't sent.** The bar says
  `budget used: $2.00 per boot · raise it: ctrl+f12`. A line you typed stays at the prompt.
- **A full-screen program stays as it is,** and its ticks stop.
- **Raising the cap in the panel lets the next message through.** So does the Refill budgets
  button (section 5): the cap then counts from the refill, not from the start of the boot.
- **Ctrl-D on an empty line halts the machine,** with no message to the AI. That is the way
  out today as well: a failed answer to Ctrl-D halts (`hallux/machine.py:194,389`). A
  `poweroff` typed as a command needs the AI, and so the budget.
- **In a full-screen program** the way out is the panel, or the hard exit.
- **A scripted run halts** when it reaches its cap: nobody is at its keyboard.

**What it costs:** Hallux checks between two answers, so one answer can go over the cap by
what that answer costs. The SDK's cap may stop a session in the middle of an answer; whether
it does isn't known.

---

## 7. Saving

- **Save writes `<world>/.hallux/config.toml`,** the file of this machine.
- **Only the rows you changed in the panel are written.** A setting you didn't touch is never
  written. So a `--model` flag given for one run doesn't end up in the file.
- **Entering the value a row has already is no change.** A row opens with its value in it,
  so Enter on an untouched row would otherwise count, and the flag's value would be saved.
- **The file keeps its line endings,** also Windows ones.
- **The file is changed line by line:**
  - a setting that has a line gets that line replaced, and a comment at its end is kept;
  - a setting without a line gets a new one at the end;
  - an empty budget per boot, or no fallback model, removes its line;
  - every other line stays as it is, your comments included.
- **Hallux writes the lines itself.** Python reads TOML and can't write it. The values are a
  name, a number, or true and false, so that is a few lines of code.
- **The file is read again when you save.** What you changed in an editor meanwhile stays.
- **Nothing broken is written.** The new text has to be valid TOML and pass the checks of
  `hallux/config.py`. If it doesn't, or if the file on the disk has an error by now, nothing
  is saved and the panel says why, with the line.
- **The write is one step:** a new file, renamed over the old one, as the memory is written
  (`hallux/disk.py:286-288`).
- **Without a file,** Save creates it.
- **A flag still wins at the next start.** If you start with `--model` again, that model
  runs, whatever the file says. Those are the layers of `hallux/config.py:3`.
- **Closing without saving loses nothing now.** The changes stay for this run of Hallux. The
  panel's foot says how many aren't saved, each time it is open.

---

## 8. The screen underneath

**At the shell:**

1. Hallux takes the bar's scroll region off, as it does before a full-screen program
   (`hallux/terminal.py:259`).
2. The panel runs on the terminal's alternate screen. The terminal itself keeps the shell's
   screen, with its scrollback. Full-screen programs come and go this way today.
3. While the panel is open, what the AI writes isn't printed. Hallux keeps it, in order
   (`write`, `hallux/terminal.py:146`). What an answer takes back comes after the answer,
   and so after the panel.
4. When the panel closes, the shell's screen is back, the bar is pinned again, and Hallux
   prints what it kept.
5. Then the prompt comes, with the line you were typing.

- **Keys you had typed for the next prompt don't go into the panel.** Hallux sets them
  aside while the panel is open, and they are there for the prompt afterwards.

- **Why the result is exact:** the shell's output is one stream. Printing it a little later
  gives the same screen as printing it at once.
- **What you don't get:** you don't see the answer arrive while the panel is open. The bar on
  the panel's last row shows that the AI works, and what the answer cost.
- **A window that was resized while the panel was open** is what your terminal makes of it,
  as with any resize today.

**In a full-screen program:**

- **The panel is a layer over the program,** in the same full-screen app. The program's
  screen, its fields, their text and their cursors stay where they are, under it.
- **A new screen from the AI is shown when the panel closes.** The answer goes on to its end
  under the panel, and its screen waits. For a moment after the panel closes the old screen
  is there, until the new one is drawn.
- **Why it waits:** in block mode a new screen replaces the whole layout and takes the focus
  (`hallux/blockmode.py:236-254`). Putting it under the panel would mean changing that. An
  answer's end waits for the panel anyway, so the screen waits with it.
- **One thing has to change in block mode,** and it showed in my check: while the AI is busy
  with a program's screen, block mode holds every key for the next screen
  (`hallux/blockmode.py:246,540`). The panel's keys have to pass, and Ctrl+F12 has to act at
  once, as the hard exit does there.
- **Typing in the panel is plain typing,** also over a program with vi keys. The editing
  keys belong to the whole app (`hallux/blockmode.py:247`), so the app edits the plain way
  while the panel is open, and the program's way afterwards.

**While the panel is open, nothing new is sent to the AI:**

| What | While the panel is open |
|---|---|
| An answer the AI is writing | Goes on to its end |
| The next shell prompt | Waits |
| An event from an addon | Waits, then arrives as it would have |
| A tick of a full-screen program | Waits. The program's clock starts again when the panel closes |
| Keys you type | Are the panel's. None of them reaches the machine later |

- **The keyboard has one owner.** My check showed it: when the AI's answer ended and Hallux
  moved on while the panel was open, the panel got no key any more.
- **No money is spent on a screen nobody sees.** A tick is a model call.

---

## 9. Safety

- **Only the real keyboard opens the panel.** Nothing the AI writes is input. Hallux takes
  Ctrl+F12 before the machine sees any key. In a raw-mode program that key goes to the AI
  today, like every key (`hallux/blockmode.py:450`); from now on it never does.
- **The AI isn't told.** The prompt doesn't change, and no message says that the panel was
  open or what was changed.
- **`config.toml` stays out of the machine's reach.** No tool is added, and `/.hallux` is
  still invisible to the machine (`hallux/disk.py:83`). The rule in `hallux/config.py:4`
  holds: the machine can't pick its own hardware.
- **A program can draw something that looks like the panel.** It changes nothing: only the
  real panel reaches the settings. The panel never asks for a password, a key or a login, so
  a copy of it has nothing to collect.
- **Raising a budget is your decision to spend,** and so is refilling them. The panel shows
  what was spent beside each, and only the real keyboard reaches the button.
- **A value is checked before it is taken, and the file before it is written.**
- **A scripted run has no panel.**

---

## 10. Testing

**Without a model call:**
- **The writer:** a line replaced, added and removed; comments kept; a broken file refused;
  a setting that wasn't changed never written.
- **The tabs, on a pipe,** with stand-in tabs: a letter and a click switch the tab; the
  letters don't act while a tab is typing; a disabled tab is grey and says why; a tab's keys
  act only while it is shown; Esc, Ctrl+F12 and the hard exit work in every tab.
- **The Config tab, on a pipe:** moving, changing each kind of row, a wrong value refused
  with its reason, Refill budgets, Save and Close.
- **A refill, in the machine:** every budget counts from zero again, what was paused goes
  on, the bar's total is what it was, and nothing is unsaved.
- **The terminal, on a pipe:**
  - at the prompt, the typed line comes back;
  - while the AI works, what it writes comes out afterwards, in order, and the next prompt
    waits for the panel;
  - at a password prompt, nothing typed survives.
- **The exact screen:** an output that records every byte. A run with a visit to the panel
  in the middle writes the same bytes as a run without one, apart from the panel's own.
- **Block mode, on a pipe:** the layer over a form with a field and over a raw-mode program;
  while the AI is busy with the screen; a new screen shown when the panel closes; typing
  over a program with vi keys; ticks waiting.
- **The machine, with the fake model** the tests already have: a budget raised and its pause
  lifted, the cap per boot holding a message back, the effort used by the next boot, the
  model switched between two answers.

**With a model, once:** the switch of a running session's model, on Haiku, for a few cents.

**By the user, live:** Ctrl+F12 in the real terminal, the shell's screen coming back, and
the tick budget raised under a running player.

---

## 11. What has to change

| File | Change |
|---|---|
| `hallux/panel.py` (new) | The host: the tab row, switching, opening and closing, the foot. It knows nothing of what a tab shows |
| `hallux/panel_tabs/config.py` (new) | The Config tab: its rows, changing a row, Save and Close. It knows nothing of the machine: it gets the settings and gives back changes |
| `hallux/config.py` | The check of one setting; the writer that changes the file line by line |
| `hallux/terminal.py` | Ctrl+F12 at the prompt, at a password prompt and while the AI works; the panel on the alternate screen; keeping what is written; waiting for the panel |
| `hallux/blockmode.py` | The panel as a layer; its keys while the AI is busy; plain typing while it is open; ticks wait |
| `hallux/machine.py` | Taking a change: new settings (`Hardware` can't be changed, so a new one replaces it), the model switched between answers, a pause lifted, the budgets refilled, the cap per boot checked by Hallux |
| `hallux/statusbar.py` | The key in the idle hint; the model and the effort that run |
| `hallux/app.py` | Tells the machine which settings came from flags, and builds the panel |
| `hallux/script.py` | A scripted run has no panel, and halts when it reaches its cap |
| `README.MD` | Configuration: the panel, and what changes when. Keys: Ctrl+F12 |
| `docs/concept.md` | Principle 1 names two things on the screen that aren't the AI's. The panel is a third |
| `tests/` | As in section 10 |

---

## 12. Later, and the room this version leaves

- **The Agents and Details tabs** ([addon-agents.md](addon-agents.md), section 17): two more
  files in `hallux/panel_tabs/`, and two more entries in the host's list of tabs.
- **The settings of addon agents** ([addon-agents.md](addon-agents.md), section 6): six more
  rows in the first group. Every job is a new session, so each of them acts from the next
  job on.
- **The effort without a reboot.** A session could be closed and opened again with the same
  conversation and a new effort. That needs Claude Code to keep its transcript, which Hallux
  turns off by default. I didn't check it.
- **A reset button:** a reboot from the panel, without the AI. The machine's RAM would be
  gone, as on a real machine.
- **The four settings of the third group.** They could be changed and saved in the panel,
  and act at the next start.
- **A click on the bar** to open the panel, in full-screen programs, where the mouse is on
  already.
- **Back to the file:** a button that drops the changes of this run.

---

## Where this differs from the first idea

Every row was accepted on 2026-10-03, with the rest of the recommendations.

| The first idea | This design | Why |
|---|---|---|
| A button on the status bar opens it | A key, Ctrl+F12, which the bar names | A click needs mouse reporting. At the shell that takes away your terminal's own text selection and wheel |
| Efforts are switched live | The effort changes at the machine's next reboot, and the panel says so | A session gets its effort when it starts, and the SDK can't change it later |
| Max prices are changed live | The same, and for that the budget per boot becomes Hallux's own check | Today it is handed to the session at the start of the boot |
| The panel collects what the AI puts on the screen | The same, and nothing new is sent to the AI while it is open | The keyboard has one owner, and a tick costs money |

---

## Still to find out

Each needed a run, and each has had one. One part of one point is left for later: a slow
line.

- **Answered on 2026-10-04: Ctrl+F12 reaches Hallux in the user's terminal.** The user ran
  `cat -v`, pressed it, and `^[[24;5~` appeared. So the key stands. In another terminal
  program the same test applies; if a terminal keeps the chord for itself, another key takes
  its place, and nothing else in the design depends on which key it is.
- **Answered on 2026-10-05: `set_model()` switches Hallux's running session,** with its
  in-process tools and its conversation. The first answer after it costs more, once: see
  section 5.
- **Answered on 2026-10-05: a session that started with an effort switches to Haiku,** and
  back.
- **Answered on 2026-10-05: the shell's screen is back in a real terminal.** The user's
  first try found a bug: what the AI had written behind the panel was printed before the
  bar's region was pinned again, so the bar's row went up into the text. After the fix:
  "now it works perfectly". The same over a full-screen program: "this is really working
  nicely".
- **Answered on 2026-10-05: a window that is resized while the panel is open** comes back
  right in the user's terminal.
- **Answered on 2026-10-05, for the user's own terminal: the short wait after Esc.** Esc is
  quick there, and an arrow key never closed the panel: "yeah i tried esc and arrows".
  **Left for later: a slow line.** Over ssh the bytes of an arrow key can arrive apart, and
  the first one alone is Esc. The user didn't try it over ssh, expects it to work, and keeps
  it as a test for the future. If an arrow key ever closes the panel there, the wait is one
  number, `ESCAPE_SECONDS` in `hallux/blockmode.py`.
- **Answered on 2026-10-05: by how much one answer goes over the budget per boot.** In the
  live run an answer of $0.026 took a boot $0.004 over a cap of $0.16. It can't be more than
  the cost of the answer that crosses the cap.
- **Answered on 2026-10-05: the bar is enough** to tell you that an answer arrived while
  the panel was open. The user: "yeah, its enoght".

---

## Decisions

**Decided by the user on 2026-10-03.**

| Question | Decision | In the user's words |
|---|---|---|
| Is there a panel, and what is it for? | A full-screen config panel inside Hallux that changes settings while the machine runs and saves them | "configure things live, like max prices or switch models and efforts for the main model. and save the config" |
| What happens to the screen? | The panel takes the terminal over. What the AI writes meanwhile is collected, and the screen is the AI's again afterwards | "when you exit the screen is exatly what the AI made" |
| Which key opens it? | Ctrl+F12. Before it: a button on the bar, then Ctrl+Shift+Ins, which prompt_toolkit doesn't map | "okay ctrl+f12" |
| How does it close? | The Close button, or Esc | "you just either press close or press esc" |
| Does it take the mouse? | Yes | "the actual config panel could have mouse input, since its fullcreen" |

**Accepted on 2026-10-03.** These were my recommendations, and the user accepted all of them
together ("go with all your recommendations"). The first table holds the six questions that
were still open then; each row says what was turned down. The second holds what I had
proposed in my first view of the idea, which the user had already answered with "yeah,
sounds good".

| Question | Decision | Why |
|---|---|---|
| When does a change count, and what do Close and Esc do? | A change counts when you make it. Save writes the file. Close and Esc only leave. Turned down: an Apply button, with Esc dropping what wasn't applied | Esc never throws anything away, and a budget raised for a running program acts at once |
| Does Hallux check the budget per boot itself? | Yes (section 6). Turned down: leaving it with the SDK, where it changes only at a reboot, and a boot that used its budget can only be left with the hard exit | It is the only way to raise it while the machine runs. The price: one answer can go over the cap |
| Does anything new go to the AI while the panel is open? | No: the next prompt, events and ticks wait. Turned down: events and ticks going on, with their output collected too | The keyboard has one owner, and a tick costs money for a screen you don't see |
| Which settings are in the panel? | Six that change, and the four start-up settings shown only. Turned down: only the six, and all ten changeable | You see everything `config.toml` decides, and no row promises a change that needs a new start |
| What does the panel do at a password prompt? | It opens, and what was typed of the password is dropped. Turned down: not opening there | The key works everywhere, and nothing of a password is kept |
| Does the status bar stay on the panel's last row? | Yes. Turned down: the panel taking the whole screen | It shows that the AI still works, and what the answer cost |

| Question | Decision |
|---|---|
| How is the screen kept at the shell? | The terminal's alternate screen, and what the AI writes is held back until the panel closes |
| And in a full-screen program? | A layer over the program. Ticks wait while it is open |
| What is live? | The tick and event budgets at once, the model from the next answer, the effort at the next reboot |
| How is the file saved? | Only the lines of the settings changed in the panel. Comments stay |
| How is a model chosen? | Free text, with a few names to pick from |
| When is it built? | Before addon agents. Both change `terminal.py`, `blockmode.py`, `statusbar.py`, `config.py` and `machine.py`, so not at the same time |

**Decided by the user on 2026-10-04: the tabs.**

| Question | Decision | In the user's words |
|---|---|---|
| One screen or two, for the settings and for watching the agents? | One, behind Ctrl+F12, with three tabs: Agents, Details, Config | "i think we could merge it with the ctrl+f12 panel. it would have 3 tabs [Agents] [Details] [Config]" |
| How is a tab chosen? | By its first letter, which is marked | "with the first letter wither bold or underlined" |
| How is it built? | A tab system, with one Python file per tab | "one tab = 1 python file, like components in react" |
| Where do the tab files live? | `hallux/panel_tabs/`, beside `hallux/panel.py` | "panel_tabs/ is fine" |
| What does a machine without an agent addon show? | Agents and Details disabled, in dark grey. Not hidden | "lets show the agents and detals tabs as disabled (dark grey) when no agent addon" |

**Accepted on 2026-10-04.** My proposals on the tabs, which the user accepted together
("everything sounds good"):

| Question | Decision | Why |
|---|---|---|
| Bold or underlined? | Underlined | Bold looks like plain text in some terminal fonts and themes |
| Do the letters act while a row is open for typing? | No. A click on a tab always works | In the Config tab you type model names |
| Which tab does the panel open on? | Agents while a job runs, otherwise Config | You open it to watch a job, or to change a setting |
| What does a disabled tab do when it is chosen? | Nothing, and the foot says why | Otherwise it looks broken |
| When do the two grey tabs appear? | With addon agents. The panel's first build has the tab system and Config alone | Nobody should see two tabs that can never work |
| What is a tab, in the code? | A title, its part of the screen, its keys, a hint line, whether it is typing or disabled, and the functions it is given | The host then knows nothing of what a tab shows |

**Decided on 2026-10-04, after the review**
([plans-review-2026-10-04.md](plans-review-2026-10-04.md)). The user accepted a fix for
every finding ("go with all your recommendations"). The ones that change what you see:

| Question | Decision | Why |
|---|---|---|
| How do you leave a machine that has used its budget? | Ctrl-D on an empty line halts it. Turned down: the hard exit alone, which the design had by mistake called "as today" | Today a failed answer to Ctrl-D halts the machine. Taking that away would leave only the hard exit |
| What does a scripted run do at its cap? | It halts | Nobody is at its keyboard |
| Which part of the hint goes last on a narrow bar? | The power-off keys. They come first, then the panel's key, then the triple Ctrl-C | The hint is there so that nobody gets stuck |
| Does a new screen go under the panel? | No: it is shown when the panel closes. The design had said under it | The end of an answer waits for the panel anyway, and block mode's way of showing a screen needn't change |
| Is entering the same value a change? | No | Otherwise Enter on an untouched row saves a flag's value |
| What do keys typed for the next prompt do when the panel opens? | They are set aside and are there for the prompt afterwards | Otherwise the panel gets them, and an Enter presses a button |
| How is text typed in the panel over a program with vi keys? | The plain way | Otherwise a model name runs as vi commands |

**Decided by the user on 2026-10-04: the Refill budgets button** (section 5).

| Question | Decision | In the user's words |
|---|---|---|
| Can the budgets be filled again from the panel? | Yes, all of them with one button | "in the setting panel, we could add a reset usage budget for everything"; then "add the refill budgets button to the docs" |

My proposals for it, which came with the idea and were accepted with it:

| Question | Decision | Why |
|---|---|---|
| What is it called? | Refill budgets. Turned down: "reset usage" | It starts the counting anew and doesn't forget what was spent. The bar's total keeps counting |
| Does it ask before it acts? | No | One refill allows at most one more round of each budget, and the panel shows what was spent |
| Is it saved? | No. It is an action, not a setting | Nothing in `config.toml` changes |
| What does the budget per boot count afterwards? | What was spent since the refill. The row shows that and the boot's whole spend | The cap has to let messages through again, and the money mustn't disappear from view |

---

## Order of work

A rough order, for the plan:

1. Saving: the check of one setting, and the writer that changes the file line by line.
2. Taking a change in the machine: the budgets, a pause lifted, a refill, the cap per boot
   as Hallux's own check, the effort at the next boot. The model switch, after its live
   check.
3. The panel by itself: the tab system, and the Config tab with its rows, changing one,
   Refill budgets, Save and Close, on a pipe.
4. The panel at the shell: the key at the prompt and while the AI works, the alternate
   screen, what is written kept, the machine waiting.
5. The panel over a full-screen program: the layer, its keys, ticks.
6. The key on the bar, the documentation, and the live run.
