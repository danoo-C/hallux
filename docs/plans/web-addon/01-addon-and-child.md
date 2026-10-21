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
