# Step 7: migrations

[The plan](README.md) · the design: [migrations.md](../../hpm/migrations.md); plan
decisions 6 to 8

**Needs:** step 6. **Changes:** new `hallux/hpm/migrate.py` (with `StagingDisk`), `hallux/hpm/prompts/{migrate,
write-migration}.md`; `hallux/hpm/engine.py`, `cli.py`, `hallux/panel_tabs/packages.py`;
`tests/test_hpm_migrate.py`.

After this step a package can change how its data is stored, and an update brings the data
along instead of leaving it behind.

## Build

**Notes:** `migrations/<from>-to-<to>.md` in the package, as migrations.md section 3 shows
one. hpm reads the "Old paths" line and the "Checks" list out of it; the rest is for the AI.
A package whose `data_format` is N must have every note from 1 to N that a world could need
(publish checks that the chain has no hole).

**`hpm update` with older data** (migrations.md section 4, with decision 8):

1. **Backup** of every file under the old and the new data paths (step 3's backup).
2. **Plan:** the AI reads the note and the world's files (read-only) and gives back the
   plan's rows (what becomes what). Shown; Enter goes on, `q` ends with nothing changed.
3. **Migrate:** the AI writes the new files into `/.hallux/hpm/staging/<time>/` (decision 8):
   the world is untouched. The world's `Disk` can't do that, since it refuses everything
   under `/.hallux`, so this is a disk of its own, `StagingDisk`, built the way
   `hallux/jobdisk.py` keeps a job's private copies. The AI uses world paths
   (`~/.kittystory/characters/emma.toml`), and the file lands at
   `staging/<time>/home/<user>/.kittystory/characters/emma.toml`. A read takes the staged
   file if there is one and the world's otherwise; a write goes only to the staging folder,
   and only under the package's data paths. Its tools (decision 9) are the read-only ones,
   `write_file`, and **`copy(from, to)`**: Hallux's code copies the bytes into the staging
   folder with `copy_whole`, so a memory or a chat history is never typed out again by the
   model.
4. **Check:** Hallux's code: every path the plan named is in the staging folder, the
   world's old files are as they were at the backup, and every file made with `copy` is
   still its source byte for byte. Then the AI checks the note's own
   list against the staging folder and the old files, and reports each check.
5. **You decide:** Enter accepts: the staging folder lands in the world (`copy_whole` file by
   file), the old paths are removed, the record says the new format, and only then the new
   app files are installed as in any update. `r`: the staging folder is deleted, nothing
   else happened. `l`: the staged files, to look at first.

Several notes in a row (1 → 2 → 3) run one after the other, each staged on top of the last,
and are accepted together at the end. With 15 packages at once (hpm.md section 6a), each
package's migration has its own plan screen and its own accept.

**Incoming data in an old format** (migrations.md section 2): a data package in format 1
installed beside its app in format 2. The notes come from the app, not from the data
package: the world's copy in `/usr/local/share/hpm/<app>/migrations/`, else the app's
release in the store. The data package is unpacked into a temporary folder laid out as a
world (`files/root/` at `/`, `files/home/` at `/home/<user>/`), so the note's paths mean what
they say there; it is migrated there by the same steps, with a `StagingDisk` over that
folder, and installed from the result.

**`hpm publish`** (step 2's stop when data paths moved) now offers the `write-migration`
job: the AI gets the last release (the old layout) and the world (the new one), writes the
note into `/usr/local/share/hpm/<name>/migrations/`, and publish says the note never ran on
real data and offers the test install (migrations.md section 7).

**In the Packages tab:** the plan, the checks and the accept on the tab, as in the terminal:
Enter accepts, `r` rolls back, `l` looks (no tab letter among them).

## Tests

With a stand-in AI that follows a fixed note.

- Formats: same, older (one step, two steps), newer refused, a hole in the chain refused at
  publish.
- The staging disk writes only into its folder, and only under the data paths; a read of a
  staged path gives the staged file; the world untouched until accept.
- `copy`: the bytes are the source's, for a big memory file whose content the stand-in AI
  never reads: it only says what goes where.
- Incoming data: the note taken from the app; the package's files seen at their world paths.
- Accept: landed, old paths removed, the record's format, then the app files.
- Roll back after accept (`hpm rollback`): the old layout and the old version back.
- `q` at the plan and `r` at the end: nothing in the world changed, no staging left.
- A check that fails is shown, and accept still asks.
- Incoming data migrated before install.

## Done when

kittystory 2.0, with characters in the new layout of migrations.md section 1 and its note,
updates a copy of `test-hallux` in format 1: Emma, Lucy and Emilly come through with every
memory line, and a rollback brings back 1.x as it was. One paid run, after the user says go.
