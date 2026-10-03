# Step 1: checking and saving a setting

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), sections 4, 5
and 7

**Needs:** nothing. **Changes:** `hallux/config.py`, `tests/test_config.py`.

Today `config.py` reads the file and checks all settings at once. The panel needs three more
things: to check one value, to turn what you typed into a value, and to write a change back
into the file without touching the rest of it. This step has no screen and no machine in it.

## Build

**`check(name, value)`** returns why a value can't be that setting's, or `None`.

- The rules and the words are the ones `_validate` has today: `must be a number, 0 or more`,
  `must be one of low, medium, high, xhigh, max, not 'turbo'`.
- `_validate` becomes a loop over the settings. It calls `check` for each and puts the
  file's path and the setting's name in front. What `load` says for a wrong file stays the
  same, word for word: the tests that exist match on those words.

**`typed(name, text)`** turns what you typed into a value, and raises `ValueError` with the
reason when it can't.

| Setting | What is typed | The value |
|---|---|---|
| `model` | A name | The text without spaces around it. Empty is refused |
| `fallback_model` | A name, or nothing | The text, or `None` |
| `effort` | One of the five | The text |
| `max_budget_usd` | A number, or nothing. A `$` in front is fine | A float, or `None`: no cap |
| `tick_budget_usd`, `event_budget_usd` | A number. A `$` in front is fine | A float |
| Every other setting | | Refused: `is set when Hallux starts: edit config.toml` |

- A number is digits with at most one point. Anything else is refused with the words of
  `check`, so `nan`, `inf` and `1e9` never get in.
- The value then goes through `check`.

**`WHEN`** says when a change of each setting takes effect: `"now"`, `"reboot"` or
`"start"`. The panel groups its rows by it (step 5).

| Setting | In this step | Later |
|---|---|---|
| `tick_budget_usd`, `event_budget_usd` | `now` | |
| `max_budget_usd` | `reboot` | `now` from step 3 |
| `model` | `reboot` | `now` from step 4, if its check passes |
| `effort`, `fallback_model` | `reboot` | |
| `status_bar`, `addons`, `keep_transcripts`, `os_sandbox` | `start` | |

The table is true at every step: it says what the code does then.

**`save(root, changes)`** writes the changed settings into `<root>/.hallux/config.toml`.
`changes` maps a setting's name to its new value; `None` takes the setting out of the file.
It raises `ValueError` with a message for the panel when it can't.

1. Read the file. No file is an empty one.
2. Check it as `load` does: valid TOML, no unknown setting, every value right. If it has an
   error by now, stop.
3. For each change, in the lines of the file:
   - a line that sets it is replaced by `name = value`, and a comment at its end is kept;
   - no such line: a new line at the end, after a line break if the file doesn't end in one;
   - `None`: the line is taken out.
4. Check the new text as in 2. Then compare: it has to parse to exactly the old settings
   with the changes applied. If it doesn't, stop.
5. Write the new text to a file beside it and rename that over `config.toml`. Create
   `.hallux` if it isn't there.

**How a value is written:**

| Value | Written as |
|---|---|
| A name | A TOML string, with `"` and `\` escaped: `"claude-opus-5-5"` |
| A number | As Python prints it: `1.25`, `2.0` |

**Finding the comment at the end of a line.** After the `=`, the old value is skipped: a
string up to its closing quote, anything else up to the first `#`. What follows stays. The
comparison in 4 catches a line this gets wrong.

**What can go wrong,** and what the panel is told:

| Case | Message |
|---|---|
| The file has an error by now | `config.toml: ` and the reason `load` gives, then `Nothing saved.` |
| The new text isn't the old settings plus the changes | `config.toml: can't change tick_budget_usd safely. Edit the file. Nothing saved.` |
| The file can't be written | `config.toml: ` and the system's reason, then `Nothing saved.` |

The second case covers a value that spans several lines, a setting that is in the file
twice, and a table header.

## Tests

In `tests/test_config.py`:

- `check` for each setting: a good value, and each wrong one with its words;
- `load` says what it said before for every wrong file in the list that exists;
- `typed`: `1.25`, `$1.25`, `0`, an empty budget per boot, an empty tick budget (refused),
  `-1`, `nan`, `1e9`, `abc`, an effort that doesn't exist, an empty model, a setting that
  only changes at the start;
- `save` replaces a line and keeps the comment at its end, also when the old value is a
  string with a `#` in it;
- `save` adds a line to a file that doesn't end in a line break, and to no file at all;
- `save` with `None` takes the line out, and does nothing when there is none;
- every other line is the same afterwards, byte for byte, comments and empty lines included;
- a setting that isn't in `changes` is never written, even when it differs from the default;
- a file that is broken by now, a value over several lines, a setting that is there twice:
  nothing is written, the file is as it was, and the message names the reason;
- what `save` wrote is read back by `load` as the new settings.

## Done when

`save` changes one line of the README's example file, the comments are all still there, and
`load` reads the new value.
