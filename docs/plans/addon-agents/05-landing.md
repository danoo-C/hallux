# Step 5: the landing

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), sections 5
and 10

**Needs:** step 4. **Changes:** `hallux/jobdisk.py`, `tests/test_jobdisk.py`.

A job's work lands when the job ends well: its copies are put into the folder. Until then
the main agent and the user can do anything to the real files, so Hallux looks before it
writes. This step is the one place where a job changes the user's disk.

## Build

**`land()`** returns what landed: the paths, and the conflicts if there were any. It raises
when the folder is gone.

1. **The folder, again.** Hallux resolves it through the jail once more. If it isn't there,
   or isn't the same place as when the job started, nothing lands.
2. **Each file the job wrote is compared** with the folder as it is now:

   | The job's file | A conflict when |
   |---|---|
   | A given file it changed | The real file holds something else than at the start, or is gone |
   | A file it created | A file of that name exists now |

3. **Every place is checked before anything is written.** Each file's place goes through
   the fence once more: its folder is still there, still inside the job's folder, and not a
   link that leads out. A job may write into subfolders that exist, and one of them can be
   gone or replaced by now. If any place fails, nothing lands, as when the folder is gone.
4. **No conflict:** every file takes its place. Each is written through the whole-file write
   of step 1, as bytes, so each lands in one step and nothing is changed on the way.
5. **Any conflict:** nothing takes its place. Every file of the job lands beside it, with
   `.new` added to its name. If that name is taken, it is `.new.2`, then `.new.3`, and so on.
6. **The copies are deleted.**

The whole landing holds the disk's lock (step 4), so an addon function in its thread can't
write between two of these points.

- **A given file the job never wrote** isn't touched, and isn't in the list.
- **A job that wrote nothing** lands nothing, and its list is empty.
- **The order** is the order of the names, so a test can say what a crash in the middle
  leaves.
- **What isn't promised:** that a set of files lands in one step. Each file does. If Hallux
  crashes between two of them, part of the set is in place. `sweep` (step 4) deletes the
  rest at the next start and names it in the log.

**What `Jobs` gets back,** for the event (step 7):

| The landing | In the event |
|---|---|
| Clean | `files`: the paths that were written |
| With a conflict | `conflict`: the files that were in the way; `files`: the `.new` paths |
| The folder is gone, or a place in it isn't what it was | The job ends as `failed`, with `why: folder` |

**`written()`** says how many files the job has written so far. A job that is killed lands
nothing, and its event carries that number.

## Tests

In `tests/test_jobdisk.py`:

- a new file and a changed one land: the folder has both, and `.hallux/jobs` is empty;
- a given file that wasn't written keeps its time of change;
- the real file was changed meanwhile: nothing is replaced, and the job's version is beside
  it as `.new`;
- the real file was deleted meanwhile: the same;
- a file of the new name appeared meanwhile: the same;
- three files, a conflict on one: all three land as `.new`, and none took its place;
- `neon.score.new` exists: the job's version is `neon.score.new.2`, and the old `.new` is as
  it was;
- the folder was deleted, moved, or replaced by a link to another folder: nothing lands,
  and nothing was written anywhere;
- a job wrote one file in the folder and one in a subfolder, and the subfolder was replaced
  by a link that leads out: neither lands, and nothing was written through the link;
- a given file that isn't valid text, changed by an append: the landed file has the old
  bytes and the new ones;
- a landed file has the mode the real file had;
- a job that wrote nothing: an empty list, and no file touched;
- `written()` counts created and changed files, and a file written twice once.

## Done when

A test job changes a score, the test changes the same score meanwhile, and after the
landing the folder holds the test's version under its name and the job's as `.new`.

## As built

Built on 2026-10-05, on the branch `addon-agents`. 24 new tests, 1267 in all; no old test
changed. Decided while building:

- **`land()` returns what the event needs, as it is:** `{"files": [...]}`, and with a
  conflict also `"conflict": [...]`. The paths are the machine's.
- **When nothing lands it raises `FolderGone`,** an error of the fenced disk's own. Its
  message is the path: the folder, or the place in it that isn't what it was.
- **The landing ends the disk, whatever happened.** Afterwards the disk is dead and the
  copies are gone: after a clean landing, after a conflict, after `FolderGone`, and after a
  write that failed. `Jobs` needn't remember to do either.
- **`drop()` makes the disk dead too.** A disk without its copies has nothing true to
  show. `written()` still answers after it, for the event of a job that was killed.
- **A job lands once.** A second `land()`, and a `land()` after `drop()`, raise `ESTALE`.
  So a job that was killed can't land by mistake.
- **"The same place" is more than the same path.** The folder is known again by what the
  file system tells it by, so a folder that was deleted and made again under its old name
  isn't the same place, and nothing lands in it. The plan had only the path.
- **A place whose folder has become a link is refused,** also when the link leads to
  somewhere inside the job's folder. It isn't what it was.
- **A given file that has become a link is a conflict.** Nothing is read or written
  through it.
- **A name counts as taken** also when it is a link that leads nowhere.
- **A file that lands beside another has a new file's mode.** A file that takes its place
  keeps the mode the real file had, by the whole-file write of step 1.
- **With its folder gone, a job that wrote nothing raises `FolderGone` too.** The folder is
  looked at first.

**For step 7:** a write can fail in the middle of a landing, when the disk is full, say.
`land()` then raises that `OSError`. What had landed stays, as this file says of a crash,
and the copies are gone. The plan doesn't say how such a job ends; it isn't `why: folder`.

**The "Done when" is a test:** a job changes a score, the test changes the same score
meanwhile, and after the landing the folder holds the test's version under its name and
the job's as `.new`.

**Nothing here needs a terminal or a model.** Nothing calls `land()` before step 7.
