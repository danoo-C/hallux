# Step 1: whole-file writes

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 10

**Needs:** nothing. **Changes:** `hallux/disk.py`, `tests/test_disk.py`.

Today `write_file` and `edit_file` open a file and write into it
(`hallux/disk.py:169,177`). For a moment the file is empty or half-written. With one agent
that never showed: Hallux's file tools run one at a time. An addon function reads in a
thread of its own, though, and with jobs a `check` can read a score while the main agent
saves it. So a whole file is written beside the old one and renamed over it. The machine's
memory is written that way already (`hallux/disk.py:286-288`).

**This step changes a running machine.** Files have the same content afterwards. Three
things differ, and a user can meet each: a folder's time of change moves whenever a file in
it is saved, a file in a folder that takes no new files falls back to the old way, and a
crash of Hallux in the middle of a write can leave the new file behind.

## Build

**One helper** writes a whole file: a new file in the same folder, then a rename over the
target. It takes text, as the tools give it, or bytes, as the landing of step 5 will.

| Who writes | Today | From this step |
|---|---|---|
| `write_file`, not appending | In place | Through the helper |
| `edit_file` | In place | Through the helper |
| `write_file` with `append` | In place | In place, as today: a reader sees the old text, or more of it |
| The landing (step 5) | | Through the helper |

- **The new file gets the old file's mode.** A file that didn't exist gets what a new file
  gets today.
- **A link stays a link.** `write_file` follows a link to the file it points to, as today,
  and that file is the one replaced.
- **`parents=true`** makes the folders first, as today.
- **If the write fails,** the half-written new file is taken away, and the old file is as
  it was.
- **If the folder takes no new file,** because Hallux may write the file but not create one
  beside it, the write goes in place, as today. A file that could be written before this
  step can still be written.
- **The new file has a name that is easy to tell,** with a dot in front and `.hallux-` in
  it. It exists only inside one call, so no tool ever lists it. After a crash it can be
  left over; the user sees an odd file, and nothing is lost.
- **What it gives up:** a file that has a second name (a hard link) loses the tie to it.

## Tests

In `tests/test_disk.py`:

- everything the tests of `write_file` and `edit_file` check today still holds;
- a reader that has the file open during a write still reads the old text to its end;
- the mode of an existing file is the same after a write and after an edit;
- a new file has the mode a new file had before this step;
- writing through a link changes the file it points to, and the link is still a link;
- a write into a folder that isn't there fails as today, and leaves nothing behind;
- a file in a folder that takes no new files is written in place, with the new content;
- an edit whose `old` doesn't match fails as today, and the file is untouched;
- appending behaves as before.

## Done when

The tests of the disk pass, old and new, and no test of another file had to change.

## As built

Built on 2026-10-05, on the branch `addon-agents`. 14 new tests, 1080 in all; no test of
another file changed. Decided while building:

- **The helper is `write_whole(real, data)`,** a function of `hallux/disk.py` beside the
  `Disk`. It takes a real path, so the landing of step 5 can call it with bytes.
- **The file beside it** is named `.<name>.hallux-<eight hex digits>`, such as
  `.notes.md.hallux-3f9a1c0e`. `TEMP_MARK` holds the `.hallux-`.
- **A file Hallux may not write is still refused.** The plan didn't name this. A rename
  needs only the folder's leave, so a file of mode 444 would have become writable. The
  helper first opens the old file for writing, without changing it, and fails with what
  that says: `EACCES`, as before.
- **What is no regular file is written in place.** A directory fails with `EISDIR`, as
  before. A pipe or a device is written into, never replaced by a file.
- **In place too, whenever no file can be made beside it:** the folder isn't Hallux's to
  write, or the name is too long for a longer one beside it. A folder that isn't there
  fails with `ENOENT`, as before.
- **The log says when a write went in place** for that reason:
  `<path> was written in place: no file can be made beside it`. It is the one case where a
  reader can still see half a file, so it isn't silent.
- **The mode is set before the text is written.** The new text of a private file is never
  in a file that others may read, not even for a moment.
- **Text becomes bytes before anything is touched.** Text that is no UTF-8, half a
  character, used to empty the file and then fail. Now it fails, and the file is as it was.
- **What it gives up beside a second name:** the owner, the group and the extended
  attributes of a file that Hallux's user didn't make. The new file is that user's.
- **The memory and `config.toml` keep their own way** of writing beside and renaming. They
  weren't touched.
- **The lines of `disk.py` moved.** `write_whole` is at 63, `write_file` at 228 and
  `edit_file` at 240, where this step's first lines say 169 and 177. The design's three
  references into the file are set again.

**Tried on 2026-10-05,** with a throwaway script. A thread reads a file of 400 KB through
the disk again and again, as an addon function does, while the file is saved a few thousand
times in three seconds.

| | Reads | Of a half-written file |
|---|---|---|
| With this step | 12,654 | 0 |
| With the code before it | 20,158 | 18,006 |

**Nothing here needs a terminal or a model,** so nothing is left to try by hand. What a
user can see in a running machine: a file saved in nano has the mode it had, and its
folder's time of change moves.
