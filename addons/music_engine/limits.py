"""Every limit of the music addon, as a named number (docs/addon-music.md, section 6).

A score is text from the AI, possibly led by something it read in a file, so everything about
it is bounded. These are first numbers: they are confirmed or changed when a whole render is
timed.
"""

SCORE_BYTES = 64 * 1024                       # the biggest score file
PROBLEMS = 20                                 # problems one play reports, and the longest
PROBLEM_CHARS = 160                           # of them: the result has to stay small

BPM_MIN, BPM_MAX = 20, 400
STEPS_MIN, STEPS_MAX = 1, 96                  # steps in a quarter note
LOWEST_KEY, HIGHEST_KEY = 12, 131             # C0 and B9, as note numbers

SONG_SECONDS = 300                            # the longest song, with its tails
EVENTS = 10_000                               # notes and changes, once the patterns are unfolded
PATTERN_DEPTH = 8                             # patterns inside patterns
VOICES = 64                                   # notes that sound at once, tails included

EXPRESSION_CHARS = 500                        # the longest expression
EXPRESSION_DEPTH = 40                         # brackets, signs and choices inside each other
PARTS = 16                                    # named parts of one instrument
TAIL_SAMPLES = 441_000                        # the longest tail: 10 seconds
