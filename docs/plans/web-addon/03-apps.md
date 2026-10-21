# Step 3: apps and windows

[The plan](README.md) · the design: [apps.md](../../web-addon/apps.md), sections 1, 2 and
5; plan decisions 1 to 4, 8 and 11

**Needs:** step 2. **Changes:** `addons/web.py`, `tests/test_addon_web.py`.

After this step the AI can open an app, see it load, reload it and close it. The page
can't talk to the AI yet.

## Build

**`app.json`,** in the app's folder:

```json
{"name": "chat", "title": "Kitty chat", "size": [800, 600],
 "files": ["index.html", "style.css", "app.js", "settings.html", "icons/send.svg",
           "data/messages.json"]}
```

- `name`: letters, digits, `_` and `-`, at most 30; `title`: at most 100 characters;
  `size`: from 200 × 150 to 1600 × 1000; `files`: 1 to 200 paths, relative, without `..`,
  and `index.html` among them.
- Checked like `gui` checks a layout: every problem found, all told at once.

**The functions:**

| Function | What it does |
|---|---|
| `open_page(disk, folder)` | Reads `app.json` and every file it lists through the disk handle, checks the limits (1 MB a file, 10 MB in all), sends them to the child, which opens a window on `hallux://<name>/index.html`. Returns `{"page": name}` at once, without waiting for the page to load. An app that is open already is brought forward and keeps its files (use `reload`). A third window is refused: at most 2 |
| `reload(disk, page)` | Reads the folder's `app.json` and files again, and loads the page again. Also how a page sees data the AI saved |
| `close_page(page)` | Closes one window |
| `stop()` | Closes every window and ends the child |

A file that can't be read is one error naming it (`ENOENT`, `EFBIG`, or "not text"). Nothing
opens.

**Events,** through `emit`, as in `gui`:

| Event | When |
|---|---|
| `{"event": "loaded", "page": name}` | The page finished loading |
| `{"event": "failed", "page": name, "why": ...}` | It didn't, or the child crashed |
| `{"event": "closed", "page": name}` | The user closed the window |

**The window:** the size of `app.json`, its title followed by `— hallux`, a plain
`QWebEngineView` with no menu, no address bar, and no context menu items that leave the
page (Back, Forward, Reload stay; "Open in new window", "Save page", "View source" go).

## Tests

- `app.json` and its checks: good, bad, limits, `..`, a missing `index.html`, all problems
  at once.
- `open_page` with a stand-in disk: files read, sent, the window opened offscreen, `loaded`
  arrives; a missing file is one error and no window.
- Opening an open app brings it forward; a third app is refused; `close_page`, `stop`.
- `reload` shows a changed file.
- The user closing a window is a `closed` event; a crashed child is `failed` for each of
  its windows, and the next `open_page` starts a new child.
- Two apps open at once can't load each other's files.

## Done when

An app of several files and pages opens in a real window, links between its pages work,
`reload` shows a change, and `loaded` and `closed` reach the AI.

## As built (2026-10-21)

Built on branch `gui-addon`, committed with this text.

- **`open_page(disk, folder)`, `reload(disk, page)`, `close_page(page)`, `stop()`**, as in the
  table above. `open_page` of an app that is open answers `{"page": name, "open":
  "already"}`, so the AI knows nothing was read again. `reload` refuses if the folder's
  `app.json` now names another app. The child gets 5 seconds to take an app's files and make
  its window (`OPEN_SECONDS`); the page itself loads after the call returns.
- **`app.json`:** `check_app` finds every problem at once, as `gui`'s layouts do. Beyond the
  plan: unknown keys, a path listed twice, `app.json` listing itself, and paths that aren't
  plain (`a/./b`, `a//b`) are problems too. `title` defaults to the name, `size` to
  800 × 600.
- **Reading:** `app.json` first, then each listed file through the disk handle. The first one
  that fails ends the call with one error naming it (`<path>: ENOENT`, `EFBIG`, or `not
  text`), and nothing is started. Over 10 MB in all is refused.
- **The pages the addon knows** live on its link to the child (`pages`: name to folder). A
  `closed` event takes a page off; a crash of the child sends `failed` for each of its pages,
  with "the web engine stopped: it crashed (...)", and the next call starts a new child.
- **The window:** the title is `<title> — hallux`, sized from `app.json`. The right-click
  menu loses "Open link in new window/tab", "Save page", "View source", the downloads and
  "Inspect"; Back, Forward, Reload, copy and paste stay. Not tried by hand yet (offscreen has
  no mouse): the live run of step 5.
- **Found while testing:** Qt calls a load failed when a navigation away is refused, so a
  hostile `location = ...` would have sent `failed` while the page sat there unharmed. A
  refused main-frame navigation is now remembered, and the failure it causes isn't reported.
- **Not in the plan:** a child command `as_user`, which closes a window the way the user's
  click does, for the tests; `report` also gives the window's title. Neither is exposed to
  the AI.
- **The manual** (`prompt()`) now describes the four functions, `app.json` and the events;
  step 5 finishes it.
- **Tests:** 14 more, 33 in all: `app.json`'s checks and limits, unreadable files, 10 MB,
  loaded after return, open twice, the third page, `close_page` and `stop`, reload showing a
  change, title and size, the user's close, a crash failing both pages and a new child
  after, links between pages, a refused navigation that isn't a failure, the tools' schemas.
  Three runs in a row passed. Full suite: 1892 passed, and the sandbox test failed only
  inside my own sandbox.
- **Not done here:** "Done when" asks for a real window. Offscreen, everything above holds; a
  window on the desktop is for the live run of step 5, outside my sandbox.

