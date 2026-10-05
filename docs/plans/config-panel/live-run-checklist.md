# The settings panel: what to try by hand

[The plan](README.md) · [step 8](08-live-run.md), whose live run this is

**What this is:** the points of the live run that nobody has reported yet, written out so
that each can be tried and ticked off. The tests can't show any of them: they need a real
terminal, and most need a real model.

**How to use it:** try a point, tick its box, and write what you saw on the line under it.
A few words are enough, and "fine" is an answer. Where a point asks for a number, the place
to read it is named. When you are through, give me the file or tell me the results, and I
write them into step 8.

**If something looks wrong:** a screenshot and the number of the point are all I need.

---

## Before you start

- **Start Hallux on a test world,** as usual:

  ```bash
  python hallux.py ./test-hallux/
  ```

- **The answers cost what they always cost.** The whole list is a few dozen short commands.
  Point 5 needs a budget of a few cents, which you set in the panel itself.
- **For point 8, put a comment into the world's settings first,** if it has none. In
  `test-hallux/.hallux/config.toml`, before you start Hallux:

  ```toml
  # my test world
  tick_budget_usd = 0.25    # live updates
  ```

- **The panel's own keys:** Ctrl+F12 opens it. Esc, Ctrl+F12 or the Close button close it.
  ↑ ↓ move, Enter opens a row or presses a button.

**Already reported, no need to repeat:** the screen after the panel was opened during an
answer (point 2), the panel over an editor and over vim (point 3), and a paused program that
moves again (point 4).

---

## The points

The numbers are the ones of the plan's list.

### 1. Half a line

1. At the prompt type `echo hel`, and don't press Enter.
2. Press Ctrl+F12, then Esc.
3. Type `lo` and press Enter.

**Should happen:** after Esc the prompt is there with `echo hel` on it, and the cursor
behind it. The command that runs is `echo hello`.

- [x] Tried
- Result:

### 5. The budget per boot

1. Open the panel. The row "Budget per boot" says what the boot has spent so far. Open the
   row and enter that amount plus about three cents, for example `0.08`. Close the panel.
2. Run short commands until the bar says `budget used: $0.08 per boot · raise it: ctrl+f12`.
3. Open the panel and read the row: `spent in this boot: $…  (paused)`. **How far over the
   cap is it?** Write both numbers down.
4. Close the panel, type `echo held` and press Enter. Press Enter once more.
5. Open the panel, raise the budget by a few cents, close it. Press Enter.
6. Use the budget up again. Type `echo again`, press Enter: it is held.
7. Open the panel and press **Refill budgets**. Look at the row and at the bar. Close the
   panel and press Enter.

**Should happen:**

- In 4 nothing is sent: the line comes back at the next prompt, and each Enter adds a row.
- In 5 the note leaves the bar when the budget is raised, and `echo held` runs.
- In 7 the panel says `budgets refilled`. The row shows two numbers,
  `spent since the refill: $0.00 · this boot: $…`. The total on the right of the bar hasn't
  dropped. Then `echo again` runs.

- [x] Tried
- The cap, and what the boot had spent when it was reached:
- Result:

### 6. The model

1. Note the total on the right of the bar.
2. Open the panel, open the row "Model", pick another model with ↓ and Enter. Close the
   panel. The bar still shows the old model.
3. Run `echo switched`. Note the total again.
4. Run `echo once more`, and note the total a third time.

**Should happen:** the bar shows the new model with the answer to `echo switched`, not
before. That answer costs more than the one after it: the new model reads the whole
conversation of the boot once.

- [x] Tried
- The three totals:
- Result: it works

**If you like, a wrong name too:** open the row again and type `claude-banana-9`. With the
next command the bar should say `model not switched: Model 'claude-banana-9' not found`, and
the answer should still come, from the model that ran. Put a real name back, and the note
should go with the next command. Don't save the wrong name: a boot that starts on it fails.

- [x] Tried
- Result:

### 7. The effort

1. Open the panel, open the row "Effort", pick another value. The row then says
   `running now: …` with the old one. Close the panel.
2. Look at the bar: it still shows the old effort.
3. Type `sudo reboot`.

**Should happen:** the bar shows the new effort after the reboot, and not before.

- [x] Tried
- Result:

### 8. Save

1. Change one or two settings in the panel. The line of buttons says how many changes
   aren't saved.
2. Press **Save**. It says `saved`.
3. In another terminal: `cat test-hallux/.hallux/config.toml`

**Should happen:** only the lines you changed are new. Your comments and every other line
are as they were. A setting that had no line has one at the end.

- [x] Tried
- Result:

### 9. The window

1. Open the panel. Make the terminal's window larger, then smaller, then very small.
2. Close the panel.
3. Once more while an answer is being written: start a long listing, open the panel, resize
   the window, wait until the bar stops spinning, close the panel.

**Should happen:** the panel follows the window; on a small one the rows scroll and the
buttons stay. After it closes, the bar is on the last row and the prompt is above it.

- [x] Tried
- Result:

### 10. Esc and the arrows

1. Open the panel and press Esc. Does it close at once?
2. Open it again and press ↑ and ↓ many times, fast.
3. If you use Hallux over ssh: the same there.

**Should happen:** Esc feels quick, and an arrow key never closes the panel.

- [x] Tried
- Result:

### 11. The mouse

1. Open the panel. Click a row: it opens. Click an entry of the list under the Effort or
   the Model row: it is taken. Click `[ Close ]`.
2. Back at the shell: select some text with the mouse, and turn the wheel.

**Should happen:** the clicks do what the keys do. At the shell the mouse is the terminal's
again: selecting and scrolling back work as before the panel was opened.

- [x] Tried
- Result:

### 12. The hard exit from inside the panel

1. Open the panel and press Ctrl+Shift+Del.
2. Start Hallux again, open the panel, and press Ctrl-C three times within a second.

**Should happen:** both end Hallux at once with `hallux: power cut`. The terminal is left
usable: the cursor is there, and moving the mouse prints nothing.

- [x] Tried
- Result:

### 13. A password prompt

1. Run something that asks for a password, such as `sudo ls` on a machine that has one.
2. At the password prompt type a few keys, press Ctrl+F12, then Esc.
3. Type the password and press Enter.

**Should happen:** after Esc the password prompt is there again, empty. Only what you type
now counts. The password prompt after that one behaves as always.

- [x] Tried
- Result:

---

## One question of judgement

An answer can arrive while the panel is open. Nothing of it is drawn until the panel
closes; the bar on the panel's last row stops spinning and shows the new cost.

- **Is that enough to notice that the answer is there?**
- Your word: yeah, its enoght
