# Step 4: the fenced disk

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 5

**Needs:** step 1. **Makes:** `hallux/jobdisk.py`, `tests/test_jobdisk.py`.

A job sees one folder, creates files there, and changes only the files it was given. What
it writes goes into private copies, and nobody else sees them. This step builds that view of
the disk, a `JobDisk`. It has no session, no table and no model in it: it is a `Disk`, a
folder, a list of files and a number. Putting the copies in place is step 5.

## Build

**`JobDisk(disk, folder, edit, pid)`** checks what it is given, and raises when something is
refused, with the path that was.

| Checked | Refused with |
|---|---|
| The folder exists and is a directory inside the machine | `ENOENT`, `ENOTDIR`, or what the jail says |
| The folder isn't `/`, `/home`, or a home folder itself: `/root`, or a folder directly in `/home` | `EACCES` |
| The folder isn't a system folder or inside one: `/etc`, `/usr`, `/bin`, `/sbin`, `/lib`, `/boot` | `EACCES` |
| Each file in `edit` exists, is a regular file, and lies inside the folder | `ENOENT`, `EISDIR` or `EACCES` |
| No file is named twice, and there are at most 8 | `EINVAL`, `E2BIG` |

- **The folder is checked as it really is,** after the jail has followed its links: a link
  called `Music` that points to `/etc` is refused.
- **It remembers the given files as they are now:** what each one holds, to tell at the
  landing whether someone changed it (step 5).

**The methods** have the names and the answers of `Disk`'s, so the file tools and the disk
handle work on a `JobDisk` unchanged:

| Method | For a job |
|---|---|
| `list_dir`, `read_file`, `read_text` | Anything inside the folder, subfolders included. A file the job has written is read as the job wrote it, and a file it created is in the listing |
| `write_file(path, content, append)` | A given file, a file the job created, or a new name. There is no `parents` |
| `edit_file(path, old, new)` | A given file, or a file the job created |

- **Paths are the machine's,** and a path without a `/` in front starts at the folder: the
  job has its own working directory, and it never changes.
- **The fence:** a path goes through `Disk.real()` as always. The result has to lie inside
  the folder, or the call fails with `EACCES`. So `..`, an absolute path elsewhere, and a
  link in the folder that points out of it are all refused.

**Writing:**

| The path is | What happens |
|---|---|
| A file the job was given | The job's copy is written. The first change copies the real file, so an edit or an append starts from the real text |
| A file the job created earlier | The copy is written |
| A new name in a folder that exists | Checked, then the copy is written |
| A file that exists and wasn't given | `EACCES` |
| A new name in a folder that isn't there | `ENOENT`: a job can't create a folder |

- **A new name** has letters, digits, `.`, `-` and `_`, and no dot in front. Anything else is
  `EACCES`. A given file keeps its name, whatever it is.
- **The limits:** 16 files and 1 MB in all, the given files it changed included. Over them:
  `EDQUOT`.
- **The copies live in `<root>/.hallux/jobs/<pid>/`,** under the same path they have in the
  folder. The machine can't see that place: the jail hides `/.hallux`.
- **A copy goes by the file itself, not by its name.** A link inside the folder can give a
  file a second name. Both names lead to one copy, and a list that names a file twice that
  way is refused like one that repeats a name.
- **Files are bytes.** A copy is made byte for byte, and an append adds to those bytes. A
  given file that isn't valid text is damaged nowhere the job didn't write.

**One lock.** A job's disk is used from two threads: its file tools and its landing run in
Hallux's event loop, and an addon function's disk handle runs in the addon's own thread
(`hallux/addons.py:384`). The machine's `Disk` holds nothing that two threads could trip
over. This one holds the copies, the counts and whether it is closed. Every method takes the
lock, so a write from a thread can't fall between a landing's steps, or between the check
for "closed" and the deleting of the copies.

**When the job is over:**

- **`close()` makes the disk dead.** Every later call raises `ESTALE`. An addon function
  that outlives its job then can't read or write through its handle.
- **`drop()` deletes the copies.**
- **`sweep(disk)`** deletes every job's folder that is still there, and returns their names
  for the log. Hallux calls it when it starts (step 10).

## Tests

In `tests/test_jobdisk.py`, on a test world, with no model:

- each refused folder, with its error: `/`, `/home`, `/home/user`, `/root`, `/etc`,
  `/usr/local/bin`, a file, a folder that isn't there, a link that points to `/etc`;
- `/home/user/Music` and `/tmp/work` are accepted;
- each refused list: a missing file, a folder, a file outside the folder, a file twice, nine
  files;
- reading inside the folder and in a subfolder; `..`, `/etc/passwd` and a link that points
  out are `EACCES`; `/.hallux` is hidden as always;
- a relative path starts at the folder, also after the machine's own `cd`;
- a new file: the job reads it back and lists it, and the real folder doesn't have it;
- a given file: after the job's write the job reads its own text, and the real file is as
  it was;
- an edit and an append of a given file start from the real text;
- a file that exists and wasn't given: `EACCES` for a write and for an edit;
- each refused name: a space, a dot in front, a `/` into a folder that isn't there;
- a name the user chose, such as `My Song.score`, is fine as a given file;
- a file and a link to it in the same folder: one copy, read the same under both names; both
  in the list are refused;
- a given file with bytes that aren't text: after an append its old bytes are unchanged;
- a write from a second thread while the first is in the middle of a call waits for it;
- the seventeenth file and the write that passes 1 MB: `EDQUOT`, and nothing was written;
- the disk handle of the addons, built on a `JobDisk`, reads the job's own version;
- after `close()` every call raises `ESTALE`, also through the handle;
- `drop()` leaves nothing in `.hallux/jobs`, and `sweep` finds what a crash left.

## Done when

A test job writes a new score and changes a given one, reads both back as it wrote them,
and the user's folder is, byte for byte, what it was.
