# Step 1: the manifest and the archive

[The plan](README.md) · the design: [hpm.md](../../hpm/hpm.md), sections 3 and 6a; plan
decisions 1, 2, 13

**Needs:** nothing. **Changes:** new `hallux/hpm/__init__.py`, `manifest.py`,
`archive.py`; `tests/test_hpm_manifest.py`, `tests/test_hpm_archive.py`.

After this step a manifest can be read and checked, and a package packed and unpacked.
Nothing reads a world or writes one yet.

## Build

**`manifest.py`: `Manifest.load(text)` and `check`.** Read with `tomllib`. What it knows:

| Key | What |
|---|---|
| `name` | letters, digits, `-`; at most 40; starts with a letter |
| `version` | dotted whole numbers (decision 13); `Version` compares them |
| `summary`, `author` | text, at most 120 characters |
| `data_format` | a whole number from 1; missing means 1 |
| `requires.addons`, `requires.packages` | lists of names |
| `memory_line` | one line, at most 300 characters, no newline |
| `files.app`, `files.seed`, `files.data` | lists of patterns |
| `extras.<key>` | `package`, `default`, `needs` (other extras' keys) |
| `for` | a data package's app |
| `bundle` | a list of package names; a bundle has no `files`, but a `version` like any package |
| `private` | true or false; missing means false |
| `rules` | a list of lines, for a rules extra (hpm.md decision 5) |

- Every problem is found and told at once, as `gui`'s layouts are checked: unknown keys,
  wrong types, an extra that needs one that doesn't exist, needs that go round in a circle,
  a bundle with files or without a version, the same pattern written in two kinds.
- **A file two kinds match** (hpm.md section 3) isn't a problem: `kind_of(path)` gives the
  narrower kind, `data` before `seed` before `app`. So the design's own manifest, with
  `state.json` as a `seed` inside the `app` folder, is good.
- **Patterns.** `/` or `~/` in front, then a path; `*` within a name and `**` for any depth.
  No `..`, nothing under `/.hallux`, nothing under `/proc`-like names the machine invents
  (`/proc`, `/sys`, `/dev`). `match(pattern, path)` and `expand(pattern, files)` work on
  machine paths, so step 2 can give them a world's files and step 3 a package's.
- **`~`.** A pattern keeps its `~`. `place(path, home)` turns `~/x` into `/home/<user>/x`
  when a world's user is known (step 3).

**`archive.py`.**
- `pack(folder, out)`: the folder of hpm.md section 3 (`hpm.toml`, `CHANGELOG.md`,
  `files/root/…`, `files/home/…`, `migrations/`) into one `.hpm` file, a gzipped tar, with
  the names in a fixed order and times kept, so the same files make the same archive.
- `unpack(file, into)`: the checks of decision 2, all before anything is written; a file
  that breaks one is refused as a whole, with what was wrong.
- `sha256(file)`; `read_manifest(file)` reads only `hpm.toml` out of an archive, without
  unpacking the rest (the install screen needs only that).

## Tests

- Good manifests: an app, a data package, a bundle, a rules extra; their defaults.
- `kind_of`: `state.json` under the app's `**` is a `seed`; a file only `app` matches is
  `app`; a file no pattern matches has no kind.
- Every check, and all problems at once.
- Patterns: `*`, `**`, `~`, refused paths; `expand` over a list of paths.
- Versions: 1.4 < 1.10 < 2.0; 1.4 == 1.4.0 is refused as ambiguous (one form only).
- `pack` then `unpack` gives the same files; the same folder packs to the same bytes.
- `unpack` refuses: a link, an absolute name, `..`, too many files, too big; nothing is
  written then.

## Done when

kittystory's manifest from hpm.md section 3 (as corrected by the review: its `seed` inside
the `app` folder), typed by hand, is read and checked, and a folder laid out as a package
packs and unpacks to the same files.

## As built

Built 2026-10-23: `hallux/hpm/__init__.py`, `manifest.py`, `archive.py`;
`tests/test_hpm_manifest.py` (92 tests), `tests/test_hpm_archive.py` (36). The whole suite:
2033 passed. One test, `test_sandbox.py::test_claude_code_starts_inside_the_sandbox`,
can't run inside the sandbox of the session that built this (bubblewrap inside bubblewrap)
and was left out of that run. It has nothing to do with hpm.

What the code does that the step above didn't say, or says differently:

- **1.4 and 1.4.0 are the same version.** They are equal and have one hash, so a store
  can't hold both (step 2's "a version that is there already"). `str` keeps the form that
  was written. What's refused is a second way of writing one *number*: `1.04`, `01`.
  A version has at most four numbers, of at most six digits each.
- **Patterns.** A `**` at the end matches what is inside the folder, not the folder;
  elsewhere it matches no folders or more (`/a/**/z` matches `/a/z`). Only `*` and `**` are
  wildcards: `? [ ] { } \` in a pattern are refused, and so are control characters. A
  `.hallux` folder under a home (`~/.hallux/…`) is allowed: only `/.hallux` is the
  machine's.
- **Addon names** follow `ADDON_NAME` of `hallux/addons.py` (lowercase, `_`), package names
  the step's rule (letters, digits, `-`, starting with a letter, at most 40).
- **A bundle** carries nothing of its own: `files`, `extras`, `for` and `rules` are refused
  in one, and so is an empty list.
- **Two extras with the same package** are refused, and so is an extra that needs itself;
  a circle is told with its keys (`a → c → b → a`).
- **An hpm.toml** is at most 64 KB.
- **The archive keeps no modes and no owners.** Every file goes in as 0644 with owner 0,
  and the gzip header has no time and no name. That is what makes the same files give the
  same bytes on any machine. Only files are stored, so an empty folder doesn't travel.
- **The layout is strict.** At the top only `hpm.toml`, `CHANGELOG.md`, `files/` and
  `migrations/`; under `files/` only `root/` and `home/`; `migrations/` holds `.md` notes
  and no folders. Step 6 adds `review.md` to that list.
- **`pack` checks first and tells everything at once:** the manifest, and every file
  (links, devices, names outside the layout, paths under `/proc`, the limits). Its file is
  written beside the target and renamed, so it appears whole or not at all.
- **`unpack` reads the file twice:** once to check every header, once to write. If the
  second read differs from the first, it stops. It writes into a new folder, or an empty
  one, never over a file (`open("xb")`). If anything fails on the way, the new folder is
  taken away again, and an empty one is left empty.
- **`sha256` gives `"sha256:<hex>"`,** the form the world's record shows (hpm.md section 8).
- **Added for steps 2 and 3:** `to_machine` and `to_member` (`files/home/x` ↔ `~/x`),
  `package_files(folder)` (an unpacked package's files by machine path), `check_path`,
  `check_pattern`.
