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
