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
| `hpm store init NAME --repo OWNER/REPO` | makes the repository with `gh repo create` (public, sharing.md decision 1), an empty `index.toml` and a README saying how to add the store, and clones it into `mine/NAME/` for `push` |
| `hpm store add NAME URL` | `URL` is the repository's address as the browser shows it (`https://github.com/<owner>/<repo>`). hpm asks GitHub's API for its default branch (`https://api.github.com/repos/<owner>/<repo>`, no sign-in needed for a public one) and downloads `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/index.toml` into `stores/NAME/` |
| `hpm store list` / `hpm store remove NAME` | |
| `hpm store refresh [NAME]` | downloads the indexes again; `install`, `update` and `search` refresh one older than an hour |
| `hpm push NAME… [--all]` | sharing.md section 2: refuses private packages, shows the review (step 6) when it found something, `gh release create <name>-<version>` with the archive, the index updated in `mine/<store>/` (pulled first), committed and pushed with `git`; the last line says GitHub may show the old index for a few minutes |
| `hpm yank NAME VERSION` | marks it in the index; installs skip it unless named exactly |

**Installing from a store:** `Store.find` looks in `local/` and every store; `store/name`
picks one, and a name in several stores is asked about (sharing.md section 5). A download goes
into `cache/`, and its sha256 must be the index's or it is deleted and refused. The record
keeps the store, and `hpm update` takes the next version from the same one.

**Network:** HTTPS only, with `urllib`, a time limit, and a clear error when GitHub can't be
reached. **Public stores only** in this step (sharing.md section 1): a store that answers
"not found" or asks for a sign-in is an error that says so; reading a private store through
`gh` comes when someone needs it. `gh` and `git` must be installed for `store init` and `push`; hpm says how when
they aren't, and never asks for a token itself.

**The Packages tab** shows every store's packages, the store's name on each row, and `R`
to refresh (an uppercase letter, so no tab's key).

## Tests

No network: a folder stands in for GitHub (`file://` URLs), and `gh` and `git` are stand-in
commands that record what they were asked.

- `index.toml` written and read back; the same index from the same releases.
- Push: private refused, the review shown, the release and index commands, a version pushed
  twice refused.
- Add from a repository's address: the default branch asked for, the raw address built;
  refresh, remove; a stale index refreshed; a broken index refused; a private store's
  answer told as such.
- `store init` makes the clone in `mine/`; push pulls it first.
- Install from a store: the checksum checked (a changed archive refused), the cache, a yanked
  version skipped, a name in two stores asked about, the record's store, update from it.

## Done when

The user makes their store on GitHub, pushes kittystory with packs and characters, and
installs it into a second world from the store's URL, as a friend would. The user's run,
since it uses their GitHub account.

## As built

Built 2026-10-23, **without the user's run** (it needs their GitHub account):
`hallux/hpm/remote.py` (the index and its TOML writer, downloads, a friend's store, your own
store's clone, the `gh` and `git` calls), the store (`Store.find` and the rest take a store
name; `Ambiguous`), the engine (a `Want` names its store), `cli.py` (`hpm store
init/add/list/remove/refresh`, `push`, `yank`; install, update, list and search across
stores), `publish.py`, `running.py` and the Packages tab; `tests/test_hpm_remote.py` (17
tests), with a folder in place of GitHub and a stand-in for `gh` and `git`. No test, and
nothing else in this step, touched the network or GitHub. The whole suite: 2291 passed, the
sandbox test left out as before.

**Checked on a real terminal** (tmux, 80 columns): danika's store pushed into the folder
that stands in for GitHub, oliver's PC with it added and nothing downloaded, Hallux on a
fresh copy of `oliver-test`. Ctrl+F12, `g`: "danika: 2 packages not downloaded yet · R
downloads them"; `R`: `danika/kittystory` with its packs; space, Enter, Enter: both
installed, and `hpm list` says `kittystory 1.1 (from danika)`. That run found: the empty
list said "hpm publish puts one there" while a friend's packages waited for R (now it says
only the R line); a line cut at 80 columns (folded now); the list's head, cut at 80 columns
since step 5 (its keys fold onto a line of their own when it doesn't fit); and a store whose
kittystory was in data format 2 with its packs still in 1, so installing the packs migrated
them, as migrations.md section 2 says. Publish now tells that to the author.

**The user's run, still to do:** `hpm store init <name> --repo <you>/hpm-store`, `hpm push
kittystory kittystory-packs` (and characters, if published), then in a second world `hpm
store add <name> https://github.com/<you>/hpm-store` and `hpm install <name>/kittystory`,
as a friend would; `gh` must be installed and signed in (`gh auth login`).

What the code does that the step above didn't say, or says differently:

- **`hpm store`** is dispatched to `Run.stores`, since `Run.store` is the store itself.
- **Your own store** is the clone in `mine/<name>/` and a small `mine/<name>.toml` with its
  owner and repository (so push needn't ask git). `store init` runs `gh repo create
  OWNER/REPO --public`, `gh repo clone` into `mine/`, writes `index.toml` and `README.md`
  (with the line a friend needs), commits and pushes. A friend's store is `stores/<name>/`
  with `index.toml` and `source.toml` (owner, repo, branch, url, when it was fetched).
- **A friend's release downloads when it is first needed** (its path is wanted), into
  `cache/<store>/<name>-<version>.hpm`. Every use checks its sha256 against the index, and
  that its manifest is the name and version the index says; one that isn't is deleted and
  refused. Downloads: HTTPS only, 20 s each, an index at most 4 MB, an archive 256 MB; 401,
  403 and 404 say "isn't there, or it is private".
- **Names:** `danika/kittystory` is that store's; `kittystory` is the one store's that has
  it; in two (your `local` counts) the terminal asks with the pick screen, and without a
  terminal the error names both forms. **Extras, needs and a bundle's packages** come from
  the store of the package that brought them, else from your own store, else from wherever
  they are. The record keeps the store (`from`), and `update` and `list` look there.
- **`push`** pulls the clone first, takes the newest local release of each NAME (or `--all`:
  each newer than in the store, private ones skipped and told), refuses a private package
  and a version that is there already, tells an extra that isn't in the store, shows the
  review made at publish, and if there is none and you are in a world, can have the AI make
  one (`--review`, or asked on a terminal). A review that found something stops the push
  unless you say yes (`--yes`). Each package is its own GitHub release (the changelog's
  entry and the review as its notes) and its own commit of the index, so a failure half way
  leaves the index right about what was pushed.
- **The index** keeps `sha256` as bare hex, `requires = { addons = […] }`, `extras`,
  `data_format`, `yanked`, and `latest`, the newest version that isn't yanked. `yank`
  changes only that (a yanked version is still installed when named exactly, as update and
  the test install can).
- **install, update and search** refresh an index older than an hour first; one that can't
  be reached is used as it was, with a note. `search` reads friends' summaries from their
  indexes and downloads nothing.
- **The Packages tab** shows every store's packages, a friend's as `danika/kittystory`,
  once its archive is downloaded: the tab never waits on the network while it draws. `R`
  refreshes every store and downloads their newest archives in a thread; until then a line
  says how many wait. `R refresh` shows in the list's head only when there is a friend's
  store.
- **Publish** says when an app's data format is newer than an extra's in the store: every
  install of that extra beside the app would be migrated.

**Not built:** reading a private store through `gh` (sharing.md: when someone needs it);
`hpm show` of a friend's package (it shows your own store's).
