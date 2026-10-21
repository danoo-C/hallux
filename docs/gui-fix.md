# GUI addon: fixes

**Status:** fixes 0 to 4 are built and tested, 2026-10-21, not committed (fix 0 was
committed with the addon as 76045d0). Fix 5 is left for later. The open questions were
settled by my recommendations when the user said "build the gui-fix.md". The user's live
try is still to come. [As built](#as-built) has where the code differs from the text below. Every fix stays inside `addons/gui.py` and its tests:
Hallux's own code is not changed. The design is [addon-gui.md](addon-gui.md).

**Where these came from:** the user's live tries in `test-hallux` on 2026-10-20: a
calculator (kittycalc), a bare test window, and a chat app the AI built ("Hallux AI").

| # | Problem | Status |
|---|---|---|
| 0 | Clicks and Enter never reached the AI | Fixed (76045d0) |
| 1 | Arrows, math signs and other symbols draw as empty boxes | Fixed |
| 2 | Emoji draw as empty boxes | Fixed; the user installs an emoji font |
| 3 | The AI never learns what didn't draw | Fixed |
| 4 | Text that doesn't fit its widget is cut off silently | Fixed, with 3 |
| 5 | No copy and paste in inputs | Later |

---

## 0. Clicks never reached the AI (fixed)

**Seen:** in kittycalc and in a bare test window, `closed` arrived but no click and no Enter.
The log of `test-hallux` showed no event dropped by Hallux.

**Cause:** the pipe between the addon and a window's child told an answer from an event by
an `"id"` key. A click carries the `id` of its button, so the addon took every click for a
stray answer and dropped it. `closed` has no `id`.

**Fix:** the pipe numbers its messages with `seq`. A test sends a click through a real
child. Still to see: a click in a live try.

## 1. Symbols draw as empty boxes

**Seen:** in the chat app, the send button's arrow, and in kittycalc `⌫`, `÷`, `×`, `−`.

**Cause:** every text is drawn with pygame's built-in font, which covers little more than
basic Latin.

**Fix:** draw with DejaVu Sans when it's installed (it is on this machine:
`/usr/share/fonts/truetype/dejavu/`), found once per window with `pygame.font.match_font`.
Without it, pygame's font as now. It covers arrows, math, `⌫`, box drawing, Greek, Cyrillic.
The canvas already looks for DejaVu Sans Mono.

**Mind:** DejaVu Sans is wider than pygame's font at the same size, so a layout that just
fits may not fit any more. Fix 4 makes that visible.

## 2. Emoji draw as empty boxes

**Seen:** "🐾 Hallux", "🐾 Danika Hous", and the model name in the chat app.

**Cause:** no emoji font is installed on this machine, so no font can draw them.

**Fix:**
- The user installs one: `sudo apt install fonts-noto-color-emoji`.
- A line of text is drawn in runs: each character goes to the first font that has it
  (DejaVu Sans, then the emoji font), and the runs are drawn side by side. Measuring a text
  (for wrapping, the cursor and alignment) adds up the same runs, so both stay in step.
- Noto Color Emoji is a bitmap font with one size (109 px). It is drawn at that size and
  scaled down to the line's height. To check while building: that pygame's SDL_ttf (2.20.1
  here) draws it in color at all. If it doesn't, emoji stay boxes and fix 3 says so.

## 3. Tell the AI what didn't draw

**Fix:** `show` (and `update`) return what went wrong, beside what they return now:

```json
{"window": "chat", "missing": "🐾✨", "cut": ["answer", "title"]}
```

- `missing`: the characters no font could draw, each once.
- `cut`: the widgets whose text doesn't fit (fix 4).
- Both keys are left out when there's nothing to say, so a good window costs nothing.
- The manual says what to do: replace a missing character with a plain one, make a cut
  widget bigger, give it a smaller `font_size` or use a `text` widget that scrolls.

## 4. Text cut off silently

**Seen:** in the chat app, point 3 of the answer was missing, with an empty gap where it
should have been. The likely cause is a widget too small for its text; the layout file
would tell, and wasn't kept.

**Fix:** the child measures each text when it shows a layout or an update, and lists the
widgets where it doesn't fit, for `cut` in fix 3:
- `label`, `button`, `checkbox`, `input`'s first text: wider than the widget;
- `text`: more lines than fit. It still scrolls with the wheel, but the AI should know that
  the user has to scroll;
- `canvas`: rows or columns beyond the widget.
What the user types doesn't count: an input scrolls, and a textarea is meant to grow.

## 5. Copy and paste (later)

Inputs and textareas take typing only. Ctrl+V could paste through `pygame.scrap`, and
Ctrl+C copy what is selected, but there is no selection yet. Not needed for anything seen
so far.

---

## Open questions

1. **Should `missing` and `cut` come back from `update` too, or only from `show`?**
   My recommendation: both. An update that puts "42 🐾" into a label has the same problem.
2. **When no emoji font is installed, should the addon replace emoji by itself (with `?` or
   nothing) instead of drawing a box?** My recommendation: no. It keeps the box, tells the
   AI through `missing`, and the AI chooses a replacement that fits the program.

## Order of work

1. Fonts in runs, DejaVu Sans first (fixes 1 and 2), with tests that measure and draw with
   and without each font.
2. Measuring what doesn't fit (fix 4), and `missing` and `cut` in what `show` and `update`
   return (fix 3), with the manual's lines.
3. A live try by the user: kittycalc and the chat app again, once with an emoji font
   installed.

---

## As built

Built 2026-10-21 in `addons/gui.py` (a `Fonts` class in the child, `Gui.drawn` and
`Gui.is_cut`, and two lines in `show` and `update`), with 7 new tests in
`tests/test_addon_gui.py` (36 in all).

- **The fonts are found once, when a window starts,** before it says it is ready: finding a
  font asks `fc-list`, which can be slow, and the first answer has a deadline. The main
  font is the first of DejaVu Sans, Noto Sans, Liberation Sans, Arial that is installed (on
  this machine `match_font` picks DejaVu Sans Condensed); the emoji font the first of Noto
  Color Emoji, Noto Emoji, Twemoji, EmojiOne, Symbola.
- **Whether a font has a character** comes from pygame's metrics, except where they can't
  tell: above U+FFFF they are always empty, and pygame's own font has metrics for
  everything. There the character is drawn once and compared with the box the font draws
  for a character nobody has (U+10FFFD). The answer is cached per font and character.
- **Color emoji work** with pygame 2.6.1 (SDL_ttf 2.20.1): checked with a copy of Noto
  Color Emoji in the session's scratch folder, never installed. 🐾 and 😀 come out in
  color, and so does 👍🏽 with its skin tone.
- **Characters from U+1F000 on go to the emoji font first,** when it has them. DejaVu has a
  few emoji of its own, in black; the color ones look right next to the rest.
- **Joiners and variation selectors (U+200D, U+FE00 to U+FE0F) are left out** when drawing:
  one by one they would only be boxes. They never count as missing.
- **The canvas** draws a character its monospace font lacks with the other fonts, centered
  on its cell. An emoji is wider than a cell, as in a terminal.
- **`cut` leaves out inputs, textareas and sliders.** That includes an input's first text,
  which the list above counted: an input scrolls, whoever wrote its text. A `list` counts
  when a line is wider than the list; more lines than fit is just scrolling.
- **At most 40 characters in `missing` and 30 ids in `cut`.**
- **One existing test changed:** the wheel test assumed how many lines a list scrolls,
  which depends on the font's height.
- **The manual** has four new lines: what `missing` and `cut` mean, and to fix them before
  calling the window done.
