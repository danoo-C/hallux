# hpm, from zero

A walk through hpm, the Hallux package manager, in the order you'll need it. You don't need
to read the rest of `docs/hpm/` to use it. Start at the top; stop when you have what you
came for. Section 14 is a cheat sheet, and section 15 lists the errors you're most likely
to see.

The example all the way through is kittystory: built in one world, moved into another.

---

## 1. The idea in one minute

You build an app in one world. Before hpm, you'd ask that machine for an install file
(`kittystory-web.update`), copy it to another world, and ask that machine to install it.
Every time.

With hpm:

```
 the world you built it in          the store on your PC             any other world
 ─────────────────────────          ────────────────────             ───────────────
   kittystory's files      ──publish──►  kittystory 1.0    ──install──►  kittystory 1.0
   your characters, packs                kittystory-packs 1.0             (you pick which
                                         kittystory-chars 1.0              extras come along)
```

- **publish** takes a snapshot of the app's files out of a world, into the store.
- **install** puts that snapshot into another world.
- Change the app, **publish** again (1.1), then **update** the other worlds.

That's all of it. Everything else in this tutorial is detail on those three.

If you know git, it's a bit like this: the store is a repository on your PC, `publish` is
a commit, and `install` and `update` are a checkout. Unlike git, hpm never touches your own
data without asking.

---

## 2. Six words to know

| Word | What it is |
|---|---|
| **world** | A Hallux machine: a folder with `.hallux/` in it, like `~/hallux-distros/oliver-test`. hpm works on the world you `cd` into, or the one `--world` names. |
| **package** | One app, or one part of an app's data, with a name and a version: `kittystory 1.0`. |
| **manifest** | A package's `hpm.toml`: its name, version, and which files are in it. It lives in the world it was built in, at `/usr/local/share/hpm/<name>/hpm.toml`. |
| **store** | Where published packages wait, on your PC, outside every world: `~/.local/share/hallux/hpm/`, or the folder `$HPM_HOME` names. Your own packages are in the store called `local`. |
| **extras** | Packages that belong to an app and come with it as checkboxes: kittystory's packs, characters, world, memories. Each is a package of its own (`kittystory-packs`), so it has its own version. |
| **file kinds** | Each file in a package is `app`, `seed` or `data`. The kind decides what happens on an update (below). |

The three kinds matter most, so here they are side by side:

| Kind | Example | Install | Update |
|---|---|---|---|
| `app` | the card, `/usr/local/share/apps/kittystory/**` | copied | replaced with the new version (a file you changed is asked about) |
| `seed` | `state.json`, the app's first state | copied only if missing | never touched |
| `data` | `~/.kittystory/chars/*/char.md`, packs | copied (asked if one is there) | never touched; only a migration changes it (section 10) |

`~/` in a manifest means the home of the world's user, whatever their name is in that world.

---

## 3. Once: setting it up

```bash
cd ~/IT/hallux && python3 install.py              # puts .venv/bin/hpm there
export PATH="$HOME/IT/hallux/.venv/bin:$PATH"     # so `hpm` works from any folder
export EDITOR=nano                                # hpm opens manifests and changelogs in it
hpm --help
```

Put the two `export` lines in your shell's startup file (`~/.zshrc` or `~/.bashrc`) if you
want them in every terminal.

**A store just for trying things:** `export HPM_HOME=~/hpm-try`. hpm then uses that folder
instead of your real store. `rm -rf ~/hpm-try` empties it again.

---

## 4. Your first package

Do this in the world where you built the app.

### 4a. `hpm init`: let the AI write the manifests

```bash
cd ~/IT/hallux/test-hallux          # the world kittystory was built in
hpm init kittystory
```

hpm asks first: it uses the AI and costs money (it shows the model and the cap; about $0.25
for kittystory). The AI reads the card and the files, and writes a manifest for the app and
one for each extra it sees (packs, characters, memories…). hpm then shows you all of them.

**What to look at:**
- The app's manifest lists the card and the app's folder as `app`, and its first state as
  `seed`.
- Your data (characters, packs) is in extras, as `data`.
- The memories package says `private = true`: it never leaves your PC (section 11).
- `author = …`: if you'll share with friends on GitHub, that line becomes public.

At the end it asks `edit …/kittystory/hpm.toml before it is kept? [y/N]`. Say **N** if it
looks right. You can always edit any manifest later with nano: they're plain files in the
world, at `/usr/local/share/hpm/<name>/hpm.toml`.

You only run `init` once per app. For an app without the AI, write `hpm.toml` by hand
([hpm.md](hpm.md), section 3, has the format).

### 4b. `hpm publish`: put a release into the store

```bash
hpm publish kittystory --all --changelog "First release"
```

- `--all` publishes the extras too, each one that changed.
- It asks the version of each (Enter takes the one it suggests).
- `--changelog` is the entry for this release. Without it, nano opens for each package with
  a `## 1.0 (date)` line: write a line under it, then Ctrl+O, Enter, Ctrl+X. If you quit
  without writing, the publish stops ("the changelog entry is empty") and nothing is
  written.
- It may ask whether a package with data is private, and whether the AI should review the
  card. Both are yours to decide.

Check what's in the store now:

```bash
hpm show kittystory          # its versions, files and changelog
hpm search kitty             # every package whose name or summary has "kitty"
hpm list                     # what this world has: publishing adopts your own packages
```

Publishing twice with nothing changed is refused: there's nothing new to release.

---

## 5. Installing into another world

```bash
hpm install kittystory --world ~/hallux-distros/oliver-test
```

(Or `cd` into the world and leave `--world` out.) The world must not be running: from a
terminal, hpm refuses a running world. For a running one, use its Packages tab (section 6).

### The checkbox screen

```
 kittystory 1.0  ·  Pink split-screen chat…
 [x] kittystory
   [x] packs
   [x] characters
   [x] world
   [ ] memories
```

| Key | Does |
|---|---|
| ↑ ↓ | move |
| space | tick or untick |
| → ← | open or close a package's extras |
| + − | tick all, untick all |
| v | show the card (and its review) |
| Enter | go on |
| q | cancel; nothing is written |

An extra that needs another one (characters need packs) ticks it along.

### The conflicts screen

It only comes when a file is already where a package wants to put one:

| Key | Answer |
|---|---|
| o | overwrite it |
| s | skip it: yours stays, the package's isn't installed |
| k | keep both: the package's goes next to it under another name |
| m | merge (only `memory.md` and `shared.md`; the AI does it, and it's refused if a line would be lost) |
| f | fail: stop everything, nothing is written |
| O / S | overwrite all / skip all |
| Enter | go on |

Each row says why it's asking: "different, not hpm's", "you changed it", or "a folder or a
link is there".

### What install writes

- **A backup first,** in the world's `.hallux/hpm/backups/`, of every file it will change.
- **The files.**
- **A record,** `.hallux/hpm/installed.json`: which package, which version, which files.
- **One line in the machine's memory,** tagged `[hpm kittystory 1.0]`, so the machine knows
  the app is there. If the machine already had its own line about the app, hpm asks
  whether to replace it.

The machine is told what was installed in front of your next message.

---

## 6. From inside a running world: the Packages tab

In a running world: **Ctrl+F12**, then **`g`**. It's the same as the terminal, inside
Hallux.

| Key | Does |
|---|---|
| ↑ ↓ | move |
| space | tick a package |
| → | its extras |
| v | its card |
| r | remove it from this world |
| Enter | install what's ticked (then the same checkboxes and questions) |
| u / i | show only updates / only what's installed here |
| / | find by word |
| + − | tick all, untick all |
| R | download friends' stores again (only with a friend's store added) |
| Esc | back |

---

## 7. A new version

You changed kittystory in the world you built it in. To get the change everywhere:

```bash
cd ~/IT/hallux/test-hallux
hpm publish kittystory --all          # it suggests 1.1; on a terminal it offers the AI's changelog draft
```

Then, in each other world:

```bash
hpm update --world ~/hallux-distros/oliver-test             # everything with a newer version
hpm update kittystory --world ~/hallux-distros/oliver-test  # just that one
hpm list --world ~/hallux-distros/oliver-test               # "↑ 1.1 in the store" marks what is newer
```

What the update does, by kind (section 2): `app` files are replaced (one you changed is
asked about), `seed` and `data` files are never touched. So your characters and chats stay
as they are.

**Publishing from another world.** A world that installed kittystory has its manifest
too, so you can change the app there and `hpm publish kittystory` from it. It sends the
release's clean seeds (install keeps a copy in `/usr/local/share/hpm/kittystory/seed/`),
not that world's played-in ones. hpm doesn't merge: before you change the app in a world,
`hpm update kittystory` there, or the next publish from it drops what another world added.

---

## 8. Undo

```bash
hpm rollback kittystory --world W      # undo kittystory's last install, update or remove
hpm remove kittystory --world W        # take the app out; its data stays
hpm remove kittystory --data --world W # its data too (backed up first)
hpm backups --world W                  # list the backups
hpm backups --clean --world W          # delete them (asks first)
```

A rollback puts back exactly what was there before, from the backup, including the old
version in the record and the old memory line.

---

## 9. A world that already had the app: `hpm adopt`

A world that got kittystory the old way, from an `.update` file, has the files but no
record. hpm doesn't know them yet. Adopt tells it:

```bash
hpm adopt kittystory --world ~/hallux-distros/sofi-hallux
```

It compares the world's files with the release in the store. Files that are the same are
recorded as kittystory's; the others stay as they are, and a later update asks about them.
`--version 1.0` compares with that version instead of the newest.

---

## 10. When the app changes how it stores data: migrations

Say kittystory 2.0 keeps characters in `~/.kittystory/characters/<name>.toml` instead of
`~/.kittystory/chars/<Name>/char.md`. An update never touches data, so a world updated to
2.0 would still have `chars/`, which 2.0 can't read. A migration fixes that.

**When you publish:**
1. In the manifest of each package whose data moved, change its `data = [...]` paths and
   raise `data_format` (1 → 2). The app's own manifest gets `data_format = 2` too.
2. `hpm publish kittystory --all`. It sees that the data moved and offers to have the AI
   write a note, `migrations/1-to-2.md`: how the old files become the new ones. Read it. It
   goes into the release.

**When a world updates:**
1. `hpm update kittystory`. hpm sees that the world's data is in format 1.
2. The AI reads the note and shows a plan: which files become which (Emma, Lucy, Emilly…).
   Enter goes on.
3. It writes the new files into a staging folder at the side. Your real files aren't
   touched yet.
4. The checks: hpm and the AI check the result. `l` shows the staged files.
5. Enter accepts: the new files go in, the old ones go, and 2.0 is installed. `r` rolls it
   back instead, and nothing changes.

`hpm rollback kittystory` afterwards brings back the old data and the old version together.
Each migration costs an AI session, and hpm asks before it starts.

---

## 11. Sharing with friends

Friends get your packages through a public GitHub repository. You need `gh` (signed in
with `gh auth login`) and `git`.

**You, once:**

```bash
hpm store init dano --repo YOUR-GITHUB-NAME/hpm-store    # makes the public repository
```

**You, each time you want friends to have a release:**

```bash
hpm push kittystory kittystory-packs kittystory-chars    # or: hpm push --all
hpm yank kittystory 1.1                                  # a bad release: nobody gets it by default
```

Packages marked `private = true` (the memories) are refused: they never leave your PC.

**Your friend, once:**

```bash
hpm store add dano https://github.com/YOUR-GITHUB-NAME/hpm-store
```

**Your friend, to install:**

```bash
hpm install dano/kittystory --world ~/their-world
hpm list --world ~/their-world               # "(from dano)"
hpm store refresh                            # see your newest pushes
```

GitHub can take a few minutes to show a new push; `hpm store refresh` later picks it up.
A name that's in two stores is asked about; `dano/kittystory` and `local/kittystory` say
which one.

---

## 12. Many at once

```bash
hpm install local/ --world W             # every package in your store, on one screen
hpm install dano/ --world W              # every package in a friend's store
```

Write the trailing slash and nothing after it (`dano/*` would be expanded by the shell).
It's one checkbox screen, one conflicts screen and one backup for all of them.

**A bundle** is a package that's only a list of packages: a manifest with
`bundle = ["kittystory", "kittymusic", …]` and no files. Publish it like any other;
`hpm install kitty-desktop` installs the set.

---

## 13. The AI's parts, and what they cost

| When | What the AI does | How you get asked |
|---|---|---|
| `hpm init` | writes the manifests | always |
| publish | drafts a changelog entry (not for a first release) | on a terminal, or `--draft` |
| publish | reviews the card | on a terminal, or `--review` |
| publish | writes a migration note | on a terminal, or `--write-migration` |
| install, update | merges a `memory.md` (if you press `m`) | the `m` key |
| update | migrates data | on a terminal, or `--accept-migration` |

Each asks first and shows the model and the cap. Without `--changelog`, `--draft` and the
others, nothing costs money: install, update, remove and rollback alone never use the AI.

The settings are in the store's `config.toml` (`~/.local/share/hallux/hpm/config.toml`, or
in `$HPM_HOME`):

```toml
model = "claude-sonnet-5-5"   # default: the world's model
effort = "medium"
cap_usd = 1.00                # at most this per AI session
```

---

## 14. Cheat sheet

| I want to… | Command |
|---|---|
| make manifests for an app | `hpm init NAME` (in its world) |
| release it | `hpm publish NAME --all` |
| release it, keeping the last release's first state | `hpm publish NAME --seeds release` |
| see what's in the store | `hpm search WORD`, `hpm show NAME` |
| put it into a world | `hpm install NAME --world W` |
| see what a world has | `hpm list --world W` |
| get newer versions | `hpm update --world W` |
| undo the last change | `hpm rollback NAME --world W` |
| take it out | `hpm remove NAME --world W` |
| tell hpm about an app that's already there | `hpm adopt NAME --world W` |
| everything in a store | `hpm install local/ --world W` |
| my store on GitHub | `hpm store init NAME --repo ME/hpm-store`, then `hpm push NAME` |
| a friend's store | `hpm store add NAME https://github.com/THEM/hpm-store` |
| install from a friend | `hpm install THEM/NAME --world W` |
| empty a test store | `rm -rf $HPM_HOME` |

Every question on a screen has a flag too (`--extras packs,characters`, `--overwrite none`,
`--yes`…), so hpm also runs in a script. `hpm COMMAND --help` lists them.

---

## 15. When something goes wrong

On a terminal hpm's lines have colors: green worked, yellow look at it, red failed (the
error is the red line starting with `hpm:`), magenta is the AI and what it cost.
`NO_COLOR=1` turns the colors off; `HPM_COLOR=always` keeps them in a pipe
(`hpm list | less -R`).

hpm's errors start with `hpm:` and say what to do. The common ones:

| You see | It means |
|---|---|
| `the changelog entry is empty; nothing published` | The editor closed without a line written. Run it again and write one, or pass `--changelog "…"`. |
| `there is no package NAME in the store` | Nothing by that name is published, or `$HPM_HOME` points at another store than you think (`echo $HPM_HOME`). |
| `… is in no Hallux world` | You're not inside a world. `cd` into one, or add `--world W`. |
| `… is running` | Hallux is running on that world. Quit it, or use its Packages tab. |
| `there is no $EDITOR …` | `export EDITOR=nano`. |
| `NAME has a manifest already` | `init` already ran. Edit `/usr/local/share/hpm/NAME/hpm.toml` instead. |
| `… isn't installed in this world; hpm install it` | `update` only updates. Use `install` first, or `adopt` if the files are there already. |

Every AI part prints what it cost when it ends ("the AI's part cost ~$0.23"), and writes a
line in the world's log, `.hallux/hallux.log` (`hpm init: done, ~$0.4462, model …`), from a
terminal or the Packages tab. `grep "hpm " .hallux/hallux.log` lists what the AI cost in
that world.

---

## Read more

- [hpm.md](hpm.md): the full design, with the manifest's format and every screen.
- [migrations.md](migrations.md): migrations in depth.
- [sharing.md](sharing.md): friends, GitHub and privacy.
