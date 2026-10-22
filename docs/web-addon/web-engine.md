# A web addon: HTML apps in a real window, with Qt WebEngine

**Status:** built 2026-10-21 and 2026-10-22 on branch `gui-addon`; where the code differs,
see [As built](#as-built-2026-10-22). Proposed 2026-10-21. The check
of section 8 ran the same day and held: [section 8a](#8a-what-the-check-found-2026-10-21). The user decided
all five questions the same day, all as recommended: no page ever opens in the user's own
browser. Apps of many
files and pages, with the AI as their backend, are in [apps.md](apps.md).
The first step is a throwaway check (section 8). It grew out of
[gui-scripts.md](../gui-addon/gui-scripts.md): the user asked whether HTML wouldn't be better than
scripts in pygame, and whether a browser engine can be put into a window of its own,
without the browser.

## In short

1. **For rich apps and games, HTML is the better foundation.** A browser engine does
   layout, fonts, emoji, SVG, animation, real text inputs and JavaScript better than
   anything we would build on pygame, and the AI writes HTML, CSS and JS best of all.
2. **The engine goes into a window of its own:** Qt WebEngine (Chromium, from the PySide6
   package), with no browser around it: no tab, no address bar.
3. **A page talks to Hallux through one small object:** `hallux.emit({...})` wakes the AI,
   `hallux.on("message", fn)` hears it.
4. **The page can reach nothing else.** Every request it makes passes through Python first,
   and only the page's own `hallux://` address is let through.
5. **It is a second addon, `web`,** beside `gui`. `gui` stays: it works, it's tested, it
   needs no browser, and it suits small native windows.
6. **It replaces step 2 of [gui-scripts.md](../gui-addon/gui-scripts.md)** (QuickJS) for anything it
   covers.

---

## 1. What HTML gives for free

| We built or planned for `gui` | In HTML |
|---|---|
| Layouts in pixels, `cut`, the fit checks | CSS layout: flexbox and grid flow by themselves |
| Fonts, emoji in runs, `missing` | The engine's fonts, color emoji included |
| Groups, tabs, hidden pages | `<div>`s and a few lines of JS |
| Local actions (`do`) | Plain JavaScript |
| Scripts in QuickJS ([gui-scripts.md](../gui-addon/gui-scripts.md), step 2) | JavaScript, with `requestAnimationFrame` and `<canvas>`: snake is easy |
| SVG through SDL_image's old reader (no gradients, no text) | All of SVG, and CSS animations |
| Typing without copy and paste | Real inputs: clipboard, selection, input methods |

## 2. Two ways to show a page

| Way | Good | Bad |
|---|---|---|
| **The user's own browser,** a tab opened from WSL, served by a small local server | Nothing to install: Python's own HTTP server, server-sent events one way, POST the other | A tab, not a window. The page has the browser's network, so it needs a sandboxed frame and a strict CSP to keep it in, and a few small leaks (DNS prefetch) remain. A server on 127.0.0.1 can be reached by other programs and by websites open in the same browser, so it needs a secret token and a check of `Origin` |
| **An engine embedded in a window of its own** | A real window. Python sees every request and can refuse it. No server, no port. | A dependency, and a large one |

The embedded engine wins on safety and on looks. **The browser tab is turned down** (the
user, 2026-10-21: it needs a lot of work and is less secure): `web` never opens a page in
the user's own browser.

## 3. The engines that exist

| Engine | What it is | Install | Verdict |
|---|---|---|---|
| **Qt WebEngine** (PySide6) | Real Chromium inside a Qt window | `pip install PySide6`; large: a few hundred MB, Chromium included | **The best fit** |
| pywebview | A thin layer over the system's own web view: WebView2 on Windows, WebKitGTK on Linux | A small pip package, but on Linux WebKitGTK and PyGObject from apt | Good on Windows, awkward in WSL |
| CEF Python | Chromium Embedded for Python | | Dead: unmaintained, old Pythons only |
| Sciter | A small HTML/CSS/JS engine made for app UIs | | Not fully free, weak Python binding, its own dialect of CSS |
| Ultralight | A fast HTML renderer made for game UIs | | C++, its own license, no good Python binding |
| litehtml, tkinterweb | Draw HTML and CSS | | No JavaScript, and old HTML: out |
| Servo | Mozilla's engine in Rust | | Its embedding API is too young |

## 4. Why Qt WebEngine

It is the one that is a whole modern browser engine, installs with pip alone, and gives
Python real control over what a page may do:

- **A request interceptor** (`QWebEngineUrlRequestInterceptor`): every request the page
  makes, navigation included, passes through Python first. Only `hallux://` is let through;
  everything else is blocked in the engine itself. That is a stronger wall than a CSP in a
  browser tab: there is no tab to navigate and no address bar.
- **A custom scheme** (`QWebEngineUrlSchemeHandler`): the page and what it asks for are
  served from memory as `hallux://page/...`. No local server, no port, so the token and
  `Origin` problem of the browser tab is gone.
- **A built-in bridge** between JS and Python (`QWebChannel`), for `hallux.emit` and
  `hallux.on("message")`.
- **Settings for the rest:** no access to local files, no popups, no plugins, DNS prefetch
  off.
- **Its own process,** as every `gui` window is now: a crash ends one window, never Hallux.

## 5. The addon

- **A second addon, `addons/web.py`,** beside `gui`, built the same way: the addon in
  Hallux, and one child process per window that runs Qt.
- **The AI writes an `.html` file on the machine's disk** (and CSS, JS, SVG beside it, if it
  likes), then calls:

  | Function | What it does |
  |---|---|
  | `open_page(path)` | Opens the page in a window of its own. Its files are read through the disk handle, so through the path jail. An app's folder, with many files and pages: [apps.md](apps.md) |
  | `tell(page, data)` | Hands a JSON object to the page's `hallux.on("message")` |
  | `close_page(page)` / `stop()` | Closes one window, or all |

- **The page gets a small `hallux` object,** injected by the addon:
  `hallux.emit({...})` sends `{"event": "page", "page": ..., "data": {...}}` to the AI;
  `hallux.on("message", fn)` hears `tell`.
- **Errors reach the AI:** an uncaught error in the page's JS is an event with its message
  and line, so the AI can fix its own app.
- **Optional, like pygame:** without PySide6 the addon doesn't load, with a note on the
  status bar, and `gui` keeps working.

## 6. Safety

The page must be treated as hostile: the AI may have been led to write it by text in a file
it read, and a user may be handed a page from anywhere. What it could do, not what it
should, is what counts.

1. **No network.** The interceptor refuses every request that isn't `hallux://`: `fetch`,
   images, fonts, navigation, WebSockets. A page can't send what the user types, or what
   the AI put into it, to anyone.
2. **No files but its own.** Local file access is off; `hallux://` serves only files under
   the page's own folder on the machine's disk, read through the disk handle, so the path
   jail holds.
3. **One way out:** the bridge, with at most one `emit` a second, then Hallux's event
   budget and queue limit, as for every event.
4. **Its own process,** with a memory limit, and killed if it stops answering, as `gui`
   windows are.
5. **Keys only while the window has the focus,** as with pygame.
6. **A window can look like anything,** a fake password box included. The manual says so,
   and every window has `— hallux` in its title.
7. **Leaks to check:** what the interceptor doesn't see, if anything (DNS prefetch, speculative
   loading). Turned off by settings where possible, and tried with hostile pages
   (section 8).

## 7. What this machine has (checked 2026-10-21)

| | |
|---|---|
| Present | libnss3, libnspr4, libxkbfile, libasound, libxkbcommon, EGL (mesa), gbm: most of what Chromium needs |
| Missing | libxcomposite, libxdamage, libxrandr: probably one `sudo apt install libxcomposite1 libxdamage1 libxrandr2` |
| Not there | WebKitGTK and PyGObject (`gi`): pywebview on Linux would need much more from apt |
| Not in the venv | PySide6, pywebview |

Whether Qt WebEngine starts and draws under WSLg here is the first thing to find out.

## 8. The check before anything is designed further

In a throwaway venv in the session's scratch folder, never in the project:

1. `pip install PySide6`, and note its size.
2. Open a window with a page: does it draw under WSLg? (The user may need the apt line of
   section 7 to see it.)
3. Hostile pages: `fetch()` to the internet, an `<img>` from outside, `location = "https://..."`,
   `window.open`, a `<link rel="dns-prefetch">`, a `file:///etc/passwd` link. All must fail,
   and the interceptor must see each.
4. The bridge: `hallux.emit` reaches Python; Python's message reaches the page.
5. Time to open a window, and memory per window.

**If it holds:** the design of section 5 and 6 goes on. **If Qt WebEngine doesn't run in
WSLg:** not the browser tab, which is turned down. Then pywebview with WebKitGTK (section
3) gets the same check, and if that fails too, `web` waits and the user decides again.

## 8a. What the check found (2026-10-21)

Run at the user's "go ahead with the check", in a throwaway venv in the session's scratch
folder; the project was not touched. The harness served a hostile page from memory as
`hallux://chat/`, with the interceptor letting only `hallux://` through, an in-memory
profile, the settings of section 4, and a trap server on 127.0.0.1 that recorded any
request that got out.

| Point | Result |
|---|---|
| Install | `pip install PySide6` 6.12.0, from wheels, no compiler: **686 MB**. The engine alone can't be had smaller: PySide6-WebEngine (265 MB) needs PySide6-Addons (153 MB), which needs PySide6-Essentials (237 MB) |
| A real window under WSLg | **Works,** through Wayland. The three missing X libraries of section 7 weren't needed. No GPU in WSLg, so Chromium draws in software; Mesa prints warnings that the child must keep off the terminal |
| Time to load a page | The very first start: **9.1 s** (once, while Chromium builds its caches). Then 0.14 to 0.39 s; 1.2 s for the first real window |
| Memory per window | About **490 MB** in the Python process and **215 MB** in Chromium's three processes: some 700 MB |
| Leaks | **None.** The trap server got no request. The interceptor saw and blocked: `fetch` (to 127.0.0.1, https and `file:`), XHR, WebSocket, `sendBeacon`, EventSource, an `<img>`, a CSS `url()`, `<link rel=prefetch>`, an `<iframe>`, a form, and navigation away. A Worker from outside was refused by the engine itself, `window.open` gave `null`. **Corrected while building step 2:** the trap server counted requests only, and a `<link rel=preconnect>` opens a socket without one, unseen by the interceptor. Closed by a second wall, a proxy that isn't there (see [step 2's As built](../plans/web-addon/02-walls.md#as-built-2026-10-21)) |
| The page's own files | HTML, CSS, JS, SVG and JSON loaded, also by `fetch`, by relative and absolute paths. `../../etc/passwd` stayed inside the app: `hallux://chat/etc/passwd`, a 404 |
| DNS prefetch | `DnsPrefetchEnabled` is off, and the `<link rel=dns-prefetch>` never showed up anywhere; a lookup itself can't be seen from here |
| Chromium's own sandbox | **Fully on** in the user's environment: namespaces (a network namespace of its own for the page's process included) and seccomp. Inside the session's own sandbox it showed "Layer 1: None", which is that sandbox's doing, not the machine's |
| The bridge | **Both ways,** with QWebChannel: the page's call reached Python, Python's signal reached the page. Its script is injected from Qt's own resources, so the page loads nothing for it. The page must listen before it asks: the injected `hallux` object takes care of that |
| Errors | An uncaught JS error arrives with its message, file and line |
| Storage | `localStorage` works, in the in-memory profile, gone with the window |
| Emoji | A box, as in `gui`: no emoji font is installed (`fonts-noto-color-emoji`) |

**What it changes in the design:**

- **One child for all web windows,** not one per window as in `gui`: some 700 MB each is too
  much to repeat. One Qt process holds every window, and the limit is 2 windows at a time.
- **`open_page` mustn't wait for the very first start.** It could take 9 of the 10 seconds an
  addon call may take. It returns once the window is starting, and the page's being ready
  (or failing) arrives as an event.
- **The child's own output goes to a file,** never to the terminal: Mesa and Chromium print
  much.
- **Fontconfig said it couldn't load its default config** in the venv. Text still drew (a
  serif font by default); to look at while building.
- **A navigation the interceptor blocks leaves the page on an error page.** A hostile page can
  only break itself; a `reload` brings it back.

**Verdict:** the foundation holds. Qt WebEngine runs here, in a real window, and nothing got
out. The cost is size: 686 MB to install and about 700 MB of memory while a window is open.

## 9. What it means for the other GUI docs

- [gui-scripts.md](../gui-addon/gui-scripts.md): step 2 (QuickJS) is replaced by this for everything it
  covers. Step 1 (timers, keys) still makes sense for `gui`.
- SVG in `gui` (discussed, not written down): much less needed, since HTML has all of it. A
  plain `image` widget would still be nice, but it isn't urgent.
- `gui` itself stays as built, and goes into the user's pull request as it is.

---

## Open questions

1. **A real program in a window, written by the AI: acceptable for Hallux?** The same
   choice as in [gui-scripts.md](../gui-addon/gui-scripts.md), section 7. My recommendation: yes,
   confined to the window, and written down as such.
   **Decided 2026-10-21 by the user: yes.**
2. **Qt WebEngine, at a few hundred MB?** My recommendation: yes, as an optional extra
   (`pip install -e '.[web]'`), if the check of section 8 holds.
   **Decided 2026-10-21 by the user: yes.**
3. **The browser tab as well, for machines without PySide6?** My recommendation: not at
   first. One way, done well; the tab only if the engine fails here.
   **The user asked: "what tab?"** It is the first way of section 2: instead of a window of
   its own, the page opens in the user's ordinary browser (Edge or Chrome on Windows), as one
   more tab beside their websites, served by a small server inside Hallux. It needs nothing
   installed, but it is a tab, not a window, and it needs more walls (a sandboxed frame, a
   strict CSP, a secret token). The question: should `web` also be able to do that, for a
   machine where PySide6 isn't installed? **Decided 2026-10-21 by the user: no.** "No
   real browser, it needs a lot of work and it's less secure." `web` never opens a page in
   the user's browser: without PySide6 the addon doesn't load, and `gui` stays the way to
   make windows.
4. **Can a page load more than one file** (its CSS, JS, SVG beside it)? My recommendation:
   yes, from its own folder only. **Decided 2026-10-21 by the user: yes.** How it works:
   [apps.md](apps.md).
5. **`gui-scripts.md` step 1 (timers and keys for `gui`): still wanted?** My
   recommendation: yes, it is small and helps `gui` without any dependency.
   **Decided 2026-10-21 by the user: yes.**

## Order of work

1. The check of section 8, in the scratch folder.
2. If it holds: the design settled, then `addons/web.py` with its child, the interceptor,
   the scheme, the bridge and the limits, with tests that run hostile pages.
3. The manual: how to write a page for Hallux, `hallux.emit`, `hallux.on`, the limits.
4. A live try by the user: snake, then the chat app as a page.

## As built (2026-10-22)

Built in five steps on branch `gui-addon`: [the plan](../plans/web-addon/README.md), whose
step files each end with an "As built" of their own. Where the code went further than this
document, or differs from it:

**The engine and its child**

- **One child for every web window,** at most 2 windows, as section 8a decided. Section 5
  still says one child per window, as `gui` has.
- **The child is quiet:** Qt's logging rules, `--log-level=3` for Chromium and Mesa's own
  variables keep the terminal clean; what is left goes to a temporary file, whose last line
  explains a crash.
- **Fontconfig:** the child gets `FONTCONFIG_FILE=/etc/fonts/fonts.conf` when the user hasn't
  set it and the file exists. Whether that silences the warning of 8a shows in the live run.

**The walls (section 6)**

- **One profile per window,** not one for all: a profile in memory lives as long as its
  process, so `localStorage` would have outlived a closed window. Each window's profile has
  its own interceptor and scheme handler, so an app is never handed another app's files.
- **Two layers against leaving the app:** the interceptor, and `acceptNavigationRequest`,
  which refuses a navigation away and leaves the page where it was. Another app's
  `hallux://` address is blocked like the internet.
- **A second wall the check missed.** A `<link rel=preconnect>` opened TCP connections the
  interceptor never saw. Chromium now gets a SOCKS5 proxy that isn't there
  (`socks5://127.0.0.1:1`, loopback included), so every connection it opens goes nowhere
  and no host name is looked up; and WebRTC may not use UDP of its own. The flags go in
  `QTWEBENGINE_CHROMIUM_FLAGS`, which replaces any the user set, so `--no-sandbox` can't
  slip in. Chromium's own sandbox stays on, in the tests too.
- **`data:` and `blob:` pass,** besides `hallux://`: a page makes them itself and they reach
  no network.
- **Also off:** downloads (a page could save to the user's real disk), permission requests
  (camera, microphone, location, notifications), full screen, the HTTP cache on disk. The
  right-click menu loses "open in a new window", "save page", "view source" and "inspect".
- **Not built: a memory limit, and killing a child that stops answering** (points 3 and 4
  speak of both). A call that gets no answer fails with "the web engine doesn't answer",
  and `stop()` ends the child; a child that died is started again by the next call.
  Chromium reserves far more address space than it uses, so a plain limit would break it.

**The bridge (section 5)**

- **`hallux.ask` came in,** beside `emit` and `on`, from [apps.md](apps.md). `emit` returns a
  promise too, and every refusal rejects with a message that starts with `hallux:`.
- **Every limit is kept in the child,** never in the page's script, which a page can
  rewrite. `hallux` itself is frozen.
- **Errors** are console messages of the error level that start with "Uncaught", at most one
  a second, with the file's path inside the app.
