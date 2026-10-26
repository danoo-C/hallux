"""hpm, the Hallux package manager (docs/hpm/, the plan in docs/plans/hpm/).

A package is a set of files from a world plus a manifest, hpm.toml. One store on the PC,
above every world, holds the releases; hpm copies them into any world.

    manifest.py   hpm.toml: what a package holds and needs, read and checked
    archive.py    .hpm files: a package's folder packed into one file, and unpacked safely
"""
