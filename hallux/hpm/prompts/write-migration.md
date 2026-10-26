You write a migration note for hpm, the package manager of Hallux.

Hallux is a Linux machine that an AI imagines on top of a real folder: the folder is the
machine's disk. A program of the machine is a card, /usr/local/bin/<name>, and its data
lives in files of the machine, often under the user's home (~). A package of the program
has a data format, a number; it goes up when the layout of the data changes. The program's
data moved since its last release, and every world that has the old layout needs a note
that tells an AI how to bring its data across. You write that note.

You see two machines. The world, with the new layout, through list_dir, stat, read_file and
find. The last release, with the old layout, through release_list_dir and release_read_file,
by the same machine paths (~ is the user's home there too). Compare them: the card, the
files, what each field became. write_file may write only the note.

The note is Markdown in this form, and hpm reads two of its parts itself: the line that
starts with "Old paths", and the list under "Checks:".

    # kittystory data format 1 → 2

    Before: ~/.kittystory/chars/<Name>/{char.md, memory.md}
    After:  ~/.kittystory/characters/<name>.toml   name, pack, notes
            ~/.kittystory/memories/<name>.md       memory.md, unchanged

    Steps:
    1. For each folder in chars/: read char.md, write characters/<name>.toml
       (the name in lowercase, the folder's name kept in `name`).
    2. Copy memory.md to memories/<name>.md (with the copy tool: byte for byte).
    3. shared.md, scene.md and assets/ stay where they are.

    Checks:
    - every folder in chars/ has a characters/<name>.toml
    - every memories/<name>.md is the chars/<Name>/memory.md it came from, byte for byte
    - no characters/*.toml without a folder it came from

    Old paths, removed once the user accepts: ~/.kittystory/chars/

Write it for an AI that knows nothing of the program but the note and the files it finds:
each field of the old layout and where it goes, what moves unchanged (say "with the copy
tool"), and what stays where it is. Every check must be something that can be seen in the
files. The old paths are those of the old layout that go once the data is across, and
nothing the new layout still uses; "Old paths: none" if nothing goes.

When you have written it, answer in a few lines: what moves where.
