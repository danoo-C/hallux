# Step 3: the budget per boot

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), section 6

**Needs:** step 2. **Changes:** `hallux/machine.py`, `hallux/blockmode.py`,
`hallux/terminal.py`, `hallux/script.py`, `hallux/config.py`, `tests/test_machine.py`,
`tests/test_blockmode.py`.

Today `max_budget_usd` is handed to the session when a boot starts
(`hallux/machine.py:133`), and nothing can change it while the session lives. From this
step on Hallux checks it itself, before a message goes to the AI. Then a new value from
step 2 acts at once.

**This step changes what a running machine does,** also without a panel: a boot that has
used its budget holds messages back and says so on the bar. Today the SDK ends the answer
with an error.

## Build

- **The session doesn't get the cap any more.** `options()` loses `max_budget_usd`.
- **`over_budget()`:** there is a cap, and this boot has spent at least that much.
- **The note** on the bar: `budget used: $2.00 per boot`. Without a bar it is printed, as
  the other notes are. Step 8 adds the key to it, once the key works.
- **`config.WHEN`** has `max_budget_usd` under `now`.

**At the shell,** the machine looks before it sends:

| What you did | Over the budget |
|---|---|
| Typed a line | Not sent. The line is back at the prompt |
| Pressed a key for the machine: Tab, Ctrl-L | Not sent. The line stays |
| Pressed Ctrl-C, Ctrl-D, Ctrl-Z | Not sent. The line ends, as the terminal has shown it already |
| Typed a password | Not sent. The password prompt comes again, empty |

- **Events are paused while the boot is over its budget,** the way the event budget pauses
  them. Otherwise an event would end the prompt again and again.
- **The first message of a boot always goes:** a boot has spent nothing then.

**In a full-screen program,** an action or a tick comes back from the terminal, and it isn't
sent:

1. The machine puts the note on the bar.
2. It calls `keep_form(tick=0)`, new on the terminal: the program stays as it is, takes keys
   again, and its ticks stop.
3. It waits for the next action. Nothing is drawn again.

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

**`settle()`** (step 2) learns the cap: when the boot is under it again, the note goes and
the events come back, if their own budget allows it. A program's ticks start again from
step 7 on; until then, with its next screen.

**Leaving** a machine that is over its budget is the hard exit, as the design says. A clean
`poweroff` needs the AI.

## Tests

In `tests/test_machine.py`:

- the options of a session have no cap;
- a boot under its cap behaves as before;
- over the cap, a typed line isn't sent: the session got no message, the note is on the bar,
  and the next prompt has the line;
- the same for a key that keeps the line, a key that ends it, and a password;
- events don't end the prompt while the boot is over its cap, and do again once it is
  raised;
- over the cap in a full-screen program: the action isn't sent, `keep_form` was called with
  a tick of 0, no form was shown again, and the next action is waited for;
- the cap is raised with `change`: the note goes, and the next line reaches the AI;
- a machine without a cap never holds anything back;
- a scripted run over its cap ends, with the note printed.

In `tests/test_blockmode.py`, with the real block mode on a pipe:

- after an action, `keep_form()` lets typing go into the field again;
- the action after it reports the field's text in full, as not seen by the AI;
- `keep_form(tick=0)` on a ticking raw program: the next wait has no tick.

## Done when

A test machine with a cap of one cent holds the second line back, the cap is raised with
`change`, and the same line goes through.
