# GUI addon

**Later:** the fixes of [gui-fix.md](gui-fix.md) and the features of
[gui-features.md](gui-features.md) (groups, tabs, local actions, adding and removing widgets,
defaults, canvas clicks) are built on top of what this document describes.

**Status:** built 2026-10-20 on branch `gui-addon` (from origin/main), not committed:
`addons/gui.py` and `tests/test_addon_gui.py` (28 tests, no display needed). The user
answered the open questions the same day (see the end) and asked for a slider and an ascii
art canvas. Still to do: the user's live try. [As built](#as-built) lists where the code
went further than the sections below.

**The one rule, from the user:** Hallux's own code is not changed. Everything here is one
new addon file, `addons/gui.py`, plus its tests. It uses only what addons already have:
`EXPOSED`, the `disk` handle, `connect(emit)`, `stop()` and, if wanted, `agent()`
([addons.md](../addons.md), [addon-events.md](../addon-events.md), [addon-agents.md](../addon-agents.md)).

## In short

1. **The machine can open real windows on the desktop,** with labels, text, buttons, input
   boxes and more, placed where it says.
2. **A press of a button goes to the AI** as an event, with the values of every input in the
   window, so the AI can answer at once: change a label, open another window, write a file.
3. **A window is described by a layout file on the machine's disk,** the way a song is a
   score file. One call shows it. It survives a reboot, the user can edit it in nano, and
   showing it again costs no tokens.
4. **It is built like the window addon:** pygame runs in a child process, never inside
   Hallux. One child per open window.

---

## 1. What the AI calls

The user's sketch was one function per widget: `create_button()`, `multitext(text, position,
text, position, ...)`. That works, but every call is a model round trip
([addons.md](../addons.md) section 6): a window with ten widgets would make the user wait ten
times. So the widgets go into one file, and the functions are few and coarse:

| Function | What it does |
|---|---|
| `show(disk, path)` | Reads the layout file at `path` and opens its window. A window with the same `name` that is open already is redrawn from the file, and keeps what the user typed. Returns `{"window": name}` |
| `update(window, changes)` | Changes widgets of an open window without the file: `changes` is a JSON object such as `{"display": {"text": "42"}, "ok": {"enabled": false}}`. This is how the AI answers a press |
| `read(window)` | The values of every input, checkbox and list in that window |
| `close(window)` | Closes one window |
| `stop()` | Closes them all (also called by Hallux on halt and reboot) |

`changes` is a string of JSON, since the schema builder takes only `str`, `int`, `float`,
`bool` and `list[str]`.

**`multitext` is still there,** as a widget: a `text` widget can hold several lines, and a
layout can have as many `label`s at as many positions as it likes.

## 2. The layout file

JSON, because the AI writes it reliably and the addon reads it without a parser of its own.

```json
{
  "name": "calc",
  "title": "Calculator",
  "size": [260, 320],
  "background": "#202020",
  "widgets": [
    {"id": "display", "type": "label",  "pos": [20, 20],  "size": [220, 40], "text": "0"},
    {"id": "a",       "type": "input",  "pos": [20, 80],  "size": [100, 32]},
    {"id": "b",       "type": "input",  "pos": [140, 80], "size": [100, 32]},
    {"id": "add",     "type": "button", "pos": [20, 130], "size": [100, 40], "text": "+"},
    {"id": "notes",   "type": "text",   "pos": [20, 190], "size": [220, 110],
     "text": "Type two numbers\nand press +"}
  ]
}
```

**The widgets, first version:**

| Type | What it is | Its value in an event |
|---|---|---|
| `label` | One line of text | none |
| `text` | Several lines, read only, wraps and scrolls | none |
| `button` | A button with a label; a press is an event | none |
| `input` | One line the user types into; Enter is an event | the text |
| `textarea` | Several lines the user types into | the text |
| `checkbox` | On or off, with a label | `true` / `false` |
| `list` | A list of lines, one can be picked; a pick is an event | the picked line |
| `slider` | A number from `min` to `max` on `step`s; letting go is an event, dragging isn't | the number |
| `canvas` | Ascii art: text in a fixed grid, every character the same width, never wrapped | none |

Every widget has `id`, `type`, `pos` and `size`, and may have `color`, `background`,
`font_size` and `enabled`, plus the keys of its type (`text`, `align`, `items`, `value`,
`min`, `max`, `step`). `update` can change every key but `id`, `type`, `pos` and `size`.

**Positions are pixels from the window's top left,** as the user asked. The window has a
fixed size.

**The addon checks the file,** since the AI wrote it: at most 100 widgets, ids unique and
short, texts at most 2000 characters, colors a name or `#rrggbb` (the window addon's rule),
every widget inside the window, the window at most 1600 × 1000. A broken file is one error
that names every problem, like the music addon's `check`, so the AI fixes it in one round.

## 3. Events: the press reaches the AI

Through `connect(emit)`, exactly as the window addon's Send button. The AI must listen first:
`addon_listen("gui")`. Without it, a press costs nothing and goes nowhere.

```text
<events cwd="/home/user" ...>
<event addon="gui">{"event": "click", "window": "calc", "id": "add", "values": {"a": "2", "b": "40"}}</event>
</events>
```

The AI then calls `update("calc", '{"display": {"text": "42"}}')` and prints what the program
behind the window would print, or nothing.

| Event | When |
|---|---|
| `click` | A button was pressed (let go on it) |
| `slide` | A slider was let go; carries `value` |
| `submit` | Enter in an `input` |
| `pick` | A line of a `list` was picked; carries `value` |
| `closed` | The user closed a window |

**Every event carries `values`,** all inputs of that window, so the AI needs no `read` call.
The whole event must stay under 4000 characters; values are cut to fit, and the event says
`"cut": true`.

**A checkbox or typing is not an event.** Only what a user means as "do it" is, so that the
AI isn't called on every key.

## 4. What it costs, and what it can't do

- **Every press is one model call:** a few seconds and some cents. A calculator works, but
  answers each press after a pause. What must be instant, like a button looking pressed or
  text appearing as it's typed, is the child's own work and costs nothing.
- **The event budget holds:** `event_budget_usd`, 0.25 by default, counted since the user
  last typed a command. A window clicked for long with nobody at the keyboard pauses.
- **Inside a full-screen program,** a press waits until the program ends (events don't reach
  raw mode yet). At the shell prompt it arrives at once.
- **A call may take at most 10 seconds.** The window addon's start takes up to 8, so `show`
  fits; a second window starts its own child the same way.
- **pygame needs a display.** Without one, `show` returns `no display`, as the window
  addon does.

## 5. How it is built

- `addons/gui.py`, both sides in one file like `addons/window.py`: the addon above, and the
  child with `--child`. The pipe, the start, the crash report and `stop()` are copied from
  the window addon (not imported: one addon doesn't import another).
- **One child per window,** since pygame shows one window per process. At most 4 windows.
- The child draws the widgets, handles focus, typing, Backspace, scrolling, the mouse, and
  sends a line for each event; the addon's reader passes it to `emit`.
- `tests/test_addon_gui.py`: the layout check and `update` without a window, the child with
  SDL's `dummy` driver, and the events with a fake `emit`. No model calls.
- A live try at the end, by the user: open a window, press its button, see the AI answer.

---

## Open questions

1. **One layout file, or one call per widget?** My recommendation: the file (sections 1
   and 2). It's one round trip instead of one per widget, and it survives a reboot. The
   user's `create_button()` style can be added later on top of it if it's missed.

        - file
2. **"An addon with an agent": which agent?** I read it two ways:
   - **the main AI uses the addon** (what everything above describes); or
   - **the addon brings a worker agent** ([addon-agents.md](../addon-agents.md)), a "designer"
     that writes big layouts as a background job, the way the composer writes songs.
   My recommendation: the first, without a worker, at first. A layout is small enough for
   the main AI to write, and a worker adds a job's cost and wait for nothing. A `design()`
   function with `spawn` can come later without changing anything else.

            - okay no worker agent yet
3. **Pixel positions, or rows and columns that place themselves?** My recommendation:
   pixels, as asked. They are simple and exact. If the AI's windows come out crooked, a
   `"layout": "rows"` mode can come later.
        - okay
4. **More widgets** (an image, a slider, a drawing canvas, menus)? My recommendation: not in
   the first version. The seven above are enough for forms, tools and small games.
    - a slider and a text ascii art canvas. the slider only reports a value once its released.

## Order of work

1. The layout file and its check, with tests.
2. The child: drawing every widget, typing and focus, with the `dummy` driver in tests.
3. The addon: `show`, `update`, `read`, `close`, `stop`, the pipe, several windows.
4. Events through `emit`, with `values`.
5. The manual (`prompt()`): the functions, the file, the events, with one short example.
6. A live try by the user.

## As built

Where the code goes further than, or differs from, the sections above:

- **Events carry `window`,** the window's name, since up to four can be open:
  `{"event": "click", "window": "calc", "id": "add", "values": {...}}`.
- **The id `window` is reserved** in `update`: `{"window": {"title": ..., "background":
  ...}}` changes the window itself. No widget may be called `window`.
- **`update` is checked like a layout:** the changes are merged into a copy of the last
  layout and the whole is checked, so a change can't put a widget in a broken state. New
  `items` of a list, or a new `min`/`max` of a slider, let go of the old value unless the
  change gives one.
- **A canvas** is 8000 characters at most (ascii art is wide), white on black, font size 18.
  Each character is drawn in a cell of its own, so the grid stays straight even where no
  monospace font is installed.
- **Typing:** a click puts the cursor where it was; Left, Right, Home, End, Delete and
  Backspace work; Up and Down move between lines of a textarea; Tab moves between the
  inputs and textareas; Escape lets go. A user can type 2000 characters at most. No
  clipboard yet.
- **A button clicks when the mouse is let go on it,** as in other toolkits: dragged off, it
  doesn't.
- **A disabled widget** is greyed out and takes no clicks or typing.
- **A dead window still counts until it's noticed:** `show` clears closed windows before it
  counts to four.
- **One test outside the new file changed:** `tests/test_addons.py` lists every addon that
  exists, and now has `gui` too. Hallux's own code is untouched.
- **pygame** comes from the `window` extra (`pip install -e '.[window]'`); `pyproject.toml`
  was left alone, so the addon has no extra of its own.

## The first live try, 2026-10-20

The user's kittycalc, then a bare test window, got `closed` events but never a click or an
Enter. The log of `test-hallux` showed no event dropped by Hallux: they never left the addon.
**Cause:** the pipe told an answer from an event by an `"id"` key, and every click carries the
`id` of its widget, so the addon took clicks for stray answers and dropped them. `closed` has
no `id`. The tests only ever sent `closed` through a real child. **Fix:** the pipe numbers its
messages with `seq`, a key no event has, and a test now sends a click through a real child.
