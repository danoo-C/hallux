"""hpm's config file, ~/.config/hallux/hpm.toml (docs/plans/hpm/config/)."""
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hallux.hpm import config as cfg
from hallux.hpm.paint import enabled
from hallux.hpm.store import store_home
from hallux.hpm.world import HpmError


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home" / "dano"
    (home / "hpm-live").mkdir(parents=True)
    return home


def env_of(home, **more):
    return {"HOME": str(home), **more}


def write(home, text):
    path = home / ".config/hallux/hpm.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


# ---------------------------------------------------------------- where the file is

def test_the_file_is_in_the_home_and_xdg_config_home_changes_nothing(home, tmp_path):
    assert cfg.config_path(env_of(home)) == home / ".config/hallux/hpm.toml"
    assert cfg.config_path(env_of(home, XDG_CONFIG_HOME=str(tmp_path / "elsewhere"))) == \
        home / ".config/hallux/hpm.toml"
    assert cfg.config_path(env_of(home, HPM_CONFIG=str(tmp_path / "x.toml"))) == tmp_path / "x.toml"


# ---------------------------------------------------------------- reading it

def test_no_file_is_the_defaults(home):
    found = cfg.load(env_of(home))
    assert (found.store, found.editor, found.color) == (None, None, None)


def test_the_three_keys(home):
    write(home, 'store = "~/hpm-live"   # my store\neditor = "nano -w"\ncolor = "never"\n')
    found = cfg.load(env_of(home))
    assert found.store == home / "hpm-live"
    assert (found.editor, found.color) == ("nano -w", "never")
    assert found.said("store") == "~/hpm-live"


@pytest.mark.parametrize("text, problem", [
    ('stor = "~/x"\n', "unknown key 'stor' (hpm knows store, editor, color)"),
    ("store = 3\n", "store must be the path of a folder"),
    ('store = "hpm-live"\n', "store must start with / or ~/"),
    ('color = "blue"\n', "color must be one of auto, always, never"),
    ('editor = ""\n', "editor must be a command"),
    ("store = [\n", "isn't TOML hpm can read"),
])
def test_a_mistake_names_the_file_and_the_key(home, text, problem):
    path = write(home, text)
    with pytest.raises(HpmError, match=str(path).replace(".", r"\.") + ".*" + problem.replace(
            "(", r"\(").replace(")", r"\)").replace("[", r"\[")):
        cfg.load(env_of(home))


def test_a_changed_file_is_read_again(home):
    path = write(home, 'color = "never"\n')
    assert cfg.load(env_of(home)).color == "never"
    path.write_text('color = "always"\n')
    os.utime(path, ns=(1, 1))                      # a new stamp, however fast the test is
    assert cfg.load(env_of(home)).color == "always"


# ---------------------------------------------------------------- the store

def test_store_home_order(home, tmp_path):
    assert store_home(env_of(home)) == home / ".local/share/hallux/hpm"
    write(home, 'store = "~/hpm-live"\n')
    assert store_home(env_of(home)) == home / "hpm-live"
    assert store_home(env_of(home, HPM_HOME=str(tmp_path / "t"))) == tmp_path / "t"


def test_a_store_that_isnt_there_is_an_error(home):
    write(home, 'store = "~/hpm-gone"\n')
    with pytest.raises(HpmError, match="store = '~/hpm-gone', but .*hpm-gone is no folder. "
                                       "Fix it with: hpm config set store PATH"):
        store_home(env_of(home))


def test_the_store_is_found_from_anywhere(home, tmp_path):
    """The user's goal: the same store wherever hpm runs, here from three folders in a new
    process with no HPM_HOME and no HPM_CONFIG, only HOME."""
    write(home, 'store = "~/hpm-live"\n')
    world = tmp_path / "danika"
    (world / ".hallux").mkdir(parents=True)
    clean = {k: v for k, v in os.environ.items() if k not in ("HPM_HOME", "HPM_CONFIG")}
    clean["HOME"] = str(home)
    code = "from hallux.hpm.store import Store; print(Store().home)"
    repo = Path(__file__).resolve().parents[1]
    for here in (world, repo, Path("/")):
        out = subprocess.run([sys.executable, "-c", code], cwd=here, env=clean | {
            "PYTHONPATH": str(repo)}, capture_output=True, text=True, check=True).stdout
        assert out.strip() == str(home / "hpm-live"), here


def test_a_wrong_file_is_an_error_not_a_traceback(home, monkeypatch, capsys):
    from hallux.hpm import cli
    write(home, "store = [\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("HPM_HOME")
    monkeypatch.delenv("HPM_CONFIG")
    assert cli.main(["search", "kitty"]) == 1
    assert "isn't TOML hpm can read" in capsys.readouterr().err


def test_the_packages_tab_boots_with_a_wrong_file(home, monkeypatch, tmp_path):
    """Its store is made when first used, so a wrong file is the tab's problem to show, not
    a machine that doesn't start."""
    from hallux.disk import Disk
    from hallux.hpm.running import Installs
    write(home, 'store = "~/hpm-gone"\n')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("HPM_HOME")
    monkeypatch.delenv("HPM_CONFIG")
    world = tmp_path / "w"
    (world / ".hallux").mkdir(parents=True)
    installs = Installs(Disk(world))                # no error here
    with pytest.raises(HpmError, match="is no folder"):
        installs.store


# ---------------------------------------------------------------- the editor and the colors

def test_the_editors_order(home, monkeypatch):
    found = {"nano": "/usr/bin/nano", "vi": "/usr/bin/vi"}
    monkeypatch.setattr(cfg.shutil, "which", lambda name, path=None: found.get(name))
    env = env_of(home)
    assert cfg.editor_command(env) == ("nano", "the default")
    del found["nano"]
    assert cfg.editor_command(env) == ("vi", "the default")
    del found["vi"]
    assert cfg.editor_command(env) == (None, "")
    assert cfg.editor_command(env_of(home, EDITOR="micro")) == ("micro", "$EDITOR")
    assert cfg.editor_command(env_of(home, EDITOR="micro", VISUAL="code -w")) == ("code -w", "$VISUAL")
    write(home, 'editor = "nano"\n')
    assert cfg.editor_command(env_of(home, VISUAL="code -w")) == ("nano", "the file")
    assert cfg.editor_command(env_of(home, HPM_EDITOR="ed")) == ("ed", "HPM_EDITOR")


class Terminal(io.StringIO):
    def isatty(self):
        return True


def test_the_files_color(home):
    write(home, 'color = "never"\n')
    assert enabled(Terminal(), env_of(home)) is False
    assert enabled(Terminal(), env_of(home, HPM_COLOR="always")) is True
    write(home, 'color = "always"\n')
    assert enabled(io.StringIO(), env_of(home)) is True
    assert enabled(io.StringIO(), env_of(home, NO_COLOR="1")) is False
    write(home, "color = [\n")                       # a broken file never stops the colors
    assert enabled(Terminal(), env_of(home)) is True


def test_root_is_told_once(home, monkeypatch, capsys):
    monkeypatch.setattr(cfg.os, "geteuid", lambda: 0)
    monkeypatch.setattr(cfg, "_root_told", False)
    cfg.load(env_of(home))
    cfg.load(env_of(home))
    err = capsys.readouterr().err
    assert err.count("hpm runs as root, so it reads") == 1
