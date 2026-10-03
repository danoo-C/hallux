# Step 6: the panel at the shell

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), sections 3
and 8

**Needs:** step 5. **Changes:** `hallux/terminal.py`, `hallux/machine.py`, `hallux/app.py`,
`tests/test_terminal.py`, `tests/test_machine.py`.

**Before this step:** the user runs `cat -v` in the terminal Hallux runs in and presses
Ctrl+F12. `^[[24;5~` should appear. If nothing does, another key is chosen first.

From this step on Ctrl+F12 opens the panel at the shell prompt, at a password prompt and
while the AI answers. In a full-screen program it does nothing yet; that is step 7.

## Build

**The terminal is handed the panel.** `app.py` builds the machine first, then the panel
from the machine's `view`, `change` and `save`, the bar and the terminal's two hard-exit
functions, and gives it to the terminal. A terminal without a panel ignores the key: the
tests that exist build one that way.

**Opening it,** by where the machine is:

| The machine is | How |
|---|---|
| At the shell prompt | The key ends the prompt the way Tab does: the prompt line is erased. The terminal shows the panel, then reads the line again, starting with what you had typed |
| At a password prompt | The same, and nothing you had typed is carried over |
| Answering | The reader that watches the keyboard while the AI works sees the key and shows the panel |
| In a full-screen program | Nothing yet |

**Showing it:**

1. The bar's scroll region is taken off, as before a full-screen program
   (`hallux/terminal.py:259`).
2. From here on `write` doesn't print: it keeps the text, in order. The bar isn't drawn onto
   the shell's screen, and a change of the bar redraws the panel, whose last row it is.
3. `panel.run()` shows the panel on the alternate screen until it is closed.
4. The bar is pinned again, for the size the window has now.
5. The kept text is printed.

**The wait.** When the AI's answer ends and the panel is open, the end of the answer waits
until the panel is closed. It is in `busy()`, before the reader lets go of the keyboard.

- **Why there:** everything that follows an answer waits with it: the screen it wrote, a
  full-screen program it starts, the next prompt, a halt, a reboot. And the keyboard is let
  go in the right order. The check of 2026-10-03 showed what happens otherwise: the panel
  gets no key any more.
- **The bar stops spinning when the answer ends,** not when the panel closes.
- **The cost is on the bar at once.** Today the machine puts an answer's cost on the bar
  after `busy()` has ended (`hallux/machine.py:475-480`). It moves to where the result
  arrives, inside the answer.
- **Ctrl-C in the panel doesn't interrupt the AI.** It only counts for the hard exit.

**An event from an addon, while the panel is open at the prompt.** The machine asks the
terminal to end the prompt. The terminal says yes and remembers it. When the panel closes,
`read_line` returns what an event makes it return today, with the line you had typed.

**Keys you type in the panel are the panel's.** What you typed before it opened, while the
AI was working, still waits for the next prompt.

## Tests

In `tests/test_terminal.py`, on a pipe, with a real panel around fake functions. What the
terminal writes is recorded.

- at the prompt: `ls -l`, Ctrl+F12, Esc, `a`, Enter gives the line `ls -la`, and the panel
  was shown once;
- at a password prompt: some keys, Ctrl+F12, Esc, a password, Enter gives only the password;
- a terminal without a panel: the key does nothing, and the line is what was typed;
- while the AI works: the key shows the panel; what is written meanwhile isn't printed; after
  Esc it is printed, in the order it was written;
- **the exact screen:** the same writes, once with a visit to the panel in the middle and
  once without, give the same recorded output;
- the answer ends first: the `busy()` block doesn't end while the panel is open, and ends
  when it closes. A key typed after that goes to the next prompt;
- the panel closes first: Ctrl-C after that still interrupts the AI;
- keys typed before the panel opened are still there for the next prompt; keys typed in the
  panel aren't;
- an event while the panel is open at the prompt: `interrupt_prompt` says yes, nothing
  happens until the panel closes, and then `read_line` returns the typed line as
  `Interrupted`;
- the hard exit key works inside the panel.

In `tests/test_machine.py`:

- the cost of an answer is on the bar before the answer's `busy()` ends.

## Done when

The tests pass, and the user has tried it by hand in a test world:

- at the prompt, with half a line typed: Ctrl+F12, Esc, and the line is there;
- during a long answer, such as a long listing: Ctrl+F12, wait, Esc. The screen holds the
  whole answer, and scrolling back in the terminal shows what was there before.

I can't see a real terminal, so this part is the user's.
