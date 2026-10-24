"""hpm's colors on a terminal (docs/plans/hpm/colors/).

A line's kind decides its colors: the marker it starts with (✓, ✗, –, !!, warning:, note:,
hpm:) in its bold color, the rest in the kind's color. Only the colors change, never the
text: stripped of its codes, a painted line is the line. Sixteen ANSI colors, so the
terminal's own theme decides how they look.
"""
from __future__ import annotations

import os
import re

KINDS = ("ok", "fail", "skip", "error", "warning", "note", "loud", "ai", "ask", "plain")

RESET = "\x1b[0m"
BOLD, RED, GREEN, YELLOW, MAGENTA, CYAN, GRAY = "1", "31", "32", "33", "35", "36", "90"

# kind: (the marker's codes, the rest's codes); None is the terminal's own color
STYLES = {
    "ok": ((BOLD, GREEN), (GREEN,)),
    "fail": ((BOLD, RED), (RED,)),
    "skip": ((GRAY,), (GRAY,)),
    "error": ((BOLD, RED), (RED,)),
    "warning": ((BOLD, YELLOW), (YELLOW,)),
    "note": ((BOLD, CYAN), None),
    "loud": ((BOLD, RED), (BOLD,)),
    "ai": (None, (MAGENTA,)),
    "ask": (None, (BOLD,)),
    "dim": (None, (GRAY,)),
    "plain": (None, None),
}
MARKERS = (("✓", "ok"), ("published ", "ok"), ("✗", "fail"), ("–", "skip"), ("!!", "loud"),
           ("warning:", "warning"), ("note:", "note"), ("hpm:", "error"),
           ("the AI ", "ai"), ("the AI's ", "ai"))
COST = re.compile(r"~\$[0-9]+(?:\.[0-9]+)?")
ENDS_IN_COST = re.compile(r"cost ~\$[0-9.]+\s*$")
DEFAULT = re.compile(r"\[[^\]\n]*\](?=:?\s*$)")    # "[Y/n]" or "[1.2]" at the question's end
CODES = re.compile(r"\x1b\[[0-9;]*m")


def enabled(stream, env=None) -> bool:
    """Colors for this stream: HPM_COLOR=always|never first; else off with NO_COLOR (set,
    not empty) or TERM=dumb; else on if the stream is a terminal."""
    env = os.environ if env is None else env
    forced = env.get("HPM_COLOR", "").strip().lower()
    if forced in ("always", "never"):
        return forced == "always"
    if env.get("NO_COLOR") or env.get("TERM") == "dumb":
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):     # no isatty, or a closed stream
        return False


def kind_of(line: str) -> str:
    """The kind a line's first characters say; leading spaces don't count."""
    first = line.split("\n", 1)[0]
    bare = first.lstrip()
    for marker, kind in MARKERS:
        if bare.startswith(marker):
            return kind
    if ENDS_IN_COST.search(first):
        return "ai"
    return "plain"


def _sgr(codes) -> str:
    return f"\x1b[{';'.join(codes)}m" if codes else ""


def _piece(text: str, codes) -> str:
    return f"{_sgr(codes)}{text}{RESET}" if codes and text else text


def paint(text: str, kind: str | None = None, on: bool = True) -> str:
    """The text with its colors: the marker in its bold color, the rest in the kind's color.
    `kind` None: kind_of the first line. Only the first line of a block is painted; the
    lines under it (a manifest under its --- header) stay as they are."""
    if not on or not text:
        return text
    kind = kind or kind_of(text)
    if kind not in STYLES or kind == "plain":
        return text
    first, newline, rest = text.partition("\n")
    return _line(first, kind) + newline + rest


def _line(line: str, kind: str) -> str:
    marker_codes, rest_codes = STYLES[kind]
    bare = line.lstrip()
    lead = line[:len(line) - len(bare)]
    marker = next((m for m, k in MARKERS if k == kind and bare.startswith(m)), "")
    if kind == "ai" and marker:                   # "the AI " is words, not a marker
        marker = ""
    body = bare[len(marker):]
    if kind == "ai":
        return lead + _costs(body, rest_codes)
    if kind == "ask":
        return lead + _question(body, rest_codes)
    head = _piece(marker.rstrip(" "), marker_codes) + (" " if marker.endswith(" ") else "")
    return lead + head + _piece(body, rest_codes)


def _costs(text: str, codes) -> str:
    """The AI's line in its color, each cost in it bold."""
    out, at = [], 0
    for found in COST.finditer(text):
        out.append(_piece(text[at:found.start()], codes))
        out.append(_piece(found.group(0), (BOLD,) + tuple(codes)))
        at = found.end()
    out.append(_piece(text[at:], codes))
    return "".join(out)


def _question(text: str, codes) -> str:
    """A question bold, its default in brackets dim."""
    found = DEFAULT.search(text)
    if not found:
        return _piece(text, codes)
    return (_piece(text[:found.start()], codes) + _piece(found.group(0), (GRAY,))
            + text[found.end():])


def strip_codes(text: str) -> str:
    return CODES.sub("", text)
