# Step 1: reading a drop

[The plan](README.md)

**Needs:** nothing. Its real examples are the four texts the user's terminals sent on
2026-10-10 (the plan's README, "What a drop is"). **Makes:** `hallux/importing.py`, `tests/test_importing.py`. **Changes:** nothing.

The text a terminal pastes for a drop becomes a list of real paths, or a reason why it
isn't one. Nothing calls it yet.

## Build

**`read_drop(text, translate=from_windows) -> list[Path]`.** It raises `NotADrop`, a
`ValueError` whose text is for the panel's foot, when the text isn't a drop.

**Three readings.** Each makes a list of path texts. They are tried in this order, and the
first one in which every path exists is taken.

| Reading | How the text is cut | Who pastes this way |
|---|---|---|
| The whole text | One path. One pair of quotes around it is taken off | One file without a space, anywhere |
| Quotes, and a backslash is a character | Cut at spaces outside `"…"` and `'…'`, and between a quote that closes and one that opens right after it. A backslash stays as it is | Windows Terminal: `"C:\Users\dano\my file.txt" C:\Users\dano\b.txt`. VS Code, two drops in a row: `'/a/Pictures''/a/hallux.hlx'` |
| A shell's words | `shlex.split`: quotes, and a backslash in front of a space | macOS Terminal, iTerm2, GNOME Terminal, kitty: `/home/dano/my\ file.txt` |

- **Before the readings:** spaces and line ends at both ends are cut off. An empty text is
  no drop. A text of more than 64 kB is no drop, and so is one with a NUL in it.
- **A path that starts with `file://`** is turned into a path first (`urllib.parse`).
- **A path that looks like a Windows path** is translated, unless it exists as it is
  written: it starts with two slashes of either kind, or with a letter, a colon and a slash
  of either kind. First by rule, with no other program:

  | The path | Becomes |
  |---|---|
  | `\\wsl$\NAME\rest`, `\\wsl.localhost\NAME\rest`, and both with `/` for `\` | `/rest`, when `NAME` is this distribution (`WSL_DISTRO_NAME`, whatever the case of its letters) |
  | `//wsl/NAME/rest` | The same. It is VS Code's form: it turns the slashes and takes the `$` out |
  | `C:\rest`, `c:/rest` | `/mnt/c/rest` |

  **If that gives nothing that exists,** the path is given to `translate`, and if that
  gives nothing either, the path doesn't exist for this reading. The rule comes first
  because a drop can hold hundreds of paths, and `wslpath` takes one at a call.
- **A path that is not absolute** after that doesn't exist for this reading. A terminal
  always pastes the whole path, and a bare word like `ls` must never be read as a file in
  Hallux's own directory.
- **"Exists"** is `os.path.lexists`: a link counts, also one that leads nowhere.
- **The result** is the paths as they were dropped, not resolved, and each one once: the
  name the user dropped is the name that is copied.

**`from_windows(text) -> str | None`.** It runs `wslpath -u` with the text as one argument,
without a shell, and returns what it prints. `None` when `wslpath` isn't on the `PATH`, when
it fails, or after two seconds. It is what knows a Windows drive that is mounted somewhere
else than `/mnt`. Outside WSL every Windows path "doesn't exist", and the foot says so.

**What `NotADrop` says:**

| When | The words |
|---|---|
| No reading has a path that exists | `no such file or folder on this computer: ` and the text, cut to its last 60 characters |
| A Windows path of another distribution, or one that `wslpath` refused | `can't be reached from here: ` and the path |
| Empty, too long, a NUL | `not a path` |

The words name "this computer" because the commonest cause is a window on another one: a
drop over ssh.

## Tests

In `tests/test_importing.py`, with real files in a temporary folder and a stand-in
`translate`:

- One path; one path in double quotes; in single quotes.
- Two paths with a space between them; one of them quoted because of a space in it.
- A path with `\ ` for its space.
- `file:///…`, with `%20` in it.
- The user's own drop, as a string, `\\wsl$\kali-linux\…\Pictures`, with `WSL_DISTRO_NAME`
  set: one path, and `translate` wasn't called.
- The eight files Windows Terminal sent as one paste, with a space between them: eight
  paths, in their order, and `translate` wasn't called.
- `C:\…` with a temporary folder standing in for `/mnt`: one path. A drive the rule can't
  find, with a `translate` that maps it: one path, and `translate` was called once.
- The same folder as VS Code's terminal sent it, `'//wsl/kali-linux/…'`, with
  `WSL_DISTRO_NAME` set to `kali-linux` and to `Kali-Linux`: one path. With another name,
  and with none: `NotADrop`, `can't be reached from here`.
- The text of the second check, a folder and a file with nothing between them,
  `'//wsl/kali-linux/…/Pictures''//wsl/kali-linux/…/hallux.hlx'`: two paths.
- A Windows path with a space, in double quotes, beside one without: the backslashes are
  not eaten.
- A text in which one path of two doesn't exist: `NotADrop`.
- `ls`, `notes.txt`, an empty text, a text with a NUL: `NotADrop`. A file `ls` in the
  current directory changes nothing.
- The same path twice: listed once.
- `from_windows` with `wslpath` missing gives `None`. Where `wslpath` exists (the test skips
  elsewhere): `C:\` gives a path under the Windows mount.

## Done when

The tests pass, and the four texts the user's terminals sent, as they arrived, are among
them.

## As built

Built on 2026-10-10, and committed together with step 2 on the branch `drag-and-drop`. 57
new tests, 1636 in all; no old test changed, and nothing called `read_drop` yet.

**Where it differs from the text above:**

- **A path of this distribution is never given to `translate`.** The text above says that
  `translate` is asked wherever the rule gives nothing that exists. Its own test says that
  the eight files are read without one call. Both can't hold: the first reading takes the
  whole paste as one path, and what the rule makes of that doesn't exist. For
  `\\wsl$\NAME\…` of this distribution the rule's answer is the only one there is, also
  when nothing is there. `wslpath` says the same: asked for
  `\\wsl.localhost\kali-linux\home\dano\gone.txt` it prints `/home/dano/gone.txt`. So
  `translate` is asked for a drive that isn't found under `/mnt`, and for a Windows path
  the rule doesn't know.

**Decided while building,** where the text above leaves it open:

- **Which of the two refusals.** `can't be reached from here` when some reading found a
  Windows path that neither the rule nor `translate` could turn into a path: another
  distribution, a drive that isn't mounted, any Windows path outside WSL.
  `no such file or folder on this computer` for everything else, also for a Windows path
  that was translated to a place where nothing is.
- **The path that `can't be reached from here` names** is the shortest one that a reading
  found out of reach. The first reading takes a paste of eight paths as one path, so the
  first one found would be the whole paste.
- **`translate` is asked once for a path** in one call of `read_drop`, whatever number of
  readings name it.
- **`file://` with a computer's name in it:** the path is taken when the name is empty,
  `localhost` or this computer's own. A file of another computer is
  `no such file or folder on this computer`.
- **A quote in the middle of a word is a character** in the second reading, so
  `C:\Users\O'Brien\a.txt` is one path. A quote opens only where a piece starts.
- **The second reading cuts at line ends too,** not only at spaces: a terminal that sends
  one path to a line is read.
- **The 64 kB are bytes,** of the text as UTF-8. **The 60 characters** are a `…` and 59.
- **`MOUNT`,** a constant, is `/mnt`. The tests put a temporary folder in its place.

**For step 2:**

- **A path can come without a name of its own.** `\\wsl$\kali-linux` by itself reads as
  `/`, whose name is empty, and a typed path may end in `..`. `read_drop` returns both as
  they were dropped. Step 2 says "a source goes to `into` plus its own name", so it has to
  refuse them, or resolve them first.

**Decided by the user afterwards** (2026-10-10, "keep the end"):

- **Of a long text the refusal shows the end.** The step said "cut to 60 characters", and
  as first built that was the start. A path's name is at its end, and the user's own paths
  are 79 characters and more, so the name was what was cut off. Now it reads
  `no such file or folder on this computer: …e\dano\hallux-distros\test-hallux\home\danika-hous\gone.txt`.
  The table above says so too.

**Checked beyond the tests:**

- **With the real `wslpath` and the user's real folder,** on the user's machine: the texts
  as they arrived. `\\wsl$\kali-linux\home\dano\hallux-distros\test-hallux\home\danika-hous\Pictures`;
  the same folder as VS Code's terminal typed it; `Pictures` and `hallux.hlx` with nothing
  between them; four of that folder's files as one paste. All are read, without a call of
  `wslpath`.
- **From `C:`,** in the forms the plan expects: `C:\Windows`, `C:\Program Files` without
  quotes, and `"C:\Program Files" C:\Windows` give the paths under `/mnt/c`. Whether a
  terminal sends them in these forms is still the user's to see (the README, "Not
  checked").
- **What can't be reached:** `\\wsl$\Ubuntu\home\x` and `Q:\x.txt`, both refused by the real
  `wslpath`, give `can't be reached from here`.
- **The module was broken in 48 ways,** one at a time, and a test noticed each.

**What the tests' texts are.** The forms as they arrived, with a temporary folder in the
place of the user's home, so that the tests run on any computer. Of the eight files
dragged at once the plan records three names; the other five are made up.
