"""The hallux command line.

    python hallux.py <root>                        the machine, in your terminal
    python hallux.py <root> --script cmds.txt      run commands from a file (- for stdin)
    python hallux.py <root> --check reboot         build a new machine, check it survives a reboot

Every mode takes --model and --effort.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from hallux import addons, config
from hallux.addons import Addon
from hallux.config import Hardware
from hallux.disk import HIDDEN_NAME

log = logging.getLogger("hallux")
ADDONS_FOLDER = Path(__file__).resolve().parent.parent / "addons"    # at the root of the repo


def main() -> None:
    cli = argparse.ArgumentParser(prog="hallux", description="a hallucinated shell")
    cli.add_argument("root", type=Path, help="the folder that becomes the machine's / "
                                             "(created if it doesn't exist)")
    cli.add_argument("--model", help="e.g. claude-haiku-4-5, claude-sonnet-5-5, claude-opus-5-5")
    cli.add_argument("--effort", choices=config.EFFORTS)
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument("--script", type=Path, metavar="FILE",
                      help="type the commands in FILE (one per line; - for stdin) instead of "
                           "reading the keyboard")
    mode.add_argument("--check", choices=["reboot"],
                      help="build a new machine in ROOT (an empty or new folder) and check "
                           "that it survives a reboot")
    flags = cli.parse_args()

    root = flags.root.expanduser().resolve()
    home = Path.home().resolve()
    if root == home or root in home.parents:
        sys.exit(f"hallux: refusing to use {root} as the machine's disk; the AI can delete "
                 f"anything in it. Use a dedicated folder like ~/hallux-world.")
    headless = flags.script is not None or flags.check is not None
    if not headless and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        sys.exit("hallux: needs an interactive terminal (or --script)")
    if flags.check and root.exists() and any(root.iterdir()):
        sys.exit(f"hallux: the {flags.check} check builds a new machine; {root} isn't empty")
    try:
        hardware = config.load(root, model=flags.model, effort=flags.effort)
    except ValueError as e:
        sys.exit(f"hallux: {e}")

    _log_to(root)
    log.info("power on: %s", hardware)
    attached, notes = attach(root, hardware)    # once: a changed addon needs a restart
    if headless:
        _complain(notes)
        sys.exit(_headless(root, hardware, flags, attached))

    from hallux.machine import Machine          # imported late: pulls in the SDK
    from hallux.statusbar import StatusBar
    from hallux.terminal import Terminal        # and prompt_toolkit
    bar = StatusBar(hardware.model, hardware.model_effort) if hardware.status_bar else None
    if bar and notes:
        bar.update(note=" · ".join(notes))
    else:
        _complain(notes)
    terminal = Terminal(bar, before_power_cut=lambda: addons.stop_all(
        attached, addons.HARD_EXIT_SECONDS))
    try:
        asyncio.run(Machine(root, hardware, terminal, addons=attached).run())
    except Exception as e:                      # the SDK or the CLI failed: "hardware" error
        log.exception("crash")
        sys.exit(f"hallux: {e}")


def attach(root: Path, hardware: Hardware,
           folder: Path | None = None) -> tuple[list[Addon], list[str]]:
    """Load the addons this machine gets. Returns them, and a note for each one it was meant
    to get and doesn't: a broken addon never keeps the machine from starting."""
    folder = folder or ADDONS_FOLDER
    if hardware.addons == ():                   # addons = []: none, so nothing is imported
        return [], []
    if root == folder or root in folder.parents:
        # The AI could write a Python file there, and the next start would run it.
        log.warning("no addons: %s is inside the machine", folder)
        return [], [f"no addons: {folder} is inside the machine, which could write to it"]
    loaded, skipped = addons.load(folder, only=hardware.addons)
    log.info("addons: %s", ", ".join(addon.name for addon in loaded) or "none")
    return loaded, [f"addon {name} skipped: {reason}" for name, reason in skipped.items()]


def _complain(notes: list[str]) -> None:
    """Without a status bar, the notes go where the other hallux messages go."""
    for note in notes:
        print(f"hallux: {note}", file=sys.stderr)


def _headless(root: Path, hardware: Hardware, flags: argparse.Namespace,
              attached: list[Addon]) -> int:
    from hallux.script import REBOOT_SCRIPT, reboot_report, run_script, summary
    if flags.check:
        lines = REBOOT_SCRIPT
    elif str(flags.script) == "-":
        lines = sys.stdin.read().splitlines()
    else:
        lines = flags.script.read_text(encoding="utf-8").splitlines()
    try:
        records = asyncio.run(run_script(root, hardware, lines,
                                         echo=lambda text: print(text, end="", flush=True),
                                         addons=attached))
    except Exception as e:
        log.exception("crash")
        print(f"hallux: {e}", file=sys.stderr)
        return 1
    print(f"\n── {summary(records, hardware)}", file=sys.stderr)
    if not flags.check:
        return 0
    report, passed = reboot_report(records)
    print(f"\nreboot check: {'passed' if passed else 'FAILED'}\n{report}")
    return 0 if passed else 1


def _log_to(root: Path) -> None:
    (root / HIDDEN_NAME).mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(root / HIDDEN_NAME / "hallux.log", maxBytes=1_000_000,
                                  backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
