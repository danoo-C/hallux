"""hpm's colors (docs/plans/hpm/colors/)."""
import io

import pytest

from hallux.hpm.paint import enabled, kind_of, paint, strip_codes


class Terminal(io.StringIO):
    def isatty(self):
        return True


# ---------------------------------------------------------------- when colors are on

@pytest.mark.parametrize("stream, env, on", [
    (io.StringIO(), {}, False),                           # a pipe
    (Terminal(), {}, True),
    (Terminal(), {"NO_COLOR": "1"}, False),
    (Terminal(), {"NO_COLOR": ""}, True),                 # empty doesn't count
    (Terminal(), {"TERM": "dumb"}, False),
    (io.StringIO(), {"HPM_COLOR": "always"}, True),       # hpm list | less -R
    (Terminal(), {"HPM_COLOR": "never"}, False),
    (Terminal(), {"HPM_COLOR": "always", "NO_COLOR": "1"}, True),
    (object(), {}, False),                                # no isatty at all
])
def test_enabled(stream, env, on):
    assert enabled(stream, env) is on


# ---------------------------------------------------------------- what kind a line is

@pytest.mark.parametrize("line, kind", [
    ("  ✓ kittystory 1.1 updated (was 1.0), 4 files", "ok"),
    ("✓ pushed kittystory 1.1 to danika", "ok"),
    ("published kittystory 1.1: 10 files, 48.2 KB", "ok"),
    ("  ✗ kittystory-chars 1.1 failed: the disk is full", "fail"),
    ("✗ kittystory-chars: it carries files its manifest doesn't list", "fail"),
    ("  – kittystory-memories skipped: its migration was cancelled", "skip"),
    ("hpm: kittystory: nothing changed since 1.1; nothing to publish", "error"),
    ("warning: kittystory holds what may be your own memories or chats", "warning"),
    ("note: published the clean seed …", "note"),
    ("!! kittystory-theme: it adds rules, which change the whole machine", "loud"),
    ("the AI is drafting kittystory's manifest…", "ai"),
    ("the AI's part cost ~$0.4462", "ai"),
    ("the merge cost ~$0.0123", "ai"),
    ("kittystory 1.1  extras: packs, characters", "plain"),
    ("everything is up to date", "plain"),
])
def test_kind_of(line, kind):
    assert kind_of(line) == kind


# ---------------------------------------------------------------- the colors

@pytest.mark.parametrize("text, kind, painted", [
    ("  ✓ kittystory 1.1 updated", None, "  \x1b[1;32m✓\x1b[0m\x1b[32m kittystory 1.1 updated\x1b[0m"),
    ("published kittystory 1.1", None, "\x1b[1;32mpublished\x1b[0m \x1b[32mkittystory 1.1\x1b[0m"),
    ("✗ x failed", None, "\x1b[1;31m✗\x1b[0m\x1b[31m x failed\x1b[0m"),
    ("  – x skipped", None, "  \x1b[90m–\x1b[0m\x1b[90m x skipped\x1b[0m"),
    ("hpm: no world", "error", "\x1b[1;31mhpm:\x1b[0m\x1b[31m no world\x1b[0m"),
    ("warning: big seed", None, "\x1b[1;33mwarning:\x1b[0m\x1b[33m big seed\x1b[0m"),
    ("note: a note", None, "\x1b[1;36mnote:\x1b[0m a note"),
    ("!! rules", None, "\x1b[1;31m!!\x1b[0m\x1b[1m rules\x1b[0m"),
    ("the AI's part cost ~$0.4462", None,
     "\x1b[35mthe AI's part cost \x1b[0m\x1b[1;35m~$0.4462\x1b[0m"),
    ("version [1.2]: ", "ask", "\x1b[1mversion \x1b[0m\x1b[90m[1.2]\x1b[0m: "),
    ("1 updated", "ok", "\x1b[32m1 updated\x1b[0m"),            # a kind given, no marker
    ("kittystory 1.1", None, "kittystory 1.1"),                  # plain stays
])
def test_paint(text, kind, painted):
    assert paint(text, kind) == painted
    assert strip_codes(painted) == text


def test_only_the_first_line_of_a_block_is_painted():
    text = "warning: the seed changed\n  r  keep it\n  w  send it"
    painted = paint(text)
    assert painted.startswith("\x1b[1;33mwarning:")
    assert painted.endswith("\n  r  keep it\n  w  send it")
    assert strip_codes(painted) == text


def test_off_is_the_text_as_it_is():
    for line in ("  ✓ x", "hpm: y", "the AI's part cost ~$1.00"):
        assert paint(line, on=False) == line
    assert paint("") == ""
