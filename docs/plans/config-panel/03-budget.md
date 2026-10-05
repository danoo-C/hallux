# Step 3: the budget per boot

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), section 6

**Needs:** step 2. **Changes:** `hallux/machine.py`, `hallux/blockmode.py`,
`hallux/terminal.py`, `hallux/script.py`, `hallux/config.py`, `tests/test_machine.py`,
`tests/test_blockmode.py`, `tests/test_script.py`.

Today `max_budget_usd` is handed to the session when a boot starts
(`hallux/machine.py:133`), and nothing can change it while the session lives. From this
step on Hallux checks it itself, before a message goes to the AI. Then a new value from
step 2 acts at once.

**This step changes what a running machine does,** also without a panel: a boot that has
used its budget holds messages back and says so on the bar. Today the SDK ends the answer
with an error.

## Build

- **The session doesn't get the cap any more.** `options()` loses `max_budget_usd`.
- **`over_budget()`:** there is a cap, and the boot has spent at least that much since it
  started, or since the last refill.
- **`refill()`** (step 2) learns the cap: it notes what the boot has spent by now, and the
  cap counts from there. The session's own running total can't be set back: the cost of each
  answer is worked out from it (`hallux/machine.py:475-480`). So the machine remembers where
  the counting started.
- **The panel's view** gets both numbers: what was spent since the refill, and what the boot
  has spent in all. Without a refill they are the same, and the row shows one.
- **The note** on the bar: `budget used: $2.00 per boot`. It has its own reason among the
  machine's notes (step 2). Without a bar it is printed, as the other notes are, once.
  Step 8 adds the key to it, once the key works.
- **`config.WHEN`** has `max_budget_usd` under `now`.

**Where the check sits.** In the machine's loop and in `block_mode`, before a message is
handed to `send`. `send` itself never holds anything back, so the two messages it sends by
itself always go: the second one after a Ctrl-C that interrupted an answer
(`hallux/machine.py:382-384`), and the one after a full-screen app died
(`hallux/machine.py:331-334`). Both belong to a message that is under way already.

**At the shell,** the machine looks before it sends:

| What you did | Over the budget |
|---|---|
| Typed a line | Not sent. The line is back at the prompt |
| Pressed a key for the machine: Tab, Ctrl-L | Not sent. The line stays |
| Pressed Ctrl-C or Ctrl-Z | Not sent. The line ends, as the terminal has shown it already |
| Pressed Ctrl-D on an empty line | **The machine halts.** No message is sent |
| Typed a password | Not sent, and not checked. The password prompt comes again, empty |

- **Ctrl-D is the way out.** Today a failed answer to Ctrl-D halts the machine
  (`hallux/machine.py:194,389`), so a boot that has used its budget can be left cleanly.
  That stays: the halt runs the addons' hooks and gives the terminal back, as any halt.
- **The check comes before a password is looked at.** Looking at it changes what the
  password store remembers (`hallux/machine.py:199`).
- **How a held line looks.** The terminal has taken the line before the machine looks, so it
  stays on the screen, and the next prompt shows it again, ready to send. Each Enter adds a
  row. That is what you see until the cap is raised.
- **Events are paused while the boot is over its budget,** the way the event budget pauses
  them. Otherwise an event would end the prompt again and again.
- **The first message of a boot always goes:** a boot has spent nothing then.

**A scripted run halts** when it reaches its cap. A script has no keyboard, so nobody can
raise the cap or press Ctrl-D, and a held line would be glued to the script's next line
(`hallux/script.py:94`). The scripted terminal says that nobody is at its keyboard, the
machine halts instead of holding, and the note is printed once.

**In a full-screen program,** an action or a tick comes back from the terminal, and it isn't
sent:

1. The machine puts the note on the bar.
2. It calls `keep_form(tick=0)`, new on the terminal: the program stays as it is, takes keys
   again, and its ticks stop.
3. It waits for the next action. Nothing is drawn again.

- **The way out of a program** is the panel, from step 7 on, or the hard exit. Until step 7
  it is the hard exit alone: today a failed answer puts you back at the shell
  (`hallux/machine.py:388`), and that is gone.

**`keep_form(tick=None)`,** in block mode:
- The form takes keys again: what block mode held while it waited for the AI goes into the
  form.
- **The fields count as not seen by the AI.** When an action is sent, block mode notes each
  field's text as seen, so that the next action leaves out text the AI has. This action
  never reached the AI, so that note is taken back. Otherwise the AI would miss what you
  typed.
- With a `tick`, the form's tick is set to it.
- The scripted terminal and the tests' fake terminal get an empty `keep_form`.

**Why not show the form again:** the reply that made the form may carry the text of its
fields. Showing it again would put that text over what you typed since.

**`settle()`** (step 2) learns the cap: when the boot is under it again, its note goes and
the events come back, if their own budget allows it. A program's ticks start again from
step 7 on; until then, with its next screen.

## Tests

In `tests/test_machine.py`:

- the options of a session have no cap;
- a boot under its cap behaves as before;
- over the cap, a typed line isn't sent: the session got no message, the note is on the bar,
  and the next prompt has the line;
- the same for a key that keeps the line and a key that ends it;
- a password over the cap isn't sent and isn't checked: the store is as it was;
- Ctrl-D on an empty line over the cap: the machine halts, no message was sent, and the
  addons' hooks ran;
- the two messages `send` sends by itself still go;
- events don't end the prompt while the boot is over its cap, and do again once it is
  raised;
- over the cap in a full-screen program: the action isn't sent, `keep_form` was called with
  a tick of 0, no form was shown again, and the next action is waited for;
- the cap is raised with `change`: the note goes, another note stays, and the next line
  reaches the AI;
- over the cap, `refill()`: the note goes and the next line reaches the AI; the cap holds
  again after as much was spent once more; the cost of the next answer is right, and the
  view has both numbers;
- a reboot starts the count at zero, with or without a refill before it;
- a machine without a cap never holds anything back.

In `tests/test_script.py`:

- a scripted run that reaches its cap halts: the lines after it aren't typed, none is glued
  to another, and the note is printed once.

In `tests/test_blockmode.py`, with the real block mode on a pipe:

- after an action, `keep_form()` lets typing go into the field again;
- the action after it reports the field's text in full, as not seen by the AI;
- `keep_form(tick=0)` on a ticking raw program: the next wait has no tick.

## Done when

A test machine with a cap of one cent holds the second line back, the cap is raised with
`change`, and the same line goes through. And Ctrl-D halts a machine that is over its cap.
