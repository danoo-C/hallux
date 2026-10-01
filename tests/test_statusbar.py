import re

from hallux import statusbar
from hallux.protocol import decode
from hallux.statusbar import StatusBar, describe, fade, fit, short_model


def text(bar, width, now=1.0):
    line = "".join(piece for _, piece in bar.segments(width, now))
    assert len(line) == width                          # always exactly fills the row
    return line


def test_idle_shows_the_way_out_and_the_hardware():
    line = text(StatusBar("claude-opus-5-5", "low"), 100)
    assert line.startswith(" • power off: ctrl+shift+del · ctrl+c ×3")
    assert line.endswith("opus 5.5 · low · $0.00 ")


def test_busy_spins_and_says_what_the_ai_does():
    bar = StatusBar("claude-sonnet-5-5", "medium")
    bar.update(busy=True, activity=describe("read_file", {"path": "/etc/os-release"}),
               tools=2, started=0.0, cost=0.2117)
    line = text(bar, 100, now=4.4)
    assert re.match(r" [⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏] reading /etc/os-release \(2\) +sonnet 5.5 · medium · \$0.21 · 4.4s $", line)
    assert text(bar, 100, now=0.0)[1] != text(bar, 100, now=0.08)[1]    # it animates


def test_errors_are_red_and_explicit():
    bar = StatusBar("claude-haiku-4-5", None)
    bar.update(error="overloaded (HTTP 529)", seconds=2.5)
    assert text(bar, 80).startswith(" ✗ model failed: overloaded (HTTP 529)")
    assert text(bar, 80).endswith("haiku 4.5 · $0.00 · 2.5s ")
    assert (statusbar.RED, "✗") in bar.segments(80)


def test_long_activities_keep_the_end_of_the_path():
    assert fit("reading /usr/share/doc/bash/copyright", 24) == "reading …/bash/copyright"
    assert fit("thinking…", 20) == "thinking…"
    assert fit("remembering everything forever", 12) == "remembering…"
    text(StatusBar("claude-opus-5-5", "low"), 30)      # narrow terminals still fit


def test_describe_and_model_names():
    assert describe("list_dir", {"path": "/home/user"}) == "listing /home/user"
    assert describe("copy", {"src": "a", "dst": "b"}) == "copying a"
    assert describe("memory_edit", {}) == "remembering…"
    assert describe("save_field", {"field": "text", "path": "hello.txt"}) == "saving hello.txt"
    assert describe("mcp__music__play", {"path": "song.score"}) == "music: play"
    assert describe("mcp__sound_card__set_volume", {}) == "sound_card: set_volume"
    assert describe("addon_help", {"name": "music"}) == "reading the manual of music"
    assert describe("list_addons", {}) == "listing the addons"
    assert short_model("claude-opus-5-5") == "opus 5.5"
    assert short_model("claude-haiku-4-5-20251001") == "haiku 4.5"
    assert short_model("sonnet") == "sonnet"


def test_the_fade_goes_green_yellow_green():
    assert fade(0) == "#5fd787" and fade(0.8) == "#d7d75f" and fade(1.6) == "#5fd787"


def test_the_ai_cannot_move_the_bar():
    """Scroll regions, resets, origin mode and the alternate screen never reach the terminal."""
    assert decode("a␛[1;5rb␛[rc␛cd␛[?1049he␛[?6lf") == "abcdef"
    assert decode("␛[31mred␛[0m ␛[H␛[2J") == "\x1b[31mred\x1b[0m \x1b[H\x1b[2J"


def test_pinning_the_bar():
    assert statusbar.install(30) == "\n\x1b7\x1b[1;29r\x1b8\x1b[1A"
    drawn = statusbar.draw(StatusBar("claude-opus-5-5", "low"), 30, 120)
    assert drawn.startswith("\x1b7\x1b[1;29r\x1b[30;1H") and drawn.endswith("\x1b[0m\x1b8")
    assert statusbar.uninstall(30) == "\x1b7\x1b[r\x1b[30;1H\x1b[0m\x1b[2K\x1b8"


def test_a_note_replaces_the_idle_hint():
    bar = StatusBar("claude-opus-5-5", "low")
    bar.update(note="live updates paused: tick budget used")
    assert text(bar, 100).startswith(" • live updates paused: tick budget used")
    bar.update(busy=True, started=0.0)
    assert "thinking…" in text(bar, 100, now=1.0)            # work still shows while busy
