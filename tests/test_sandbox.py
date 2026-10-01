import os
import shutil
import subprocess

import pytest

from hallux import sandbox


def test_the_wrapper_hides_home_and_keeps_the_login(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    script = sandbox.wrapper(tmp_path / ".hallux", cli=tmp_path / "claude")
    text = script.read_text()
    home = os.path.expanduser("~")
    assert text.startswith("#!/bin/sh\n") and os.access(script, os.X_OK)
    assert "--ro-bind / /" in text and f"--tmpfs {home}" in text          # read-only, home hidden
    assert f"--bind-try {home}/.claude {home}/.claude" in text             # ... but the login
    assert "--unshare-pid" in text and "--die-with-parent" in text
    assert text.rstrip().endswith(f'-- {tmp_path / "claude"} "$@"')


def test_without_bubblewrap_it_says_how_to_get_it(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="apt install bubblewrap"):
        sandbox.wrapper(tmp_path)


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="needs bubblewrap")
def test_claude_code_starts_inside_the_sandbox(tmp_path):
    script = sandbox.wrapper(tmp_path)
    version = subprocess.run([str(script), "--version"], capture_output=True, text=True, timeout=30)
    if version.returncode != 0 and "Operation not permitted" in version.stderr:
        pytest.skip("no nested sandboxes here")
    assert "Claude Code" in version.stdout
