# Fix 06: a world that installed an app has no clean seeds to publish

[The fixes](README.md) · [the plan](../README.md) · built on [step 3](../03-install-engine.md)
(install) and [step 6](../06-ai-session.md) (`hpm init`'s clean seed)

**Status:** planned 2026-10-24, from a read-only analysis the user asked for ("what happens
when i init APP1 in WORLD1 and then install APP1 to WORLD2 … can i use hpm to publish the
changes from WORLD2?"). Not built. The decisions below are proposals, not confirmed. What
goes wrong is read from the code and the two worlds' files; no publish from WORLD2 was run.

**Changes:** `hallux/hpm/engine.py` (`_meta_files` also lists the clean seeds),
`hallux/hpm/publish.py` (one helper for the clean seed's path, shared with the engine),
`docs/hpm/hpm.md` (section 5's publish bullet), `docs/hpm/sharing.md` (section 3),
`docs/hpm/tutorial.md` (a short "publishing from another world" passage),
`tests/test_hpm_engine.py`, `tests/test_hpm_publish.py`.

## What happens

Publishing from a world the app was installed into works: install copies `hpm.toml`,
`CHANGELOG.md` and the migration notes into `/usr/local/share/hpm/<name>/`
(`engine.py`, `_meta_files`), and that is all publish needs. But it doesn't copy the
`seed/` folder that `hpm init` wrote there, so publish in that world takes the seeds as
they are on its disk, after the app has used them.

The user's worlds show it:

- `danika` (where kittystory was built and inited) has
  `usr/local/share/hpm/kittystory/seed/usr/local/share/apps/kittystory/data/state.json` and
  `tree.json`.
- `test-kittystory` (installed from the store) has `hpm.toml` and `CHANGELOG.md` there,
  and no `seed/`. Its `state.json` and `tree.json` differ from the shas `installed.json`
  recorded at install: the app has written to them since.

So `hpm publish kittystory` in `test-kittystory` would put that world's state (its chat,
its story tree) into the next release as the first state of every new install. The only
warning, a seed more than twice its last size, doesn't fire: both files are smaller than
`danika`'s.

A second effect: since the used seeds differ from the release's, publish in that world
never says "nothing changed": using the app is a change.

## Why

`_meta_files` lists `hpm.toml`, `CHANGELOG.md` and `migrations/*` from the unpacked
release. The clean seeds are not in the release under their own names: publish puts each
one in `files/` in place of the world's own (`_with_clean_seeds`), so the release's seed
*is* the clean seed. Nothing writes it back to `/usr/local/share/hpm/<name>/seed/` in the
world it lands in.

## What to build

1. **Install writes each seed of the package twice** (decision 1): at its own path, as now
   (only if missing), and at `/usr/local/share/hpm/<name>/seed/<the seed's path without its
   leading />`, as a meta file. Its source is the same file of the release. `_meta_files`
   takes the manifest, so it knows which files are seeds.
2. **One helper for that path**, `clean_seed_path(name, machine)` in `publish.py`, used by
   `_with_clean_seeds` and by the engine, so the two can't drift. A `~/` seed keeps its `~`
   (`seed/~/.kittystory/x`), as `_with_clean_seeds` already reads it.
3. **The copy is a meta file in every other way** (decision 2): recorded in `installed.json`
   with kind `meta`; an update replaces it if it is as installed and asks if you changed it;
   a remove takes it away; an adopt records it if it matches the release. So `danika`, which
   had seed copies only where init wrote them, gets one for every seed at its next update.
4. **Publish is unchanged:** it already prefers the copy. In the installed world, that means
   the release's seed goes out again unless the author edits the copy, which is what an
   author in the first world does today. Fix 07 tells the author when the world's own seed
   and the copy differ.

## Tests

- Install of a package with two seeds (one under `/`, one under `~/`): both copies are under
  `/usr/local/share/hpm/<name>/seed/`, match the release's seeds, and are recorded as `meta`.
- The seed itself changed in the world after install, then publish of a new card: the
  release's seed is the copy, not the world's file.
- In that world, publish with only a used seed and nothing else changed: "nothing changed
  since …".
- Update: an untouched copy is replaced by the new release's seed; an edited copy is asked
  about. Remove takes the copies away. Adopt of a world that has the copy records it.
- `_with_clean_seeds` and the engine give the same path for `/x/y` and `~/x/y`.

## Done when

- The tests pass, and the whole suite (`--deselect tests/test_sandbox.py`).
- By hand, free: in a copy of `test-kittystory`, `hpm update kittystory` (or a remove and
  install) leaves a `seed/` folder there, and `hpm publish kittystory --changelog x
  --version 9.9` into a scratch `HPM_HOME` packs `danika`'s clean `state.json`, not the
  world's.

## By hand, for kittystory now

Until this is built, don't publish kittystory from `test-kittystory`. To try it there anyway,
copy `danika/usr/local/share/hpm/kittystory/seed/` into the same place in `test-kittystory`
first.

## Decisions of this fix

| # | Proposal | Why |
|---|---|---|
| 1 | **Install writes the clean seed into `/usr/local/share/hpm/<name>/seed/`** in every world, not only the author's | Then every world that has the manifest can publish the same way, with no new question; the copy is the release's own file, so it costs nothing to get |
| 2 | **The copy is a plain meta file** (recorded, updated, removed with the package) | Same rules as the manifest and changelog next to it; no new kind |
| 3 | **No change to the archive's layout** | The release's seed in `files/` already is the clean seed; carrying it twice would only add a second place to disagree |
