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
- **The machine repaired the file.** It put three instruments back into a score the user
  had edited by hand. It had to take them from what it remembered of the score.
- **kittymusic's card has half of an answer:** "a score the machine composed itself is
  fixed and replayed". That covers the program's own work. It doesn't cover a file the user
  changed.

**Why a silent repair is the wrong default:**

- **It changes the user's work without being asked.** What looks like a mistake can be a
  half-finished edit.
- **The repair can be wrong,** and then the file holds something neither the user nor the
  program wrote on purpose.
- **A real program doesn't do it.** A player that can't read a score says which line it
  stopped at.

## Build

**One rule in the prompt,** under PROGRAMS:

```text
- A program changes a file only when changing it is what the command is for: an editor, a
  redirect, sed -i, a program that saves. One that reads a file and finds a mistake in it
  prints what is wrong and where, as the real program would, and leaves the file as it
  is. What a program wrote itself during this run it may correct. When the user asks for
  the repair, make it.
```

- **"During this run"** is the line between the two kinds of file. A score the program
  composed a moment ago is its draft. The same score after the user opened it in an editor,
  or after a reboot, is the user's.
- **The error names the place,** so the user can fix it or ask for the fix. The music addon
  reports each problem with its line already.
- **Under PROGRAMS, not under THE DISK IS REAL.** Rules made with `hallux` override the
  prompt except for REPLY FORMAT and THE DISK IS REAL. Under PROGRAMS, a user who wants it
  the other way can say so: `hallux kittymusic may repair my scores`.

**`docs/concept.md`:** the copy of PROGRAMS under "The system prompt" gets the rule.

## What doesn't change

- **Programs that are for changing files.** An editor saves, `sed -i` edits, a formatter
  formats.
- **kittymusic's card.** Its line about scores it composed itself agrees with the rule.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| A file with a mistake | Report it, and leave the file alone | It is what a real program does, and it keeps the user's work the user's |
| Asking "repair it? y/n" | Not the default | A program that asks would stop every script. One that should ask can have it in its card |
| A file the program wrote in this run | It may correct it | A composer has to be able to fix its own draft before it plays it |
| Where the rule stands | PROGRAMS | So that a rule from `hallux` can change it for one program |

## Tests

In `tests/test_machine.py`:

- the prompt has the rule, under PROGRAMS.

No test can show what the AI does with it.

## Done when

The test passes, and the user has tried it in the test world:

1. Copy a score that plays: `cp song.score broken.score`. Keep a second copy to compare.
2. Open `broken.score` in an editor and take one instrument out.
3. Ask the program to play it.
4. Compare the file with the second copy of the broken one: `diff`.
5. Ask for the repair in words.

**Should happen:** in 3 the program says what is missing and on which line, and plays
nothing. In 4 the file is as the user left it. In 5 the program repairs it and says what it
changed.
