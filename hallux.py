#!/usr/bin/env python3
"""Launch hallux: python hallux.py <root> [--model MODEL] [--effort LEVEL]

Works with any Python: if this isn't the project's .venv, it re-runs itself there.
Run `python install.py` once first.
"""
import os
import subprocess
import sys
from pathlib import Path

VENV = Path(__file__).resolve().parent / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

if Path(sys.prefix).resolve() != VENV.resolve():
    if not VENV_PYTHON.exists():
        sys.exit("hallux: no .venv found, run `python install.py` first")
    if os.environ.get("HALLUX_REEXEC"):             # already re-ran once; don't loop forever
        sys.exit(f"hallux: {VENV_PYTHON} doesn't run inside {VENV}, try `python install.py --fresh`")
    os.environ["HALLUX_REEXEC"] = "1"
    cmd = [str(VENV_PYTHON), __file__, *sys.argv[1:]]
    if sys.platform == "win32":
        sys.exit(subprocess.call(cmd))
    os.execv(cmd[0], cmd)                           # replace this process: tty and signals stay direct

# The hallux/ package folder takes precedence over this hallux.py file on import.
from hallux.app import main

main()
