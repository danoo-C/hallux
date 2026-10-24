# hpm: fixes after the build

[The plan](../README.md) · fixes for what the user's own use of hpm turned up, after the nine
steps were built. One file per fix; each says what went wrong, why, and what to build.

| Fix | What | Status |
|---|---|---|
| [01](01-init-overlapping-packages.md) | `hpm init` keeps manifests that share a file, and only `publish` finds out | **Planned** 2026-10-24; its decisions are proposals, not confirmed |
| [02](02-memory-line-double-tag.md) | The memory line ends with two version tags (`[hpm kittystory 1.0] [hpm kittystory 1.1]`) | **Built** 2026-10-24 |
| [03](03-manifest-words-left-behind.md) | A new version keeps the manifest's old summary, memory line and requires | **Planned** 2026-10-24; proposals, not confirmed |
| [04](04-adopt-records-no-extras.md) | An adopted app (the author's world after publish) records none of its extras | **Built** 2026-10-24 |
| [05](05-docs-log-line.md) | The tutorial and checklist say hpm's AI writes no log line; it does | **Done** 2026-10-24; docs only |
| [06](06-install-carries-clean-seeds.md) | A world that installed an app has no clean seeds, so publishing from it sends its used ones | **Planned** 2026-10-24; proposals, not confirmed |
| [07](07-publish-asks-about-used-seeds.md) | Publish sends a used seed without asking, and an old clean copy without saying | **Planned** 2026-10-24; proposals, not confirmed; builds on 06 |

02 to 05 come from a read-only review of the user's own run on 2026-10-24: kittystory
published from `~/hallux-distros/danika`, installed from nothing in `test-kittystory`, then
updated to 1.1. The rest of that run checked out: every file hpm recorded matched the
disk, the update wrote only the four changed files, and kept data and seeds as they were.

06 and 07 come from a read-only analysis of publishing from a world the app was installed
into (init in one world, install into a second, change it there, publish from there). That
works, with these catches: the seeds (06, 07); the second world's extras wiped from its record by the
adopt after publish (fix 04's bug, which hits an installed world too); and no merge, so
publishing later from the first world without updating it first drops the second world's
change and its changelog entry (not planned as a fix: update before you change a world).
