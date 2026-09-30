"""The hallux command line: python hallux.py <root> [--model MODEL] [--effort LEVEL]."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from hallux import config
from hallux.disk import HIDDEN_NAME


def main() -> None:
    cli = argparse.ArgumentParser(prog="hallux", description="a hallucinated shell")
    cli.add_argument("root", type=Path, help="the folder that becomes the machine's / "
                                             "(created if it doesn't exist)")
    cli.add_argument("--model", help="e.g. claude-haiku-4-5, claude-sonnet-5-5, claude-opus-5-5")
    cli.add_argument("--effort", choices=config.EFFORTS)
    flags = cli.parse_args()

    root = flags.root.expanduser().resolve()
    home = Path.home().resolve()
    if root == home or root in home.parents:
        sys.exit(f"hallux: refusing to use {root} as the machine's disk; the AI can delete "
                 f"anything in it. Use a dedicated folder like ~/hallux-world.")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.exit("hallux: needs an interactive terminal")
    try:
        hardware = config.load(root, model=flags.model, effort=flags.effort)
    except ValueError as e:
        sys.exit(f"hallux: {e}")

    (root / HIDDEN_NAME).mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(root / HIDDEN_NAME / "hallux.log", maxBytes=1_000_000,
                                  backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger("hallux").addHandler(handler)
    logging.getLogger("hallux").setLevel(logging.INFO)
    logging.getLogger("hallux").info("power on: %s", hardware)

    from hallux.machine import Machine          # imported late: pulls in the SDK
    from hallux.terminal import Terminal        # and prompt_toolkit
    try:
        asyncio.run(Machine(root, hardware, Terminal()).run())
    except Exception as e:                      # the SDK or the CLI failed: "hardware" error
        logging.getLogger("hallux").exception("crash")
        sys.exit(f"hallux: {e}")
