"""The status bar: the bottom row of the terminal, hallux's own front panel.

It shows an activity light (gray when idle, a green-yellow spinner while the AI works),
what the AI is doing, the model, the effort, what the session has cost and how long the
last answer took. The AI is told the screen is one row shorter and never draws here.

In the scrolling shell the bar is pinned with a scroll region (rows 1..rows-1 scroll,
the last row stays); in block mode it's a row of the full-screen layout.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
FRAME_SECONDS = 0.08
FADE_SECONDS = 1.6
GREEN, YELLOW = (0x5F, 0xD7, 0x87), (0xD7, 0xD7, 0x5F)
GRAY, DIM, RED, BACKGROUND = "#808080", "#5c5c5c", "#ff5f5f", "#1c1c1c"
YELLOW_NOTE = "#d7af5f"
IDLE_HINT = "power off: ctrl+shift+del · ctrl+c ×3"

VERBS = {"list_dir": "listing", "stat": "checking", "read_file": "reading", "find": "searching",
         "write_file": "writing", "edit_file": "editing", "make_dir": "creating",
         "chdir": "entering", "remove": "removing", "move": "moving", "copy": "copying",
         "save_field": "saving"}


def describe(tool: str, args: dict) -> str:
    """What a tool call looks like on the bar: "reading /etc/os-release"."""
    if tool.startswith("memory_"):
        return "remembering…"
    target = str(args.get("path") or args.get("src") or "")
    return f"{VERBS.get(tool, tool.replace('_', ' '))} {target}".strip()


def short_model(model: str) -> str:
    """claude-opus-5-5 -> "opus 5.5"; claude-haiku-4-5-20251001 -> "haiku 4.5"."""
    name = re.sub(r"-\d{8}$", "", model.removeprefix("claude-"))
    family, _, version = name.partition("-")
    return f"{family} {version.replace('-', '.')}".strip()


@dataclass
class Status:
    model: str
    effort: str | None = None
    busy: bool = False
    activity: str = ""
    tools: int = 0                    # tool calls in the current turn
    error: str | None = None
    note: str | None = None           # shown instead of the idle hint (e.g. ticks paused)
    cost: float = 0.0                 # dollars since hallux started
    seconds: float | None = None      # how long the last answer took
    started: float = field(default=0.0)


class StatusBar:
    def __init__(self, model: str, effort: str | None) -> None:
        self.status = Status(model=model, effort=effort)

    def update(self, **changes: object) -> None:
        for name, value in changes.items():
            setattr(self.status, name, value)

    # ---------------------------------------------------------------- what it shows

    def segments(self, width: int, now: float | None = None) -> list[tuple[str, str]]:
        """The bar as (color, text) pieces exactly `width` characters wide."""
        s = self.status
        now = time.monotonic() if now is None else now
        if s.error:
            light, light_color, text, text_color = "✗", RED, f"model failed: {s.error}", RED
        elif s.busy:
            light = SPINNER[int(now / FRAME_SECONDS) % len(SPINNER)]
            light_color, text_color = fade(now), GRAY
            text = s.activity or "thinking…"
            if s.tools > 1:
                text += f" ({s.tools})"
        elif s.note:
            light, light_color, text, text_color = "•", GRAY, s.note, YELLOW_NOTE
        else:
            light, light_color, text, text_color = "•", GRAY, IDLE_HINT, DIM
        info = " · ".join(part for part in (
            short_model(s.model), s.effort or "",
            f"${s.cost:.2f}",
            f"{now - s.started:.1f}s" if s.busy else (f"{s.seconds:.1f}s" if s.seconds else ""),
        ) if part)
        room = max(0, width - len(info) - 5)             # " x " + text + "  " + info + " "
        text = fit(text, room)
        gap = max(1, width - 3 - len(text) - len(info) - 1)
        pieces = [(GRAY, " "), (light_color, light), (GRAY, " "), (text_color, text),
                  (GRAY, " " * gap), (DIM, info), (GRAY, " ")]
        return _clip(pieces, width)

    def fragments(self, width: int) -> list[tuple[str, str]]:
        """For prompt_toolkit (block mode)."""
        return [(f"fg:{color} bg:{BACKGROUND}", text) for color, text in self.segments(width)]

    def ansi(self, width: int) -> str:
        """For the scrolling shell: one line of escape-coded text, no newline."""
        bg = _rgb(BACKGROUND)
        out = [f"\x1b[0m\x1b[48;2;{bg}m\x1b[2K"]         # erase the row in the bar's color
        out += [f"\x1b[38;2;{_rgb(color)}m{text}" for color, text in self.segments(width)]
        return "".join(out) + "\x1b[0m"


def fade(now: float) -> str:
    """Green to yellow and back, on a sine curve."""
    t = (1 - math.cos(2 * math.pi * now / FADE_SECONDS)) / 2
    r, g, b = (round(a + (b - a) * t) for a, b in zip(GREEN, YELLOW))
    return f"#{r:02x}{g:02x}{b:02x}"


def fit(text: str, width: int) -> str:
    """Shorten to `width`, keeping the end of a path: "reading …/share/doc/copyright"."""
    if len(text) <= width:
        return text
    if width <= 1:
        return "…"[:width]
    verb, space, rest = text.partition(" ")
    if space and rest.startswith("/") and len(verb) + 3 < width:
        return f"{verb} …{rest[-(width - len(verb) - 2):]}"
    return text[: width - 1] + "…"


def _clip(pieces: list[tuple[str, str]], width: int) -> list[tuple[str, str]]:
    out, used = [], 0
    for color, text in pieces:
        text = text[: max(0, width - used)]
        if text:
            out.append((color, text))
            used += len(text)
    if used < width:
        out.append((GRAY, " " * (width - used)))
    return out


def _rgb(color: str) -> str:
    return ";".join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))


# ---------------------------------------------------------------- pinning it in the shell

def install(rows: int) -> str:
    """Make room for the bar and pin rows 1..rows-1 as the scrolling part (like apt does).

    The newline scrolls the screen if the cursor is on the last row; setting the region
    homes the cursor, so it's saved and restored, then moved back inside the region.
    """
    return f"\n\x1b7\x1b[1;{rows - 1}r\x1b8\x1b[1A"


def draw(bar: StatusBar, rows: int, cols: int) -> str:
    """Re-pin the region and redraw the bar, leaving the cursor where it was."""
    return f"\x1b7\x1b[1;{rows - 1}r\x1b[{rows};1H{bar.ansi(cols - 1)}\x1b8"


def uninstall(rows: int) -> str:
    """Give the whole screen back: no region, no bar."""
    return f"\x1b7\x1b[r\x1b[{rows};1H\x1b[0m\x1b[2K\x1b8"
