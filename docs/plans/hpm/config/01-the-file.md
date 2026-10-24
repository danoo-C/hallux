# Step 1: the file, read on every start

[The config plan](README.md) · [the hpm plan](../README.md)

**Changes:** `hallux/hpm/config.py` (new), `hallux/hpm/store.py` (`store_home`),
`hallux/hpm/publish.py` (`Questions.edit`), `hallux/hpm/paint.py` (`enabled`),
`tests/conftest.py` (`HPM_CONFIG`), `tests/test_hpm_config.py` (new).

## What to build

**1. `hallux/hpm/config.py`.**

```python
KEYS = {"store", "editor", "color"}

def config_path(env=None) -> Path:
    """HPM_CONFIG if set, else ~/.config/hallux/hpm.toml. Never XDG_CONFIG_HOME
    (decision 1), never the folder hpm runs in."""

@dataclass(frozen=True)
class Config:
    path: Path
    store: Path | None = None        # "~" expanded; absolute
    editor: str | None = None
    color: str | None = None         # "auto", "always" or "never"

def load(env=None) -> Config:
    """The file, checked. No file: an empty Config. An unknown key, a wrong type, a
    relative store, a color that isn't auto|always|never, or broken TOML: an HpmError that
    names the file and the key (decision 7)."""
```

- Read once per process: `load()` keeps what it read (an `functools.cache` keyed on the
  path), so `Store()`, `Questions()` and `paint` don't read the file three times.
- `config.py` imports only `tomllib`, `pathlib` and `hallux.hpm.world.HpmError`, so
  `store.py` and `paint.py` can use it without import loops.
- Run as root (`os.geteuid() == 0`), `load` notes once on stderr: "hpm runs as root, so it
  reads /root/.config/hallux/hpm.toml, not yours" (decision 8).

**2. The store.** `store_home(env)` becomes: `HPM_HOME`, else the file's `store`, else
`$XDG_DATA_HOME/hallux/hpm`, else `~/.local/share/hallux/hpm`. (`XDG_DATA_HOME` stays as
today for the default; only the config file's own place ignores `XDG_CONFIG_HOME`.) A
`store` that names a folder that doesn't exist is an error that names the file: hpm doesn't
make a store where a typo points. `Store()` everywhere (the command, the Packages tab's
`Installs`) gets it through `store_home`, so nothing else changes.

**3. The editor.** `Questions.edit` takes the editor from `editor_command(env)` in
`config.py`: `HPM_EDITOR`, the file's `editor`, `$VISUAL`, `$EDITOR`, then `nano` if
`shutil.which("nano")`, else `vi` (decision 4). The error "there is no $EDITOR …" stays only
for a machine with none of them, and names `hpm config set editor nano`.

**4. The colors.** `paint.enabled(stream, env)`: `HPM_COLOR` first, then `NO_COLOR` and
`TERM=dumb` as now, then the file's `color` (`always` or `never`; `auto` goes on), then the
terminal check.

**5. The tests stay away from the user's file.** `tests/conftest.py` sets `HPM_CONFIG` to a
path in the temp folder that doesn't exist, next to the `HPM_HOME` it sets already. The
config tests write their own files and pass `env`.

## Tests (`tests/test_hpm_config.py`)

- `config_path`: `HPM_CONFIG` wins; else `~/.config/hallux/hpm.toml` with a `HOME` given;
  `XDG_CONFIG_HOME` set changes nothing.
- `load`: no file is an empty Config; the three keys read; `~` expanded; each mistake an
  error naming the file and the key (an unknown key, `store = 3`, `store = "rel/path"`,
  `color = "blue"`, broken TOML).
- **From anywhere** (the user's goal): with `HOME` and `HPM_CONFIG` unset but the file in a
  temporary home, `store_home` gives the file's store when the working folder is a world,
  the repo, and `/`.
- `store_home`: `HPM_HOME` beats the file; the file beats the default; a store that
  doesn't exist is an error.
- `editor_command`: each step of the order, with `shutil.which` stood in for.
- `paint.enabled`: the file's `never` turns a terminal off; `HPM_COLOR=always` beats it.
- Run as root (`os.geteuid` stood in for): the note, once.

## Done when

- The tests pass, and the whole suite (`--deselect tests/test_sandbox.py`); nothing in the
  existing tests changes, since `HPM_CONFIG` points at no file.
- By hand, free: with `~/.config/hallux/hpm.toml` holding `store = "~/hpm-live"` and no
  `HPM_HOME`, `hpm search ""` lists the six kittystory packages from `/`, from a world and
  from the repo. That is the user's real file, so it is written only with the user's go;
  otherwise the same with `HPM_CONFIG` and a copy.

## As built

- `hallux/hpm/config.py`: `config_path`, `home_of` (`HOME` from the given environment, so
  the tests can give one), `expand`, `load` (read again only when the file's stamp
  changes), `check` (every problem at once), `store_from_file`, `editor_command` (returns
  the editor and where it came from, for step 2's `hpm config`), `file_color`. `set_value`,
  step 2's writer, is in the module already; its tests come with step 2.
- `store_home` uses `home_of` for the default too, so a given `HOME` is honored throughout.
- **Two places a wrong file could have crashed, found while building:** `main` built `Run`
  (and with it `Store()` and `Questions()`) before its `try`, so a broken file would have
  been a traceback; it is inside the `try` now. And `machine.py` makes the Packages tab's
  `Installs` at boot: its store is now made on first use (a property), so a wrong file is
  the tab's "The store can't be read: …" and never stops a world from booting.
- `paint.enabled` reads the file through `file_color`, which never raises: colors never stop
  hpm; the store's lookup tells the error.
- `tests/conftest.py` sets `HPM_CONFIG` to a path with no file.
- Tests: `tests/test_hpm_config.py`, 18 (the file's place, `XDG_CONFIG_HOME` ignored, the
  keys, each mistake, re-reading, the store's order, a missing store folder, **the store
  found from a world, the repo and `/` in a new process with only `HOME`**, a wrong file as
  an error not a traceback, the tab booting with a wrong file, the editor's order, the
  file's color, root told once). Whole suite: 2385 passed.
- By hand, with `HPM_CONFIG` pointing at a file in the scratch folder and a copy of the
  store, no `HPM_HOME`: `hpm search ""` listed the 6 packages from `/`, from `danika` and
  from the repo. The user's real `~/.config/hallux/hpm.toml` was not written.
