# Fix 04: an adopted app records none of its extras

[The fixes](README.md) · [the plan](../README.md) · built on [step 3](../03-install-engine.md)
(adopt) and [step 2](../02-store-and-publish.md) (publish adopts the author's world)

**Status:** planned 2026-10-24, from a read-only review of the user's own run. Decisions
confirmed by the user 2026-10-24 ("yes, as proposed"). **Built** 2026-10-24: see "As built"
at the end. What the empty list breaks is read from
the code, not seen in a run.

**Changes:** `hallux/hpm/engine.py` (`_install_item` when adopting), `tests/test_hpm_engine.py`,
`tests/test_hpm_cli.py`.

## What happened

In `danika`, where the user published all six packages, `.hallux/hpm/installed.json` has
kittystory 1.1 with `"adopted": true` and `"extras": []`, while all five extras are there as
packages of their own (also adopted). In `test-kittystory`, installed from the store, the
same entry has `"extras": ["packs", "characters", "me", "places"]`.

## Why

`plan_adopt` makes `Item(manifest.name, release, manifest)` with no extras, and
`_install_item` records `list(item.extras)`. An extra adopted later doesn't add its key to
the app's entry either. So after a publish, the author's own world says the app has no
extras.

## What it breaks (from the code)

- **`hpm update kittystory`** in that world builds its `Want` from the recorded extras
  (`cli.py:272`), so it passes `extras=()`: the app is updated, its extras aren't, even
  when a newer extra is in the store.
- **The Packages tab** ticks an installed app's extras from the record
  (`panel_tabs/packages.py:194`), so all of kittystory's extras show unticked in `danika`.
- `hpm list` shows no `extras:` for it.

## What to build

1. **Adopting an app records the extras that are already recorded:** the keys of its
   `[extras]` whose package is in `installed.json` (decision 1).
2. **Adopting an extra adds its key to its app's entry,** if the app is recorded. Publish
   `--all` adopts the app first and the extras after, so (1) alone would miss them.
3. The same in `hpm adopt` and in the adopt that publish does; both go through
   `_install_item`.

## Tests

- Publish `--all` of an app with two extras into its own world: the app's entry lists both
  keys.
- `hpm adopt` of an extra whose app is recorded: the key is added; of an app whose extras
  are recorded: they're listed.
- After that, `hpm update` of the app with a newer extra in the store updates the extra too.

## Done when

- The tests pass, and the whole suite (`--deselect tests/test_sandbox.py`).
- On a copy of `danika`, `hpm adopt kittystory` again gives
  `"extras": ["packs", "characters", "me", "places", "memories"]`. No paid run.

## Decisions of this fix

| # | Proposal | Why |
|---|---|---|
| 1 | **The record follows what is installed,** not the extras' defaults | In the author's world every extra is there, `memories` too, though it isn't ticked by default |

## Seen too, and as designed

`danika`'s `data/state.json` and `data/tree.json` belong to no package. Init wrote clean
seed copies for the release (`/usr/local/share/hpm/kittystory/seed/`), and the world's
played-in copies differ from them, so adopt leaves them the user's. Nothing to fix.

## As built

- `_install_item` in `hallux/hpm/engine.py`: an adopted package's entry lists the keys of its
  `[extras]` whose packages are in `installed.json`; `_join_app` adds an adopted extra's key
  to its app's entry, reading the app's manifest from the world.
- This also covers publishing from a world that *installed* the app (fix 06's analysis): the
  adopt after publish used to wipe that world's extras from its record.
- Tests (`tests/test_hpm_cli.py`): `test_publish_all_records_the_extras_in_its_own_world`,
  `test_publish_from_a_world_that_installed_it_keeps_its_extras`,
  `test_adopting_an_extra_adds_its_key_to_the_app` (with the update that follows). All three
  fail without the change.
- By hand: on a copy of `danika` with a copy of the store, `hpm adopt kittystory` gave
  `["packs", "characters", "me", "places", "memories"]` (it was `[]`). `danika` itself is
  fixed by running the same command there.
