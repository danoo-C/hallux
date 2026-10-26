# Step 1: the colors, and when they are on

[The colors plan](README.md) · [the hpm plan](../README.md)

**Changes:** `hallux/hpm/paint.py` (new), `tests/test_hpm_paint.py` (new).

## What to build

A small module with no other hpm imports, so `publish.py`, `cli.py` and the rest can all
use it.

```python
KINDS = ("ok", "fail", "skip", "error", "warning", "note", "loud", "ai", "ask", "plain")

def enabled(stream, env=os.environ) -> bool:
    """Colors for this stream: HPM_COLOR=always|never first; else off with NO_COLOR (not
    empty) or TERM=dumb; else on if the stream is a terminal."""

def kind_of(line: str) -> str:
    """The kind a line's first characters say (README, "What hpm prints today"):
    "✓" or "published " → ok, "✗" → fail, "–" → skip, "!!" → loud, "warning:" → warning,
    "note:" → note, "the AI " → ai, a line that ends in "cost ~$…" → ai; else plain.
    Leading spaces don't count ("  ✓ kittystory 1.1 updated")."""

def paint(text: str, kind: str | None = None, on: bool = True) -> str:
    """The text with its colors (README, "The colors"): the marker in its bold color, the
    rest in the kind's color. `kind` None: kind_of the first line. With `on` False, or
    kind "plain", the text as it is. Only the first line of a block is colored; the lines
    under it (a manifest under its --- header) stay plain."""
```

- The codes are plain SGR: bold `1`, dim `2` is not used (it is faint in some terminals;
  bright black `90` instead), red `31`, green `32`, yellow `33`, magenta `35`, cyan `36`,
  reset `0`. Each painted piece ends with a reset, so a color never runs into the next line.
- The cost in an AI line (`~$0.4462`) is found with a regex and made bold.
- `paint` never changes the characters: `strip_codes(paint(x, k))` is `x` for every kind.

## Tests

- `enabled`: a pipe is off; a stand-in terminal (an object whose `isatty()` is True) is on;
  `NO_COLOR=1` off, `NO_COLOR=` (empty) on; `TERM=dumb` off; `HPM_COLOR=always` on a pipe,
  `HPM_COLOR=never` on a terminal.
- `kind_of` on one example line of each kind from the README's table, with and without the
  leading spaces of a progress line, and on a plain listing line.
- `paint`: for each kind, the codes are where the README's table says, and stripping them
  gives the text back; a two-line block colors only its first line; `on=False` returns the
  text as it is.

## Done when

The tests pass. Nothing calls the module yet, so no output changes.

## As built

- `hallux/hpm/paint.py` as above, plus a `dim` kind (gray, no marker) for pieces such as
  the `(backup: …)` after a summary, and `strip_codes`. `HPM_COLOR=always` wins over
  `NO_COLOR`, as the README says it overrides the rest.
- An AI line has no marker of its own: "the AI " is part of the words, so the whole line is
  magenta, each `~$…` in it bold.
- `tests/test_hpm_paint.py`: 38 tests (the switch, a line of each kind, the codes of each
  kind, a block, off).
