"""The rendered samples, played through pygame's mixer (docs/addon-music.md, section 6).

The only module that touches pygame. The mixer passes the samples on unchanged, plays a sound
again and again without a gap, and starts a queued sound on the sample after the one before
it. Only the mixer is started, not the display.
"""
from __future__ import annotations

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

from music_engine.song import RATE  # noqa: E402

BUFFER = 1024                                 # samples the mixer hands to the sound card at once
QUEUED_SECONDS = 0.5                          # the shortest sound that is queued behind another


class PlayerError(Exception):
    """The sound can't get out; the message is for the AI."""


class Player:
    def __init__(self) -> None:
        try:                                  # 44100 Hz, 16-bit, one channel, and nothing else
            pygame.mixer.init(frequency=RATE, size=-16, channels=1, buffer=BUFFER,
                              allowedchanges=0)
        except pygame.error as problem:
            raise PlayerError(f"no sound device: {problem}") from None
        self.channel = pygame.mixer.Channel(0)
        self.again: pygame.mixer.Sound | None = None   # a loop's later rounds, to keep queued
        self.once = False                     # a song that plays once is sounding

    def play(self, first: np.ndarray, again: np.ndarray | None, loop: bool) -> None:
        """Start a song. One that is playing stops in the same moment, with what it had
        queued."""
        sound, self.again, self.once = _sound(first), None, not loop
        if not loop:
            self.channel.play(sound)
        elif again is None:
            self.channel.play(sound, loops=-1)   # one sound, again and again
        else:
            # The first round, and the later ones queued behind it. tick() has to queue the
            # next one in time, so a round that is very short is queued several at once.
            rounds = -(-int(QUEUED_SECONDS * RATE) // len(again))
            self.again = _sound(np.tile(again, rounds))
            self.channel.play(sound)
            self.channel.queue(self.again)

    def tick(self) -> bool:
        """To be called a few times a second. It keeps a loop's next round queued, and it is
        True, once, when a song that plays once has ended by itself."""
        if self.again is not None and self.channel.get_queue() is None:
            self.channel.queue(self.again)
        if self.once and not self.channel.get_busy():
            self.once = False
            return True
        return False

    def stop(self) -> None:
        """End the sound at once. What wasn't played yet is thrown away."""
        self.again, self.once = None, False
        self.channel.stop()

    def close(self) -> None:
        self.stop()
        pygame.mixer.quit()


def _sound(samples: np.ndarray) -> pygame.mixer.Sound:
    return pygame.mixer.Sound(buffer=samples.astype("<i2").tobytes())
