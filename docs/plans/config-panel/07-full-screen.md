# Step 7: the panel over a full-screen program

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), sections 5
and 8

**Needs:** steps 3 and 6. **Changes:** `hallux/blockmode.py`, `hallux/terminal.py`,
`hallux/machine.py`, `hallux/script.py`, `tests/test_blockmode.py`,
`tests/test_terminal.py`, `tests/test_machine.py`.

In a full-screen program, block mode runs one full-screen app and owns the keyboard. The
panel becomes a layer in that app. The program's screen, its fields, their text and their
cursors stay under it, untouched. This step also makes a paused program tick again when its
budget is raised.

## Build

**Block mode is handed the panel.** Block mode exists before the panel does
(`hallux/terminal.py:97`). When the terminal is given the panel (step 6), it passes it on.

**Opening it.** Block mode binds `OPEN_KEY` in both of its key tables, the one for programs
with fields and the one for raw-mode programs, the way it binds the hard exit
(`hallux/blockmode.py:458,472`). From now on the key never reaches the AI.

**The layer:**
- The panel's container floats over the program's rows. The bar's row is block mode's own
  and stays where it is.
- While it is open, the app's keys are the panel's, and the focus is on it.
- When it closes, the program's keys are back, and the focus is where it was.
- The wait after Esc is 0.05 seconds while it is open, and what it was before afterwards.

**Typing in the panel is plain typing, whatever the program's keys are.** Block mode sets
the editing keys for the whole app (`hallux/blockmode.py:247`). Over a program with vi
keys in normal mode, a model name typed into a row would run as vi commands. So while the
panel is open the app edits the plain way, and the program's way, with the mode it was in,
comes back when the panel closes.

**While the AI is busy with the program's screen,** block mode holds every key for the next
screen (`hallux/blockmode.py:246,540`). Two changes:
- `OPEN_KEY` acts at once there, like the hard exit.
- While the panel is open, keys aren't held: they go to the panel. What was held before it
  opened stays held, for the program's next screen.

**A new screen from the AI** isn't shown while the panel is open. The wait of step 6 is in
`busy()`, and block mode's answers go through it too: the answer ends, its cost is on the
bar, and the screen is shown when the panel closes. `show()` doesn't change. For a moment
after the panel closes the old screen is there, until the new one is drawn.

**The visit is over when the layer is gone,** the keys and the focus are the program's
again, and the editing keys are back. That is what `busy()` waits for here.

**If the full-screen app dies while the panel is open over it,** the panel is closed with
it. Otherwise it would stay "open" with nothing to show it, and the next answer would wait
for it for ever.

**Ticks wait.** When a program's tick is due and the panel is open, `next_action` returns no
tick. It waits for the panel to close and starts the program's clock again.

**`set_tick(seconds)`,** new on the terminal and in block mode: sets the tick of the form on
screen, and starts a wait that is running again with the new time. The scripted terminal
and the tests' fake terminal get an empty one.

**A paused program ticks again.** The machine remembers the tick a program asked for, and
why its ticks are stopped: the tick budget (today, `hallux/machine.py:323`) or the budget
per boot (step 3). `settle()` learns the last part: when a program is on screen, its ticks
are stopped and both budgets allow them again, it calls `set_tick` with the tick the
program asked for, and that reason's note goes. The clock then starts when the panel
closes. A refill (step 2) runs `settle()` too, so the Refill budgets button makes a paused
program tick again the same way.

## Tests

In `tests/test_blockmode.py`, with the real block mode on a pipe and a real panel around
fake functions:

- a program with a field: some text is typed, Ctrl+F12, more keys, Esc, one more key. The
  keys in between went to the panel, the field has the text from before and the last key,
  and nothing was sent to the AI;
- **a program with vi keys, in normal mode:** Ctrl+F12, a model name typed into the Model
  row arrives whole. After Esc the program is in normal mode again;
- a raw-mode program: no key reaches the AI while the panel is open, and Ctrl+F12 itself
  never does;
- the AI is busy with the screen: Ctrl+F12 opens the panel at once, the panel gets the keys,
  and what was typed before it opened goes to the program's next screen;
- a ticking program: the panel stays open for longer than the tick, and no tick comes. After
  it closes, a tick comes after the tick's time;
- `set_tick` while `next_action` waits without a tick: a tick comes after the new time;
- a click in the panel doesn't reach the program;
- the bar's row is still drawn under the panel;
- the app ends while the panel is open: the panel is closed, and a wait for it returns;
- the hard exit key works inside the panel.

In `tests/test_terminal.py`:

- in a full-screen program, an answer that ends while the panel is open doesn't end its
  `busy()` until the panel closes.

In `tests/test_machine.py`:

- a program's ticks are paused by the tick budget; the budget is raised; `set_tick` is
  called with the tick the program asked for, and that note is gone;
- the same when the budget per boot stopped them;
- the same after `refill()`, with both budgets used up: `set_tick` is called, and both notes
  are gone;
- ticks don't come back while the other budget is still used up, and its note stays.

## Done when

The tests pass, and the user has tried it by hand:

- in an editor with unsaved text: Ctrl+F12, Esc, and the text and the cursor are as they
  were;
- in vim, in normal mode: Ctrl+F12, a new model name typed, Esc;
- in a player whose live updates are paused: Ctrl+F12, a higher tick budget, Esc, and the
  player moves again. And once more with Refill budgets in place of the higher number.

## As built

Built on 2026-10-05, on the branch `config-panel`. 18 new tests, 1053 in all; every old test
passes as it was. **The user tried it by hand on 2026-10-05:** "this is really working
nicely".

Decided while building:

- **The panel tells who shows it that it was closed, at once.** `Panel.on_close` is called
  by the very key that closes it. Block mode gives the program its keys, its focus and its
  way of editing back right there, so a key typed directly behind the closing one is the
  program's. A wait for the panel's own event would come one step too late for that key.
- **`ESCAPE_SECONDS` sits beside the two key names** in `hallux/blockmode.py`, and the panel
  takes it from there. Block mode still never imports the panel.
- **The layer is a float over the program's rows,** above the fields, in every screen block
  mode lays out. It is drawn only while the panel is open. The bar's row lies beside that
  area, so it stays.
- **The app's keys are the panel's while the layer is up,** and the program's otherwise.
- **The editing keys are the plain ones while it is open.** The vi mode the program was in
  isn't touched, so normal mode is normal mode again afterwards. The rows of the Config tab
  bind their own keys (step 5), but vi's commands for single letters would still win over
  them: that is why the switch is needed.
- **While the AI is busy with the screen,** Ctrl+F12 acts at once, the keys typed behind it
  in the same burst are the panel's, and no key is held while the layer is up. What was held
  before stays held.
- **`next_action` waits in a loop that can be started again.** One event starts it again:
  when the panel opens, when it closes, and when `set_tick` gives a new tick. While the
  layer is up the wait has no tick at all.
- **`panel_gone()`** is what `busy()` waits for in a full-screen program, after the wait for
  a visit at the shell.
- **The app's end closes the panel** through the app's own task, so it also happens while
  the machine is waiting for an answer and nobody asks block mode anything. `end()` closes
  it too.
- **Without a panel, Ctrl+F12 still never reaches the AI** in a raw-mode program.
- **The machine keeps two things for the program on screen:** the tick it asked for, and
  whether a budget has stopped its ticks. `settle()` gives the tick back with `set_tick`
  when neither the tick budget nor the budget per boot is used up.
- **A cap lowered under a ticking program** stops its ticks with the next tick, which is
  held back, and raising it starts them again.

**Checked on a pseudo-terminal, with a terminal emulator drawing the screen** (pyte, 24
rows by 80). The real terminal with the bar, a machine, and a pretend model that knows an
editor and a ticking program. No model call.

| What was done | The screen |
|---|---|
| `nano`, `abc` typed, Ctrl+F12 | The panel covers the editor. The bar is on the last row, as before |
| The tick budget changed in the panel, Esc | The editor is back: `abchi`, the cursor behind `abc` as it was |
| One more letter, then Ctrl-X | `abcdhi`. The AI gets the action with the whole text |
| `top`, until its ticks run out | `live updates paused: tick budget used` on the bar |
| Ctrl+F12, Refill budgets | `(paused)` is gone from the row, and the note from the bar |
| A second and a half under the panel | No tick: the count on top's screen doesn't move |
| Esc | top ticks again: the next tick reaches the AI, and its screen is drawn |

**Seen on the way:** at 80 columns the note of the budget per boot is cut after a refill.
`spent since the refill: $0.00 · this boot: $0.64` is longer than what is left of the row.
The user doesn't mind it at that width, so the words stay.
