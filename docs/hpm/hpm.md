# hpm: packages for Hallux worlds

**Status:** design declared done by the user 2026-10-23, and **built** the same day, plan
steps 1 to 5 and the AI of step 6 ([docs/plans/hpm/](../plans/hpm/README.md); what the code
does differently is in [As built](#as-built) at the end). Every question is decided, all as recommended
([Decisions](#decisions)). Changed after the review of 2026-10-23
([docs/hpm-review-2026-10-23.md](../hpm-review-2026-10-23.md), all its recommendations
taken by the user: "go all recommended"): kittystory's real files (section 2), a file two
kinds match (section 3), `danika/` for a whole store (section 6a), apps installed before hpm
(section 7a), the Packages tab's key `g` (section 10), and smaller points. Migrations are in
[migrations.md](migrations.md), sharing with friends in [sharing.md](sharing.md); this
document is the rest.

## Using it

```bash
hpm init kittystory                    # in the world it was built in: the AI drafts hpm.toml
hpm publish kittystory --all           # a release of it and its extras into your PC's store
hpm install kittystory                 # in another world: checkboxes, then the questions
hpm update                             # everything this world has that is newer
hpm list                               # what it has, and what is newer
hpm rollback kittystory                # undo its last install, update or remove
hpm adopt kittystory                   # an app this world got before hpm, recorded
```

Without `--world W`, hpm works on the world you are in. In a running world use the panel's
Packages tab instead: Ctrl+F12, then `g`. Every question has a flag for scripts
(`hpm install --help`).

## In short

1. **A package is a set of files from a world, plus a small manifest, `hpm.toml`.** It
   says which files are the app and which are your data, what the app needs, and the one
   line the machine should remember about it.
2. **There is one store on your PC, above every world.** `hpm publish` puts a release
   there, and `hpm install` copies it into any world.
3. **The AI helps where judgement is needed.** It drafts the manifest once (`hpm init`),
   drafts each changelog, and writes and runs migrations. Copying, conflicts, backups and
   the record of what was installed are Hallux's own code: exact, instant and free.
4. **Install options are checkboxes.** A package lists its extras (packs, characters,
   memories), and you tick the ones you want.
5. **Nothing of yours is overwritten without a question.** Each file in the way is either
   identical (skipped) or different (you choose: overwrite, skip, keep both).
6. **A world remembers what it installed.** That makes `update`, `remove` and `list`
   possible, and an update can tell a file you changed from one it may replace.
7. **Many packages install as one.** A whole store (`danika/`) or a bundle goes through
   one checkbox screen, one conflicts screen and one backup (section 6a).

---

## 1. What it's for, and what it isn't

**For:** moving the programs you invent in one world (their cards, web apps, data) into
other worlds on your PC and into your friends' worlds, and keeping them up to date there.

**Not for:**
- **The machine's imagined packages.** `apt install htop` inside a world installs nothing;
  the machine invents it and writes it under "Packages (changes to the base image)" in its
  memory. hpm packages are real files. The two never mix.
- **Whole worlds.** A copy of a world's folder, like `~/hallux-distros/kitty-snapshot-install`,
  is still the way to clone a machine. hpm moves one app at a time.
- **Python addons.** Addons (`addons/*.py`) are code of Hallux itself and come with the
  repository. A package can *need* an addon (section 3), but it can't carry one.

## 2. What an app is today

kittystory in `test-hallux` is spread over four places (as the world had it on 2026-10-23):

| Piece | Where it lives |
|---|---|
| The card (what the AI follows when you type `kittystory`) | `/usr/local/bin/kittystory` |
| The web app | `/usr/local/share/apps/kittystory/**` (`index.html`, `app.js`, `faces.js`, `style.css`, `app.json`) |
| The characters' sprites | in the web app's folder: `/usr/local/share/apps/kittystory/sprites/{emma,lucy,emilly,cat}.svg` |
| Its first state, and later the chat history | `/usr/local/share/apps/kittystory/data/state.json` |
| Packs | `~/.kittystory/packs/*.pack` (`tsundere`, `sensitive-sweetheart`, `dirty`) |
| Characters | `~/.kittystory/chars/<Name>/char.md` (folders `Emma`, `Lucy`, `emilly`) |
| The scene and how things look | `~/.kittystory/scene.md` (who is where), `~/.kittystory/assets/{places,things}.md` |
| Memories | `~/.kittystory/chars/<Name>/memory.md`, `~/.kittystory/shared.md` |
| What the machine knows about it | one line under "Invented programs" in `/.hallux/memory.md` |

The sprites are the one awkward piece: they belong to the characters, but live in the app's
folder, so they travel with the app (section 3). An app that wants its characters to travel
alone keeps their sprites beside them, under `~/.kittystory/`.

Today the machine moves all this with files it writes itself, like `kittystory-web.update`:
a README the AI follows in the target world, step by step. That works, but each install
costs a model call, can go slightly differently each time, and needs a new file each time
the app changes.

## 3. A package

A package is a folder (in the store, a single archive) with:

```
kittystory-1.4/
  hpm.toml              the manifest
  CHANGELOG.md          what changed, newest first
  files/root/...        files under / of a world: files/root/usr/local/bin/kittystory
  files/home/...        files under the user's home: files/home/.kittystory/...
  migrations/           notes for the AI when the data format changes (migrations.md)
```

The manifest:

```toml
name = "kittystory"
version = "1.4"
summary = "Chat with characters built from personality packs"
author = "danika"
data_format = 2                              # migrations.md

requires.addons = ["web"]                    # the app's -w mode needs the web addon
requires.packages = []

memory_line = "kittystory: split-screen chat with characters made from personality packs; ..."

[files]
app  = ["/usr/local/bin/kittystory", "/usr/local/share/apps/kittystory/**"]
seed = ["/usr/local/share/apps/kittystory/data/state.json"]   # installed only if missing
data = []                                    # this package carries no data of its own

[extras]                                     # the checkboxes at install
packs      = { package = "kittystory-packs",    default = true }
characters = { package = "kittystory-chars",    default = true,  needs = ["packs"] }
memories   = { package = "kittystory-memories", default = false, needs = ["characters"] }
```

**Three kinds of files.** This is what makes updates safe:

| Kind | Install | Update |
|---|---|---|
| `app` | copied | replaced, unless you changed the file since it was installed (section 7) |
| `seed` | copied only if missing | never touched |
| `data` | copied, conflicts asked (section 7) | never overwritten; changed only by a migration ([migrations.md](migrations.md)) |

**A file two kinds match** takes the narrower kind: `data` before `seed` before `app`. So
`app = ["/usr/local/share/apps/kittystory/**"]` with `seed = [".../data/state.json"]` means
"the app's folder, but its first state only if missing". Two packages of the same app (the
app and its extras) may not carry the same file: publish refuses it and names the file.

**Paths.** `/…` is a path in the world. `~/…` is the home of the world's user, whatever
their name is (`danika-hous` in one world, `user` in another; section 6).

**Extras are packages of their own.** `kittystory-packs`, `kittystory-chars` and
`kittystory-memories` each have their own manifest, version and changelog, so you can
publish new characters without releasing the app again. The main package only lists them.
A data package has `data` files and no card:

```toml
name = "kittystory-chars"
version = "1.1"
data_format = 2
for = "kittystory"                           # useless without it; installs it first
[files]
data = ["~/.kittystory/chars/*/char.md", "~/.kittystory/scene.md", "~/.kittystory/assets/**"]
```

`kittystory-memories` carries `~/.kittystory/chars/*/memory.md` and `~/.kittystory/shared.md`,
so no file is in both.

`kittystory-memories` is private by default, so it never leaves your PC
([sharing.md](sharing.md), section 3).

**The memory line** is what the machine should know about the program: the line it would
write under "Invented programs" itself. Hallux puts it there at install (section 9).

**Rules are not part of a package by default.** kittystory's look leans on the world's pink
kitty theme, which is a rule in `memory.md`, not a file. A package may carry rules (an extra
like `kittystory-theme` with `rules = ["..."]`), but they change the whole machine, so the
install screen shows them loudly (decision 5).

## 4. The store on your PC

```
~/.local/share/hallux/hpm/
  config.toml                 the model, effort and cap for AI work; the base world for tests
  local/                      what you published yourself
    kittystory/
      1.3.hpm
      1.4.hpm                 an archive: the folder of section 3, in one file
  stores/                     friends' stores, copied from GitHub (sharing.md)
    oliver/index.toml
  mine/                       a clone of your own store on GitHub, for `hpm push`
    danika/
  cache/                      downloaded packages
```

A world can't see this folder. The AI inside a world can't reach it either: the world's
disk tools stay fenced to the world's own folder. Only Hallux's own code reads the store
and copies from it.

## 5. Publishing

**Once per app: `hpm init kittystory --world test-hallux`.** The AI reads the card, the
memory line and the files around them, and drafts `hpm.toml`: which files are `app`, which
are `seed`, which extras there should be and what goes in each, and the memory line. You
read it and change what's wrong. The manifest is saved in the world, beside the app, at
`/usr/local/share/hpm/kittystory/hpm.toml`, so the next publish needs no AI to find the
files again. An install writes the manifest (and the migration notes) to the same place in
the world it installs into, so a friend can publish a fix of their own, and a copy of the
world keeps them.

**Every release: `hpm publish kittystory`.** Hallux's code, with the AI for two things:

1. **Collects the files** the manifest lists. A pattern that matches nothing is an error:
   the app moved something, and the manifest has to follow.
2. **Version.** It must be higher than the last one in the store. hpm suggests one: a
   small bump (1.3 → 1.4) when only `app` files changed, a big bump (1.4 → 2.0) when
   `data_format` went up.
3. **Changelog.** The AI compares the files with the last release in the store and drafts
   the entry, and you edit it.
4. **Data format.** If the paths of `data` files changed since the last release and there
   is no migration for it, publish stops and offers to have the AI write one
   ([migrations.md](migrations.md), section 3).
5. **Test install, if you want it.** hpm copies a clean world (the base world named in its
   `config.toml`), installs the package there, and the AI starts the app once and reports
   what is missing. It costs a model call, so it is a question, not a step (decision 6).
6. **Writes `kittystory/1.4.hpm`** into `local/`, and records the release in the world it
   came from (section 8), whose files *are* that release: `hpm list` there shows it, and
   the next update there knows the files as hpm's.

Publish writes into the world only under `/usr/local/share/hpm/<name>/` (the manifest, the
changelog, migration notes) and the world's record, so it works on a running world too.

`hpm publish --all` publishes the main package and every extra that changed.

## 6. Installing

`hpm install kittystory --world ~/hallux-distros/oliver-test`:

```
kittystory 1.4  ·  Chat with characters built from personality packs  ·  by danika

  [x] kittystory     the app and its card              needs the web addon ✓
  [x] packs          3 packs                           kittystory-packs 1.0
  [x] characters     Emma, Lucy, Emilly                kittystory-chars 1.1 · needs packs
  [ ] memories       their memories and chat history   kittystory-memories 1.0 · needs characters

  This adds to the machine's memory:
    kittystory: split-screen chat with characters made from personality packs; ...

  space toggle · Enter install · v view the card · q cancel
```

- **Needs.** Ticking `characters` ticks `packs`. Unticking `packs` unticks `characters`.
- **Addons.** If the world doesn't get the web addon (its `addons` setting) or Hallux
  doesn't have it, the row says so. You can still install; the app's `-w` mode just won't
  work there.
- **The card can be read before installing** (`v`). A card is instructions to the AI that
  runs the machine; [sharing.md](sharing.md), section 4.
- **The user.** `~/…` goes to the home of the world's user, read from its `/etc/passwd`
  (the users with uid 1000 or more and a home under `/home`). A world without
  `/etc/passwd` (`hallux-world` has none) gives the homes under `/home` that aren't empty:
  every world gets an empty `/home/user` when it is made, so that one doesn't count by
  itself. If there are several, hpm asks (`--user`).
- **The order:** the extras' requirements first, then the app, then data. A failure in the
  middle leaves what was written in the world's record (section 8), so `hpm remove` can
  clean it up.

## 6a. Many packages at once

A store can hold any number of packages, and one command can install all of them, or a
chosen set. (Added 2026-10-23: the user asked "i can have my danika store that has like 15
apps? and can i install all 15 in one command?", and liked the answer.)

**Two ways to say "all of them":**
- **The whole store:** `hpm install danika/ --world ~/my-world`: the store's name with a
  slash and nothing after it. (Not `danika/*`: bash expands that whenever a folder
  `danika` is where you stand, and `~/hallux-distros/danika` is a world.)
- **A bundle:** a package with no files of its own, only a list of packages. It is
  published and pushed like any other, so it has a version too.
  ```toml
  name = "kitty-desktop"
  version = "1.0"
  summary = "All of danika's kitty apps"
  bundle = ["kittystory", "kittymusic", "kittydash", "kittycalc", "kittyshop", "kittyfiles"]
  ```
  `hpm install danika/kitty-desktop` installs the set.

**One screen for all of it.** One row per package, and its extras fold open under it:

```
danika · 15 packages

  [x] kittystory      chat with characters          ▸ packs, characters
  [x] kittymusic      music player and composer     ▸ songs
  [x] kittydash       GUI dashboard
  [ ] kittyshop       SVG drawing app               needs the web addon ✗
  ...
  space toggle · → open extras · + all · - none · Enter install
```

(`+` and `-`, not letters: in the panel's Packages tab, letters like `a` choose a tab.)

**What happens on Enter:**

1. **Everything is checked first.** The walk of section 7 goes over every file of every
   ticked package before anything is written, and the conflicts come on one screen,
   grouped by package, with "overwrite all" and "skip all" across all of them.
2. **The order follows needs:** a package that another one needs goes first.
3. **One backup** of everything the install touches ([migrations.md](migrations.md),
   section 4, for all the packages together).
4. **One package after another**, each written into the world's record (section 8) as it
   ends. One that fails doesn't stop the others, but every package that needs it (an extra
   of it, a package that requires it) is skipped. The end says
   `12 installed · 1 failed: kittystory (…) · 2 skipped: need kittystory`, and
   `hpm install` of the failed one tries again.
5. **Migrations one at a time.** Each package that needs one shows its own plan and waits
   for its own Enter: each changes your data.
6. **The machine is told once:** every memory line, and one note naming every package
   (section 9).

`hpm update --world …` works the same way: every package with a newer version, on one
screen, in one go. The panel's Packages tab (section 10) shows a store and a bundle the same
way.

**What it costs the machine.** Every package adds a line to `memory.md`, which the AI reads
at every boot. Fifteen short lines are fine; a world with a hundred packages would start to
cost more per boot. hpm keeps memory lines to one line each, and publish warns about a long
one.

## 7. Conflicts

Before writing anything, hpm walks every file it would write and sorts them into:

| What's in the way | What hpm does |
|---|---|
| Nothing | writes it |
| The same file | skips it, silently |
| A different file hpm installed, and you haven't changed it since | an update replaces it |
| A different file you changed, or one hpm didn't install | asks |
| A folder or a link where the file goes | asks: it can be skipped, never written through |

Folders a file needs are made first.

When it asks, it groups files by what they are, not one by one:

```
3 packs are already installed here:
  tsundere.pack               the same — skipped
  metal-head.pack             different   [o]verwrite  [s]kip  [k]eep both
  sensitive-sweetheart.pack   different   [o]verwrite  [s]kip  [k]eep both

  O overwrite all · S skip all · Enter go on
```

- **Keep both** writes the package's file beside yours as `metal-head.hpm-new.pack`.
- **Memories are asked about more carefully.** For `memory.md` and `shared.md` there is a
  fourth choice, **merge**: the AI keeps the dated lines of both, without repeats. The
  default for memories is skip, never overwrite.
- **The drag-and-drop work does this already, for a drop.** Its tree (`hallux/importing.py`,
  `look`) marks "what is in the way" before a copy, and its copy (`carry_out`) never
  replaces a file the user wasn't asked about. Those two copy things from your PC into one
  folder, so hpm doesn't call them: it takes their way of marking, and their file copy,
  `copy_whole` (`hallux/disk.py`), which never shows a half-written file.

## 7a. Apps installed before hpm

Your worlds already have apps the machine installed by its own install files
(`kittystory-web.update`). To hpm, those files are foreign, and the world's memory already
has an untagged line about the app. So:

- **`hpm adopt kittystory --world …`** compares the world's files with a release in the
  store. The identical ones are recorded as hpm's (section 8), so later updates replace them
  without a question; the different ones stay foreign, and an update asks about them. The
  world you publish from adopts by itself at publish (section 5).
- **The old memory line.** When an install or an adopt finds an untagged line under
  "Invented programs" that starts with the program's name, it shows it and offers to replace
  it with the tagged one (default: replace), so the machine doesn't read two lines about one
  program that may disagree.

## 8. What a world remembers

Each world gets `/.hallux/hpm/installed.json`:

```json
{
  "kittystory": {
    "version": "1.4", "from": "local", "installed": "2026-10-23T14:02",
    "data_format": 2, "extras": ["packs", "characters"],
    "files": { "/usr/local/bin/kittystory": "sha256:9f2…", "…": "…" }
  }
}
```

It lives in `/.hallux`, so the machine can't see it or change it. With it:

- **`hpm list --world …`** shows what is installed, and which are behind the store.
- **`hpm update kittystory`** knows, by each file's fingerprint, which files you changed
  since the install (section 7), and which `data_format` the world's data is in
  ([migrations.md](migrations.md)).
- **`hpm remove kittystory`** deletes the `app` files and the memory line. Data stays
  unless you add `--data`, and then it goes to a backup first.
- **`hpm update --all`** goes over every package of the world.
- **`hpm adopt kittystory`** records an app that was there before hpm (section 7a).

`installed.json`, the backups and a migration's staging folder are written by hpm's own code
straight into the world's `.hallux` folder. The world's `Disk` refuses every path under
`/.hallux`, as it should: what a package carries goes through the `Disk`, so it can never
land there.

## 9. Telling the machine

The AI must know what changed, or it answers from what it saw before.

- **The memory line.** Hallux writes it under "Invented programs" in `/.hallux/memory.md`,
  with a tag at its end, `[hpm kittystory 1.4]`, so the next update finds and replaces the
  line instead of adding a second one. The AI may still write about the program on other
  lines; hpm only owns the tagged one. The machine's AI edits `memory.md` too, and the
  Packages tab may write while it answers, so every edit of `memory.md` takes one lock (in
  `Disk.memory_edit`); neither edit is lost.
- **A note before the next message.** If the world is running (section 10), the machine
  gets a note in front of the AI's next message: "kittystory 1.4 was installed: 214 files
  under /usr/local/…, ~/.kittystory/…". It is an `<installed>` block of its own, told the way
  drag and drop tells a copy with `<imported>` (`imported_block` in `hallux/machine.py`).
- **At the next boot** the memory line is enough: the AI reads `memory.md` when it boots.

## 10. Where you type it

| Where | How | When |
|---|---|---|
| **Your real terminal** | `hpm install kittystory --world ~/hallux-distros/oliver-test`: a program of its own, with real checkboxes; works while the world isn't running | first |
| **The settings panel** (Ctrl+F12) | a **Packages** tab beside Files, chosen with `g` (Packa**g**es): the store's packages, the checkboxes, the conflicts, for the running world | second |
| **The world's shell** | `hpm install kittystory` typed in the machine: the AI draws the screens and calls one tool that does the copy | later, maybe |

The panel is drawn by Hallux, not the AI, like the Files tab, so it keeps the first
principle of [concept.md](../concept.md): every character on the machine's screen comes from
the AI, and the panel is not the machine's screen.

**The tab's key.** The panel chooses a tab by its first letter, but `p` is the Files tab's
own key (it opens the path row), and the panel's letters win over a tab's keys. So a tab
gets an optional key of its own, and Packages takes `g`. Inside the tab no key is a tab's
letter (`a`, `d`, `f`, `c`, `g`): a migration is accepted with Enter, and "all" and "none"
are `+` and `-`.

**Inside a world, `hallux <anything>` reshapes the machine** (concept.md, principle 5). So
`hallux publish kittystory` typed in a world would be read as a wish, not a command. The
command is `hpm`, in your real terminal, and the Packages tab in the panel.

**A running world.** Hallux doesn't mark a world as running today. hpm needs that: a
running Hallux writes `/.hallux/running` (its process number and the time that process
started) and removes it when it ends. A mark whose process is gone, or is another program
that got the same number later (WSL hands out low numbers again after a restart), counts as
not running. An `hpm` in your terminal won't install, update, remove or roll back in a
running world; it says to use the panel's Packages tab there, or to stop the world. `list`,
`show`, `publish`, `init` and `adopt` are allowed: they write only under
`/usr/local/share/hpm/<name>/` and the world's record.

## 11. Where the AI runs

`hpm init`, a changelog, a merge of memories and a migration need the AI. From your real
terminal, there is no machine running, so hpm starts a short session of its own on the
world: the Agent SDK, the world's disk tools (fenced to that world, as always) and a prompt
of its own for the job, like the addon agents' `hallux/agent.md`. Its model, effort and a
cap per job are in the store's `config.toml`. The cost is shown when it ends, the way a job's
cost is.

From the panel, the same session runs beside the machine, like an addon agent's job.

## 12. What has to change in Hallux

- A new command, `hpm` (`[project.scripts]` in `pyproject.toml`), and its package,
  `hallux/hpm/`: the manifest, the store, install, conflicts, the world's record.
- `/.hallux/running`, written and removed by `hallux/app.py`.
- The Packages tab, `hallux/panel_tabs/packages.py`, and a key of its own for a tab in
  `hallux/panel.py` (section 10).
- `<installed>` in front of the AI's next message, beside drag and drop's `<imported>`
  (`hallux/machine.py`).
- A lock in `Disk.memory_edit` (`hallux/disk.py`), so the tab and the machine's AI never
  lose each other's edit of `memory.md`.
- The session for AI work outside a running machine (section 11), built from what
  `hallux/agents.py` has.
- The manual: the machine should know what `[hpm …]` in its memory means, and that it
  doesn't install hpm packages itself.

## Decisions

All decided as recommended (the user, 2026-10-23: "i read trogh the questions and go all
recommended").

| Question | Decision |
|---|---|
| 1. One package with parts, or separate packages joined as extras? | **Extras** (section 3): each part has its own version, so characters can be released without the app |
| 2. Where is the manifest kept in the world? | `/usr/local/share/hpm/<name>/hpm.toml`, beside the app's other files, so it moves with a copy of the world |
| 3. Where is the store? | `~/.local/share/hallux/hpm/`, the usual place for a program's data on Linux |
| 4. Who owns the memory line? | hpm owns the one tagged `[hpm name version]`; the AI may write others about the same program |
| 5. Can a package carry rules? | Yes, but only in an extra of its own, unticked by default, shown loudly at install |
| 6. Is the test install part of publish? | Asked each time, default no; `--test` to always do it |
| 7. Is `hpm` typed inside a world wanted at all? | Not in the first version. The terminal and the panel are enough; decide after using them |
| 8. Is the name `hpm` right? | Yes, unless it clashes with something on your PC; `hpm` is short and says what it is |

## Order of work

The plan ([docs/plans/hpm/](../plans/hpm/README.md)) builds it in nine steps, and brings the
Packages tab forward to step 5. The order as this design first had it:

1. The manifest and the package archive; `hpm publish` without the AI (a manifest you write
   by hand).
2. The store on your PC; `hpm install` from the terminal with checkboxes, conflicts, the
   world's record, the memory line.
3. `update`, `remove`, `list`; `/.hallux/running`.
4. The AI's session (section 11): `hpm init`, changelogs, merging memories.
5. Migrations ([migrations.md](migrations.md)).
6. Stores on GitHub, `hpm push` ([sharing.md](sharing.md)).
7. The panel's Packages tab, and the note to a running machine.
8. The manual, the docs, a live run with kittystory between two worlds.

## As built

Built 2026-10-23 in `hallux/hpm/` (`manifest.py`, `archive.py`, `world.py`, `store.py`,
`publish.py`, `record.py`, `engine.py`, `screens.py`, `cli.py`, `running.py`, `ai.py`,
`assist.py`, `prompts/`) and `hallux/panel_tabs/packages.py`. Each step of the plan has its
own "As built" with the details; what the code does differently from this document:

- **Versions:** `1.4` and `1.4.0` are one version; a leading zero is refused. A pattern's
  `**` at the end is what is inside the folder, not the folder.
- **The archive** keeps no modes and no owners, and its layout is strict (`hpm.toml`,
  `CHANGELOG.md`, `review.md`, `files/`, `migrations/`); it is read twice at unpack, once to
  check, once to write.
- **Publish** suggests the next version (`--yes` takes it), opens the changelog entry in
  `$EDITOR` (or `--changelog`, or the AI's draft with `--draft`), asks about privacy for a
  data package (`--private`), and adopts its own world afterwards, so `hpm list` there shows
  what was published. A clean seed at `/usr/local/share/hpm/<name>/seed/<path>` is published
  in place of the world's own. The AI's review of the card is asked for (`--review`), not
  always made: it costs a call each time.
- **Install:** every question is answered before anything is written; without a terminal
  each needs its flag (`--extras`, `--overwrite all|none`, `--old-line replace|keep`,
  `--user`, `--yes`). "Merge" is offered for `memory.md` and `shared.md`: the AI merges,
  hpm refuses a merge that drops a line, and you see the text before it is written. An
  extra that is installed already at the same version is left alone.
- **A NAME** is `kittystory`, `local/kittystory` or `danika/kittystory`, `local/` or
  `danika/` for a whole store; a name in two stores is asked about.
- **The world's record** keeps each package's memory line, rules, home and store (`from`);
  a package that failed in the middle is marked `incomplete` and counts as new.
- **A running world:** Hallux writes `.hallux/running` (`{"pid", "start"}`) while it runs,
  and the terminal hpm refuses install, update, remove and rollback there. The memory is
  changed under one lock, so the machine's own edit and hpm's line never cross.
- **The Packages tab** is `g`, counts as typing while it asks (so `o s k f r m` are answers
  there), shows every store's packages, `R` refreshes friends' stores in a thread, and
  `<installed>` reaches the machine with the next line: names, versions, places, and
  `data_migrated` when a migration moved its data. The machine's manual
  (`hallux/prompt.md`) says what to do with it, and with the `[hpm …]` lines in memory.
- **hpm's AI** runs with the store's `config.toml` (`model`, `effort`, `cap_usd`,
  `base_world`; default the world's model, `medium`, $1.00 a session), always after a
  question that names the model and the cap; the tests can't reach it
  (`HALLUX_NO_REAL_MODEL`).
- **Not built:** a world with several users can't be planned from the Packages tab (the
  terminal's `--user` can).
