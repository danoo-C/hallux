"""The hallux app. For now: the command line and an environment check."""
import argparse
from importlib.metadata import version
from pathlib import Path


def main() -> None:
    cli = argparse.ArgumentParser(prog="hallux", description="a hallucinated shell")
    cli.add_argument("root", type=Path, help="the folder that becomes the machine's /")
    cli.add_argument("--model", help="e.g. claude-haiku-4-5, claude-sonnet-5-5, claude-opus-5-5")
    cli.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    flags = cli.parse_args()

    print(f"hallux {version('hallux')}, claude-agent-sdk {version('claude-agent-sdk')}")
    print(f"root: {flags.root.resolve()} (the machine itself isn't built yet)")
