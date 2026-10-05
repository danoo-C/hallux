# Point 1: ticks stop, and nothing says so

[The plan](README.md) · the report's point 1

**Needs:** nothing. **Changes:** `hallux/machine.py`, `hallux/prompt.md`,
`tests/test_machine.py`, `docs/concept.md`.

> Ticks: they stopped mid-song and nothing told me. kittymusic was stuck waiting for a
> "first tick" to start playing. I patched the card (play on the first key/click), but a
> "ticks exhausted" signal would remove the guessing.

## What happens today

- **A program asks for ticks** with `<form raw="yes" tick="3">`, and the terminal wakes it
  every 3 seconds with `<tick>`.
- **The machine takes the ticks away** in three cases, by showing the program's screen with
  no tick: the tick budget of this program run is used up, the boot is over its budget, or
  the program comes up while either is so (`hallux/machine.py`, `block_mode`).
- **The AI isn't told.** The prompt has one sentence: "The terminal may stop ticking when a
  budget is used up; the program then just waits for a key." It says that it can happen,
  not when it has.
- **Since the settings panel, ticks also come back:** a higher budget or Refill budgets
  gives the program its tick again. The AI isn't told that either; a `<tick>` just arrives.
- **What went wrong.** kittymusic's card said to call `play()` on the first `<tick>`. No
  tick came, so the song never started. The machine then guessed, from a key that arrived
  before any tick had.

## Build

**The mark.** While a raw-mode program that asked for a tick has its ticks stopped, every
message the machine sends into that program says so:

```text
<keys ticks="paused" cwd="/home/user" time="…" cols="100" rows="29"><text>j</text></keys>
```

- **It rides on a message that goes anyway:** `<keys>`, which is all a raw-mode program
  gets besides `<tick>`. No message is sent to say it. A scripted run sends `<action>` into
  such a program, and that carries the mark too.
- **No mark means ticks run,** or the program never asked for one.
- **When the ticks come back, a `<tick>` arrives,** as today, and the mark is gone from the
  next `<keys>`.
- **In the code:** the machine knows already whether a budget has stopped the ticks of the
  program on screen (`ticks_stopped`, from the panel's step 7). `block_mode` adds the mark
  to what it sends when that is so.
- **Only raw-mode programs tick.** Today a form with fields that names a tick counts as
  having asked for one, though block mode never ticks it. The machine takes the tick a
  program asked for from a raw form only, so such a form gets no mark and no `set_tick`.

**The prompt,** under RAW MODE. The last sentence of that section goes, and two things take
its place:

```text
- Ticks can stop. The terminal pauses them when one of the machine's budgets is used up,
  and may start them again. While they are paused, every message in the program carries
  ticks="paused": nothing wakes you then but a key or a click. Show that what should move
  stands still (a line such as "paused: press a key to update"), and bring the screen up
  to date with every key. When a <tick> arrives again, they are back.
- Never wait for a tick to do what the command is for. Start the song, open the file,
  load the data when the program starts. A tick only redraws.
```

**`docs/concept.md`:** the "Ticks" line under raw mode says that the program "just waits
for a key". It gets the mark and the rule.

## What doesn't change

- **The bar's note,** `live updates paused: tick budget used`, and the panel. They are the
  user's side of the same thing, and they work.
- **No message when the ticks stop.** See the decisions below.
- **Cards on the disk.** kittymusic's card in the test world has lines of its own for this
  by now: play on the first key or click, and say that ticks ran out. They agree with the
  new rule. Its line "call play() only on the FIRST tick" does not; the user can change it
  with `hallux`.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| When the AI is told | With the next message that goes anyway | A message of its own is a model call, made after the budget is used up |
| A last tick that says "this is the last" | Not built | The machine learns that the budget is used up from the cost of that tick's answer, so it can't mark the tick before sending it |
| What the mark says | `paused`, and no reason | The budgets are hardware. The prompt names "a budget" and no more |
| The stuck program | A rule in the prompt, beside the mark | With the mark alone a program that starts its work on a tick still waits for the first key |

## Tests

In `tests/test_machine.py`, with the fake model and the fake terminal:

- a ticking program whose tick budget runs out: the `<keys>` after that has
  `ticks="paused"`, and none before it has;
- the same when the budget per boot stopped the ticks, and when the program came up with
  the budget used already;
- the budget is raised: the next message has no mark;
- a program that asked for no tick never has the mark, also when the boot is over its
  budget;
- a form with fields that names a tick: no mark, and `set_tick` isn't called for it;
- the prompt has both new rules, and no longer says "just waits for a key".

## Done when

The tests pass, and the user has tried it in the test world:

1. In the panel, set the tick budget to `0.01`.
2. Start a program that ticks, such as `top`, and press a key once its updates are paused.
3. Raise the tick budget in the panel.

**Should happen:** after the key the program's own screen says that its updates are paused,
and it is up to date. After the budget is raised it moves again, and that line is gone.
