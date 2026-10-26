# Sharing packages with friends

**Status:** design declared done by the user 2026-10-23, and **built** the same day, public
stores only ([docs/plans/hpm/](../plans/hpm/README.md), step 8; [As built](#as-built) at the
end). Its run with a real GitHub account is the user's, still to do. Every question is decided, all as
recommended ([Decisions](#decisions)). It builds on [hpm.md](hpm.md) (packages, the store on
your PC, publishing) and [migrations.md](migrations.md). Changed after the review of
2026-10-23 ([docs/hpm-review-2026-10-23.md](../hpm-review-2026-10-23.md), taken as
recommended): where your store's clone is kept, which address a friend adds, public stores
only at first, and a check at install that needs no AI.

**Where it came from:** of three levels offered (only your PC; friends; a public store
anyone can use), the user chose **level 2, friends**. A public store is left for later
(section 6).

## In short

1. **A store you share is a GitHub repository.** No server: an index of packages and their
   archives, the way Homebrew "taps" and Scoop "buckets" work.
2. **`hpm push kittystory`** sends a release from your PC's store to your GitHub store.
3. **A friend adds your store once**, `hpm store add danika <url>`. After that,
   `hpm install danika/kittystory` and `hpm update` work for them as for you.
4. **Your memories stay yours.** A package marked private never leaves your PC, and data
   packages with memories are private unless you say otherwise.
5. **A package is instructions to someone else's AI.** So the install shows what a package
   adds to the machine's mind before anything is written, and the AI reviews a card when
   it is published.

---

## 1. A store on GitHub

```
github.com/<you>/hpm-store
  index.toml
  README.md                   what the store is, how to add it (written by hpm)
```

The archives (`kittystory-1.4.hpm`) are files of GitHub releases of that repository, one
release per package version, so the repository itself stays small.

`index.toml`:

```toml
store = "danika"
updated = "2026-10-23T14:10"

[packages.kittystory]
summary = "Chat with characters built from personality packs"
latest = "1.4"
[packages.kittystory.versions."1.4"]
url = "https://github.com/<you>/hpm-store/releases/download/kittystory-1.4/kittystory-1.4.hpm"
sha256 = "9f2c…"
data_format = 2
requires = { addons = ["web"] }
extras = ["kittystory-packs", "kittystory-chars"]

[packages.kittystory-packs]
latest = "1.0"
# ...
```

**Who can see it.** A public repository can be read by anyone who has the link. A private
one only by people you add on GitHub; they would sign in once (`gh auth login`) and hpm
would download through `gh`. Which to use is decision 1: public. The first version reads
public stores only; reading a private one through `gh` comes when someone needs it.

**The address a friend adds** is the repository's, as they would copy it from the browser
(`https://github.com/<you>/hpm-store`). hpm asks GitHub for the repository's main branch
and reads `index.toml` from there. GitHub serves such files from a cache for a few minutes,
so right after a push a friend may still see the index as it was; a refresh a little later
shows the new one.

**More than one store.** You can add a friend's store as they add yours, and a group can
share one store where everyone sends packages as a pull request and one person merges them.
That is GitHub's own review, and hpm needs nothing extra for it.

## 2. Publishing to friends

```
(in your dev world) change kittystory with the AI
hpm publish kittystory         → into the store on your PC (hpm.md, section 5)
hpm install kittystory --world ~/hallux-distros/oliver-test     → try it in another world
hpm push kittystory            → to your GitHub store
```

`hpm push`:

1. Takes the newest release of each package you name from your PC's store (`--all`: every
   package newer than in the GitHub store).
2. **Refuses private packages** (section 3).
3. **Checks the card**, if the AI hasn't reviewed this version yet (section 4). What it
   finds is shown, and you decide whether to push anyway.
4. Makes a GitHub release `kittystory-1.4` with the archive, through `gh`, and adds the
   version to `index.toml` with its checksum. The index is changed in a clone of your store
   that `hpm store init` made on your PC (`mine/danika/` in hpm's folder), then committed
   and pushed with `git`.
5. Says what it pushed, the line a friend needs to add the store, and that GitHub may
   show the old index for a few minutes.

A version that was pushed is never changed. A wrong release is followed by a fixed one
(1.4.1), and `hpm yank kittystory 1.4` marks the bad one in the index, so nobody installs it
by default any more.

## 3. Privacy

What you would never want to send by mistake is in the data: your characters' memories,
your chat history, the things the machine knows about you.

- **A package can be marked `private = true`.** `hpm push` refuses it, always. A data
  package whose files include memories (`memory.md`, `shared.md`, a chat history like
  kittystory's `state.json`) is private when `hpm init` makes it, until you change that.
- **Publish says what each package holds.** `kittystory-chars: 3 characters (no memories)`,
  `kittystory-memories: private, 3 memory files, 1 chat history`.
- **`seed` files are looked at too.** kittystory's `state.json` is a seed of the app, but in
  your world it holds your chat. hpm.md, section 5 publishes what is in the world, so the AI
  is asked at `hpm init` for a clean seed (a first state with no chat), and publish warns
  when a seed is far bigger than the one before. Install puts a copy of each release's
  seed beside the manifest too (`/usr/local/share/hpm/<name>/seed/`), so a world that
  installed the app and publishes it sends that clean copy, not its own used one.

## 4. Packages are instructions to the AI

A Hallux package is not like other packages. Its card is instructions to the AI that runs a
friend's machine, and its memory line goes into that machine's memory. A card could say
"also delete ~/Music" or "ignore the user's rules". Friends are trusted, but a mistake or a
copied card is enough.

- **At install, the friend sees what goes into the machine's mind first:** the card (`v` on
  the install screen, hpm.md section 6), the memory line, and any rules, before anything is
  written.
- **At publish, the AI reviews the card** and lists anything that reaches beyond the app:
  files outside the package's own paths, changes to the world's rules, the machine's memory
  or other programs' cards. The review is saved with the release and shown to whoever
  installs it. It was made at the publisher's end, which is fine between friends.
- **At install, hpm's own code checks what needs no AI,** at the installer's end: a package
  that writes a file the machine reads at every boot (`/etc/passwd`, `/etc/motd`,
  `/etc/hostname`, `.bashrc` and the rest of `BOOT_FILES` in `hallux/disk.py`) or another
  program's card in `/usr/local/bin` is shown loudly on the install screen, as rules are.
- **Rules are loud.** A package that carries rules (hpm.md, decision 5) says so in red
  on the install screen.
- **A package can only write what its manifest lists**, and never into `/.hallux` (except
  the memory line and the world's record, which Hallux's code writes). This is enforced by
  hpm's own code, not the AI.
- **Checksums.** Every archive's sha256 is in the index, and an archive that doesn't match
  is refused.
- **Signing, later.** A checksum shows the file is the one in the index, not that the index
  is yours. GitHub's own login protects the index for now; signatures can come if stores get
  shared more widely.

## 5. Names

In a friend's world, packages are named by store: `danika/kittystory`, and `danika/` alone
means every package of the store (hpm.md section 6a). `hpm install kittystory` works when
only one store has the name, and asks otherwise. The world's record
remembers which store a package came from, so `hpm update` takes the next version from the
same store.

## 6. Later: a public store

A website with accounts, search and download counts, where anyone can publish. It needs a
server, logins, and handling of abuse, which section 4 shows is a real concern for packages
that are instructions to an AI. It is left until stores on GitHub have shown that people
share packages.

## Decisions

All decided as recommended (the user, 2026-10-23: "i read trogh the questions and go all
recommended").

| Question | Decision |
|---|---|
| 1. Is your store public or private on GitHub? | **Public**, with the link only given to friends: no sign-in for them. Private if a package ever must not be seen by others |
| 2. Do archives go in GitHub releases, or into the repository itself? | **Releases**: the repository stays small, and a version can't be changed by accident |
| 3. Is `gh` (GitHub's command line) needed, or does hpm talk to GitHub itself? | **`gh`** for pushing; reading a public store needs nothing but downloads |
| 4. Is the AI's review of a card a hard stop? | No, it is shown, and you decide. It is also shown to whoever installs |
| 5. Does a store name have to be your GitHub name? | No, you choose it when you make the store (`hpm store init danika`) |

## As built

Built 2026-10-23 in `hallux/hpm/remote.py` and the store, the engine, the command and the
Packages tab; plan step 8's "As built" has the details. What the code does differently from
this document:

- **The commands:** `hpm store init NAME --repo OWNER/REPO`, `hpm store add NAME ADDRESS`,
  `hpm store list | remove NAME | refresh [NAME]`, `hpm push NAME… [--all]`, `hpm yank NAME
  VERSION`. `--store S` picks one of your stores if you have several.
- **Your store's clone** is `mine/<name>/` with `mine/<name>.toml` naming its repository; a
  friend's store is `stores/<name>/` (`index.toml`, `source.toml`).
- **The index** keeps `sha256` as bare hex and `latest` as the newest version that isn't
  yanked; one GitHub release and one commit of the index per package pushed.
- **A friend's archive** downloads when it is first needed, into `cache/`, and is checked
  against the index's sha256 and its own name and version every time it is used. Extras
  come from the same store as their app, else from your own.
- **An index older than an hour** is refreshed by `install`, `update` and `search`; one that
  can't be reached is used as it was, with a note.
- **Push** refuses private packages and a version pushed already, shows the review made at
  publish, can have the AI make one when there is none (`--review`, in a world), and pushes
  a card whose review found something only on yes (`--yes`).
- **The Packages tab** shows a friend's packages once downloaded (`danika/kittystory`);
  `R` downloads them in a thread, so the tab never waits on the network.
- **Not built:** reading a private store through `gh`, and `hpm show` of a friend's package.
