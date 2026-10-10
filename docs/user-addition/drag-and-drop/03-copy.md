# Step 3: the copy

[The plan](README.md)

**Needs:** step 2. **Changes:** `hallux/importing.py`, `hallux/disk.py`,
`tests/test_importing.py`, `tests/test_disk.py`.

Files and folders go into the machine's disk. No file is ever seen half-written, nothing is
written outside the machine, and nothing is replaced that the user wasn't asked about.

## Build

**`carry_out(disk, sources, into, overwrite, stop=None, tell=None) -> Result`.** It walks
the sources again and decides for every file at that moment, by the rules of step 2. It
doesn't copy from the tree: the tree is what the user saw, and may leave lines out.

**`overwrite`** has three values:

| Value | When | A file that exists |
|---|---|---|
| `True` | The user answered `o` | Is replaced |
| `False` | The user answered `s` | Is skipped |
| `None` | The question wasn't asked: the tree had no `exists` | Is skipped, and counted as `appeared meanwhile` |

**One file:** `copy_whole(source, real, stop)`, new in `hallux/disk.py`, beside `write_whole`
(`hallux/disk.py:63`). It does what `write_whole` does, for a file that may be bigger than
memory:

1. A new, empty file beside the place, with `_new_beside` (`hallux/disk.py:99`): its name
   starts with a dot and has `.hallux-` in it.
2. The source is read and written in pieces of 1 MB. Between two pieces it looks at `stop`.
3. An overwritten file's mode goes onto the new file, as in `write_whole`. A new file keeps
   the mode a new file gets.
4. The source's time is set on it (`os.utime`).
5. It is renamed over the place (`os.replace`): the old file or the new one, never half.
6. Whatever goes wrong, and when `stop` is set: the new file is removed, and the place is
   as it was.

Unlike `write_whole`, it has no way to write in place. Where the folder takes no new file,
the copy of that file fails, and is counted.

**A folder:** made with `mkdir` if it isn't there. Its place is asked of `Disk.place` first,
like every place.

**A link inside a folder:** made with `os.symlink`, with the text the source's link has.

**What stops the whole copy:**

| When | The result says |
|---|---|
| `stop` is set | `stopped` |
| The disk is full (`ENOSPC`), or over its quota (`EDQUOT`) | `the disk is full` |
| The destination is gone | `the folder is gone` |

Any other error is that one file's: it is counted with its reason, and the copy goes on.

**The result:**

| | What |
|---|---|
| `into` | The destination |
| `files`, `folders`, `bytes` | What was written |
| `skipped` | How many weren't, by reason: the marks of step 2, `exists` for the ones the user skipped, `appeared meanwhile` |
| `failed` | Up to 50 paths with their reasons, and how many more there were |
| `ended` | Nothing, or why it stopped early |
| `names` | The top-level names under which something was written, a folder with `/` after it. For the AI's note (step 6) |

**`tell(done)`** is called after every file and about ten times a second inside a big one,
with the files and bytes so far.

## Tests

In `tests/test_importing.py`, on real temporary folders, with a real `Disk`:

- A file; a folder with folders; into a folder that exists, merged.
- `overwrite=True` replaces, `False` skips, `None` skips and counts `appeared meanwhile`.
  The replaced file has the old file's mode and the source's time.
- Each mark of step 2 is skipped, and nothing at its place has changed.
- A link inside a folder arrives as a link with the same text.
- A new file's mode is a new file's, also when the source is `rwxrwxrwx`.
- A source of 3 MB with `stop` set after the first piece: the result says `stopped`, the
  place is as it was, and no file with `.hallux-` in its name is left.
- A file that can't be read, between two that can: both others arrive, one is in `failed`.
- A stand-in that raises `ENOSPC`: the copy ends with `the disk is full`, and what was
  written before stays.
- A source named `.hallux` into `/`, and a destination with a link out of the machine above
  it: nothing is written outside the temporary machine. The test looks at the folder
  outside.
- A reader that holds the old file open while it is replaced reads the old text to its end
  (as the test for `write_whole` does).
- `names`: a folder in which nothing could be written isn't among them.

In `tests/test_jobdisk.py`, the row of the decision table: a job creates `a.score`, an
import puts an `a.score` there before the job lands, and the job's file lands as
`a.score.new`.

## Done when

The tests pass, and a folder of a few hundred real files (the repository's own `docs`)
copied into a temporary machine is the same as its source, compared file by file.

## As built

Built on 2026-10-10, on the branch `drag-and-drop`. 38 new tests (25 for the copy, 12 for
`copy_whole`, 1 in `tests/test_jobdisk.py`), 1722 in all; no old test changed. Nothing calls
`carry_out` yet.

**How it is built:**

- **The copy goes over the sources with the tree's own walk,** `_walk` of step 2. So a
  thing's mark in the copy is worked out by the very lines that marked it in the tree, at
  the moment the copy comes to it.
- **The walk gives each thing its real place too.** The disk is asked once for a thing, the
  mark is worked out for that place, and the copy writes at that place and no other.
- **`copy_whole(source, real, stop, wrote)` has a fourth thing, `wrote`.** It is told the
  bytes of each piece. That is how `tell` can speak inside a big file. It returns `False`
  when it was stopped.
- **`_new_beside` is two functions now.** `_open_beside` makes the file beside the place and
  raises what the folder says against it. `_new_beside` is the old one on top of it, which
  says nothing and returns `None`, for `write_whole`. The copy needs the reason: a full
  disk ends the whole copy, a folder that isn't there ends one file.

**Where it differs from the text above:**

- **"A file that can't be read, between two that can"** is skipped and counted as
  `can't be read`, by the walk's mark: it never reaches the copy. It is in `failed` only
  when it seemed readable and then couldn't be opened. Both are tested.
- **`tell` counts what the copy is through with, copied or not:** folders, files and bytes,
  as a `Counts`. So it ends at the counts of the tree, and the tab's `120 of 1,400 files`
  ends at 1,400 (the note step 2 left).

**Decided while building,** where the text above leaves it open:

- **`copy_whole` replaces a file and nothing else.** If a folder or a link has the name by
  the time it writes, it fails with `File exists`, and the name stays what it was. The
  walk would have marked that `in the way`; this is for what gets there in between.
- **A path in `failed` is the path below the destination,** `album/b.txt`. Its reason is
  the system's own words: `Permission denied`, `No such file or directory`. How many more
  failed than the 50 is in `more`.
- **A copy that the tree would refuse never starts.** `ended` then holds the tree's words:
  `would be copied into itself: home`, `the folder is gone: /home/user/Videos`.
- **Whether the destination is gone** is looked at when a write fails. A copy in which
  nothing fails never asks.
- **`folders` are the folders that were made,** not the ones that were there and got
  something. **`bytes`** are the bytes that were written, counted piece by piece.
- **A name is in `names` when something was written at it or under it:** a folder that was
  made, a file, a link. A folder that was there already, in which everything was skipped,
  isn't among them.
- **A folder that can't be made is in `failed`, and so is every thing in it,** each with
  `No such file or directory`. Nothing in it is left out without a word.
- **The copy has the source's time, the one it was changed at and the one it was read
  at.** A folder that is made has the time it was made.
- **Stopped inside a file,** the copy ends at once: `copy_whole` looks at `stop` before
  every megabyte.

**What it can't do:**

- **A file whose name is longer than about 238 bytes can't be copied.** There is no room
  for the longer name of the file beside it. It is in `failed` with `File name too long`.
  `write_whole` writes such a file in place; a copy never writes in place, as the step
  says.
- **A file that appears at a place while the copy writes to that place is replaced.** The
  walk looks, then the copy writes and renames, and what is renamed last stays (the
  README's risk about the AI and the copy writing at the same time).

**For the later steps:**

- **Step 4:** `tell` gets a `Counts`, as the walk's `tell` does. How far the copy is, of
  how much, is that `Counts` beside the tree's.
- **Step 6:** `names` is in the order of the drop.

**Checked beyond the tests:**

- **Done when:** the repository's `docs`, 77 files in 19 folders, 1.1 MB, copied into a
  temporary machine in 0.05 seconds: the same as its source file by file, and every file
  has its source's time. Dropped a second time without the question, all 77 are
  `appeared meanwhile` and nothing is written. With overwrite, all 77 are replaced.
- **Many small files:** 686 files of 8.5 MB in 0.34 seconds, the same as their source.
- **Files of the Windows drive:** three fonts from `C:\Windows\Fonts` are `r-xr-xr-x`
  there and arrive as `rw-r--r--`, the mode of a new file here, with the same bytes and
  the source's time.
- **A real thread, stopped from another:** a file of 200 MB, `stop` set 0.1 seconds into
  it. The copy ended as `stopped`, no file was at the place, nothing with `.hallux-` in its
  name was left, and the thread had ended.
- **The code was broken in 59 ways,** one at a time, and a test noticed each.
