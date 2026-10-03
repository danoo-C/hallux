# Step 8: the bar, the documentation and the live run

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), section 3 and
"Still to find out"

**Needs:** steps 4 and 7. **Changes:** `hallux/statusbar.py`, `hallux/machine.py`,
`tests/test_statusbar.py`, `README.MD`, `docs/`.

The panel works by now, but nothing tells you that it exists. This step puts the key on the
bar, writes the documentation, and ends with the run in a real terminal that the tests
can't replace.

## Build

**The idle hint** names the key: `config: ctrl+f12 · power off: ctrl+shift+del · ctrl+c ×3`.

- **On a narrow window the hint loses parts from the end,** whole ones: first the triple
  Ctrl-C, then the power key. Today a hint that is too long is cut in the middle of a word.
  At 80 columns the whole hint doesn't fit beside the model and the cost.
- **The note of a used-up budget per boot** (step 3) gets the key:
  `budget used: $2.00 per boot · raise it: ctrl+f12`.

**The documentation:**

| File | What changes |
|---|---|
| `README.MD`, "Keys" | A row for Ctrl+F12 |
| `README.MD`, "Configuration" | The panel; a table of what changes at once, at the next reboot and at the start; that Save keeps the file's comments |
| `README.MD`, "Cost and speed" | A budget can be raised while the machine runs |
| `docs/concept.md`, principle 1 | It names two things on the screen that aren't the AI's. The panel is a third |
| `docs/concept.md`, "Configuration: model and effort" | It says that changing the hardware means rebooting, and that a switch inside a running session would break the first principle. With the panel that is no longer so: the paragraph says what the panel does, and why it doesn't break the principle |
| `hallux/machine.py`, the docstring | It names the bar as the one exception. Now there are two |
| `docs/roadmap.md` | An entry for the panel |
| `docs/config-panel.md`, this plan | The status lines |

## Tests

In `tests/test_statusbar.py`:

- the idle hint on a wide bar is the whole hint;
- on a bar too narrow for it, parts go from the end, and no part is cut in the middle;
- the hardware on the right is still there at every width.

## The live run

By the user, in a real terminal. Each line is something the tests can't show.

1. **The key.** At the prompt, with half a line typed: Ctrl+F12, Esc. The line is there.
2. **The screen at the shell.** During a long answer: Ctrl+F12, wait until the bar stops
   spinning, Esc. The whole answer is on the screen, and scrolling back shows what was
   before it.
3. **The screen in a program.** In an editor with unsaved text: Ctrl+F12, Esc. The text and
   the cursor are as they were.
4. **The tick budget.** In a player whose updates are paused: raise the budget in the panel.
   The player moves again.
5. **The budget per boot.** Set it low, use it up, raise it. The held line goes through. How
   far did the last answer go over the cap?
6. **The model.** Switch it. The bar shows the new model with the next answer. What did that
   answer cost, beside the ones before it?
7. **The effort.** Change it, type `reboot`. The bar shows it after the reboot, not before.
8. **Save.** Press it, then look at `config.toml`: the changed lines are new, and every
   comment is still there.
9. **The window.** Resize it while the panel is open, then close the panel.
10. **Esc and the arrows.** Does Esc feel quick? Does an arrow key ever close the panel? Over
    ssh too, if Hallux is used that way.
11. **The mouse.** A click on a row and on Close. After closing, at the shell: does selecting
    text with the mouse work as before?
12. **The hard exit** from inside the panel.
13. **A password prompt:** `sudo`, some keys, Ctrl+F12, Esc, then the password.

## Done when

The live run is written up below, the status lines say "built", and the design's "Still to
find out" has an answer for each of its points, or says that it is still open.

## What the live run taught

Not run yet.
