# Point 2: the user's file, or the program's

[The plan](README.md) · the report's point 2

**Needs:** nothing. **Changes:** `hallux/prompt.md`, `tests/test_machine.py`,
`docs/concept.md`.

> Your files vs my files: a hand-edited score had lost its gtr/lead/bass instruments.
> Should I fix the user's file, or only report the error? I put the instruments back, but
> it was a judgement call.

## What happens today

- **The prompt doesn't say.** THE DISK IS REAL says that every change to a file really
  happens. It doesn't say when a program may change a file that it was only asked to read.
- **kittymusic's card says:** "a score the machine composed itself is fixed and replayed".
  It doesn't say what holds once somebody else has changed that score.

**What went wrong,** from the machine's log in the test world, on 2026-10-02. All of it is
one run of kittymusic:

| Time | What happened |
|---|---|
| 23:32 | The user asks for a death metal song. The machine composes `claws-of-the-abyss-deathmetal.score` and plays it |
| 23:34 | The user asks for a louder kick. The machine changes the score and plays it again |
| after 23:35 | The score changes with no action of the machine in between: the user edited it by hand, outside the machine. Three instruments are gone |
| 23:39 | `play` fails with `line 38: unknown instrument or variable: gtr` and more lines like it. The machine puts the instruments back |

- **The machine had composed that score, in that same run.** So "the program wrote it in
  this run" doesn't tell the two kinds of file apart: it was true of this one.
- **What does tell them apart:** the file was no longer what the machine had written.
- **The card's line fits the repair.** The machine had composed the score, and the card
  says such a score is fixed.

**Why a silent repair is the wrong default:**

- **It changes the user's work without being asked.** What looks like a mistake can be a
  half-finished edit.
- **The repair can be wrong,** and then the file holds something neither the user nor the
  program wrote on purpose. The machine took the instruments from what it remembered.
- **A real program doesn't do it.** A player that can't read a score says which line it
  stopped at.

## Build

**One rule in the prompt,** under PROGRAMS:

```text
- A program changes a file only when changing it is what the command is for: an editor, a
  redirect, sed -i, a program that saves. One that reads a file and finds a mistake in it
  prints what is wrong and where, as the real program would, and leaves the file as it
  is. A file it wrote itself in this run, and that is still as it wrote it, it may
  correct. One that has changed since, or that it can't be sure of, is the user's. When
  the user asks for the repair, make it.
```

- **"Still as it wrote it"** is the line between the two kinds of file. The machine has
  what it wrote in front of it for as long as the boot lasts, and it reads the file to find
  the mistake. A file that differs was changed by somebody else.
- **"In this run"** is from the program's start to its exit. A score from an earlier run,
  or from before a reboot, is the user's.
- **"Can't be sure"** goes to the user. A wrong report costs one more command. A wrong
  repair costs the user's work.
- **The error names the place,** so the user can fix it or ask for the fix. The music addon
  reports each problem with its line already.
- **Under PROGRAMS, not under THE DISK IS REAL.** Rules made with `hallux` override the
  prompt except for REPLY FORMAT and THE DISK IS REAL. Under PROGRAMS, a user who wants it
  the other way can say so: `hallux kittymusic may repair my scores`.

**`docs/concept.md`:** "The rules for all of them", under "Programs, Python and friends",
gets the rule, beside "Side effects are real". The prompt under "The system prompt" is the
first draft, kept for history. It stays as it is.

## What doesn't change

- **Programs that are for changing files.** An editor saves, `sed -i` edits, a formatter
  formats.
- **kittymusic's card.** This plan doesn't change it, but its line is wider than the new
  rule: "a score the machine composed itself is fixed and replayed" has no "still as it
  wrote it". A card describes its program, so the machine may go on following it. The user
  can tighten it:
  `hallux kittymusic fixes a score only when it composed it in this run and nobody changed it since; any other broken score it reports and leaves alone`.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| A file with a mistake | Report it, and leave the file alone | It is what a real program does, and it keeps the user's work the user's |
| Asking "repair it? y/n" | Not the default | A program that asks would stop every script. One that should ask can have it in its card |
| A file the program wrote in this run | It may correct it, as long as the file is still as it wrote it | A composer has to be able to fix its own draft. The score in the report was written in that run and then changed by hand, so "in this run" alone would have allowed the repair |
| A file the program can't be sure of | It is the user's | A wrong report costs a command, a wrong repair costs the user's work |
| Where the rule stands | PROGRAMS | So that a rule from `hallux` can change it for one program |

## Tests

In `tests/test_machine.py`:

- the prompt has the rule, under PROGRAMS.

No test can show what the AI does with it.

## Done when

The test passes, and the user has tried it in the test world, the way it happened. If the
card's line is to be tightened, do that first.

1. Start kittymusic and ask for a short song. It composes one and plays it.
2. Stop the song and stay in kittymusic. Outside the machine, open the score in your own
   editor (`home/<user>/Music/<song>.score` in the world's directory), take one
   `INSTRUMENT` block out and save. Keep a copy of the broken file beside it.
3. In kittymusic, play that song again.
4. Outside the machine, compare the score with the copy: `diff`.
5. In kittymusic, ask for the repair in words.

**Should happen:** in 3 the program says what is missing and on which lines, and plays
nothing. In 4 the two files are the same. In 5 the program repairs the score and says what
it changed.

**A second try,** cheaper: the same with a copy of a score, `cp song.score broken.score`,
edited in the machine's own editor. The program never wrote that file, so it reports and
leaves it alone.

**What it costs:** composing one song.
