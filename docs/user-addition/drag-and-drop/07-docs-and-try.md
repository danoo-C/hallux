# Step 7: the documentation and the user's try

[The plan](README.md)

**Needs:** steps 5 and 6. **Changes:** `README.MD`, `docs/config-panel.md`,
`docs/roadmap.md`, and this plan's status.

## Build: the documentation

| Where | What |
|---|---|
| `README.MD`, the features (line 68, "A settings panel") | One more point: files and folders are dragged onto the window while the panel is open, and land in the shell's directory |
| `README.MD`, the keys (line 156, Ctrl+F12) | The Files tab beside the other three |
| `README.MD`, the section on the panel (line 428) | A short part of its own: what a drop is (the terminal pastes a path), the tree, the question, what the AI is told. And where it can't work: over ssh, and for anything that has no path, such as a picture dragged out of a browser |
| `README.MD`, the list of files (lines 522 and 523) | `importing.py`, and `files.py` among the tabs |
| `docs/config-panel.md`, section 4 | The Files tab: its states, its keys, and that a drop in any tab finds it |
| `docs/config-panel.md`, section 9, Safety | The copy is Hallux's and the user's: the AI can't start one, every write goes through the disk's fence, and the note for the AI holds names only |
| `docs/config-panel.md`, section 12, Later | What this plan leaves out (the plan's "Not in this plan") |
| `docs/roadmap.md` | An entry for the feature |
| `hallux/panel.py`, the docstring | "The AI never learns of the panel" stays true, and gets half a sentence: it is told that files arrived |

## The user's try

In Windows Terminal, in `test-hallux`. I can't run any of this: here a paste stands in for
the drop.

| | What to do | What should happen |
|---|---|---|
| 1 | Ctrl+F12, then drag one file from `C:` onto the window | The panel shows the Files tab with one line, and the destination is the shell's directory |
| 2 | Enter, Esc, then `ls` | The file is listed |
| 3 | Drag a folder with folders in it | The tree, with counts. ↑ ↓ and the wheel scroll it |
| 4 | Drag the same folder again after copying it | Every file is marked `exists`. Enter asks; `s` copies nothing |
| 5 | Drag a file whose name has a space, and two files at once | Each is one line |
| 6 | Drag a big folder (a few thousand files), press Enter, and close the panel while it copies | The counts move while it copies. Ctrl+F12 opens on Files, with the result |
| 7 | The same, and `s` while it copies | It stops. What was copied is there, and no file with `.hallux-` in its name |
| 8 | Open the panel over a full-screen program (`htop`) and drop a file | As at the shell. After Esc the program is as it was |
| 9 | Drop while the AI is answering | As at the shell. The answer goes on |
| 10 | Drag the machine's own `Pictures` folder while the shell is in its home | `is already here`, and Enter does nothing |
| 11 | Paste a path at the shell prompt, with the panel closed | It lands on the line as text, as before |
| 12 | After an import, ask the machine "what is new in this folder?" | It knows of the files, and says nothing of a panel |
| 13 | Hallux in VS Code's terminal: Ctrl+F12, `f`, then drag a folder onto the window, and a file right after it | The path is typed into the row, and the tree appears without Enter. The file is added to it |

**Point 1 is the first drop into the panel itself.** The check before the build ran with
`cat`, with the modes the panel sets, and there Windows Terminal sent the drop as a paste
with the mouse on. If the panel shows nothing at point 1, that is the first thing to look
at: the log has a line for every paste the host was given.

A point that fails gets one line under the table: what was seen instead.

## Done when

The documentation says what the code does, the user has gone through the table, and the
plan's README has the status of every step and what the try showed.
