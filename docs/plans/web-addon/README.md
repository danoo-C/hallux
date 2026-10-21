# Plan: the web addon

**Status:** written on 2026-10-21, for the user to confirm. Nothing is built. The design it
follows is in [docs/web-addon/](../../web-addon/README.md): [web-engine.md](../../web-addon/web-engine.md)
(the engine, its walls, and the check that held) and [apps.md](../../web-addon/apps.md)
(apps of many files, the AI as their backend). Every question of both is decided. The
decisions this plan takes on its own are in [a table below](#decisions-of-this-plan): **the
user confirmed all of them on 2026-10-21** ("the decisions look good"), and chose to build
on branch `gui-addon`. **Decision 1 changes apps.md:** an app lists its files, and
they are read when the app opens, not when the page asks for them.

**How this plan is laid out.** Like the plans of the config panel and addon agents: this
file holds what the steps share, and every step has a file of its own. A step is built and
committed by itself, only when the user says so.

**The user's rule:** Hallux's own code is not changed. Everything is `addons/web.py`, its
tests and its docs. The one exception the user allowed (2026-10-21) is one line in
`pyproject.toml`: the `web` extra, so that `pip install -e '.[web]'` installs PySide6.

## In short

1. **The addon and its child:** `addons/web.py` loads when PySide6 is installed, and starts
   one Qt process that will hold every web window. The `web` extra.
2. **The walls:** the engine's profile in memory, its settings, the interceptor that lets
   only `hallux://` through, pages served from memory. Tried with hostile pages.
3. **Apps:** `open_page` reads an app's folder through its `app.json`, opens a window,
   `reload`, `close_page`, `stop`, the limits, and the `loaded`, `failed` and `closed`
   events.
4. **The bridge:** `hallux.ask`, `hallux.emit` and `hallux.on` in the page, `reply` and
   `tell` for the AI, errors as events, the rate limits and the time limit of an `ask`.
5. **The manual, the docs and the live run.**

Until step 3 the AI can't open anything; until step 4 a page can't talk to it.

---

## How the parts fit

```text
 Hallux ──► addons/web.py  (the addon, in Hallux's process; never imports Qt)
               │  open_page(disk, folder)  reads app.json and its files, through the jail
               │  reload / close_page / reply / tell / stop
               │  connect(emit)            events: loaded, failed, closed, ask, page, error
               │
               │  one line of JSON per message, over a pipe (as gui does)
               ▼
            the child: python web.py --child  (one Qt process for every web window)
               ├─ a profile in memory, the settings of the walls
               ├─ the interceptor: hallux:// only
               ├─ the scheme handler: serves each app's files from memory
               └─ per window: a view, its page, the injected bridge (QWebChannel + hallux)
                     │
                     └─ Chromium's own processes, in Chromium's own sandbox
```

## Decisions of this plan

Confirmed by the user on 2026-10-21.

| # | Decision | Why |
|---|---|---|
| 1 | **An app lists its files in `app.json`,** and `open_page` and `reload` read them all, through the disk handle, before the window opens. A file not listed doesn't exist for the page | The disk handle works only during the call it was given for, and it can't list a folder. Reading when the page asks, as [apps.md](../../web-addon/apps.md) said, would need the handle after the call, which the addon contract doesn't give |
| 2 | **`app.json`** holds `name`, `title`, `size` and `files`, the paths relative to the folder. At most 200 files, 1 MB each (the handle's own limit), 10 MB in all | One small file the AI writes with the app; the limits keep `open_page` within Hallux's 10 seconds |
| 3 | **One child for all web windows,** at most 2 windows open | The check measured about 700 MB per window |
| 4 | **`open_page` returns at once,** with `{"page": name}`; the page being ready arrives as a `loaded` event, or `failed` | The very first start took 9.1 of the 10 seconds an addon call may take |
| 5 | **The time limit of an `ask` lives in `addons/web.toml`,** `ask_timeout_seconds = 120`, from 10 to 3600, read when the addon loads; without the file, 120 | The user wants to configure it, and Hallux's `config.toml` and its panel are Hallux's code. A file beside the addon is the user's to edit; a restart takes it, like any change to an addon |
| 6 | **Events need listening,** as in `gui`: the manual makes `addon_listen("web")` the step before `open_page`. An `ask` nobody hears fails at its time limit | Hallux drops the events of an addon nobody listens to, and an addon can't see who listens, so it can't fail sooner without changing Hallux |
| 7 | **Rate limits:** at most one `ask` and one `emit` a second per window, at most 10 asks waiting for a reply | What [apps.md](../../web-addon/apps.md), section 5, asked for |
| 8 | **`reload` reads the files again** from the disk; the page's data files too, so it is also how a page sees data the AI saved | The files are read when the app opens (decision 1) |
| 9 | **The child's output goes to a temporary file,** whose last line explains a crash, as in `gui` | Mesa and Chromium print much; the terminal must never see it |
| 10 | **Tests run Qt with `QT_QPA_PLATFORM=offscreen`,** and are skipped when PySide6 isn't installed | As the check did; no display needed |
| 11 | **A window's title ends with `— hallux`** | [web-engine.md](../../web-addon/web-engine.md), section 6, point 6 |

## Where the code goes

| File | What |
|---|---|
| `addons/web.py` | Both sides, as `addons/gui.py`: the addon above `--child`, the Qt child below it |
| `addons/web.toml` | Optional, the user's: `ask_timeout_seconds` |
| `tests/test_addon_web.py` | Every step's tests |
| `tests/test_addons.py` | The one line that lists every addon that exists gets `web` |
| `pyproject.toml` | The `web` extra (allowed by the user) |
| `docs/web-addon/` | What each step built, in its "As built" |

## The steps

| Step | What | Status |
|---|---|---|
| [1](01-addon-and-child.md) | The addon, its child, the `web` extra | **Built** 2026-10-21, not committed |
| [2](02-walls.md) | The profile, the settings, the interceptor, pages from memory; hostile pages | Not built |
| [3](03-apps.md) | `app.json`, `open_page`, `reload`, `close_page`, windows, `loaded` / `failed` / `closed` | Not built |
| [4](04-bridge.md) | `ask`, `reply`, `emit`, `tell`, errors, rate and time limits, `web.toml` | Not built |
| [5](05-manual-and-live-run.md) | The manual, the docs, the live run | Not built |
