# Fix 03: a new version keeps the manifest's old words

[The fixes](README.md) · [the plan](../README.md) · built on [step 2](../02-store-and-publish.md)
(publish) and [step 6](../06-ai-session.md) (the changelog's draft)

**Status:** planned 2026-10-24, from a read-only review of the user's own run. Not built.
The decisions below are proposals, not confirmed.

**Changes:** `hallux/hpm/publish.py` (a notice when the card changed and the manifest's
words didn't), `hallux/hpm/ai.py` and `hallux/hpm/prompts/changelog.md` (the draft also
says what in the manifest disagrees), `hallux/hpm/assist.py`, `tests/test_hpm_publish.py`,
`tests/test_hpm_ai.py`.

## What happened

kittystory 1.1's changelog (drafted by the AI, kept by the user) says: no options now
opens the web window, `-c` is a plain text chat, GUI mode (`-g`) is gone, and a content
setting is saved in `~/.kittystory/config.json`. Its manifest is 1.0's with only `version`
changed:

- `summary`: "…: TUI, GUI and web app …"
- `memory_line`: "… -w web (SVG scene, sprites, faces, ⚙ config), -g gui"
- `requires.addons = ["web", "gui"]`: an install still needs the gui addon.
- `~/.kittystory/config.json` is in no package's `[files]`. The review did name it
  ("that file is not mentioned anywhere in the manifest or its memory_line").

The cost shows in `test-kittystory`: its memory has only the manifest's line, so its
machine is told `-g gui` exists. (`danika` has the machine's own line about 1.1 besides,
from the user's session.)

## Why

Publish packs the manifest as it is in the world and only sets `version`. Nothing compares
the manifest's words with what changed. The changelog's draft sees the changed files but
not the manifest; the review sees both but looks only at what reaches beyond the program.

This is the author's text, not an hpm bug. But hpm is the one place that knows the card
changed and the manifest's words didn't, and it already has an AI reading the change.

## What to build

1. **A notice in publish, with no AI** (decision 1). For a new version whose card changed,
   when `summary`, `memory_line` and `requires` are word for word as in the last release:

   ```
   kittystory: the card changed since 1.0, but the summary, memory line and requires are
   as they were. Still right? [Y/n]
   ```

   `n` stops the publish, with "edit /usr/local/share/hpm/kittystory/hpm.toml, then
   publish again". `--yes` or no terminal: the notice is said and the publish goes on.
2. **The changelog's draft looks at the manifest too** (decision 2). The changelog job gets
   the manifest's text. Its prompt asks for the entry, then, only if something disagrees,
   a block after a line `Manifest:` naming it ("memory_line still mentions -g gui, which
   this version removes"; "requires.addons still has gui"; "~/.kittystory/config.json is
   written by the card and in no package"). hpm cuts that block off before the entry goes
   into `$EDITOR`, and says it above, so the user can fix the manifest first.
3. **No rewriting of the manifest by the AI** (decision 3). It names; the user edits.

## Tests

- Publish of a second version with the card changed and the three fields the same: the
  question is asked; `n` stops with the edit message; `--yes` says the notice and goes on.
- The card the same, or one of the fields changed: no notice.
- The stand-in changelog AI answers an entry plus a `Manifest:` block: the entry put in the
  changelog has no block, and the block is said.
- An answer with no block: the entry as now.

## Done when

- The tests pass, and the whole suite (`--deselect tests/test_sandbox.py`).
- One paid check, only on the user's go: publish a kittystory 1.2 from a copy of `danika`
  with the old words, and see the block name `-g gui` (about $0.25).

## By hand, for kittystory now

Before 1.2: in `danika/usr/local/share/hpm/kittystory/hpm.toml`, change the summary and
the memory line to say what 1.1 does, set `requires.addons = ["web"]`, and decide which
package owns `~/.kittystory/config.json` (likely the app, as `data`, so updates keep it).
Publishing that as 1.2 and updating `test-kittystory` puts the right line in its memory.

## Decisions of this fix

| # | Proposal | Why |
|---|---|---|
| 1 | **A plain notice, asked only when the card changed and all three fields didn't** | Free and certain; a question after every publish would be ignored |
| 2 | **The changelog's draft names what disagrees,** in the same session | It already reads the change; a few more tokens, no new session |
| 3 | **The AI names, the user edits** the manifest | The manifest is the author's promise to friends; hpm writes only `version` and what fix 02 cleans |
