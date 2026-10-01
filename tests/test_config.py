import pytest

from hallux import config
from hallux.config import Hardware


def write_config(root, text):
    (root / ".hallux").mkdir(exist_ok=True)
    (root / ".hallux" / "config.toml").write_text(text)


def test_defaults(tmp_path):
    assert config.load(tmp_path) == Hardware(model="claude-opus-5-5", effort="low", status_bar=True)


def test_config_file_then_flags(tmp_path):
    write_config(tmp_path, 'model = "claude-sonnet-5-5"\neffort = "medium"\n'
                           'fallback_model = "claude-haiku-4-5"\nmax_budget_usd = 2.5\n')
    assert config.load(tmp_path) == Hardware("claude-sonnet-5-5", "medium", "claude-haiku-4-5", 2.5)
    assert config.load(tmp_path, effort="high", model=None) == Hardware(
        "claude-sonnet-5-5", "high", "claude-haiku-4-5", 2.5)


def test_haiku_gets_no_effort():
    assert Hardware(model="claude-haiku-4-5", effort="max").model_effort is None
    assert Hardware(model="claude-sonnet-5-5", effort="max").model_effort == "max"


@pytest.mark.parametrize("text, message", [
    ('modle = "claude-opus-5-5"\n', "unknown setting modle"),
    ('effort = "turbo"\n', "effort must be one of"),
    ('model = ""\n', "model must be"),
    ("max_budget_usd = -1\n", "positive number"),
    ("max_budget_usd = true\n", "positive number"),
    ('status_bar = "yes"\n', "status_bar must be true or false"),
    ("os_sandbox = 1\n", "os_sandbox must be true or false"),
    ("tick_budget_usd = -1\n", "tick_budget_usd must be a number"),
    ('keep_transcripts = "no"\n', "keep_transcripts must be true or false"),
    ('model = "claude-opus-5-5\n', r"config\.toml: Illegal character"),   # broken TOML
])
def test_bad_config_is_a_readable_error(tmp_path, text, message):
    write_config(tmp_path, text)
    with pytest.raises(ValueError, match=message):
        config.load(tmp_path)
