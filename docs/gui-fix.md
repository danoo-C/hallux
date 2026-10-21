# GUI addon: fixes

**Status:** a list for the user to review, 2026-10-20. Nothing here is built yet, except
fix 0, which is built and tested. Every fix stays inside `addons/gui.py` and its tests:
Hallux's own code is not changed. The design is [addon-gui.md](addon-gui.md).

**Where these came from:** the user's live tries in `test-hallux` on 2026-10-20: a
calculator (kittycalc), a bare test window, and a chat app the AI built ("Hallux AI").

| # | Problem | Status |
|---|---|---|
| 0 | Clicks and Enter never reached the AI | Fixed and tested, not committed |
| 1 | Arrows, math signs and other symbols draw as empty boxes | To build |
| 2 | Emoji draw as empty boxes | To build; needs a font installed |
| 3 | The AI never learns what didn't draw | To build |
| 4 | Text that doesn't fit its widget is cut off silently | To build, with 3 |
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
