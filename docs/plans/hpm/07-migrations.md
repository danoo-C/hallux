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

## As built

Built 2026-10-23, **without the paid run** (it waits for the user's go):
`hallux/hpm/migrate.py` (the notes, `StagingDisk`, one package's `Migration`, the note at
publish), `hallux/hpm/prompts/{migrate,write-migration}.md`; the engine (a package can
wait for a migration, `rewalk`, a backup that grows), `record.py` (`extend_backup`,
`drop_from_backup`), `ai.py` (a job's own disk, the `copy` tool, a job without
`write_file`), `assist.py` (the note writer, the test install's migrations), `cli.py`,
`publish.py`, `running.py` and the Packages tab; `tests/test_hpm_migrate.py` (28 tests).
Four tests of steps 2 and 3 now expect step 7's rules (a note needs an "Old paths" line; a
new format needs its note). The whole suite: 2274 passed with the sandbox test left out as
before; two web addon tests fail now and then, on their own too
(`test_the_manuals_example_works_as_it_says` failed once in four runs alone; it waits
20 ms at a time for a Qt page), and step 7 changes nothing of the web addon.

**Checked on a real terminal** (tmux, 80 and 100 columns): Hallux on a fresh copy of the
step 5 world (`test-hallux` with kittystory 1.1 and the packs), a kittystory 2.0 built
from 1.1 with the layout of migrations.md section 1 and its note, the machine on the tests'
pretend model and hpm's AI a stand-in that follows the note on the real files. Ctrl+F12,
`g`, `u`, space, Enter: "its data migrates 1 → 2 first, with the AI"; Enter: the wait
before the AI starts; Enter: the plan (Emma, Lucy, emilly); Enter: the checks, 6 of 6;
`l`: the staged files; Enter: accepted and written. Emma, Lucy and Emilly came through,
each `memories/<name>.md` byte for byte the original `memory.md`, `chars/` gone, no staging
folder left, and the machine's next message had `"data_migrated": {"from": 1, "to": 2,
"gone": ["~/.kittystory/chars/"], "into": [...]}`. Then `hpm rollback kittystory` in the
terminal: `~/.kittystory` as it was (`diff -r`), the 1.1 card back. Long lines were cut at
the tab's edge on the first try; they are folded now.

**The paid run, still to do** (after the user says go): the same update, with the AI
following the note itself, on a copy of `test-hallux`; Emma, Lucy and Emilly with every
memory line, a rollback to 1.x as it was, and the cost noted here. The pieces for it are in
the session's scratchpad (`run7/setup.py` builds the 2.0); a run with the model needs
`fake_hallux.py` without its stand-in for hpm's AI.

What the code does that the step above didn't say, or says differently:

- **One backup for an update and its migrations.** The first migration takes it (every
  file under the old and the new data paths, and the record's entry as it was); the next
  ones and the install after them add to it, and a path or an entry it has already stays
  as it was then. So `hpm rollback kittystory` brings back the 1.x data and 1.x together,
  as migrations.md section 5 wants. A cancelled migration takes its package out of the
  backup again, and a backup left with nothing is removed.
- **The order.** Data coming in is migrated first (in the plan's temporary folder, nothing
  in the world), then every question of the install is asked, then the world's data is
  migrated, and only then is anything installed. So you answer everything before the AI
  starts, and nothing is installed over data in the old format. A migrated package is
  walked again, and a question that brings is asked then. Cancelling there says that the
  data is migrated, and how to go on (`hpm update`) or back (`hpm rollback`); the tab
  doesn't let Esc go back there at all.
- **A package whose migration doesn't land is skipped, not failed:** q at the plan, r at
  the end, a failed session, or `--accept-migration` with a check that didn't hold. What
  needs it is skipped too. Nothing of it was written.
- **Without a terminal:** `--accept-migration` lets the AI run and accepts only if every
  check held; without it hpm stops before anything is written and names the flag. On a
  terminal hpm asks first (the model and the cap), then shows the plan (Enter, q) and the
  checks (Enter, r, l).
- **The AI's two parts are two sessions per note,** the plan (no `write_file`, no `copy`)
  and the migration, each with the cap of the store's `config.toml`. Each must end with JSON
  (`{"rows": …}`, `{"checks": …}`); an answer without it is shown to the AI once more, then
  the migration fails. A row whose new path is outside the data paths is a problem too.
- **The staging disk** reads `~/…` as the user's home, as the notes write paths, refuses
  every write outside the new layout's data paths (and anything the world's Disk refuses),
  and holds at most 10,000 files and 512 MB. `copy` copies a staged file or the world's;
  Hallux's check compares each copy with its source at the end.
- **Hallux's checks:** every file the plan named is staged; the world's files under the
  old and new data paths are as the backup has them (none new, none changed, none gone);
  every copy is its source byte for byte. Then the note's checks as the AI reports them; a
  check it didn't report counts as not held.
- **At accept** the staged files land, the files under the old paths go (not one another
  package's record holds: those stay, and the checks screen says so), the record's entry
  gets the new files and the new format. With several notes, a file staged by one note
  under a later note's old paths was a step on the way and doesn't land.
- **The machine is told** in `<installed>`: `"data_migrated": {"from", "to", "gone",
  "into"}` beside the package, so its AI knows where the characters are now. (Step 9 puts a
  line about it into `prompt.md`.)
- **Incoming data** takes the notes of the app coming in the same plan, else the world's
  copy (`/usr/local/share/hpm/<app>/migrations/`), else the app's release in the store; the
  new layout is that app's manifest. After accept the data package is made again from its
  migrated folder, its manifest given the app's data patterns and the new format, and walked
  again. Its own `hpm.toml` in `/usr/local/share/hpm/<name>/` is the one it was published
  with (format 1): the record has the format.
- **A note** must have the line `Old paths…:` (its value may be `none`); each old path is
  a machine path or pattern, not `~/` or `/` themselves, not a whole top folder (`/usr`),
  nothing under `/.hallux`. "Checks:" is the list under that line. Its name is
  `<from>-to-<to>.md`; a note may skip formats (`1-to-3.md`), and the chain takes the one
  that goes furthest.
- **Publish** refuses a hole: for the format of every earlier release in the store, the
  notes must lead to the new one. When the data moved without a new format, or the format
  went up without the note, publish offers the `write-migration` job (`--write-migration`
  without a terminal): the AI reads the last release laid out as a world and the world,
  writes `/usr/local/share/hpm/<name>/migrations/<old>-to-<new>.md`, hpm checks the note
  (once back to the AI if it doesn't read), raises `data_format` in the world's manifest if
  it has to, and says the note never ran on real data. The test install (`--test`) runs a
  migration on its copy and accepts it whatever the checks say (the copy goes after),
  showing the plan and the checks.
- **The Packages tab** waits three times for each migration, as the terminal: Enter lets
  the AI start (q leaves the package out), Enter migrates after the plan (q cancels),
  Enter accepts after the checks (r rolls back, l shows the staged files, ↑ ↓ scroll).
  Esc cancels the migration on the screen; while the AI works it cancels once its step is
  done. The tab counts as typing there, so no letter is a tab's.

**Not built:** `--force` for an older app on newer data (migrations.md, decision 2). No step
of the plan names it; a world with newer data is refused, as the step's tests say.
