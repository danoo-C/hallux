# Step 3: the install engine

[The plan](README.md) · the design: [hpm.md](../../hpm/hpm.md), sections 3, 6, 6a, 7, 8 and
9; plan decisions 4 to 7

**Needs:** step 2. **Changes:** new `hallux/hpm/engine.py`, `record.py`;
`tests/test_hpm_engine.py`, `tests/test_hpm_record.py`.

After this step everything an install, an update or a remove does works from Python, with
no screen: the command (step 4) and the Packages tab (step 5) only ask the questions and
call it. Data in an older format is refused here; migrating it is step 7.

## Build

**The world's user:** `world_user(disk)` reads `/etc/passwd` through the Disk; the users
with a uid of 1000 or more and a home under `/home`. One is the answer; several mean the
caller must ask; none means `~` files can't be installed.

**`plan(world, wanted) -> Plan`.** `wanted` is a list of packages with the extras chosen for
each, or a store or bundle that expands into one (`danika/*`, `kitty-desktop`). The plan:

1. **Expands** bundles and extras into packages, and orders them by their needs
   (`requires.packages`, `for`, an extra's package after its app). A circle is an error.
2. **Checks** what can be checked before writing: the world's addons (its `config.toml`
   `addons`, and the addons Hallux has, `addons.load`'s list) against `requires.addons`;
   the data format of what is installed (`installed.json`) against the package's: older in
   the world means "needs a migration" (step 7), newer means refused.
3. **Walks** every file of every package and marks it, as drag and drop's tree marks what
   is in the way (`importing.look`):

| Mark | What is there | What happens |
|---|---|---|
| `new` | nothing | written |
| `same` | the same bytes | skipped |
| `ours` | a different file this package wrote, unchanged since (its sha256 is in the record) | `app`: replaced; `data`: kept (decision 7) |
| `changed` | a different file this package wrote, changed since | asked |
| `foreign` | a different file hpm didn't write | asked |
| `seed-kept` | a `seed` file that is there | never touched |

Each file the plan would overwrite or remove is a question in `plan.questions`, grouped by
package and by folder (hpm.md section 7: "3 packs are already installed here"). An answer
is `overwrite`, `skip` or `both` (written beside as `name.hpm-new.ext`); `merge` comes in
step 6.

**`apply(plan, answers, progress) -> Outcome`.**

1. **Backup** (decision 6) of every file that will be overwritten or removed, once for the
   whole plan, before anything else.
2. **Writes** package after package, each file with `copy_whole` from the unpacked package
   into `Disk.place` of its path (so nothing outside the world and nothing in `/.hallux`).
3. **Records** each package in `installed.json` as soon as it is written: version, store,
   extras, data format, time, and each file's kind and sha256.
4. **One package that fails doesn't stop the others** (hpm.md section 6a): its files that
   were written are in the record, marked `incomplete`, so a remove can take them away and a
   new install finish it. A full disk stops everything.
5. **The memory line:** under `## Invented programs` in `/.hallux/memory.md`, through
   `Disk.memory_edit`, ending in `[hpm <name> <version>]`. An older line with the same tag is
   replaced; without the section, it is added at the end with the section's title. Rules of
   a rules extra go under `## Rules (from \`hallux ...\`)`, each tagged the same way.
6. **The outcome:** per package installed, skipped or failed and why; the counts; the backup's
   name; and a `Note` for the machine (step 5 tells it).

**`remove(world, name, data=False)`:** the `app` files of the record, if unchanged (a
changed one is asked about, as above), the memory line and rules; with `data`, the `data`
files too, after a backup. **`rollback(world, name)`:** the newest backup that holds the
package, and the record as it was.

**Updates** are a plan with the newer version: the marks above do the rest. A file the old
version had and the new one doesn't is removed if it is `ours`, asked about if `changed`.

## Tests

All on worlds made in a temporary folder.

- The world's user: one, several, none; `~` placed under that home.
- Order: needs first, an extra after its app, a bundle expanded; circles refused.
- Addons missing; a newer data format refused; an older one reported as needing migration.
- Every mark, and what happens to each; a seed kept; data never overwritten by an update.
- The backup holds exactly the files overwritten, and a rollback brings them and the record
  back.
- 15 packages at once, one failing in the middle: 14 installed, the failed one recorded as
  incomplete, and a second install finishes it.
- The memory line: added, replaced on update, removed on remove; a memory without the
  section; the machine's own lines untouched.
- Nothing is ever written outside the world's folder (a package with a `~` path whose user
  has a home that links out of it is refused by the Disk).

## Done when

kittystory with its packs and characters installs into a fresh copy of a world, updates to a
newer version with one file changed by hand (asked about, not replaced), and is removed again
with the data kept, all from a test.
