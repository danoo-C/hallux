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
  shows a screen while it is written (`hallux/terminal.py:75`,
  `hallux/machine.py:491-501`), and the tag comes after `</prompt>`, at the very end. What
  was shown is taken back, the way a full-screen program's screen that streamed is taken
  back today (`hallux/machine.py:398-401`).

**After `<resume>`:**

| The kept screen | What happens |
|---|---|
| Is there, and the program has a tick | It is shown, and the program gets a tick at once, so it can patch what changed while it was away |
| Is there, no tick | It is shown. No message goes to the AI |
| Is gone | Hallux tells the AI at once, with `<gone job="1"/>` as a message of its own, and the AI draws the program again |

- **What the machine restores with the form:** the fields it knows on screen, and what the
  program had spent on ticks.
- **A program in the background gets no ticks,** so it costs nothing.

**Ctrl-Z always reaches the AI in a full-screen program,** like Ctrl-C. In raw mode it does
already. In a form with fields it is an action key from now on, whether the form lists it
or not (`hallux/blockmode.py:477`).

**`list_processes` on every machine.** It returns `{"jobs": [...], "screens": ["1", "2"]}`:
the rows of the real jobs, and the numbers of the kept screens. On a machine without an
agent addon `jobs` is empty. `kill_process` stays where it was: only where an addon has an
agent.

**The end of a boot** drops every kept screen.

**The prompt:**

| File | Gets |
|---|---|
| `hallux/prompt.md`, for every machine | The three tags; that `fg` answers with `<resume>` and no screen; `<gone>`; that `jobs` reads `list_processes` first, so it never lists a program whose screen is gone; that a program in the background gets no ticks |
| `hallux/prompt_jobs.md`, with an agent addon | That a `Done` line has two sources: a real job's event, or the AI's own decision for a program in the background |

## Tests

In `tests/test_protocol.py`:

- each tag is read with its number, after `</prompt>` and beside the other tags;
- a tag inside `<screen>` is text, not a tag;
- a job that isn't digits is ignored.

In `tests/test_machine.py`, with the fake model and the fake terminal:

- Ctrl-Z in a program, the AI answers with `<suspend job="1"/>`: the form is kept, the
  `Stopped` line is printed, and the prompt is the shell's;
- `fg`, the AI answers with `<resume job="1"/>`: the form is back, and nothing was printed;
- the same on a terminal that shows screens while they are written, with a screen in the
  answer: what was shown is taken back. The tests' terminal doesn't stream by default
  (`tests/test_machine.py:139`), so this test turns it on;
- a resumed program with a tick gets a tick at once; one without gets nothing;
- `<resume>` of a screen that is gone: the AI gets `<gone job="1"/>`, and its answer is
  shown;
- `<forget>` drops the screen;
- `<suspend>` at the shell prompt keeps nothing, and the log says so;
- `reboot` with a kept screen: it is gone in the next boot;
- what a program spent on ticks is the same after a resume.

In `tests/test_blockmode.py`:

- Ctrl-Z in a form with fields that doesn't list it is sent as an action, with the fields.

In `tests/test_tools.py`. Two tests there count the tools, 13 and 14
(`tests/test_tools.py:34,93`), and become 14 and 15.

- `list_processes` is there on a machine without addons, with an empty `jobs` and the kept
  screens' numbers;
- `kill_process` isn't there without an agent addon.

## Done when

The tests pass, and the user has tried it by hand: text typed into nano, Ctrl-Z, a command
at the shell, `fg`, and the text is there, within the time of one short answer.
