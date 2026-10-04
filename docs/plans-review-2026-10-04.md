# Config panel and addon agents: review of the designs and plans

**Reviewed on 2026-10-04:** [config-panel.md](config-panel.md) with
[its plan](plans/config-panel/README.md), and [addon-agents.md](addon-agents.md) with
[its plan](plans/addon-agents/README.md), as they stood in the working tree that day. Two
readers who hadn't written the documents checked them against the code, the installed
`claude-agent-sdk` (0.2.163) and prompt_toolkit (3.0.53), one feature each. I then
confirmed their main findings in the source. Nothing was changed while reviewing, and no
model call was made.

**The verdict:** the designs hold up, and the plans weren't ready. Every `file:line`
reference in the four documents was right but one. Eight things in the plans would have
stopped a builder or given wrong behaviour, and each plan had a list of gaps. None of it
called for a new design.

**What was done about it** is at the end: the user accepted a fix for everything on
2026-10-04, and the fixes are in the documents.

Paths of the libraries are inside `.venv/lib/python3.13/site-packages/`.

---

## The config panel

### Would have gone wrong

**1. Keys typed earlier for the shell are fed into the panel** (step 6). Every prompt_toolkit
application takes the stored type-ahead when it starts
(`prompt_toolkit/application/application.py:672`), and `busy()` stores what was typed while
the AI worked (`hallux/terminal.py:235`). Two answers run back to back, with no prompt
between them, after Ctrl-C (`hallux/machine.py:382-384`) and when events wait
(`hallux/machine.py:185-186`). Tried on a pipe: `ls` and Enter typed during one answer, the
panel opened in the next. The panel got `l`, `s` and Enter, and the next prompt got nothing.
Enter opens a row or presses a button there.

**2. Over a program with vi keys, typing in a panel row runs vi commands** (step 7). Block
mode sets the editing mode for the whole app (`hallux/blockmode.py:247`). Tried with the
real block mode: a vi form in normal mode, a text row floating over it. Typing
`claude-haiku-4-5` gave `aude-haiku-4-5`.

**3. The end of an answer has to wait for the whole visit to the panel** (step 6), not for
the key that closes it. Leaving `input.attach()` puts back the reader that was there on
entry (`prompt_toolkit/input/vt100.py:186-196`). If `busy()` goes on when the close key is
handled, before the panel's app has ended, its own reader stays attached for good, and keys
typed before the next prompt are lost. The plan's `wait_closed()` invited that.

**4. Scripted runs would crash** (step 2). `ScriptTerminal.set_status` reads its last record
(`hallux/script.py:121`), and the first record is made when the AI starts to work
(`hallux/script.py:112-113`). Setting the bar at the start of a boot comes before that.

### For the user to decide

**5. Leaving a machine that has used its budget.** The design said "as today: the hard
exit". Today a failed answer to Ctrl-D halts the machine cleanly
(`hallux/machine.py:194,389`), and a failed answer in a program puts you back at the shell
(`hallux/machine.py:388`). Step 3 would take both away, and until steps 6 and 7 nothing can
raise the cap.

**6. Which hint survives on a narrow bar.** At 80 columns there is room for 38 characters
beside the model and the cost, so only `config: ctrl+f12` would remain, and the power-off
keys would go. The hint exists so that nobody gets stuck.

### Gaps

- **A "change" to the same value.** Enter on an untouched row marked it unsaved and took it
  out of the flags. Save would then write a `--model` flag's value, which the design
  promises never happens.
- **Esc in an open text row took a second.** prompt_toolkit's second wait, `timeoutlen`, is
  1.0 (`prompt_toolkit/application/application.py:297`) and applies because the editing
  keys have bindings that start with Esc. Bound eagerly it took 0.05 seconds.
- **The password prompt never resets `erase_when_done`** (`hallux/terminal.py:142-144`;
  `read_line` does at `:125`). After one Ctrl+F12 there, every later password prompt would
  be erased on Enter.
- **A wrong model name that is saved ends Hallux at the next boot.** A boot that fails is
  fatal (`hallux/machine.py:164-165,386-387`). The design only covered "model failed" on
  the bar.
- **What a held message looks like.** In a real terminal the line is accepted before the
  machine looks, so it stays on the screen and comes back at the next prompt: a row per
  Enter. In a scripted run the held line would be glued to the next script line
  (`hallux/script.py:94`).
- **The check has to come before a password's verdict,** which changes the password's state
  (`hallux/machine.py:199`).
- **The bar has one slot for a note,** and several reasons write to it
  (`hallux/statusbar.py:60`; `hallux/machine.py:263,268,325,427-428`). Clearing one budget's
  note could clear another's.
- **Windows line endings in `config.toml`.** `load` reads with universal newlines
  (`hallux/config.py:43`), so "byte for byte" needs the file read and written as it is.
- **Step 4:** an error put on the bar before a message goes out is wiped when the answer
  starts (`hallux/terminal.py:213`); the row for the "not with Haiku" outcome is in step 5's
  file; nothing said what the Effort row shows when no effort runs.
- **Smaller things a builder would hit:** the panel's app needs `handle_sigint=False`, as
  block mode has (`hallux/blockmode.py:243`); `exit()` raises when called twice; the two key
  names in two modules that import each other; the bar as part of the panel's container,
  which block mode can't use; a block mode that dies with the panel open over it.

### Where the design and the plan disagreed

- **The new screen.** The plan shows it when the panel closes, on purpose. The design still
  said in seven places that it goes under the panel, or that `show()` has to change.
- **Five smaller ones,** in how and not in what is seen: what is kept while the panel is
  open (`write` only), who is told about the flags (the machine), how many functions the
  Config tab gets, what the log says for a save, and when a lowered budget pauses.

### Small corrections

- Step 1: a setting that is in the file twice is a TOML error, and a table is an unknown
  setting; only a value over several lines reaches the comparison. A number of more than
  308 digits becomes `inf`.
- Step 6: with that step alone, Ctrl+F12 in a raw-mode program still goes to the AI
  (`hallux/blockmode.py:450`).
- Step 8: `tests/test_statusbar.py:16,96` pin the hint; the README's "Project layout" and
  the key rule in `docs/light-and-keys.md` weren't in the list; `docs/concept.md:673` says
  "edit the config, then `reboot`", but the file is read once, at the start.
- The plan's table of files missed `config.py` for steps 3 and 4 and `tests/test_script.py`.
- The Fallback model's list needs "none".

### Checked and correct

- All 17 line references in the design and all 7 in the plan.
- Every "today" statement but the one under 5.
- Ctrl+F12 is `c-f12`; `set_model()` exists and nothing like it for the effort; the cap is
  passed to Claude Code as a flag.
- The seven messages of `_validate` all fit "path: name reason", so the config tests keep
  passing.
- A second app during `busy()` gives the keyboard back when its whole run is awaited; a text
  row over a real block-mode form takes typing and leaves the field alone; the wait for an
  action can take a signal to start again.
- Steps 1, 4 and 5 could be built as written.

---

## Addon agents

### Would have gone wrong

**1. Step 7 uses what step 6 introduces.** `Refused` and the declaration on a loaded addon
come from step 6 (`hallux/addons.py:56-63` has no such field today). The table said step 7
needs 3 and 5.

**2. Step 8 needs the machine to hold `Jobs`, which step 10 introduced.** And how `Jobs`
gets what only the running machine has was never said: its `Disk`
(`hallux/machine.py:104`), the settings as they are now, what the boot has spent, and the
event loop, which doesn't exist yet when `app.py` builds things
(`hallux/app.py:59-76`). `hallux/script.py:160` builds a machine of its own.

**3. Step 11 doesn't wake a program when the job's end arrives while the AI is answering.**
The machine goes from its answer straight into the wait (`hallux/machine.py:328-346`), and
`wake_form()` only ends a wait that is running. A program without a tick would sit on
"composing…" until a key: the case the step exists for.

**4. Step 16 needs a tab to show another tab.** Enter in Agents shows Details, and Esc in
Details goes back. The panel's host, as planned, switches tabs only by its own letters and
clicks.

### For the user to decide

- **Does a reboot fill the jobs' budget again?** The event budget is reset at every boot
  (`hallux/machine.py:275`).
- **Does a job get the machine's fallback model?** It could then run on a model other than
  `agent_model`.
- **The six settings in the panel** would appear seven steps before any job can start.
- **A killed job whose cost can't be read.** The plan's fallback, "the cost isn't known",
  contradicts the design's "never left out".

### Gaps

- **Job events and a message that doesn't go out.** A held message, or a model that fails,
  would lose them: the hub's events are lost that way today (`hallux/machine.py:173,186`).
  And the test that wakes the prompt has to be the test that takes events, or the prompt is
  ended in a loop (`hallux/machine.py:227-228`).
- **A wake in a form with fields can lose what the user typed.** It is the first message
  without the fields that reaches the AI while such a form is up. If the AI restates a
  field, the text is replaced (`hallux/blockmode.py:341-345`); if the model fails, the
  machine leaves the form (`hallux/machine.py:388`).
- **The job's disk is used from two threads:** its tools and the landing in the event loop,
  the disk handle in the addon's thread (`hallux/addons.py:384`). `Disk` has no state of its
  own; the job's disk has. And the `spawn` an addon function got stays usable after its
  call.
- **A kill against a natural end.** A row marked `killed` must never land. A kill before the
  session is open meets "Not connected" (`claude_agent_sdk/client.py:308-312`). Between a
  kill and its cost, the job has to keep counting with its full cap. The SDK helps: a
  result after `interrupt()` says so in `terminal_reason`
  (`claude_agent_sdk/types.py:1363-1371`).
- **"Ended well" has to mean no error,** not only the result's kind: a failed API call
  arrives as `success` with `is_error` set (`claude_agent_sdk/_errors.py:78-80`).
- **One file failing in the middle of a landing.** Only the folder was checked again. A
  subfolder can be gone or replaced by a link. Two names for one file give two copies. A
  file that isn't valid UTF-8 is damaged if it passes through text.
- **The table on a tick has to go through `json_body`** (`hallux/protocol.py:158-162`), as
  the events do, and the prompt has to say that a tick can carry it.
- **Which argument is "the file" in `tool`,** for an addon function with any parameters.
- **Where the jobs' dollars are kept.** An event's turn is measured as the change of the
  machine's total (`hallux/machine.py:240-242`), so a job that ends during it would be
  charged to the event budget. The scripted terminal books every rise of the cost to the
  last line typed (`hallux/script.py:124-126`).
- **`<resume>` and streaming.** The real terminal shows the screen while it is written,
  before the tag after `</prompt>` is read. The tests' terminal doesn't stream.
- **Step 3** changes the Config tab's file and needs two new kinds of value: a whole number
  and seconds.
- **The check child must not load the player module,** which loads pygame
  (`addons/music_engine/__main__.py:39`, `player.py:14`).
- **Without a rule:** what `tokens` counts; caps that can never fit (a job's budget larger
  than the budget for all); the code for a brief that is too long; the order of addon events
  and job events that wait together; the first status line; who owns the redraw once a
  second; the log line for a capped effort, which was in no step.
- **The composer's prompt.** The part of the manual it gets says "WHAT PLAY RETURNS" and
  "then play again" (`addons/music.py:184-191`), while the step says nothing of the text
  changes and tests for no line on `play`.

### Small corrections

- **Design, stale sentences:** two rows of the first Decisions table (the budget "since the
  last typed line"; job control "needs nothing from the agents"); the limits count "the
  files it was given"; copies deleted "when the next boot starts"; `list_processes` called
  read-only though reading it drops ended rows; "the SDK marks the cost as computed from
  list prices", for which the source only has "pricing lookup".
- **Step 7** cites `hallux/addons.py:136` for the hand-over to the loop; the thread-safe one
  is `hallux/machine.py:226`.
- **Step 6:** `hallux/config.py:12` imports from `hallux/addons.py`, so the loader can't
  take the efforts from `config.py`; the schema compares hints by identity
  (`hallux/addons.py:345`), and `list[str] is list[str]` is false; `connect()` has to stay
  the last check; `tests/test_addons.py:161` pins a message the step rewords.
- **Tests that pin what changes:** `$0.00` in `tests/test_statusbar.py:17,25,33`; 13 and 14
  tools in `tests/test_tools.py:34,93`.
- **Step 12:** the bar shows a tool's `path`, `src` or `name` (`hallux/statusbar.py:41`), so
  a pid needs code, not only a word.
- **Step 1,** "nothing a user can see": the folder's time of change moves with every save,
  a file in a folder that takes no new files can't be written any more, and a crash can
  leave the new file behind.
- **The plan's table of files** missed seven entries, and the README's "Safety and privacy"
  wasn't in the documentation step.
- **Line numbers** in the plan are the code's of that day. The panel is built first and
  moves them.

### Checked and correct

- Every line reference in the design and the plan but the one above.
- The earlier review's five problems, its gaps 6 to 14 and its corrections are all in the
  design's sections, and each has a step.
- The SDK: tools per session; `max_turns` and `max_budget_usd`, with the result kinds
  `error_max_turns` and `error_max_budget_usd`; `interrupt()`; tokens on each model message
  and on the result; a full schema passes through, so a list as an argument works; a session
  can be closed from another task.
- What the plan takes from the panel's plan is what those steps provide, apart from the tab
  that shows another tab.
- A landing, the main agent's writes and the hard-exit key all run in one loop and can't
  cut into each other. Only a crash of Hallux cuts a landing.

### Not checked

Anything that needs a model: the cost after `interrupt()`, the cap in the middle of a turn,
live tokens, the model switch. And putting a kept form back was judged from reading
`hallux/blockmode.py`, not tried.

---

## A finding in the code, not in the documents

With `FORCE_COLOR` set in the shell, two tests fail:
`tests/test_addon_window.py::test_a_window_that_crashes_says_why` and
`tests/test_addon_music.py::test_a_child_that_dies_says_why_and_the_next_play_starts_a_new_one`.
Python then colours a child's traceback, and the addons' "it crashed (…)" message carries
the escape codes. Without the variable all 838 tests pass. The `check` child of the agents
plan starts the same way, so its step now starts every child with colours off.

---

## What was decided, and done

On 2026-10-04 the user accepted a fix for every finding ("go with all your
recommendations"), and for the six questions:

| Question | Decision |
|---|---|
| Leaving a machine over its budget | Ctrl-D on an empty line halts it, as it does today after a failed answer. A scripted run halts when it reaches its cap |
| The hint on a narrow bar | The power-off keys come first, and parts go from the end |
| A reboot and the jobs' budget | A reboot fills it again, as it does the event budget |
| A job and the fallback model | A job gets none. It fails before it runs on a model nobody chose for it |
| The six settings in the panel | They are drawn from step 10 on, when a job can start |
| A killed job whose cost can't be read | It counts with its full cap, and its row says that the cost isn't known |

The fixes are in both designs and both plans. Each plan's README lists what changed under
"After the review".
