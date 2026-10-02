"""An instrument's expression, from text to a tree (docs/addon-music.md, section 3).

The text comes from the AI, so nothing here trusts it. There is no eval: only the operators,
functions and names of the design are accepted, and the length and the nesting are limited.

read() returns the tree, or raises ExprError with one problem, worded for the AI: it says
what to write, not only what is wrong. Nothing is computed here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Collection, NamedTuple

from music_engine import limits

# What every note gives its expression. The score adds its variables and named parts.
NAMES = ("t", "p", "vel", "dur", "key")
# The functions, and how many values each takes.
FUNCTIONS = {"sin": 1, "saw": 1, "square": 1, "tri": 1, "noise": 1,
             "decay": 2, "min": 2, "max": 2, "abs": 1}
SIGNS = ("-", "~")                            # the operators in front of one value
# The operators between two values, by how tightly they bind: the lower, the tighter. It is
# C's order, and the numbers are the levels of the plan's table.
LEVELS = {"*": 3, "/": 3, "%": 3,
          "+": 4, "-": 4,
          "<<": 5, ">>": 5,
          "<": 6, "<=": 6, ">": 6, ">=": 6,
          "==": 7, "!=": 7,
          "&": 8,
          "^": 9,
          "|": 10}
LOOSEST = 10
# What the AI writes out of habit from other languages, and what to write instead.
NOT_HERE = {"&&": "use & between comparisons",
            "||": "use | between comparisons",
            "!": "write x == 0",
            "**": "multiply",
            "//": "/ already gives a whole number",
            ">>>": "use >>, which keeps the sign",
            "=": "a comparison is =="}

TOKEN = re.compile(r"""
      (?P<number> \.?[0-9][0-9A-Za-z_.]* )
    | (?P<name>   [A-Za-z][A-Za-z0-9_]* )
    | (?P<op>     >>> | && | \|\| | \*\* | // | << | >> | <= | >= | == | !=
                | [-+*/%&|^~<>?:(),!=] )
""", re.VERBOSE)
NUMBER = re.compile(r"0[xX][0-9A-Fa-f]+|0|[1-9][0-9]*")
SPACE = re.compile(r"\s*")


class ExprError(Exception):
    """The expression can't be read; the message is for the AI."""


# ---------------------------------------------------------------- the tree

@dataclass(frozen=True)
class Number:
    value: int                                # as a signed 64-bit number


@dataclass(frozen=True)
class Name:
    name: str


@dataclass(frozen=True)
class Unary:
    op: str                                   # one of SIGNS
    value: Node


@dataclass(frozen=True)
class Binary:
    op: str                                   # one of LEVELS
    left: Node
    right: Node


@dataclass(frozen=True)
class Choice:
    """condition ? then : otherwise"""
    condition: Node
    then: Node
    otherwise: Node


@dataclass(frozen=True)
class Call:
    function: str                             # one of FUNCTIONS
    args: tuple[Node, ...]


Node = Number | Name | Unary | Binary | Choice | Call


# ---------------------------------------------------------------- reading

def read(text: str, names: Collection[str]) -> Node:
    """The tree of an expression. `names` are the names it may use: those of NAMES, the
    score's variables, and the named parts above its line. Raises ExprError."""
    if len(text) > limits.EXPRESSION_CHARS:
        raise ExprError(f"the expression is longer than {limits.EXPRESSION_CHARS} characters")
    reader = _Reader(_tokens(text), names)
    if reader.peek().kind == "end":
        raise ExprError("the expression is empty")
    tree = reader.expression()
    if reader.peek().kind != "end":
        raise _unexpected(reader.peek())
    return tree


class Token(NamedTuple):
    kind: str                                 # "number", "name", "op" or "end"
    text: str
    value: int = 0                            # of a number


def _tokens(text: str) -> list[Token]:
    tokens, at = [], SPACE.match(text).end()
    while at < len(text):
        found = TOKEN.match(text, at)
        if not found:
            raise ExprError(f"unexpected character: {text[at]}")
        kind, piece = found.lastgroup, found.group()
        if piece in NOT_HERE:
            raise ExprError(f"{piece} isn't an operator here: {NOT_HERE[piece]}")
        tokens.append(Token(kind, piece, _number(piece) if kind == "number" else 0))
        at = SPACE.match(text, found.end()).end()
    return tokens + [Token("end", "")]


def _number(text: str) -> int:
    """A whole number, decimal or hexadecimal. From 2^63 up it wraps around, as everything
    does in the arithmetic: 0xFFFFFFFFFFFFFFFF is -1."""
    if not NUMBER.fullmatch(text):
        if "." in text:
            raise ExprError("whole numbers only: multiply first, then divide")
        if text.isdigit():                    # 017: 15 in C, 17 to a reader, so neither
            raise ExprError(f"can't read the number {text}: a number doesn't start with 0")
        raise ExprError(f"can't read the number {text}: write it in decimal, or in "
                        f"hexadecimal with 0x")
    value = int(text, 0)
    if value >= 1 << 64:
        raise ExprError(f"the number {text} doesn't fit 64 bits")
    return value - (1 << 64) if value >= 1 << 63 else value


def _unexpected(token: Token) -> ExprError:
    if token.kind == "end":
        return ExprError("the expression ends too early")
    return ExprError(f"unexpected {token.text}")


class _Reader:
    """Reads the tokens of one expression, from the loosest level down to a single value."""

    def __init__(self, tokens: list[Token], names: Collection[str]):
        self.tokens, self.names = tokens, names
        self.at = 0
        self.depth = 0

    def peek(self) -> Token:
        return self.tokens[self.at]

    def take(self) -> Token:
        token = self.tokens[self.at]
        if token.kind != "end":                   # the end stays, however often it is taken
            self.at += 1
        return token

    def expect(self, text: str) -> None:
        token = self.take()
        if token.text != text:
            raise _unexpected(token)

    def inside(self, parse: Callable[[], Node]) -> Node:
        """Read what sits inside something else: brackets, a sign, a choice. The count of
        those is what bounds how deep reading, and later computing, can go."""
        self.depth += 1
        if self.depth > limits.EXPRESSION_DEPTH:
            raise ExprError(f"the expression is nested more than {limits.EXPRESSION_DEPTH} deep")
        node = parse()
        self.depth -= 1
        return node

    def expression(self) -> Node:
        """Level 11: a ? b : c, grouped from the right."""
        condition = self.binary(LOOSEST)
        if self.peek().text != "?":
            return condition
        self.take()
        return self.inside(lambda: self.choice(condition))

    def choice(self, condition: Node) -> Node:
        then = self.expression()
        self.expect(":")
        return Choice(condition, then, self.expression())

    def binary(self, loosest: int) -> Node:
        """Levels 3 to 10: a value, and every operator after it that binds at least as
        tightly as `loosest`. Operators of one level group from the left."""
        left = self.signed()
        while (level := LEVELS.get(self.peek().text, LOOSEST + 1)) <= loosest:
            op = self.take().text
            left = Binary(op, left, self.binary(level - 1))
        return left

    def signed(self) -> Node:
        """Level 2: -x and ~x."""
        if self.peek().text in SIGNS:
            op = self.take().text
            return self.inside(lambda: Unary(op, self.signed()))
        return self.value()

    def value(self) -> Node:
        """Level 1: a number, a name, a function call, brackets."""
        token = self.take()
        if token.kind == "number":
            return Number(token.value)
        if token.kind == "name":
            return self.named(token.text)
        if token.text == "(":
            return self.inside(self.bracketed)
        raise _unexpected(token)

    def bracketed(self) -> Node:
        inner = self.expression()
        self.expect(")")
        return inner

    def named(self, name: str) -> Node:
        called = self.peek().text == "("
        if name in FUNCTIONS:
            if not called:
                raise ExprError(f"{name} is a function: write {name}(...)")
            self.take()
            return self.inside(lambda: self.call(name))
        if called and name in self.names:
            raise ExprError(f"{name} is a name, not a function: to multiply, write "
                            f"{name} * (...)")
        if called:
            raise ExprError(f"unknown function {name}: there are {', '.join(FUNCTIONS)}")
        if name not in self.names:
            raise ExprError(f"unknown name {name}")
        return Name(name)

    def call(self, function: str) -> Node:
        """A function's values, up to its closing bracket; the opening one is taken."""
        args = []
        if self.peek().text == ")":
            self.take()
        else:
            args.append(self.expression())
            while self.peek().text == ",":
                self.take()
                args.append(self.expression())
            self.expect(")")
        if len(args) != (takes := FUNCTIONS[function]):
            raise ExprError(f"{function} takes {takes} value{'s' * (takes != 1)}, "
                            f"not {len(args)}")
        return Call(function, tuple(args))
