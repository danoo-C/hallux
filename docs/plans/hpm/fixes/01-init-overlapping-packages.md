# Fix 01: `hpm init` keeps manifests that share a file

[The fixes](README.md) · [the plan](../README.md) · built on [step 6](../06-ai-session.md)
(`hpm init`) and [step 2](../02-store-and-publish.md) (publish's checks)

**Status:** planned 2026-10-24, at the user's request ("please write a plan for it in the
hpm's plan folder"). Not built. The decisions below are proposals, not confirmed.

**Changes:** `hallux/hpm/publish.py` (the shared-file check becomes a function both
commands use), `hallux/hpm/assist.py` (`init` runs it), `hallux/hpm/prompts/init.md` (one
rule more), `tests/test_hpm_ai.py`, `tests/test_hpm_publish.py`.

## What happened

The user's own run, 2026-10-24, in `~/hallux-distros/danika` (a copy of the repo's
`test-hallux/`, with the newest kittystory). `hpm init kittystory` drafted six manifests and
ended with "kept: …. Next: hpm publish kittystory --all". The publish then refused:

```
hpm: kittystory can't be published: /usr/local/share/apps/kittystory/sprites/emilly-smoke.svg
is in kittystory and in kittystory-chars; one package must carry it; …/sprites/emilly.svg
is in kittystory and in kittystory-chars; …/sprites/emma.svg …; …/sprites/lucy.svg …;
…/sprites/me-smoke.svg is in kittystory and in kittystory-me; …/sprites/me.svg …
```

kittystory's app line is `/usr/local/share/apps/kittystory/**`, the whole folder. The AI
also put the characters' sprites into `kittystory-chars`
(`/usr/local/share/apps/kittystory/sprites/emma.svg`, …) and the user's into
`kittystory-me`. Six files were in two packages. The init prompt already says "Two packages
may never hold the same file"; the AI broke the rule anyway, and nothing in init checked it.

## Why init let it through

1. **Init checks each manifest alone.** `_problems` in `hallux/hpm/assist.py` loads each
   manifest, checks where it lives, and checks that each pattern matches a file. It never
   compares the app's files with its extras' files. That check exists only in publish:
   `_shared_with_family` in `hallux/hpm/publish.py`, called for each package as it is
   published.
2. **Init checks only the manifests it wrote in this session.** `_problems(disk,
   answer.wrote, home)` sees what the AI wrote this time. In the user's run, the user had
   removed only `kittystory/hpm.toml` and run init again; the extras' manifests were from
   the first run (00:17) and the second run rewrote only the app's and the memories'
   (00:29). The chars and me manifests, where the sprites were, were never checked by the
   second run, and weren't shown either.

So the one round where hpm shows its problems to the AI (step 6: "shows its problems to the
AI once, then to you") had nothing to show, and the user got "kept".

## What to build

**1. One check of a program's whole family, in `publish.py`.**

```python
def family_problems(disk: Disk, app: str, home: str | None) -> list[str]:
    """The files that two packages of one program both carry: the app and every extra its
    manifest lists, whose manifests are in the world. Each problem names the file and both
    packages, in publish's words."""
```

- It reads the app's manifest and each extra's under `[extras]`, collects each one's files
  (`collect`), and returns `"<path> is in <a> and in <b>; one package must carry it"` for
  each file in two of them. The words stay those of publish today, so the user sees the
  same sentence from init and from publish.
- A manifest that can't be read is a problem of its own ("… has problems; …"), not a
  silent skip: init must not say "kept" over it.
- `_shared_with_family` keeps its job in publish (one package against the others) and uses
  the same pieces, so the two can't drift apart.

**2. Init checks the family, both times.** In `hallux/hpm/assist.py`, `_problems` takes
the program's name and checks:
- each manifest alone, as now, for every manifest of the family **that is in the world**,
  not only those written this session (decision 1);
- then `family_problems` over all of them.

`problems_of` (the one round shown to the AI) and the final `left` check both use it. So:
- the AI is told "…/sprites/emma.svg is in kittystory and in kittystory-chars; one package
  must carry it" and fixes its draft in the same session, at no extra session's cost;
- if it's still wrong, init ends with "the manifests still have problems; fix them by hand,
  then hpm publish: …", naming the files, instead of "kept".

**3. Init shows every manifest of the family** at the end, the ones written this time and
those that were there already, each under its `--- path` line as now (decision 2). In the
user's run the chars and me manifests, where the problem was, weren't shown at all.

**4. One rule more in `prompts/init.md`,** under the patterns paragraph (decision 3):

> An extra may carry files inside the app's folder (a character's sprite in
> /usr/local/share/apps/<name>/sprites/). Then the app's patterns must not reach them:
> list the app's own files (`*.js`, `index.html`, `sprites/cat.svg`) instead of `**`.

That is what fixed the user's world by hand (below), so the AI learns the same way out.

**5. A manifest the AI wrote but didn't list under `[extras]`** (a
`/usr/local/share/hpm/<name>-<part>/hpm.toml` the app doesn't name) is a problem too:
"… is not listed under [extras] of <name>'s manifest; publish --all would leave it out"
(decision 4). Today it is published only by its own `hpm publish`, and no overlap check
sees it.

## Tests

In `tests/test_hpm_ai.py`, with the stand-in AI (`StandIn`, `writes`) and the fixtures there:

- **The AI is shown the overlap and fixes it.** The first draft: the app with `**` over
  its folder, and an extra that carries `sprites/emma.svg` from that folder. The second
  message to the stand-in names the file and both packages. The second draft lists the
  app's files; init keeps both manifests.
- **An overlap left is init's error, not publish's.** The stand-in writes the same
  overlapping draft twice: init raises `HpmError` "still have problems", naming the file;
  the manifests are left, to fix by hand.
- **Manifests from before are checked.** An extra's manifest is in the world before init
  runs (as in the user's run). The AI writes only the app's, with `**`. The overlap with
  the old extra is shown to the AI.
- **Every manifest of the family is shown,** the old one included.
- **An unlisted extra** written by the AI is named as a problem.

In `tests/test_hpm_publish.py`: **publish refuses a file two packages carry,** with the
words it uses today ("… is in kittystory and in kittystory-chars; one package must carry
it"). No test covers that message now; this one pins it before the check is shared.

## Done when

- The tests above pass, and the whole suite (`--deselect tests/test_sandbox.py`).
- **The user's own case, without the AI:** on a copy of `danika` with its manifests as init
  left them (the app with `**`, the sprites in `kittystory-chars` and `kittystory-me`),
  `family_problems(disk, "kittystory", home)` returns the six files that publish named.
  After the by-hand fix below, it returns none, and publish goes through (as it did on a
  scratch copy on 2026-10-24: six packages, the app with 10 files).
- No paid run is needed. A real `hpm init` on a fresh copy of the repo's `test-hallux/` is
  for the user to try if they want (about $0.25).

## The by-hand fix, for a world that has the problem now

This is what the user can do without waiting for the fix; it was tried on a scratch copy of
`danika` on 2026-10-24, and all six packages published. The app lists its own files, and
the sprites stay with the characters:

```bash
cd ~/hallux-distros/danika
sed -i 's#^  "/usr/local/share/apps/kittystory/\*\*",$#  "/usr/local/share/apps/kittystory/*.js",\n  "/usr/local/share/apps/kittystory/*.css",\n  "/usr/local/share/apps/kittystory/*.html",\n  "/usr/local/share/apps/kittystory/app.json",\n  "/usr/local/share/apps/kittystory/sprites/cat.svg",#' usr/local/share/hpm/kittystory/hpm.toml
hpm publish kittystory --all --changelog "First release"
```

The cost of listing files: a new kind of file in the app's folder (say a `fonts/` folder)
must be added to the list, or publish won't carry it.

## Decisions of this fix

| # | Proposal | Why |
|---|---|---|
| 1 | **Init checks every manifest of the program that is in the world,** not only those written in this session | In the user's run, the problem was in manifests from an earlier run that the second run never looked at |
| 2 | **Init shows every manifest of the program at the end,** the old ones too | You read what will be published, not only what changed this time |
| 3 | **The init prompt gets the rule about files of an extra inside the app's folder** | The AI broke a rule it had; one example of the way out makes a second mistake less likely. The check (2) catches it either way |
| 4 | **An extra's manifest that the app doesn't list is a problem in init** | `publish --all` would leave it out without a word, and no overlap check would see it |
| 5 | **No new command** (such as `hpm check NAME`) | Init and publish both check now; a third way in isn't needed yet. Easy to add later on top of `family_problems` |

## Also seen, not part of this fix

- **Step 6 says "the log of the world gets a line"** for each AI session. That wasn't built:
  from a terminal, hpm writes nothing to `.hallux/hallux.log` (only a failed session and the
  tab's migrations log). The checklist and the tutorial were corrected on 2026-10-24 to say
  so. Whether to build the line is a separate question.
- **Removing only the app's manifest to run init again** keeps the extras' manifests from
  the first run, and the AI sees and keeps them ("the packages are the same as before").
  With this fix those are checked and shown; whether init should say up front "these
  manifests are there from before, and stay" is a small extra, left for the build.
