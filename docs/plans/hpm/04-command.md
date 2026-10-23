# Step 4: the command in your terminal

[The plan](README.md) · the design: [hpm.md](../../hpm/hpm.md), sections 6, 6a, 7, 8 and 10;
plan decisions 11, 12, 14

**Needs:** step 3. **Changes:** `hallux/hpm/cli.py`, new `hallux/hpm/screens.py`;
`hallux/app.py` (the running mark); `tests/test_hpm_cli.py`, `tests/test_app.py`.

After this step hpm is usable: you publish by hand (step 2) and install, update, remove and
roll back from your terminal, with the screens of the design.

## Build

**The commands:**

| Command | What |
|---|---|
| `hpm install NAME… [--world W] [--extras K,K] [--overwrite all\|none] [--user U] [--yes]` | `NAME` is a package, `store/*` or a bundle |
| `hpm update [NAME…] [--world W]` | without a name: every package with a newer version |
| `hpm remove NAME [--data] [--world W]` | |
| `hpm list [--world W]` | installed, with the store's latest beside it; the backups and their size |
| `hpm rollback NAME [--world W]` | |
| `hpm search WORD` | names and summaries in the store |
| `hpm backups --clean [--world W]` | removes the backups, after a question |

**The screens** (`screens.py`, prompt_toolkit), each skipped when its flag answers it:

1. **The checkboxes** of hpm.md section 6 and 6a: one row per package, its extras folding
   open under it (`→`), needs ticked and unticked together, a row marked when an addon is
   missing, `v` showing the card and the memory line (and rules, in red) before installing.
2. **The user,** when the world has several.
3. **The conflicts:** the plan's questions, grouped; `o` / `s` / `k` on a row, `O` / `S` for
   all, Enter to go on.
4. **The progress,** package by package, and the end: `14 installed · 1 failed: …`, the
   backup's name.

Without a terminal (a pipe), a question without its flag is an error that names the flag.

**A running world** (decision 11). `hallux/app.py` writes `/.hallux/running` (its process
number) after `config.load`, and removes it when the run ends, also on a crash (`finally`).
`hpm install`, `update`, `remove` and `rollback` refuse a world whose mark names a process
that is alive: "this world is running: use the Packages tab (Ctrl+F12), or stop it". A mark
with a dead process is ignored and replaced at the next start. `list`, `show` and `publish`
work on a running world.

## Tests

- Each command with flags only, on temporary worlds: what was written, the record, the
  exit code.
- The screens with prompt_toolkit's pipe input: ticking, folding, needs, `v`, the conflict
  keys, cancelling with `q` (nothing written).
- A question without a terminal and without its flag is an error naming the flag.
- The running mark: written, removed at the end and after a crash in `machine.run`;
  hpm refuses a world with a live mark and accepts one with a dead mark.

## Done when

On a copy of `test-hallux` and one of `oliver-test`: `hpm install kittystory` with the
checkboxes, a conflict on a pack answered on the screen, `hpm list`, `hpm update` after a
new publish, `hpm rollback`, `hpm remove`. Checked on a pty through a terminal emulator, as
Hallux's other screens are, before I say it works.
