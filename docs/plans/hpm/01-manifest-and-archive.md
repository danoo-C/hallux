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
| `bundle` | a list of package names; a bundle has no `files` |
| `private` | true or false; missing means false |
| `rules` | a list of lines, for a rules extra (hpm.md decision 5) |

- Every problem is found and told at once, as `gui`'s layouts are checked: unknown keys,
  wrong types, an extra that needs one that doesn't exist, needs that go round in a circle,
  a bundle with files, a pattern in two kinds.
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
- Every check, and all problems at once.
- Patterns: `*`, `**`, `~`, refused paths; `expand` over a list of paths.
- Versions: 1.4 < 1.10 < 2.0; 1.4 == 1.4.0 is refused as ambiguous (one form only).
- `pack` then `unpack` gives the same files; the same folder packs to the same bytes.
- `unpack` refuses: a link, an absolute name, `..`, too many files, too big; nothing is
  written then.

## Done when

kittystory's manifest from hpm.md section 3, typed by hand, is read and checked, and a
folder laid out as a package packs and unpacks to the same files.
