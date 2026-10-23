# Step 1: the addon, its child, the `web` extra

[The plan](README.md) · the design: [web-engine.md](../../web-addon/web-engine.md),
sections 4, 5 and 8a

**Needs:** nothing. **Changes:** `addons/web.py` (new), `tests/test_addon_web.py` (new),
`tests/test_addons.py` (one line), `pyproject.toml` (one line).

After this step the addon loads and can start and stop its Qt child, but opens no page.

## Build

- **`pyproject.toml`:** `web = ["PySide6"]` among the optional dependencies, beside
  `window` and `music`.
- **`addons/web.py`,** shaped like `addons/gui.py`:
  - a module docstring whose first line is the summary;
  - at the top, `if importlib.util.find_spec("PySide6") is None: raise ModuleNotFoundError`:
    without PySide6 the loader skips the addon with "No module named 'PySide6'", and the
    status bar says so;
  - **Hallux never imports Qt:** the addon side only checks that it's installed;
  - `prompt()`: a short manual for now, finished in step 5;
  - `EXPOSED`: `stop` only, until step 3;
  - `connect(emit)`, kept for later steps.
- **The child,** `python web.py --child`:
  - one `QApplication`, which holds every web window of later steps;
  - says hello on its line (`{"seq": 0, "ok": true}`), then answers messages numbered by
    `seq`, as `gui`'s pipe does after its fix;
  - its stdout is the line to the addon; everything else it, Qt, Chromium or Mesa print
    goes to a temporary file (plan decision 9);
  - `QT_LOGGING_RULES` and Chromium's log level set low, so the file stays small;
  - quits on `{"cmd": "quit"}` or when its stdin closes.
- **The addon's link to the child:** started by the first call that needs it, kept until
  `stop()`; a child that died is started again by the next call. The start may take up to
  9 seconds the very first time (8a), so starting waits at most 9 seconds and then fails
  with "the web engine didn't start".
- **Fontconfig:** the check printed "Cannot load default config file" in its venv. Find
  out why (the venv, `-I`, or the environment) and make the child find the system's fonts.

## Tests

- The loader takes the file: summary, `EXPOSED`, `connect`; skipped without PySide6.
- Loading the addon in a fresh Python never imports PySide6.
- The child starts with `QT_QPA_PLATFORM=offscreen`, says hello, answers, quits on `quit`
  and when its stdin closes.
- A child that prints a lot to stderr never garbles the line; a child that crashes is
  reported with its last line.
- `tests/test_addons.py`'s list of addons has `web`.

## Done when

The addon loads with PySide6 installed and is skipped cleanly without it; `stop()` ends the
child; nothing reaches the terminal.

## As built (2026-10-21)

Built on branch `gui-addon`, committed as b1e5b61.

- **`addons/web.py`:** the addon, with `stop` its one function, and `connect`. Its link to
  the child, `_child()`, starts the child at the first call that needs it and starts it again
  if it died; `stop()` ends it. Errors are `WebError`: "the web engine didn't start", "the
  web engine doesn't answer", "the web engine stopped", the last two with "it crashed (<its
  last line>)" when the child ended badly.
- **The child** imports `QtWebEngineWidgets` before its `QApplication`, as Qt requires, keeps
  running with no window open, and takes Hallux's messages through a Qt signal, so they are
  answered in Qt's own thread. For now it knows `ping` and `quit`; anything else is an error.
- **Quiet:** `QT_LOGGING_RULES` turns off Qt's debug, info and warnings,
  `QTWEBENGINE_CHROMIUM_FLAGS=--log-level=3` keeps Chromium to fatal errors, and
  `EGL_LOG_LEVEL` and `LIBGL_DEBUG` quiet Mesa. What is left goes to a temporary file.
- **`pyproject.toml`:** `web = ["PySide6"]`, three lines in the shape of `window` and `music`.
- **Tests:** `tests/test_addon_web.py`, 13 tests. Eleven need PySide6 and are skipped without it;
  the two that run either way check that Hallux never imports Qt and that, without PySide6,
  the addon is skipped with "No module named 'PySide6'". The pipe's failures are tried with a
  small stand-in script in the child's place: a flood on stderr, a crash at the start and
  later, a child that never says hello, an event line.
- **Tried with** PySide6 6.12.0 from the check's throwaway venv, lent through `PYTHONPATH`; the
  project's venv still has no PySide6. All 14 tests passed (with `test_addons.py`'s list);
  the full suite: 1872 passed, and the sandbox test failed only because it ran inside my own
  sandbox, as before.

**Fontconfig, not settled.** The "Cannot load default config file: (null)" of the check
doesn't appear here: offscreen, inside my sandbox, Qt finds 24 font families, and a page
finds DejaVu Sans. The check printed it only in its run outside my sandbox, where Chromium's
own sandbox was on; my run outside to compare was refused. The likely reading: the
Chromium inside the PySide6 wheel doesn't know where the system keeps fontconfig's file,
and "a serif font by default" was only a browser's usual default for a page that names no
font. The child is now started with `FONTCONFIG_FILE=/etc/fonts/fonts.conf` when the user
hasn't set it and the file exists. Whether the message is gone shows in the live run
(step 5), or in a run outside my sandbox.

