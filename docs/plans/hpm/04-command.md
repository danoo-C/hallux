# Step 4: the command in your terminal

[The plan](README.md) · the design: [hpm.md](../../hpm/hpm.md), sections 5, 6, 6a, 7, 7a, 8 and 10;
plan decisions 11, 12, 14

**Needs:** step 3. **Changes:** `hallux/hpm/cli.py`, new `hallux/hpm/screens.py`;
`hallux/app.py` (the running mark); `tests/test_hpm_cli.py`, `tests/test_app.py`.

After this step hpm is usable: you publish by hand (step 2) and install, update, remove,
adopt and roll back from your terminal, with the screens of the design.

## Build

**The commands:**

| Command | What |
|---|---|
| `hpm install NAME… [--world W] [--extras K,K] [--overwrite all\|none] [--user U] [--yes]` | `NAME` is a package, `store/name`, a whole store as `store/` (with the slash and nothing after it: `danika/*` would be expanded by bash wherever a folder `danika` is), or a bundle |
| `hpm update [NAME…] [--world W]` | without a name: every package with a newer version |
| `hpm remove NAME [--data] [--world W]` | |
| `hpm list [--world W]` | installed, with the store's latest beside it; the backups and their size |
| `hpm rollback NAME [--world W]` | |
| `hpm adopt NAME [--world W]` | step 3's `adopt`, for an app that was there before hpm (hpm.md section 7a) |
| `hpm search WORD` | names and summaries in the store |
| `hpm backups --clean [--world W]` | removes the backups, after a question |

**The screens** (`screens.py`, prompt_toolkit), each skipped when its flag answers it:

1. **The checkboxes** of hpm.md section 6 and 6a: one row per package, its extras folding
   open under it (`→`), needs ticked and unticked together, a row marked when an addon is
   missing, `v` showing the card and the memory line (and rules, in red) before installing,
   and the plan's loud marks (step 3) in red on their package's row. `+` ticks all, `-`
   none: the same keys as the Packages tab, where letters choose tabs.
2. **The user,** when the world has several.
3. **The old memory line,** when the world has an untagged one about the program: shown,
   with "replace it? [Y/n]".
4. **The conflicts:** the plan's questions, grouped; `o` / `s` / `k` on a row, `O` / `S` for
   all, Enter to go on.
5. **The progress,** package by package, and the end:
   `12 installed · 1 failed: … · 2 skipped: need …`, the backup's name.

Without a terminal (a pipe), a question without its flag is an error that names the flag.

**A running world** (decision 11). `hallux/app.py` writes `/.hallux/running` (its process
number and that process's start time, field 22 of `/proc/<pid>/stat`) after `config.load`,
before the headless and the interactive runs part, so `--script` and `--check` runs are
marked too. It removes it when the run ends, also on a crash (`finally`). A hard kill leaves
it, which is what the start time is for.
`hpm install`, `update`, `remove` and `rollback` refuse a world whose mark names a process
that is alive and started at the time the mark says: "this world is running: use the
Packages tab (Ctrl+F12), or stop it". A mark with a dead process, or with a number another
process has now, is ignored and replaced at the next start. `list`, `show`, `publish`,
`init` (step 6) and `adopt` work on a running world: they write only under
`/usr/local/share/hpm/<name>/` and the world's record.

**Publish adopts its own world** (hpm.md section 5): at its end, `hpm publish` calls step 3's
`adopt` with the release it just made, so `hpm list` in the dev world shows it and the next
update there knows its files.

## Tests

- Each command with flags only, on temporary worlds: what was written, the record, the
  exit code.
- The screens with prompt_toolkit's pipe input: ticking, folding, needs, `v`, the conflict
  keys, cancelling with `q` (nothing written).
- A question without a terminal and without its flag is an error naming the flag.
- The running mark: written (also for `--script`), removed at the end and after a crash in
  `machine.run`; hpm refuses a world with a live mark and accepts one with a dead mark and
  one whose number belongs to a process that started at another time.
- `danika/` expands to the store's packages; a name that isn't a package or a store is an
  error that names the forms.
- `hpm adopt`, and a publish that adopts its world: `hpm list` there shows the release.
- The old memory line's question: replaced on yes, kept on no, `--yes` replaces.

## Done when

On a copy of `test-hallux` and one of `oliver-test`: `hpm list` in the `test-hallux` copy
after its publish, `hpm install kittystory` with the checkboxes, a conflict on a pack answered on the screen, `hpm list`, `hpm update` after a
new publish, `hpm rollback`, `hpm remove`. Checked on a pty through a terminal emulator, as
Hallux's other screens are, before I say it works.
