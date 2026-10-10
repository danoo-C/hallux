# Step 15: job control

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), sections 7,
12 and 13

**Needs:** steps 10 and 14. **Changes:** `hallux/protocol.py`, `hallux/machine.py`,
`hallux/blockmode.py`, `hallux/tools.py`, `hallux/prompt.md`, `hallux/prompt_jobs.md`,
`tests/test_protocol.py`, `tests/test_machine.py`, `tests/test_blockmode.py`,
`tests/test_tools.py`.

Ctrl-Z, `fg`, `bg` and `jobs` for full-screen programs. The words stay bash's, and bash is
the AI. What changes is that Hallux keeps a suspended program's screen (step 14), so `fg`
brings it back without the AI writing it again.

## Build

**Three tags** the AI adds after `</prompt>`:

| Tag | Hallux |
|---|---|
| `<suspend job="1"/>` | Keeps the form on screen under that number, leaves block mode, and prints the AI's screen: `[1]+  Stopped                 kittymusic` |
| `<resume job="1"/>` | Puts that form back. The screen in the same answer isn't shown, see below |
| `<forget job="1"/>` | Drops it: the program ended, or was killed |

- **The job number is the AI's.** Hallux only keeps screens under the number it is given.
  It has to be digits; anything else is ignored, with a line in the log.
- **A reply with `<suspend>` and no full-screen program on screen** keeps nothing, with a
  line in the log.
- **A screen that came with `<resume>` may be on the terminal already.** The real terminal
  shows a screen while it is written (`hallux/terminal.py:87`,
  `hallux/machine.py:844-854`), and the tag comes after `</prompt>`, at the very end. What
  was shown is taken back, the way a full-screen program's screen that streamed is taken
  back today (`hallux/machine.py:725-728`).

**After `<resume>`:**

| The kept screen | What happens |
|---|---|
| Is there, and the program has a tick that may run | It is shown, and the program gets a tick at once, so it can patch what changed while it was away |
| Is there, and its ticks are paused or the boot is over its budget | It is shown without a tick, and the bar says why. No message goes to the AI |
| Is there, no tick | It is shown. No message goes to the AI |
| Is gone | Hallux tells the AI at once, in a message of its own, and the AI draws the program again |

- **What the machine restores with the form:** the fields it knows on screen, what the
  program had spent on ticks, and the tick the program asked for. Leaving a program forgets
  all three today (`hallux/machine.py:753-757`), so the machine puts them aside with the
  job's number at the suspend.
- **Whether its ticks run is decided as for a new screen** (`hallux/machine.py:600-606`):
  not when the tick budget is used up, which the restored count can say, and not while the
  boot is over its budget. A tick that is due then isn't sent, as since the fixes of
  Hallux's report (`hallux/machine.py:631`). Every message of the resumed program carries
  `ticks="paused"` while that holds, without anything new.
- **The message for a screen that is gone** is `<gone job="1" …></gone>`: it goes through
  the machine's envelope like every message, so it has the cwd, the time and the size too
  (`hallux/machine.py:759-764`). The prompt shows it that way.
- **A program in the background gets no ticks,** so it costs nothing.

**Ctrl-Z always reaches the AI in a full-screen program,** like Ctrl-C. In raw mode it does
already. In a form with fields it is an action key from now on, whether the form lists it
or not (`hallux/blockmode.py:659`).

**`list_processes` on every machine.** It returns `{"jobs": [...], "screens": ["1", "2"]}`:
the rows of the real jobs, and the numbers of the kept screens, from the terminal's
`suspended_forms()` (step 14). On a machine without an agent addon `jobs` is empty.
`kill_process` stays where it was: only where an addon has an agent.

**The end of a boot** drops every kept screen, where it leaves a program that is still on
screen (`hallux/machine.py:356-360`).

**The prompt:**

| File | Gets |
|---|---|
| `hallux/prompt.md`, REPLY FORMAT | The three tags, beside `<halt/>` and `<reboot/>` (`hallux/prompt.md:22-31`). They are part of the wire, and REPLY FORMAT is what no rule changes |
| `hallux/prompt.md`, KEYS | The line on C-z (`hallux/prompt.md:64`) says that a full-screen program is suspended with `<suspend>`, that `fg` answers with `<resume>` and no screen, and that a program in the background gets no ticks |
| `hallux/prompt.md`, BLOCK MODE | "C-c always comes to you" (`hallux/prompt.md:141`) becomes C-c and C-z |
| `hallux/prompt.md`, INPUT | `<gone>`, as it arrives; that `jobs` reads `list_processes` first, so it never lists a program whose screen is gone |
| `hallux/prompt_jobs.md`, with an agent addon | That a `Done` line has two sources: a real job's event, or the AI's own decision for a program in the background. It belongs to the section's second group, "how it shows" (step 10) |

## Tests

In `tests/test_protocol.py`:

- each tag is read with its number, after `</prompt>` and beside the other tags;
- a tag inside `<screen>` is text, not a tag;
- a job that isn't digits is ignored.

In `tests/test_machine.py`, with the fake model and the fake terminal, which keeps the
names it is given (step 14):

- Ctrl-Z in a program, the AI answers with `<suspend job="1"/>`: the form is kept, the
  `Stopped` line is printed, and the prompt is the shell's;
- `fg`, the AI answers with `<resume job="1"/>`: the form is back, and nothing was printed;
- the same on a terminal that shows screens while they are written, with a screen in the
  answer: what was shown is taken back. The tests' terminal doesn't stream by default
  (`tests/test_machine.py:170`), so this test turns it on;
- a resumed program with a tick gets a tick at once; one without gets nothing;
- a program that was suspended with its tick budget used up: after the resume no tick is
  sent, the bar says that live updates are paused, and its next key carries
  `ticks="paused"`;
- a program resumed while the boot is over its budget gets no tick;
- `<resume>` of a screen that is gone: the AI gets `<gone job="1" …>`, and its answer is
  shown;
- `<forget>` drops the screen;
- `<suspend>` at the shell prompt keeps nothing, and the log says so;
- `reboot` with a kept screen: it is gone in the next boot;
- what a program spent on ticks, and the tick it asked for, are the same after a resume;
- the words of the prompt: REPLY FORMAT has the three tags, and the two changed lines say
  C-z.

In `tests/test_blockmode.py`:

- Ctrl-Z in a form with fields that doesn't list it is sent as an action, with the fields.

In `tests/test_tools.py`. Two tests there count the tools, 13 and 14
(`tests/test_tools.py:34,93`), and become 14 and 15.

- `list_processes` is there on a machine without addons, with an empty `jobs` and the kept
  screens' numbers;
- `kill_process` isn't there without an agent addon.

## Before the user tries it

A check on a pseudo-terminal, with a terminal emulator drawing the screen, as for the
panel's steps 6 and 7: text typed into an editor, Ctrl-Z, a line at the shell, `fg`. After
the suspend the shell's screen and the pinned bar are back, with the `Stopped` line. After
the resume the editor's screen is as it was, row by row.

## Done when

The tests pass, the check on the pseudo-terminal holds, and the user has tried it by hand:
text typed into nano, Ctrl-Z, a command at the shell, `fg`, and the text is there, within
the time of one short answer.

## As built

Built on 2026-10-10, on the branch `addon-agents`. 35 new tests, 1578 in all. The user's
try by hand, the last part of "Done when", is open. Decided while building:

**The tags**

- **A job is a whole number of at most nine digits.** `job="007"` is job 7, since the
  terminal keeps a screen under a number (step 14). Anything else is ignored, and the log
  has `ignored <suspend job="%1"/>: a job is a number`.
- **The tags are read after `</screen>`, and not inside a `<file>`.** A file whose text
  holds a tag is written as it is.
- **In the older order, with the form after the prompt, the tags may stand between the
  two.** Without that the form wasn't read, and a field's text was searched for tags.
- **One answer can hold several `<forget>`,** and one `<suspend>` and one `<resume>`: the
  first of each counts.
- **Their order in one answer is forget, suspend, resume.** So
  `<suspend job="2"/><resume job="1"/>` puts the program on screen aside and brings
  another back, in one answer.

**Suspend and resume**

- **The machine keeps three things beside the terminal's screen,** in `Machine.suspended`,
  by job number: the fields, what the program spent on ticks, the tick it asked for. After
  every suspend it drops what the terminal doesn't keep: the ninth screen, and in a
  scripted run all of them.
- **Nothing of an answer with `<resume>` is shown,** and its prompt isn't taken. That
  holds also when the screen is gone.
- **A `<resume>` with a program on screen and no `<suspend>` ends that program.** The
  resumed one takes its place, and nothing of the other stays: not its tick, and not its
  note on the bar. Step 14 left this to this step.
- **A `<suspend>` in an answer that shows a form** keeps the old program, and the new one
  starts anew: a field of the same name is a new field.
- **The first tick of a program that came back is sent by the machine,** without a wait
  on the terminal. Keys typed while it is answered are kept by block mode, as after any
  action.
- **`block_mode` is three parts now:** showing a form, deciding its tick (`tick_for`), and
  attending the program on screen (`attend`). A resume uses the last two.

**A screen that is gone**

- **A `<resume>` in the answer to `<gone>` isn't followed.** A model that insists would be
  called in a loop, a message each time. The log says so, and the user is at the shell
  with the prompt it had.
- **Over the boot's budget `<gone>` isn't sent.** The bar says that the budget is used,
  and the user is at the shell. After the cap is raised, `fg` leads to `<gone>` as usual.
- **In a scripted run every `fg` leads to `<gone>`,** since a transcript keeps no screen.
  The AI draws the program again, and the transcript has it under `fg`.

**`list_processes`**

- **`screens` holds numbers, `[1, 2]`,** not the strings of this file's example. The
  terminal keeps them as numbers since step 14.
- **It stands with the base tools, after `memory_edit`.** `kill_process` is still the last
  of Hallux's own tools, and only on a machine with an agent addon.
- **The terminal is asked at each call,** through `build_tools(..., screens=…)`.

**The budgets**

- **Refill budgets counts for a program that is put aside too:** what it had spent on
  ticks starts at zero. Otherwise the button would lift the pause of the program on screen
  and not of one in the background.

**The prompt** grew by about 1,200 characters, and the section on jobs by about 230.

| Where | What it says now |
|---|---|
| REPLY FORMAT | A point of its own after `<halt/>`: the three tags, that the terminal keeps the screen, that a screen written with `<resume>` isn't shown, and that the job number is the AI's |
| INPUT | `<gone job="1"></gone>`, and that `jobs` calls `list_processes` first |
| KEYS | Three lines under the one on C-z: `<suspend>`, `fg` with `<resume>` and no screen, no ticks in the background |
| BLOCK MODE | "C-c and C-z always come to you" |
| The section on jobs | One more point under "How it shows": the two sources of a `Done` line |

The main prompt names `list_processes` now. A test said that it doesn't; it holds
`kill_process` to that instead.

**Old tests that changed:** eight that pin the list of tools, in `tests/test_tools.py`,
`tests/test_addons.py`, `tests/test_agents.py`, `tests/test_addon_music.py` and
`tests/test_machine.py`. Two of them were about "the two tools"; they are about
`kill_process` now. One more file than the list at the top got tests:
`tests/test_script.py`.

**How I checked the tests themselves:** 33 wrong versions, one at a time, among them a
form that isn't kept, fields, spending or a tick that don't come back, no tick at once, a
tick at once while ticks are paused, a screen with `<resume>` that is shown, a `<gone>`
that isn't sent, one that goes out over the cap, a `<resume>` after `<gone>` that is
followed, a boot's end that keeps the screens, and Ctrl-Z only where a form lists it. 32
failed a test at once. One didn't: a suspend that leaves the machine's own state as it
was, which shows only when the same answer brings a new form. A test for that is added,
and the version fails it.

**The check on a pseudo-terminal:** the real machine and the real terminal with its bar,
24 rows by 80 columns, the bytes replayed through a terminal emulator. The model is a
pretend one that answers as a bash with job control would. Its nano doesn't list Ctrl-Z.

| Moment | What the screen showed |
|---|---|
| The editor, with `unsaved ` typed and the cursor a line down | The title, the two lines, the footer on row 23 and the bar on row 24 |
| After Ctrl-Z | The shell's screen from before the editor, an empty line, `[1]+  Stopped                 nano notes.txt`, the prompt, and the bar on row 24 only |
| After `ls`, thirty lines written piece by piece | The lines scrolled in order above the prompt, and the bar on row 24 only |
| After `fg`, whose answer wrote `nano notes.txt` into its screen | Every row of the editor as it was, and the cursor on row 3, column 9, where it had been |
| `more ` typed, then Ctrl-O | The text went in at the cursor: `line twomore`. At the shell the line under `fg` is the editor's last word: nothing of the answer's screen is left |
| The same, with what streamed not taken back | `nano notes.txt` stays under `fg`. So the check can fail |
| The same, with a terminal that keeps no screen | `<gone>` goes out, and the editor is drawn again as new, without the typed text. The check fails there, as it should |
| `top` with a tick of 30 seconds, Ctrl-Z, `fg` | Its screen was back and patched by a tick 0.2 seconds after `fg` |

**What I couldn't check**

- **What a real model does with the new lines of the prompt:** whether Ctrl-Z in nano gets
  `<suspend>` and a `Stopped` line, whether `fg` gets `<resume>` with an empty screen,
  whether `jobs` reads `list_processes`, and whether `kill %1` gets `<forget>`. No test
  calls a model, and no paid run was made for this step.
- **A real terminal:** the emulator shows where text lands, not how the switch looks.
- **The try by hand,** which is the user's: text typed into nano, Ctrl-Z, a command at the
  shell, `fg`, and the text is there, within the time of one short answer.
