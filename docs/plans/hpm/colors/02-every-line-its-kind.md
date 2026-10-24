# Step 2: every line hpm says gets its kind

[The colors plan](README.md) · [the hpm plan](../README.md) · built on [step 1](01-paint.md)

**Changes:** `hallux/hpm/publish.py` (`Questions`), `hallux/hpm/cli.py` (`main`'s error, the
summary, a few `say` calls), `hallux/hpm/assist.py` and `hallux/hpm/remote.py` (a few `say`
calls), the stand-in `Questions` of the tests (`say` takes `kind`), `tests/test_hpm_paint.py`.

## What to build

1. **`Questions.say(text, kind=None)`** prints `paint(text, kind, on=enabled(sys.stdout))`.
   The switch is read once, when the `Questions` is made. The tests' stand-ins (`Said`,
   `Script` in `test_hpm_publish.py`, `test_hpm_cli.py`, `test_hpm_ai.py`) take
   `kind=None` and keep only the text, so their asserts stay as they are.
2. **The questions:** `ask`, `confirm` and `choose` paint their prompt as `ask`: the question
   bold, the default in brackets dim. `edit` doesn't: the editor gets plain text.
3. **The error:** `main` prints `paint(f"hpm: {e}", "error", on=enabled(sys.stderr))`, and
   `hpm: stopped` the same.
4. **Lines with no marker say their kind** (README, decision 2). From the survey of the
   `say` calls, these:

   | Line | Kind |
   |---|---|
   | `outcome.summary()` in `_carry_out` | ok, or fail if anything failed; the `(backup: …)` after it dim |
   | `everything is up to date`, `… is the newest` | ok |
   | `cancelled; nothing was written` | warning |
   | `kept: …. Next: hpm publish …` (init) | ok |
   | `{name} is marked private …`, `… holds memories or a chat: marked private …` | note |
   | `the AI's draft didn't end well …`, `the review didn't end well …`, `the note can't be used …`, `the copy didn't boot` | warning |
   | `the AI says the manifest disagrees …` (fix 03) | warning |
   | the seed question of fix 07 (`… changed since 1.1, and there's no clean copy …`) and `kept 1.1's seed …` | warning |
   | `added the store …`, `made your store …`, `removed the store …`, `yanked …`, `removed N backups` | ok |
   | `nothing to push`, `there are no backups`, `no stores yet`, `nothing installed by hpm in this world` | plain |
   | `there from before, and kept as they are …` (fix 01) | note |
   | `the machine's memory has its own line about …` (the old-line question's text) | ask |

   Every other line is left to `kind_of`. The build goes through all 57 calls once more and
   adds a kind where a line has no marker and isn't plain; this table is the start of that
   list, not the end.

## Tests

- `Questions` with a stand-in terminal for stdout: `say("  ✓ kittystory 1.1 updated")`
  prints green with a bold `✓`; with `NO_COLOR=1`, plain.
- `main` with a failing command and a stand-in terminal for stderr: the error is red with
  `hpm:` bold; with a pipe (pytest's `capsys`), plain, as the existing tests expect.
- A whole `hpm update` with a stand-in terminal: the progress lines and the summary carry
  the codes of their kinds; stripped of the codes, the output is the same as without colors.
- The whole suite passes unchanged (its output goes to pipes, so it has no colors).

## Done when

The tests pass, and the whole suite (`--deselect tests/test_sandbox.py`).

## As built

- `Questions.say(text, kind=None)` and `Run.say` paint; `Questions.color` is read once.
  `_prompt` paints `ask`, `confirm` and `choose`; under readline the codes are wrapped in
  `\x01…\x02` so line editing keeps its place. `main` paints both `hpm:` lines for stderr.
- The summary is `fail` if anything failed, `ok` if anything was done, else plain;
  `paint` dims a trailing `  (backup: …)` on an `ok` or `fail` line.
- Explicit kinds, 21 in all: the table above, plus the rollback's "kittystory back to 1.0
  (…)" (ok). "cancelled; nothing was written" raised as an error stays an error (red); said
  by `_cancelled`, it is a warning. The rest go by their markers.
- The five test stand-ins (`Said`, `Script`) take `kind=None`; nothing else in the tests
  changed.
- Tests in `tests/test_hpm_cli.py`: `test_say_paints_on_a_terminal_and_not_with_no_color`,
  `test_a_question_is_bold_with_its_default_dim`,
  `test_the_error_is_red_on_a_terminal_and_plain_in_a_pipe`,
  `test_an_update_in_colors_reads_the_same_without_them`. Whole suite: 2363 passed.
