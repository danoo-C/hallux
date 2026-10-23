"""Hallux's own panel: a window over the machine, opened and closed with Ctrl+F12.

This file is the host. It owns the screen: the tab row, the tab that is shown under it, and
the foot with that tab's keys. It knows nothing of what a tab shows. A tab is a class in a
file of its own in hallux/panel_tabs/, and a new one is a new file and one more entry in the
list the host is given. The AI never learns of the panel; of a copy from the Files tab it
is told only that files arrived. See docs/config-panel.md.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Callable, Sequence

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import (
    DynamicKeyBindings, KeyBindings, KeyBindingsBase, merge_key_bindings,
)
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import (
    AnyContainer, DynamicContainer, HSplit, Layout, VSplit, Window, WindowAlign,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from hallux.blockmode import ESCAPE_SECONDS, OPEN_KEY, POWER_CUT_KEY
from hallux.statusbar import DIM, GRAY, YELLOW_NOTE, StatusBar

MESSAGE_SECONDS = 4.0                 # how long the foot says why a tab can't be chosen

log = logging.getLogger("hallux")


class Tab:
    """One tab of the panel. It is built before the panel exists and needs nothing of it
    until the host attaches itself. What a tab doesn't say for itself is as below."""

    title = ""                        # in the tab row; its first letter, in lowercase, is its key,
    key = ""                          # unless it names one: a letter of its title (Packa_g_es)
    container: AnyContainer           # its part of the screen
    bindings: KeyBindingsBase         # its keys: they act only while it is the shown tab
    typing = False                    # True while a row is open for typing: the letters are its own
    esc = "close"                     # what Esc does in it, for the foot: Details says "back"
    host: Panel

    def attach(self, host: Panel) -> None:
        """Once, when the panel is built. Through the host a tab can show another tab
        (host.show), close the panel (host.close), put a word into the foot (host.say), and
        share which job is picked (host.pick)."""
        self.host = host

    def hint(self) -> str:
        """Its keys, for the foot."""
        return ""

    def disabled(self) -> str | None:
        """None, or why it can't be chosen."""
        return None

    def wants_first(self) -> bool:
        """Whether the panel should open on it."""
        return False

    def leave(self) -> bool:
        """Esc was pressed. True if the tab had something to leave, such as an open row."""
        return False

    def shown(self) -> None:
        """It has become the shown tab: start fresh."""

    def paste(self, text: str) -> bool:
        """Something was pasted while no row is open for typing. True if the tab takes it."""
        return False


def key_of(tab: Tab) -> str:
    """The letter that chooses a tab: its own key, or its title's first letter."""
    return tab.key or tab.title[:1].lower()


class Panel:
    def __init__(self, tabs: Sequence[Tab], bar: StatusBar | None = None,
                 power_cut: Callable[[], None] = lambda: None,
                 ctrl_c: Callable[[], None] = lambda: None) -> None:
        self.tabs = list(tabs)                           # in the order of the tab row
        keys: dict[str, Tab] = {}
        for tab in self.tabs:
            if (other := keys.setdefault(key_of(tab), tab)) is not tab:
                raise ValueError(f"two tabs have the same key, {key_of(tab)}: {other.title} and "
                                 f"{tab.title}")
        self.bar = bar                                   # hallux's status bar, for the last row
        self.power_cut = power_cut                       # the hard exit
        self.ctrl_c = ctrl_c                             # every Ctrl-C counts for it
        self.tab = self.tabs[-1]                         # the tab that is shown
        self.pick: object = None                         # what tabs share: the job that is picked
        self.message = ""                                # in the foot for a moment, not the hint
        self.fading: asyncio.TimerHandle | None = None   # takes the message away again
        self.said = 0                                    # counts the calls of say()
        self.is_open = False
        self.closed = asyncio.Event()
        self.closed.set()
        self.on_close: Callable[[], None] | None = None  # for who shows it as a layer: called
                                                         # by the key that closes it, at once
        self.app: Application | None = None              # the app of run(), while it runs
        self.bindings = self._bindings()
        self.container = HSplit([
            VSplit([Window(FormattedTextControl([("bold", " Hallux")]), dont_extend_width=True),
                    Window(FormattedTextControl(self._tab_row), align=WindowAlign.RIGHT)],
                   height=1),
            DynamicContainer(lambda: self.tab.container),
            Window(FormattedTextControl(self._foot), height=1)])
        for tab in self.tabs:
            tab.attach(self)

    # ---------------------------------------------------------------- opening and closing

    def open(self) -> None:
        """Open it fresh: on the tab it should open on, and with nothing said in the foot."""
        self.is_open = True
        self.closed.clear()
        self._show(next((tab for tab in self.tabs if tab.wants_first()), self.tabs[-1]))

    def close(self) -> None:
        """Close it. Closing what is closed does nothing."""
        if not self.is_open:
            return
        self.is_open = False
        self.say("")
        self.closed.set()
        if self.app is not None and self.app.is_running and not self.app.is_done:
            self.app.exit()                              # once: a second exit is an error
        if self.on_close is not None:
            self.on_close()

    async def wait_closed(self) -> None:
        """Wait for the key that closes it. The app of run() may still be up for a moment."""
        await self.closed.wait()

    async def run(self, input=None, output=None) -> None:
        """Show the panel in a full-screen app of its own, until it is closed."""
        root = self.container
        if self.bar is not None:
            columns = lambda: get_app().output.get_size().columns          # noqa: E731
            bar = FormattedTextControl(lambda: self.bar.fragments(columns()))
            root = HSplit([root, Window(bar, height=1)])
        self.app = Application(layout=Layout(root), key_bindings=self.bindings, full_screen=True,
                               mouse_support=True, input=input, output=output)
        self.app.ttimeoutlen = ESCAPE_SECONDS
        try:                                  # Ctrl-C's signal belongs to the answer that runs
            await self.app.run_async(pre_run=self.open, handle_sigint=False)
        finally:
            self.app = None
            self.close()                      # however the app ended

    def invalidate(self) -> None:
        """Draw again: something it shows has changed."""
        if self.app is not None:
            self.app.invalidate()

    # ---------------------------------------------------------------- the tabs

    def show(self, title: str) -> None:
        """Show the tab with this title. For a tab that leads to another."""
        for tab in self.tabs:
            if tab.title == title:
                return self._choose(tab)
        raise ValueError(f"the panel has no tab {title!r}")

    def _choose(self, tab: Tab) -> None:
        if reason := tab.disabled():
            self.say(reason)
        else:
            self._show(tab)

    def _show(self, tab: Tab) -> None:
        self.tab = tab
        self.say("")
        tab.shown()
        with contextlib.suppress(ValueError):            # nobody shows the panel yet
            get_app().layout.focus(tab.container)
        get_app().invalidate()                           # a tab may ask for it between two keys

    def say(self, message: str) -> None:
        """Put a message in the foot, in place of the hint, for a moment. "" takes it away."""
        self.message = message
        self.said += 1
        if self.fading is not None:
            self.fading.cancel()
            self.fading = None
        if message:
            with contextlib.suppress(RuntimeError):      # no loop: it stays until the next one
                self.fading = asyncio.get_running_loop().call_later(MESSAGE_SECONDS, self._fade)

    def _fade(self) -> None:
        self.message, self.fading = "", None
        get_app().invalidate()

    # ---------------------------------------------------------------- what the host draws

    def _tab_row(self) -> list:
        """Every tab's title with its key underlined. The shown one has brackets, a disabled
        one is dark grey, and a click on a title chooses it."""
        row = []
        for tab in self.tabs:
            style = f"fg:{DIM}" if tab.disabled() else "bold" if tab is self.tab else ""
            left, right = ("[ ", " ]") if tab is self.tab else ("  ", "  ")
            click = self._click(tab)
            at = max(0, tab.title.lower().find(key_of(tab)))      # the key, underlined
            row += [(style, left, click), (style, tab.title[:at], click),
                    (f"{style} underline", tab.title[at:at + 1], click),
                    (style, tab.title[at + 1:], click), (style, right, click), ("", " ")]
        return row

    def _click(self, tab: Tab) -> Callable[[MouseEvent], None]:
        def handle(event: MouseEvent) -> None:
            if event.event_type == MouseEventType.MOUSE_UP:
                self._choose(tab)
        return handle

    def _foot(self) -> list:
        """The keys of the shown tab, then the host's own."""
        if self.message:
            return [(f"fg:{YELLOW_NOTE}", f" {self.message}")]
        keys = [self.tab.hint()]
        if not self.tab.typing:                          # while it is, the letters and Esc are its
            if len(self.tabs) > 1:
                keys.append(" ".join(key_of(tab) for tab in self.tabs) + " tabs")
            keys.append(f"Esc {self.tab.esc}")
        return [(f"fg:{GRAY}", " " + " · ".join(key for key in keys if key))]

    # ---------------------------------------------------------------- the host's keys

    def _bindings(self) -> KeyBindingsBase:
        kb = KeyBindings()
        letters = Condition(lambda: not self.tab.typing)
        for tab in self.tabs:
            kb.add(key_of(tab), filter=letters)(lambda event, tab=tab: self._choose(tab))
        # Eager: a row that is open for typing has keys that start with Esc, and without this
        # Esc would wait a second to see whether one of them follows.
        kb.add("escape", eager=True)(lambda event: self._escape())
        kb.add(OPEN_KEY, eager=True)(lambda event: self.close())
        kb.add(POWER_CUT_KEY, eager=True)(lambda event: self.power_cut())
        kb.add("c-c", eager=True)(lambda event: self.ctrl_c())       # and nothing else
        # A paste is the host's while no row is open for typing: a drop arrives as one, and it
        # finds the tab that takes it from any tab. Of two bindings for one key the later is
        # called, and these come after the tab's, so a tab never binds it for itself.
        kb.add(Keys.BracketedPaste, filter=letters)(lambda event: self._paste(event.data))
        return merge_key_bindings([DynamicKeyBindings(lambda: self.tab.bindings), kb])

    def _paste(self, text: str) -> None:
        """Offer a paste to the shown tab, then to the others in the order of the row. The
        first that takes it is shown, with what it said about it. A disabled tab isn't asked."""
        said = self.said
        offered = [self.tab, *(tab for tab in self.tabs if tab is not self.tab)]
        taker = next((tab for tab in offered if not tab.disabled() and tab.paste(text)), None)
        log.info("panel: a paste of %d characters, %s", len(text),
                 f"taken by {taker.title}" if taker else "taken by no tab")
        if taker is not None and taker is not self.tab:
            message = self.message if self.said != said else ""
            self._show(taker)
            self.say(message)

    def _escape(self) -> None:
        if not self.tab.leave():                         # the tab had nothing open
            self.close()
