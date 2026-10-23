"""The hpm command (docs/hpm/hpm.md; the plan's step 2: publish and show).

    hpm publish NAME [--all] [--version V | --yes] [--changelog TEXT] [--user U]
                     [--private yes|no] [--world W]
    hpm show NAME

Without --world, hpm works on the world you are in: the folder you're in, or the first above
it with a .hallux folder. Every question has a flag, and without a terminal a question
whose flag is missing is an error that names it.
"""
from __future__ import annotations

import argparse
import sys

from hallux.hpm.publish import Questions, publish, show
from hallux.hpm.store import Store
from hallux.hpm.world import HpmError, find_world


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="hpm", description="the Hallux package manager: "
                                  "apps from one world into any other (docs/hpm/)")
    commands = cli.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = commands.add_parser("publish", help="put a release of a package into the store")
    p.add_argument("name", metavar="NAME")
    p.add_argument("--all", action="store_true", help="its extras too, each that changed")
    p.add_argument("--version", metavar="V", help="the release's version (else asked)")
    p.add_argument("--yes", action="store_true",
                   help="take the version hpm suggests for each, without asking")
    p.add_argument("--changelog", metavar="TEXT", help="the changelog entry (else $EDITOR)")
    p.add_argument("--user", metavar="U", help="whose home ~ is, in a world with several")
    p.add_argument("--private", choices=("yes", "no"),
                   help="the answer, if hpm asks whether to mark a package private")
    p.add_argument("--world", metavar="W", help="the world (else the one you are in)")

    s = commands.add_parser("show", help="a package in the store: versions, files, changelog")
    s.add_argument("name", metavar="NAME")
    return cli


def main(argv: list[str] | None = None, questions: Questions | None = None,
         store: Store | None = None) -> int:
    flags = parser().parse_args(argv)
    questions = questions or Questions()
    store = store or Store()
    try:
        if flags.command == "publish":
            world = find_world(given=flags.world)
            publish(world, flags.name, store, questions, every=flags.all,
                    version=flags.version, changelog=flags.changelog, user=flags.user,
                    private=None if flags.private is None else flags.private == "yes",
                    suggested=flags.yes)
        elif flags.command == "show":
            questions.say(show(store, flags.name))
    except HpmError as e:
        print(f"hpm: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("hpm: stopped; nothing more was written", file=sys.stderr)
        return 130
    return 0
