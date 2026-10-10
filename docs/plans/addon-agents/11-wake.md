# Step 11: a job's end in a full-screen program

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 8

**Needs:** step 10, and steps 3 and 7 of the
[config panel's plan](../config-panel/README.md). **Changes:** `hallux/machine.py`,
`hallux/blockmode.py`, `hallux/terminal.py`, `hallux/script.py`, `hallux/prompt_jobs.md`,
`tests/test_machine.py`, `tests/test_blockmode.py`.

After step 10 a full-screen program hears a job's end with its next key or tick. A player's
ticks stop when their budget is used up, so a player would sit on "composing…" until a key
is pressed. This step lets a job's end wake a program that has no fields: a player, `htop`,
anything in raw mode.

## Build

**Which program is woken.** One without fields. A program with fields, such as nano, a
pager or a form with a line to type into, isn't woken: the event goes in front of its next
action, as when nobody listens.

- **Why not a program with fields.** A wake would be the one message that reaches the AI
  without the fields while such a program is up. Its answer could then lose what the user
  typed, in three ways: it restates a field's text (`hallux/blockmode.py:432-436`), it
  leaves the field out, and the prompt says such a field disappears
  (`hallux/prompt.md:132-133`), or it is a plain screen and prompt, which ends the program
  (`hallux/machine.py:672`). A model at low effort may well answer a job's end with bash's
  `Done` line. Unsaved text in an editor must not depend on that.
- **How the machine tells:** by the fields it knows on screen. A form has fields or is raw,
  never neither.
- **Decided on 2026-10-05.** Until then the plan woke every program and guarded the fields.

**When it wakes.** A job event that may go out by itself (step 10's question, all four
parts) wakes a program without fields:

| The event arrives | What happens |
|---|---|
| While the program waits for the user | The wait ends at once |
| While the AI answers a key or a tick of the program | When that answer is done and shown, **before** the machine waits for the next key, it looks for such an event, and wakes |
| And may not go out by itself | Nothing new: it goes in front of the program's next key or tick (step 10) |
| In a program with fields | The same: in front of its next action |

- **The second row is the one that is easy to miss.** The machine goes from an answer
  straight into the wait (`hallux/machine.py:568-602`), and `wake_form()` only ends a wait
  that is running. A job that ends during a tick's answer, in a program whose ticks then
  stop, would never be heard.
- **A budget that is raised wakes too.** `settle()` asks the question again (step 10), so
  an event that waited for the event budget or the budget per boot wakes the program when
  the panel has raised it.

**How it wakes.** Block mode's wait for an action gets one more way to end: `wake_form()`,
new on the terminal, makes it return an action called `wake`, the way it returns a tick
when the time is up. It answers whether it did.

- **While the AI is busy with the screen,** `wake_form()` does nothing and says no. The
  machine looks again when the answer is shown.
- **While the config panel is open** over the program, the wake waits with everything else
  (the panel's rule). Block mode remembers that it was asked, and the wait returns `wake`
  when the panel closes. The terminal does the same for an event at the prompt
  (`hallux/terminal.py:163-165`).
- **In a form with fields** `wake_form()` does nothing and says no, whoever calls it.
- **The machine asks the question again when it gets a `wake`.** The event may have gone
  out meanwhile, in front of keys that were typed. With nothing to send, the program stays
  as it is, by `keep_form()` (the panel's step 3).
- The machine sends the waiting job events as an `<events>` message of their own, and the
  program answers with its new screen or a patch.
- **Once per job,** since a job ends once, and by step 10's rule also when the message
  fails. Two jobs that end together wake it once, with both events.
- **Its cost counts towards the event budget,** like an event at the shell prompt. When
  that budget is used up, the program isn't woken again until a line is typed or the budget
  is raised.
- What the user types during the wake's answer is held for the next screen, as during any
  answer.

**If the model fails on the wake.** Today a failed message leaves the program
(`hallux/machine.py:657`). After a wake that would take the player off the screen though
nobody touched it. So the program stays: the machine uses `keep_form()`, the error is on
the bar, and the event waits for the next message. It doesn't wake again.

**The prompt's section** gets a line. RAW MODE says of paused ticks that "only a key or a
click wakes you" (`hallux/prompt.md:189`), and of a program that waits that it acts "on the
first message that arrives, a tick or a key" (`hallux/prompt.md:193-195`). The line says:
in a full-screen program without fields a job's event can arrive by itself, also while
ticks are paused. Answer as the program would, with a patch. It counts as a message that
arrives.

The scripted terminal gets an empty `wake_form` that says no. The tests' fake terminal gets
one that works: it ends the fake's scripted wait for an action, as its `interrupt_prompt`
ends a scripted wait at the prompt (`tests/test_machine.py:149-156`).

## Tests

In `tests/test_blockmode.py`, with the real block mode on a pipe:

- `wake_form()` while the wait runs: it says yes, and the wait returns the action `wake`;
- in a form with fields: it says no, the wait goes on, and the field's text is untouched;
- while an action is with the AI: it says no;
- keys typed during the answer to a wake go to the next screen;
- a wake and a tick that fall together give one action, not two;
- with the panel open over the program: nothing returns until the panel closes, then the
  wait returns `wake`.

In `tests/test_machine.py`:

- a raw-mode program without a tick, listening: a job ends, the AI gets `<events>` at once,
  and its patch is shown;
- **a job ends while the AI answers a key of the program,** and the program has no tick:
  after that answer the AI gets `<events>`, without another key;
- a program whose ticks are paused by the tick budget is still woken, and the message
  carries `ticks="paused"`;
- not listening: no message goes out, and the event is in front of the next key;
- the event budget used up: the same, and the bar's note says so; the budget is raised in
  the panel, and the program is woken;
- the cost of the wake is in what the events have spent;
- two jobs end together: one message, two events;
- a program with a field, listening: no message goes out, the field keeps what the user
  typed, and the event is in front of the next action;
- the model fails on the wake: the program is still on screen, the error is on the bar, no
  second wake follows, and the event is in front of the next key;
- the boot is over its budget: the program isn't woken, not even once; after the cap is
  raised it is;
- a `wake` arrives when the event has gone out already: no message goes out, and the
  program takes keys again.

## Before the user tries it

A check on a pseudo-terminal, with a terminal emulator drawing the screen, as for the
panel's steps 6 and 7: a raw-mode program with the bar pinned, a wake, and the patch on the
rows where it belongs. A test on a pipe pins no bar and can't show that.

## Done when

In a test, a full-screen program with no ticks left shows "composing…", a job ends while
the AI answers the program's last tick, and the program's next screen arrives without a key
being pressed.

## As built

Built on 2026-10-06, on the branch `addon-agents`. 21 new tests, 1465 in all; no old test
changed. Decided while building:

**The wake**

- **`BlockMode.wake()` is the wake,** and `Terminal.wake_form()` calls it. The scripted
  terminal's says no.
- **A wake is an action in block mode's own queue,** put there the way a key's action is.
  So what is typed after it waits for the next screen, as after any action. And a wake and
  a tick can't both come: whichever is first is with the AI, and `wake()` says no while an
  action is with the AI.
- **Under the panel, block mode notes that it was asked** (`wake_asked`) and sends the wake
  when the panel closes. A program that ends under the panel takes the note with it.

**The machine**

- **`job_event_waits()` wakes whoever waits for the keyboard:** the shell prompt, or a
  program that has no fields. It is still the one place that asks `due()` for this.
- **`block_mode()` calls it after every screen it shows.** That is the look before the
  wait: a job that ended while the AI answered is found there.
- **When the action `wake` comes back, the machine asks `due()` again.** With something
  due it sends `send_events(client, [], due, stay=True)`. With nothing, or when the model
  failed on it, it calls `keep_form()` and waits on.
- **`send(…, stay=True)` returns nothing when the model fails,** and doesn't leave the
  program. Only the wake uses it.
- **A wake that reaches a program with fields is never sent,** whoever asked for it: the
  machine looks at its fields again when the action comes back. Block mode refuses such a
  wake already; this is the second lock.
- **The addons' own events aren't taken into a wake.** They wait until the program ends,
  as before this step.

**The prompt's section** got one line in "What is real": in a full-screen program without
fields a job's event can arrive by itself, also while ticks are paused, and counts as a
message that arrives. "How it shows" says that such a program answers as it would to a
tick, with a patch.

**The tests' fake terminal** got `wake_form()` and a scripted action, `Sitting`: the user
sits in front of a program and presses nothing until it is woken.

**The "Done when" is a test:** a ticking program shows "composing…", the answer to its tick
uses up the tick budget, a job ends during that answer, and the program's next screen
arrives with no key pressed. Its message carries `ticks="paused"`.

**How I checked the tests themselves:** six wrong versions of the machine's side, one at a
time: no look before the wait, a program with fields woken too, a failed wake leaving the
program, a wake sent without asking again, a wake sent in a program with fields, the shell
prompt no longer woken. Each fails a test.

**The check on a pseudo-terminal, before the user tries it.** The real machine with the
real terminal, its bar and its panel, on a pseudo-terminal of 24 rows and 80 columns. The
model was a pretend one and the job's worker a stand-in. The bytes were replayed through a
terminal emulator (`pyte`), with one screen for the shell and one for the alternate screen.

| Run | What the screen showed |
|---|---|
| A job ends while the program waits | Row 2 went from `composing…` to `playing night.score` with no key pressed. Row 1, the footer on row 23 and the bar on row 24 stayed as they were, and nothing else changed |
| The same, with the wake switched off | Five seconds on, the program still said `composing…`. So the check can fail |
| The panel is open over the program when the job ends | The panel stayed up and nothing of the wake showed. After Esc the patch was on row 2, and no line of the panel was left |
| After `q`, in all three | The shell's text in order, the prompt under it, and the bar on the last row only |

**What I couldn't check**

- **What a real model answers to a wake:** a patch, or bash's `Done` line, which would end
  the program. The first live run is in step 13.
- **A real terminal.** The emulator shows where the text lands, not how it looks while it
  changes.
- **A wake and a tick in the very same moment.** Both orders are tested, one after the
  other.

**Nothing can be tried by hand yet:** no real addon has an agent before step 13.
