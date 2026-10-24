# Fix 07: publish sends a used seed without asking

[The fixes](README.md) · [the plan](../README.md) · built on [step 2](../02-store-and-publish.md)
(publish) and [fix 06](06-install-carries-clean-seeds.md)

**Status:** planned 2026-10-24, from the same analysis as fix 06. Not built. The decisions
below are proposals, not confirmed.

**Changes:** `hallux/hpm/publish.py` (`_with_clean_seeds` says which seeds had no clean
copy; a question for each that changed), `hallux/hpm/cli.py` (`--seeds release|world`),
`docs/hpm/hpm.md` (the usage line and section 5), `docs/hpm/tutorial.md` (the cheat sheet),
`tests/test_hpm_publish.py`, `tests/test_hpm_cli.py`.

## What happens

When a seed has no clean copy at `/usr/local/share/hpm/<name>/seed/<path>`, publish packs
the world's own file, whatever the app has written to it since. That happens:

- in a world the app was installed into, until fix 06 (the case of the analysis:
  `test-kittystory`'s `state.json` and `tree.json` have changed since install);
- in the author's world, for a seed `hpm init` judged clean and gave no copy, once the app
  has been used (init's prompt asks for a copy only "if a seed holds the user's own data");
- for a seed added to the manifest by hand after init.

The only guard is the size warning (more than twice the last release's), which a used
state that is about the same size passes.

And the opposite case, which fix 06 makes common: a clean copy is there, the author
changed the seed on purpose (a new first state for a feature), and publish packs the old
copy without a word.

## Why

`_with_clean_seeds` swaps in a copy when there is one and says nothing either way. Publish
knows the last release's seed (`theirs`), so it can tell a seed that changed since then,
but only uses that for the size warning.

## What to build

1. **A seed with no clean copy that differs from the last release's: asked** (decision 1).

   ```
   kittystory: the seed /usr/local/share/apps/kittystory/data/state.json changed since 1.0,
   and there's no clean copy of it. It may hold this world's own use (a chat, a story).
     r  keep 1.0's seed (the default)
     w  publish this world's file
     s  stop
   ```

   `r` packs the last release's file. `w` packs the world's, as today. `s` stops with
   "write a clean one at /usr/local/share/hpm/kittystory/seed/…, then publish again".
   The first release (no last one) is not asked: init has just looked at the seeds.
2. **`--seeds release|world` answers it for every seed** (decision 2). Without a terminal
   and without the flag: an error that names the flag, like every other question.
   `--yes` takes `release`, and says so per seed.
3. **A clean copy that differs from the world's seed: told, not asked** (decision 3):
   `note: published the clean seed /usr/local/share/hpm/kittystory/seed/…; the world's own
   state.json differs. To publish a new first state, write it there.`
4. **The question comes before the version and the changelog,** with the other checks, so
   `s` leaves nothing half done.

## Tests

- A second release, a seed with no copy, changed since the last release: asked; `r` packs
  the last release's bytes, `w` the world's, `s` stops and writes nothing (store and world
  as before).
- No terminal: an error naming `--seeds`; `--seeds world` and `--seeds release` answer it;
  `--yes` takes `release` and says it.
- The seed the same as the last release's, or a first release: not asked.
- A clean copy that differs from the world's file: the copy is packed, the note is said.
- With fix 06 built: publish in an installed world whose seed was used asks nothing (the
  copy is there) and says the note.

## Done when

- The tests pass, and the whole suite (`--deselect tests/test_sandbox.py`).
- By hand, free: in a copy of `test-kittystory` without fix 06's copies, `hpm publish
  kittystory --changelog x` into a scratch `HPM_HOME` asks about `state.json` and
  `tree.json`.

## Decisions of this fix

| # | Proposal | Why |
|---|---|---|
| 1 | **Ask only for a seed with no copy that changed since the last release; default: the last release's** | The cases where a world's use can leak, and only those; keeping the old seed is never worse than the release before |
| 2 | **One flag for all seeds,** `--seeds release\|world` | Like `--overwrite all\|none`; per-seed answers are what the terminal is for |
| 3 | **A differing clean copy is told, not asked** | The copy is the author's own choice; the note is enough to catch a forgotten one |
