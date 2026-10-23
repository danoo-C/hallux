# Migrations: when an app changes how it stores its data

**Status:** design declared done by the user 2026-10-23. No code; the plan is in
[docs/plans/hpm/](../plans/hpm/README.md), step 7. Every question is decided, all as
recommended ([Decisions](#decisions)). It builds on [hpm.md](hpm.md), whose three kinds of
files (`app`, `seed`, `data`) it takes as given. Changed after the review of 2026-10-23
([docs/hpm-review-2026-10-23.md](../hpm-review-2026-10-23.md), taken as recommended): the
example follows kittystory's real files; the AI writes into a staging folder, not into the
world (the plan's decision 8); copies are made by Hallux, not typed out by the AI; incoming
data takes its note from the app.

**Where it came from:** the user: "lets say i do a drastic change on how kittystory stores
characters. if you update then you loose all the characters. how do we work around that?"
and "i think the AI should be involved."

## In short

1. **An update never deletes or overwrites data.** It may replace `app` files; `data` is
   only changed by a migration, and only after a backup.
2. **Each package has a data format, a number.** When the way an app stores its data
   changes, the number goes up.
3. **The AI that makes the change writes the migration**, a short note of the old layout,
   the new one and how to get from one to the other. It knows both, and it migrates your
   own data with the same note first.
4. **The AI runs the migration in the other world; Hallux's code guards it.** Backup
   first, a plan you see before anything is written, the new files written to one side,
   checks after, and nothing in the world changed until you accept.
5. **`hpm rollback` brings back the data and the old version together.**

---

## 1. The problem

Say kittystory 2.0 stores characters differently:

```
1.x:  ~/.kittystory/chars/<Name>/char.md, memory.md
2.0:  ~/.kittystory/characters/<name>.toml          (name, pack, notes)
      ~/.kittystory/memories/<name>.md
```

The 2.0 card reads `characters/`. A world that updates the app but keeps its data in
`chars/` now has no characters as far as the app can tell. A careless update that removed
the old files would lose them for good.

## 2. Data formats

Every package with data, and every app whose data that is, has `data_format` in its
manifest, a whole number. The world's record (`/.hallux/hpm/installed.json`, hpm.md
section 8) remembers the format the world's data is in.

| The world has | The package brings | What happens |
|---|---|---|
| format 2 | format 2 | a normal update |
| format 1 | format 2 | migrate 1 → 2 first (section 4) |
| format 1 | format 3 | migrate 1 → 2, then 2 → 3, in that order |
| format 3 | format 2 | refused: an older app on newer data. `--force` only with a backup |

A data package (like `kittystory-chars`) has a format too. If someone installs
`kittystory-chars` in format 1 next to kittystory in format 2, the incoming characters are
migrated to 2 before they are copied in:

- **The note comes from the app,** not from the data package: kittystory 2.0's
  `migrations/1-to-2.md`, from the world's copy of it (`/usr/local/share/hpm/kittystory/`)
  or from the release in the store. The data package in format 1 has no note of its own.
- **The incoming files are laid out as a world first.** A package holds `files/root/…` and
  `files/home/…`; the note speaks of `~/.kittystory/chars/`. So the files are unpacked into
  a temporary folder in which `files/home/` is at `/home/<user>/`, migrated there by the
  steps of section 4, and installed from it.

## 3. Writing a migration

A migration is a note in the package, `migrations/1-to-2.md`, for the AI to follow:

```markdown
# kittystory data format 1 → 2

Before: ~/.kittystory/chars/<Name>/{char.md, memory.md}
After:  ~/.kittystory/characters/<name>.toml   name, pack, notes
        ~/.kittystory/memories/<name>.md       memory.md, unchanged

Steps:
1. For each folder in chars/: read char.md, write characters/<name>.toml
   (the name in lowercase, the folder's name kept in `name`).
2. Copy memory.md to memories/<name>.md (with the copy tool: byte for byte).
3. shared.md, scene.md and assets/ stay where they are.

Checks:
- every folder in chars/ has a characters/<name>.toml
- every memories/<name>.md is the chars/<Name>/memory.md it came from, byte for byte
- no characters/*.toml without a folder it came from

Old paths, removed once the user accepts: ~/.kittystory/chars/
```

**Who writes it, and when.** The AI that redesigns the storage, at the time it does. In
your own world it has to migrate your characters anyway, so it writes the note first and
then follows it. The note gets tested on real data before anyone else runs it. It is saved
beside the manifest, `/usr/local/share/hpm/kittystory/migrations/1-to-2.md`.

**If you forget.** `hpm publish` compares the paths of the `data` files with the last
release. If they changed and `data_format` didn't, or there is no note for the step,
publish stops: "the data moved from ~/.kittystory/chars/ to ~/.kittystory/characters/;
write a migration?" On yes, the AI writes the note from the last release in the store (the
old layout) and the world (the new one).

**Why a note and not a script.** Hallux runs no programs: a Python script on the machine
is imagined, not run. A note the AI follows is the way a Hallux machine already does
things, as `kittystory-web.update` shows. And the AI copes with what a script trips on: a
character you edited by hand, a file that is missing, a name with a space.

## 4. Running a migration

When `hpm update kittystory` finds the world's data in format 1:

1. **Backup (Hallux's code).** Everything under the old and the new data paths is copied
   to `/.hallux/hpm/backups/kittystory-2026-10-23T14-02/`, with the world's record as it
   was. The machine's AI can't see or change that folder.
2. **Plan (the AI, writing nothing).** It reads the note and the world's files, and says
   what it will do:
   ```
   kittystory data 1 → 2

     Emma     chars/Emma/     → characters/emma.toml · memories/emma.md
     Lucy     chars/Lucy/     → characters/lucy.toml · memories/lucy.md
     Emilly   chars/emilly/   → characters/emilly.toml · memories/emilly.md

     Enter migrate · q cancel (nothing changes)
   ```
3. **Migrate (the AI), into a staging folder.** The AI writes the new files by their world
   paths, but they land in `/.hallux/hpm/staging/<time>/`, not in the world. It reads the
   world as it is, and a file it has written it reads back from the staging folder. It has
   a `copy` tool for files that move unchanged: Hallux copies the bytes, so a memory is
   never typed out again by the model, which would cost tokens and could change it. The
   session gets no delete, and writes only under the package's data paths.
4. **Check.** Hallux's code checks what it can without understanding: the world's old
   files are as they were at the backup, every new path the plan named is in the staging
   folder, and what was copied with `copy` is its source byte for byte. The AI then goes
   through the note's own checks and reports each.
5. **You decide.**
   ```
   ✓ 3 characters, 3 memories · all 3 checks held

     Enter accept (the old chars/ goes, the backup stays) · r roll back · l look first
   ```
   On accept, Hallux's code moves the staged files into the world, removes the old paths,
   and the world's record says format 2. Then the app files of 2.0 are installed as in any
   update. On roll back, the staging folder is deleted: the world was never touched, and
   nothing of 2.0 is installed.

The migration comes before the new app files, so the world is never left with a 2.0 card
and 1.x data. Several notes in a row (1 → 2 → 3) are staged one on top of the other and
accepted together.

## 5. Rollback

`hpm rollback kittystory` puts back the newest backup and the release that was installed
before it, from the store. Backups stay until you remove them (`hpm backups --clean`), and
`hpm list` shows how much room they take.

## 6. What it costs

A migration is one session of the AI (hpm.md, section 11): the plan and the writes,
seconds to a minute, with the cap of the store's `config.toml`. What moves unchanged is
copied by Hallux, so a big memory costs no more than a small one. Updates without a change
of format need no AI and cost nothing.

## 7. What can still go wrong

- **The checks can't prove the meaning survived.** They count characters and compare
  copies. They can't tell if the AI left a detail out of a `.toml` it wrote. That's why
  nothing changes until you accept, and the backup stays after.
- **A migration that never ran on your own data.** If the AI writes the note at publish
  time (section 3, "If you forget"), it was never tried. Publish says so, and offers the
  test install of hpm.md, section 5.
- **Data the app keeps outside its data paths.** If kittystory starts writing somewhere the
  manifest doesn't list, neither the backup nor the migration knows of it. Publish warns
  about files the card mentions that no pattern of the manifest covers.

## Decisions

All decided as recommended (the user, 2026-10-23: "i read trogh the questions and go all
recommended").

| Question | Decision |
|---|---|
| 1. Should a migration have an exact form (a list of moves) Hallux can run without the AI, for simple cases? | Not at first. Notes for everything; a "moves" form later, if many migrations turn out to be plain renames |
| 2. May an older app run on newer data with `--force`? | Yes, with a backup first and a warning that the app may not see all of it |
| 3. How long do backups stay? | Until you remove them; `hpm list` shows their size |
| 4. Does "accept" have a time limit, so the old files don't stay forever? | No. The old paths stay until you accept or roll back; `hpm list` reminds you |
| 5. Where does the AI write a migration's new files? (the plan's decision 8, confirmed 2026-10-23) | Into a staging folder under `/.hallux/hpm/staging/`; Hallux's code lands them when you accept |
