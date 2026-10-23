# Step 3: the install engine

[The plan](README.md) · the design: [hpm.md](../../hpm/hpm.md), sections 3, 6, 6a, 7, 7a, 8
and 9; [sharing.md](../../hpm/sharing.md), section 4; plan decisions 4 to 7

**Needs:** step 2. **Changes:** new `hallux/hpm/engine.py`, `record.py`;
`tests/test_hpm_engine.py`, `tests/test_hpm_record.py`.

After this step everything an install, an update, a remove or an adopt does works from
Python, with no screen: the command (step 4) and the Packages tab (step 5) only ask the
questions and call it. Data in an older format is refused here; migrating it is step 7.

## Build

**Two ways into a world.** What a package carries goes in through the world's `Disk`
(`Disk.place`, then `copy_whole`): inside the world's folder only, and never under
`/.hallux`, which the `Disk` refuses as if it didn't exist (`hallux/disk.py`, `_check`).
hpm's own files are written by `record.py` straight under `disk.hidden`
(`<world>/.hallux/hpm/`): `installed.json` with `write_whole`, the backups with
`copy_whole`. The memory line goes through `Disk.memory_edit`, the one way the `Disk` has
into `/.hallux`.

**The world's user:** `world_user(disk)`. First `/etc/passwd`, read through the Disk: the
users with a uid of 1000 or more and a home under `/home`. A world without one
(`hallux-world` has none) gives the folders under `/home` that aren't empty; an empty
`/home/user`, which every new world gets from `Disk.lay_skeleton`, doesn't count when
another home is there. One is the answer; several mean the caller must ask (`--user`); none
means `~` files can't be installed.

**`plan(world, wanted) -> Plan`.** `wanted` is a list of packages with the extras chosen for
each, or a store or bundle that expands into one (`danika/`, `kitty-desktop`). The plan:

1. **Expands** bundles and extras into packages, and orders them by their needs
   (`requires.packages`, `for`, an extra's package after its app). A circle is an error.
2. **Checks** what can be checked before writing: the world's addons (its `config.toml`
   `addons`, and the addons Hallux has: the names of the `*.py` files in
   `hallux.app.ADDONS_FOLDER`, without importing them) against `requires.addons`; the data
   format of what is installed (`installed.json`) against the package's: older in the world
   means "needs a migration" (step 7), newer means refused.
3. **Walks** every file of every package and marks it, the way drag and drop's tree marks
   what is in the way (`importing.look`; hpm doesn't call it, since it copies a drop from
   the PC into one folder):

| Mark | What is there | What happens |
|---|---|---|
| `new` | nothing | written; the folders it needs are made first |
| `same` | the same bytes | skipped |
| `ours` | a different file this package wrote, unchanged since (its sha256 is in the record) | `app`: replaced; `data`: kept (decision 7) |
| `changed` | a different file this package wrote, changed since | asked |
| `foreign` | a different file hpm didn't write | asked |
| `in-the-way` | a folder or a link where the file goes, or a file where a folder must be | asked: skip, or the package fails; never written through (`copy_whole` refuses it) |
| `seed-kept` | a `seed` file that is there | never touched |

4. **Marks what must be shown loudly** (sharing.md section 4), in hpm's code at the
   installer's end: rules; a file the machine reads at every boot (`BOOT_FILES` in
   `hallux/disk.py`, and any home's `.bashrc`); a card in `/usr/local/bin` that isn't the
   package's own. They are in `plan.loud`, for the screens.
5. **Finds the old memory line** (hpm.md section 7a): an untagged line under "Invented
   programs" that starts with the program's name is a question, "replace it with the tagged
   one?", default yes.

Each file the plan would overwrite without knowing it is `ours`, or remove, is a question in
`plan.questions`, grouped by package and by folder (hpm.md section 7: "3 packs are already
installed here"). An answer is `overwrite`, `skip` or `both` (written beside as
`name.hpm-new.ext`); `merge` comes in step 6.

**`apply(plan, answers, progress) -> Outcome`.**

1. **Backup** (decision 6) of every file that will be overwritten or removed, once for the
   whole plan, before anything else.
2. **Writes** package after package, each file with `copy_whole` from the unpacked package
   into `Disk.place` of its path. With the files, the package's manifest and its migration
   notes go to `/usr/local/share/hpm/<name>/` in this world too (hpm.md section 5).
3. **Records** each package in `installed.json` as soon as it is written: version, store,
   extras, data format, time, and each file's kind and sha256.
4. **One package that fails doesn't stop the others** (hpm.md section 6a), but every package
   that needs it (an extra of it, a package that requires it) is skipped, with why. The
   failed one's files that were written are in the record, marked `incomplete`, so a remove
   can take them away and a new install finish it. A full disk stops everything.
5. **The memory line:** under `## Invented programs` in `/.hallux/memory.md`, through
   `Disk.memory_edit`, ending in `[hpm <name> <version>]`. An older line with the same tag is
   replaced, and so is the untagged one if the answer was yes; without the section, it is
   added at the end with the section's title. Rules of a rules extra go under
   `## Rules (from \`hallux ...\`)`, each tagged the same way.
6. **The outcome:** per package installed, skipped or failed and why; the counts; the backup's
   name; and the notes for the machine's `<installed>` (step 5 tells it).

**`remove(world, name, data=False)`:** the `app` files of the record, if unchanged (a
changed one is asked about, as above), the memory line and rules; with `data`, the `data`
files too, after a backup. **`rollback(world, name)`:** the newest backup that holds the
package, and the record as it was.

**`adopt(world, release)`** (hpm.md section 7a): the release's files are compared with the
world's. The identical ones are recorded as the package's; the others stay out of the
record, so they are `foreign` to the next update and asked about. The old memory line is
offered for replacing, as at an install. Nothing else is written. Step 4 also calls it at the
end of a publish, for the world the release came from.

**Updates** are a plan with the newer version: the marks above do the rest. An `app` file
the old version had and the new one doesn't is removed if it is `ours`, asked about if
`changed`. A `data` file is never removed by an update (decision 7).

## Tests

All on worlds made in a temporary folder.

- The world's user: one, several, none; without `/etc/passwd`; an empty `/home/user` beside
  a real home; `~` placed under that home.
- Order: needs first, an extra after its app, a bundle and `danika/` expanded; circles
  refused.
- Addons missing (found by file name, none imported); a newer data format refused; an older
  one reported as needing migration.
- Every mark, and what happens to each; a folder and a link in the way; folders made; a seed
  kept; data never overwritten or removed by an update.
- The loud marks: a rules extra, a package that writes `~/.bashrc`, one that writes another
  program's card.
- The backup holds exactly the files overwritten, and a rollback brings them and the record
  back.
- 15 packages at once, one failing in the middle: the others installed, those that need it
  skipped, the failed one recorded as incomplete, and a second install finishes it.
- The memory line: added, replaced on update, removed on remove; an untagged line replaced
  when the answer is yes and kept when it is no; a memory without the section; the
  machine's own lines untouched.
- Adopt: identical files recorded, a changed one left foreign and asked about at the next
  update.
- The record, the backups and the manifest's copy: `installed.json` and the backups only
  under `.hallux/hpm/`, the manifest under `/usr/local/share/hpm/<name>/`.
- Nothing is ever written outside the world's folder (a package with a `~` path whose user
  has a home that links out of it is refused by the Disk), and nothing a package carries
  reaches `/.hallux`.

## Done when

kittystory with its packs and characters installs into a fresh copy of a world, updates to a
newer version with one file changed by hand (asked about, not replaced), and is removed again
with the data kept, all from a test; and a copy of `test-hallux`, whose kittystory was there
before hpm, is adopted from the release published from it.
