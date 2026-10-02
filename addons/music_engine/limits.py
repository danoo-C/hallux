"""Every limit of the music addon, as a named number (docs/addon-music.md, section 6).

A score is text from the AI, possibly led by something it read in a file, so everything about
it is bounded. These are first numbers: they are confirmed or changed when a whole render is
timed.
"""

EXPRESSION_CHARS = 500                        # the longest expression
EXPRESSION_DEPTH = 40                         # brackets, signs and choices inside each other
