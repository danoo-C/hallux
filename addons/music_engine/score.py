"""A score file, from text to its parts (docs/addon-music.md, sections 2 and 4).

read() returns a Score, or raises ScoreError with everything that is wrong with the file:
every problem has its line, and says what to write. The text comes from the AI, so nothing
here trusts it.

Nothing is unfolded or timed yet: a pattern stays a pattern, and a + stays a +. No numpy is
needed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from music_engine import expr, limits

KEYWORDS = ("INSTRUMENT", "PATTERN", "SONG")
SETTINGS = {"BPM": (limits.BPM_MIN, limits.BPM_MAX),
            "STEPS": (limits.STEPS_MIN, limits.STEPS_MAX)}
STEPS = 8                                     # steps in a quarter note, when the file sets none
VELOCITY = 255                                # of a note that names none: full
# All names share one namespace, and these are in it before the file says anything.
TAKEN = frozenset([*expr.NAMES, *expr.FUNCTIONS, *SETTINGS, *KEYWORDS])
SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
ACCIDENTALS = {"": 0, "#": 1, "b": -1}
SHARPS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
NUMBER = re.compile(r"-?[0-9]+")              # whole and decimal
NOTE = re.compile(r"([A-G])([#b]?)(-?[0-9]{1,3})")
PLUS = re.compile(r"\+\s*([0-9]*)")
KEYWORD = re.compile(r"(INSTRUMENT|PATTERN|SONG)(?![A-Za-z0-9_])")
SETTING = re.compile(r"([^\s=(]+)\s*=\s*(.*)")
PART = re.compile(r"([A-Za-z][A-Za-z0-9_]*)\s*=(?!=)\s*(.*)")

AN_EVENT = "an event is (start, duration, value, target, velocity)"
A_PLACEMENT = "a placement is (start, pattern, transpose, times)"
OWN_LINE = "put it on a line of its own"
BYTE_ORDER_MARK = "\ufeff"                     # some editors start a file with it


class ScoreError(Exception):
    """The score can't be played. `problems` has every problem, in the order of the lines;
    the message has the first of them, as many as the AI is to read at once."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        shown = [problem if len(problem) <= limits.PROBLEM_CHARS
                 else problem[:limits.PROBLEM_CHARS - 1] + "…"
                 for problem in self.problems[:limits.PROBLEMS]]
        if more := len(self.problems) - len(shown):
            shown.append(f"… and {more} more")
        super().__init__("\n".join(shown))


# ---------------------------------------------------------------- what a score is made of

@dataclass(frozen=True)
class Plus:
    """A start written as + or +4: so many steps after the end of the line above."""
    distance: int


@dataclass(frozen=True)
class Notes:
    """An event on an instrument: one note, or the notes of a chord."""
    line: int
    start: int | Plus
    duration: int                             # in steps, 1 or more
    instrument: str
    keys: tuple[int, ...]                     # the notes as numbers: A4 is 69
    velocity: int


@dataclass(frozen=True)
class Change:
    """An event on a variable: a jump, or with a duration a glide."""
    line: int
    start: int | Plus
    duration: int                             # in steps, 0 or more
    variable: str
    value: int


@dataclass(frozen=True)
class Placement:
    """A pattern placed in a pattern or in the song."""
    line: int
    start: int | Plus
    pattern: str
    transpose: int                            # in semitones
    times: int


Line = Notes | Change | Placement


@dataclass(frozen=True)
class Instrument:
    name: str
    line: int
    tail: int                                 # in samples
    parts: dict[str, expr.Node]               # the named parts, in their order
    sample: expr.Node                         # the last line


@dataclass(frozen=True)
class Pattern:
    name: str
    line: int
    length: int | None                        # in steps
    lines: tuple[Line, ...]


@dataclass(frozen=True)
class Score:
    bpm: int
    steps: int                                # steps in a quarter note
    variables: dict[str, int]                 # each with its starting value
    instruments: dict[str, Instrument]
    patterns: dict[str, Pattern]
    song: tuple[Line, ...]


def read(text: str) -> Score:
    """The parts of a score file. Raises ScoreError with every problem that was found."""
    if len(text.encode("utf-8")) > limits.SCORE_BYTES:
        raise ScoreError([f"the score is bigger than {limits.SCORE_BYTES} bytes"])
    reader = _Reader()
    for number, line in enumerate(text.removeprefix(BYTE_ORDER_MARK).split("\n"), 1):
        reader.take(number, line.rstrip("\r"))
    return reader.finish()


def name_of(key: int) -> str:
    """The name of a note's number, with a sharp where there is a choice: 61 is C#4."""
    return f"{SHARPS[key % 12]}{key // 12 - 1}"


def key_of(note: str) -> int | None:
    """The number of a note name, or nothing if it isn't one: A4 is 69, C4 is 60."""
    if not (parts := NOTE.fullmatch(note)):
        return None
    letter, accidental, octave = parts.groups()
    return 12 * (int(octave) + 1) + SEMITONES[letter] + ACCIDENTALS[accidental]


# ---------------------------------------------------------------- reading

class _Bad(Exception):
    """What is wrong with the line that is being read."""


def _whole(text: str, what: str) -> int:
    if not NUMBER.fullmatch(text):
        raise _Bad(f"{what} is a whole number, not {text or 'nothing'}")
    if len(text) > 20 or not -2 ** 63 <= int(text) < 2 ** 63:
        raise _Bad(f"the number {text} doesn't fit 64 bits")
    return int(text)


@dataclass
class _InstrumentBlock:
    line: int
    names: list[str]                          # what a line of it may use, so far
    label: str = ""                           # its name as written, for the messages
    name: str | None = None                   # its name, once that passed the checks
    tail: int = 0
    parts: dict[str, expr.Node] = field(default_factory=dict)
    part_lines: dict[str, int] = field(default_factory=dict)
    sample: expr.Node | None = None
    sample_line: int | None = None


@dataclass
class _EventsBlock:
    """A PATTERN, or SONG."""
    line: int
    song: bool = False
    label: str = ""
    name: str | None = None
    length: int | None = None
    lines: list[Line] = field(default_factory=list)
    seen: int = 0                             # its lines so far, readable or not
    no_length: str | None = None              # the line above placed this pattern, which has none
    keep: bool = True                         # False for a second SONG:

    @property
    def title(self) -> str:
        return "SONG:" if self.song else f"PATTERN {self.label}"


class _Reader:
    def __init__(self) -> None:
        self.problems: dict[int, str] = {}    # by line: the first problem of a line counts
        self.settings: dict[str, int] = {}
        self.declared: dict[str, int] = {}    # every name of the score, with its line
        self.variables: dict[str, int] = {}
        self.instruments: dict[str, Instrument] = {}
        self.patterns: dict[str, Pattern] = {}
        self.part_names: set[str] = set()
        self.song: tuple[Line, ...] = ()
        self.song_line: int | None = None
        self.block: _InstrumentBlock | _EventsBlock | None = None

    def problem(self, line: int, message: str) -> None:
        self.problems.setdefault(line, message)

    def take(self, number: int, line: str) -> None:
        text = line.strip()
        if not text or text.startswith("#"):
            return
        try:
            if line[0] in " \t":
                self.inside(number, text)
            else:
                self.start(number, text)
        except _Bad as bad:
            self.problem(number, str(bad))

    def finish(self) -> Score:
        self.close()
        problems = [f"line {line}: {message}" for line, message in sorted(self.problems.items())]
        if "BPM" not in self.settings:
            problems.append("the file has no BPM")
        if self.song_line is None:
            problems.append("the file has no SONG:")
        if problems:
            raise ScoreError(problems)
        return Score(self.settings["BPM"], self.settings.get("STEPS", STEPS), self.variables,
                     self.instruments, self.patterns, self.song)

    # ------------------------------------------------------------ lines that aren't indented

    def start(self, number: int, text: str) -> None:
        if text.startswith("("):              # an event that lost its indentation
            raise _Bad("this line must be indented: it belongs to a PATTERN or to SONG:")
        self.close()
        text = self.without_comment(number, text, "this line")
        setting = SETTING.fullmatch(text)
        keyword = found[1] if (found := KEYWORD.match(text)) and not setting else None
        if not setting and not keyword and (lower := KEYWORD.match(text.upper())):
            keyword = lower[1]                # read on as if it were written right
            self.problem(number, f"the keywords are in upper case: write {keyword}")
            text = keyword + text[len(keyword):]
        if self.song_line is not None and keyword != "SONG":
            self.problem(number, "SONG: must be the last block")
        if setting:
            self.set(number, *setting.groups())
        elif keyword == "INSTRUMENT":
            self.start_instrument(number, text)
        elif keyword == "PATTERN":
            self.start_pattern(number, text)
        elif keyword == "SONG":
            self.start_song(number, text)
        else:
            raise _Bad("can't read this line")

    def without_comment(self, number: int, text: str, after: str) -> str:
        """A comment only follows an event. Elsewhere it is a problem, and the line is read
        without it, so that nothing below it goes wrong for that reason alone."""
        if "#" in text:
            self.problem(number, f"a comment can't follow {after}: {OWN_LINE}")
        return text.partition("#")[0].rstrip()

    @staticmethod
    def header(keyword: str, text: str) -> list[str]:
        """The words between a keyword and its colon."""
        if not text.endswith(":"):
            raise _Bad(f"{keyword} needs a : at the end of its line")
        return text[len(keyword):-1].split()

    def set(self, number: int, name: str, value: str) -> None:
        if name in SETTINGS:
            if name in self.settings:
                raise _Bad(f"{name} is set twice")
            low, high = SETTINGS[name]
            self.settings[name] = low         # it is set, whatever is wrong with its number
            if not low <= (setting := _whole(value, name)) <= high:
                raise _Bad(f"{name} must be between {low} and {high}")
            self.settings[name] = setting
        else:
            self.declare(name, number)
            self.variables[name] = 0
            self.variables[name] = _whole(value, f"the value of {name}")

    def declare(self, name: str, line: int) -> None:
        self.check_name(name)
        self.declared[name] = line

    def check_name(self, name: str) -> None:
        if not NAME.fullmatch(name):
            raise _Bad(f"{name} isn't a name: a name is letters, digits and _, and starts "
                       f"with a letter")
        if name in TAKEN:
            raise _Bad(f"{name} is a taken name")
        if key_of(name) is not None:
            raise _Bad(f"{name} is a note name, and can't be declared")
        if name in self.declared:
            raise _Bad(f"{name} is declared twice (first on line {self.declared[name]})")

    def start_instrument(self, number: int, text: str) -> None:
        # The block is there before its header is checked: its lines are read all the same.
        block = self.block = _InstrumentBlock(number, list(expr.NAMES) + list(self.variables))
        words = self.header("INSTRUMENT", text)
        block.label = words[0] if words else ""
        if not 1 <= len(words) <= 2:
            raise _Bad("an instrument starts with INSTRUMENT name: or INSTRUMENT name tail:")
        self.declare(words[0], number)
        block.name = words[0]
        if len(words) == 2:
            if not 0 <= (tail := _whole(words[1], "a tail")) <= limits.TAIL_SAMPLES:
                raise _Bad(f"a tail is 0 to {limits.TAIL_SAMPLES} samples")
            block.tail = tail

    def start_pattern(self, number: int, text: str) -> None:
        block = self.block = _EventsBlock(number)
        words = self.header("PATTERN", text)
        block.label = words[0] if words else ""
        if not 1 <= len(words) <= 2:
            raise _Bad("a pattern starts with PATTERN name: or PATTERN name length:")
        self.declare(words[0], number)
        block.name = words[0]
        if len(words) == 2:
            if (length := _whole(words[1], "a pattern's length")) < 1:
                raise _Bad("a pattern's length is 1 or more")
            block.length = length

    def start_song(self, number: int, text: str) -> None:
        first, self.song_line = self.song_line, self.song_line or number
        self.block = _EventsBlock(number, song=True, keep=first is None)
        if first is not None:
            raise _Bad(f"SONG: is declared twice (first on line {first})")
        if self.header("SONG", text):
            raise _Bad("SONG: has no name")

    def close(self) -> None:
        """The block that was being read is complete: keep it, and say what it lacks."""
        block, self.block = self.block, None
        if isinstance(block, _InstrumentBlock):
            if block.sample_line is None:
                self.problem(block.line, f"INSTRUMENT {block.label} has no expression")
            if block.name:
                self.instruments[block.name] = Instrument(
                    block.name, block.line, block.tail, block.parts, block.sample)
        elif isinstance(block, _EventsBlock):
            if not block.seen:
                self.problem(block.line, f"{block.title} is empty")
            if block.name:
                self.patterns[block.name] = Pattern(
                    block.name, block.line, block.length, tuple(block.lines))
            elif block.song and block.keep:
                self.song = tuple(block.lines)

    # ------------------------------------------------------------ indented lines

    def inside(self, number: int, text: str) -> None:
        if self.block is None:
            raise _Bad("this line belongs to nothing: it is indented, and no INSTRUMENT, "
                       "PATTERN or SONG is above it")
        if isinstance(self.block, _InstrumentBlock):
            self.instrument_line(self.block, number, text)
        else:
            self.block.seen += 1
            no_length, self.block.no_length = self.block.no_length, None
            line = self.events_line(self.block, number, text, no_length)
            self.block.lines.append(line)
            if isinstance(line, Placement) and self.patterns[line.pattern].length is None:
                self.block.no_length = line.pattern

    def instrument_line(self, block: _InstrumentBlock, number: int, text: str) -> None:
        text = self.without_comment(number, text, "an expression")
        if block.sample_line is not None:
            raise _Bad(f"the expression on line {block.sample_line} has to be the last line "
                       f"of INSTRUMENT {block.label}")
        if not (part := PART.fullmatch(text)):
            block.sample_line = number
            block.sample = self.expression(text, block.names)
            return
        name, text = part.groups()
        try:
            if name in block.part_lines:
                raise _Bad(f"{name} is declared twice (first on line {block.part_lines[name]})")
            self.check_name(name)
            if len(block.part_lines) >= limits.PARTS:
                raise _Bad(f"INSTRUMENT {block.label} has more than {limits.PARTS} named parts")
            block.part_lines[name] = number
            self.part_names.add(name)
            block.parts[name] = self.expression(text, block.names)
        finally:
            block.names.append(name)          # the lines below may use it, whatever is wrong

    @staticmethod
    def expression(text: str, names: list[str]) -> expr.Node:
        try:
            return expr.read(text, names)
        except expr.ExprError as problem:
            raise _Bad(str(problem)) from None

    def events_line(self, block: _EventsBlock, number: int, text: str,
                    no_length: str | None) -> Line:
        """A line of a pattern or of the song: an event, or a pattern placed in it."""
        if not text.startswith("("):
            raise _Bad(f"can't read this line: {AN_EVENT}, in brackets")
        inner, closed, after = text[1:].partition(")")
        if not closed:
            raise _Bad("the ) is missing")
        if after.strip() and not after.strip().startswith("#"):
            raise _Bad("only a comment, with a # in front, can follow the )")
        fields = [part.strip() for part in inner.split(",")]
        second = fields[1] if len(fields) > 1 else ""

        def start() -> int | Plus:
            if plus := PLUS.fullmatch(fields[0]):
                if block.seen == 1:
                    raise _Bad("+ has no line above it to count from")
                if no_length:
                    raise _Bad(f"+ can't count from {no_length}: that pattern has no length")
                return Plus(_whole(plus[1] or "0", "the distance after +"))
            if not NUMBER.fullmatch(fields[0]):
                raise _Bad(f"a start is a whole number or +, not {fields[0] or 'nothing'}")
            if (value := _whole(fields[0], "a start")) < 0:
                raise _Bad("a start is 0 or more")
            return value

        if second in self.patterns and "" not in fields:
            return self.placement(number, fields, start)
        if NUMBER.fullmatch(second):
            if len(fields) not in (4, 5) or "" in fields:
                raise _Bad(AN_EVENT)
            return self.event(block, number, fields, start)
        if len(fields) < 2 or "" in fields or key_of(second) is not None \
                or second in self.instruments or second in self.variables:
            raise _Bad(AN_EVENT)              # the duration is missing
        if second == block.name:
            raise _Bad(f"{second} can't be placed inside itself")
        if NAME.fullmatch(second):
            raise _Bad(f"{second} isn't declared above this line")
        raise _Bad(f"the second field is a duration or a pattern's name, not {second}")

    def placement(self, number: int, fields: list[str], start) -> Placement:
        name = fields[1]
        if len(fields) > 4:
            raise _Bad(A_PLACEMENT)
        transpose = _whole(fields[2], "a transposition") if len(fields) > 2 else 0
        times = _whole(fields[3], "the number of times") if len(fields) > 3 else 1
        if times < 1:
            raise _Bad("a pattern is placed 1 time or more")
        if times > 1 and self.patterns[name].length is None:
            raise _Bad(f"{name} has no length, so it can't be repeated")
        return Placement(number, start(), name, transpose, times)

    def event(self, block: _EventsBlock, number: int, fields: list[str], start) -> Line:
        duration_text, value, target = fields[1:4]
        if target in self.instruments:
            keys = tuple(self.key(note, target, value) for note in value.split())
            velocity = _whole(fields[4], "a velocity") if len(fields) == 5 else VELOCITY
            if not 0 <= velocity <= 255:
                raise _Bad("a velocity is 0 to 255")
            if (duration := _whole(duration_text, "a duration")) < 1:
                raise _Bad("a note needs a duration of 1 or more")
            return Notes(number, start(), duration, target, keys, velocity)
        if target in self.variables:
            if len(fields) == 5 or len(value.split()) > 1:
                raise _Bad("a change to a variable has one value")
            if not NUMBER.fullmatch(value):
                raise _Bad(f"{target} is a variable: its value is a number, not {value}")
            amount = _whole(value, "a value")
            if (duration := _whole(duration_text, "a duration")) < 0:
                raise _Bad("a duration is 0 or more")
            return Change(number, start(), duration, target, amount)
        if target in self.patterns or target == block.name:
            raise _Bad(f"{target} is a pattern: place it with ({fields[0]}, {target})")
        if target in self.part_names:
            raise _Bad(f"{target} is a named part of an instrument: an event can't change it")
        raise _Bad(f"unknown instrument or variable: {target}")

    @staticmethod
    def key(note: str, instrument: str, value: str) -> int:
        if (key := key_of(note)) is None:
            raise _Bad(f"{instrument} is an instrument: its value is a note such as A4, "
                       f"not {value}")
        if not limits.LOWEST_KEY <= key <= limits.HIGHEST_KEY:
            raise _Bad(f"{note} is outside C0 to B9")
        return key
