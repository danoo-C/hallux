# The config panel

**Status:** designed on 2026-10-03, and every question is settled. Nothing is built; the
plan comes next. The idea is the user's: a panel inside Hallux that changes the machine's
settings while it runs, saves them, and gives the screen back exactly as the AI made it. The
user also chose the key, how the panel closes, and that it takes the mouse. The rest was my
proposal, and the user accepted all of it. The answers are part of the sections, and
[Decisions](#decisions) lists them with what was turned down.

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
- **Two things in block mode get in the way today.** The build has to change them
  (section 8).

What I didn't check is in [Still to find out](#still-to-find-out). The two that matter most:
nobody has pressed Ctrl+F12 in a real terminal yet, and switching the model of a running
session needs a model call.

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
  `config: ctrl+f12 · power off: ctrl+shift+del · ctrl+c ×3`.
- **The mouse works in the panel:** a click picks a row or presses a button. At the shell
  the mouse is off again when the panel closes, so your terminal's own text selection and
  wheel stay as they are.
- **The hard exit works inside the panel:** Ctrl+Shift+Del, and Ctrl-C three times. One
  Ctrl-C does nothing there.
- **Esc is quick.** prompt_toolkit waits after Esc, to tell it from the start of an arrow
  key. The panel sets that wait to 0.05 seconds.

**Where the machine is when you press it:**

| The machine is | The panel | The machine meanwhile |
|---|---|---|
| At the shell prompt | Opens. When it closes, the line you were typing is back | Waits. Events from addons wait too |
| Answering, at the shell | Opens at once | The answer goes on. What it writes is kept, and printed when the panel closes. The next prompt waits |
| In a full-screen program, waiting for you | Opens over the program | Ticks wait |
| In a full-screen program, the AI busy with it | Opens over the program | The answer goes on. The new screen goes under the panel |
| At a password prompt | Opens. What was typed of the password is dropped | Waits |
| Running a `--script` | There is none: a script has no keyboard | |

---

## 4. What the panel shows

A sketch. The last row is Hallux's status bar, which stays where it is.

```text
 Hallux · configuration                            test-hallux/.hallux/config.toml

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

    [ Save ]   [ Close ]                           2 changes not saved

 ↑ ↓ move · Enter change · Esc close
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
- **A model name can't be checked.** Any name is taken. A wrong one shows as "model failed"
  on the bar with the next answer. The list holds the three names Hallux's help names, the
  model that runs and the one in the file.
- **A row that a flag set says so:** "from --model, for this run".

---

## 5. When a change takes effect

| Setting | Takes effect | Why |
|---|---|---|
| `tick_budget_usd`, `event_budget_usd` | At once | They are Hallux's own counters, read at each use (`hallux/machine.py:250,323`) |
| `max_budget_usd` | At once | Hallux checks it itself (section 6). Today the session gets it when it starts |
| `model` | From the next answer | The SDK can switch a running session: `set_model()`. Not run yet |
| `effort`, `fallback_model` | At the machine's next reboot | The session gets them when it starts (`hallux/machine.py:131-132`), and the SDK has no way to change them later |
| `status_bar`, `addons`, `keep_transcripts`, `os_sandbox` | When Hallux starts | The bar and the addons are wired once, at the start (`hallux/app.py:60,68`). The other two could act at a reboot, but this version doesn't change them |

**The budgets:**
- **Raising a budget that is used up lifts its pause.** Events come again at once. A program
  whose live updates were paused ticks again when the panel closes.
- **Lowering a budget below what was spent** pauses at the next check, as if it had run out.

**The model:**
- **It switches between two answers.** If the AI is answering, the switch waits for the end
  of that answer.
- **The first answer on the new model costs more, once.** A model has its own cache, so it
  reads the whole conversation of the boot at the full price.
- **If `set_model()` doesn't work for Hallux's session,** the model moves to the second
  group and changes at the next reboot, like the effort.
- **Haiku is a special case.** It gets no effort (`hallux/config.py:34`). Whether a session
  that started with an effort can switch to Haiku isn't known yet.

**The effort:**
- **The panel shows both:** the effort you set, and the one that runs now.
- **The status bar shows what runs.** It changes at the reboot, not when you set the value.
- **The panel doesn't reboot the machine.** A reboot is the machine's own: you type `reboot`.

**The log** gets a line for each change and each save, with the old and the new value.

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
- **Raising the cap in the panel lets the next message through.**
- **Leaving is as today:** the hard exit. A clean `poweroff` needs the AI, and so the budget.

**What it costs:** Hallux checks between two answers, so one answer can go over the cap by
what that answer costs. The SDK's cap may stop a session in the middle of an answer; whether
it does isn't known.

---

## 7. Saving

- **Save writes `<world>/.hallux/config.toml`,** the file of this machine.
- **Only the rows you changed in the panel are written.** A setting you didn't touch is never
  written. So a `--model` flag given for one run doesn't end up in the file.
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
3. While the panel is open, what the AI writes isn't printed. Hallux keeps it, in order: the
   text, and what it takes back (`write` and `retract`, `hallux/terminal.py:146-158`).
4. When the panel closes, the shell's screen is back, the bar is pinned again, and Hallux
   prints what it kept.
5. Then the prompt comes, with the line you were typing.

- **Why the result is exact:** the shell's output is one stream. Printing it a little later
  gives the same screen as printing it at once.
- **What you don't get:** you don't see the answer arrive while the panel is open. The bar on
  the panel's last row shows that the AI works, and what the answer cost.
- **A window that was resized while the panel was open** is what your terminal makes of it,
  as with any resize today.

**In a full-screen program:**

- **The panel is a layer over the program,** in the same full-screen app. The program's
  screen, its fields, their text and their cursors stay where they are, under it.
- **A new screen from the AI goes under the layer.** When the panel closes, the program shows
  its newest screen.
- **Two things have to change in block mode,** and both showed in my check:
  - While the AI is busy with a program's screen, block mode holds every key for the next
    screen (`hallux/blockmode.py:246,540`). The panel's keys have to pass, and Ctrl+F12 has
    to act at once, as the hard exit does there.
  - A new screen replaces the whole layout and takes the focus
    (`hallux/blockmode.py:236-254`). It has to leave the panel on top, with the focus.

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
- **Raising a budget is your decision to spend.** The panel shows what was spent beside it.
- **A value is checked before it is taken, and the file before it is written.**
- **A scripted run has no panel.**

---

## 10. Testing

**Without a model call:**
- **The writer:** a line replaced, added and removed; comments kept; a broken file refused;
  a setting that wasn't changed never written.
- **The panel by itself, on a pipe:** moving, changing each kind of row, a wrong value
  refused with its reason, Save, Close, Esc, Ctrl+F12, the hard exit.
- **The terminal, on a pipe:**
  - at the prompt, the typed line comes back;
  - while the AI works, what it writes comes out afterwards, in order, and the next prompt
    waits for the panel;
  - at a password prompt, nothing typed survives.
- **The exact screen:** an output that records every byte. A run with a visit to the panel
  in the middle writes the same bytes as a run without one, apart from the panel's own.
- **Block mode, on a pipe:** the layer over a form with a field and over a raw-mode program;
  while the AI is busy with the screen; a new screen arriving under it; ticks waiting.
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
| `hallux/panel.py` (new) | The panel: its rows, changing a row, Save and Close. It knows nothing of the machine: it gets the settings and gives back changes |
| `hallux/config.py` | The check of one setting; the writer that changes the file line by line |
| `hallux/terminal.py` | Ctrl+F12 at the prompt, at a password prompt and while the AI works; the panel on the alternate screen; keeping what is written; waiting for the panel |
| `hallux/blockmode.py` | The panel as a layer; its keys while the AI is busy; a new screen under it; ticks wait |
| `hallux/machine.py` | Taking a change: new settings (`Hardware` can't be changed, so a new one replaces it), the model switched between answers, a pause lifted, the cap per boot checked by Hallux |
| `hallux/statusbar.py` | The key in the idle hint; the model and the effort that run |
| `hallux/app.py` | Tells the panel where the file is and which settings came from flags |
| `README.MD` | Configuration: the panel, and what changes when. Keys: Ctrl+F12 |
| `docs/concept.md` | Principle 1 names two things on the screen that aren't the AI's. The panel is a third |
| `tests/` | As in section 10 |

---

## 12. Later, and the room this version leaves

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

Each needs a run.

- **Whether Ctrl+F12 reaches Hallux in the user's terminal.** Run `cat -v`, press it, and
  `^[[24;5~` should appear. If it doesn't, another key takes its place; nothing else in the
  design depends on which key it is.
- **Whether `set_model()` switches Hallux's running session,** with its in-process tools, and
  what the first answer after it costs.
- **Whether a session that started with an effort can switch to Haiku,** and back.
- **Whether the shell's screen is back exactly in a real terminal:** the scrollback, the
  cursor, the colors, the pinned bar. Full-screen programs leave it that way today, so I
  expect it. Also after the window was resized while the panel was open.
- **Whether the short wait after Esc is safe on a slow line.** Over ssh the bytes of an arrow
  key can arrive apart, and the first one alone is Esc.
- **By how much one answer goes over the budget per boot,** now that Hallux checks between
  answers.
- **Whether the bar is enough** to tell you that an answer arrived while the panel was open.

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

---

## Order of work

A rough order, for the plan:

1. Saving: the check of one setting, and the writer that changes the file line by line.
2. Taking a change in the machine: the budgets, a pause lifted, the cap per boot as Hallux's
   own check, the effort at the next boot. The model switch, after its live check.
3. The panel by itself: the rows, changing one, Save and Close, on a pipe.
4. The panel at the shell: the key at the prompt and while the AI works, the alternate
   screen, what is written kept, the machine waiting.
5. The panel over a full-screen program: the layer, its keys, a new screen under it, ticks.
6. The key on the bar, the documentation, and the live run.
