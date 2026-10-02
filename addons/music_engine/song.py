"""A score, unfolded (docs/addon-music.md, section 4).

A Score still has patterns, chords and +. unfold() turns it into what the renderer needs: a
flat list of notes and, for every variable, its changes, each with its place in samples. It
raises ScoreError, as the reader does, for what only shows once the patterns are placed.

Everything is counted in whole numbers. A step's sample is worked out from the step itself and
never by adding lengths up, so a long song can't drift. No numpy is needed.
"""
from __future__ import annotations

from dataclasses import dataclass

from music_engine import limits
from music_engine.score import (Change, Line, Notes, Pattern, Placement, Plus, Score, ScoreError,
                                name_of)

RATE = 44100                                  # samples in a second: there is one sample rate
MINUTE = 60 * RATE                            # samples in a minute


@dataclass(frozen=True)
class Note:
    start: int                                # its first sample
    length: int                               # in samples, without its instrument's tail
    key: int                                  # its number, transposing included: A4 is 69
    instrument: str
    velocity: int


@dataclass(frozen=True)
class Glide:
    """A change to a variable: from whatever its value is at `first` to `value` at `last`.
    A jump is a glide with no length."""
    first: int                                # in samples
    last: int
    value: int


@dataclass(frozen=True)
class Song:
    notes: tuple[Note, ...]                   # by their first sample
    changes: dict[str, tuple[Glide, ...]]     # for every variable, by their first sample
    end: int                                  # the sample at which a loop starts again
    length: int                               # the samples of a song that plays once, tails too


def unfold(score: Score) -> Song:
    """The notes and the changes of a score. Raises ScoreError with every problem found."""
    return _Unfolder(score).song()


def sample_of(step: int, score: Score) -> int:
    """The sample a step starts at: the nearest one, with a half rounded up."""
    beat = score.bpm * score.steps            # steps in a minute
    return (2 * step * MINUTE + beat) // (2 * beat)


class _TooMany(Exception):
    """The song has more events than the limit: nothing more is unfolded."""


@dataclass(frozen=True)
class _Sound:
    """A note while it is still counted in steps, with the line that wrote it."""
    step: int
    duration: int
    key: int
    notes: Notes


class _Unfolder:
    def __init__(self, score: Score):
        self.score = score
        self.problems: dict[int, str] = {}    # by line: the first problem of a line counts
        self.starts: dict[str, list[int]] = {}    # of every pattern's lines, with + worked out
        self.sounds: list[_Sound] = []
        self.changes: list[tuple[int, Change]] = []    # each with its step
        self.events = 0
        self.reach = 0                        # the last step that anything reaches
        self.top = 0                          # the line of the song that is being placed

    def problem(self, line: int, message: str) -> None:
        self.problems.setdefault(line, message)

    def song(self) -> Song:
        self.check_nesting()
        self.fail_if_problems()
        for name, pattern in self.score.patterns.items():
            self.starts[name] = self.starts_of(pattern.lines)
        whole = []                            # the problems that have no line
        try:
            for line, start in zip(self.score.song, self.starts_of(self.score.song)):
                self.top = line.line
                self.place(line, start, 0, None)
        except _TooMany:
            self.problem(self.top, f"line {self.top}: the song has more than {limits.EVENTS} "
                                   f"events")
            self.fail_if_problems()
        changes = self.glides()
        notes = [Note(self.sample(sound.step),
                      self.sample(sound.step + sound.duration) - self.sample(sound.step),
                      sound.key, sound.notes.instrument, sound.notes.velocity)
                 for sound in self.sounds]
        end = self.sample(self.reach)
        length = max([end] + [note.start + note.length + self.tail(note) for note in notes])
        if not notes:
            whole.append("the song has no notes")
        elif length > limits.SONG_SECONDS * RATE:
            whole.append(f"the song is {-(-length // RATE)} seconds long, and the limit is "
                         f"{limits.SONG_SECONDS}")
        else:
            self.check_voices(notes)
        self.fail_if_problems(whole)
        return Song(tuple(sorted(notes, key=lambda note: note.start)), changes, end, length)

    def fail_if_problems(self, whole: list[str] = ()) -> None:
        problems = [message for _, message in sorted(self.problems.items())] + list(whole)
        if problems:
            raise ScoreError(problems)

    def sample(self, step: int) -> int:
        return sample_of(step, self.score)

    def tail(self, note: Note) -> int:
        return self.score.instruments[note.instrument].tail

    # ------------------------------------------------------------ before anything is placed

    def check_nesting(self) -> None:
        """A pattern only places patterns from above it, so how deep each one goes is known
        without placing anything."""
        depths: dict[str, int] = {}
        for name, pattern in self.score.patterns.items():
            inside = [(depths[line.pattern], line.line) for line in pattern.lines
                      if isinstance(line, Placement)]
            deepest, line = max(inside, key=lambda found: found[0], default=(0, 0))
            depths[name] = deepest + 1
            if depths[name] == limits.PATTERN_DEPTH + 1:    # the first that is too deep
                self.problem(line, f"line {line}: patterns are nested more than "
                                   f"{limits.PATTERN_DEPTH} deep")

    def starts_of(self, lines: tuple[Line, ...]) -> list[int]:
        """The step each line of a block starts at. A + counts from the end of the line
        above it."""
        starts, end = [], 0
        for line in lines:
            plus = isinstance(line.start, Plus)
            starts.append(end + line.start.distance if plus else line.start)
            end = starts[-1] + self.span(line)
        return starts

    def span(self, line: Line) -> int:
        """How many steps a line takes up, for the + below it."""
        if isinstance(line, Placement):
            return (self.score.patterns[line.pattern].length or 0) * line.times
        return line.duration

    # ------------------------------------------------------------ placing

    def place(self, line: Line, step: int, transpose: int, placed: Placement | None) -> None:
        """Put a line at a step. `placed` is the line that placed its pattern, if one did."""
        if isinstance(line, Placement):
            pattern = self.score.patterns[line.pattern]
            if pattern.length is not None:
                self.reach = max(self.reach, step + pattern.length * line.times)
            for time in range(line.times):
                self.place_pattern(pattern, step + time * (pattern.length or 0),
                                   transpose + line.transpose, line)
            return
        self.reach = max(self.reach, step + line.duration)
        if isinstance(line, Change):          # transposing leaves it as it is written
            self.count()
            self.changes.append((step, line))
            return
        for key in line.keys:
            self.count()
            if limits.LOWEST_KEY <= key + transpose <= limits.HIGHEST_KEY:
                self.sounds.append(_Sound(step, line.duration, key + transpose, line))
            else:
                way = "up" if transpose > 0 else "down"
                edge = "above B9" if transpose > 0 else "below C0"
                self.problem(placed.line, f"line {placed.line}: {placed.pattern} moved {way} by "
                                          f"{abs(transpose)} puts {name_of(key)} "
                                          f"(line {line.line}) {edge}")

    def place_pattern(self, pattern: Pattern, step: int, transpose: int,
                      placed: Placement) -> None:
        for line, start in zip(pattern.lines, self.starts[pattern.name]):
            self.place(line, step + start, transpose, placed)

    def count(self) -> None:
        """One more note or change. Counted while unfolding, not after, so that a small file
        can't make a million notes first."""
        self.events += 1
        if self.events > limits.EVENTS:
            raise _TooMany

    # ------------------------------------------------------------ what only shows afterwards

    def glides(self) -> dict[str, tuple[Glide, ...]]:
        """For every variable its changes, in order. Two that are the same count as one, so a
        pattern with automation can play on top of itself. Two different ones at one step are
        a problem: it's unclear which should win."""
        first: dict[tuple[str, int], Change] = {}
        for step, change in self.changes:
            other = first.setdefault((change.variable, step), change)
            if (other.duration, other.value) != (change.duration, change.value):
                low, high = sorted((other.line, change.line))
                self.problem(low, f"line {low} and line {high}: two different changes to "
                                  f"{change.variable} at step {step}")
        glides: dict[str, list[Glide]] = {name: [] for name in self.score.variables}
        for (variable, step), change in sorted(first.items(), key=lambda found: found[0][1]):
            glides[variable].append(Glide(self.sample(step), self.sample(step + change.duration),
                                          change.value))
        return {name: tuple(found) for name, found in glides.items()}

    def check_voices(self, notes: list[Note]) -> None:
        """A tail still sounds, so it counts. A note that ends at a sample doesn't sound in
        it any more, so its end is taken before another note's start."""
        edges = []
        for index, note in enumerate(notes):
            edges.append((note.start, 1, index))
            edges.append((note.start + note.length + self.tail(note), 0, index))
        sounding = 0
        for _, starts, index in sorted(edges):
            sounding += 1 if starts else -1
            if sounding > limits.VOICES:
                sound = self.sounds[index]
                self.problem(sound.notes.line, f"line {sound.notes.line}: more than "
                                               f"{limits.VOICES} notes sound at step {sound.step}")
                return
