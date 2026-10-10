# Step 2: the tree

[The plan](README.md)

**Needs:** step 1. **Changes:** `hallux/importing.py`, `hallux/disk.py`,
`hallux/statusbar.py`, `tests/test_importing.py`, `tests/test_disk.py`,
`tests/test_statusbar.py`.

What would be copied, where to, and what is in the way: worked out without writing
anything. The tab draws it in step 5, and the copy of step 3 follows the same rules.

## Build

**`look(disk, sources, into, stop=None, tell=None) -> Tree`.** `sources` are the paths of
step 1, `into` is a directory of the machine (`/home/user/Music`). It walks every source
and returns the tree. It is made to run in a thread: it looks at `stop` between entries and
returns early when it is set, and it calls `tell(counts)` now and then, so that the tab can
show the counts growing.

**The tree:**

| | What |
|---|---|
| `into` | The destination, as the machine's path |
| `lines` | What the tab draws, top to bottom: a depth, a name, a kind, a size, for a folder its number of files, and a mark |
| `counts` | Of everything, also of what `lines` leaves out: folders, files, bytes, and how many are marked in each way |
| `refused` | Why nothing can be copied at all, or nothing |

**Where a thing goes.** A source goes to `into` plus its own name, and what is in a folder
goes under that folder's place. Every place is asked of the disk: `Disk.place(path)`.

**`Disk.place(path) -> Path`,** new in `hallux/disk.py`: the real path for a write of the
import. It is `real(path, follow=False)`, so the folders above it are resolved and checked
by the fence that is there (`hallux/disk.py:144`, `_check`), and the last name is left as it
is. A link out of the machine among those folders is refused there, and so is `/.hallux`.

**The marks.** One per line, the first that fits:

| Mark | When | What the copy does |
|---|---|---|
| `is already here` | The source and its place are the same file or folder | Skips it, with all that is in it |
| `in the way` | A file where a folder should go, a folder where a file should go, or a link at the place | Skips it, with all that is in it |
| `can't go there` | The disk refuses the place: `/.hallux`, or a link out of the machine above it | Skips it |
| `can't be read` | The source can't be opened or listed | Skips it |
| `not copied` | A socket, a pipe, a device | Skips it |
| `exists` | A file is at the place already | Asks: overwrite or skip |
| `→ target` | A link inside a dropped folder | Copies the link, if its place is free; otherwise `in the way` |
| none | | Copies it |

- **A folder that exists already has no mark.** The two are merged, and its files have
  marks of their own.
- **A source that is a link** is followed: its name, and what it leads to. A link inside a
  dropped folder is not.

**What refuses the whole drop** (`refused`):

| When | The words |
|---|---|
| The destination is the dropped folder, or inside it | `would be copied into itself: ` and the name |
| The destination isn't there any more, or is no folder | `the folder is gone: ` and the path |

**The order.** In a folder: by name, as `sorted` does, folders and files together. The
sources: in the order they were dropped.

**The limits.** Constants in `hallux/importing.py`:

| | | |
|---|---|---|
| `FOLDER_MAX` | 50 | Entries a folder lists. Then one line, `… N more` |
| `TREE_MAX` | 2,000 | Lines the tree keeps. Then one last line, `… and more` |

The walk goes on past both: the counts are of everything, and so is the number of files
that exist already. The walk never follows a link into a folder.

**`size(bytes) -> str`** in `hallux/statusbar.py`, beside `tokens` and `spent`: `812 B`,
`340 kB`, `2.3 MB`, `1.1 GB`. Thousands, not 1024s, as a file manager shows them.

## Tests

- A file into an empty folder: one line, no mark, the counts.
- A folder with folders in it: the depths, the order, each folder's number of files and its
  size.
- Each mark, with the least that makes it: a file over a file; a file where a folder is; a
  folder where a file is; a link at the place; a source that is its own place; a source
  named `.hallux` into `/`; a folder that can't be listed; a pipe; a link inside a folder.
- A folder into a folder of the same name with one file in common: the folder has no mark,
  that file has `exists`.
- A link among the destination's folders that leads out of the machine: `can't go there`.
- The destination inside the dropped folder: `refused`, and no lines.
- 60 files in a folder: 50 lines and `… 10 more`, and the count says 60.
- More than `TREE_MAX` lines: the last line, and the counts are whole.
- `stop` set before the walk: it returns at once.
- Nothing was written: the destination is as it was after every one of these.
- `Disk.place`: a plain path; a link as the last name is not followed; `/.hallux`; a link
  out among the folders above.
- `size`: the four examples above, and 0.

## Done when

The tests pass. `look` on the machine's own `Pictures` folder, dropped into its home, gives
one line with `is already here`: the user's first drop.

## As built

Built on 2026-10-10, and committed together with step 1 on the branch `drag-and-drop`. 48
new tests (30 for the tree, 2 for `Disk.place`, 16 for `size`), 1684 in all; no old test
changed. Nothing calls `look` yet.

**How it is built:**

- **One walk, `_walk`, which the copy can use too.** It gives every thing in the order of
  the tree, with its place and its mark, and it works out a mark only when it comes to the
  thing. Step 3 says the copy "walks the sources again and decides for every file at that
  moment, by the rules of step 2". With `_walk` those are the same lines of code, not the
  same rules written twice. A copy that makes a folder before it asks for the next entry is
  told of what is in that folder as it is by then.
- **The walk keeps a list of what waits, and doesn't call itself,** so it doesn't matter how
  deep the folders are nested.
- **`look` makes the lines and the counts of that walk.** A folder's line gets its number of
  files and its size when the walk has left the folder.
- **`Disk.place`** is `real(path, follow=False)` under a name of its own, as the step says.

**Where it differs from the text above:**

- **`can't go there` is looked for first,** before `is already here` and `in the way`.
  Those two need the place, and the disk gives none.
- **A pipe, a socket or a device is `not copied` also when its name is taken.** The table
  has `in the way` in front of it; `not copied` says more, and nothing is copied either
  way.
- **The tree has a fifth thing, `stopped`.** A walk that was stopped returns no lines, the
  counts so far, and `stopped`. Without it a tree that was cut short looks like a whole
  one.

**Decided while building,** where the text above leaves it open:

- **What the counts count:** everything the walk came to, whatever its mark. `folders` are
  the folders, `files` is all that is no folder (files, links, pipes), `bytes` is what the
  files hold. What is in a folder with a mark isn't walked, and so isn't counted. A
  folder's own line counts the same way, at any depth below it.
- **`counts.marks`** has a number for each mark that was given. The links that would be
  copied are under `→`. `SKIPPED` names the five marks that aren't copied.
- **A line's mark is the text to draw.** For a link it is `→ ` and where the link leads,
  as it is written in the link.
- **`… N more` and `… and more` are lines of the kind `more`.** `… N more` stands at the
  depth of the entries it stands for, `… and more` at depth 0.
- **A thing that was dropped itself always has a line,** however many were dropped: the 50
  are what a folder lists. Only `TREE_MAX` ends them.
- **`is already here` is told by the file itself** (device and number, `os.path.samestat`),
  not by its path. So a file in a dropped folder that is the very file at its place, by a
  hard link, has the mark too.
- **Anything at the place of a link is in its way,** also the same link.
- **`can't be read`:** a folder is listed, and that fails or doesn't. A file is asked about
  with `os.access`; no file is opened for the preview. A file that can't be opened after
  all fails in the copy, and is counted there. A thing of which nothing can be found out,
  like a dropped link that leads nowhere, is `can't be read` and of the kind `other`.
- **A destination behind a link out of the machine, or in `/.hallux`, is not "gone".**
  Every dropped thing gets `can't go there`, as the step's test says, and `refused` stays
  empty.
- **`the folder is gone`** is also said of a destination that is a file.
- **`would be copied into itself`** is told by the real paths, with every link followed, so
  also when the folder was dropped under a link's name.
- **A dropped path that ends in `..`** comes under the name of the folder it leads to (step
  1 left that for this step). `/` has no name. It is always refused, with `/` as its name:
  the machine is inside it.
- **`tell`** is called at most ten times a second (`TELL_SECONDS`), each time with counts
  of their own that don't change afterwards.
- **`size`:** one digit after the point below ten of a unit, none from there on: `9.9 kB`,
  `10 kB`. Never `1000 kB`: that is `1.0 MB`. `TB` is the last unit.

**For the later steps:**

- **Step 3:** the tab shows `120 of 1,400 files`. The 1,400 are the tree's `counts.files`,
  which counts what has a mark too. For the two numbers to meet at the end, the copy's
  `tell` has to count the files it is through with, copied or not.
- **Step 4:** `_refused` and `_holds` are "the same check as step 2's" for a drop that
  holds the destination.
- **Step 4:** two things of the same name get the same place, and `look` lists both
  without a word. Refusing the second is step 4's, as its text says.

**Checked beyond the tests:**

- **The user's first drop,** on the real machine `test-hallux`, from the text as it
  arrived: `Pictures` into `/home/danika-hous` is one line, `is already here`. The same
  folder into `Music` is 4 files, 30 kB. The machine's `home` into its own `Music` is
  refused: `would be copied into itself: home`. Nothing in the machine was touched.
- **A big folder:** the repository's `.venv`, 758 folders and 6,196 files, 418 MB, takes
  1.1 seconds. The tree has 2,000 lines and `… and more`, and `tell` was called 10 times.
- **A folder of the Windows drive:** `C:\Windows\Fonts`, 342 files, takes 0.9 seconds.
  That is about 3 ms a file, where a file on the Linux disk takes 0.16 ms. A folder of
  10,000 files from `C:` will count for about half a minute before the tree is there.
- **The code was broken in 70 ways,** one at a time, and a test noticed each.
