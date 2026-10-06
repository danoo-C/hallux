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
  `hallux/machine.py:830-840`), and the tag comes after `</prompt>`, at the very end. What
  was shown is taken back, the way a full-screen program's screen that streamed is taken
  back today (`hallux/machine.py:711-714`).

**After `<resume>`:**

| The kept screen | What happens |
|---|---|
| Is there, and the program has a tick that may run | It is shown, and the program gets a tick at once, so it can patch what changed while it was away |
| Is there, and its ticks are paused or the boot is over its budget | It is shown without a tick, and the bar says why. No message goes to the AI |
| Is there, no tick | It is shown. No message goes to the AI |
| Is gone | Hallux tells the AI at once, in a message of its own, and the AI draws the program again |

- **What the machine restores with the form:** the fields it knows on screen, what the
  program had spent on ticks, and the tick the program asked for. Leaving a program forgets
  all three today (`hallux/machine.py:739-743`), so the machine puts them aside with the
  job's number at the suspend.
- **Whether its ticks run is decided as for a new screen** (`hallux/machine.py:586-592`):
  not when the tick budget is used up, which the restored count can say, and not while the
  boot is over its budget. A tick that is due then isn't sent, as since the fixes of
  Hallux's report (`hallux/machine.py:617`). Every message of the resumed program carries
  `ticks="paused"` while that holds, without anything new.
- **The message for a screen that is gone** is `<gone job="1" …></gone>`: it goes through
  the machine's envelope like every message, so it has the cwd, the time and the size too
  (`hallux/machine.py:745-750`). The prompt shows it that way.
- **A program in the background gets no ticks,** so it costs nothing.

**Ctrl-Z always reaches the AI in a full-screen program,** like Ctrl-C. In raw mode it does
already. In a form with fields it is an action key from now on, whether the form lists it
or not (`hallux/blockmode.py:597`).

**`list_processes` on every machine.** It returns `{"jobs": [...], "screens": ["1", "2"]}`:
the rows of the real jobs, and the numbers of the kept screens, from the terminal's
`suspended_forms()` (step 14). On a machine without an agent addon `jobs` is empty.
`kill_process` stays where it was: only where an addon has an agent.

**The end of a boot** drops every kept screen, where it leaves a program that is still on
screen (`hallux/machine.py:342-346`).

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
