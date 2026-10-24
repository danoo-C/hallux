# Step 3: lists, `show`, and the look on a real terminal

[The colors plan](README.md) · [the hpm plan](../README.md) · built on [step 2](02-every-line-its-kind.md)

**Changes:** `hallux/hpm/cli.py` (`list`, `search`, `store list`, `backups`),
`hallux/hpm/publish.py` (`show`), `docs/hpm/hpm.md` and `docs/hpm/tutorial.md` (a few
lines), `tests/test_hpm_paint.py`.

## What to build

Listings are plain lines, but a little color helps the eye find what to act on. Each
piece is painted where the line is put together, only when colors are on:

| Command | Highlight |
|---|---|
| `hpm list` | the package's name bold; `↑ 1.2 in the store` cyan (an update is there); `(incomplete)` red; `(adopted)` and `(from danika)` dim; `extras: …` as it is |
| `hpm search`, `hpm store list` | the name bold, the store (`danika/`) dim, the summary as it is |
| `hpm show` | the first line (name, version) bold; the headings (`versions:`, `extras:`, `app files:`, `changelog:`) bold; `private: hpm push never sends it` yellow; `rules (they change the whole machine):` bold red, as a loud line |
| `hpm backups` | the backup's name as it is, its packages bold, the size dim |
| init's `--- path` header over a manifest | dim; the manifest under it plain |

`show` returns its text (the tests read it); it gets an `on` argument, False by default,
and `cli` passes the switch.

**Docs:** `docs/hpm/hpm.md` gets one bullet in its "As built" section, and the tutorial's
"When something goes wrong" one line: what the colors mean (green worked, yellow look at
it, red failed), and that `NO_COLOR=1` turns them off and `HPM_COLOR=always` keeps them in a
pipe (`hpm list | less -R`).

## Tests

- `list` with a stand-in terminal: a package with a newer version in the store has the
  cyan `↑`; an incomplete one the red mark; stripped, the line is as today.
- `show(store, name, on=True)`: its headings bold, a rules line red; `on=False`, the text
  of today.

## Done when

- The tests pass, and the whole suite.
- **The look on a real terminal** (as every Hallux change that draws on a terminal is
  checked): in tmux on a copy of `test-kittystory` with a copy of the store, run `hpm list`,
  a `hpm update` after a rollback, a failing `hpm publish` (nothing changed), and `hpm show
  kittystory`. `tmux capture-pane -e` shows the codes where this plan puts them, and the
  screen reads on tmux's default colors. No paid run.
- **The user's look:** the same commands in Windows Terminal, with the user's own theme.
  Whether a color is wrong there (yellow on a light background, say) is the user's call;
  a color is one line of `paint.py` to change.
