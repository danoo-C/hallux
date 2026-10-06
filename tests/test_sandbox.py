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


def test_the_script_isnt_written_again_when_it_is_there_and_right(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    folder = tmp_path / ".hallux"
    script = sandbox.wrapper(folder, cli=tmp_path / "claude")
    first, text = script.stat(), script.read_text()
    again = sandbox.wrapper(folder, cli=tmp_path / "claude").stat()
    assert (again.st_ino, again.st_mtime_ns) == (first.st_ino, first.st_mtime_ns)
    assert [entry.name for entry in folder.iterdir()] == ["claude-in-bwrap"]     # nothing beside it

    script.write_text("#!/bin/sh\nexec something else\n")            # not what it should be,
    assert sandbox.wrapper(folder, cli=tmp_path / "claude").read_text() == text
    script.chmod(0o644)                                              # or not to be run,
    sandbox.wrapper(folder, cli=tmp_path / "claude")
    assert os.access(script, os.X_OK)
    other = sandbox.wrapper(folder, cli=tmp_path / "elsewhere" / "claude").read_text()
    assert other != text and str(tmp_path / "elsewhere" / "claude") in other    # or for another


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
