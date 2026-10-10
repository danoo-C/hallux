# Step 5: the Files tab

[The plan](README.md) · the panel's design: [config-panel.md](../../config-panel.md),
section 4

**Needs:** step 4. **Makes:** `hallux/panel_tabs/files.py`, `tests/test_panel_files.py`.
**Changes:** `hallux/panel.py`, `hallux/app.py`, `tests/test_panel.py`.

The tab, the rule by which a drop finds it, and its place in the panel's row. From this
step on the user can import.

## Build: the host

**A tab can take a paste.** `Tab` (`hallux/panel.py:31`) gets one more thing the host asks:

```python
def paste(self, text: str) -> bool:
    """Something was pasted while no row is open for typing. True if the tab takes it."""
    return False
```

**The host's key.** In `Panel._bindings` (`hallux/panel.py:215`), `Keys.BracketedPaste` is
bound with the filter the tabs' letters have: not while a tab is typing. It offers the text
to the shown tab first, then to the others in the order of the row. The first that takes it
is shown, if it isn't already. If none takes it, nothing happens, as today.

- **While a row is open for typing** the host's key is off, and the paste is the row's: the
  Config tab binds it for its open row already (`hallux/panel_tabs/config.py:336`).
- **A tab that is disabled** isn't offered the paste.
- **One line in the log** for every paste the host offers: how long the text is, and which
  tab took it, or that none did. Not the text. It is what tells, at the user's first try,
  whether a drop reached the panel at all.
- **Only the host binds the key.** The host's keys come after the tab's in the merged
  bindings, and of two bindings for the same key prompt_toolkit calls the later one
  (checked), so a binding of the tab's own would never be called.

This works in all three places the panel opens. At the shell and while the AI works the
panel is an app of its own. Over a full-screen program the app's keys are the panel's while
the layer is up (`hallux/blockmode.py:277`), so block mode's own paste key, which sends a
paste to the AI (`hallux/blockmode.py:631`), is off.

## Build: the tab

**`FilesTab(watch, drop, reads, start, stop, clear)`** in `hallux/panel_tabs/files.py`. It is
given the six functions of step 4 and knows nothing of the machine, as the Config tab is
given four.

**It draws from one function,** `draw(seen, width) -> Drawn`, with a head of two lines that
stay and a body that scrolls, as the Details tab does (`hallux/panel_tabs/details.py:41`).
That function is tested without a pipe.

| State | Head | Body |
|---|---|---|
| `empty` | `Drop files or folders onto this window.` and `They are copied into ` with the shell's directory | Empty |
| `looking` | `into ` and the destination; the counts so far, and `counting…` | The sources' names |
| `ready` | `into ` and the destination; `2 folders · 14 files · 2.3 MB`, and `· 1 exists already`, `· 2 can't be copied` when there are any | The tree |
| `ready`, refused | `into ` and the destination; the reason, in red | Empty |
| `copying` | `into ` and the destination; `copying… 120 of 1,400 files · 34 MB of 2.1 GB` | The tree |
| `done` | `copied 14 files (2.3 MB) into ` and the destination, or `stopped:` and how far it came; the second line counts what was skipped | What wasn't copied, each with its reason. `everything was copied`, when that is so |

**A line of the tree:** two spaces for each depth, the name, a `/` after a folder. On the
right, in columns: a folder's number of files, the size, the mark. A name that is too long
is cut with `cut` (`hallux/panel_tabs/agents.py:79`). A name is shown clean: a character
that isn't printable is drawn as `?`. `exists` is yellow, the marks that skip are grey, and
`… N more` is grey.

**The keys:**

| Key | When | What it does |
|---|---|---|
| ↑ ↓, PgUp, PgDn, the wheel | Always | Scroll the body, as in the Details tab. The view starts at the top |
| Enter | `ready`, and something would be copied | With no `exists`: `start(None)`. Otherwise it asks |
| `o`, `s` | The question is asked | `start(True)`, `start(False)` |
| `x` | `looking`, `ready`, `done` | `clear()` |
| `s` | `copying` | `stop()` |

**The path row,** for a terminal that types the drop. VS Code's terminal does: the path
arrives as keys, without paste brackets (the plan's README, "What a drop is"). Windows
Terminal doesn't need the row: it sends a paste, which goes the host's way.

- **What opens it:** `p`, or one of `'`, `"`, `/` and `\`, which is then the row's first
  character. Every path a terminal sends starts with one of those four, except a bare
  `C:\…`. Not while a copy runs, and not while the question is asked.
- **Where it is:** one line under the head, `path: ` and what was typed.
- **While it is open the tab counts as typing.** Every printable key is text for the row,
  so no letter chooses a tab or does anything else. Backspace deletes. The row's keys are
  bound one by one, as the Config tab binds its open row
  (`hallux/panel_tabs/config.py:336`).
- **A drop needs no Enter.** When no key has come for 0.3 seconds and the text `reads` as a
  drop, it is given to `drop` and the row closes. A second drop after that opens the row
  again with its own first quote.
- **Enter** gives the text to `drop` whatever it is. A refusal goes into the foot, and the
  row stays open with its text.
- **Esc** closes the row.
- **A paste in brackets never opens the row.** It goes the host's way, above. Pasted into
  the open row, it is typed into it.

**The question** is the tab's own hint, as the kill question is in the two job tabs
(`hallux/panel_tabs/agents.py:132`): `3 files exist already: o overwrite · s skip · Esc back`.
While it is asked the tab counts as typing, so the host takes no letter. Esc and any other
key drop it. `Asking` itself isn't used: it asks about a pid.

**What the host asks of the tab:**

| | |
|---|---|
| `title` | `Files` |
| `hint()` | The keys that do something in the state it is in |
| `paste(text)` | A text that `reads` as a drop is given to `drop`, and the tab takes it. A text that doesn't is taken only while the tab is the shown one. What `drop` or `NotADrop` says goes into the foot with `host` (see below) |
| `wants_first()` | While a copy runs, and while a result hasn't been shown yet |
| `leave()` | True if the question was asked |
| `shown()` | The view goes to the top; the result counts as shown |
| `disabled()` | Never |

**Which tab the panel opens on** stays the host's rule: the first in the row that wants to
be first. Agents comes before Files, so while a job runs the panel opens on Agents, as
today.

**A word in the foot.** A tab can't put a message into the foot today: `Panel._say`
(`hallux/panel.py:168`) is the host's own. It becomes `Panel.say`, which a tab may call. The
message fades after four seconds, which is right for "no such file or folder".

**In `hallux/app.py`** (line 87): the row is `Panel([*watching, files, settings], …)`, with
`files = FilesTab(machine.imports.watch, …)`. Config stays last.

## Tests

`tests/test_panel.py`, the host:

- A paste goes to the shown tab first; a tab that takes it is shown; a disabled tab isn't
  asked; with no taker the shown tab stays and nothing is said.
- While a tab is typing, the host doesn't offer the paste.
- The letters in a pasted text choose no tab.

`tests/test_panel_files.py`, with a real `Imports` on a temporary machine:

- `draw` for each state, without a pipe: the two head lines, the tree's lines with their
  depths, columns and marks, `… N more`, a name with a control character.
- On a pipe: a paste of a real folder's path, in the Files tab and in the Config tab. Both
  times the tree is drawn and Files is the shown tab.
- A paste of `hello` in the Files tab: the foot says `no such file or folder…`. In the
  Config tab: nothing.
- A paste into the Config tab's open Model row is typed into the row, and Files isn't
  shown.
- Enter with nothing in the way copies: the files are in the temporary machine, and the
  head says `copied`.
- Enter with one `exists`: the question; `o` replaces, `s` skips, Esc drops the question
  and nothing is copied.
- `x` clears. Enter in `empty` does nothing.
- The path row: a real folder's path in single quotes, sent key by key, and then nothing
  for half a second: the tree is drawn and the row is closed. The letters `a d f c k y x s
  o` in that path chose no tab and did nothing.
- The path row with a path that doesn't exist: after the pause the row is still open. Enter
  puts the reason into the foot, and Esc closes the row with the panel still open.
- `p` opens the row empty. While a copy runs, `p` and `/` open nothing.
- A tree of 100 lines in a window of 24 rows: ↓ and PgDn scroll, the head and the foot
  stay.
- `wants_first`: while a slow copy runs, and after it until the tab was shown once.
- The tab row has four tabs and fits a window of 60 columns.

## Before the user tries it

The drawn screen is checked as the memory of this project says: the real `Machine`,
`Terminal` and `Panel` with a pretend model, in tmux. A paste stands in for the drop:
`tmux set-buffer` with a path, then `paste-buffer -p`, which sends it in paste brackets.

- The panel at the prompt, while the AI works, and over a full-screen program: each time
  the tree appears, Enter copies, and after Esc there is one whole bar on the bottom row.
- A path pasted at the shell prompt lands on the line as text, as before.
- A typed drop: `tmux send-keys -l` with a quoted path, in the Files tab. The tree appears
  without Enter.
- A window of 60 × 16.

## Done when

The tests pass, the check in tmux shows the tree in all three places, and the files are on
the temporary machine's disk afterwards.
