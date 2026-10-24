# Fix 02: the memory line ends with two version tags

[The fixes](README.md) · [the plan](../README.md) · built on [step 3](../03-install-engine.md)
(the memory lines) and [step 6](../06-ai-session.md) (`hpm init`)

**Status:** planned 2026-10-24, from a read-only review of the user's own run ("please
append these to the plans/hpm/fixes"). Not built. The decisions below are proposals, not
confirmed.

**Changes:** `hallux/hpm/record.py` (a helper that takes tags off a line, used by
`set_memory`), `hallux/hpm/assist.py` (init gives the AI the line without its tag),
`hallux/hpm/publish.py` (takes a tag out of the manifest's `memory_line`),
`tests/test_hpm_engine.py`, `tests/test_hpm_ai.py`, `tests/test_hpm_publish.py`.

## What happened

Both of the user's worlds, after kittystory 1.1 was published from `danika` and installed
then updated in `test-kittystory`, have this under "Invented programs" in
`.hallux/memory.md`:

```
- kittystory: chat with characters …; -w web (SVG scene, sprites, faces, ⚙ config), -g gui [hpm kittystory 1.0] [hpm kittystory 1.1]
```

Only the last tag is hpm's. The one before it is part of the manifest's own text: the
`memory_line` in `danika/usr/local/share/hpm/kittystory/hpm.toml`, and in both releases in
the store (1.0 and 1.1 differ only in `version`), ends with `[hpm kittystory 1.0]`. The
machine reads the line as it is, so it is told two versions of kittystory are there.

## Why

1. **Init hands the AI a tagged line.** `hallux/hpm/assist.py:64`:
   `line = rec.untagged_line(disk, name) or next(iter(rec.memory_lines(disk, name)), None)`.
   When the machine's own line was replaced by hpm's (an install, an adopt, a publish that
   adopts), only a tagged line is left, and `memory_lines` returns it whole: the `- ` in
   front and `[hpm kittystory 1.0]` at the end. `init_job` puts it under "What the
   machine's memory says of it", and the AI copied it into `memory_line`.
   The user's world fits this: a first init and publish (which adopts, and so tags the
   line), then the store emptied and init run again. That order is likely, not confirmed;
   the log has the two inits (00:18, 00:30) but not the publishes in between.
2. **Nothing takes a tag out of a manifest.** `Manifest.load` checks `memory_line`'s
   length only, and publish packs it as it is.
3. **`set_memory` adds its tag after whatever the line holds** (`record.py`,
   `f"- {memory_line} {tag}"`). Replacing the line later still works: `_tagged` matches
   the last tag, so the whole line goes. Only the text is wrong.

## What to build

1. **One helper in `record.py`:** `untag(line) -> str` takes off a `- ` in front and every
   `[hpm <name> <version>]` at the end (any name: a line copied from another package's
   counts too).
2. **Init gives the AI the line untagged** (`assist.py:64`, through `untag`).
3. **`set_memory` writes `untag(memory_line)`**, so the releases already in the store
   (kittystory 1.0 and 1.1) install with one tag (decision 1).
4. **Publish takes the tag out of the manifest** and says so: `hpm.toml: memory_line: took
   out "[hpm kittystory 1.0]"; hpm adds its own when it installs`. It writes the cleaned
   manifest back to the world, as it does with `version` (decision 2).

## Tests

- `set_memory` with a `memory_line` that ends in `[hpm kittystory 1.0]`, installed as 1.1:
  the memory has the line once, with `[hpm kittystory 1.1]` only. An update after it
  leaves one line.
- `untag` on `- x [hpm a 1.0]`, `x [hpm a 1.0] [hpm a 1.1]`, `x [hpm other 2]`, and a line
  with no tag (left as it is).
- Init in a world whose only kittystory line is tagged: the stand-in AI's first message has
  the line without `- ` and without the tag.
- Publish of a manifest whose `memory_line` has a tag: the release's `hpm.toml` has none,
  the world's manifest is rewritten without it, and the notice is said.

## Done when

- The tests pass, and the whole suite (`--deselect tests/test_sandbox.py`).
- On a copy of `test-kittystory`, `hpm rollback` then `hpm update kittystory` (from the
  store as it is, with the tagged 1.1) leaves one tag on the line. No paid run.

## By hand, until it is built

Before the next publish, take the tag out of danika's manifest:

```bash
cd ~/hallux-distros/danika
sed -i 's/ \[hpm kittystory 1\.0\]"$/"/' usr/local/share/hpm/kittystory/hpm.toml
grep '^memory_line' usr/local/share/hpm/kittystory/hpm.toml
```

The worlds' memory lines are rewritten cleanly by the next install or update of a release
without the tag.

## Decisions of this fix

| # | Proposal | Why |
|---|---|---|
| 1 | **`set_memory` cleans the line too,** not only init and publish | Releases with a tag are in the store already, and maybe in a friend's |
| 2 | **Publish takes the tag out and says so,** instead of refusing | The fix is mechanical and always the same; refusing would only send the user to sed |
