# Step 4: the bridge

[The plan](README.md) · the design: [apps.md](../../web-addon/apps.md), sections 2, 3, 5
and 7; plan decisions 5 to 7

**Needs:** step 3. **Changes:** `addons/web.py`, `tests/test_addon_web.py`; the user may
add `addons/web.toml`.

After this step a page and the AI talk: the AI is the app's backend.

## Build

**In the page,** injected by the addon at `DocumentCreation`, in the main world, before the
page's own scripts run: Qt's `qwebchannel.js` (from Qt's resources, never served to the
page as a file), and a small `hallux` object on top of it:

| In the page | What it does |
|---|---|
| `await hallux.ask(data)` | A request. Resolves with the AI's `reply`; fails with "too many requests" or "no answer in N seconds" |
| `hallux.emit(data)` | An event nobody waits on |
| `hallux.on("message", fn)` | What `tell` sends |

The object queues calls made before the channel is ready, and connects its listener before
anything is sent (the check found that order matters).

**Events to the AI:**

| Event | When |
|---|---|
| `{"event": "ask", "page": ..., "id": 7, "data": {...}}` | A request; the AI answers with `reply` |
| `{"event": "page", "page": ..., "data": {...}}` | An `emit` |
| `{"event": "error", "page": ..., "message": ..., "file": ..., "line": ...}` | An uncaught error in the page's JS, at most one a second |

**The AI's functions:**

| Function | What it does |
|---|---|
| `reply(page, id, data)` | Answers request `id` of that page. `data` is a JSON object as a string, as `gui`'s `update` takes. An unknown or timed-out id is an error |
| `tell(page, data)` | Sends `data` to the page's `hallux.on("message")` |

**Limits** (decision 7): one `ask` and one `emit` a second per window, 10 asks waiting at
most; more fail in the page at once. `data` of an event or a reply at most 3800 characters
of JSON, as `gui`'s events. Hallux's event budget and queue hold on top of these.

**Listening** (decision 6): Hallux drops the events of an addon nobody listens to, and an
addon can't see who listens. So the manual makes `addon_listen("web")` the step before
`open_page`, and an `ask` that nobody hears fails at its time limit.

**The time limit** (decision 5): `addons/web.toml`, read once when the addon loads:

```toml
ask_timeout_seconds = 120     # 10 to 3600; how long a page waits for reply
```

A missing file means 120. A bad one (not TOML, an unknown key, a value out of range) makes
the addon refuse to load, with the reason: the loader skips it and the status bar says so,
as for any addon that fails its checks. An addon has no way of its own to the status bar.

## Tests

- `ask` → an `ask` event with an id → `reply` → the promise resolves with the data.
- An `ask` that is never answered fails after the time limit (set to 1 second in the test).
- `reply` to an unknown id, or to one that timed out, is an error.
- `emit` and `tell` both ways; calls made before the channel is ready are not lost.
- Rate limits: the second `ask` within a second fails at once; the eleventh waiting fails.
- An uncaught error arrives with its message, file and line.
- `web.toml`: missing, good, out of range, not TOML.
- With a stand-in `emit` that drops everything, an `ask` fails at its time limit.

## Done when

A page asks, the AI replies, the page shows it; `tell` reaches the page; every limit holds.

## As built (2026-10-21)

Built on branch `gui-addon`, committed with this text.

- **The page's side** (`HALLUX_JS`, after Qt's `qwebchannel.js`, read from Qt's resources)
  is injected at `DocumentCreation` in the main world, top frame only. `hallux` is frozen
  and can't be reassigned. `ask` and `emit` both return promises; every refusal (a limit,
  too big, not JSON) rejects the promise with a message starting `hallux:`. Calls made
  before the channel is ready wait for it.
- **Every limit is kept in the child,** in a `Bridge` object per window, never in the page's
  script: a page can rewrite its own `hallux`, or reach the channel directly, and gets
  nothing more by it. One ask and one emit a second (a strict second between two), at most
  10 asks waiting, at most 3800 characters of JSON both ways, one uncaught error a second.
- **The time limit** runs in the child, one timer per ask. An ask that times out, was
  answered, never existed, or belonged to a page that has since reloaded or closed, can't be
  answered: `reply` says which cases those are. Reloading and closing stop the timers.
- **`reply(page, id, data)` and `tell(page, data)`:** `data` is any JSON value as a string,
  not only an object (a reply is often one string). The plan said "a JSON object".
- **Uncaught errors** are console messages of the error level that start with "Uncaught"
  (promise rejections too). `file` is the path inside the app (`app.js`), not the whole URL.
  A page can fake one with `console.error("Uncaught ...")`, and gains only an event a second.
- **`addons/web.toml`:** `read_config` runs when the addon loads. A bad file raises
  `WebError`, and the loader skips the addon with "WebError: addons/web.toml: ...". The value
  is passed to the child with each `open`. The docstring's "nothing here calls the built-in
  open()" became: the machine's files only through the disk handle, and its own `web.toml`
  once at load. No test enforced it; it is a promise about the machine's files.
- **The manual** now has `reply`, `tell`, the `hallux` object, its limits, and every event.
  The time limit in it is the one `web.toml` set.
- **Tests:** 12 more, 45 in all: ask and reply, a timeout and a late reply, emit and tell
  with calls made before the channel is ready, each rate limit, the eleventh waiting ask, too
  big and not JSON both ways, an uncaught error with file and line (one a second), `reply`
  and `tell` without a page, an ask nobody hears, and `web.toml`: missing, good, five bad
  ones, and the addon skipped with the reason. Three runs in a row passed. Full suite: 1904
  passed, and the sandbox test failed only inside my own sandbox.

