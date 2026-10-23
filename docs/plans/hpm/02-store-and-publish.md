# Step 2: the store, and `hpm publish` without the AI

[The plan](README.md) · the design: [hpm.md](../../hpm/hpm.md), sections 4 and 5;
[sharing.md](../../hpm/sharing.md), section 3; plan decisions 3, 12

**Needs:** step 1. **Changes:** new `hallux/hpm/store.py`, `cli.py` (only `publish` and
`show`), `__main__.py`; `pyproject.toml` (the `hpm` command); `tests/test_hpm_store.py`,
`tests/test_hpm_publish.py`.

After this step you can publish a package whose manifest you wrote yourself, into the store
on your PC, and look at it. Nothing installs yet. The AI's parts of publish (the changelog's
draft, the migration's offer, the test install) come with steps 6 and 7.

## Build

**The store** (`store.py`), at `$HPM_HOME`, else `$XDG_DATA_HOME/hallux/hpm/`, else
`~/.local/share/hallux/hpm/`:

```
config.toml        model, effort, cap_usd (step 6); base_world (step 6's test install)
local/<name>/<version>.hpm
stores/<store>/index.toml      (step 8)
mine/<store>/                  a clone of your own store on GitHub (step 8)
cache/<store>/<name>-<version>.hpm   (step 8)
```

`Store.releases(name)`, `Store.latest(name)`, `Store.add(file)` (refuses a version that is
there already, and one lower than the latest), `Store.find(name)` (local first; stores
come in step 8).

**Finding the world** (decision 12): `--world PATH`, else the folder you're in and its
parents, to the first with `.hallux/` in it.

**`hpm publish NAME [--all] [--version V] [--changelog TEXT]`:**

1. Reads the manifest from the world: `/usr/local/share/hpm/<name>/hpm.toml`.
2. Collects the files its patterns match, through `Disk` (so nothing outside the world, and
   nothing in `/.hallux`, can get in). `~` patterns are read from the home of the world's
   user (step 3's `world_user`, written here). A pattern that matches nothing is an error.
   Each file gets its kind by `kind_of` (step 1). A file that this package and one of its
   extras both carry (their manifests are beside it in `/usr/local/share/hpm/`) stops the
   publish, with the file's name.
3. **Version:** higher than the store's latest. Without `--version` it suggests one: the
   last number up when only `app` files changed, the first number up when `data_format` went
   up, and asks.
4. **Changelog:** `--changelog`, else `$EDITOR` on a file that has the last entry's title
   filled in; an empty entry stops the publish. The entry goes at the top of the package's
   `CHANGELOG.md`, in the world too.
5. **Data paths that moved:** the `data` patterns are compared with the last release's. If
   they differ and `data_format` didn't go up, publish stops and says so. (Step 7 adds the
   offer to have the AI write the migration.)
6. **Privacy:** a package with `private = true` is published into `local/` as any other;
   only a push refuses it (step 8). A data package whose files include `memory.md`,
   `shared.md` or a file named like a chat (`state.json`, `history*`, `chat*`) and isn't
   marked private gets a warning, and the question whether to mark it.
7. **Seeds:** a seed file more than twice the size it was in the last release gets a
   warning ("it may hold your own data now").
8. Packs the folder (step 1) and adds it to the store.

Publish writes into the world only under `/usr/local/share/hpm/<name>/` (the changelog
here), so it works on a running world too (hpm.md section 10). Recording the release in the
world it came from (hpm.md section 5) needs the world's record, and comes in step 4.

`--all` publishes the package and each of its extras whose files changed since their last
release, each with its own version and changelog question.

**`hpm show NAME`:** the manifest, the versions in the store, the last changelog entries,
the files by kind and their sizes.

## Tests

- The store's folder from each of the three variables; releases, latest, refusals.
- Finding the world from a folder deep inside it; refusing without one.
- Publish: the files collected, `~` from the world's user, a pattern that matches nothing,
  a lower version, an empty changelog, data paths that moved, the privacy warning, the seed
  warning; `--all` with one extra unchanged; a file both the app and an extra carry.
- `state.json` inside the `app` folder is collected as a `seed`.
- A publish never writes outside the store, but for the world's
  `/usr/local/share/hpm/<name>/CHANGELOG.md`.

## Done when

kittystory and its packs, published from a copy of `test-hallux` with a manifest written by
hand from the world's real files (hpm.md section 2, as the review corrected it), are in the store as two `.hpm` files, and `hpm show kittystory` lists them.

## As built

Built 2026-10-23: `hallux/hpm/world.py`, `store.py`, `publish.py`, `cli.py`, `__main__.py`;
`hpm = "hallux.hpm.cli:main"` in `pyproject.toml`; `listing` and `read_member` added to
`archive.py`; `tests/test_hpm_store.py` (19 tests), `tests/test_hpm_publish.py` (46), and
`HPM_HOME` set in `tests/conftest.py`, so that no test reaches your real store. The whole
suite: 2098 passed (the sandbox test left out, as in step 1).

**The run of "Done when"** (a copy of `test-hallux` in the session's scratchpad, a store of
its own there, manifests written by hand from the world's real files): `kittystory 1.0`
(10 app files and the seed, 34.5 KB) and `kittystory-packs 1.0` (the three packs from
`~/.kittystory/packs/`) went into the store as two `.hpm` files; `hpm show` listed them,
the seed under its own kind. A second publish with nothing changed was refused. In the
world, only `/usr/local/share/hpm/kittystory/` changed (its `CHANGELOG.md`). It ran as
`python -m hallux.hpm`: the `hpm` command itself appears in `.venv/bin/` only after the
package is installed again (`pip install -e .`), which I didn't do to your venv.

What the code does that the step above didn't say, or says differently:

- **Four modules, not one.** `world.py` (finding the world, its user, the files a
  manifest's patterns match, and `HpmError`), `store.py`, `publish.py` (publish, show and
  the questions), and `cli.py`, which only reads the command line. Steps 3 and 4 use
  `world.py` as it is: `world_user` is the rules of step 3 already (`/etc/passwd`, then the
  homes that aren't empty).
- **`--yes`** takes the version hpm suggests, without asking. Without it, `--all` couldn't
  run without a terminal: each package's version is a question, and `--version` can't go
  with `--all`. The run above found that.
- **`--user U`** for a world with several users, and **`--private yes|no`** for the privacy
  question. Without a terminal, every question without its flag is an error that names the
  flag (as step 4 will do for its screens).
- **What "changed" means:** the files' fingerprints, the migration notes and the manifest
  (all but its version) against the store's latest. Nothing changed is an error for one
  package and a line for each under `--all` ("unchanged, not published").
- **The suggested version:** the manifest's own for a first release; after that the last
  number up (1.4 → 1.5, 2 → 2.1), or the first up when `data_format` went up (1.4 → 2.0).
  It doesn't look at which kinds of files changed. `data_format` going down is refused.
- **The version goes into the world's manifest** by changing its one `version = …` line;
  comments and everything else stay. `private = true` is put in the same way, before the
  first table.
- **The changelog entry** is `## <version> (<date>)`, then the text. It goes on top of
  `/usr/local/share/hpm/<name>/CHANGELOG.md`, under its `# ` title if it has one, and the
  release carries the whole file.
- **The order of writing:** every check, then the release packed in a temporary folder and
  put into the store, and only then the world (the manifest's version, the changelog). If
  the world can't be written then, hpm says the release is in the store and what to set by
  hand.
- **A link** that a pattern reaches is refused, by name: a package holds plain files.
- **The privacy question** comes for a package with `data` files or a `for`. The names it
  looks for are `memory.md`, `shared.md`, `state.json`, `history*` and `chat*`.
- **`hpm show`** lists at most 30 files of each kind by name, and the three newest
  changelog entries.
- **Seen in the real world:** kittystory's `state.json` seed is 2.9 KB and holds the chat.
  Publish warns only when a seed has more than doubled since the last release; the clean
  seed is `hpm init`'s (step 6).
