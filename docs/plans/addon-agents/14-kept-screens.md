# Step 14: keeping a screen

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 12

**Needs:** nothing of this plan. It changes `blockmode.py` and `terminal.py`, as the config
panel did, so it comes after the panel. **Changes:** `hallux/blockmode.py`,
`hallux/terminal.py`, `hallux/script.py`, `tests/test_blockmode.py`,
`tests/test_terminal.py`.

When a full-screen program is suspended today, Hallux throws its form away: the screen, and
whatever the user typed into its fields (`hallux/blockmode.py:360-363`). To come back, the
AI has to write the whole screen again, and unsaved text in an editor is lost. This step
lets the terminal put a form aside and put it back, exactly as it was. Nothing calls it yet:
that is step 15. It needs nothing of the agents.

## Build

**Four new things on the terminal:**

| | What it does |
|---|---|
| `suspend_form(job)` | Keeps the form on screen under that name, then leaves block mode as `end_form` does |
| `resume_form(job)` | Puts that form back and returns true. Without one of that name: false, and nothing happens |
| `forget_form(job)` | Drops it |
| `suspended_forms()` | The names, for `list_processes` (step 15) |

- **Why not `kept_forms()`.** Two things of the terminal are called "kept" since the
  panel, and neither is this: `keep_form()` lets a program go on without an answer, and
  `Terminal.kept` is the text that is held back while the panel is open
  (`hallux/terminal.py:100`).

**What is kept,** all of it by block mode:

- the screen as it is shown, row by row, with its footer;
- the form: its fields, its action keys, its keymap, whether it is raw, its tick;
- every field's text as the user left it, its cursor and what it has scrolled to;
- what the AI has seen of each field, and what counts as saved, so the next action still
  reports the right text and the right "modified";
- which field had the focus;
- **in a program with vi keys, the mode it was in:** normal or insert.

- **Why the vi mode has to be named.** A form that is put back is shown in a new app
  (`hallux/blockmode.py:255-261`), and a new app starts in insert mode. Tried on
  2026-10-05 with the real block mode: normal mode before, insert mode after. `:w` would
  then be typed into the text.
- **The fields are kept as the objects they are,** not copied out. Their undo history comes
  back with them.

**What comes back** is that, with no model call and no text from the AI.

- **After a window resize** the kept screen is fitted to the new size, the way a patch
  already refits the screen it is applied to (`hallux/blockmode.py:499-502`).
- **Keys typed during the switch** aren't lost: they go to the form that is on screen
  afterwards.
- **At most 8 are kept.** A ninth drops the oldest.
- **All are dropped** when block mode is told to forget everything, which step 15 does at
  the end of a boot.

The scripted terminal gets the four as empty methods: its `resume_form` returns false, and
its `suspended_forms()` returns nothing. The tests' fake terminal gets ones that work: it
keeps the names it is given, so the machine's tests of step 15 can see a screen come back.

## Tests

In `tests/test_blockmode.py`, with the real block mode on a pipe:

- an editor with typed text is suspended and resumed: the text, the cursor and the focus
  are the same, and the next action reports the text as changed since the AI saw it;
- a file was saved before the suspend: after the resume the field isn't "modified";
- a vi program in normal mode: after the resume it is in normal mode, and `x` deletes a
  character where it would otherwise type one;
- text typed before the suspend can be undone after the resume;
- a raw-mode program with a tick: after the resume the tick runs again;
- two programs suspended under two names come back each as itself;
- `resume_form` of a name that isn't kept returns false, and block mode isn't started;
- `forget_form`: the name is gone;
- nine suspends: the first is gone, the other eight are kept;
- the window is smaller at the resume: the screen is fitted, and the footer is still at the
  bottom;
- keys typed right after the suspend go to the shell prompt, and keys typed right after the
  resume go into the form;
- the panel opens over a resumed program as over any other.

In `tests/test_terminal.py`, with the bar pinned by hand, since a terminal on a pipe pins
none:

- after `suspend_form` the bar is pinned again, as after `end_form`;
- `resume_form` gives the program the whole screen again, as `show_form` does.

## Done when

On a pipe, text is typed into an editor field, the form is suspended, something is typed at
the shell prompt, the form is resumed, and the field holds exactly the text from before.
