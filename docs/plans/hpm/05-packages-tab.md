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
