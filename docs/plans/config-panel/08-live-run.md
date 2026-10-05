# Step 8: the bar, the documentation and the live run

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), section 3 and
"Still to find out"

**Needs:** steps 4 and 7. **Changes:** `hallux/statusbar.py`, `hallux/machine.py`,
`tests/test_statusbar.py`, `README.MD`, `docs/`.

The panel works by now, but nothing tells you that it exists. This step puts the key on the
bar, writes the documentation, and ends with the run in a real terminal that the tests
can't replace.

## Build

**The idle hint** names the key: `power off: ctrl+shift+del · config: ctrl+f12 · ctrl+c ×3`.

- **The power-off keys come first.** The hint is there so that nobody gets stuck, and since
  step 3 the way out of a boot that has used its budget is a key.
- **On a narrow window the hint loses parts from the end,** whole ones: first the triple
  Ctrl-C, then the panel's key. Today a hint that is too long is cut in the middle of a
  word. At 80 columns, beside a long model name and cost, only the first part fits.
- **The note of a used-up budget per boot** (step 3) gets the key:
  `budget used: $2.00 per boot · raise it: ctrl+f12`.

**The documentation:**

| File | What changes |
|---|---|
| `README.MD`, "Keys" | A row for Ctrl+F12 |
| `README.MD`, "Project layout" | `panel.py` and `panel_tabs/` |
| `docs/light-and-keys.md`, the key rule | Ctrl+F12 is Hallux's own, beside the hard exit |
| `docs/concept.md`, "Changing the hardware" | It says "edit the config, then `reboot`". That was never so: the file is read once, when Hallux starts (`hallux/app.py:53`). It says what is true now: the panel, or a new start |
| `README.MD`, "Configuration" | The panel; a table of what changes at once, at the next reboot and at the start; that Save keeps the file's comments |
| `README.MD`, "Cost and speed" | A budget can be raised while the machine runs |
| `docs/concept.md`, principle 1 | It names two things on the screen that aren't the AI's. The panel is a third |
| `docs/concept.md`, "Configuration: model and effort" | It says that changing the hardware means rebooting, and that a switch inside a running session would break the first principle. With the panel that is no longer so: the paragraph says what the panel does, and why it doesn't break the principle |
| `hallux/machine.py`, the docstring | It names the bar as the one exception. Now there are two |
| `docs/roadmap.md` | An entry for the panel |
| `docs/config-panel.md`, this plan | The status lines |

## Tests

In `tests/test_statusbar.py`. Two tests there pin today's hint
(`tests/test_statusbar.py:16,96`) and change with it.

- the idle hint on a wide bar is the whole hint;
- on an 80-column bar with a long model name and cost, the power-off keys are there;
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
   far did the last answer go over the cap? Then use it up again and press Refill budgets:
   the line goes through, the row shows both numbers, and the bar's total hasn't dropped.
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

## As built

Built on 2026-10-05, on the branch `config-panel`. 1 new test and 2 changed, 1054 in all.
Decided while building:

- **The hint is three parts,** and `idle_hint(room)` joins as many as fit. Parts go from
  the end, and the last one left is cut only when it doesn't fit by itself.
- **`PANEL_KEY`** in `hallux/statusbar.py` is the key as the bar writes it. The hint and the
  note of a used-up budget per boot both take it from there.
- **A scripted run's note has no key.** `budget used: $0.01 per boot` is printed as before:
  a script has no keyboard to press Ctrl+F12 on, and it halts there anyway.
- **While the AI listens to an addon the bar says `listening: …`,** as before, and not the
  hint. The key isn't named then.
- **The README has a feature line for the panel** and names its design under
  "Documentation", beside what the step's table lists.
- **`docs/concept.md` says why the old sentence is gone:** it had said that a switch inside
  a running session would break the first principle.
- **`tests/panel_demo.py` is gone.** It showed the panel before anything in Hallux opened
  it. The user has used the real one since.
- **The panel tests wait for the screen to be drawn again** after they type, not for a fixed
  time alone. One of them had failed once, in a full run on a busy computer.

## What the live run taught

**Run by the user on 2026-10-05,** in their own terminal, on the test world. The first
points came up while steps 6 and 7 were built. The rest the user went through with
[live-run-checklist.md](live-run-checklist.md), from 08:56 to 09:54, and ticked every one.
Their rule for it: a point with nothing written under it went as expected. Two points they
tried once more at 10:04, after the log had shown that they hadn't really been reached.

The numbers are not the user's. They are from the test world's own log,
`test-hallux/.hallux/hallux.log`, which has a line for each change, each save and each
answer's cost.

| | Point | What the user reported | What the log adds |
|---|---|---|---|
| 1 | The key, with half a line typed | As expected | |
| 2 | The screen at the shell, during an answer | **A bug, found by the user.** The panel was opened during the boot. Afterwards a copy of the bar stood in the boot's text and the prompt lay on the bar's row. Fixed in step 6. Then: "now it works perfectly" | |
| 3 | The screen in a program | An editor with unsaved text, and vim in normal mode: "this is really working nicely" | |
| 4 | The tick budget | A paused player moves again with a higher budget: the same answer. Tried again on the day of the checklist: "the tick budget works" | The tick budget was raised from 1.25 to 10. In the second try it was set to $0.01 and, a minute and a half later, to $10 |
| 5 | The budget per boot | As expected | The cap was set to $0.16 when the boot had spent $0.1384. The next answer cost $0.0261 and took the boot to $0.1644: **$0.0044 over the cap.** Nothing was sent for 18 seconds, until the cap was taken away, and the next line went through. **No refill is in the log,** of this run or of an earlier one |
| 6 | The model | "it works" | From Opus to Sonnet: the first answer cost $0.0656, the one after it $0.0054. From Sonnet to Haiku: the first answer cost $0.0287. Then back to Opus. Each switch happened with the next message, as built |
| 6 | A name that is no model | "the not existant model message works" | The first time `claude-banana-89` was put back before a message went out, so no switch was tried. The second time `claude-banana-45` was set, and four seconds later: `model not switched: Model 'claude-banana-45' not found (it stays claude-opus-5-5)`. The right name was put back after that |
| 7 | The effort, over a reboot | As expected | Low to medium, then `reboot` five seconds later |
| 8 | Save, and the comments in `config.toml` | As expected | Eleven saves. The file has its three comments and its first lines as they were. `effort`, `fallback_model` and `model` got lines at the end. The line of `max_budget_usd` was written and taken out again |
| 9 | The window resized while the panel is open | As expected | |
| 10 | Esc and the arrows | As expected: "yeah i tried esc and arrows". Not over ssh: "it should work over ssh. let it be a test for the future" | |
| 11 | The mouse, and selecting text at the shell afterwards | As expected | |
| 12 | The hard exit from inside the panel | As expected | Two power cuts, 22 seconds apart |
| 13 | A password prompt | As expected | |
| | Is the bar enough to notice an answer behind the panel? | "yeah, its enoght" | |

**One thing no real run has shown yet,** by the log: **Refill budgets.** The button was
never pressed in the test world; a paused program was made to move again with a higher
number each time. What the button does is covered by the tests, and by the run on a
pseudo-terminal in step 7, where a paused program ticked again after it.

**What the numbers say:**

- **One answer goes over the cap by less than that answer costs.** Here an answer of $0.026
  ended $0.004 over. A long answer on a large model can go over by more: the check sits
  between two answers.
- **The first answer after a model switch costs several times a normal one.** $0.066 against
  $0.005 on Sonnet, in a boot that had spent $0.19 before.

**One more thing the user saw:** at 80 columns the note of the budget per boot is cut after
a refill. They don't mind it at that width.
