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
