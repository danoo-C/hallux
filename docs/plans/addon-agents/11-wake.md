# Step 11: a job's end in a full-screen program

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 8

**Needs:** step 10, and steps 3 and 7 of the
[config panel's plan](../config-panel/README.md). **Changes:** `hallux/machine.py`,
`hallux/blockmode.py`, `hallux/terminal.py`, `hallux/script.py`, `hallux/prompt_jobs.md`,
`tests/test_machine.py`, `tests/test_blockmode.py`.

After step 10 a full-screen program hears a job's end with its next key or tick. A form with
fields has no ticks, and a player's ticks stop when their budget is used up, so a player
would sit on "composing…" until a key is pressed. This step lets a job's end wake the
program.

## Build

**When it wakes.** A job event that may go out now (step 10's question: its addon is
listened to, and event budget is left) wakes the program:

| The event arrives | What happens |
|---|---|
| While the program waits for the user | The wait ends at once |
| While the AI answers a key, an action or a tick of the program | When that answer is done and shown, **before** the machine waits for the next key, it looks for such an event, and wakes |
| And may not go out: nobody listens, or the budget is used up | Nothing new: it goes in front of the program's next key, action or tick (step 10) |

- **The second row is the one that is easy to miss.** The machine goes from an answer
  straight into the wait (`hallux/machine.py:328-346`), and `wake_form()` only ends a wait
  that is running. A job that ends during a tick's answer, in a program whose ticks then
  stop, would never be heard.

**How it wakes.** Block mode's wait for an action can be started again since the panel's
step 7. It gets one more way to end: `wake_form()`, new on the terminal, makes it return an
action called `wake`, the way it returns a tick when the time is up.

- The machine sends the waiting job events as an `<events>` message of their own, and the
  program answers with its new screen or a patch.
- **Once per job,** since a job ends once. Two jobs that end together wake it once, with
  both events.
- **Its cost counts towards the event budget,** like an event at the shell prompt. When
  that budget is used up, the program isn't woken again until a line is typed.
- **While the config panel is open** over the program, the wake waits with everything else
  (the panel's rule).

**A program with fields keeps what the user typed.** A wake is the first message that
reaches the AI without the fields while such a program is up: ticks exist only in raw mode
(`hallux/blockmode.py:284`).

| What could go wrong | What Hallux does |
|---|---|
| The AI's answer restates a field's text, and the user's text is replaced (`hallux/blockmode.py:341-345`) | In the answer to a wake, the text the AI gives a field is ignored. The screen, a patch and the footer are taken |
| The model fails on the wake, and the machine leaves the program (`hallux/machine.py:388`) | The program stays on screen: the machine uses `keep_form()` (the panel's step 3), puts the error on the bar, and the event waits for the next message |
| The wake is held back because the boot is over its budget | The same: the program stays, and the event waits |

- What the user types during the wake's answer is held for the next screen, as during any
  answer.

**The prompt's section** gets a line: `<events>` can arrive while a full-screen program
runs; answer as the program would, with a patch, and leave its fields alone.

The scripted terminal and the tests' fake terminal get an empty `wake_form`.

## Tests

In `tests/test_blockmode.py`, with the real block mode on a pipe:

- `wake_form()` while the wait runs: it returns the action `wake`;
- in a program with fields: the field's text is the same after the wake, and typing goes on;
- keys typed during the answer go to the next screen;
- a wake and a tick that fall together give one action, not two.

In `tests/test_machine.py`:

- a raw-mode program without a tick, listening: a job ends, the AI gets `<events>` at once,
  and its patch is shown;
- **a job ends while the AI answers a key of the program,** and the program has no tick:
  after that answer the AI gets `<events>`, without another key;
- a program whose ticks are paused by the tick budget is still woken;
- not listening: no message goes out, and the event is in front of the next key;
- the event budget used up: the same, and the bar's note says so;
- the cost of the wake is in what the events have spent;
- two jobs end together: one message, two events;
- a program with a field: the answer to the wake gives the field a text, and the field
  keeps what the user typed;
- the model fails on the wake: the program is still on screen with its text, the error is
  on the bar, and the event is in front of the next action;
- the wake is held by the budget per boot: the same, and after the cap is raised the event
  goes out.

## Done when

In a test, a full-screen program with no ticks left shows "composing…", a job ends while
the AI answers the program's last tick, and the program's next screen arrives without a key
being pressed.
