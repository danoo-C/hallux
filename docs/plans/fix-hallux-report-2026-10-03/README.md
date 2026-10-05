# Plan: fixing what Hallux reported about its environment

**Status:** written on 2026-10-05. Nothing is built. The decisions each plan takes are my
proposals, and the user hasn't confirmed them yet.

**Where this comes from.** On 2026-10-03 the machine in the user's test world was asked what
it thinks of its environment. It gave 8 out of 10 and named four places where it had to
guess. A guess is a place where two boots, or two models, decide differently, so each one is
a small hole in "the same machine every time". The user chose three of the four to fix now.

**How this plan is laid out.** One file per point of the report. The three don't depend on
each other, and each can be built and merged by itself. This file holds what they share.

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
| 1. Ticks stop and nothing says so | [point-1-ticks.md](point-1-ticks.md) | The machine marks its messages while ticks are paused, and the prompt says what that means | Not built |
| 2. The user's file, or the program's | [point-2-whose-file.md](point-2-whose-file.md) | One rule in the prompt | Not built |
| 4. A card's numbers against what the user asked for | [point-4-requests-and-cards.md](point-4-requests-and-cards.md) | One rule in the prompt | Not built |

This table is the only place that holds the status.

**Left for later:**

| | Why |
|---|---|
| 3. Split panes | The user's decision on 2026-10-05: laying out panes is the job of a TUI addon, and comes with it. A sentence in the prompt can't fix it: how wide ♡ is depends on the terminal's font, and the AI can't know that |
| The wish for a manual | It is so already: an addon without a manual isn't loaded. What the manual of a new addon has to say, what it draws and which events it sends, is checked when that addon is written, the way the music addon's manual was: a model that has read nothing else uses it |

## What the three share

- **All three change `hallux/prompt.md`.** That file is everything the AI knows about its
  world. Point 1 also changes what the machine sends.
- **The prompt grows by about fifteen lines,** on 272 today. It is sent with every message
  and cached.
- **A test can hold the words, not the behaviour.** Each plan tests that the prompt says
  the new rule, as `tests/test_addons.py` does for addons, and point 1 tests what the
  machine sends. Whether the AI then acts on it shows only with a real model. So each plan
  ends with a try by hand in the test world. Those are a few commands of normal use.
- **`docs/concept.md` copies parts of the prompt,** under "The system prompt". Each plan
  names the lines that have to follow.
- **Cards that exist stay as they are.** A card is the user's and the machine's; nothing
  here rewrites one. Where a card in the test world says something else than the new rule,
  the plan says so.
- **Any order.** Points 2 and 4 are a rule each. Point 1 has code, and is the one that left
  a program stuck.

## Decisions these plans take

My proposals. Each plan's file says more.

| Point | Topic | Decision | Why |
|---|---|---|---|
| 1 | How the AI learns that ticks are paused | A mark on the messages that go anyway: `ticks="paused"` | It costs nothing. A message of its own would be a model call after the budget is used up |
| 1 | What it learns | That they are paused, not why | The budgets are the machine's hardware, which it can't see |
| 1 | The stuck program | A rule: never wait for a tick to do what the command was for | The mark arrives with the next key. A program that waits for a tick to start would still wait until then |
| 2 | A file with a mistake in it | The program says what is wrong and where, and leaves the file alone | It is what a real program does, and a repair from memory can be wrong |
| 2 | A file the program wrote itself in this run | It may correct it | Otherwise a program couldn't fix its own draft |
| 2 | Where the rule stands | Under PROGRAMS, not under THE DISK IS REAL | A rule made with `hallux` can then change it for one program |
| 4 | A card against the command line | The command line comes first. A card's numbers and habits are defaults | It is how options work on a real program, and it is what the machine did |
| 4 | A limit that must hold | It is made a rule, with `hallux` | Rules come before a request already. A card needs no second kind of sentence |
