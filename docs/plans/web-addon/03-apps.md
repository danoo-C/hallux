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
