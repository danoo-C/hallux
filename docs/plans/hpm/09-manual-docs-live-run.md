# Step 9: the manual, the docs and the live run

[The plan](README.md) · the design: [docs/hpm/](../../hpm/README.md)

**Needs:** steps 1 to 8. **Changes:** `hallux/prompt.md`; `docs/hpm/*.md` ("As built"
sections), `docs/concept.md` and `README.MD` (a few lines each); new
`docs/plans/hpm/live-run-checklist.md`.

## Build

**The manual** (`hallux/prompt.md`), a few lines where it speaks of memory:

- A line in memory ending in `[hpm <name> <version>]` was written by hpm: keep it as it is;
  write about the program on lines of your own.
- `<installed>` in front of a message says what hpm wrote since your last answer: read those
  files from the disk before you use them, never from what you remember of them.
- You don't install hpm packages and you don't write install files for them: if the user
  asks you to package a program, tell them about `hpm init` and `hpm publish`.

The user edits `prompt.md` too: I change only these lines, and show the diff.

**The docs:** each design document gets its "As built", with what the code did differently
from it; [hpm.md](../../hpm/hpm.md) gets a short "Using it" at the top; `README.MD` gets a
section on `hpm`; `docs/concept.md` one line where it speaks of the folder outside the
machine.

**The live-run checklist,** points to tick, with an "If not:" line under each, as for the web
addon:

1. `hpm init kittystory` in `test-hallux`; the manifest read and fixed.
2. `hpm publish kittystory --all`: four packages, memories private.
3. Install into a copy of `oliver-test` from your terminal: checkboxes, a conflict on a pack.
   `hpm list` in `test-hallux` shows what it published (the publish adopted it).
4. In that world: `kittystory -w` works, with Emma, Lucy and Emilly.
5. The same from the Packages tab of a running world (Ctrl+F12, `g`); the AI knows the app
   at once, and the Files tab's `p` still opens its path row.
6. A change by hand to a pack, then an update: asked about, not replaced.
7. kittystory 2.0 with a new character layout: the migration, accept, every memory line still
   there; then `hpm rollback`.
8. 15 packages at once from `danika/` (or as many as there are): one conflicts screen.
9. Your store on GitHub, `hpm push`, and an install into a third world from its URL.
10. `hpm remove kittystory`: the app gone, the data kept, the memory line gone.
11. `hpm adopt kittystory` in a world that got kittystory the old way (an `.update` file):
    the identical files recorded, the old memory line offered for replacing.

## Done when

The manual and the docs are written and committed; what is left is the user's live run.
