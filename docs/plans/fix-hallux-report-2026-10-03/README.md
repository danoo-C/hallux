# Plan: fixing what Hallux reported about its environment

**Status:** written on 2026-10-05, then checked the same day against the code, the cards of
the test world and the machine's log, and corrected. A review followed the same day, with
two cases run against the machine, and changed the plans once more. The user approved both
rounds: "What the check changed" and "What the review changed" below list them. The other
decisions are my proposals. The table of the plans says what is built.

**Where this comes from.** On 2026-10-03 the machine in the user's test world was asked what
it thinks of its environment. It gave 8 out of 10 and named four places where it had to
guess. A guess is a place where two boots, or two models, decide differently, so each one is
a small hole in "the same machine every time". The user chose three of the four to fix now.

**How this plan is laid out.** One file per point of the report. The three don't depend on
each other, and each can be built and merged by itself. This file holds what they share.

**One sentence ties them together.** Point 4 writes down that a card comes before the
prompt's general rules, and points 1 and 2 lean on it. They can still be built first: their
tries start with a `hallux` line that changes the card, so the outcome doesn't hang on
that sentence.

## The report

As the machine wrote it:

> **hallux feedback on its environment (2026-10-03).** Rating: 8/10.
>
> Mostly clear: the disk is real, the addons have manuals, the program cards say what to do.
>
> Where I had to guess:
>
> 1. **Ticks:** they stopped mid-song and nothing told me. kittymusic was stuck waiting for
>    a "first tick" to start playing. I patched the card (play on the first key/click), but
>    a "ticks exhausted" signal would remove the guessing.
> 2. **Your files vs my files:** a hand-edited score had lost its gtr/lead/bass instruments.
>    Should I fix the user's file, or only report the error? I put the instruments back, but
>    it was a judgement call.
> 3. **Split panes:** lt-love means padding every row by counting characters, and symbols
>    like ♡ ╥ ✦ can be 1 or 2 columns wide depending on the font. Real column info, or a
>    pane field type, would keep the border straight.
> 4. **Rules vs requests:** the kittymusic card says 20-60 s songs and the user asked for 3
>    minutes. I went with the user, which I think is right, but it isn't written anywhere.
>
> Wishes for the coming GUI addon: a manual like the others (what it can draw, which events
> it sends back), so it can be used correctly from the first boot.

## The plans

| Point of the report | Plan | What kind of fix | Status |
|---|---|---|---|
| 1. Ticks stop and nothing says so | [point-1-ticks.md](point-1-ticks.md) | The machine marks every message while a program run has no ticks left, and the prompt says what that means | Built on 2026-10-05. The two tries in the test world are the user's, and open |
| 2. The user's file, or the program's | [point-2-whose-file.md](point-2-whose-file.md) | One rule in the prompt | Built on 2026-10-05, and tried by the user: "it did exactly what it should have done" |
| 4. A card's numbers against what the user asked for | [point-4-requests-and-cards.md](point-4-requests-and-cards.md) | One rule in the prompt with the order of rule, request, card and prompt, and where a `hallux` command goes | Built on 2026-10-05. The try in the test world is the user's, and open |

This table is the only place that holds the status.

**Left for later:**

| | Why |
|---|---|
| 3. Split panes | The user's decision on 2026-10-05: laying out panes is the job of a TUI addon, and comes with it. A sentence in the prompt can't fix it: how wide ♡ is depends on the terminal's font, and the AI can't know that |
| A label on the last tick (point 1) | Between the last tick and the next key a program's own screen can't say that it is paused. The machine could label a tick as the last by estimate, but that needs more state. The bar tells the user already. [point-1-ticks.md](point-1-ticks.md) has it under its decisions |
| The wish for a manual | It is so already: an addon without a manual isn't loaded. What the manual of a new addon has to say, what it draws and which events it sends, is checked when that addon is written, the way the music addon's manual was: a model that has read nothing else uses it |

## What the three share

- **All three change `hallux/prompt.md`.** That file is everything the AI knows about its
  world. Point 1 also changes what the machine sends.
- **The prompt grows by about twenty-five lines,** on 272 before the first of the three was
  built. It is sent with every message and cached.
- **A test can hold the words, not the behaviour.** Each plan tests that the prompt says
  the new rule, as `tests/test_addons.py` does for addons, and point 1 tests what the
  machine sends. Whether the AI then acts on it shows only with a real model. So each plan
  ends with a try by hand in the test world. Those are a few commands of normal use.
- **Each try repeats the case from the report.** All three happened in kittymusic on
  2026-10-02, between 23:14 and 23:39, and the machine's log in the test world has every
  message of it. Points 1 and 2 were in the same run of the program. Each plan tells what
  the log shows.
- **`docs/concept.md` follows in its own sections,** which each plan names. The prompt it
  shows under "The system prompt" is the first draft, kept for history, and stays as it is.
- **Cards that exist stay as they are.** A card is the user's and the machine's; nothing
  here rewrites one. Where a card in the test world says something else than the new rule,
  the plan says so, and names the `hallux` command that would change it.
- **A card comes before the prompt's general rules,** for its own program. So where a card
  says something else, that `hallux` command is the first step of the plan's try.
- **Any order.** Points 2 and 4 are prompt rules only. Point 1 has code, and is the one
  that left a program stuck.

## Decisions these plans take

Each plan's file says more.

| Point | Topic | Decision | Why |
|---|---|---|---|
| 1 | How the AI learns that ticks are paused | A mark on the messages that go anyway: `ticks="paused"` | It costs nothing. A message of its own would be a model call after the budget is used up |
| 1 | Which messages carry it | Every one, while the program run's tick budget is used up, also from a screen that asked for no tick | The stuck song was picked on a screen without a tick |
| 1 | What it learns | That they are paused, not why | The budgets are the machine's hardware, which it can't see |
| 1 | The stuck program | A rule: don't depend on a tick. Do it on the first message that arrives, and at once when ticks are paused | "Never wait for a tick" would forbid kittymusic's start order, which is there on purpose |
| 1 | A tick that arrives while the tick budget is used up | It is not sent | A budget lowered under a ticking program lets one more tick out today, and it would carry the mark |
| 1 | The end of a boot | It leaves the program: the count, `in_form` and the bar's note | A boot that ends inside a program leaves all three behind while the next `<boot>` goes out |
| 2 | A file with a mistake in it | The program says what is wrong and where, and leaves the file alone | It is what a real program does, and a repair from memory can be wrong |
| 2 | A file the program wrote itself in this run | It may correct it, as long as the file is still as it wrote it | Otherwise a program couldn't fix its own draft. The score in the report was the program's own, changed by hand afterwards |
| 2 | Where the rule stands | Under PROGRAMS, not under THE DISK IS REAL | A card can then change it for one program, and a rule made with `hallux` for all |
| 4 | A card against a request | The request comes first, in the program's arguments or typed into it. A card's numbers and habits are defaults | It is how options work on a real program, and it is what the machine did |
| 4 | A limit that must hold | It is made a rule, with `hallux`, and the prompt says that such a limit goes into the Rules and not into the card | Rules come before a request. In the card it would be a default |
| 4 | A request against a rule | The rule comes first | This is new. A limit needs a place where it holds. The user confirmed it on 2026-10-05 |
| 4 | How strict a rule is | Its own words say. "By default" leaves room for a request | Otherwise the AI would have to judge every rule |
| 4 | A card against the prompt's general rules | The card comes first, for its own program | A card is more exact than a rule for every program, and it is how the machine behaves |
| 4 | A `hallux` line that could be a habit or a limit | Into the card, and the confirming line says where it went | A wrong guess towards the card is the mild one, and the user sees the place |

## What the check changed

The first version of these plans was read against `hallux/machine.py`, `hallux/protocol.py`,
the tests, kittymusic's card and the log. Each plan missed the case it came from. The user
approved these corrections on 2026-10-05.

| Point | The first version | Now | What the check found |
|---|---|---|---|
| 1 | The mark is on a message only while the screen that is up asked for a tick | It is on every message while the program run's tick budget is used up | The song that got stuck was picked on kittymusic's library screen, which asks for no tick |
| 1 | A rule: never wait for a tick | Don't depend on a tick: the first message that arrives, and at once when ticks are paused | The card waits for the first tick on purpose, so that the screen is up before the song starts |
| 1 | Nothing on the form while ticks are paused | The form keeps its tick | The machine restarts only a tick that is asked for |
| 1 | "A form with fields that names a tick counts as having asked for one", and a change for it | Taken out | The parser drops that tick already, and a test holds it |
| 1 | A test for the mark while the boot's budget stopped the ticks | The test says there is none | Nothing is sent while that budget is used up, and raising it restarts the ticks before the next key |
| 1 | The count of a program's ticks starts anew when the program is left | Also when a boot starts | A boot can end inside a program, and the mark would then be on the next boot's messages |
| 2 | A program may correct what it wrote during this run | Only while the file is still as it wrote it | The repaired score was composed and changed by the machine in that same run, and then edited by hand |
| 2 | kittymusic's card "agrees with the rule" | Its line is wider than the rule, and the plan names the command that tightens it | "A score the machine composed itself is fixed" fits the repair that was made |
| 2 | The try by hand breaks a copy made with `cp` | It breaks a song the program just composed, from outside the machine | The program never wrote the copy, so that try passes with the old rule too |
| 4 | What the user asks for "on the command line" | What the user asks the program for, in its arguments or typed into it | The three minutes were typed into kittymusic's own line |
| 4 | A limit is made a rule with `hallux` | And the prompt says that it goes into the Rules, not into the card | Every change to kittymusic so far went into its card |
| 4 | A rule before a request "is what the prompt says today" | It is a new decision | The prompt says only that rules override the prompt |
| 2, 4 | The prompt copied in `docs/concept.md` gets the new rules | The sections on programs and on rules get them | That copy is the first draft, kept for history |

## What the review changed

The corrected plans were reviewed on 2026-10-05, again against the code, the cards and the
log. Two cases of point 1 were run against the machine with the fakes of
`tests/test_machine.py`, and both code changes were tried on a copy: the tests gave the
same results as before. The user approved these changes the same day.

| Point | Before the review | Now | What the review found |
|---|---|---|---|
| 1, 2, 4 | Nothing said whether a card or the prompt's general rule comes first | Point 4's rule says it: the card, for its own program | kittymusic's card says otherwise than the new rules of points 1 and 2 |
| 1 | The try for the report's case took both outcomes as right | Its first step changes the card with `hallux`, and one outcome is expected | The card's START ORDER comes before the prompt's "at once" |
| 2 | Tightening the card was left open before the try | It is the try's first step | Without it the card allows the repair, and the try can't show the rule |
| 2 | The rule stands under PROGRAMS so that a rule from `hallux` can change it for one program | So that a card can, and a rule for all | Point 4 sends `hallux kittymusic may repair my scores` into the card |
| 4 | A `hallux` line about a program goes into the card, a limit into the Rules | When it isn't clear which, into the card, and the confirming line says where | "Never more than a minute" is a limit. "Always uses a piano" could be either |
| 4 | The paragraph above the new line still sent "everything else" into the Rules | It names the card | The two disagreed |
| 4 | Nothing on the rules that exist | The try ends with a look through them, and those meant as defaults are reworded | The htop rule of the test world would win over `htop -d 50` |
| 1 | The mark is on every message while the tick budget is used up | A tick that arrives then is not sent, so no `<tick>` carries the mark | A budget lowered under a ticking program let one more tick out (run against the machine) |
| 1 | A boot starts the count at zero | The end of a boot leaves the program: the count, `in_form` and the bar's note | All three were still there while the next `<boot>` went out (run against the machine) |
| 1 | A label on the last tick isn't built, because the machine can't know which is the last | It is left for later, because the machine could only estimate | The reason was too strong |
| 1 | "A form with fields never ticks" | "A form without `raw="yes"` never ticks" | The parser keeps the tick of a raw form |
| 1 | The prompt's INPUT lists what every message carries, without the mark | It names the mark | With `tick_budget_usd = 0` the mark is on `<boot>` too |
