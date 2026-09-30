"""The wire between the terminal and the AI: envelopes in, replies out.

The AI answers every envelope with

    <screen>
    ...exactly what the terminal shows...
    </screen><prompt>user@hallux:~$ </prompt>

optionally followed by control tags (<halt/>, <reboot/>, <tty mode="raw"/>) and, for a
full-screen program in block mode, a <form> of editable fields (see Form). It writes
control characters as Unicode control pictures ("␛" for ESC), which decode() turns into
real bytes.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

# U+2400..U+241F picture the C0 control characters 0x00..0x1F; U+2421 pictures DEL.
CONTROL_PICTURES = {0x2400 + c: c for c in range(32)} | {0x2421: 0x7F}
TTY_TAG = re.compile(r'<tty\s+mode="(raw|cooked)"\s*/>')
FORM_START = re.compile(r"</prompt>(?:\s*<(?:halt|reboot)/>|\s*<tty[^>]*/>)*\s*<form\b")
FIELD_TAG = re.compile(r"<(editor|line|pager)\b([^>]*?)(/>|>(.*?)</\1>)", re.DOTALL)
ATTRIBUTE = re.compile(r'([\w-]+)="([^"]*)"')
KEYMAPS = ("emacs", "nano", "vi")


@dataclass(frozen=True)
class Field:
    """An editable box on a block-mode screen, like a field on an IBM 3270 terminal."""
    kind: str                     # "editor" (multi-line), "line" (Enter acts) or "pager"
    id: str
    top: int = 1                  # 1-based screen position
    left: int = 1
    width: int = 0                # 0: to the right edge
    height: int = 1               # 0: to the bottom edge
    text: str | None = None       # None: keep what the field holds (or load `file`)
    file: str | None = None       # fill the field from this file on the machine's disk
    cursor: tuple[int, int] | None = None     # (line, column), 1-based
    style: str = ""               # prompt_toolkit style, e.g. "fg:#ffb6c1 bg:#1e1e1e"
    lang: str | None = None       # syntax highlighting, e.g. "python"


@dataclass(frozen=True)
class Form:
    fields: tuple[Field, ...]
    keys: tuple[str, ...] = ()    # action keys that go to the AI, e.g. ("C-o", "C-x")
    focus: str | None = None      # the id of the field that gets the cursor
    keymap: str = "emacs"         # local editing keys: "emacs", "nano" or "vi"


@dataclass(frozen=True)
class FieldState:
    """A field as the user left it when they pressed an action key."""
    id: str
    text: str
    cursor: tuple[int, int]       # (line, column), 1-based
    modified: bool                # changed since loaded, set by the AI, or saved
    changed: bool                 # changed since the AI last saw it


@dataclass(frozen=True)
class Action:
    """An action key (or a click outside the fields) in block mode."""
    key: str                      # as the form named it ("C-o"), "Enter", or "click"
    focus: str | None
    fields: tuple[FieldState, ...] = ()
    row: int | None = None        # where a click landed, 1-based
    col: int | None = None


@dataclass(frozen=True)
class Reply:
    screen: str                   # printed byte for byte (in block mode: the background)
    prompt: str | None            # None when the reply had no <prompt>
    halt: bool = False
    reboot: bool = False
    tty: str | None = None        # "raw" or "cooked" when the AI switches modes
    form: Form | None = field(default=None)


def envelope(tag: str, body: str = "", **attrs: object) -> str:
    """One message to the AI, e.g. <input cwd="/home/user" ...>ls -la</input>."""
    attributes = "".join(f' {name}="{html.escape(str(value))}"' for name, value in attrs.items())
    return f"<{tag}{attributes}>{body}</{tag}>"


def decode(text: str) -> str:
    """Turn control pictures ("␛[31m") into the real control characters ("\\x1b[31m")."""
    return text.translate(CONTROL_PICTURES)


def parse(text: str) -> Reply:
    """Split the AI's reply into what to print, the next prompt and the control tags.

    Anything before <screen> (stray narration) is dropped. If the tags are missing, the
    text is shown anyway: a garbled screen beats a silent one.
    """
    form = None
    if start := FORM_START.search(text):              # cut the form off first: its fields
        form_at = text.index("<form", start.start())  # may hold any text
        form = parse_form(text[form_at:])
        text = text[:form_at]
    body, closed, tail = text.rpartition("</screen>")
    if not closed:                                # no </screen>: the prompt ends the screen
        body, has_prompt, rest = text.partition("<prompt>")
        tail = "<prompt>" + rest if has_prompt else ""
    screen = body.partition("<screen>")[2] if "<screen>" in body else body
    prompt = tail.partition("<prompt>")[2].partition("</prompt>")[0] if "<prompt>" in tail else None
    tty = TTY_TAG.search(tail)
    return Reply(
        screen=decode(screen.removeprefix("\n")),
        prompt=None if prompt is None else decode(prompt),
        halt="<halt/>" in tail,
        reboot="<reboot/>" in tail,
        tty=tty[1] if tty else None,
        form=form,
    )


def parse_form(text: str) -> Form | None:
    """Read <form keys=".." focus=".." keymap=".."> with <editor>, <line> and <pager> fields."""
    head, _, body = text.partition(">")
    attrs = _attributes(head)
    fields = []
    for match in FIELD_TAG.finditer(body.rpartition("</form>")[0] or body):
        kind, raw_attrs, closing, content = match.groups()
        a = _attributes(raw_attrs)
        if not a.get("id"):
            continue
        fields.append(Field(
            kind=kind,
            id=a["id"],
            top=_int(a.get("top"), 1),
            left=_int(a.get("left"), 1),
            width=_int(a.get("width"), 0),
            height=_int(a.get("height"), 1 if kind == "line" else 0),
            text=None if closing == "/>" else content.removeprefix("\n"),   # <x/> keeps
            file=a.get("file"),
            cursor=_cursor(a.get("cursor")),
            style=a.get("style", ""),
            lang=a.get("lang"),
        ))
    if not fields:
        return None
    keymap = attrs.get("keymap", "emacs")
    return Form(fields=tuple(fields), keys=tuple(attrs.get("keys", "").split()),
                focus=attrs.get("focus"), keymap=keymap if keymap in KEYMAPS else "emacs")


def _attributes(text: str) -> dict[str, str]:
    return {name: html.unescape(value) for name, value in ATTRIBUTE.findall(text)}


def _int(value: str | None, default: int) -> int:
    try:
        return max(0, int(value)) if value is not None else default
    except ValueError:
        return default


def _cursor(value: str | None) -> tuple[int, int] | None:
    line, _, col = (value or "").partition(":")
    try:
        return max(1, int(line)), max(1, int(col or 1))
    except ValueError:
        return None
