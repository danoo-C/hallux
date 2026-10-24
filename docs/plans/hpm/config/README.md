# hpm: a config file

[The hpm plan](../README.md) · a plan for one file of hpm's own settings that loads
by itself, wherever hpm is run from.

**Status:** planned 2026-10-25 at the user's request ("could we create a config file for
hpm? because setting $EDITOR every time or the hpm-live store each time is soo bad";
"my main objective with this, is no matter where i run hpm from, the config should load
automatically"; "yes write the plan as recommended"). Decisions 1 to 4 are the user's
("as recommended"); 5 to 8 confirmed by the user 2026-10-25 ("commit and build it as
proposed").

| Step | What | Status |
|---|---|---|
| [01](01-the-file.md) | `hallux/hpm/config.py`: the file, read on every start; the store, the editor and the colors take it into account | **Built** 2026-10-25 |
| [02](02-the-command.md) | `hpm config`, `hpm config set`, `hpm config path`; the hints; the docs | Planned |

## Why

Today two settings come only from the environment:

- **The store:** `HPM_HOME`, else `~/.local/share/hallux/hpm/` (`store_home` in
  `hallux/hpm/store.py`). The user's store is `~/hpm-live`, so every new shell without
  `export HPM_HOME=~/hpm-live` sees an empty store: `hpm search` finds nothing, `hpm install`
  says "there is no package … in the store".
- **The editor:** `$VISUAL`, else `$EDITOR`, else the error "there is no $EDITOR to write
  the changelog entry in" (`Questions.edit` in `hallux/hpm/publish.py`).

A line in `~/.bashrc` fixes both in an interactive shell, but not where no shell reads it:
a Hallux started from a desktop shortcut or a VS Code task, whose Packages tab then looks at
the wrong store without a word. A file in the user's home is read however hpm starts.

## The file

`~/.config/hallux/hpm.toml`, always (decision 1). Found by the user's home, never by the
folder hpm runs in, so a world, the repo or any other folder all read the same file.

```toml
store  = "~/hpm-live"   # where the store is
editor = "nano"         # for changelog entries and manifests
color  = "auto"         # auto | always | never
```

Every key is optional. No file at all: the defaults, as today. `~` is the user's home;
a relative path is refused (it would depend on where hpm runs, the very thing to avoid).

## Who wins

A flag, then an environment variable, then the file, then the default (decision 2):

| Setting | In order |
|---|---|
| store | `HPM_HOME` → `store` → `~/.local/share/hallux/hpm` |
| editor | `HPM_EDITOR` → `editor` → `$VISUAL` → `$EDITOR` → `nano` if it is on the PATH, else `vi` |
| color | `HPM_COLOR` → `NO_COLOR`, `TERM=dumb` → `color` → on if a terminal |

So everything that works today keeps working: `HPM_HOME`, `$EDITOR`, `NO_COLOR` and
`HPM_COLOR` mean what they mean now. `hpm config` shows each setting and where it came
from, so a stray `HPM_HOME` in some shell is seen at once.

`HPM_CONFIG`, a path, reads that file instead (decision 6). It is for the tests, which must
never read the user's own file (`tests/conftest.py` sets it, as it sets `HPM_HOME`); the
docs mention it once, as the way to try another config.

## What stays where it is

- **The AI's settings** (`model`, `effort`, `cap_usd`, `base_world`) stay in the store's
  `config.toml` (decision 3): they belong to the store and move with it, and one place
  per setting keeps "which file wins?" from coming up.
- **Hallux's own settings** stay in each world's `.hallux/config.toml`: they are the
  machine's, not hpm's.

## Decisions of this plan

| # | Decision | Why |
|---|---|---|
| 1 | **Always `~/.config/hallux/hpm.toml`; `XDG_CONFIG_HOME` is not read** | The user's goal: the same file from anywhere. A shell that sets `XDG_CONFIG_HOME` and a shortcut that doesn't would read two files |
| 2 | **Flag, environment, file, default**, in that order | Nothing that works today changes; the environment stays the way to override once |
| 3 | **The AI's settings stay in the store's `config.toml`** | They belong to the store; one place per setting |
| 4 | **The editor falls back to `nano`, then `vi`**, instead of stopping | "there is no $EDITOR" never stops a publish again; git does the same with `vi` |
| 5 | **`hpm config set` writes the file**, keeping its comments and the other lines | No need to know where the file is or how TOML is written; the line-wise writer of `hallux/config.py` is the model |
| 6 | **`HPM_CONFIG` names another file**, for the tests | The tests must never read the user's file; one variable, like `HPM_HOME` |
| 7 | **A mistake in the file is an error that names the file and the key**; the file is never guessed around | As the store's `config.toml` already does (`ai.settings`) |
| 8 | **Run as root (`sudo hpm`), hpm says it reads root's file**, and goes on | Root's home is `/root`; hpm never needs root, so a note is enough |

## Later, if missed

A default `--user` for worlds with several users, and a default store for `hpm push`
(`--store`). Not in this plan: the file has room for them.
