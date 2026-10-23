# hpm: what to try by hand

[The plan](README.md) · [step 9](09-manual-docs-live-run.md), whose live run this is

**What this is:** every point that only a person with real worlds, a real model and a GitHub
account can show. The tests ran without any model (a stand-in followed the notes), with a
folder in place of GitHub, and the real-terminal checks used a pretend model. Here the AI is
real, and so are your characters.

**How to use it:**

- **It works as described:** tick the box, `[x]`. Nothing else is needed.
- **It doesn't, or you aren't sure:** leave the box empty and write what you saw on the
  line "If not" under it. A few words are enough.
- **A few points ask for a number,** such as what the AI cost. They have a line for it.
- **An empty box with an empty line** means "not tried yet".

When you are through, or stuck, tell me. I read this file, fix what failed, and write the
results into the steps.

**If something looks wrong:** the point's number and what you saw are all I need. hpm's
error starts with `hpm:`; the world's log, `.hallux/hallux.log`, has a line for each of
hpm's AI sessions (what it was, how it ended, what it cost).

---

## Before you start

- **The `hpm` command:** run `python install.py` once more, so `.venv/bin/hpm` is there
  (or use `.venv/bin/python -m hallux.hpm` wherever this says `hpm`).
- **A store of its own for this run,** so nothing of it stays in your real one:

  ```bash
  export HPM_HOME=~/hpm-live
  ```

- **Copies of the worlds you install into.** hpm writes into the worlds it installs into,
  after a backup; still, try it on copies:

  ```bash
  cp -a ~/hallux-distros/oliver-test ~/hallux-distros/oliver-hpm
  cp -a ~/hallux-distros/test-hallux ~/hallux-distros/test-hallux-copy
  ```

  `test-hallux` itself is where kittystory is built: points 1 and 2 add hpm's manifests to
  it (`/usr/local/share/hpm/`) and its record (`.hallux/hpm/`), nothing else.

- **For point 9:** `gh` installed and signed in (`gh auth login`), and `git`.

**What it costs.** Every AI part asks first, with the model and the cap. With the defaults
(the world's model, effort medium, at most $1.00 a session): point 1 is one session (two if
the AI has to fix its draft), point 7 is three or more (the note, then a plan and a
migration per note), and the reviews and drafts at publish one each, only if you say yes.
The installs, updates, removes and rollbacks themselves use no AI and cost nothing.

---

## A. Making the packages

1. [ ] **`hpm init kittystory`,** in `test-hallux` (`cd ~/hallux-distros/test-hallux`).
   It asks before the AI starts, then shows the manifests it drafted: kittystory's (its
   card and `/usr/local/share/apps/kittystory/` as app, `state.json` as seed) and its
   extras', such as the packs and the characters, and the memories, marked private. Read
   them and fix what is wrong; compare with what step 2 wrote by hand
   (`docs/plans/hpm/02-store-and-publish.md`, "As built").

   What it cost (the last line, or the log):

   If not:

2. [ ] **`hpm publish kittystory --all`.** It asks each version (or `--yes`), opens the
   changelog in your editor (or say yes to the AI's draft), asks whether to have the card
   reviewed, and says what each package holds: the memories private, `state.json` the
   clean one if init wrote it. Then `hpm list` in `test-hallux` shows the packages it
   published (the publish adopted them), and `hpm show kittystory` shows the release.

   If not:

## B. Installing

3. [ ] **Into `oliver-hpm`, from your terminal:** `hpm install kittystory --world
   ~/hallux-distros/oliver-hpm`. The checkboxes show its extras (`→` opens them, `v` shows
   the card and the review); untick one, Enter. Put a file of your own where a pack goes
   first (`~/.kittystory/packs/tsundere.pack` with anything in it) and the conflicts screen
   asks about it.

   If not:

4. [ ] **In that world, the app works:** start Hallux on `oliver-hpm` and run
   `kittystory -w`: the web app opens, with Emma, Lucy and Emilly (if the characters were
   ticked).

   If not:

5. [ ] **The same from the Packages tab of a running world:** start Hallux on a second copy
   of `oliver-test`, Ctrl+F12, `g`, space on kittystory, Enter, Enter. Then Esc and type
   `kittystory`: the AI knows the app at once (it was told with that line). In the Files
   tab, `p` still opens its path row.

   If not:

6. [ ] **A pack you changed is asked about, not replaced:** in `oliver-hpm` change a pack
   by hand, publish a newer kittystory-packs in `test-hallux` (change a pack there too),
   and `hpm update --world ~/hallux-distros/oliver-hpm`: the changed pack is asked about,
   and "skip" keeps yours.

   If not:

## C. A new data layout

7. [ ] **kittystory 2.0 with characters in a new layout, migrated.** In `test-hallux`, ask
   the machine to change kittystory to keep each character in
   `~/.kittystory/characters/<name>.toml` and its memory in `~/.kittystory/memories/<name>.md`
   (migrations.md, section 1), and to move your characters there. Change the data patterns
   in `/usr/local/share/hpm/kittystory/hpm.toml` to match, then `hpm publish kittystory`:
   it says the data moved and offers the AI's note (`migrations/1-to-2.md`); read it.
   Then in `test-hallux-copy` (still 1.x, with the old `chars/`; `hpm adopt kittystory`
   there first if it has no record yet): `hpm update kittystory`. The plan shows Emma,
   Lucy and Emilly; Enter; the checks; `l` shows the staged files; Enter accepts. Every
   `memories/<name>.md` is its old `memory.md` (`cmp` them against `test-hallux`'s from
   before, or the backup in `.hallux/hpm/backups/`), and kittystory 2.0 shows the
   characters. Then `hpm rollback kittystory`: `chars/` and 1.x are back as they were.

   What the migration cost (the checks screen says it):

   If not:

## D. Many at once, friends, and the rest

8. [ ] **A whole store at once:** into a fresh copy of `oliver-test`
   (`cp -a ~/hallux-distros/oliver-test ~/hallux-distros/oliver-all`), `hpm install local/
   --world ~/hallux-distros/oliver-all`: one checkbox screen with every package, one
   conflicts screen, one backup (`hpm backups --world …` lists one).

   If not:

9. [ ] **Your store on GitHub, and a friend's install.** `hpm store init <name> --repo
   <you>/hpm-store` (a public repository), `hpm push kittystory kittystory-packs` (and the
   characters if you published them; the memories are refused). Then, as a friend would,
   with another store (`HPM_HOME=~/hpm-friend`): `hpm store add <name>
   https://github.com/<you>/hpm-store`, then `hpm install <name>/kittystory --world
   ~/hallux-distros/oliver-friend` (one more copy of `oliver-test`). `hpm list` there says
   `(from <name>)`. Right after a push GitHub may still show the old index for a few minutes:
   `hpm store refresh` a little later shows the new one.

   If not:

10. [ ] **`hpm remove kittystory`** in `oliver-hpm`: the app's files are gone, the
    characters and packs stay, and its `[hpm kittystory …]` line is gone from the memory.

    If not:

11. [ ] **`hpm adopt kittystory`** in a world that got kittystory the old way, from an
    `.update` file (`sofi-hallux` or `danika`, if they have it; on a copy): the files that
    are the release's are recorded, the others stay as they are, and the machine's own line
    about kittystory is offered for replacing.

    If not:
