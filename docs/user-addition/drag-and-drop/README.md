# Plan: drag and drop into the machine

**Status:** written on 2026-10-10, at the user's request. **Steps 1 and 2 are built,** steps
3 to 7 are not ([The steps](#the-steps)). There is no
separate design document: this file holds the design and the plan, and every step has a
file of its own in this folder. The decisions in the table below are my proposals. The user
set the frame (a tab of the panel, a scrollable tree of what is imported) and hasn't gone
through the table. The check before the build is done, in Windows Terminal and in VS Code's
terminal ([Before the build](#before-the-build)).
The build is on the branch `drag-and-drop`, made from `main` on 2026-10-10, after the
user had merged `addon-agents` into it.

**How this plan is laid out.** Like the plans for the config panel and the addon agents.
This file holds what the steps share: what the feature does, how the parts fit, the
decisions, where the code goes, and the status. A step is built and merged by itself, so
whoever builds one reads this file and that step's file.

## In short

You drag a file or a folder from your computer onto the terminal window while Hallux's
panel is open. The panel's new **Files** tab shows what would be copied, as a tree that
scrolls. Enter copies it into the directory the shell is in. The AI takes no part in the
copy and is told afterwards, with your next line.

1. **Reading a drop:** the text a terminal sends for a drop becomes a list of real paths.
2. **The tree:** what would be copied, where to, and what is in the way.
3. **The copy:** files and folders go into the machine's disk, never half-written.
4. **The machine's side:** one list and one copy at a time, in a thread of their own.
5. **The Files tab:** the tab, the rule that a drop finds it, and its place in the panel.
6. **Telling the AI:** a note in front of the next message.
7. **The documentation and the user's try.**

Until step 5 nothing changes for the user. Step 6 changes `hallux/prompt.md`, which the
user edits too.

---

## What a drop is

A terminal has no "a file was dropped" message. It **pastes the path** of what was dropped,
as text. So a drop and a pasted path look the same to Hallux, and that is why the drop is
taken in the panel only: there a pasted path can mean nothing else. **At the shell and in a
full-screen program a paste stays a paste,** as today.

What the user's terminal sent on 2026-10-10 (Windows Terminal, Hallux in WSL, a folder
dragged from Explorer onto the shell prompt):

```text
\\wsl$\kali-linux\home\dano\hallux-distros\test-hallux\home\danika-hous\Pictures
```

The check under [Before the build](#before-the-build), run in Windows Terminal the same
day, showed the rest. Eight files dragged at once, then one file, then a folder:

```text
^[[200~\\wsl$\kali-linux\home\…\.bash_history \\wsl$\kali-linux\home\…\.bashrc … \\wsl$\kali-linux\home\…\matus_bonar.txt^[[201~
^[[200~\\wsl$\kali-linux\home\…\special.ai^[[201~
^[[200~\\wsl$\kali-linux\home\…\Music^[[201~
```

- **Windows Terminal sends a drop as a paste:** `^[[200~` in front and `^[[201~` after it
  are the paste brackets. So the panel gets it as one key, and can tell it from typing.
- **Several things dragged at once are one paste,** with a space between the paths.
- **It arrives while the mouse is on,** as it is in the panel.

What VS Code's terminal sent, for the same folder (the same check, run there first):

```text
'//wsl/kali-linux/home/dano/hallux-distros/test-hallux/home/danika-hous/Pictures'
```

- **Two terminals, two forms.** VS Code puts the path in single quotes, turns the slashes,
  and takes the `$` out of `wsl$`, so the path as written doesn't exist. Step 1 reads both.
- **VS Code types the drop.** It came without paste brackets: to a program it looks like
  keys pressed very fast. The panel can't tell that from typing, so for such a terminal the
  Files tab has a row for a typed path (step 5).
- **Two drops, one after the other, come with nothing between them:**
  `'…/Pictures''…/hallux.hlx'`, in the second run of the check. Step 1 cuts there.
- **It is a Windows path, not a Linux one.** Hallux has to translate it (step 1). I had
  expected Windows Terminal to do that; in this setup it doesn't.
- **The file itself never arrives,** only its path. So a drop works only when Hallux can
  read that path: on the same computer. Over ssh it can't work.
- **That folder was inside the machine's own disk.** A source inside the machine is
  allowed: it is a copy like any other, unless it would land on itself (step 2).

---

## What the user sees

The panel has a fourth tab, between Details and Config: `Agents  Details  Files  Config`.
Its key is `f`.

**Nothing dropped yet:**

```text
 Hallux                                     Agents   Details  [ Files ]  Config

 Drop files or folders onto this window.
 They are copied into /home/danika-hous/Music

 a d f c tabs · Esc close
```

**After a drop:**

```text
 Hallux                                     Agents   Details  [ Files ]  Config

 into /home/danika-hous/Music
 2 folders · 14 files · 2.3 MB · 1 exists already

 Pictures/                                              13 files    2.2 MB
   holiday/                                              8 files    1.2 MB
     beach.jpg                                                      340 kB
     dunes.jpg                                                      212 kB
     … 6 more
   cat.png                                                           88 kB   exists
 notes.txt                                                          1.2 kB

 ↑ ↓ scroll · Enter copy · x clear · a d f c tabs · Esc close
```

**After Enter, if something exists already,** the foot asks once:
`1 file exists already: o overwrite · s skip · Esc back`.

**While it copies,** the second line counts: `copying… 120 of 1,400 files · 34 MB of 2.1 GB`,
and the foot offers `s stop`.

**Afterwards:** `copied 14 files (2.3 MB) into /home/danika-hous/Music`, and under it what
wasn't copied, each with its reason.

| Key | What it does |
|---|---|
| A drop, or a pasted path | Adds to the list. In any tab, unless a row is open for typing; the panel then shows Files |
| ↑ ↓, PgUp, PgDn, the wheel | Scroll the tree |
| Enter | Copies. Asks first if a file exists already |
| `o`, `s` | The answer to that question: overwrite, or skip those files |
| `x` | Clears the list, or the result of the last copy |
| `p`, or a typed `'` `"` `/` `\` | Opens a row for a typed path: for a terminal that types the drop, and for typing one by hand. A drop into it needs no Enter (step 5) |
| `s` while it copies | Stops after the file in hand. What was copied stays |
| Esc | Drops the question if one is asked. Otherwise closes the panel; the list stays |

---

## How the parts fit

```text
 the terminal ── a drop: a paste of paths ──► Panel  (hallux/panel.py)
                                                │  offers a paste to its tabs
                                                ▼
                                             Files tab  (hallux/panel_tabs/files.py)
                                                │  watch()        what to show
                                                │  drop(text)     add to the list, or why not
                                                │  start(over)    copy
                                                │  stop() clear()
                                                ▼
                                             Imports  (hallux/importing.py, the machine has one)
                                                ├─ read_drop    text ─► real paths      step 1
                                                ├─ look         the tree, in a thread   step 2
                                                ├─ carry_out    the copy, in a thread   step 3
                                                │     └─ through Disk: the fence, and files
                                                │        written beside and renamed
                                                └─ a note for the AI ──► Machine.send   step 6
```

**One import, from start to end.**

1. You press Ctrl+F12 and drag a folder onto the window. The terminal sends its path as a
   paste. The panel offers the paste to its tabs; the Files tab takes it and is shown.
2. The tab calls `drop(text)`. `read_drop` makes real paths of the text. The list notes the
   shell's directory as the destination, and a thread walks the folder: `look`.
3. The tab draws the tree from `watch()` at every redraw. The counts grow while the walk
   runs.
4. You press Enter. Nothing exists already, so the tab calls `start(False)`. A thread copies,
   file by file, through the disk's fence.
5. The tab shows the progress, then the result. A note for the AI waits.
6. You close the panel and type `ls`. The note goes in front of that message, the AI calls
   `list_dir`, and the new files are in its answer.

**The fence.** The AI can't start an import and never learns of the panel. Every path
written goes through `Disk`, so nothing is written outside the machine's folder or into
`/.hallux`, also not through a link. Reading is the other way round on purpose: the copy
reads from anywhere on the user's computer, because the user pointed at it.

---

## Decisions this plan takes

My proposals. The user decided the first two rows; the rest is open until the user has gone
through it.

| Topic | Decision | Why |
|---|---|---|
| Where a drop is taken | In the panel, in a tab of its own. **The user's decision** | A pasted path can't be told from a drop. In the panel it can mean nothing else |
| What is shown before the copy | The tree of what would be copied, scrollable. **The user's decision** | |
| The tab's name | `Files`, key `f`, between Details and Config | A, D and C are taken, so "Drop" is out. Config stays last: the panel opens on the last tab |
| A drop while another tab is shown | The Files tab takes it and is shown, unless a row is open for typing | Otherwise "Ctrl+F12, drop" loses the drop without a word: the panel opens on Config or Agents |
| A paste that isn't a path | In the Files tab the foot says why. In another tab nothing happens, as today | |
| A terminal that types the drop (VS Code's does) | The Files tab has a path row. A quote, a slash or a backslash typed in the tab opens it, and so does `p`. When the keys stop for 0.3 seconds and the text is a path that exists, it is taken | A drop that is typed can't be told from typing. In a row that is open for typing, every key is text, and no letter is a command. Windows Terminal doesn't need the row: it sends a paste. The user's first two checks were drops into VS Code's terminal, so the row is part of the plan |
| A typed drop onto another tab | Not caught: its letters are that tab's keys, as they are today | The host can't know that a drop is coming. The Files tab has to be shown first |
| Reading the paste | Three readings are tried, and the first in which every path exists wins (step 1) | Terminals quote differently, and a Windows path is full of backslashes that are no escapes. What exists decides |
| Windows paths | Translated by rule: `\\wsl$\NAME\…` and `\\wsl.localhost\NAME\…` of this distribution, and `C:\…` as `/mnt/c/…`. Where that gives nothing that exists, `wslpath -u` is asked. A path of this distribution is never asked about: `wslpath` could say nothing else (step 1, "As built") | A drop can hold hundreds of paths, and `wslpath` takes one at a call. It knows a changed mount point, which the rule doesn't. Checked on the user's machine |
| The destination | The shell's directory at the first drop of a list. It is shown, and it stays until the list is copied or cleared | The marks in the tree are worked out against it. An answer that changes the directory meanwhile moves nothing |
| More drops | They add to the list. A path that is listed already, or a second thing of the same name, is refused with a word in the foot | |
| Confirming | Enter copies. One question, and only if a file exists already: overwrite or skip | The tree is the preview. A second "are you sure" for every import would be noise |
| A folder that exists already | The two are merged, as `cp -r` does | |
| A file where a folder should go, a folder where a file should go, a link in the way | That item is skipped and marked `in the way`. Nothing is replaced | Replacing a folder by a file loses more than anyone meant. And nothing is ever written through a link |
| Something that exists only by the time of the copy | Skipped, when the question wasn't asked | Nothing is overwritten that the user wasn't asked about |
| Links in a dropped folder | Copied as links, as the machine's own `cp -r` does. A link that is dropped itself is followed | A link out of the machine is dead inside it: the fence refuses it |
| Sockets, pipes, devices | Skipped, and marked | |
| What can't be read | Marked, skipped, and the copy goes on. A full disk stops the copy | |
| A file's mode and time | The mode of a new file; an overwritten file keeps its mode. The time of the source is kept | A file from a Windows drive arrives as `rwxrwxrwx`, and the machine would list every picture as a program |
| A source that is its own target | Marked `is already here`, skipped | The user's first drop was the machine's own `Pictures` |
| A destination inside the dropped folder | That drop is refused: it would be copied into itself | |
| A huge folder | A folder lists 50 entries and then `… N more`; the tree keeps 2,000 lines. The counts are of everything | A tree of 50,000 lines is no preview |
| Who copies | A thread. The panel stays alive, and so does an answer of the AI that runs | |
| Never a half file | Every file is written beside its place under another name and renamed, as the disk does it today | An addon may read while the copy writes |
| The panel is closed while it copies | The copy goes on. The panel opens on Files while a copy runs or its result is unseen | Tying a copy to an open panel makes every key that closes it a question |
| Hallux ends while it copies | The copy is stopped; the file in hand is dropped. The hard exit kills it, and may leave one file with `.hallux-` in its name | |
| A reboot of the machine while it copies | The copy goes on | The disk outlives a boot |
| Telling the AI | A note in front of the next message of any kind, never a message of its own (step 6) | It costs nothing, and the AI doesn't answer `ls` from what it saw before |
| What the note says | The directory, the counts, and up to 20 top-level names. Not the panel, and no contents | The AI never learns of the panel |
| A job that writes the same name | Nothing to build. The landing never writes over someone else's change: the job's files land with `.new` (`hallux/jobdisk.py`). A test holds it | |
| A scripted run, a run without a keyboard | No panel, so no import | |

---

## Checked before the plan

- **What the terminal sends:** the user's drop of 2026-10-10, above. A path, in Windows
  form, at the shell prompt.
- **`wslpath -u`** on the user's machine turns that path into
  `/home/dano/hallux-distros/test-hallux/home/danika-hous/Pictures`, `C:\Users\dano\a b.png`
  into `/mnt/c/Users/dano/a b.png`, and a `\\wsl.localhost\kali-linux\…` path likewise. For
  a path of another distribution (`\\wsl$\Ubuntu\…`) it fails with exit code 1.
- **The panel gets a paste as one key.** With a throwaway script: the real `Panel` on a
  pipe, prompt_toolkit 3.0.53, a paste in paste brackets (`ESC[200~ … ESC[201~`). A tab that
  binds `Keys.BracketedPaste` got the whole text, with its backslashes, `$`, quotes and
  spaces. The letters in it chose no tab. In a tab without that binding nothing happened.
- **The landing of a job** was read, not run: `JobDisk._conflict` and `_beside`.
- **VS Code's terminal** (the user's check of 2026-10-10, run there twice): a drop arrives
  while the mouse is on. It arrives typed, without paste brackets, in the form shown under
  [What a drop is](#what-a-drop-is). A file arrives like a folder. Two drops in a row come
  with nothing between them. A click arrives as a mouse report, apart from the path.

- **Windows Terminal** (the user's check of 2026-10-10, the third run): a drop arrives
  while the mouse is on, in paste brackets, as a Windows path with backslashes and without
  quotes. Eight files dragged at once are one paste with a space between the paths.

**Not checked:**

- How a path **with a space** and a file from **`C:`** arrive, in either terminal. Step 1
  reads the forms I know: double quotes in Windows Terminal, single quotes in VS Code.
- A drop into **the panel itself.** The check ran with `cat`, with the modes the panel sets.
- Any other terminal.

---

## Before the build

| Check | Who | Before | What it decides | Status |
|---|---|---|---|---|
| **In Windows Terminal,** in a plain WSL shell, not in Hallux, run the command below. Drag onto the window, one after the other: a folder, a file from `C:` with a space in its name, two files at once. It ends by itself after 30 seconds, or with Ctrl-C, and turns the mouse off again either way. A click in the window shows as `^[[<…`: that is the mouse, which the command turns on as the panel does. A screenshot is enough | The user | Step 1 | If each drop appears as `^[[200~`, the path, `^[[201~`, a drop finds the Files tab from any tab. **If the brackets are missing,** a drop works in the Files tab's path row (step 5). **If nothing arrives,** the mouse is in the way, and the plan needs another way in | **Done on 2026-10-10, three runs.** Windows Terminal: the drop arrives with the mouse on, in brackets. VS Code's terminal (twice): it arrives with the mouse on, typed, without brackets |

```sh
(trap : INT; printf '\e[?2004h\e[?1000h\e[?1006h'; timeout --foreground 30 cat -v; printf '\e[?2004l\e[?1000l\e[?1006l')
```

The first form of this command didn't turn the mouse off by itself, and after Ctrl-C every
click and every turn of the wheel typed numbers at the prompt. `reset` ends that. This form
was tried on a pseudo-terminal, in bash and in zsh: it turns the mouse off after the 30
seconds and after Ctrl-C.

---

## Where the code goes

| File | What | Step |
|---|---|---|
| `hallux/importing.py` (new) | `read_drop`, `from_windows` | 1 |
| `hallux/importing.py` | `look`, the tree and its lines | 2 |
| `hallux/disk.py` | `copy_whole`: a file streamed beside its place and renamed; `Disk.place`: a path for a write, with a link refused | 2, 3 |
| `hallux/importing.py` | `carry_out`, the result | 3 |
| `hallux/importing.py` | `Imports`: the list, the two threads, what the tab is shown | 4 |
| `hallux/machine.py` | The machine has its `Imports`, and stops it when Hallux ends | 4 |
| `hallux/script.py` | An empty `refresh`: a scripted run has no panel | 4 |
| `hallux/statusbar.py` | `size`: `340 kB`, `2.3 MB` | 2 |
| `hallux/panel.py` | `Tab.paste`, and the host's key for a paste | 5 |
| `hallux/panel_tabs/files.py` (new) | The Files tab | 5 |
| `hallux/app.py` | The tab in the panel's row | 5 |
| `hallux/machine.py`, `hallux/prompt.md` | The note in front of a message, and what the AI is told about it | 6 |
| `README.MD`, `docs/config-panel.md`, `docs/roadmap.md` | The tab, what a drop is, where it can't work | 7 |
| `tests/test_importing.py`, `tests/test_panel_files.py` | New | 1 to 5 |
| `tests/test_disk.py`, `test_panel.py`, `test_machine.py`, `test_jobdisk.py` | More tests in each | 2 to 6 |

**The line numbers** in the steps are the code's at commit 0e4d0a8. Every step moves them,
so each reference also names what stands there.

---

## The steps

| Step | File | Needs | Status |
|---|---|---|---|
| 1. Reading a drop | [01-reading-a-drop.md](01-reading-a-drop.md) | | Built on 2026-10-10 |
| 2. The tree | [02-tree.md](02-tree.md) | 1 | Built on 2026-10-10 |
| 3. The copy | [03-copy.md](03-copy.md) | 2 | |
| 4. The machine's side | [04-imports.md](04-imports.md) | 3 | |
| 5. The Files tab | [05-files-tab.md](05-files-tab.md) | 4 | |
| 6. Telling the AI | [06-telling-the-ai.md](06-telling-the-ai.md) | 4 | |
| 7. The documentation and the user's try | [07-docs-and-try.md](07-docs-and-try.md) | 5, 6 | |

Steps 5 and 6 don't depend on each other. This table is the only place that holds the
status.

---

## Not in this plan

- **A path pasted at the shell that opens the tab.** It brings the guessing back. With the
  tree as a preview a wrong guess costs one Esc, so it may be worth it later.
- **Copying out of the machine.** The tab's name leaves room for it.
- **A word on the status bar** when a copy ends while the panel is closed.
- **A drop over ssh.** The path belongs to the computer with the window.

---

## Risks

- **Not every terminal sends a drop as a paste.** Windows Terminal does, VS Code's doesn't.
  The plan has a way in for both. What it has none for is a terminal in which nothing
  arrives while the panel has the mouse.
- **In a terminal that types the drop, a drop onto another tab presses that tab's keys.** In
  the Agents tab a `k` in the path asks whether to kill the picked job, and a `y` right
  after it kills it. That is so today, without this feature. The documentation of step 7
  says to show the Files tab first in such a terminal.
- **I can't run Windows Terminal.** The tab is tried here on a pipe and in tmux, where a
  paste stands in for the drop. The real drag is the user's try (step 7).
- **Other terminals quote in other ways.** Step 1 reads the three ways I know. A fourth
  shows as "no such file" in the foot, and is one more reading to add.
- **A hard exit in the middle of a big file leaves its unfinished copy** on the disk, under
  a name with `.hallux-` in it. The AI sees it in `ls -a`. Nothing cleans it up.
- **The AI and the copy write at the same time.** Both write beside and rename, so no file
  is ever half of each. The one that renames last is the one that stays.
- **Step 6 changes `hallux/prompt.md`,** which the user edits too. The step gives the lines
  and where they go; the user decides their words.
