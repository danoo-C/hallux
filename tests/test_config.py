import re
from dataclasses import fields
from pathlib import Path

import pytest

from hallux import config
from hallux.config import Hardware


def write_config(root, text):
    (root / ".hallux").mkdir(exist_ok=True)
    (root / ".hallux" / "config.toml").write_text(text)


def saved(root):
    """The config file as it is on the disk, with its own line endings."""
    return (root / ".hallux" / "config.toml").read_bytes().decode("utf-8")


def readme_example():
    """The config.toml that the README shows."""
    readme = (Path(__file__).resolve().parent.parent / "README.MD").read_text(encoding="utf-8")
    return readme.split("## Configuration")[1].split("```toml\n")[1].split("```")[0]


def test_defaults(tmp_path):
    assert config.load(tmp_path) == Hardware(model="claude-opus-5-5", effort="low", status_bar=True)


def test_config_file_then_flags(tmp_path):
    write_config(tmp_path, 'model = "claude-sonnet-5-5"\neffort = "medium"\n'
                           'fallback_model = "claude-haiku-4-5"\nmax_budget_usd = 2.5\n')
    assert config.load(tmp_path) == Hardware("claude-sonnet-5-5", "medium", "claude-haiku-4-5", 2.5)
    assert config.load(tmp_path, effort="high", model=None) == Hardware(
        "claude-sonnet-5-5", "high", "claude-haiku-4-5", 2.5)


def test_the_addons_setting(tmp_path):
    assert config.load(tmp_path).addons is None                    # left out: all that loaded
    write_config(tmp_path, 'addons = ["window", "sound_card"]\n')
    assert config.load(tmp_path).addons == ("window", "sound_card")
    write_config(tmp_path, "addons = []\n")
    assert config.load(tmp_path).addons == ()                      # none


def test_the_event_budget_setting(tmp_path):
    assert config.load(tmp_path).event_budget_usd == 0.25
    write_config(tmp_path, "event_budget_usd = 2\n")
    assert config.load(tmp_path).event_budget_usd == 2
    write_config(tmp_path, "event_budget_usd = 0\n")
    assert config.load(tmp_path).event_budget_usd == 0                # events are off


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
    ("event_budget_usd = -0.5\n", "event_budget_usd must be a number, 0 or more"),
    ('event_budget_usd = "a lot"\n', "event_budget_usd must be a number"),
    ("event_budget_usd = true\n", "event_budget_usd must be a number"),
    ('keep_transcripts = "no"\n', "keep_transcripts must be true or false"),
    ('addons = "window"\n', "addons must be a list of addon names"),
    ("addons = true\n", "addons must be a list of addon names"),
    ('addons = ["window", 3]\n', "addons must be a list of addon names"),
    ('addons = ["window.py"]\n', "addons must be a list of addon names"),
    ('addons = ["Window"]\n', "addons must be a list of addon names"),
    ("agent_max_running = -1\n", "agent_max_running must be a whole number, 0 or more"),
    ("agent_max_running = 2.5\n", "agent_max_running must be a whole number, 0 or more"),
    ("agent_max_running = true\n", "agent_max_running must be a whole number, 0 or more"),
    ("agent_job_budget_usd = 0\n", "agent_job_budget_usd must be a positive number"),
    ("agent_budget_usd = -1\n", "agent_budget_usd must be a number, 0 or more"),
    ('agent_max_effort = "turbo"\n', "agent_max_effort must be one of low, medium, high"),
    ("agent_timeout_seconds = 0\n", "agent_timeout_seconds must be a positive number"),
    ('agent_model = ""\n', "agent_model must be a model name"),
    ("agent_model = 5\n", "agent_model must be a model name"),
    ('model = "claude-opus-5-5\n', r"config\.toml: Illegal character"),   # broken TOML
])
def test_bad_config_is_a_readable_error(tmp_path, text, message):
    write_config(tmp_path, text)
    with pytest.raises(ValueError, match=message):
        config.load(tmp_path)


def test_a_wrong_file_is_named_with_its_setting(tmp_path):
    write_config(tmp_path, 'effort = "turbo"\n')
    with pytest.raises(ValueError) as e:
        config.load(tmp_path)
    assert str(e.value) == (f"{tmp_path / '.hallux' / 'config.toml'}: effort must be one of "
                            f"low, medium, high, xhigh, max, not 'turbo'")


# --- one setting by itself: check, typed, and when a change takes effect -------------------------

@pytest.mark.parametrize("name, value", [
    ("model", "claude-sonnet-5-5"),
    ("effort", "max"), ("effort", None),
    ("fallback_model", "claude-haiku-4-5"), ("fallback_model", None),
    ("max_budget_usd", 2.5), ("max_budget_usd", 3), ("max_budget_usd", None),
    ("status_bar", False), ("keep_transcripts", True), ("os_sandbox", True),
    ("tick_budget_usd", 0), ("tick_budget_usd", 1.25),
    ("event_budget_usd", 0.0), ("event_budget_usd", 2),
    ("tick_budget_usd", float("inf")),             # no limit, for who writes it into the file
    ("addons", None), ("addons", ()), ("addons", ("window", "sound_card")),
    ("agent_model", None), ("agent_model", "claude-haiku-4-5"),
    ("agent_max_effort", "low"), ("agent_max_effort", "max"),
    ("agent_max_running", 0), ("agent_max_running", 8),
    ("agent_job_budget_usd", 0.01), ("agent_job_budget_usd", 3),
    ("agent_budget_usd", 0), ("agent_budget_usd", 2.5),
    ("agent_timeout_seconds", 1), ("agent_timeout_seconds", 90.5),
])
def test_check_takes_a_good_value(name, value):
    assert config.check(name, value) is None


@pytest.mark.parametrize("name, value, words", [
    ("model", "", "must be a model name like claude-opus-5-5"),
    ("model", 5, "must be a model name like claude-opus-5-5"),
    ("effort", "turbo", "must be one of low, medium, high, xhigh, max, not 'turbo'"),
    ("fallback_model", 5, "must be a model name"),
    ("max_budget_usd", 0, "must be a positive number"),
    ("max_budget_usd", -1, "must be a positive number"),
    ("max_budget_usd", True, "must be a positive number"),
    ("max_budget_usd", "2", "must be a positive number"),
    ("status_bar", "yes", "must be true or false"),
    ("keep_transcripts", "no", "must be true or false"),
    ("os_sandbox", 1, "must be true or false"),
    ("tick_budget_usd", -1, "must be a number, 0 or more"),
    ("tick_budget_usd", True, "must be a number, 0 or more"),
    ("tick_budget_usd", None, "must be a number, 0 or more"),
    ("event_budget_usd", -0.5, "must be a number, 0 or more"),
    ("event_budget_usd", "a lot", "must be a number, 0 or more"),
    ("event_budget_usd", float("nan"), "must be a number, 0 or more"),
    ("max_budget_usd", float("nan"), "must be a positive number"),
    ("addons", "window", 'must be a list of addon names, like ["window"]'),
    ("addons", ("window", 3), 'must be a list of addon names, like ["window"]'),
    ("addons", ("Window",), 'must be a list of addon names, like ["window"]'),
    ("agent_model", "", "must be a model name like claude-opus-5-5"),
    ("agent_max_effort", None, "must be one of low, medium, high, xhigh, max, not None"),
    ("agent_max_effort", "turbo", "must be one of low, medium, high, xhigh, max, not 'turbo'"),
    ("agent_max_running", -1, "must be a whole number, 0 or more"),
    ("agent_max_running", 2.0, "must be a whole number, 0 or more"),
    ("agent_max_running", "2", "must be a whole number, 0 or more"),
    ("agent_job_budget_usd", 0, "must be a positive number"),
    ("agent_job_budget_usd", float("nan"), "must be a positive number"),
    ("agent_budget_usd", -0.5, "must be a number, 0 or more"),
    ("agent_budget_usd", None, "must be a number, 0 or more"),
    ("agent_timeout_seconds", 0, "must be a positive number"),
    ("agent_timeout_seconds", "600", "must be a positive number"),
])
def test_check_says_why_a_value_is_wrong(name, value, words):
    assert config.check(name, value) == words


def test_check_knows_every_setting_and_no_other():
    for f in fields(Hardware):
        assert config.check(f.name, f.default) is None
    with pytest.raises(KeyError):
        config.check("modle", "claude-opus-5-5")


def test_every_setting_says_when_a_change_takes_effect():
    assert set(config.WHEN) == {f.name for f in fields(Hardware)}
    assert set(config.WHEN.values()) == {"now", "reboot", "start"}
    now = {name for name, when in config.WHEN.items() if when == "now"}
    agents = {name for name in config.WHEN if name.startswith("agent_")}
    assert len(agents) == 6 and agents < now      # every job is a new session: from the next job
    assert now - agents == {"tick_budget_usd", "event_budget_usd", "max_budget_usd", "model"}


@pytest.mark.parametrize("name, text, value", [
    ("tick_budget_usd", "1.25", 1.25),
    ("tick_budget_usd", "$1.25", 1.25),
    ("tick_budget_usd", " $ 2 ", 2.0),
    ("event_budget_usd", "0", 0.0),
    ("event_budget_usd", ".5", 0.5),
    ("event_budget_usd", "3.", 3.0),
    ("max_budget_usd", "2", 2.0),
    ("max_budget_usd", "", None),                  # empty: no cap
    ("max_budget_usd", "  ", None),
    ("model", "  claude-sonnet-5-5 ", "claude-sonnet-5-5"),
    ("fallback_model", "claude-haiku-4-5", "claude-haiku-4-5"),
    ("fallback_model", "", None),                  # empty: none
    ("effort", "xhigh", "xhigh"),
    ("agent_model", " claude-haiku-4-5 ", "claude-haiku-4-5"),
    ("agent_model", "", None),                     # empty: the model the machine runs on
    ("agent_max_effort", "medium", "medium"),
    ("agent_max_running", "3", 3),                 # a whole number, and not 3.0
    ("agent_max_running", "0", 0),
    ("agent_job_budget_usd", "$0.50", 0.5),
    ("agent_budget_usd", "0", 0.0),
    ("agent_timeout_seconds", "600", 600.0),
    ("agent_timeout_seconds", "90s", 90.0),
    ("agent_timeout_seconds", " 90.5 s ", 90.5),
])
def test_typed_makes_a_value(name, text, value):
    made = config.typed(name, text)
    assert made == value and type(made) is type(value)


@pytest.mark.parametrize("name, text, words", [
    ("tick_budget_usd", "", "must be a number, 0 or more"),
    ("tick_budget_usd", "-1", "must be a number, 0 or more"),
    ("tick_budget_usd", "nan", "must be a number, 0 or more"),
    ("tick_budget_usd", "inf", "must be a number, 0 or more"),
    ("tick_budget_usd", "1e9", "must be a number, 0 or more"),
    ("tick_budget_usd", "abc", "must be a number, 0 or more"),
    ("tick_budget_usd", "9" * 400, "must be a number, 0 or more"),
    ("event_budget_usd", "1" * 13, "must be a number, 0 or more"),     # twelve digits at most
    ("event_budget_usd", "1.2.3", "must be a number, 0 or more"),
    ("event_budget_usd", "1,25", "must be a number, 0 or more"),
    ("event_budget_usd", "$", "must be a number, 0 or more"),
    ("max_budget_usd", "0", "must be a positive number"),
    ("max_budget_usd", "-1", "must be a positive number"),
    ("max_budget_usd", "nan", "must be a positive number"),
    ("max_budget_usd", "9" * 400, "must be a positive number"),
    ("effort", "turbo", "must be one of low, medium, high, xhigh, max, not 'turbo'"),
    ("effort", "", "must be one of low, medium, high, xhigh, max, not ''"),
    ("model", "", "must be a model name like claude-opus-5-5"),
    ("model", "   ", "must be a model name like claude-opus-5-5"),
    ("agent_max_running", "2.5", "must be a whole number, 0 or more"),
    ("agent_max_running", "-1", "must be a whole number, 0 or more"),
    ("agent_max_running", "", "must be a whole number, 0 or more"),
    ("agent_max_running", "two", "must be a whole number, 0 or more"),
    ("agent_max_running", "9" * 7, "must be a whole number, 0 or more"),
    ("agent_timeout_seconds", "0", "must be a positive number"),
    ("agent_timeout_seconds", "0s", "must be a positive number"),
    ("agent_timeout_seconds", "", "must be a positive number"),
    ("agent_timeout_seconds", "10 min", "must be a positive number"),
    ("agent_timeout_seconds", "1e3", "must be a positive number"),
    ("agent_job_budget_usd", "0", "must be a positive number"),
    ("agent_job_budget_usd", "", "must be a positive number"),      # it can't be left out
    ("agent_budget_usd", "", "must be a number, 0 or more"),
    ("agent_max_effort", "", "must be one of low, medium, high, xhigh, max, not ''"),
    ("status_bar", "off", "is set when Hallux starts: edit config.toml"),
    ("addons", "window", "is set when Hallux starts: edit config.toml"),
    ("keep_transcripts", "on", "is set when Hallux starts: edit config.toml"),
    ("os_sandbox", "on", "is set when Hallux starts: edit config.toml"),
])
def test_typed_refuses_with_the_reason(name, text, words):
    with pytest.raises(ValueError) as e:
        config.typed(name, text)
    assert str(e.value) == words


# --- save: config.toml changed line by line ---------------------------------------------------

def test_save_changes_one_line_of_the_readme_example(tmp_path):
    example = readme_example()
    write_config(tmp_path, example)
    config.save(tmp_path, {"tick_budget_usd": 1.25})
    changed = example.replace("tick_budget_usd = 0.25  ", "tick_budget_usd = 1.25  ")
    assert changed != example
    assert saved(tmp_path) == changed                 # every other line, and every comment
    assert config.load(tmp_path).tick_budget_usd == 1.25

    config.save(tmp_path, {"effort": "high", "max_budget_usd": 3.0})
    lines, before = saved(tmp_path).splitlines(), example.splitlines()
    was = {line.split(" = ")[0]: line for line in before if " = " in line}
    assert was["effort"].replace('"low"', '"high"') in lines               # the comment stays,
    assert was["max_budget_usd"].replace("2.0", "3.0") in lines            # spaces and all
    assert "#" in was["effort"] and "#" in was["max_budget_usd"] and len(lines) == len(before)
    assert config.load(tmp_path) == Hardware(
        "claude-opus-5-5", "high", "claude-haiku-4-5", 3.0, tick_budget_usd=1.25,
        addons=("window",))


def test_save_keeps_what_follows_the_value(tmp_path):
    write_config(tmp_path, 'model = "a#b"   # the "model", so far\n'
                           "fallback_model = 'c#d'# none\n"
                           "  tick_budget_usd=0.25\n"
                           "event_budget_usd =   2   \n")
    config.save(tmp_path, {"model": "claude-sonnet-5-5", "fallback_model": "claude-haiku-4-5",
                           "tick_budget_usd": 1.0, "event_budget_usd": 0.5})
    assert saved(tmp_path) == ('model = "claude-sonnet-5-5"   # the "model", so far\n'
                               'fallback_model = "claude-haiku-4-5"# none\n'
                               "  tick_budget_usd=1.0\n"
                               "event_budget_usd =   0.5   \n")


def test_save_adds_a_line(tmp_path):
    config.save(tmp_path, {"effort": "high"})                  # no file, and no folder for it
    assert saved(tmp_path) == 'effort = "high"\n'              # and no setting that wasn't changed
    write_config(tmp_path, "# mine\nstatus_bar = false")       # no line break at its end
    config.save(tmp_path, {"max_budget_usd": 2.0, "model": 'a"b\\c'})
    assert saved(tmp_path) == ('# mine\nstatus_bar = false\nmax_budget_usd = 2.0\n'
                               'model = "a\\"b\\\\c"\n')
    assert config.load(tmp_path) == Hardware(model='a"b\\c', max_budget_usd=2.0, status_bar=False)


def test_save_takes_a_line_out(tmp_path):
    write_config(tmp_path, 'model = "m"\n\nmax_budget_usd = 2.0   # the cap\neffort = "low"\n')
    config.save(tmp_path, {"max_budget_usd": None})
    assert saved(tmp_path) == 'model = "m"\n\neffort = "low"\n'
    config.save(tmp_path, {"fallback_model": None})            # it has no line: nothing to do
    assert saved(tmp_path) == 'model = "m"\n\neffort = "low"\n'


def test_save_with_nothing_to_change_writes_no_file(tmp_path):
    config.save(tmp_path, {"fallback_model": None})
    config.save(tmp_path, {})
    assert not (tmp_path / ".hallux").exists()


def test_save_leaves_every_other_line_as_it_is(tmp_path):
    text = ('\n# My machine.\n\n   # an indented comment\n'
            'addons = [\n  "window",   # the first\n]\n'
            '\ttick_budget_usd = 0.25\t# tabs\n\n\n')
    write_config(tmp_path, text)
    config.save(tmp_path, {"tick_budget_usd": 0.5})
    assert saved(tmp_path) == text.replace("0.25", "0.5")
    assert config.load(tmp_path).addons == ("window",)


def test_save_keeps_windows_line_endings(tmp_path):
    (tmp_path / ".hallux").mkdir()
    (tmp_path / ".hallux" / "config.toml").write_bytes(
        b'# mine\r\nmodel = "m"   # which\r\neffort = "low"\r\nstatus_bar = false')
    config.save(tmp_path, {"model": "n", "tick_budget_usd": 1.0, "effort": None})
    assert (tmp_path / ".hallux" / "config.toml").read_bytes() == (
        b'# mine\r\nmodel = "n"   # which\r\nstatus_bar = false\r\ntick_budget_usd = 1.0\r\n')


@pytest.mark.parametrize("text, message", [
    ('effort = "turbo"\n',                                         # wrong by now
     r"config\.toml: effort must be one of low, medium, high, xhigh, max, not 'turbo'\. "
     r"Nothing saved\."),
    ('modle = "m"\n', r"config\.toml: unknown setting modle \(known: .*\)\. Nothing saved\."),
    ('[budgets]\ntick = 1\n',                                      # a table
     r"config\.toml: unknown setting budgets \(known: .*\)\. Nothing saved\."),
    ('effort = "low\n', r"config\.toml: .*line 1.*\. Nothing saved\."),              # broken TOML
    ('model = "a"\nmodel = "b"\n', r"config\.toml: .*line 2.*\. Nothing saved\."),   # there twice
    ('model = """\nclaude-opus-5-5"""\n',                          # a value over several lines
     r"config\.toml: can't change model safely\. Edit the file\. Nothing saved\."),
    ('fallback_model = """\nmodel = "inside a string"\n"""\n',     # a line that looks like it
     r"config\.toml: can't change model safely\. Edit the file\. Nothing saved\."),
    ('"model" = "m"\n',                                            # a name this doesn't find
     r"config\.toml: can't change model safely\. Edit the file\. Nothing saved\."),
])
def test_save_writes_nothing_when_it_cannot(tmp_path, text, message):
    write_config(tmp_path, text)
    with pytest.raises(ValueError) as e:
        config.save(tmp_path, {"tick_budget_usd": 1.0, "model": "claude-sonnet-5-5"})
    assert re.fullmatch(message, str(e.value), re.DOTALL)
    assert saved(tmp_path) == text
    assert [f.name for f in (tmp_path / ".hallux").iterdir()] == ["config.toml"]


def test_save_refuses_a_value_the_file_cannot_hold(tmp_path):
    write_config(tmp_path, 'effort = "low"\n')
    for changes in ({"effort": "turbo"}, {"status_bar": False}, {"modle": "m"}):
        with pytest.raises(ValueError, match="can't change .* safely"):
            config.save(tmp_path, changes)
    assert saved(tmp_path) == 'effort = "low"\n'


def test_save_says_when_the_file_cannot_be_written(tmp_path):
    (tmp_path / ".hallux").write_text("in the way")           # a file where the folder would be
    with pytest.raises(ValueError) as e:
        config.save(tmp_path, {"effort": "high"})
    assert re.fullmatch(r"config\.toml: [A-Z][^.:\[\]]+\. Nothing saved\.", str(e.value))
    assert "safely" not in str(e.value)


def test_load_reads_what_save_wrote(tmp_path):
    typed = {"model": "claude-sonnet-5-5", "effort": "max", "fallback_model": "claude-haiku-4-5",
             "max_budget_usd": "$2", "tick_budget_usd": "0.00001", "event_budget_usd": "0"}
    config.save(tmp_path, {name: config.typed(name, text) for name, text in typed.items()})
    assert config.load(tmp_path) == Hardware(
        "claude-sonnet-5-5", "max", "claude-haiku-4-5", 2.0,
        tick_budget_usd=0.00001, event_budget_usd=0.0)


# --- the six settings of the addon agents ---------------------------------------------------------

def test_the_agents_settings_have_defaults(tmp_path):
    hw = config.load(tmp_path)
    assert (hw.agent_model, hw.agent_max_effort, hw.agent_max_running) == (None, "high", 2)
    assert (hw.agent_job_budget_usd, hw.agent_budget_usd, hw.agent_timeout_seconds) == (1.0, 2.0, 600)


def test_the_agents_settings_are_read_from_the_file(tmp_path):
    """The step's "Done when": a config.toml with all six loads."""
    write_config(tmp_path, 'agent_model = "claude-sonnet-5-5"\nagent_max_effort = "xhigh"\n'
                           "agent_max_running = 0\nagent_job_budget_usd = 0.5\n"
                           "agent_budget_usd = 4\nagent_timeout_seconds = 90\n")
    assert config.load(tmp_path) == Hardware(
        agent_model="claude-sonnet-5-5", agent_max_effort="xhigh", agent_max_running=0,
        agent_job_budget_usd=0.5, agent_budget_usd=4, agent_timeout_seconds=90)
    write_config(tmp_path, "agent_max_running = -1\n")
    with pytest.raises(ValueError) as e:
        config.load(tmp_path)
    assert str(e.value) == (f"{tmp_path / '.hallux' / 'config.toml'}: agent_max_running must be a "
                            f"whole number, 0 or more")


def test_a_budget_per_job_above_the_budget_for_all_jobs_is_refused(tmp_path):
    """No job could ever start. A budget for all jobs of 0 turns the agents off instead."""
    write_config(tmp_path, "agent_job_budget_usd = 3.0\n")       # the other is 2.00 by default
    with pytest.raises(ValueError) as e:
        config.load(tmp_path)
    assert str(e.value) == (f"{tmp_path / '.hallux' / 'config.toml'}: agent_job_budget_usd (3.0) "
                            f"must not be more than agent_budget_usd (2.0)")
    write_config(tmp_path, "agent_job_budget_usd = 3.0\nagent_budget_usd = 0\n")
    assert config.load(tmp_path).agent_budget_usd == 0
    write_config(tmp_path, "agent_job_budget_usd = 3.0\nagent_budget_usd = 3\n")
    assert config.load(tmp_path).agent_job_budget_usd == 3.0     # as much as all jobs: fine


def test_the_check_of_the_two_budgets_by_itself():
    wrong = Hardware(agent_job_budget_usd=3.0, agent_budget_usd=2.0)
    assert config.check_together(Hardware()) is None
    assert config.check_together(Hardware(agent_job_budget_usd=2.0)) is None
    assert config.check_together(Hardware(agent_job_budget_usd=3.0, agent_budget_usd=0)) is None
    assert config.check_together(wrong) == (
        "agent_job_budget_usd (3.0) must not be more than agent_budget_usd (2.0)")
    # behind the setting that was changed, in its row of the panel: short enough for 80 columns
    assert config.check_together(wrong, "agent_job_budget_usd") == "is over the budget for all jobs"
    assert config.check_together(wrong, "agent_budget_usd") == "is under the budget per job"
    assert config.check_together(wrong, "model") == config.check_together(wrong)


def test_typed_knows_nothing_of_the_other_budget():
    """It is given a name and a text. The machine checks the two together."""
    assert config.typed("agent_job_budget_usd", "3") == 3.0       # above the default for all jobs


def test_save_writes_an_agents_setting(tmp_path):
    write_config(tmp_path, "# mine\nagent_max_running = 2   # at once\n")
    config.save(tmp_path, {"agent_max_running": 3, "agent_timeout_seconds": 90.0,
                           "agent_model": "claude-haiku-4-5"})
    assert saved(tmp_path) == ("# mine\nagent_max_running = 3   # at once\n"
                               'agent_timeout_seconds = 90.0\nagent_model = "claude-haiku-4-5"\n')
    config.save(tmp_path, {"agent_model": None})                  # none again: its line goes
    assert "agent_model" not in saved(tmp_path)
    assert config.load(tmp_path) == Hardware(agent_max_running=3, agent_timeout_seconds=90.0)


def test_save_takes_two_budgets_that_are_right_only_together(tmp_path):
    """Save writes the changes in the order the settings were first touched, and checks the
    file after each. The budget per job, written first, is above what the file still says for
    all jobs. Tried in the check of 2026-10-05: with the pair in that check, Save refused."""
    changes = {"agent_job_budget_usd": 5.0, "agent_budget_usd": 10.0}
    config.save(tmp_path, changes)
    assert saved(tmp_path) == "agent_job_budget_usd = 5.0\nagent_budget_usd = 10.0\n"
    assert config.load(tmp_path) == Hardware(**changes)


def test_save_refuses_a_file_that_would_hold_a_wrong_pair(tmp_path):
    text = "agent_budget_usd = 0.5   # edited by hand while Hallux ran\n"
    write_config(tmp_path, text)
    with pytest.raises(ValueError) as e:
        config.save(tmp_path, {"agent_job_budget_usd": 0.75, "effort": "high"})
    assert str(e.value) == ("config.toml: agent_job_budget_usd (0.75) must not be more than "
                            "agent_budget_usd (0.5). Nothing saved.")
    assert saved(tmp_path) == text
    assert [f.name for f in (tmp_path / ".hallux").iterdir()] == ["config.toml"]
    config.save(tmp_path, {"agent_job_budget_usd": 0.25})         # a pair the file can hold
    assert config.load(tmp_path).agent_job_budget_usd == 0.25


def test_save_mends_a_wrong_pair_in_the_file(tmp_path):
    write_config(tmp_path, "agent_job_budget_usd = 3.0\n")       # wrong by now: load refuses it
    config.save(tmp_path, {"agent_job_budget_usd": 1.5})
    assert config.load(tmp_path).agent_job_budget_usd == 1.5


def test_the_model_of_an_agent():
    """Without agent_model: the model the main session really runs on, not the setting. The two
    differ when the setting holds a name that is no model."""
    assert config.agent_model(Hardware(), "claude-opus-5-5") == "claude-opus-5-5"
    assert config.agent_model(Hardware(model="claude-banana-9"), "claude-opus-5-5") == "claude-opus-5-5"
    assert config.agent_model(Hardware(agent_model="claude-haiku-4-5"), "claude-opus-5-5") == (
        "claude-haiku-4-5")


@pytest.mark.parametrize("asked, hardware, model, gets", [
    ("xhigh", Hardware(), "claude-opus-5-5", "high"),             # above the cap: capped
    ("max", Hardware(agent_max_effort="max"), "claude-opus-5-5", "max"),
    ("medium", Hardware(), "claude-opus-5-5", "medium"),          # below it: what it asks
    ("high", Hardware(agent_max_effort="low"), "claude-opus-5-5", "low"),
    (None, Hardware(), "claude-opus-5-5", "low"),                 # no ask: the machine's effort
    (None, Hardware(effort="max"), "claude-opus-5-5", "high"),    # capped the same way
    (None, Hardware(effort=None), "claude-opus-5-5", None),       # the machine has none either
    ("high", Hardware(effort=None), "claude-opus-5-5", "high"),
    ("high", Hardware(), "claude-haiku-4-5", None),               # Haiku has no effort levels
    (None, Hardware(), "claude-haiku-4-5-20251001", None),
])
def test_the_effort_of_an_agent(asked, hardware, model, gets):
    assert config.agent_effort(hardware, asked, model) == gets
