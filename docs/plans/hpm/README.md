# Plan: hpm, the Hallux package manager

**Status:** written on 2026-10-23, at the user's request ("go ahead, write the plan"). No
step is built. The design it follows is in [docs/hpm/](../../hpm/README.md):
[hpm.md](../../hpm/hpm.md) (packages, the store, publish, install, conflicts, the world's
record, the Packages tab), [migrations.md](../../hpm/migrations.md) and
[sharing.md](../../hpm/sharing.md). The design is done and every question of it is
decided. The decisions this plan takes on its own are in
[a table below](#decisions-of-this-plan); **they are my proposals, not confirmed yet.**
**Decision 8 changes migrations.md:** the AI writes a migration's new files into a staging
folder, not into the world.

The build is on the branch `hpm`, made from `main` on 2026-10-23 after the user merged
`gui-addon` (PR #11).

**How this plan is laid out.** Like the plans of the web addon and drag and drop: this file
holds what the steps share, and every step has a file of its own. A step is built and
committed by itself, only when the user says so.

## In short

1. **The manifest and the archive:** `hpm.toml` read and checked, a package packed into one
   `.hpm` file and unpacked safely.
2. **The store and `hpm publish`,** without the AI: a manifest you write by hand is enough.
3. **The install engine,** without a screen: what would be written and what is in the way,
   the copy, the world's record, the memory line, the backup, many packages at once.
4. **The command in your terminal:** `hpm install`, `update`, `remove`, `list`,
   `rollback`, with the checkbox and conflict screens, and the mark of a running world.
5. **The Packages tab** of the panel, and the note to the running machine.
6. **The AI's session:** `hpm init`, changelogs, merging memories, the card review, the
   test install.
7. **Migrations.**
8. **Stores on GitHub:** `hpm store`, `hpm push`, installing from a friend.
9. **The manual, the docs and the live run.**

Until step 4 nothing changes for the user; after it, `hpm` works in the terminal for
packages whose manifest you wrote yourself. **The Packages tab comes as step 5,** earlier
than the design's order of work put it, because the user "exceptionally" likes it: it only
needs the engine of step 3. Step 9 changes `hallux/prompt.md`, which the user edits too.

---

## How the parts fit

```text
 your terminal                                 a running world (Ctrl+F12)
   hpm (hallux/hpm/cli.py)                       Packages tab (hallux/panel_tabs/packages.py)
        │                                              │  runs the engine in a thread,
        │  refuses to write a world that is running    │  as the Files tab runs its copy
        ▼                                              ▼
 ┌──────────────────────── hallux/hpm/ ─────────────────────────────────┐
 │ manifest.py  hpm.toml: kinds of files, extras, bundles, needs         │
 │ archive.py   .hpm files: pack, unpack, checksums                      │
 │ store.py     ~/.local/share/hallux/hpm/: local/, stores/, cache/      │
 │ engine.py    plan → conflicts → backup → write → record → memory line │
 │ record.py    /.hallux/hpm/installed.json, backups/                    │
 │ ai.py        hpm's own Claude session: init, changelog, merge, review │
 │ migrate.py   data formats, notes, staging, checks, accept, rollback   │
 │ remote.py    stores on GitHub: index.toml, download, push through gh  │
 └───────────────────────────────────────────────────────────────────────┘
        │ every write into a world goes through hallux.disk (Disk, write_whole, copy_whole):
        ▼ inside the world's folder only; /.hallux only for the record, backups, memory line
   the world's folder                         the machine's next message gets <installed>
```

## Decisions of this plan

My proposals, 2026-10-23; not confirmed yet.

| # | Decision | Why |
|---|---|---|
| 1 | **The code is a package, `hallux/hpm/`, and the command is `hpm`,** one more line in `[project.scripts]` (`hpm = "hallux.hpm.cli:main"`). `python -m hallux.hpm` works too | One install gives both commands; the engine is shared by the command and the Packages tab |
| 2 | **A `.hpm` file is a gzipped tar** of the folder of hpm.md section 3. Unpacking takes plain files and folders only: no links, no devices, no absolute paths, no `..`, at most 10 000 files and 200 MB unpacked | Python reads and writes it with no new dependency; the checks are hpm's own, so they hold on Python 3.11 too |
| 3 | **The store's folder is `$XDG_DATA_HOME/hallux/hpm/`,** by default `~/.local/share/hallux/hpm/`; `HPM_HOME` overrides it, for the tests | hpm.md decision 3; the variable keeps tests away from your real store |
| 4 | **A file's fingerprint is its sha256.** The world's record keeps one for every file hpm wrote | It is what tells "you changed this file" from "hpm installed it" (hpm.md section 7) |
| 5 | **The world's record is JSON,** `/.hallux/hpm/installed.json`, written whole (`write_whole`) | The machine can't see `/.hallux`; a half-written record never exists |
| 6 | **A backup is a plain copy** under `/.hallux/hpm/backups/<time>/`, with `backup.json` naming what each file was (there, changed, or missing). It is taken before anything is overwritten, removed or migrated, and only of those files | `hpm rollback` is then a copy back, and a backup holds no more than an install touches |
| 7 | **Data is never removed by an install or an update.** Only `hpm remove --data` and an accepted migration remove data, each after a backup | migrations.md, section 1; one rule the engine checks, whatever calls it |
| 8 | **A migration's new files are written into a staging folder,** `/.hallux/hpm/staging/<time>/`, through a disk that writes only there. Hallux's code lands them in the world when you accept, and removes the old paths then. **This changes migrations.md, section 4:** the world isn't touched until you accept | The AI can't damage the world's data even by mistake, a cancelled migration leaves nothing behind, and "the old files stay until you accept" holds without anything to clean up |
| 9 | **hpm's AI session gets its own tools:** `list_dir`, `stat`, `read_file`, `find` on the world, and a write that reaches only the one place a job may write (a manifest, a changelog, a staging folder). No `remove`, no `memory_edit`, no shell | The least that each job of step 6 and step 7 needs |
| 10 | **The AI's model, effort and cap** are in the store's `config.toml`: by default the model the world runs on, effort `medium`, at most $1.00 per session. The cost is printed when a session ends | hpm.md section 11; a migration of a big character folder may need more than a job of the addon agents |
| 11 | **A running world is marked by `/.hallux/running`,** which `hallux/app.py` writes with its process number at the start and removes at the end. A mark whose process is gone counts as not running | hpm.md section 10; a crash must not lock a world for good |
| 12 | **Without `--world`, hpm looks for the world** from the folder you are in, upwards, to the first one with a `.hallux/` folder in it, the way git finds its repository. Without one, it asks for `--world` | Suggested in the conversation (2026-10-23), not answered; easy to drop |
| 13 | **Versions are whole numbers with dots** (1.4, 1.4.1, 2.0), compared number by number; nothing like `-beta` | All that hpm.md section 5 needs |
| 14 | **The command's screens are prompt_toolkit,** like the panel, and every question has a flag too (`--extras packs,characters`, `--overwrite all|none`, `--yes`), for scripts and the tests | prompt_toolkit is already a dependency; flags make every screen testable without a terminal |
| 15 | **The Packages tab's key is `p`,** and it sits between Files and Config | The panel takes a tab's first letter as its key, and `p` is free |
| 16 | **"Merge" for memories needs the AI** (step 6). Until step 6 is built, the conflict screen doesn't offer it | hpm.md section 7 |
| 17 | **The test install runs the world headless,** as `hallux <root> --script` does (`hallux.script.run_script`), on a copy of the base world, with one line: the app's name. The AI's answer and the cost are shown | It is the way Hallux already runs a machine without a terminal |
| 18 | **A store on GitHub is pushed to with `gh` and `git`;** reading a public store is plain HTTPS downloads (`urllib`). The tests use a folder as a store (`file://`), never the network | sharing.md decision 3 |
| 19 | **The machine is told with `<installed>`,** in front of its next message, as drag and drop tells it with `<imported>` (`imported_block` in `hallux/machine.py`) | The way the machine already learns of files that arrived |

## Where the code goes

| File | What |
|---|---|
| `hallux/hpm/__init__.py`, `__main__.py` | The package; `python -m hallux.hpm` |
| `hallux/hpm/manifest.py` | `hpm.toml`: reading, checks, kinds of files, patterns, `~`, extras, bundles, needs |
| `hallux/hpm/archive.py` | Packing and unpacking `.hpm` files, checksums |
| `hallux/hpm/store.py` | The store on your PC: its folders, `config.toml`, releases, versions |
| `hallux/hpm/engine.py` | Install, update, remove: the plan, the marks, the write, many packages at once |
| `hallux/hpm/record.py` | The world's record, backups, rollback, the memory line |
| `hallux/hpm/cli.py`, `screens.py` | The command and its screens |
| `hallux/hpm/ai.py`, `hallux/hpm/prompts/*.md` | hpm's own Claude session and the prompt of each of its jobs |
| `hallux/hpm/migrate.py` | Data formats, migration notes, staging, checks, accept and roll back |
| `hallux/hpm/remote.py` | Stores on GitHub |
| `hallux/panel_tabs/packages.py` | The Packages tab |
| `hallux/app.py` | `/.hallux/running`; the Packages tab in the panel's list |
| `hallux/machine.py` | `<installed>` in front of the next message |
| `hallux/prompt.md` | What `[hpm …]` in memory means, and `<installed>` (step 9) |
| `pyproject.toml` | The `hpm` command; the prompts as package data |
| `tests/test_hpm_*.py` | Every step's tests |
| `docs/hpm/` | What each step built, in its "As built" |

## The steps

| Step | What | Status |
|---|---|---|
| [1](01-manifest-and-archive.md) | `hpm.toml` and its checks; `.hpm` files | Not built |
| [2](02-store-and-publish.md) | The store on your PC; `hpm publish` without the AI | Not built |
| [3](03-install-engine.md) | The plan, marks, the copy, the record, the memory line, backups, many packages | Not built |
| [4](04-command.md) | `hpm install / update / remove / list / rollback`, the screens, a running world | Not built |
| [5](05-packages-tab.md) | The Packages tab, `<installed>` | Not built |
| [6](06-ai-session.md) | hpm's AI session: `init`, changelogs, merge, card review, test install | Not built |
| [7](07-migrations.md) | Data formats, migration notes, staging, checks, accept, roll back | Not built |
| [8](08-github-stores.md) | `hpm store`, `hpm push`, `yank`, installing from a friend | Not built |
| [9](09-manual-docs-live-run.md) | The manual, the docs, the live run | Not built |
