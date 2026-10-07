# Step 14: keeping a screen

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 12

**Needs:** nothing of this plan for the kept screens. It changes `blockmode.py` and
`terminal.py`, as the config panel did, so it comes after the panel. **Changes:**
`hallux/blockmode.py`, `hallux/terminal.py`, `hallux/script.py`, `tests/test_blockmode.py`,
`tests/test_terminal.py`.

**It also carries two lines for the composer's prompt,** which need the code of step 13:
see [Carried with this step](#carried-with-this-step-two-lines-for-the-composers-prompt).
For those it changes `addons/music.py`, `tests/test_addon_music.py`,
`tests/test_music_manual.py` and `tests/test_agents.py`.

When a full-screen program is suspended today, Hallux throws its form away: the screen, and
whatever the user typed into its fields (`hallux/blockmode.py:381-384`). To come back, the
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
  (`hallux/terminal.py:101`).

**What is kept,** all of it by block mode:

- the screen as it is shown, row by row, with its footer;
- the form: its fields, its action keys, its keymap, whether it is raw, its tick;
- every field's text as the user left it, its cursor and what it has scrolled to;
- what the AI has seen of each field, and what counts as saved, so the next action still
  reports the right text and the right "modified";
- which field had the focus;
- **in a program with vi keys, the mode it was in:** normal or insert.

- **Why the vi mode has to be named.** A form that is put back is shown in a new app
  (`hallux/blockmode.py:256-262`), and a new app starts in insert mode. Tried on
  2026-10-05 with the real block mode: normal mode before, insert mode after. `:w` would
  then be typed into the text.
- **The fields are kept as the objects they are,** not copied out. Their undo history comes
  back with them.

**What comes back** is that, with no model call and no text from the AI.

- **After a window resize** the kept screen is fitted to the new size, the way a patch
  already refits the screen it is applied to (`hallux/blockmode.py:523-526`).
- **Keys typed during the switch** aren't lost: they go to the form that is on screen
  afterwards.
- **At most 8 are kept.** A ninth drops the oldest.
- **All are dropped** when block mode is told to forget everything, which step 15 does at
  the end of a boot.

The scripted terminal gets the four as empty methods: its `resume_form` returns false, and
its `suspended_forms()` returns nothing. The tests' fake terminal gets ones that work: it
keeps the names it is given, so the machine's tests of step 15 can see a screen come back.

## Carried with this step: two lines for the composer's prompt

This part has nothing to do with keeping a screen. The user's first live run of a
composition, on 2026-10-07, suggested two lines for the composer's prompt, and the user
asked to have them built with the next step of the plan, which is this one. What the run
showed, and why the lines are worded as they are, is in
[step 13's file](13-composer.md), under "Two lines for the composer's prompt".

**In `addons/music.py`,** the composer's role, the text `COMPOSER`:

| | What changes |
|---|---|
| A status line first | The point on `set_status` moves to the front and says: before anything else, call `set_status` with what you are about to write, in a few words; call it again whenever you start something new |
| The changes of a round in one turn | The point on `check` adds: make all the changes of a round in one turn, with several `edit_file` calls together, or with one `write_file` of the whole score when most of its lines change |

- **Nothing else of the composer's prompt changes,** and nothing of the manual: the main
  agent's text stays as it is, and so does its size.
- **Hallux's own rules for a worker stay as they are** (`hallux/agent.md`). They say "when
  you start something new"; the composer's role is where "before anything else" belongs,
  since another addon's agent may have nothing to say at its start.
- **Several edits of one file in one turn have to work.** Each of a job's tools runs to its
  end before the next one starts, and the job's disk has one lock (step 4), so two edits of
  different lines both take effect whatever their order. Two that touch the same text: the
  second finds its old text gone and says so, as any edit does. This is tested here, since
  until now a job's edits came one a turn.

**Its tests:**

- in `tests/test_music_manual.py`: the composer's role names `set_status` in its first
  point, with "before anything else", and says that the changes of a round are made in one
  turn; the manual is what it was, to the character;
- in `tests/test_agents.py`, with the fake Claude: two `edit_file` calls of one file that
  are under way together both take effect, and two that want the same text leave one
  change and one error;
- in `tests/test_addon_music.py`: the composition's test still passes, with its stand-in
  setting a status line first.

**What only a run shows:** whether a model at high effort sets the status line before it
thinks, and whether it makes its changes in one turn. Both are looked at in the next live
run of a composition, in the panel's Details tab: the first line should be a `status`
within seconds of the start, and the edits of a round should share one time.

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
And the composer's role has its two lines, with their tests.
