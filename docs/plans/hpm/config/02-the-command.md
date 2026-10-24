# Step 2: `hpm config`, the hints, the docs

[The config plan](README.md) · [the hpm plan](../README.md) · built on [step 1](01-the-file.md)

**Changes:** `hallux/hpm/config.py` (`explain`, `set_value`), `hallux/hpm/cli.py` (the
`config` command, two hints), `docs/hpm/hpm.md`, `docs/hpm/tutorial.md` (section 3 and the
cheat sheet), `hallux/hpm/cli.py`'s usage text, `tests/test_hpm_config.py`.

## What to build

**1. Three commands.**

```
hpm config                      every setting, its value, and where it came from
hpm config set KEY VALUE        write one key into the file (made if it isn't there)
hpm config path                 where the file is
```

`hpm config` prints, for the user's case:

```
file    ~/.config/hallux/hpm.toml
store   ~/hpm-live                   from the file
editor  nano                         from the file
color   auto                         the default
```

and, when something else wins: `store  /tmp/x  from HPM_HOME (the file says ~/hpm-live)`.
The source is dim and a value from the environment cyan (the colors plan's `span`), so a
stray variable stands out.

**2. `set_value(path, key, value)`** checks the value as `load` would (a store must be an
existing folder, the color one of the three), then writes it line by line, as
`hallux/config.py`'s writer does for a world's `config.toml`: the key's line is changed in
place, or added at the end; comments and other lines stay; the file is written whole
(`write_whole`), so a crash leaves the old one. `~/.config/hallux/` is made if missing.
`hpm config set store ~/hpm-live` writes `store = "~/hpm-live"` (as typed, so the file reads
the same on another PC with the same layout) and says `✓ store = "~/hpm-live" in
~/.config/hallux/hpm.toml`.

An unknown key is refused with the list of keys. `hpm config set` doesn't remove a key;
deleting its line in the file does.

**3. Two hints where people get stuck.**
- A command that finds the store empty (`search`, `show`, `install`, `update`) and has
  neither `HPM_HOME` nor a `store` in the file adds: `note: the store at
  ~/.local/share/hallux/hpm is empty. If yours is elsewhere: hpm config set store PATH`.
- The editor error (step 1) names `hpm config set editor nano`.

**4. The docs.** `docs/hpm/hpm.md`: a short "Config" part in section 4 (the store) with the
file, its three keys and who wins; the "As built" bullet. `docs/hpm/tutorial.md`: section 3
("Once: setting it up") replaces `export HPM_HOME=…` and `export EDITOR=nano` with the two
`hpm config set` lines; the cheat sheet gets `hpm config`.

## Tests

- `hpm config` on no file, on a file, with `HPM_HOME` set: each line's value and source.
- `set_value`: a new file; a changed line keeps the comment above it and the other keys;
  an unknown key and a missing store folder are refused and write nothing.
- The empty-store hint: said with nothing configured; not said with `HPM_HOME` or a `store`
  in the file.

## Done when

- The tests pass, and the whole suite.
- By hand, with the user's go (it writes their real file): `hpm config set store ~/hpm-live`
  and `hpm config set editor nano`, then from a new terminal without `HPM_HOME`,
  `hpm config` says both come from the file, and `hpm search ""` lists the store from
  anywhere. Then the user starts Hallux the way they usually do, opens the Packages tab
  (Ctrl+F12, `g`) and sees the store's packages.
