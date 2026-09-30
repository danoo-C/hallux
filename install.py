#!/usr/bin/env python3
"""Set up the hallux environment: python install.py [--fresh]

Creates .venv/ next to this file and installs hallux into it in editable mode
(pip install -e ".[dev]"), so `import hallux...` works from anywhere inside the venv
and code changes apply without reinstalling.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
MIN_PYTHON = (3, 11)


def run(*cmd: str | Path) -> None:
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    cli = argparse.ArgumentParser(description="Set up the hallux environment.")
    cli.add_argument("--fresh", action="store_true", help="delete .venv first and start over")
    flags = cli.parse_args()

    if sys.version_info < MIN_PYTHON:
        sys.exit(f"hallux needs Python {'.'.join(map(str, MIN_PYTHON))}+, "
                 f"this is {sys.version.split()[0]}")

    if flags.fresh and VENV.exists():
        print(f"removing {VENV}")
        shutil.rmtree(VENV)

    if not VENV_PYTHON.exists():
        try:
            run(sys.executable, "-m", "venv", VENV)
        except subprocess.CalledProcessError:
            shutil.rmtree(VENV, ignore_errors=True)   # don't leave a half-made venv behind
            sys.exit("could not create the virtual environment (see the message above)")

    run(VENV_PYTHON, "-m", "pip", "install", "--disable-pip-version-check", "-e", ".[dev]")
    run(VENV_PYTHON, "-c", "import hallux, claude_agent_sdk")

    print("\ndone. start the shell with:\n  python hallux.py ~/hallux-world")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(f"install failed: {e}")
