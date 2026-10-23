# hpm: what to try by hand

[The plan](README.md) · [step 9](09-manual-docs-live-run.md), whose live run this is

**What this is:** every point that only a person with real worlds, a real model and a GitHub
account can show. The tests ran without any model (a stand-in followed the notes), with a
folder in place of GitHub, and the real-terminal checks used a pretend model. Here the AI is
real, and so are your characters.

**How to use it:**

- **Each point has a block of commands.** Copy it into your terminal as it stands. Lines
  starting with `#` say what to look for; the shell skips them.
- **Use one terminal for the whole run,** and run the "Before you start" block in it first:
  it sets `hpm`, `hallux` and `HPM_HOME` for the commands below. A new terminal needs that
  block again (only its `export` lines; the copies are made already).
- **It works as described:** tick the box, `[x]`. Nothing else is needed.
- **It doesn't, or you aren't sure:** leave the box empty and write what you saw on the
  line "If not" under it. A few words are enough.
- **A few points ask for a number,** such as what the AI cost. They have a line for it.
- **An empty box with an empty line** means "not tried yet".

When you are through, or stuck, tell me. I read this file, fix what failed, and write the
results into the steps.

**If something looks wrong:** the point's number and what you saw are all I need. hpm's
error starts with `hpm:`, and each AI part prints what it cost when it ends. (From a
terminal, hpm writes nothing to the world's log, `.hallux/hallux.log`; the Packages tab
logs its migrations there.)

**Names the AI picks.** `hpm init` (point 1) names the extras. The commands use the names
it is told to use: `kittystory-packs`, `kittystory-chars` and `kittystory-memories`. If
point 1 shows other names, use those wherever these appear.

---

## Before you start

```bash
cd ~/IT/hallux && python3 install.py                # puts .venv/bin/hpm there
export PATH="$HOME/IT/hallux/.venv/bin:$PATH"       # so `hpm` and `hallux` work anywhere
export HPM_HOME=~/hpm-live                          # a store of its own for this run
export EDITOR=nano                                  # init and publish open the manifest and changelog in it
hpm --help | head -3                                # should print hpm's usage line

# copies, so no world you care about is changed (every point says which copy it uses)
# they all go into one folder, ~/hallux-distros/test-hpm/
mkdir -p ~/hallux-distros/test-hpm && cd ~/hallux-distros
cp -a test-hallux  test-hpm/test-hallux-before       # untouched: points 1, 2 and 7 change test-hallux
cp -a test-hallux  test-hpm/test-hallux-copy         # stays at 1.x for point 7
cp -a oliver-test  test-hpm/oliver-hpm               # points 3, 4, 6, 10
cp -a oliver-test  test-hpm/oliver-tab               # point 5
cp -a oliver-test  test-hpm/oliver-all               # point 8
cp -a oliver-test  test-hpm/oliver-friend            # point 9
cp -a sofi-hallux  test-hpm/sofi-hpm                 # point 11
ls ~/hallux-distros/test-hpm
```

`test-hallux` is where kittystory is built, so it is the one world used where it is: points
1 and 2 add hpm's manifests to it (`/usr/local/share/hpm/`) and its record (`.hallux/hpm/`),
nothing else. Point 7 has its machine change kittystory and move your characters;
`test-hpm/test-hallux-before` keeps them as they were.

**What it costs.** Every AI part asks first, with the model and the cap. With the defaults
(the world's model, effort medium, at most $1.00 a session): point 1 is one session (two if
the AI has to fix its draft), point 7 is the machine's own work on kittystory, then a note
per package and a migration per note, and the reviews and drafts at publish one each, only
if you say yes. The installs, updates, removes and rollbacks themselves use no AI and cost
nothing.

**When you are done**, to remove all of it:

```bash
# test-hallux keeps what points 1, 2 and 7 did; to undo that, run this line first:
#   rm -rf ~/hallux-distros/test-hallux && mv ~/hallux-distros/test-hpm/test-hallux-before ~/hallux-distros/test-hallux
rm -rf ~/hallux-distros/test-hpm ~/hpm-live ~/hpm-friend ~/hpm-chars-before
```

---

## A. Making the packages

1. [x] **`hpm init kittystory`** in `test-hallux`. It asks before the AI starts, then shows
   the manifests it drafted: kittystory's (its card and `/usr/local/share/apps/kittystory/`
   as app, `state.json` as seed) and its extras', such as the packs and the characters, and
   the memories, marked private. Read them and fix what is wrong; compare with what step 2
   wrote by hand (`docs/plans/hpm/02-store-and-publish.md`, "As built").

   ```bash
   cd ~/hallux-distros/test-hallux
   hpm init kittystory
   # then look at what it wrote:
   ls usr/local/share/hpm/
   for f in usr/local/share/hpm/*/hpm.toml; do echo "=== $f"; cat "$f"; done
   ```

   What it cost (the last line it printed):
the AI's part cost ~$0.2318
   If not:

2. [x] **`hpm publish kittystory --all`.** It asks each version (Enter takes the one it
   offers), asks whether to have the card reviewed, and says what each package holds: the
   memories private, `state.json` the clean one if init wrote it. Then `hpm list` shows the
   packages it published (the publish adopted them), and `hpm show kittystory` shows the
   release.

   Every release needs a changelog entry. `--changelog` gives the same one to all five
   packages. (Without it, nano opens once per package with a `## 1.0 (date)` line: write a
   line under it, then Ctrl+O, Enter, Ctrl+X. Quitting without writing stops the publish:
   "the changelog entry is empty". A first release has no AI draft, since there is nothing
   to compare with.) The `&&` stops the block at the first error.

   ```bash
   cd ~/hallux-distros/test-hallux
   hpm publish kittystory --all --changelog "First release" && hpm list && hpm show kittystory
   ```
this worked
   If not:

## B. Installing

3. [x] **Into `oliver-hpm`, from your terminal.** A file of yours is put where a pack goes
   first, so the conflicts screen asks about it. The checkboxes show kittystory's extras
   (`→` opens one, `v` shows the card and the review); untick one, Enter. On the conflicts
   screen, pick "skip" for `tsundere.pack`.

   ```bash
   mkdir -p ~/hallux-distros/test-hpm/oliver-hpm/home/user/.kittystory/packs
   echo "my own pack" > ~/hallux-distros/test-hpm/oliver-hpm/home/user/.kittystory/packs/tsundere.pack
   hpm install kittystory --world ~/hallux-distros/test-hpm/oliver-hpm
   hpm list --world ~/hallux-distros/test-hpm/oliver-hpm
   cat ~/hallux-distros/test-hpm/oliver-hpm/home/user/.kittystory/packs/tsundere.pack   # still "my own pack"
   ```
┌──(dano㉿DESKTOP-HAF0IOD)-[~/hallux-distros/test-hallux]
└─$ mkdir -p ~/hallux-distros/test-hpm/oliver-hpm/home/user/.kittystory/packs
echo "my own pack" > ~/hallux-distros/test-hpm/oliver-hpm/home/user/.kittystory/packs/tsundere.pack
hpm install kittystory --world ~/hallux-distros/test-hpm/oliver-hpm
hpm list --world ~/hallux-distros/test-hpm/oliver-hpm
cat ~/hallux-distros/test-hpm/oliver-hpm/home/user/.kittystory/packs/tsundere.pack   # still "my own pack"
  ✓ kittystory 1.0 updated (was 1.0)
1 updated  (backup: 2026-10-23T23-58-15-kittystory)
kittystory 1.0  extras: packs, characters, world
kittystory-chars 1.0
kittystory-packs 1.0
kittystory-world 1.0
backups: 2, 6.2 KB (hpm backups --clean removes them)
my own pack

   If not:

4. [x] **In that world, the app works:** the web app opens, with Emma, Lucy and Emilly (if
   the characters were ticked in point 3).

   ```bash
   hallux ~/hallux-distros/test-hpm/oliver-hpm
   ```

   At the machine's prompt, type `kittystory -w`. Quit Hallux afterwards (point 6 changes
   this world from your terminal, and hpm refuses a running world).

   If not:

5. [x] **The same from the Packages tab of a running world.**

   ```bash
   hallux ~/hallux-distros/test-hpm/oliver-tab
   ```

   In it: Ctrl+F12, `g`, space on kittystory, Enter, Enter. Then Esc and type `kittystory`:
   the AI knows the app at once (it was told with that line). In the Files tab, `p` still
   opens its path row.

   If not:

6. [x] **A pack you changed is kept, not replaced.** You change a pack in `oliver-hpm`,
   the same pack changes in `test-hallux` and is published again, and the update leaves
   yours as it is. Packs are data (`kittystory-packs` has `data = [...]`, as hpm.md section 3
   has it), and an update never touches data, so no question comes: the update says the
   pack is kept. (If you changed `kittystory-packs` to `app = [...]` after point 1, the
   update asks instead, and "skip" keeps yours.)

   ```bash
   # your change, in oliver-hpm (Hallux must not be running on it):
   echo "my own line" >> ~/hallux-distros/test-hpm/oliver-hpm/home/user/.kittystory/packs/sensitive-sweetheart.pack
   # a change in test-hallux, and a newer kittystory-packs:
   echo "a newer line" >> ~/hallux-distros/test-hallux/home/danika-hous/.kittystory/packs/sensitive-sweetheart.pack
   cd ~/hallux-distros/test-hallux
   hpm publish kittystory-packs --changelog "a line more in sensitive-sweetheart"
   # the update: sensitive-sweetheart.pack is kept (with app packs: it asks; pick "skip")
   hpm update --world ~/hallux-distros/test-hpm/oliver-hpm
   tail -1 ~/hallux-distros/test-hpm/oliver-hpm/home/user/.kittystory/packs/sensitive-sweetheart.pack   # "my own line"
   ```

   If not:

## C. A new data layout

7. [ ] **kittystory 2.0 with characters in a new layout, migrated.** Four parts: the
   machine changes kittystory in `test-hallux`; you change the manifests and publish 2.0;
   `test-hallux-copy` (still 1.x, with the old `chars/`) updates and its characters are
   migrated; then a rollback brings 1.x back.

   **a. The machine changes the app** (this is a normal Hallux run, so it costs what the
   machine's work costs):

   ```bash
   hallux ~/hallux-distros/test-hallux
   ```

   At the machine's prompt, type this as one line:

   ```
   hallux change kittystory to keep each character in ~/.kittystory/characters/<name>.toml (its name, pack and notes, from char.md) and its memory in ~/.kittystory/memories/<name>.md (the old memory.md, unchanged), and move my characters there
   ```

   Try `kittystory -w` once it says it is done, then quit Hallux.

   **b. The manifests and the publish.** First see which manifests name the old `chars/`
   folder:

   ```bash
   cd ~/hallux-distros/test-hallux
   ls home/danika-hous/.kittystory/characters home/danika-hous/.kittystory/memories
   grep -l "chars/" usr/local/share/hpm/*/hpm.toml
   ```

   `grep` names three manifests, and the loop below opens each in nano. In each, change only
   the `chars/` paths and keep everything else:
   - **kittystory-chars:** `"~/.kittystory/chars/*/char.md"` becomes
     `"~/.kittystory/characters/*.toml"`.
   - **kittystory-memories:** `"~/.kittystory/chars/*/memory.md"` becomes
     `"~/.kittystory/memories/*.md"`; `"~/.kittystory/shared.md"` stays.
   - **kittystory:** its `memory_line` names `chars/<Name>/{char.md,memory.md}`; write
     `characters/<name>.toml, memories/<name>.md` there instead, so a world that installs
     2.0 is told the new layout.

   Then the data format goes to 2, in those three:

   ```bash
   cd ~/hallux-distros/test-hallux
   for f in $(grep -l "chars/" usr/local/share/hpm/*/hpm.toml); do nano "$f"; done   # the changes, as above
   grep -l "chars/" usr/local/share/hpm/*/hpm.toml || echo "no chars/ left"
   # data_format = 2 in the three (the chars and memories drafts have no such line yet: it is added above [files])
   for f in usr/local/share/hpm/kittystory{,-chars,-memories}/hpm.toml; do
     if grep -q "^data_format" "$f"; then sed -i 's/^data_format = .*/data_format = 2/' "$f"
     else sed -i '0,/^\[files\]/s//data_format = 2\n\n[files]/' "$f"; fi
     grep -H "^data_format" "$f"                    # each prints "data_format = 2"
   done
   # the publish: it says the data moved and offers the AI's note (migrations/1-to-2.md)
   # for each of those packages; say yes, and read each note it shows
   hpm publish kittystory --all --changelog "Characters in characters/, memories in memories/"
   hpm show kittystory
   ```

   **c. The update in `test-hallux-copy`.** Its characters are saved aside first, to compare
   with. It has no record yet, so its packages are adopted at the version point 2 published
   (`hpm show kittystory` lists the versions; the commands assume `1.0`).

   ```bash
   cp -a ~/hallux-distros/test-hpm/test-hallux-copy/home/danika-hous/.kittystory/chars ~/hpm-chars-before
   cd ~/hallux-distros/test-hpm/test-hallux-copy
   for p in kittystory kittystory-packs kittystory-chars kittystory-memories; do hpm adopt $p --version 1.0; done
   hpm list
   hpm update
   ```

   The plan shows Emma, Lucy and Emilly; Enter; the checks; `l` shows the staged files;
   Enter accepts. Then every new memory file is its old `memory.md`, and kittystory 2.0
   shows the characters:

   ```bash
   cd ~/hallux-distros/test-hpm/test-hallux-copy
   for d in ~/hpm-chars-before/*/; do
     n=$(basename "$d"); m=$(find home/danika-hous/.kittystory/memories -iname "$n.md")
     if [ -n "$m" ] && cmp -s "$d/memory.md" "$m"; then echo "$n: same"; else echo "$n: DIFFERENT or missing"; fi
   done
   ls home/danika-hous/.kittystory/
   hpm list
   ```

   (Start Hallux on `test-hallux-copy` and run `kittystory -w` to see the characters; quit
   it before the rollback.)

   **d. The rollback:** `chars/` and 1.x are back as they were.

   ```bash
   cd ~/hallux-distros/test-hpm/test-hallux-copy
   hpm rollback kittystory
   diff -r ~/hpm-chars-before home/danika-hous/.kittystory/chars && echo "chars/ is back, byte for byte"
   hpm list
   ```

   What the migration cost (the checks screen says it):

   If not:

## D. Many at once, friends, and the rest

8. [ ] **A whole store at once:** one checkbox screen with every package, one conflicts
   screen, one backup.

   ```bash
   hpm install local/ --world ~/hallux-distros/test-hpm/oliver-all
   hpm backups --world ~/hallux-distros/test-hpm/oliver-all          # lists one
   ```

   If not:

9. [ ] **Your store on GitHub, and a friend's install.** `store init` makes a **public**
   repository `hpm-store` on your GitHub account. The memories are refused at push. Then, as
   a friend would, with a store of their own (`HPM_HOME=~/hpm-friend`), into
   `oliver-friend`; `hpm list` there says `(from dano)`.

   ```bash
   gh auth status                                     # signed in? else: gh auth login
   GH_USER=$(gh api user --jq .login); echo "$GH_USER"
   hpm store init dano --repo "$GH_USER/hpm-store"
   hpm push kittystory kittystory-packs kittystory-chars
   hpm push kittystory-memories                       # should be refused: it is private
   hpm store list
   # now as the friend:
   HPM_HOME=~/hpm-friend hpm store add dano "https://github.com/$GH_USER/hpm-store"
   HPM_HOME=~/hpm-friend hpm install dano/kittystory --world ~/hallux-distros/test-hpm/oliver-friend
   HPM_HOME=~/hpm-friend hpm list --world ~/hallux-distros/test-hpm/oliver-friend
   ```

   Right after a push GitHub may still show the old index for a few minutes. If the friend's
   `store add` or `install` doesn't see the packages yet, wait a little and run:

   ```bash
   HPM_HOME=~/hpm-friend hpm store refresh
   ```

   If not:

10. [ ] **`hpm remove kittystory`** in `oliver-hpm`: the app's files are gone, the
    characters and packs stay, and its `[hpm kittystory …]` line is gone from the memory.

    ```bash
    grep "hpm kittystory" ~/hallux-distros/test-hpm/oliver-hpm/.hallux/memory.md        # the line, before
    hpm remove kittystory --world ~/hallux-distros/test-hpm/oliver-hpm
    ls ~/hallux-distros/test-hpm/oliver-hpm/usr/local/share/apps/kittystory              # should be gone
    ls ~/hallux-distros/test-hpm/oliver-hpm/home/user/.kittystory/                       # still there
    grep "hpm kittystory" ~/hallux-distros/test-hpm/oliver-hpm/.hallux/memory.md || echo "the line is gone"
    hpm list --world ~/hallux-distros/test-hpm/oliver-hpm
    ```

    If not:

11. [ ] **`hpm adopt kittystory`** in a world that got kittystory the old way, from an
    `.update` file (`sofi-hallux`; on its copy `sofi-hpm`): the files that are the release's
    are recorded, the others stay as they are, and the machine's own line about kittystory
    is offered for replacing.

    ```bash
    hpm adopt kittystory --version 1.0 --world ~/hallux-distros/test-hpm/sofi-hpm
    hpm list --world ~/hallux-distros/test-hpm/sofi-hpm                                   # "(adopted)"
    grep -i "kittystory" ~/hallux-distros/test-hpm/sofi-hpm/.hallux/memory.md
    ```

    If not:
