# Step 2: the walls

[The plan](README.md) · the design: [web-engine.md](../../web-addon/web-engine.md),
sections 4, 6 and 8a

**Needs:** step 1. **Changes:** `addons/web.py`, `tests/test_addon_web.py`.

Everything that keeps a page in, built and tried before any page of the AI's is shown.

## Build

In the child, once, before any window:

- **The `hallux` scheme,** registered before the `QApplication` exists: syntax `Host`,
  flags `SecureScheme`, `FetchApiAllowed`, `CorsEnabled` (the check's set, under which the
  page's own `fetch` worked).
- **A profile in memory:** `QWebEngineProfile` with no storage name, so off the record. No
  cookie, cache or `localStorage` outlives the window.
- **The settings:** `LocalContentCanAccessRemoteUrls`, `LocalContentCanAccessFileUrls`,
  `JavascriptCanOpenWindows`, `PluginsEnabled`, `DnsPrefetchEnabled`,
  `AllowRunningInsecureContent`, `JavascriptCanAccessClipboard`: all off. (Clipboard here
  means a script reading it; the user's own Ctrl+C and Ctrl+V in an input still work.)
- **The interceptor:** every request whose scheme isn't `hallux` is blocked. Each blocked
  request is counted per window, and the first few go to the child's log, for debugging.
- **The scheme handler:** serves `hallux://<app>/<path>` from a dictionary of files the
  addon sent (step 3 fills it), with a content type from the extension (`html`, `css`, `js`,
  `mjs`, `svg`, `json`, `txt`, `md`); anything else is `text/plain`. A path not in the
  dictionary is a 404. An app sees only its own dictionary.
- **New windows:** `createWindow` returns nothing, so `window.open` and `target=_blank`
  open nothing.
- **Chromium's own sandbox stays on.** Never `--no-sandbox` or
  `QTWEBENGINE_DISABLE_SANDBOX`. If it can't start somewhere, the addon says so instead of
  turning it off.

## Tests

A page of hostile requests, as in the check (8a), with a trap server on 127.0.0.1. All of
these must be blocked, and the trap server must get nothing:

`fetch` to 127.0.0.1, https and `file:`, XHR, WebSocket, `sendBeacon`, EventSource, a Worker
from outside, `<img>`, CSS `url()`, `<link rel=prefetch>` and `preconnect`, `<iframe>`, a
form, `location = ...`, `<meta http-equiv=refresh>`, `window.open`, `<a target=_blank>`
clicked by script.

And:

- the page's own files load, by relative and absolute paths and by `fetch`;
- `../` and `%2e%2e` stay inside the app (a 404, never another app's file);
- one app can't load another app's file (`hallux://other/x.js`);
- the profile is off the record, and `localStorage` is gone when the window is closed and
  opened again.

## Done when

Every hostile request is blocked and counted, nothing reaches the trap server, and a
page's own files are served.
