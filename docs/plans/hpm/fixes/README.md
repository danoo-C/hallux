# hpm: fixes after the build

[The plan](../README.md) · fixes for what the user's own use of hpm turned up, after the nine
steps were built. One file per fix; each says what went wrong, why, and what to build.

| Fix | What | Status |
|---|---|---|
| [01](01-init-overlapping-packages.md) | `hpm init` keeps manifests that share a file, and only `publish` finds out | **Planned** 2026-10-24; its decisions are proposals, not confirmed |
| [02](02-memory-line-double-tag.md) | The memory line ends with two version tags (`[hpm kittystory 1.0] [hpm kittystory 1.1]`) | **Planned** 2026-10-24; proposals, not confirmed |
| [03](03-manifest-words-left-behind.md) | A new version keeps the manifest's old summary, memory line and requires | **Planned** 2026-10-24; proposals, not confirmed |
| [04](04-adopt-records-no-extras.md) | An adopted app (the author's world after publish) records none of its extras | **Planned** 2026-10-24; proposals, not confirmed |
| [05](05-docs-log-line.md) | The tutorial and checklist say hpm's AI writes no log line; it does | **Planned** 2026-10-24; docs only |

02 to 05 come from a read-only review of the user's own run on 2026-10-24: kittystory
published from `~/hallux-distros/danika`, installed from nothing in `test-kittystory`, then
updated to 1.1. The rest of that run checked out: every file hpm recorded matched the
disk, the update wrote only the four changed files, and kept data and seeds as they were.
