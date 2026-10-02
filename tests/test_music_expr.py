"""Reading an instrument's expression: addons/music_engine/expr.py. Nothing here computes,
and nothing needs numpy."""
import pytest
from music_engine import expr, limits
from music_engine.expr import Binary, Call, Choice, ExprError, Name, Number, Unary

LETTERS = ("a", "b", "c", "d", "e", "x", "y")


def read(text, *more):
    """Read with the names every note has, some letters, and whatever the test adds."""
    return expr.read(text, expr.NAMES + LETTERS + more)


def show(node):
    """A tree as text, with every bracket written out."""
    match node:
        case Number(value):
            return str(value)
        case Name(name):
            return name
        case Unary(op, value):
            return f"({op}{show(value)})"
        case Binary(op, left, right):
            return f"({show(left)} {op} {show(right)})"
        case Choice(condition, then, otherwise):
            return f"({show(condition)} ? {show(then)} : {show(otherwise)})"
        case Call(function, args):
            return f"{function}({', '.join(show(arg) for arg in args)})"


def problem(text, *more):
    with pytest.raises(ExprError) as raised:
        read(text, *more)
    return str(raised.value)


# ---------------------------------------------------------------- the tree

def test_the_tree_has_six_kinds_of_node():
    assert read("7") == Number(7)
    assert read("vel") == Name("vel")
    assert read("-x") == Unary("-", Name("x"))
    assert read("x >> 8") == Binary(">>", Name("x"), Number(8))
    assert read("a ? b : c") == Choice(Name("a"), Name("b"), Name("c"))
    assert read("decay(t, 900)") == Call("decay", (Name("t"), Number(900)))
    assert read("sin(p) * vel >> 8") == Binary(
        ">>", Binary("*", Call("sin", (Name("p"),)), Name("vel")), Number(8))


def test_spaces_dont_matter():
    assert read("sin(p)*vel>>8") == read("  sin ( p ) *\tvel  >>  8  ")


# ---------------------------------------------------------------- how tightly things bind

@pytest.mark.parametrize("text, tree", [
    # one level groups from the left
    ("a * b / c % d", "(((a * b) / c) % d)"),
    ("a - b + c - d", "(((a - b) + c) - d)"),
    ("a << b >> c", "((a << b) >> c)"),
    ("a < b <= c > d >= e", "((((a < b) <= c) > d) >= e)"),
    ("a == b != c", "((a == b) != c)"),
    ("a & b & c", "((a & b) & c)"),
    ("a ^ b ^ c", "((a ^ b) ^ c)"),
    ("a | b | c", "((a | b) | c)"),
    # each level binds tighter than the one below it, on either side
    ("-a * b", "((-a) * b)"), ("a * -b", "(a * (-b))"), ("~a * b", "((~a) * b)"),
    ("a + b * c", "(a + (b * c))"), ("a / b - c", "((a / b) - c)"), ("a - b % c", "(a - (b % c))"),
    ("a << b + c", "(a << (b + c))"), ("a - b >> c", "((a - b) >> c)"),
    ("a < b << c", "(a < (b << c))"), ("a >> b >= c", "((a >> b) >= c)"),
    ("a == b < c", "(a == (b < c))"), ("a > b != c", "((a > b) != c)"),
    ("a & b == c", "(a & (b == c))"), ("a != b & c", "((a != b) & c)"),
    ("a ^ b & c", "(a ^ (b & c))"), ("a & b ^ c", "((a & b) ^ c)"),
    ("a | b ^ c", "(a | (b ^ c))"), ("a ^ b | c", "((a ^ b) | c)"),
    ("a | b ? c | d : e | x", "((a | b) ? (c | d) : (e | x))"),
    # all of them at once, loosest first and tightest first
    ("a | b ^ c & d == e < x << y + a * -b",
     "(a | (b ^ (c & (d == (e < (x << (y + (a * (-b)))))))))"),
    ("-a * b + c << d < e == x & y ^ a | b",
     "(((((((((-a) * b) + c) << d) < e) == x) & y) ^ a) | b)"),
    # brackets
    ("(a + b) * c", "((a + b) * c)"), ("a * (b + c)", "(a * (b + c))"), ("((a))", "a"),
    ("-(a + b)", "(-(a + b))"), ("~a & b", "((~a) & b)"), ("- -a", "(-(-a))"), ("-~a", "(-(~a))"),
])
def test_every_level_binds_as_in_c(text, tree):
    assert show(read(text)) == tree


def test_the_two_traps_of_the_design():
    assert show(read("x * vel >> 8 * y >> 8")) == "(((x * vel) >> (8 * y)) >> 8)"
    assert show(read("p & 65535 - 32768")) == "(p & (65535 - 32768))"
    assert show(read("x * vel * y >> 16")) == "(((x * vel) * y) >> 16)"        # what to write
    assert show(read("(p & 65535) - 32768")) == "((p & 65535) - 32768)"


def test_a_choice_groups_from_the_right():
    assert show(read("a ? b : c ? d : e")) == "(a ? b : (c ? d : e))"
    assert show(read("a ? b ? c : d : e")) == "(a ? (b ? c : d) : e)"
    assert show(read("a < b ? c + 1 : d | e")) == "((a < b) ? (c + 1) : (d | e))"
    assert show(read("(a ? b : c) ? d : e")) == "((a ? b : c) ? d : e)"
    assert show(read("a + (b ? c : d)")) == "(a + (b ? c : d))"


# ---------------------------------------------------------------- numbers, names, functions

def test_numbers_are_whole_decimal_or_hexadecimal():
    assert read("0") == Number(0) and read("65535") == Number(65535)
    assert read("0xFFFF") == Number(65535) and read("0Xff") == Number(255)
    assert read("-32768") == Unary("-", Number(32768))


def test_a_number_fits_64_bits_and_wraps_from_the_sign_bit_up():
    assert read("9223372036854775807") == Number(2 ** 63 - 1)
    assert read("9223372036854775808") == Number(-2 ** 63)
    assert read("0xFFFFFFFFFFFFFFFF") == Number(-1) == read("18446744073709551615")
    assert problem("18446744073709551616") == "the number 18446744073709551616 doesn't fit 64 bits"
    assert problem("0x10000000000000000") == "the number 0x10000000000000000 doesn't fit 64 bits"


def test_a_name_has_to_be_one_the_expression_may_use():
    assert expr.read("t + p + vel + dur + key", expr.NAMES)
    assert expr.read("VOL", ["VOL"]) == Name("VOL")
    assert problem("VOL") == "unknown name VOL"
    assert problem("vol", "VOL") == "unknown name vol"                  # the case counts
    with pytest.raises(ExprError, match="unknown name t"):
        expr.read("t", [])


def test_the_functions_and_how_many_values_each_takes():
    assert list(expr.FUNCTIONS) == ["sin", "saw", "square", "tri", "noise", "decay", "min",
                                    "max", "abs"]
    for function, takes in expr.FUNCTIONS.items():
        args = ", ".join(["t", "p"][:takes])
        assert read(f"{function}({args})") == Call(function, (Name("t"), Name("p"))[:takes])
    assert show(read("min(a, max(b, abs(c - d)))")) == "min(a, max(b, abs((c - d))))"
    assert show(read("sin(a ? b : c)")) == "sin((a ? b : c))"


# ---------------------------------------------------------------- the problems

@pytest.mark.parametrize("text, message", [
    ("sin(p) * CUTOF >> 8", "unknown name CUTOF"),
    ("cos(p)",
     "unknown function cos: there are sin, saw, square, tri, noise, decay, min, max, abs"),
    ("decay(t)", "decay takes 2 values, not 1"),
    ("decay(t, 900, 2)", "decay takes 2 values, not 3"),
    ("sin(p, t)", "sin takes 1 value, not 2"),
    ("noise()", "noise takes 1 value, not 0"),
    ("a > 0 && b > 0", "&& isn't an operator here: use & between comparisons"),
    ("a > 0 || b > 0", "|| isn't an operator here: use | between comparisons"),
    ("!a", "! isn't an operator here: write x == 0"),
    ("a ** 2", "** isn't an operator here: multiply"),
    ("a // 2", "// isn't an operator here: / already gives a whole number"),
    ("a >>> 2", ">>> isn't an operator here: use >>, which keeps the sign"),
    ("a = 2", "= isn't an operator here: a comparison is =="),
    ("sin(p) * 0.5", "whole numbers only: multiply first, then divide"),
    ("sin(p) * .5", "whole numbers only: multiply first, then divide"),
    ("sin(p) * 2.", "whole numbers only: multiply first, then divide"),
    ("1e3", "can't read the number 1e3: write it in decimal, or in hexadecimal with 0x"),
    ("2p", "can't read the number 2p: write it in decimal, or in hexadecimal with 0x"),
    ("0xFG", "can't read the number 0xFG: write it in decimal, or in hexadecimal with 0x"),
    ("1_000", "can't read the number 1_000: write it in decimal, or in hexadecimal with 0x"),
    ("017", "can't read the number 017: a number doesn't start with 0"),
    ("sin + 1", "sin is a function: write sin(...)"),
    ("decay", "decay is a function: write decay(...)"),
    ("vel(2)", "vel is a name, not a function: to multiply, write vel * (...)"),
    ("(a + b", "the expression ends too early"),
    ("sin(p", "the expression ends too early"),
    ("a +", "the expression ends too early"),
    ("a ? b", "the expression ends too early"),
    ("-", "the expression ends too early"),
    ("a + b)", "unexpected )"),
    ("()", "unexpected )"),
    ("sin(p,)", "unexpected )"),
    ("a b", "unexpected b"),
    ("a 2", "unexpected 2"),
    ("2 (a)", "unexpected ("),
    ("a * / b", "unexpected /"),
    ("+a", "unexpected +"),
    ("a, b", "unexpected ,"),
    ("a : b", "unexpected :"),
    ("a ? b ? c", "the expression ends too early"),
    ("a $ b", "unexpected character: $"),
    ("a # loud", "unexpected character: #"),
    ("Math.sin(p)", "unexpected character: ."),
    ("a.b", "unexpected character: ."),
    ("a[0]", "unexpected character: ["),
    ("Größe", "unexpected character: ö"),
    ("_a", "unexpected character: _"),
    ("", "the expression is empty"),
    ("   ", "the expression is empty"),
])
def test_a_problem_says_what_to_write(text, message):
    assert problem(text) == message


def test_not_equal_is_not_the_missing_not():
    assert read("a != b") == Binary("!=", Name("a"), Name("b"))
    assert read("a!=-b") == Binary("!=", Name("a"), Unary("-", Name("b")))
    assert read("a<=b") == Binary("<=", Name("a"), Name("b"))
    assert read("a==b") == Binary("==", Name("a"), Name("b"))


def test_the_first_problem_is_the_one_reported():
    assert problem("CUTOF + cos(p)") == "unknown name CUTOF"
    assert problem("cos(CUTOF)") == "unknown function cos: there are " + ", ".join(expr.FUNCTIONS)


# ---------------------------------------------------------------- the limits

def test_an_expression_has_a_longest_length():
    fits = "t + " * 124 + "vel"
    assert len(fits) + 1 == limits.EXPRESSION_CHARS == 500
    assert read(fits + " ") and len(fits + " ") == limits.EXPRESSION_CHARS
    assert problem(fits + "  ") == "the expression is longer than 500 characters"
    assert problem("$" * 501) == "the expression is longer than 500 characters"   # checked first


@pytest.mark.parametrize("deep, too_deep", [
    (lambda n: "(" * n + "t" + ")" * n, "brackets"),
    (lambda n: "abs(" * n + "t" + ")" * n, "calls"),
    (lambda n: "-" * n + "t", "signs"),
    (lambda n: "~-" * (n // 2) + "-" * (n % 2) + "t", "mixed signs"),
    (lambda n: "t ? p : " * n + "vel", "choices"),
    (lambda n: "t ? " * n + "vel" + " : p" * n, "choices in the middle"),
    (lambda n: "-(" * (n // 2) + "-" * (n % 2) + "t" + ")" * (n // 2), "signs and brackets"),
])
def test_an_expression_has_a_deepest_nesting(deep, too_deep):
    assert limits.EXPRESSION_DEPTH == 40
    assert read(deep(40))
    assert problem(deep(41)) == "the expression is nested more than 40 deep", too_deep


def test_a_long_chain_isnt_nesting():
    assert read("t" + " + t" * 120)
    assert read(" | ".join(["t ^ p & vel == dur < key << t + p * -vel"] * 10))


# ---------------------------------------------------------------- the design's own expressions

# Every expression of docs/addon-music.md, sections 2, 3 and 5: the variables it needs, and
# the instrument's lines. A line with a name in front is a named part.
DESIGN = [
    # section 2, the sketch
    (["VOL"], ["sin(p) * vel * VOL >> 16"]),
    ([], ["(saw(p) + sin(p >> 1)) >> 1"]),
    # section 3, the text
    ([], ["sin(p) * decay(t, 5000) >> 16"]),
    ([], ["saw(p * 2)"]),
    ([], ["saw(p + (p >> 8))"]),
    ([], ["env = decay(t, 14000)",
          "mod = sin(p * 7 >> 1) * decay(t, 9000) >> 16",
          "sin(p + mod) * env * vel >> 24"]),
    (["x", "VOL"], ["x * vel >> 8 * VOL >> 8"]),
    (["x", "VOL"], ["x * vel * VOL >> 16"]),
    ([], ["p & 65535 - 32768"]),
    # section 3, the recipes
    ([], ["sin(p)"]),
    ([], ["sin(p >> 1)"]),
    ([], ["sin(p << 1)"]),
    ([], ["saw(p)"]),
    ([], ["(p & 65535) - 32768"]),
    ([], ["square(p)"]),
    ([], ["tri(p)"]),
    ([], ["(saw(p) + sin(p)) >> 1"]),
    ([], ["(saw(p) + saw(p + (p >> 8)) + saw(p - (p >> 8))) / 3"]),
    ([], ["sin(p) * vel >> 8"]),
    ([], ["sin(p) * (dur - t) / dur"]),
    ([], ["sin(p) * max(22050 - t, 0) / 22050"]),
    ([], ["sin(p) * decay(t, 5000) * vel >> 24"]),
    ([], ["sin(p) * decay(t, 3000 + (96 - key) * 60) * vel >> 24"]),
    ([], ["sin(p + (sin(t * 8) * min(t, 22050) / 22050 >> 2)) * vel >> 8"]),
    ([], ["sin(p + (sin(p * 7 >> 1) * decay(t, 9000) >> 16)) * decay(t, 14000) * vel >> 24"]),
    ([], ["sin(p + (sin(p) * decay(t, 3000 + (96 - key) * 60) * vel >> 25)) * decay(t, 16000) "
          "* vel >> 24"]),
    ([], ["sin(p + (65536 - decay(t, 900)) * 5) * decay(t, 5000) * vel >> 24"]),
    ([], ["(noise(t) * decay(t, 2200) + sin(p + (65536 - decay(t, 500)) * 2) * decay(t, 1500)) "
          "* vel >> 25"]),
    ([], ["(noise(t) - noise(t - 1)) * decay(t, 600) * vel >> 25"]),
    ([], ["noise(t) * decay(t, 2200) >> 16"]),
    # section 3, below the recipes
    (["formula"], ["((formula & 255) - 128) << 8"]),
    ([], ["t * 80 / 441"]),
    ([], ["(noise(t) + noise(t - 1)) >> 1"]),
    ([], ["sin(p + (sin(p) >> 1))"]),
    (["x"], ["saw(p + x)"]),
    ([], ["sin(p) * ((dur - t) / dur)"]),
    ([], ["env = min(t, 4000) * decay(t - dur, 6000) >> 12",
          "(saw(p) + saw(p + (p >> 8)) + saw(p - (p >> 8))) * env * vel >> 26"]),
    # section 5, the three scores
    ([], ["(saw(p) + sin(p)) * vel >> 9"]),
    (["VOL", "BRIGHT"], ["(saw(p) * BRIGHT + sin(p) * (255 - BRIGHT)) * vel * VOL >> 24"]),
    ([], ["body = sin(p + (65536 - decay(t, 500)) * 2) * decay(t, 1500)",
          "hiss = noise(t) * decay(t, 2200)",
          "(body + hiss) * vel >> 25"]),
]


@pytest.mark.parametrize("variables, lines", DESIGN, ids=[lines[-1][:40] for _, lines in DESIGN])
def test_every_expression_of_the_design_reads(variables, lines):
    names = list(expr.NAMES) + variables
    for line in lines[:-1]:                              # a part may use the parts above it
        name, _, text = line.partition(" = ")
        assert expr.read(text, names)
        names.append(name)
    assert expr.read(lines[-1], names)


def test_a_part_cant_be_used_above_its_line():
    with pytest.raises(ExprError, match="unknown name mod"):
        expr.read("sin(p + mod)", expr.NAMES + ("env",))
