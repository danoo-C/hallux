"""The real terminal: prompt_toolkit reads your keys, stdout shows the AI's text.

prompt_toolkit handles the keyboard side of line editing (arrows, backspace, history of
what you typed). Everything else is the AI's: the prompt it renders is the AI's prompt,
and its own screen-drawing keys are handed to the AI instead.
"""
from __future__ import annotations

import re
import shutil
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings

from hallux.blockmode import BlockMode
from hallux.machine import Key
from hallux.protocol import Action, Form

# Escape sequences other than colors (SGR): prompt_toolkit must print them as-is, zero-width.
NON_SGR_ESCAPE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-ln-z]")


def zero_width(prompt: str) -> str:
    """Mark non-color escapes (window titles, cursor moves) as zero-width for prompt_toolkit."""
    return NON_SGR_ESCAPE.sub(lambda m: f"\x01{m[0]}\x02", prompt)


class Terminal:
    def __init__(self, input=None, output=None) -> None:      # tests pass a pipe and a dummy
        keys = KeyBindings()

        @keys.add("c-l")                    # clearing the screen is the AI's job
        def _clear(event) -> None:
            event.app.exit(result=Key("C-l", event.app.current_buffer.text))

        self.session: PromptSession = PromptSession(
            history=InMemoryHistory(), key_bindings=keys, input=input, output=output)
        self.block = BlockMode(input=input, output=output)

    async def read_line(self, prompt: str, default: str = "") -> str | Key:
        return await self.session.prompt_async(ANSI(zero_width(prompt)), default=default)

    def write(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    def size(self) -> tuple[int, int]:
        return tuple(shutil.get_terminal_size())

    async def show_form(self, screen: str, form: Form) -> None:
        await self.block.show(screen, form)

    async def next_action(self) -> Action:
        return await self.block.next_action()

    async def end_form(self) -> None:
        await self.block.end()

    def field_text(self, id: str) -> str:
        return self.block.field_text(id)

    def field_saved(self, id: str) -> None:
        self.block.field_saved(id)
