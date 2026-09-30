"""The wire between the terminal and the AI: envelopes in, replies out.

The AI answers every envelope with

    <screen>
    ...exactly what the terminal shows...
    </screen><prompt>user@hallux:~$ </prompt>

optionally followed by control tags (<halt/>, <reboot/>, <tty mode="raw"/>). It writes
control characters as Unicode control pictures ("␛" for ESC), which decode() turns into
real bytes.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

# U+2400..U+241F picture the C0 control characters 0x00..0x1F; U+2421 pictures DEL.
CONTROL_PICTURES = {0x2400 + c: c for c in range(32)} | {0x2421: 0x7F}
TTY_TAG = re.compile(r'<tty\s+mode="(raw|cooked)"\s*/>')


@dataclass(frozen=True)
class Reply:
    screen: str                   # printed byte for byte
    prompt: str | None            # None when the reply had no <prompt>
    halt: bool = False
    reboot: bool = False
    tty: str | None = None        # "raw" or "cooked" when the AI switches modes


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
    )
