# Step 8: stores on GitHub

[The plan](README.md) · the design: [sharing.md](../../hpm/sharing.md); plan decision 18

**Needs:** step 6 (the review). **Changes:** new `hallux/hpm/remote.py`; `hallux/hpm/store.py`,
`cli.py`, `hallux/panel_tabs/packages.py`; `tests/test_hpm_remote.py`.

After this step you can push packages to your own store on GitHub, and a friend can add it
and install from it.

## Build

**`index.toml`** (sharing.md section 1), written by hpm only: a small writer in `remote.py`
for the few kinds of values it holds, read back with `tomllib` after every write to make sure
it reads.

**The commands:**

| Command | What |
|---|---|
| `hpm store init NAME --repo OWNER/REPO` | makes the repository with `gh repo create` (public, sharing.md decision 1), an empty `index.toml` and a README saying how to add the store |
| `hpm store add NAME URL` | downloads `index.toml` into `stores/NAME/` |
| `hpm store list` / `hpm store remove NAME` | |
| `hpm store refresh [NAME]` | downloads the indexes again; `install`, `update` and `search` refresh one older than an hour |
| `hpm push NAME… [--all]` | sharing.md section 2: refuses private packages, shows the review (step 6) when it found something, `gh release create <name>-<version>` with the archive, the index updated, committed and pushed with `git` |
| `hpm yank NAME VERSION` | marks it in the index; installs skip it unless named exactly |

**Installing from a store:** `Store.find` looks in `local/` and every store; `store/name`
picks one, and a name in several stores is asked about (sharing.md section 5). A download goes
into `cache/`, and its sha256 must be the index's or it is deleted and refused. The record
keeps the store, and `hpm update` takes the next version from the same one.

**Network:** HTTPS only, with `urllib`, a time limit, and a clear error when GitHub can't be
reached. `gh` and `git` must be installed for `store init` and `push`; hpm says how when
they aren't, and never asks for a token itself.

**The Packages tab** shows every store's packages, the store's name on each row, and a
`refresh` key.

## Tests

No network: a folder stands in for GitHub (`file://` URLs), and `gh` and `git` are stand-in
commands that record what they were asked.

- `index.toml` written and read back; the same index from the same releases.
- Push: private refused, the review shown, the release and index commands, a version pushed
  twice refused.
- Add, refresh, remove; a stale index refreshed; a broken index refused.
- Install from a store: the checksum checked (a changed archive refused), the cache, a yanked
  version skipped, a name in two stores asked about, the record's store, update from it.

## Done when

The user makes their store on GitHub, pushes kittystory with packs and characters, and
installs it into a second world from the store's URL, as a friend would. The user's run,
since it uses their GitHub account.
