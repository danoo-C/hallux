# Review of the hpm design and plan, 2026-10-23

What was read: all of [docs/hpm/](hpm/README.md) (README, hpm.md, migrations.md, sharing.md)
and all of [docs/plans/hpm/](plans/hpm/README.md) (README and the nine steps), as committed
in 5d936d7. Where they name Hallux's code, the code was read. Where they describe a world,
the worlds in `~/hallux-distros/` were looked at, but not their `/etc/passwd`, which this
session wasn't allowed to read.

**In short.** The design holds together, and the plan follows it closely. Its order of steps
is sound, every step can be tested without the model, and the hard rules are Hallux's own
code, not the AI's: data is never overwritten, the fence around a world, the backup before
anything is written. The review found **5 places where the plan would break against the
code or the worlds as they are**, **6 gaps** the plan leaves for whoever builds it, and
**9 smaller mismatches** between the documents. None of them changes the design's shape.
Three of them need the user to decide (marked **Decide**).

**Taken and applied, 2026-10-23.** The user: "go all recommended, fix the docs". Every
recommendation below is written into the design and the plan, and with it the plan's 19
decisions are confirmed (decision 15 as A1 changed it). Where each point went: the plan's
README, [What the review changed](plans/hpm/README.md#what-the-review-changed). Where I
had offered a choice without picking, I picked: B6 keeps a clone of your store in `mine/`
(not `gh api`), and a private store is left for later (public only, at first).

---

## A. What would break

### A1. The Packages tab can't have the key `p` (plan decision 15) — **Decide**

The plan says `p` is free. It isn't: the Files tab's `p` opens its path row
(`hallux/panel_tabs/files.py:319`), and the user's README documents it (`README.MD:184`).
The panel binds every tab's first letter for every tab, and its keys come after the tab's,
so they win (`hallux/panel.py:239-242`). A tab named Packages would take `p` from the Files
tab, and nothing would say so.

The same rule hits keys *inside* the Packages tab. Whenever no row is open for typing, the
letters `a`, `d`, `f`, `c` (and the new tab's letter) switch tabs from anywhere. So hpm.md
section 6a's `a all` and migrations.md section 4's `a accept` would jump to the Agents tab.
A letter can't be taken by the panel if any tab uses it for itself. Today the tabs use
`y k i x s p o`.

**Options:**
1. **(Recommended)** Keep the title "Packages" and give a tab an optional `key` of its own
   (by default its first letter, as now). Packages gets `g`, underlined: Packa**g**es. That
   is a small change to `panel.py`, and nothing the user knows changes.
2. Move the Files tab's path row from `p` to another key. That changes a documented key.
3. Name the tab after the command, "Hpm", with `h`.

Inside the tab: Enter accepts a migration, as Enter goes on everywhere else, and "all" and
"none" get keys that are neither tab letters nor any tab's own keys (for example `+` and `-`).

### A2. `/.hallux` can't be reached through `Disk`, and the plan says it is

The plan's diagram says "every write into a world goes through hallux.disk … /.hallux only
for the record, backups, memory line". But `Disk` refuses everything under `/.hallux` as if
it didn't exist (`hallux/disk.py:212-217`); only `memory_read` and `memory_edit` get in.
So:

- `record.py` writes `installed.json`, the backups and the staging folder straight under
  `disk.hidden`, with `write_whole` and `copy_whole`, not through `Disk`'s methods. The plan
  should say so. That is also how they stay out of the machine's sight.
- Step 7's "a disk that writes only there" (the staging folder) can't be the world's `Disk`.
  It needs a `Disk` of its own, rooted at the staging folder, in which the AI writes by world
  paths (`~/.kittystory/characters/emma.toml` lands at `staging/home/<user>/.kittystory/…`).
  The migration session then has two disks: it reads the world from one and writes into the
  other. When it reads a path it already wrote, the answer comes from the staging folder.
  `hallux/jobdisk.py` (a job's private copies) is close to this, and is worth reusing.

### A3. The design's own example manifest fails the plan's own check

hpm.md section 3 has `app = [..., "/usr/local/share/apps/kittystory/**"]` and
`seed = ["/usr/local/share/apps/kittystory/data/state.json"]`. `state.json` matches both.
Step 1 refuses "a pattern in two kinds", and step 1's "Done when" is to check exactly this
manifest.

**Recommendation:** a file matched by two kinds takes the narrower one: `data` before `seed`
before `app`. Step 1 refuses only a file matched twice *within* one kind's rules that
contradict each other, such as the same pattern in two kinds. This is the natural way to say
"the app folder, except its data", and it is needed again for the sprites (A4).

### A4. kittystory's files aren't where hpm.md section 2 says

What `test-hallux` really has:

| hpm.md section 2 says | `test-hallux` has |
|---|---|
| `chars/<Name>/{char.md, looks.md, sprite.prev.svg}` | `chars/<Name>/{char.md, memory.md}` only; no `looks.md`, no sprite |
| `places/`, `me/` | neither. Instead `~/.kittystory/scene.md` and `~/.kittystory/assets/{places,things}.md` |
| (sprites with the characters) | per-character sprites in the **app** folder: `/usr/local/share/apps/kittystory/sprites/{emma,lucy,emilly}.svg` |
| Emma, Lucy, Emilly | folders `Emma`, `Lucy`, `emilly` (one in lowercase) |

So the `kittystory-chars` patterns of section 3 would miss `scene.md` and `assets/`, and
would ask for `places/` and `me/`, which don't exist. In step 2 a pattern that matches
nothing is an error. The characters' sprites would travel with the app, not with the
characters. Steps 1, 2 and 9 take kittystory as their example, so section 2 should be
corrected from the world before step 2 is built. migrations.md uses the same wrong 1.x
layout as its example. It is only an illustration there, but it reads as kittystory's real
layout.

### A5. `hpm install danika/*` is expanded by the shell — **Decide**

Bash expands `danika/*` whenever a folder `danika` is in the current folder. One is:
`~/hallux-distros/danika` is a world. Decision 12 invites the user to run `hpm` from there.
From `~/hallux-distros`, `hpm install danika/* --world oliver-test` reaches hpm as
`danika/bin danika/etc danika/home …`.

**Options:**
1. **(Recommended)** A store with a slash and nothing after it: `hpm install danika/`. Bash
   leaves that alone, and it reads as "everything in danika".
2. `hpm install --store danika`.
3. Keep `danika/*` and tell people to quote it. That's easy to forget.

---

## B. Gaps the plan leaves to the builder

### B1. Apps that are already installed the old way

The user's worlds already have apps installed by the machine's own install files
(`kittystory-web.update`, and `~/kittytools.hlx` "tool bundles" in `test-hallux`'s memory).
Neither the design nor the plan covers the first `hpm install` into such a world:

- Every file is `foreign`, so the conflicts screen asks about the whole app.
- The world's memory already has an untagged `kittystory: …` line under "Invented
  programs" (in `test-hallux` it lists the 1.x paths). hpm adds its tagged line next to it.
  The machine then reads two lines about one program, and they may contradict.
- **The dev world itself** (`test-hallux`) has no record after `hpm publish`. `hpm list`
  there shows nothing. An install of your own package back into it treats every file as
  foreign.

**Recommendation:** `hpm adopt NAME --world W`. It compares the world's files with a release
in the store and records the identical ones as `ours`, so later updates go quietly. A
publish adopts in its own world automatically, since the world's files *are* the release.
At install, if an untagged memory line starts with the program's name, the screen shows it
and offers to replace it with the tagged one.

### B2. When one of many packages fails, the ones that need it shouldn't install

Step 3 says one package that fails doesn't stop the others. But if `kittystory` fails,
`kittystory-chars` (`for = "kittystory"`) and everything in a bundle that needs it would
still be installed, without what they need. **Recommendation:** a failed package skips every
package that needs it, and the end line says so:
`12 installed · 1 failed: kittystory (…) · 2 skipped: need kittystory`.

### B3. The memory line from the Packages tab races with the machine's AI

The panel opens while the AI is answering (`hallux/terminal.py:357`). The AI has its own
`memory_edit` tool (`hallux/tools.py:173`), and a reply's memory is appended at
`hallux/machine.py:888`. `Disk.memory_edit` reads the file, changes it and writes it back,
with no lock (`hallux/disk.py:416-423`). If the tab's thread and the AI edit at the same
moment, one of the two edits is lost.

**Recommendation:** a lock in `Disk.memory_edit` (the tab uses `machine.disk`, the same
object, so a `threading.Lock` on it is enough). A wider question: should the tab write only
while the AI isn't answering, as the AI might be writing the same app files? Drag and drop
accepted that risk for copies. hpm could accept it too, but it should say so.

### B4. A migration copies files through the model

The notes say "Copy memory.md to memories/<name>.md, byte for byte". The session's tools
(decision 9) are read and write only. The AI would have to read every memory file and type
it out again, which makes it:

- **Costly and slow.** Memories and chat histories only grow. The design's "seconds to a
  minute" and the $1.00 cap won't hold for a big character folder.
- **Unfaithful,** exactly where migrations.md section 7 worries: the model can shorten or
  "fix" a memory as it retypes it.

**Recommendation:** a `copy(from, to)` tool in the migration session. Hallux copies the
bytes into the staging folder and the AI only says what goes where. Hallux's code can also
count lines for checks like "as many lines as …", instead of the AI.

### B5. Migrating incoming data: which note, and at which paths?

Step 7 (and migrations.md section 2): a `kittystory-chars` in format 1, installed next to
kittystory in format 2, is migrated in a temporary folder. Two things aren't said:

- **The note is in the app's package** (kittystory 2.0's `migrations/1-to-2.md`, or the
  world's copy of it), not in the data package. The data package has format 1 and no note.
- **An unpacked package is laid out as `files/root/…` and `files/home/…`,** not as a world.
  The note talks of `~/.kittystory/chars/`. The temporary folder needs to look like a world
  (a `Disk` that shows `files/home/` at `/home/<user>/`) before the note can be followed.

### B6. Pushing needs a clone of your store, and adding one needs its raw address

Step 8 says `hpm push` updates `index.toml`, "committed and pushed with `git`". That needs a
local clone of your own store repository, but `stores/` holds only downloaded indexes.
**Recommendation:** keep it in the store's folder (`mine/<store>/`, made by
`hpm store init`), or update the one file with `gh api` and skip the clone.

Also:

- `hpm store add NAME URL` should take the repository's address, as a friend would copy it.
  hpm then reads `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/index.toml`.
  The branch should be taken from GitHub, not assumed.
- GitHub serves raw files from a cache for a few minutes. A friend who refreshes right after
  a push may see the old index. That's harmless, but `hpm push`'s last line can say so.
- sharing.md section 1 says a private store works through `gh auth login`. The plan reads
  stores with `urllib` only, so private stores wouldn't work. Either say "public only, for
  now" in the plan, or download through `gh` when the store is private.

---

## C. Smaller mismatches

| # | Where | What | Fix |
|---|---|---|---|
| C1 | hpm.md, migrations.md, sharing.md, first lines | "No code, no plan" | The plan exists now: "the plan is in docs/plans/hpm/" |
| C2 | migrations.md section 4 | Still says the AI writes the new files into the world, and checks "nothing under the old paths is gone" | Plan decision 8 changes this. Write it in once the user confirms decision 8 |
| C3 | hpm.md section 7 | "hpm reuses both": `look` and `carry_out` | They copy a drop from the PC into one folder (`hallux/importing.py:278, 457`). The plan rightly reuses `copy_whole` and only the idea of the marks. Say that |
| C4 | hpm.md sections 9 and 12 | "the `Note` of importing.py, made general" | Plan decision 19 makes an `<installed>` block of its own instead. Say that |
| C5 | Step 3, "Updates" | "A file the old version had and the new one doesn't is removed if it is `ours`" | For `data` files that breaks decision 7. Say: `app` files |
| C6 | Step 3, the marks | No mark for a folder or a link where a file goes. `copy_whole` refuses those (`hallux/disk.py:123-124`). No word about making missing folders, which `copy_whole` doesn't do | Add a mark `in-the-way` (asked about or failed, as drag and drop does), and the folders made before the files |
| C7 | Step 3, the world's user | "none means `~` files can't be installed". `hallux-world` has no `/etc/passwd`, and every world gets an empty `/home/user` from the skeleton (`hallux/disk.py:43`). So `kitty-snapshot-install` has both `danika-hous` and `user` | `/etc/passwd` first. Without it, the homes under `/home` that aren't empty. Still several: ask (`--user`) |
| C8 | Step 3, addons | "the addons Hallux has, `addons.load`'s list". `load` imports every addon's Python just to learn its name | The names of `addons/*.py` in `ADDONS_FOLDER` (`hallux/app.py:25`) are enough |
| C9 | hpm.md section 10; steps 2 and 4 | "Reading (`list`, `publish`) is always allowed" on a running world. But publish writes `CHANGELOG.md` into the world, `hpm init` writes the manifest and runs an AI on the world, and `write-migration` writes notes | Allow them on a running world, since they write only under `/usr/local/share/hpm/<name>/`, and say so instead of "reading" |

Also smaller, and worth a line in the steps:

- **The running mark and reused process numbers** (decision 11). After WSL restarts,
  process numbers start low again, so a mark left by a killed Hallux can name some other
  live process, and the world stays "running" for good. Keep the process's start time in
  the mark too (from `/proc/<pid>/stat`), or check that `/proc/<pid>/cmdline` is Hallux's.
- **The test install's cost** (step 6) is a whole machine: a boot, then one line. It runs on
  whatever `Hardware` hpm gives `run_script`, and the store's cap doesn't reach it unless hpm
  passes it. Say which model and cap it runs on.
- **A bundle needs a version** to be published like any other. hpm.md section 6a's example
  has none.
- **The card review is written at the publisher's end** and travels in the archive as
  `review.md`. That is fine between friends. But one check is free and can run at the
  installer's end, in code: a package that writes files the machine reads at every boot
  (`/etc/motd`, `/etc/passwd`, `.bashrc`: `BOOT_FILES` in `hallux/disk.py`) or another
  program's card in `/usr/local/bin` is shown loudly, as rules are.
- **The manifest in the target world.** The design keeps it at
  `/usr/local/share/hpm/<name>/hpm.toml` in the world it was made in. It doesn't say whether
  an install writes it into the target world too. I'd say yes: then a friend can publish a
  fix of their own, and a copy of the world keeps it.

---

## What I would do next

1. The user decides A1 (the tab's key) and A5 (`danika/`), and confirms or changes the
   plan's 19 decisions, decision 8 above all.
2. I fix the documents: A2 to A4, B1 to B6 and C1 to C9 go into the design and the plan's
   steps, with a "What the review changed" list in the plan's README, as was done for the
   earlier plans.
3. Then step 1.
