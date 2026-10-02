# Step 1: the disk handle

[The plan](README.md) · the design: [addons.md](../../addons.md), open question 4, and step 7
of [addons-plan.md](../addons-plan.md)

**Needs:** nothing. **Changes:** `hallux/addons.py`, `hallux/tools.py`, `hallux/machine.py`,
`tests/test_addons.py`.

`play(path)` gets a path inside the machine. An addon must not open that path by itself: it
would work around the path jail. So Hallux hands the function a small handle that reads and
writes through `hallux.disk`. This step belongs to the addon system. The music addon is only
the first one that needs it.

## Build

- **A function whose first parameter is called `disk` gets the handle.**
  `def play(disk, path: str, loop: bool = False)` is called by Hallux with the handle in
  front. The parameter needs no type hint and isn't part of the schema, so the AI never sees
  it and can't pass it.
- **The handle has two methods:**

| Method | What it does |
|---|---|
| `read_text(path)` | The whole file as text. It is `Disk.read_text`, with its limit of 1 MB |
| `write_text(path, content)` | Creates or overwrites the file. It is `Disk.write_file` |

- **Paths are the machine's.** Absolute, or relative to the machine's working directory, as
  for the disk tools. The handle wraps the machine's own `Disk`, so `cd` is followed.
- **What the jail refuses raises what the disk tools raise.** The call wrapper turns an
  `OSError` into its errno name, such as `{"error": "ENOENT"}`, and a `ValueError` into its
  text. The AI already prints those the way a program would.
- **How the handle gets there:** `Machine` passes its disk to `build_addon_servers`, that to
  `build_addon_tools`, and that to `call`. All three take it as an argument with an empty
  default, so the existing tests keep passing unchanged.
- **The `stop()` hook gets no handle.** Hallux calls it bare, also when no machine is running.

**Checks in the loader, so that a mistake is loud:**

| The function | What happens |
|---|---|
| Has `disk` as its first parameter | It gets the handle |
| Has `disk` anywhere else | The addon is skipped: `play(disk): disk must be the first parameter` |
| Is `stop`, and needs `disk` | The addon is skipped, by the check that exists: `stop()` must work without arguments |

## Tests

In `tests/test_addons.py`, with fake addons in a temporary folder, as the others:

- a fake addon's `count_lines(disk, path)` reads a file of a test world;
- a relative path follows the machine's working directory;
- a path that leaves the root is refused, and so is anything in `.hallux`;
- a missing file gives `ENOENT`, a file over 1 MB `EFBIG`, a binary file its message;
- `write_text` writes inside the root and nowhere else;
- the schema of the tool has no `disk`, and a call that passes one is refused;
- `disk` as a second parameter skips the addon, with the reason;
- a function without `disk` is called exactly as before.

## Done when

A fake addon's `count_lines(disk, path)` works on a file in a test world, called through the
tool that the AI would use.

## As built

Built on 2026-10-02. One thing differs from the list above: only the handle's own errors are
said as errno names, and an addon's own exceptions keep their name in front, as before. That
and the other decisions taken while building are under step 7 of
[addons-plan.md](../addons-plan.md).

## Also in this step

- The status line of [addons-plan.md](../addons-plan.md) says that step 7 is built.
- The roadmap's "Later" list loses its entry for the disk handle.
