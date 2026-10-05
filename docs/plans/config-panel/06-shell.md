# Step 6: the panel at the shell

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), sections 3
and 8

**Needs:** step 5. **Changes:** `hallux/terminal.py`, `hallux/machine.py`, `hallux/app.py`,
`tests/test_terminal.py`, `tests/test_machine.py`.

**The check before this step is done.** On 2026-10-04 the user ran `cat -v` in their
terminal and pressed Ctrl+F12, and `^[[24;5~` appeared. So the key stands.

From this step on Ctrl+F12 opens the panel at the shell prompt, at a password prompt and
while the AI answers. A full-screen program is step 7: until then the key does nothing in a
program with fields, and in a raw-mode program it still goes to the AI like every key
(`hallux/blockmode.py:450`).

## Build

**The terminal is handed the panel.** `app.py` builds the machine first, then the Config
tab from the machine's `view`, `change`, `save` and `refill`, then the panel around that
one tab,
with the bar and the terminal's two hard-exit functions, and gives it to the terminal. A
terminal without a panel ignores the key: the tests that exist build one that way.

**Opening it,** by where the machine is:

| The machine is | How |
|---|---|
| At the shell prompt | The key ends the prompt the way Tab does: the prompt line is erased. The terminal makes a visit to the panel, then reads the line again, starting with what you had typed |
| At a password prompt | The same, and nothing you had typed is carried over |
| Answering | The reader that watches the keyboard while the AI works sees the key and starts a visit |

- **The password prompt has to forget that it was erased.** `read_line` sets
  `erase_when_done` back at every read (`hallux/terminal.py:125`); `read_secret` doesn't
  (`hallux/terminal.py:142-144`). Without the same line there, every password prompt after
  one Ctrl+F12 would be erased on Enter.

**A visit to the panel** is one function of the terminal, and it is over when that function
returns:

1. **The type-ahead is taken out.** Every prompt_toolkit app feeds itself the keys that were
   stored for the next prompt when it starts
   (`prompt_toolkit/application/application.py:672`), and the terminal stores what you
   typed while the AI worked (`hallux/terminal.py:235`). When two answers run back to back,
   those keys are still stored, and the panel would get them: an Enter there presses a
   button. So the terminal takes them out first.
2. The bar's scroll region is taken off, as before a full-screen program
   (`hallux/terminal.py:259`).
3. From here on `write` doesn't print: it keeps the text, in order. The bar isn't drawn onto
   the shell's screen, and a change of the bar redraws the panel, whose last row it is.
4. `panel.run()` shows the panel on the alternate screen until it is closed, and returns
   when its app has ended.
5. The bar is pinned again for the size the window has now, with what a resize does today
   (`hallux/terminal.py:326-335`).
6. The kept text is printed.
7. The type-ahead is put back.

**The wait.** When the AI's answer ends and a visit is under way, the end of the answer
waits until the visit is over. It is in `busy()`, before the reader lets go of the keyboard.

- **For the whole visit, not for the key that closes the panel.** `panel.wait_closed()`
  returns when the key is handled. The panel's app is still up then, and so is its hold on
  the keyboard. If `busy()` went on at that moment, its own reader would be left attached
  for good, and the next prompt would lose keys
  (`prompt_toolkit/input/vt100.py:186-196`). The machine would also print onto the
  alternate screen. So `busy()` waits for the terminal's visit: steps 1 to 7.
- **Why there:** everything that follows an answer waits with it: the screen it wrote, what
  it takes back, a full-screen program it starts, the next prompt, a halt, a reboot.
- **The bar stops spinning when the answer ends,** not when the panel closes.
- **The cost is on the bar at once.** Today the machine puts an answer's cost on the bar
  after `busy()` has ended (`hallux/machine.py:475-480`). It moves to where the result
  arrives, inside the answer.
- **Ctrl-C in the panel doesn't interrupt the AI.** It only counts for the hard exit.

**An event from an addon, while the panel is open at the prompt.** The machine asks the
terminal to end the prompt. The terminal says yes and remembers it. When the visit is over,
`read_line` returns what an event makes it return today, with the line you had typed.

**Keys you type in the panel are the panel's.** What you typed before it opened, while the
AI was working, still waits for the next prompt.

**Changes that aren't saved** are for this run. A halt and the hard exit lose them without
a word; the panel's foot has said how many there are.

## Tests

In `tests/test_terminal.py`, on a pipe, with a real panel around fake functions. What the
terminal writes is recorded.

- at the prompt: `ls -l`, Ctrl+F12, Esc, `a`, Enter gives the line `ls -la`, and the panel
  was shown once;
- at a password prompt: some keys, Ctrl+F12, Esc, a password, Enter gives only the password;
  the next password prompt isn't erased when it is answered;
- a terminal without a panel: the key does nothing, and the line is what was typed;
- while the AI works: the key shows the panel; what is written meanwhile isn't printed; after
  Esc it is printed, in the order it was written;
- **the exact screen:** the same writes, once with a visit to the panel in the middle and
  once without, give the same recorded output;
- **two answers back to back:** `ls` and Enter are typed during the first; the panel is
  opened during the second. The panel gets none of those keys, and after it the next prompt
  reads `ls`;
- the answer ends first: the `busy()` block doesn't end while the visit lasts, and ends when
  it is over. Keys typed right after that go to the next prompt, all of them;
- the panel closes first: Ctrl-C after that still interrupts the AI;
- keys typed in the panel don't reach the next prompt;
- an event while the panel is open at the prompt: `interrupt_prompt` says yes, nothing
  happens until the visit is over, and then `read_line` returns the typed line as
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

## As built

Built on 2026-10-05, on the branch `config-panel`. 15 new tests, 1035 in all; every old test
passes as it was. **The user tried it by hand on 2026-10-05,** in their test world. The
first try found the bug below; after the fix: "now it works perfectly".

Decided while building:

- **`Terminal.set_panel(panel)`** hands the panel over. `app.py` builds the machine, then
  the Config tab around it, then the panel, as the step says.
- **A prompt that Ctrl+F12 ended returns a mark of its own,** with the line as it was typed.
  `read_line` and `read_secret` each read again after the visit. The line comes back with
  the cursor at its end, as after Tab.
- **Whose a key is,** when keys come in one burst: what is typed behind Ctrl+F12 is the
  panel's, and what is typed behind the key that closed the panel is the shell's. So
  `ls -l`, Ctrl+F12, Esc, `a`, Enter typed in one go gives `ls -la`.
- **At a prompt, the stored keys are the panel's.** The prompt took what was stored when it
  started, so whatever is stored when Ctrl+F12 ends it was typed behind that key. While the
  AI works it is the other way round: what is stored was typed for the shell during an
  earlier answer, and is taken out for the visit.
- **`visit_panel(keys)` is the one function a visit is,** and returns the keys typed behind
  the closing key. During an answer they join the keys typed for the next prompt, in the
  order they were typed.
- **While a visit lasts, `write` keeps the text in a list.** The same list being there is
  how the terminal knows a visit is on: the bar isn't drawn, a resize does nothing, and a
  change of the bar draws the panel again.
- **A window that changes its size during a visit** is handled when the visit is over: the
  bar's old row is wiped and the bar is pinned for the new size.
- **`busy()` stops the bar's light, then waits for the visit,** and only then forgets how
  to interrupt the answer and stores the typed keys.
- **An event while the panel is open over the prompt:** `interrupt_prompt` says yes and
  remembers it. After the visit `read_line` returns `Interrupted` with the line and the
  cursor as they were. At a password prompt nothing asks, as before.
- **A second Ctrl+F12 while a visit is starting** is typed for the shell. It does nothing
  there.
- **If the panel's app fails,** the error ends Hallux with its message, as any crash does.
  The screen is given back first.
- **The machine counts an answer's cost where the result arrives,** inside the busy period.
  `last_turn_cost` is what the log line uses afterwards.

**A bug the user found on the first try,** fixed the same day. The panel was opened during
the boot. After it closed, a copy of the bar stood in the middle of the boot's text, and
the prompt was drawn on the bar's own row until Enter was pressed.

- **The cause:** after a visit the kept text was printed first, and the bar's region was
  pinned after that. With the region off, the text scrolled the whole screen. The bar's
  row went up with it, and the cursor ended on the last row, where the bar is drawn.
- **The fix:** the region is pinned and the bar drawn before the first kept line is
  printed, and each line goes through `write`, as it would have without a visit.
- **Why no test caught it:** on a pipe the terminal pins nothing, and the one test that
  set a size by hand also changed it, which pins the region early by another way. A test
  now holds the order for a window that keeps its size.

**Checked on a pseudo-terminal, with a terminal emulator drawing the screen** (pyte, 24
rows by 80). The real terminal, the bar pinned, a machine, and a pretend model that writes
slowly. No model call. A throwaway script types the keys; after each visit it looks at the
screen as a terminal would show it.

| The visit | The screen afterwards |
|---|---|
| Ctrl+F12 during the boot, Esc after the boot has ended | The 12 lines of the boot, the prompt under them, the bar on the last row only |
| Half a line typed, Ctrl+F12, Esc | The same screen, and the prompt with the half line. The AI then gets the whole line |
| Ctrl+F12 after 7 lines of a listing of 20, Esc after it has ended | All 20 lines in order, the prompt on the row above the bar, the bar on the last row only |

Run against the code as it was before the fix, the same script reports what the user saw:
the bar on two rows, and the listing's last line gone under it.

**What that can't show** is the user's own terminal program. The user's try covered that.

**`tests/panel_demo.py` is still there.** It shows the panel without a model call. It can
go once the real one has been tried.
