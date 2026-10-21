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

## As built (2026-10-21)

Built on branch `gui-addon`, not committed when written.

- **Everything of "Build" above is in the child,** with one profile **per window**, not one
  for all: a profile in memory lives as long as its child, so `localStorage` would have
  outlived a closed window. A window's own profile goes with it, and also carries its own
  interceptor and scheme handler, so an app is never handed another's files.
- **Two layers against leaving the app:** the interceptor (blocks, counts, keeps the first
  50 addresses and logs the first 5), and `acceptNavigationRequest`, which refuses a
  navigation away and leaves the page where it was (`location =`, a form, a meta refresh).
  `hallux://<other app>/` is blocked like the internet.
- **A second wall, found while testing.** A `<link rel=preconnect>` opened two TCP
  connections to the trap server that the interceptor never saw: a socket with no request.
  The check (8a) missed it because its trap counted requests, not connections. Chromium now
  gets `--proxy-server=socks5://127.0.0.1:1` with `--proxy-bypass-list=<-loopback>`: every
  connection it opens goes to a proxy that isn't there, localhost included. SOCKS5 leaves
  host names to the proxy, so no name is looked up either. Plus
  `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`, so WebRTC can't use UDP of
  its own (it sent nothing here, but that may depend on the machine). The flags go in
  `QTWEBENGINE_CHROMIUM_FLAGS`, which replaces any the user set, so `--no-sandbox` can't
  slip in. On the application's command line, Chromium ignored them. A DNS rule
  (`--host-resolver-rules`) can't be passed this way, because the variable is split on
  spaces; SOCKS5 makes it unneeded.
- **Also turned off, beyond the plan:** downloads are cancelled (a page could save a file
  to the user's real disk), permission requests (camera, microphone, location,
  notifications) are denied, full screen is refused, and the HTTP cache is in memory.
- **`data:` and `blob:` pass the wall:** a page makes them itself and they reach no network,
  and inline images and icons are common in what the AI writes. The plan said only
  `hallux://`.
- **The scheme handler:** decodes the path (`%2e%2e` included), makes it absolute, then takes
  `..` away, so no path climbs out of the app; `/` is `index.html`, `folder/` is
  `folder/index.html`. A missing file is a 404 to the page.
- **For step 3, already in the child:** the commands `open` (an app's files, title, size),
  `close` and `report` (what a window blocked and its console, for the tests and the log;
  the addon doesn't expose it). Events `loaded`, and `failed` when a page didn't load or its
  process crashed. Closing a window isn't reported as a failure. The AI can't reach any of
  this yet: step 3 adds `open_page` and its checks.
- **Tests:** 6 more, 19 in all. A hostile page with `fetch` (local, https, `file:`, another
  app), XHR, WebSocket, `sendBeacon`, EventSource, a Worker, `window.open`, `<a
  target=_blank>`, `location =`, a form, a meta refresh, `<img>`, CSS `url()`, `<iframe>`,
  prefetch, preconnect and dns-prefetch. The trap server records every socket opened and
  every request, and gets nothing. Also: the page's own files and their types, `../` and
  `%2e%2e`, another app's file, storage gone after closing, a preconnect alone, closing is no
  failure. Both leak tests fail with the proxy wall removed, and pass with it.
- **Chromium's own sandbox stays on**, also in the tests. Inside my sandbox it runs with its
  first layer missing, but pages load.
- **Full suite:** 1878 passed. The sandbox test failed only because it ran inside my own
  sandbox, as before.

