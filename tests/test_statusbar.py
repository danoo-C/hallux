import re

import pytest

from hallux import statusbar
from hallux.protocol import decode
from hallux.statusbar import Running, StatusBar, describe, fade, fit, short_model, size


def text(bar, width, now=1.0):
    line = "".join(piece for _, piece in bar.segments(width, now))
    assert len(line) == width                          # always exactly fills the row
    return line


def test_idle_shows_hallux_own_keys_and_the_hardware():
    line = text(StatusBar("claude-opus-5-5", "low"), 100)
    assert line.startswith(" • power off: ctrl+shift+del · config: ctrl+f12 · ctrl+c ×3  ")
    assert line.endswith("opus 5.5 · low · ~$0.00 ")


def test_a_narrow_bar_loses_whole_parts_of_the_hint_from_its_end():
    """The way out is the last to go, and no part is cut in the middle while another could
    go instead. The hardware on the right is there at every width."""
    bar = StatusBar("claude-haiku-4-5-20251001", "medium")
    bar.update(cost=123.45, seconds=12.3)
    hardware = "haiku 4.5 · medium · ~$123.45 · 12.3s "
    whole = " • power off: ctrl+shift+del · config: ctrl+f12 · ctrl+c ×3"
    shown = {width: text(bar, width) for width in (111, 96, 81, 67, 61)}
    assert all(line.endswith(hardware) for line in shown.values())
    assert shown[111].startswith(whole + "  ")                         # all three
    assert shown[96].startswith(" • power off: ctrl+shift+del · config: ctrl+f12  ")
    assert "ctrl+c" not in shown[96]                                   # the triple Ctrl-C went
    assert shown[81].startswith(" • power off: ctrl+shift+del  ")      # then the panel's key
    assert "config" not in shown[81] and "…" not in shown[81]
    assert shown[67].startswith(" • power off: ctrl+shift+del ") and "…" not in shown[67]
    assert shown[61].startswith(" • power off: ctrl+s") and "… haiku" in shown[61]   # only then
    assert statusbar.idle_hint(0) == "power off: ctrl+shift+del"


def test_busy_spins_and_says_what_the_ai_does():
    bar = StatusBar("claude-sonnet-5-5", "medium")
    bar.update(busy=True, activity=describe("read_file", {"path": "/etc/os-release"}),
               tools=2, started=0.0, cost=0.2117)
    line = text(bar, 100, now=4.4)
    assert re.match(r" [⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏] reading /etc/os-release \(2\) +sonnet 5.5 · medium · ~\$0.21 · 4.4s $", line)
    assert text(bar, 100, now=0.0)[1] != text(bar, 100, now=0.08)[1]    # it animates


def test_errors_are_red_and_explicit():
    bar = StatusBar("claude-haiku-4-5", None)
    bar.update(error="overloaded (HTTP 529)", seconds=2.5)
    assert text(bar, 80).startswith(" ✗ model failed: overloaded (HTTP 529)")
    assert text(bar, 80).endswith("haiku 4.5 · ~$0.00 · 2.5s ")
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
    assert describe("addon_listen", {"name": "window"}) == "listening to window"
    assert describe("addon_listen", {"name": "window", "on": True}) == "listening to window"
    assert describe("addon_listen", {"name": "window", "on": False}) == "no longer listening to window"
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
    bar = StatusBar("claude-opus-5-5", "low")
    drawn = statusbar.draw(bar, 30, 120)
    assert drawn.startswith("\x1b7\x1b[1;29r\x1b[30;1H") and drawn.endswith("\x1b[0m\x1b8")
    assert statusbar.uninstall(30) == "\x1b7\x1b[r\x1b[30;1H\x1b[0m\x1b[2K\x1b8"
    # back from the alternate screen the cursor may be on the bottom row: a line down, which
    # scrolls the screen there, then the region and the bar, then up again into the region
    assert statusbar.reinstall(bar, 30, 120) == f"\x1bD{drawn}\x1b[1A"


def test_a_note_replaces_the_idle_hint():
    bar = StatusBar("claude-opus-5-5", "low")
    bar.update(note="live updates paused: tick budget used")
    assert text(bar, 100).startswith(" • live updates paused: tick budget used")
    bar.update(busy=True, started=0.0)
    assert "thinking…" in text(bar, 100, now=1.0)            # work still shows while busy


def test_the_idle_bar_says_when_the_machine_listens():
    bar = StatusBar("claude-opus-5-5", "low")
    bar.update(listening="window, bell")
    assert text(bar, 100).startswith(" • listening: window, bell ")
    assert "power off" not in text(bar, 100)
    bar.update(note="addon music skipped: No module named 'numpy'")
    assert text(bar, 100).startswith(" • addon music skipped")       # a note still comes first
    bar.update(note=None, busy=True, started=0.0)
    assert "thinking…" in text(bar, 100, now=1.0)
    bar.update(busy=False, listening="")
    assert text(bar, 100).startswith(" • power off: ctrl+shift+del · config: ctrl+f12")


# --- the jobs of the addons' agents on the bar -------------------------------------------------

MUSIC = Running("music", "balancing the mix", began=100.0, tokens=21340)
GUI = Running("gui", "drawing", began=120.0, tokens=900)


def with_jobs(*jobs, **more):
    bar = StatusBar("claude-opus-5-5", "low")
    bar.update(jobs=jobs, **more)
    return bar


def test_an_idle_bar_shows_the_job_that_runs():
    bar = with_jobs(MUSIC, cost=1.21, jobs_cost=0.21, seconds=2.1)
    line = text(bar, 100, now=148.9)
    assert line.startswith(" • music: balancing the mix · 0:48 · 21k tok  ")
    assert line.endswith("  opus 5.5 · low · ~$1.42 · 2.1s ")
    assert text(bar, 100, now=149.0) != line                    # its time moves


@pytest.mark.parametrize("job, now, shown", [
    (Running("gui", "drawing", 120.0, 900), 125.2, "gui: drawing · 0:05 · 900 tok"),
    (Running("gui", "drawing", 120.0, 0), 120.0, "gui: drawing · 0:00 · 0 tok"),
    (Running("gui", "drawing", 120.0, 999_999), 3845.0, "gui: drawing · 62:05 · 999k tok"),
    (Running("gui", "drawing", 120.0, 1_250_000), 180.0, "gui: drawing · 1:00 · 1.2M tok"),
    (Running("gui", "drawing", 120.0, 5), 119.0, "gui: drawing · 0:00 · 5 tok"),   # never -0:01
])
def test_a_jobs_time_and_tokens_as_the_bar_writes_them(job, now, shown):
    assert text(with_jobs(job), 100, now=now).startswith(f" • {shown}  ")


def test_more_jobs_are_counted_and_named():
    assert text(with_jobs(MUSIC, GUI), 100, now=148).startswith(" • 2 jobs: music, gui  ")


def test_while_the_ai_works_the_bar_says_its_activity_and_how_many_jobs_run():
    bar = with_jobs(MUSIC)
    bar.update(busy=True, activity=describe("read_file", {"path": "/etc/os-release"}),
               started=147.2)
    assert re.match(r" [⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏] reading /etc/os-release · 1 job +opus 5.5 · low · "
                    r"~\$0.00 · 0.8s $", text(bar, 100, now=148.0))
    bar.update(jobs=(MUSIC, GUI), activity="thinking…", tools=3)
    assert " thinking… (3) · 2 jobs  " in text(bar, 100, now=148.0)
    bar.update(activity=describe("read_file", {"path": "/usr/share/doc/bash/copyright"}), tools=1)
    narrow = text(bar, 62, now=148.0)                           # the path is cut, not the jobs
    assert "reading …" in narrow and "copyright · 2 jobs " in narrow
    bar.update(jobs=())
    assert "job" not in text(bar, 100, now=148.0)


def test_an_error_and_a_note_come_before_a_job_and_a_job_before_listening():
    bar = with_jobs(MUSIC, listening="music")
    assert text(bar, 100, now=148).startswith(" • music: balancing the mix · 0:48 · 21k tok  ")
    bar.update(note="events paused: budget used")
    assert text(bar, 100, now=148).startswith(" • events paused: budget used  ")
    bar.update(error="overloaded")
    assert text(bar, 100, now=148).startswith(" ✗ model failed: overloaded  ")
    bar.update(error=None, note=None, jobs=())
    assert text(bar, 100, now=148).startswith(" • listening: music  ")      # as before


def test_the_cost_is_the_sessions_and_the_jobs_and_has_the_tilde():
    bar = StatusBar("claude-opus-5-5", "low")
    assert text(bar, 100).endswith(" opus 5.5 · low · ~$0.00 ")
    bar.update(cost=1.21)
    assert text(bar, 100).endswith(" opus 5.5 · low · ~$1.21 ")
    bar.update(jobs_cost=0.21)                                  # a job has ended
    assert text(bar, 100).endswith(" opus 5.5 · low · ~$1.42 ")
    assert "\x1b[38;2;92;92;92mopus 5.5 · low · ~$1.42" in bar.ansi(100)


def test_a_jobs_line_that_is_too_long_loses_its_status_first():
    """The time and the tokens are what moves. The bar's own shortening cuts from the end,
    which would take them first."""
    job = Running("music", "balancing the mix of the second chorus against the bass", 100.0, 21340)
    wide, narrow = text(with_jobs(job), 110, now=148), text(with_jobs(job), 70, now=148)
    assert " against the bass · 0:48 · 21k tok  " in wide and "…" not in wide
    assert narrow.startswith(" • music: balancing the mix… · 0:48 · 21k tok ")
    assert narrow.endswith(" opus 5.5 · low · ~$0.00 ")         # the hardware stays
    for width in range(30, 70):                                 # at any width that has room
        assert text(with_jobs(job), width, now=148).rstrip().endswith("~$0.00")     # for it
    tight = text(with_jobs(job), 53, now=148)                   # the status goes altogether,
    assert tight.startswith(" • music: … · 0:48 · 21k tok ")    # and the rest is still there


def test_the_two_process_tools_have_their_words():
    assert describe("list_processes", {}) == "listing the processes"
    assert describe("kill_process", {"pid": 30001}) == "killing 30001"


@pytest.mark.parametrize("count, shown", [
    (0, "0 B"), (812, "812 B"), (999, "999 B"),
    (1000, "1.0 kB"), (1200, "1.2 kB"), (9949, "9.9 kB"), (9950, "10 kB"),
    (88_000, "88 kB"), (340_000, "340 kB"), (999_499, "999 kB"),
    (999_500, "1.0 MB"),                          # never "1000 kB"
    (2_300_000, "2.3 MB"), (34_000_000, "34 MB"),
    (1_100_000_000, "1.1 GB"), (2_100_000_000_000, "2.1 TB"), (5_000_000_000_000_000, "5000 TB"),
])
def test_a_size_is_written_in_thousands_as_a_file_manager_does(count, shown):
    assert size(count) == shown
