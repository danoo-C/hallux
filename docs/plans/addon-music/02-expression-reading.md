# Step 2: reading an expression

[The plan](README.md) · the design: [addon-music.md](../../addon-music.md), section 3

**Needs:** nothing. **Makes:** `addons/music_engine/__init__.py`, `limits.py`, `expr.py`,
`tests/test_music_expr.py`. **Changes:** `pyproject.toml`.

An instrument's expression is text from the AI. This step turns it into a tree, and refuses
everything the design doesn't allow. It computes nothing, and it needs no numpy.

## Build

**The start of the package:**
- **`pyproject.toml`** gets `music = ["numpy", "pygame"]` under the optional installs, and
  `.venv/bin/python -m pip install -e ".[music]"` puts numpy into the venv. pygame is there.
- **`addons/music_engine/__init__.py`** holds only a docstring that says what the package is.
- **`limits.py`** holds the limits as named numbers. This step adds two: the longest
  expression, and the deepest nesting. The numbers are in step 6.
- **The tests reach the package** through `addons/` on `sys.path`, set up in one place,
  `tests/conftest.py`.

**`expr.py` has one function, `read(text, names)`.** `names` are the names this expression
may use. It returns the tree, or raises `ExprError` with a message for the AI.

**What it accepts,** tightest first. It is C's order:

| Level | What |
|---|---|
| 1 | A number, a name, a function call, brackets |
| 2 | `-x`, `~x` |
| 3 | `*`, `/`, `%` |
| 4 | `+`, `-` |
| 5 | `<<`, `>>` |
| 6 | `<`, `<=`, `>`, `>=` |
| 7 | `==`, `!=` |
| 8 | `&` |
| 9 | `^` |
| 10 | `\|` |
| 11 | `a ? b : c`, grouped from the right |

- **Numbers** are whole: decimal, or hexadecimal with `0x`. One that doesn't fit 64 bits is
  refused.
- **Functions** are checked by name and by the number of arguments: `sin`, `saw`, `square`,
  `tri`, `noise` and `abs` take one; `decay`, `min` and `max` take two.
- **A name** has to be in `names`. The score reader (step 4) passes `t`, `p`, `vel`, `dur`,
  `key`, the declared variables, and the named parts above the line.

**The tree** is made of six kinds of node: a number, a name, a unary operation, a binary
operation, a choice (`? :`), and a call. Step 3 walks it.

**The problems,** each with a message that says what to write:

| The AI wrote | Message |
|---|---|
| A name that isn't known | `unknown name CUTOF` |
| A function that isn't known | `unknown function cos: there are sin, saw, square, tri, noise, decay, min, max, abs` |
| The wrong number of arguments | `decay takes 2 values, not 1` |
| `&&` or `\|\|` | `&& isn't an operator here: use & between comparisons` |
| `!x` | `! isn't an operator here: write x == 0` |
| `**` | `** isn't an operator here: multiply` |
| `0.5` | `whole numbers only: multiply first, then divide` |
| A function's name without brackets, or a name with them | `sin is a function: write sin(...)` |
| Brackets that don't close, or an operator with nothing after it | `the expression ends too early`, or `unexpected )` |
| Anything else that isn't allowed | `unexpected character: $` |
| Too long, or nested too deep | `the expression is longer than N characters` |

One problem per expression is enough. The score reader collects them across the lines.

## Tests

- every level of the table binds as it should, against a helper that prints a tree with all
  its brackets;
- the two traps of the design: `x * vel >> 8 * VOL >> 8` shifts by `8 * VOL`, and
  `p & 65535 - 32768` is `p & (65535 - 32768)`;
- `a ? b : c ? d : e` groups from the right; `-x * y`; `~x & y`; `0xFFFF` is 65535;
- every row of the problems table;
- both limits;
- every expression in the design's section 3 and section 5 reads without a problem.

## Done when

Every recipe of the design reads into a tree, and each row of the problems table gives its
message.

## As built

Built on 2026-10-02. numpy 2.5.3 is in the venv. Decided while building:

- **A number fits 64 bits when it is below 2^64.** From 2^63 up it wraps around, as everything
  does in the arithmetic, so `0xFFFFFFFFFFFFFFFF` is -1 and works as a mask. The tree holds
  the wrapped number.
- **A number that starts with 0 is refused,** apart from `0` itself and `0x…`. `017` is 15 in
  C and 17 to a reader, so it is neither: `can't read the number 017: a number doesn't start
  with 0`. A number that runs into letters, such as `1e3` or `2p`, is
  `can't read the number 1e3: write it in decimal, or in hexadecimal with 0x`.
- **What counts as nesting:** brackets, a function's brackets, a sign (`-x`, `~x`) and a
  choice inside a choice. A long chain such as `a + b + c + …` isn't nesting.
- **Three more problems that teach,** beside those of the table:

| The AI wrote | Message |
|---|---|
| `//` | `// isn't an operator here: / already gives a whole number` |
| `>>>` | `>>> isn't an operator here: use >>, which keeps the sign` |
| `=` | `= isn't an operator here: a comparison is ==` |

- **A name with brackets has its own message:**
  `vel is a name, not a function: to multiply, write vel * (...)`.
- **Nothing at all** is `the expression is empty`.
- **A sign in front that isn't `-` or `~`,** such as `+x`, is `unexpected +`.
- **The length is checked first,** before anything of the text is read.
- **`expr.NAMES`** holds what every note gives its expression: `t`, `p`, `vel`, `dur`, `key`.
  The score reader adds the variables and the named parts.
