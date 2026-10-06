"""Optional: run Claude Code under bubblewrap, so the operating system enforces the fence too
(os_sandbox = true in .hallux/config.toml).

hallux's own fence already keeps the AI inside the machine's folder: Claude Code gets no tools
of its own, only hallux's, and every path goes through hallux.disk. This adds a second wall
for the case of a bug in that chain. Inside, the whole filesystem is read-only, your home
folder is hidden except ~/.claude (Claude Code's login and state), /tmp is private, and
Claude Code can't see other processes. The network stays: the model runs at Anthropic.
The machine's disk isn't needed in there: hallux's tools run in the hallux process.
"""
from __future__ import annotations

import os
import shlex
import shutil
import stat
import sys
from pathlib import Path

SCRIPT = "claude-in-bwrap"


def claude_cli() -> Path:
    """The Claude Code program the SDK starts: the bundled one, else `claude` on the PATH."""
    import claude_agent_sdk
    bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"
    if bundled.exists():
        return bundled
    if found := shutil.which("claude"):
        return Path(found)
    raise RuntimeError("os_sandbox: can't find the Claude Code program")


def wrapper(folder: Path, cli: Path | None = None) -> Path:
    """The script that starts Claude Code inside bubblewrap; returns its path. It is written
    when it isn't there, or isn't what it should be, and then in one step: the sessions of a
    run start at different times, a job's while the machine's is open, and none of them may
    find the script half-written."""
    if not sys.platform.startswith("linux"):
        raise RuntimeError("os_sandbox needs Linux (bubblewrap)")
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise RuntimeError("os_sandbox needs bubblewrap: sudo apt install bubblewrap")
    cli = (cli or claude_cli()).resolve()
    home = Path.home()
    q = lambda path: shlex.quote(str(path))               # noqa: E731
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / SCRIPT
    text = (
        "#!/bin/sh\n"
        "# Written by hallux (os_sandbox = true): Claude Code inside bubblewrap.\n"
        f"exec {q(bwrap)} \\\n"
        "  --ro-bind / / \\\n"
        f"  --tmpfs {q(home)} \\\n"
        f"  --bind-try {q(home / '.claude')} {q(home / '.claude')} \\\n"
        f"  --bind-try {q(home / '.claude.json')} {q(home / '.claude.json')} \\\n"
        f"  --ro-bind {q(cli)} {q(cli)} \\\n"
        "  --dev /dev --proc /proc --tmpfs /tmp --setenv TMPDIR /tmp \\\n"
        "  --unshare-pid --die-with-parent --chdir / \\\n"
        f"  -- {q(cli)} \"$@\"\n")
    try:
        there = script.read_text() == text and os.access(script, os.X_OK)
    except OSError:
        there = False
    if not there:
        new = folder / f".{SCRIPT}.{os.getpid()}"         # beside it, then renamed over it
        new.write_text(text)
        new.chmod(new.stat().st_mode | stat.S_IXUSR)
        os.replace(new, script)
    return script
