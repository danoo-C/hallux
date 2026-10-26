# Step 5: the Packages tab

[The plan](README.md) · the design: [hpm.md](../../hpm/hpm.md), sections 6a, 9 and 10;
plan decisions 15, 19

**Needs:** step 4. **Changes:** new `hallux/panel_tabs/packages.py`; `hallux/panel.py` (a
tab's own `key`); `hallux/disk.py` (a lock in `memory_edit`); `hallux/app.py` (the tab in
the panel's list); `hallux/machine.py` (`<installed>`); new `hallux/hpm/running.py` (the
engine in a thread, for the tab); `tests/test_panel_packages.py`, `tests/test_panel.py`,
`tests/test_disk.py`, `tests/test_machine.py`.

After this step you can install, update and remove packages in the world you are in, from
Ctrl+F12, and the machine learns of it with your next line. The AI takes no part in it.

## Build

**The tab's key** (decision 15). `Tab` in `hallux/panel.py` gets an optional `key`; without
one it is the title's first letter, as now, and the check that two tabs don't share a key
looks at `key`. The tab row underlines the key wherever it is in the title: Packa**g**es.
Packages takes `g`. It can't take `p`: that is the Files tab's path row (`files.py`), and
the panel's letters are bound after a tab's own keys, so they win.

**The tab** (`g`, between Files and Config). It knows nothing of hpm: it is given functions,
as the Files tab is given those of `Imports`. None of its keys is a tab's letter (`a`, `d`,
`f`, `c`, `g`): those choose a tab whenever no row is open for typing.

```
 Agents  Details  Files  Packages  Config
 ───────────────────────────────────────────────────────────────────
  danika · 15 packages                          installed here: 4

  [x] kittystory      chat with characters   1.4   installed 1.3 ↑
      [x] packs       3 packs                1.0
      [x] characters  Emma, Lucy, Emilly     1.1
      [ ] memories    private
  [ ] kittyshop       SVG drawing app        2.0   needs the web addon ✗
  [ ] kittycalc       GUI calculator         1.0   installed ✓
  ...
 ───────────────────────────────────────────────────────────────────
  space tick · → extras · + all · - none · v card · u updates · r remove · Enter install
```

- **Views:** the store's packages (the default), `u` only those with an update, the
  installed ones. A filter row (`/`) for a word; while it is open the tab counts as typing,
  so its letters are the row's.
- **`+` and `-`** tick and untick every row (hpm.md section 6a's "all" and "none").
- **Enter** makes the plan (step 3) in a thread, then shows the conflicts on the same tab,
  then writes, with the progress, as the Files tab does. Esc during the write stops between
  packages, never in the middle of a file.
- **`v`:** the card, the memory line, rules and the plan's loud marks (step 3), scrollable.
- **While the AI answers.** The panel opens then too, so the tab may write app files while
  the AI works, as the Files tab may copy: the same risk drag and drop accepted, and said
  here so it is a choice. `memory.md` is the one file both write on purpose, so
  `Disk.memory_edit` takes a lock (one `threading.Lock` on the `Disk`; the tab uses
  `machine.disk`, the same object), and neither edit is lost.
- **What can't be done here:** a migration that needs the AI (step 7) says "run
  `hpm update kittystory` in your terminal" until step 7 builds it into the tab; the AI
  session of step 6 isn't started from the panel in this step.
- **The world's own mark** (step 4) is this Hallux's, so the tab writes to it.

**`<installed>`** (decision 19). `running.py` keeps the notes of what was written, as
`Imports` does (`waiting`, `told`, `forget` at a boot). `machine.py` puts them in front of the
next message beside `imported_block`:

```xml
<installed>{"packages": [{"name": "kittystory", "version": "1.4", "was": "1.3",
  "files": 214, "places": ["/usr/local/bin/kittystory", "/usr/local/share/apps/kittystory/",
  "~/.kittystory/packs/"]}]}</installed>
```

The memory line is written already (step 3), so the AI's next boot knows it too. A remove is
told the same way, with `"removed": true`.

## Tests

- The tab's drawing at 80 and 120 columns; ticking, extras, needs, the views, the filter.
- Enter → conflicts → write, with a stand-in engine; Esc stopping between packages.
- `<installed>` in front of the next message, once; forgotten at a boot; a remove told.
- The panel lists five tabs in their order, `g` chooses Packages, and `p` in the Files tab
  still opens its path row. Two tabs with the same `key` are refused, as two first letters
  are now.
- No key of the Packages tab is a tab letter.
- `Disk.memory_edit` from two threads at once: both edits are in the file.

## Done when

In a running world, Ctrl+F12, `g`, kittystory installed with its packs, Esc, and the next
`kittystory` typed at the shell starts the app the AI now knows about. Checked on a pty
through a terminal emulator first.

## As built

Built 2026-10-23: `hallux/panel_tabs/packages.py` (the tab), `hallux/hpm/running.py`
(`Installs`: the engine in a thread, the notes), a tab's own `key` in `hallux/panel.py`
(`key_of`), `Disk.memory_change` and its lock in `hallux/disk.py`, `installed_block` and the
machine's `installs` in `hallux/machine.py`, the tab in the panel's list in `hallux/app.py`;
a stop between packages in `engine.apply`; `tests/test_panel_packages.py` (18 tests), three
in `tests/test_machine.py`, and the tab lists of `test_machine.py` and `test_panel_config.py`
with five tabs. The whole suite: 2223 passed, the sandbox test left out as before.

**The run of "Done when",** on a real pty: the real `hallux` command in tmux (100 × 26,
outside the session's sandbox) on a fresh copy of `oliver-test`, with the machine tests'
pretend model in place of Claude (no model was called), and the store of step 4's run.
Ctrl+F12 opened the panel with five tabs and "a d f g c tabs" in the foot; `g` showed the
Packages tab ("local · 1 package · installed here: 0"); space and Enter showed "kittystory
1.1: 13 new · kittystory-packs 1.0: 5 new"; Enter wrote both ("2 installed", the backup,
"The machine is told with your next line"); Esc closed the panel. The tab opened again
showed "installed ✓", the memory had hpm's tagged line, and the message the pretend model
got for the next line, `kittystory`, began with `<installed>{"packages": [{"name":
"kittystory", "version": "1.1", …`; the one after it (`exit`) had none. The running mark
was gone when Hallux ended.

**Not shown in that run:** that the real AI reads `<installed>` and starts the app. That
takes a paid run, and the manual's lines about `<installed>` (step 9); it is a point of the
live-run checklist.

The run found two things, fixed before its last round: Esc after the outcome went back to
the list instead of closing the panel (so the next keys went to the tab: its `r` planned a
remove, which only asks); and the keys' row was cut at 100 columns (the view keys, `+ -
all · u updates · i installed · / find`, are in the tab's head line now).

What the code does that the step above didn't say, or says differently:

- **The tab's rows and answers are the terminal's:** it shows `screens.Checkboxes` and
  `screens.Conflicts` as its models, so ticking, needs and the conflicts' keys behave the
  same in both. `Checkboxes.summary_width` lets the tab narrow the summaries to its width.
- **After Enter the tab always shows what would be written,** even with nothing to ask
  ("kittystory 1.1: 13 new"), and writes only on a second Enter. A remove (`r`) is the same:
  "remove kittycalc 1.0: 2 files; its data stays", then Enter. Esc there writes nothing.
- **While the plan's questions are shown, the tab counts as typing,** so `o s k f r` (and
  `y n` for the old memory line) are its answers, not tabs. Esc while a plan is worked out
  or written stops it (between packages, `engine.apply(stop=…)`), and the foot says "Esc
  stop".
- **`i`** is the view of what is installed here; `u` the updates; each again goes back to
  the whole store.
- **A world with several users** can't be planned from the tab yet: it says "say which with
  --user". hpm in the terminal can, once the world is stopped.
- **The memory's lock** is `Disk.memory_change(change)`, a read, change and write under one
  lock; `memory_edit` goes through it, and hpm's lines too. This replaces step 4's "the
  machine's memory changed while hpm was writing" stop, which could only happen in the
  window this lock now closes. Between two processes (a terminal `hpm adopt` on a running
  world) there is no lock: the window is the few milliseconds of one write.
- **A bundle** is a row of its own, with "bundle of N"; an extra is shown under its app, and
  as a row of its own only when its app isn't in the store.
