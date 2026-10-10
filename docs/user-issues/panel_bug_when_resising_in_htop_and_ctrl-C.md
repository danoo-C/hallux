# The old status bar left in the text after a resize in htop

Investigated 2026-10-10 on `addon-agents` at bdbf177, and fixed the same day, in the
commit that added this file. The screenshot is
`panel_bug_when_resising_in_htop_and_ctrl-C.png`, next to this file.

Everything up to "The fix" describes Hallux as it was at bdbf177.

## The cause

The gray line in the middle of the screenshot is the status bar as it was drawn on the
shell's screen just before `htop` came up. It is the bar, not the Ctrl+F12 panel.

While `htop` was on screen, the window was made wider: 86 columns became 121, the height
stayed 30 rows. `htop` runs on the terminal's second screen, and the shell's screen waits
behind it with the bar still on its bottom row. When a window changes its width, the
terminal lays the waiting screen out again. One line on it was 87 characters wide. It
took two rows at 86 columns and one row at 121, so every row below it moved up by one,
and the old bar moved from row 30 to row 29.

When `htop` ended, Hallux drew the bar on the bottom row, as it always does. It has no
step that erases the old bar, because it takes for granted that the old bar is on the
bottom row and is overwritten there. This time it was one row higher, inside the part of
the screen that scrolls. `^C` was printed over its first two characters, and the line
break after it scrolled it up into the text for good.

So the resize is the cause. Ctrl-C matters only because it prints a line.

## Why it happens only sometimes

All three have to be true:

1. The window's width changes while a full-screen program is on screen.
2. The new width moves the old bar. Either a line on the shell's screen takes a different
   number of rows at the new width (it was wrapped and now fits, or the other way round),
   or the window gets narrower: the old bar is as wide as the old window, so it no longer
   fits on one row. The second case I saw in the replay only.
3. The program prints at least one line when it ends, as `^C` here. If it prints nothing
   (`q` in `htop`), the next prompt is drawn from the cursor's row, erases everything
   below it first, and takes the old bar with it. Nothing is left to see.

A resize with no long line on screen, or a program left with `q`, shows nothing. That is
why it looks random.

## What the log and the screenshot show

The run is in `test-hallux/.hallux/hallux.log`, lines 5742 to 5822.

| Time | What happened | Window |
|---|---|---|
| 12:44:39.4 | the composer's job starts | 86 × 30 |
| 12:45:23 | `htop` is typed | 86 × 30 |
| 12:45:40.1 | `htop`'s screen arrives, after 16.8 s | 86 × 30 |
| 12:45:42 | first tick goes out | 86 × 30 |
| 12:45:49 | second tick goes out | 121 × 30 |
| 12:46:12 | Ctrl-C stops the answer to the third tick | 121 × 30 |
| 12:46:15 | the answer: `^C`, a line break, the prompt (2.9 s) | 121 × 30 |

(The log has `rows="29"`: the bar's row is not counted there.)

The stale line reads `music: composing… · 1:00 · 5k tok … opus 5.5 · low · ~$1.04 · 16.8s`.
Each number in it fixes when it was drawn:

- `16.8s` is the time of `htop`'s answer, so it was drawn after 12:45:40.1.
- `1:00` is the job's clock. The job began at 12:44:39.4, so the clock shows `1:00` until
  12:45:40.4.
- `~$1.04` is $0.8130 of the boot before plus $0.2251 of this boot right after `htop`'s
  answer.

So this bar was drawn within those 0.3 seconds: it is the last bar drawn on the shell's
screen before `htop` took the screen. Its text is also still laid out for 86 columns.

The line `🐾 composing "a slow blues in twelve bars with a walking bass" into ~/Music ... ♪ =^.^=`
is 87 cells wide (measured from the logged answer). No other line on the screen was
wider than 86.

The rows fit too. Before `htop`: `$ htop` on row 28, the cursor on row 29, the bar on
row 30. In the screenshot `$ htop` is on row 23 and the old bar on row 25, after `^C`,
an empty line and the three prompt lines scrolled the screen four times. Four rows back,
`$ htop` was on row 27 and the old bar on row 29: one row above where it was drawn.

## What Hallux does, step by step

Line numbers are those of bdbf177.

1. `htop`'s answer ends. `busy()` sets the bar to idle and draws it on row 30
   (`hallux/terminal.py:302`). This is the bar of the screenshot.
2. `show_form` takes the scroll region away and block mode starts its full-screen
   application on the second screen (`hallux/terminal.py:392`, `hallux/blockmode.py:275`).
   The bar's row on the shell's screen is left as it is. Block mode has a bar of its own.
3. The window is resized. Hallux does nothing to the shell's screen: `_check_size` returns
   at once while a program is up (`hallux/terminal.py:496`). The terminal moves the rows.
4. The program ends. `end_form` goes back to the shell's screen and calls `_draw_bar()`
   (`hallux/terminal.py:409`), which pins rows 1 to 29 and draws the bar on row 30
   (`hallux/statusbar.py:235`). The old bar on row 29 is not touched.
5. The answer's text is written at the cursor, which is on row 29, the last row that
   scrolls. `^C` lands on the old bar, and the line break scrolls it up.

`suspend_form` (Ctrl-Z) ends a program the same way, so it has the same gap.

`_check_size` would not have helped here even if it had been called. It erases an old
bar only when the window got taller, and it erases the row number the bar had in the old
size. Here the height did not change, and the old bar was no longer on that row.

## The replay

I ran the real `Machine` and the real `Terminal` with its bar, with a pretend model that
gives the logged answers, typed the same lines from the boot on, and used tmux as the
terminal. tmux also lays the waiting screen out again after a resize. The runs are
without scrollback, except the one that says otherwise.

| Run | Old bar right after `htop` is left | Screen at the next prompt |
|---|---|---|
| 86 → 121 columns | on row 29, the new bar on row 30 | clean: tmux puts the cursor above the old bar, and the prompt erases it |
| the same, cursor on row 29 as in the screenshot | on row 29 | the screenshot, all 30 rows |
| the same, left with `q` | on row 29 | clean: the prompt erases it |
| 100 → 121 columns (the long line fits both) | none | clean |
| 86 → 121, tmux with scrollback | none | clean |
| 121 → 86 columns | its first 86 characters on row 29 | clean in tmux |
| 30 → 36 rows, same width | on row 30, the new bar on row 36 | clean in tmux |

Right after `htop` is left, 86 → 121 columns:

```
 > ^ <  🐾 $ htop

 • power off: ctrl+shift+del · config: ctrl+f12       opus 5.5 · low · ~$0.07 · 1.0s
 • power off: ctrl+shift+del · config: ctrl+f12 · ctrl+c ×3                              opus 5.5 · low · ~$0.09 · 0.5s
```

At the next prompt, with the cursor where the screenshot has it:

```
 > ^ <  🐾 $ htop

^C power off: ctrl+shift+del · config: ctrl+f12       opus 5.5 · low · ~$0.07 · 1.0s

 /\_/\  danika-hous@hallux
( o.o ) ~
 > ^ <  🐾 $
 • power off: ctrl+shift+del · config: ctrl+f12 · ctrl+c ×3                              opus 5.5 · low · ~$0.09 · 0.5s
```

Two things differ between terminals, and they decide whether the bar is left:

- **Where the rows go.** tmux with scrollback pulls a line down from the scrollback and
  leaves the rows below the long line where they are, so nothing is left. tmux without
  scrollback moves them up, as Windows Terminal did in the screenshot.
- **Where the cursor comes back.** tmux moves the cursor with its line, so it ends above
  the old bar and the next prompt erases the bar. In the screenshot `^C` covers the start
  of the old bar, so Windows Terminal put the cursor back on its old screen row. For the
  second run I moved the cursor down one row by hand to match that.

**Not checked:** I did not run Windows Terminal itself. That it moves the rows up and
puts the cursor back on row 29 is read from the screenshot, not measured. The scripts of
the replay are not in the repository.

## The fix

Built 2026-10-10 in `hallux/terminal.py` and `hallux/statusbar.py`.

1. **No bar waits on the shell's screen.** Before a program or the panel takes the second
   screen, Hallux erases the bar's row on the shell's screen (`_take_bar_off`, called by
   `show_form`, `resume_form` and `visit_panel`). Whatever the terminal does with the rows
   during a resize, there is no old bar that it could move.
2. **The bar comes back for the window as it is then** (`_put_bar_back`, called by
   `end_form`, `suspend_form` and `visit_panel`). Nothing is wiped at that point any more.
   The panel's visit used to wipe the row where the bar had been before a taller window;
   after a resize that row can hold text.
3. **The cursor is taken off the bottom row first** (`statusbar.reinstall`). With the
   bar's row empty, a window that gets shorter can leave the cursor on the bottom row. My
   first version of the fix had only points 1 and 2, and the replay showed the answer's
   text and the prompt written over the bar there. Now the cursor goes one line down,
   which scrolls the screen only if it stands on the bottom row, then the bar is drawn,
   then the cursor goes one row up again.

### How it was checked

The tests: 1579 pass. Five of them describe the new behaviour and fail on the old code
(one is new, four were changed).

The replay in tmux, each case with the old code and with the fix. "One bar" means: one
whole bar, on the bottom row, both right after the program or the panel is gone and at
the next prompt.

| Case | Old code | With the fix |
|---|---|---|
| `htop`, wider (86 → 121), Ctrl-C | old bar on row 29 until the prompt erases it | one bar |
| the same, cursor as in the screenshot | the screenshot | one bar |
| the same, left with `q` | old bar on row 29 until the prompt erases it | one bar |
| `htop`, narrower (121 → 86), Ctrl-C | a piece of the old bar on row 29 until the prompt erases it | one bar |
| `htop`, taller (30 → 36 rows), Ctrl-C | old bar on row 30 until the prompt erases it | one bar |
| `htop`, shorter (30 → 24 rows), Ctrl-C | one bar | one bar |
| `htop`, smaller both ways (86 × 30 → 70 × 20), Ctrl-C | one bar | one bar |
| `htop`, wider, Ctrl-Z, `fg`, narrower, Ctrl-C | old bars stay in the text | one bar |
| the panel at the prompt, wider, Esc | one bar | one bar |
| the panel while the AI works, wider, Esc | old bar stays in the text | one bar |

With the fix I also ran wider, taller, shorter and smaller in tmux with scrollback, and
Ctrl-Z and both panel cases with the cursor as in the screenshot: one bar in all of them.
Without point 3, the shorter and the smaller cases had the text over the bar.

One thing stays visible. With the cursor where the screenshot has it, `^C` stands one
row lower than before, with an empty row above it:

```
 > ^ <  🐾 $ htop

^C

 /\_/\  danika-hous@hallux
```

That row comes from where the terminal puts the cursor after the resize, not from Hallux.

**Not checked:** Windows Terminal itself. The replay is tmux, and the two places where
Windows Terminal differs from it are imitated, not run.

## How to try it

In Windows Terminal, in `test-hallux`:

1. Print a line that is a little longer than the window, so that it wraps onto a second
   row (`echo` with a long text does it). It has to stay on screen.
2. Start `htop`.
3. Make the window wider, enough for that line to fit on one row.
4. Press Ctrl-C.

Before the fix the old bar stood in the text, with `^C` over its start. Now there should
be one bar, on the bottom row. Worth a second try with the window made smaller instead.
