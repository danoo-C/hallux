# GUI addon: new features

**Status:** all seven features are built, 2026-10-21, not committed, at the user's "lets do
gui-features.md before i do a pr. so please build it". The five open questions were settled
by my recommendations. The user's live try is still to come. [As built](#as-built) has
where the code differs from the text below. The fixes in [gui-fix.md](gui-fix.md) came
first. As before, everything stays inside
`addons/gui.py` and its tests: Hallux's own code is not changed. The addon as built is
[addon-gui.md](addon-gui.md).

**Where it came from:** the user asked which additions make sense: panes, panels, tabs,
containers, hidden tabs the AI switches as instant layout changes, and changing the
position, size and color of any widget by its id.

## What decides it

1. **Everything the AI does is a model call:** seconds and cents. So the best additions let
   the window do something by itself, at once, without the AI.
2. **Everything the AI writes is tokens.** So additions that make layouts and updates
   shorter pay for themselves.

## In short

| # | Feature | What it gives |
|---|---|---|
| 1 | `pos`, `size` and `visible` in `update` | Move, resize, show and hide any widget by its id |
| 2 | `group`: a container | Panels, hidden pages, a scrolling area |
| 3 | `tabs` | Pages that switch at once, by a click or by the AI; hidden tabs without the bar |
| 4 | Adding and removing widgets in `update` | A chat that grows by one message, without rewriting the file |
| 5 | Local actions on buttons | A calculator whose digits appear at once, with no model call |
| 6 | `defaults` in the layout | Shorter layouts: a style written once, not on every button |
| 7 | Clicks on a canvas, with the cell | Ascii games: tic-tac-toe, minesweeper, chess |

Turned down, and later: at the end.

---

## 1. Move, resize, show and hide by id

Every widget already has an `id`, and `update` already changes `text`, `color`,
`background`, `font_size` and `enabled`. Today `pos` and `size` are locked.

- **`pos` and `size` can change.** The changed layout is checked as a whole, as now, so a
  widget can't be moved outside the window (or outside its group, point 2).
- **A new key on every widget: `visible`,** `true` by default. A hidden widget isn't drawn,
  takes no clicks and no typing, and keeps its value: it is still in `values`.
- `id` and `type` stay locked. A new type is a new widget (point 4).

```json
{"result": {"pos": [20, 40], "size": [280, 90], "color": "gold"},
 "help":   {"visible": false}}
```

## 2. Groups: panels, hidden pages, scrolling

A `group` is a widget that holds widgets:

```json
{"id": "sidebar", "type": "group", "pos": [0, 0], "size": [220, 700],
 "background": "#f0ece4", "widgets": [
   {"id": "new", "type": "button", "pos": [20, 20], "size": [180, 36], "text": "+ New chat"},
   {"id": "recent", "type": "list", "pos": [20, 80], "size": [180, 560], "items": []}]}
```

- **Its children are placed relative to the group** and must fit inside it. Moving the
  group moves them all; hiding it hides them all.
- **Ids are unique across the whole window,** at any depth, so `update`, `values` and
  events stay flat: `{"recent": {...}}` reaches a widget wherever it is.
- **`"scroll": true`** lets the children reach below the group's bottom; the wheel scrolls
  them. **`"follow": true`** keeps it scrolled to the bottom when something is added there,
  as a chat does.
- **`"border": true`** draws a thin frame.
- **Hidden pages** are groups on top of each other, all but one with `"visible": false`.
  One `update` switches a whole screen at once, without rewriting the file:
  `{"login": {"visible": false}, "main": {"visible": true}}`.

## 3. Tabs

```json
{"id": "views", "type": "tabs", "pos": [0, 0], "size": [600, 400], "value": "chat",
 "pages": [
   {"name": "chat", "title": "Chat", "widgets": [...]},
   {"name": "settings", "title": "Settings", "widgets": [...]}]}
```

- **A click on a tab switches the page in the window itself:** at once, with no model call.
- **The AI switches it with `update`:** `{"views": {"value": "settings"}}`.
- **`"bar": false` hides the tab bar.** These are the hidden tabs: pages only the AI
  switches, as instant changes of the whole layout.
- **`"events": true`** sends `{"event": "tab", "id": "views", "value": "settings", ...}` when
  the user switches. Off by default, so a switch costs nothing unless the program cares.
- A page's widgets are placed relative to the area under the bar, like a group's.
- `values` has the open page under the tabs' id.

## 4. Adding and removing widgets

Two more reserved ids in `update`, beside `window`:

```json
{"add":    {"into": "history", "widgets": [
              {"id": "msg7", "type": "text", "pos": [0, 640], "size": [560, 80], "text": "..."}]},
 "remove": ["msg1", "msg2"]}
```

- **`into`** is a group, a tab page (`"views/chat"`), or left out for the window itself.
- New ids must be unused; removing a group removes what is in it.
- **The file isn't changed.** `show` from the file brings back what the file says. The
  manual says so: a program that wants its window to survive writes the file too.
- So no widget may be called `add` or `remove`.

## 5. Local actions: clicks that cost nothing

Today a calculator's `7` is a model call before the 7 appears. A button may carry a few
steps that the window carries out by itself:

```json
{"id": "d7", "type": "button", "text": "7", "pos": [20, 180], "size": [60, 60],
 "do": [["append", "display", "7"]], "silent": true}
```

| Step | What it does |
|---|---|
| `["set", id, text]` | Sets a widget's text |
| `["append", id, text]` | Adds to the end of it |
| `["chop", id]` | Removes the last character (a calculator's ⌫) |
| `["clear", id]` | Empties it |
| `["show", id]`, `["hide", id]` | Shows or hides a widget or group |
| `["switch", tabs_id, page]` | Opens a page |

- **At most 10 steps on a button.** Their targets are checked when the layout is shown.
- **Without `silent`, the event is still sent,** after the steps, so its `values` already
  show them. With `"silent": true` the AI isn't woken.
- **The list stays this small on purpose.** No conditions, no variables, no arithmetic:
  once it has those it is a programming language, and the AI is meant to be the program.
  kittycalc's `=` still goes to the AI, which works out the result.
- On a button only, at first. `submit` on an input could take steps later.

## 6. Defaults

```json
{"name": "kittycalc", "size": [320, 470],
 "defaults": {"button": {"background": "#7a2d5c", "color": "white", "font_size": 26}},
 "widgets": [...]}
```

- One entry per type. A widget's own keys win.
- kittycalc's layout repeated the same two colors on 20 buttons; with defaults, once.

## 7. Clicks on a canvas

- **`"clickable": true`** on a canvas sends
  `{"event": "click", "id": "board", "col": 3, "row": 1, "values": {...}}`, counted in
  characters from the canvas's top left.
- Off by default, so a canvas of ascii art costs nothing.
- It makes the canvas a board for turn-based games, where each move is a turn anyway.

---

## Later

- **A progress bar.** Cheap, and it would suit addon agents' jobs. Nothing needs it yet.
- **A dropdown.** `list` already does the job; a dropdown only saves room.
- **Dialogs.** A second small window does it today (four may be open).
- **Images.** The disk handle reads text only; bringing a picture's bytes through needs more
  than this addon. Ascii art on a canvas covers much of it.

## Not needed

- **Split panes the user drags.** In a window of fixed size, laid out in pixels by the AI,
  they add little. Groups give panes without them.
- **Windows that resize and reflow** (anchors, layout managers). A lot of code; pixels have
  worked so far.
- **Key presses and timers sent to the AI.** Each would be a model call: a game loop at one
  tick a second would use up the event budget in minutes.
- **Menus and toolbars.** A row of buttons in a group does the same.
- **Drag and drop between widgets.** Complex, and nothing asks for it.
- **containerd.** It runs Docker-style containers and has nothing to do with windows; the
  containers meant here are groups (point 2).

---

## Open questions

1. **Tabs: pages inside the `tabs` widget, or tabs that point at groups by id?**
   My recommendation: pages inside. A page belongs to its tabs and nowhere else, and the
   layout reads top to bottom.
2. **How many widgets, and how deep?** Today at most 100. My recommendation: 200 in a
   window, counted at every depth, and groups at most 3 deep. A chat with a long history
   needs more than 100; deeper nesting is rarely worth its tokens.
3. **Does a button with steps still send its event?** My recommendation: yes, unless
   `"silent": true`. Forgetting `silent` costs a call; forgetting to send would make the AI
   miss a click.
4. **Do added widgets survive a `show` from the file?** My recommendation: no. The file is
   what `show` shows, and the program writes it when it wants the window kept.
5. **Should `chop` and `append` work on inputs too, not only on labels?** My recommendation:
   yes, on anything with a text. A calculator may show its expression in an input.

## Order of work

1. The fixes of [gui-fix.md](gui-fix.md).
2. Points 1 and 2 together: `pos`, `size` and `visible` in updates, and groups, with
   checks and drawing at every depth. Hidden pages work from here.
3. Point 3, tabs, and point 5, local actions: the window starts to feel instant.
4. Points 4, 6 and 7.
5. The manual (`prompt()`) for all of it, kept short: every line of it is read once a boot.
6. A live try by the user: kittycalc with local digits, and the chat app with tabs and a
   growing history.

---

## As built

Built 2026-10-21 in `addons/gui.py`, with 13 new tests in `tests/test_addon_gui.py` (49 in
all). The open questions went as recommended: pages inside the tabs; 200 widgets, groups 3
deep; a button with steps still sends its click unless `silent`; what `add` and `remove`
do is gone when `show` reads the file again; `append` and `chop` work on every widget with a
text, inputs included.

- **The window keeps a tree.** Every widget has its own `pos` and `size`; one step,
  `Gui.place`, works out where each is on the screen and what of the screen it may draw on,
  after every layout, update, scroll and local action. Drawing, clicking and typing work
  on what it gives, as before.
- **`values` also has the text of every widget a local action writes to.** Found in a
  first try: kittycalc's display is a label, which has no value, so the click on `=`
  brought the AI no expression.
- **The checks write the defaults into the layout** the addon keeps, so the window and every
  later `update` see the widgets as they are. Widgets that `add` brings get them too.
- **A widget a local action needs can't be removed** while the step is still there: the
  update is refused and says which step. Change the button's `do` in the same update.
- **The wheel** scrolls a text, textarea or list under the mouse when it has something to
  scroll, and otherwise the scrolling group around it, 20 pixels a line.
- **A tab bar** gives each page the same width. Defaults suit a dark window, as for the
  other widgets: on a light background, the AI gives `color`.
- **The manual** grew to about 6,900 characters (the music addon's is 8,500). It is read once
  a boot.
- **`check_layout` no longer changes the layout it is given:** found by a test, since the
  defaults were being written into the caller's own lists.
