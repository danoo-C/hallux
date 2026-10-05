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
- **The tick budget counts for the whole run of a program,** over all its screens. It starts
  anew when the program goes back to the shell.
- **The AI isn't told.** The prompt has one sentence: "The terminal may stop ticking when a
  budget is used up; the program then just waits for a key." It says that it can happen,
  not when it has.
- **Since the settings panel, ticks also come back:** a higher budget or Refill budgets
  gives the program its tick again. The AI isn't told that either; a `<tick>` just arrives.
- **A lowered tick budget counts from the next screen.** When the budget is set under what
  the run has spent while a program ticks, one more `<tick>` still goes out, and the pause
  comes with the screen after it.
- **A boot that ends inside a program** (a form with `<reboot/>`) leaves the program's
  state behind. The count, `in_form` and the bar's note are all still there while the next
  `<boot>` is sent.

**What went wrong,** from the machine's log in the test world, on 2026-10-02:

| Time | What happened |
|---|---|
| 23:35:00 | The last `<tick>` of a song in kittymusic. The ticks stop mid-song |
| 23:38:40 | A click. The machine goes back to kittymusic's library: a form with a field, and no tick |
| 23:38:54 | The user types `2` there: play song 2 |
| 23:39:06 | The machine draws the now-playing screen with `tick="2"`, and waits for the first tick to call `play()` |
| 23:39:29 | No tick came. The user clicks, and only then `play()` is called |

- **The card waits for the first tick on purpose.** Its START ORDER says never to call
  `play()` before the now-playing screen is on screen: the song starts when the user sees
  it, and the bar counts from there. All the tool calls of an answer run before its screen
  is shown, so a tick is the only "afterwards" a program has.
- **The message that started the song came from a screen that asks for no tick.** Whatever
  tells the AI has to be on that message, or the AI guesses again.

## Build

**The mark.** While the tick budget of the program run is used up, every message the
machine sends says so:

```text
<action key="Enter" focus="q15" ticks="paused" cwd="/home/user" time="…" cols="120" rows="29">
<keys ticks="paused" cwd="/home/user" time="…" cols="120" rows="29"><text>j</text></keys>
```

- **It means: no tick comes now, whatever the form asks for.** It is on the messages from
  every screen of the program, also from one that asked for no tick. So the AI knows before
  it draws a screen that would tick.
- **It rides on messages that go anyway.** No message is sent to say it.
- **No mark means ticks run** for a form that asks for one.
- **When the budget allows ticks again,** the next message has no mark. A program whose
  screen asks for a tick gets a `<tick>`, as today.
- **In the code:** `Machine.envelope` builds every message. It adds the mark when
  `tick_spent` has reached `tick_budget_usd`. The mark stands after the message's own
  attributes and before `cwd`, so the tests that pin a message by its tag and its own
  attributes stay as they are.
- **At the shell the count is zero,** so there is no mark there. One exception: with
  `tick_budget_usd = 0` ticks are off, and every message of the boot carries the mark,
  `<boot>` too.
- **No `<tick>` carries the mark.** A tick that arrives while the tick budget is used up is
  not sent: the program stays on screen without ticks, and the bar gets its note. It is
  what `block_mode` does already while the boot's budget is used up. It covers a budget
  that is lowered under a ticking program, where the tick would otherwise go out with the
  mark: a tick that says no tick comes.
- **A boot's end leaves the program.** `power_on` ends with `leave_block_mode()` in place
  of `terminal.end_form()`. That resets the count, `in_form` and the bar's note together,
  however the boot ended. Today only leaving a program does that, so after a boot that
  ends inside a program the next `<boot>` would carry a mark that isn't true.
- **The boot's budget needs no mark.** While it is used up, the machine sends nothing at
  all. When it is raised, the ticks are back before the next key goes out.
- **`ticks_stopped` stays for what it does today:** it starts the ticks again when a budget
  allows it. The mark doesn't use it.

**The prompt,** under RAW MODE. The last sentence of that section goes, and two things take
its place:

```text
- Ticks can stop. The terminal pauses them when one of the machine's budgets is used up,
  and may start them again. While they are paused, every message carries ticks="paused":
  no <tick> comes then, whatever the form asks for, and only a key or a click wakes you.
  Keep tick in the form all the same: that is how they start again. Show that what should
  move stands still (a line such as "paused: press a key to update"), and bring the screen
  up to date with every key.
- Don't let a program depend on a tick. What has to wait until its screen is up (a song
  that starts when the player shows) is done on the first message that arrives, a tick or
  a key, and at once when ticks are paused.
```

- **"Keep tick in the form":** the machine starts again only a tick that the form on screen
  asks for (`settle`). A form that dropped its tick would stand still after the budget is
  raised, until a key.
- **"On the first message that arrives":** a program may still wait for its screen, as
  kittymusic does. It may not wait for a tick alone.

**And under INPUT,** the first sentence names the mark. With `tick_budget_usd = 0` it is on
`<boot>` and on the shell's messages too, and that sentence lists what every message
carries:

```text
Every message carries the cwd, the local time and the terminal size (cols, rows), and
ticks="paused" while ticks are paused (see RAW MODE). It is one of these:
```

**`docs/concept.md`:** the "Ticks" line under raw mode says that the program "just waits
for a key". It gets the mark and the rule.

## What doesn't change

- **The bar's note,** `live updates paused: tick budget used`, and the panel. They are the
  user's side of the same thing, and they work.
- **No message when the ticks stop.** See the decisions below.
- **A form without `raw="yes"` never ticks.** The parser drops its tick already
  (`hallux/protocol.py`), and `tests/test_protocol.py` holds that.
- **Cards on the disk.** kittymusic's card stays as it is:
  - Its START ORDER, `play()` on the first tick, holds while ticks run.
  - Its NO TICKS section starts the song on the first key or click. It was written when the
    machine couldn't know beforehand that ticks were paused.
  - **The card comes before the prompt here.** For its own program a card comes before
    what the prompt says about programs in general
    ([point 4](point-4-requests-and-cards.md) writes that down). The card says "NEVER call
    play() before the now-playing screen is on screen", so with this card the song still
    waits for the first key while ticks are paused. The prompt's "at once" is for programs
    whose card doesn't say.
  - **What the mark still gives kittymusic:** the message that picks the song carries it,
    so the now-playing screen can say from the start that a key is needed.
  - **To start at once,** one line changes the card:
    `hallux kittymusic starts the song at once when ticks are paused`. It is the first step
    of the try below.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| What the mark means | No tick comes now. It is on every message while the program run's tick budget is used up | The stuck song was picked on a screen without a tick. A mark only on the screens that tick would not have been on that message |
| When the AI is told | With the next message that goes anyway | A message of its own is a model call, made after the budget is used up |
| A last tick that says "this is the last" | Left for later | The machine learns that the budget is used up from the cost of that tick's answer. It could estimate from the tick before, and pause after a tick it labelled. That needs more state: the last cost, a flag for "paused early", and the mark and the restart following that flag. The bar tells the user already, and the stuck song is fixed without it |
| A tick that arrives while the tick budget is used up | It is not sent | A budget lowered under a ticking program lets one more tick out today, and it would carry the mark. The boot's budget is held the same way already |
| The end of a boot | It leaves the program: the count, `in_form` and the bar's note | A boot that ends inside a program leaves all three behind while the next `<boot>` goes out |
| kittymusic's card against "at once" | The card comes first. The user changes it with one `hallux` line, the first step of the try | A card comes before the prompt's general rules ([point 4](point-4-requests-and-cards.md)), and its start order is there on purpose |
| What the mark says | `paused`, and no reason | The budgets are hardware. The prompt names "a budget" and no more |
| The boot's budget | No mark | Nothing is sent while it is used up, and the ticks are back as soon as it is raised |
| Ticks switched off, `tick_budget_usd = 0` | The mark is on every message of the boot | It is true: no program will tick. It costs a few characters |
| The stuck program | A rule: don't depend on a tick. Do it on the first message, and at once when ticks are paused | "Never wait for a tick" would forbid kittymusic's start order, which is there on purpose |
| The form while ticks are paused | It keeps its tick | The machine restarts only a tick that is asked for |

## Tests

In `tests/test_machine.py`, with the fake model and the fake terminal:

- a ticking program whose tick budget runs out: the `<keys>` after that has
  `ticks="paused"`, and no message before it has;
- the case from the log: the program then shows a form with a field and no tick, and the
  `<action>` from that form has the mark;
- the budget is raised, or the budgets are refilled: the next message has no mark;
- the program is left: the next `<input>` at the shell has no mark;
- `tick_budget_usd = 0`: every message has the mark, `<boot>` and `<input>` too;
- the tick budget is lowered under what the run has spent while a program ticks: the tick
  that arrives then is not sent, the form is kept without ticks and the bar has its note.
  Raising the budget starts the ticks again;
- no `<tick>` in any of these tests has the mark;
- a boot that ends inside a program whose tick budget is used up: the next `<boot>` has no
  mark, the bar's note is gone, and the machine is no longer in a form;
- the boot's budget is used up and then raised: the `<keys>` that goes then has no mark;
  with the tick budget used up as well, it has;
- Ctrl-C while the AI answers inside a paused program: the `<key … interrupted="yes">` has
  the mark;
- the prompt has both new rules, no longer says "just waits for a key", and names the mark
  under INPUT.

The test that holds a budget lowered while a tick is answered stays as it is: the next
screen comes up without ticks.

## Done when

The tests pass, and the user has tried both in the test world.

**A program that ticks:**

1. In the panel, set the tick budget to `0.01`.
2. Start a program that ticks, such as `top`, and press a key once its updates are paused.
3. Raise the tick budget in the panel.

**Should happen:** after the key the program's own screen says that its updates are paused,
and it is up to date. After the budget is raised it moves again, and that line is gone.

**The case from the report,** with a song that exists, so nothing is composed:

1. `hallux kittymusic starts the song at once when ticks are paused`. The card comes before
   the prompt, so the card has to say it: see "Cards on the disk" above.
2. In the panel, set the tick budget to `0.01`.
3. Start kittymusic and play a song. After a tick or two the bar says
   `live updates paused: tick budget used`.
4. Go to the library with `l`, and pick a song.

**Should happen:** in 1 the card says that a song starts at once while ticks are paused. In
4 the song starts without another key or click, and the screen says that its updates are
paused.

**Without step 1** the card holds: the song waits for the first key, and the now-playing
screen should say from the start that its updates are paused.
