"""The wire between the terminal and the AI: envelopes in, replies out.

The AI answers every envelope with

    <screen>
    ...exactly what the terminal shows...
    </screen><prompt>user@hallux:~$ </prompt>

optionally followed by control tags (<halt/>, <reboot/>, <tty mode="raw"/>), the line to
put back at the prompt (<edit>cat /etc/</edit>, for Tab completion and friends), a new
working directory (<cwd>/home/user</cwd>) and, for a
full-screen program in block mode, a <form> of editable fields (see Form). It writes
control characters as Unicode control pictures ("␛" for ESC), which decode() turns into
real bytes.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field, replace

# U+2400..U+241F picture the C0 control characters 0x00..0x1F; U+2421 pictures DEL.
CONTROL_PICTURES = {0x2400 + c: c for c in range(32)} | {0x2421: 0x7F}
# A color code the AI wrote without its ␛ ("[38;5;218m"), which it does in long, colorful
# output. Spelled-out codes ("\e[31m" in a .bashrc being shown) are text and stay text.
BARE_COLOR = re.compile(r"(?<!\x1b)(?<!\\e)(?<!\\033)(?<!\\x1b)(?<!\\u001b)\[(?=\d[0-9;]{0,19}m)")
# The end of a text that might still become one of those, or a spelled-out code.
COLOR_START = re.compile(r"(?:\\(?:e|033|x1b|u001b))?\[[0-9;]{0,19}$"
                         r"|\\(?:e|0|03|033|x|x1|x1b|u|u0|u00|u001|u001b)?$")
TTY_TAG = re.compile(r'<tty\s+mode="(raw|cooked)"\s*/>')
FORM_START = re.compile(r"</prompt>(?:\s*<(?:halt|reboot)/>|\s*<tty[^>]*/>)*\s*<form\b")
FIELD_TAG = re.compile(r"<(editor|line|pager)\b([^>]*?)(/>|>(.*?)</\1>)", re.DOTALL)
FOOTER_TAG = re.compile(r"<footer>(.*?)</footer>", re.DOTALL)
FILE_TAG = re.compile(r"<file\b([^>]*)>(.*?)</file>", re.DOTALL)
MEMORY_TAG = re.compile(r"<memory>(.*?)</memory>", re.DOTALL)
FORM_BEFORE_SCREEN = re.compile(r"</form>\s*(?=<screen>)")
ESCAPES = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[78c=>]")
ATTRIBUTE = re.compile(r'([\w-]+)="([^"]*)"')
KEYMAPS = ("emacs", "nano", "vi")


@dataclass(frozen=True)
class Field:
    """An editable box on a block-mode screen, like a field on an IBM 3270 terminal.

    None means "not given": a field the AI shows again keeps what it had (see resolve()),
    a new field gets the defaults (see with_defaults()).
    """
    kind: str                     # "editor" (multi-line), "line" (Enter acts) or "pager"
    id: str
    top: int | None = None        # 1-based row (default 1); negative counts from the bottom
    left: int | None = None       # (default 1)
    width: int | None = None      # 0: to the right edge (default)
    height: int | None = None     # 0: down to the footer or the bottom (default; 1 for a line)
    text: str | None = None       # None: keep what the field holds (or load `file`)
    file: str | None = None       # fill the field from this file on the machine's disk
    cursor: tuple[int, int] | None = None     # (line, column), 1-based: move the cursor
    style: str | None = None      # prompt_toolkit style, e.g. "fg:#ffb6c1 bg:#1e1e1e"
    lang: str | None = None       # syntax highlighting, e.g. "python"

    def with_defaults(self) -> Field:
        return replace(self, top=self.top or 1, left=max(1, self.left or 1),
                       width=self.width or 0,
                       height=self.height if self.height is not None else (1 if self.kind == "line" else 0),
                       style=self.style or "")


@dataclass(frozen=True)
class Form:
    fields: tuple[Field, ...]
    keys: tuple[str, ...] = ()    # action keys that go to the AI, e.g. ("C-o", "C-x")
    focus: str | None = None      # the id of the field that gets the cursor
    keymap: str = "emacs"         # local editing keys: "emacs", "nano" or "vi"
    footer: str | None = None     # lines pinned to the bottom of the screen (status, help)


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
class FileWrite:
    path: str
    content: str                  # literal text, written as is
    append: bool = False


@dataclass(frozen=True)
class Reply:
    screen: str                   # printed byte for byte (in block mode: the background)
    prompt: str | None            # None when the reply had no <prompt>
    halt: bool = False
    reboot: bool = False
    tty: str | None = None        # "raw" or "cooked" when the AI switches modes
    form: Form | None = field(default=None)
    edit: str | None = None       # the line to put back at the prompt (Tab completion...)
    cwd: str | None = None        # the new working directory (boot, cd ~) without a tool call
    files: tuple[FileWrite, ...] = ()   # files to write without a tool call
    memory: str | None = None     # a whole new memory (first boot only)


def envelope(tag: str, body: str = "", **attrs: object) -> str:
    """One message to the AI, e.g. <input cwd="/home/user" ...>ls -la</input>."""
    attributes = "".join(f' {name}="{html.escape(str(value))}"' for name, value in attrs.items())
    return f"<{tag}{attributes}>{body}</{tag}>"


def decode(text: str) -> str:
    """Turn control pictures ("␛[31m") into the real control characters ("\\x1b[31m"),
    and bare color codes ("[31m", the ␛ forgotten) into real ones."""
    return BARE_COLOR.sub("\x1b[", text.translate(CONTROL_PICTURES))


def parse(text: str) -> Reply:
    """Split the AI's reply into what to print, the next prompt and the control tags.

    Anything before <screen> (stray narration) is dropped. If the tags are missing, the
    text is shown anyway: a garbled screen beats a silent one.
    """
    form = None
    if end := FORM_BEFORE_SCREEN.search(text):        # a full-screen program: form first
        form_at = text.find("<form")
        if 0 <= form_at < end.start():
            form = parse_form(text[form_at:end.start() + len("</form>")])
            text = text[:form_at] + text[end.end():]
    elif start := FORM_START.search(text):            # the older order: form after the prompt
        form_at = text.index("<form", start.start())  # (cut off first: fields hold any text)
        form = parse_form(text[form_at:])
        text = text[:form_at]
    body, closed, tail = text.rpartition("</screen>")
    if not closed:                                # no </screen>: the prompt ends the screen
        body, has_prompt, rest = text.partition("<prompt>")
        tail = "<prompt>" + rest if has_prompt else ""
    screen = body.partition("<screen>")[2] if "<screen>" in body else body
    prompt = tail.partition("<prompt>")[2].partition("</prompt>")[0] if "<prompt>" in tail else None
    tty = TTY_TAG.search(tail)
    files = tuple(FileWrite(path=a["path"], content=content.removeprefix("\n"),
                            append=a.get("append") == "yes")
                  for raw, content in FILE_TAG.findall(tail)
                  if (a := _attributes(raw)).get("path"))
    tail_without_files = FILE_TAG.sub("", tail)
    memory = MEMORY_TAG.search(tail_without_files)
    return Reply(
        screen=decode(screen.removeprefix("\n")),
        prompt=None if prompt is None else decode(prompt),
        halt="<halt/>" in tail,
        reboot="<reboot/>" in tail,
        tty=tty[1] if tty else None,
        form=form,
        edit=decode(tail.partition("<edit>")[2].partition("</edit>")[0]) if "<edit>" in tail else None,
        cwd=tail.partition("<cwd>")[2].partition("</cwd>")[0].strip() or None if "<cwd>" in tail else None,
        files=files,
        memory=memory[1].removeprefix("\n") if memory else None,
    )


def plain(text: str) -> str:
    """Screen text without colors or other escape codes."""
    return ESCAPES.sub("", text).replace("\r", "")


class ScreenStream:
    """Picks the screen out of a reply while the AI is still writing it, to show it right away.

    feed() takes the raw text as it arrives and returns what can be printed now: the decoded
    text between <screen> and </screen>, minus a tail that might still turn into "</screen>"
    or an escape sequence (whole sequences, so the terminal's filters see them). A reply that
    starts with <form> is a full-screen program: nothing is streamed, it's shown whole.
    """

    def __init__(self) -> None:
        self.raw = ""                  # text of the current block not handed out yet
        self.state = "before"          # before <screen>, inside, done, or off (a form)
        self.first = True              # the newline right after <screen> isn't output
        self.shown = ""                # everything handed out so far (decoded)

    def new_block(self) -> None:
        if self.state == "before":
            self.raw = ""

    def feed(self, text: str) -> str:
        if self.state in ("done", "off"):
            return ""
        self.raw += text
        if self.state == "before":
            head = self.raw.lstrip()
            if head.startswith("<form"):
                self.state = "off"
                return ""
            at = self.raw.find("<screen>")
            if at < 0:
                return ""
            self.state, self.raw = "inside", self.raw[at + len("<screen>"):]
        if self.first and self.raw:
            self.raw, self.first = self.raw.removeprefix("\n"), False
        end = self.raw.find("</screen>")
        if end >= 0:
            out, self.raw, self.state = self.raw[:end], "", "done"
        else:
            keep = _holdback(self.raw)
            out, self.raw = self.raw[:len(self.raw) - keep], self.raw[len(self.raw) - keep:]
        out = decode(out)
        self.shown += out
        return out

    def rest(self, screen: str) -> str | None:
        """What's left to print of the final screen; None if it doesn't match what was shown."""
        return screen[len(self.shown):] if screen.startswith(self.shown) else None


def _holdback(raw: str) -> int:
    """How many characters at the end must wait for more: part of "</screen>" or an escape."""
    keep = next((k for k in range(min(8, len(raw)), 0, -1) if raw.endswith("</screen>"[:k])), 0)
    if color := COLOR_START.search(raw):              # decoded whole, with what precedes it
        keep = max(keep, len(raw) - color.start())
    esc = max(raw.rfind("␛"), raw.rfind("\x1b"))
    if esc >= 0 and len(raw) - esc < 64:
        sequence = decode(raw[esc:])
        complete = (re.match(r"\x1b\[[0-9;?]*[ -/]*[@-~]", sequence)
                    or re.match(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", sequence)
                    or (len(sequence) >= 2 and sequence[1] not in "[]"))
        if not complete:
            keep = max(keep, len(raw) - esc)
    return keep


def parse_form(text: str) -> Form | None:
    """Read <form keys=".." focus=".." keymap=".."> with <editor>, <line> and <pager> fields."""
    head, _, body = text.partition(">")
    attrs = _attributes(head)
    body = body.rpartition("</form>")[0] or body
    footer = FOOTER_TAG.search(body)
    if footer:
        body = body[:footer.start()] + body[footer.end():]
    fields = []
    for match in FIELD_TAG.finditer(body):
        kind, raw_attrs, closing, content = match.groups()
        a = _attributes(raw_attrs)
        if not a.get("id"):
            continue
        fields.append(Field(
            kind=kind,
            id=a["id"],
            top=_row(a.get("top")),
            left=_int(a.get("left")),
            width=_int(a.get("width")),
            height=_int(a.get("height")),
            text=None if closing == "/>" else content.removeprefix("\n"),   # <x/> keeps
            file=a.get("file"),
            cursor=_cursor(a.get("cursor")),
            style=a.get("style"),
            lang=a.get("lang"),
        ))
    if not fields:
        return None
    keymap = attrs.get("keymap", "emacs")
    return Form(fields=tuple(fields), keys=tuple(attrs.get("keys", "").split()),
                focus=attrs.get("focus"), keymap=keymap if keymap in KEYMAPS else "emacs",
                footer=decode(footer[1].removeprefix("\n")) if footer else None)


def _attributes(text: str) -> dict[str, str]:
    return {name: html.unescape(value) for name, value in ATTRIBUTE.findall(text)}


def resolve(form: Form, previous: dict[str, Field]) -> tuple[Form, set[str]]:
    """Complete a form against the fields already on screen.

    A field the AI shows again keeps whatever it doesn't restate: position, size, style,
    file, and the text the user typed (an empty body keeps it too; only a body replaces it).
    Returns the form and the ids of the fields to fill from their `file`: new fields, or a
    different file. Repeating file="..." never reloads it over unsaved edits.
    """
    fields, to_load = [], set()
    for f in form.fields:
        before = previous.get(f.id)
        if before is not None and before.kind == f.kind:
            kept = {name: getattr(before, name)
                    for name in ("top", "left", "width", "height", "style", "lang", "file")
                    if getattr(f, name) is None}
            new_file = f.file is not None and f.file != before.file
            f = replace(f, **kept, text=f.text or None)
            if new_file and f.text is None:
                to_load.add(f.id)
        elif f.file and not f.text:
            to_load.add(f.id)
        fields.append(f.with_defaults())
    return replace(form, fields=tuple(fields)), to_load


def _row(value: str | None) -> int | None:
    """A row: 1, 2, ... from the top, or -1, -2, ... from the bottom. 0 means not given."""
    try:
        return int(value) or None if value is not None else None
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    try:
        return max(0, int(value)) if value is not None else None
    except ValueError:
        return None


def _cursor(value: str | None) -> tuple[int, int] | None:
    line, _, col = (value or "").partition(":")
    try:
        return max(1, int(line)), max(1, int(col or 1))
    except ValueError:
        return None
