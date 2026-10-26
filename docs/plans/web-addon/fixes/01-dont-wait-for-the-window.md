# Fix 01: `open_page` doesn't wait for a slow first window

[The fixes](README.md) · [the plan](../README.md) · built on [step 1](../01-addon-and-child.md)
(the child) and [step 3](../03-apps.md) (`open_page`)

**Status:** planned 2026-10-26, from a read-only look at the user's report (the fixes'
[README](README.md) has it and the logs). The user chose this fix, and said "create the
new branch and start the fixes" without a word on the decisions at the end: built with
them as proposed. **Built** 2026-10-26 on branch `web-fixes`: see "As built" at the end.

**Changes:** `addons/web.py` (the addon's side only: `open_page`, `_Link`, the other
functions' check for a page still opening, the manual in `prompt()`),
`tests/test_addon_web.py`, `docs/web-addon/web-engine.md` and `docs/web-addon/apps.md`
(their "As built"), `docs/plans/web-addon/live-run-checklist.md` (the note on a slow first
window).

## What happens

1. The child starts at the first call that needs it and says hello as soon as Qt's
   application exists (`child_main`). Chromium isn't started yet.
2. `open_page` sends `open` and waits `OPEN_SECONDS`, 5 seconds, for the answer.
3. The child builds the `Window` in Qt's thread before it answers. The first window's
   `QWebEngineProfile` and page start Chromium: its browser side, its GPU and zygote
   processes. That blocks the thread. Measured on 2026-10-21: 9.1 seconds the very first
   time, 1.2 seconds for a first real window with warm caches. After a restart of the PC
   or WSL the caches are cold, and the logs show more than 5 seconds about half the time.
4. After 5 seconds the addon gives up: "the web engine doesn't answer". The page is not
   put in `link.pages`.
5. The child knows nothing of that. It finishes the window, which appears, and answers
   `ok`. Nobody waits for that answer: `_answer` drops it at the next question.
6. **The window is now cut off.** Its `loaded` and its asks still reach the AI as events,
   but every `reply`, `tell` or `reload` for it fails with "no page called kittystory is
   open". The user sees an error and a window that works only on the page's side.
7. The next `open_page` of the same app finds the child warm. It isn't in `link.pages`, so
   the addon sends `open` again, and the child closes the old window and opens a new one,
   at once.

The design asked for this not to happen: "`open_page` mustn't wait for the very first
start ... It returns once the window is starting, and the page's being ready (or failing)
arrives as an event" ([web-engine.md, 8a](../../../web-addon/web-engine.md#8a-what-the-check-found-2026-10-21)).
The build kept the wait. Step 5 saw the failure once in a test run and left it
([step 5](../05-manual-and-live-run.md), "Seen once").

The child can't answer before the window is made: building it is what blocks Qt's thread.
So the fix is on the addon's side.

## What to build

1. **`open_page` takes a slow window as "starting"** (decision 1). It still waits
   `OPEN_SECONDS` for the answer. If none comes, it puts the page in `link.pages` as it
   would on `ok`, marks it as opening, and returns `{"page": name, "starting": true}`
   instead of failing. A page that answers in time returns as now.
2. **An answer that comes late is taken by the reader thread,** not dropped (decision 2).
   `_Link` keeps a table `late`: seq to what it was for. When `_answer` gives up on an
   `open`, it puts the seq there. `_read` looks at every answer: one whose seq is in
   `late` is handled there and never queued.
   - `ok`: the page stops being "opening". No event of its own: the page's `loaded` (or
     `failed`) follows from the child, as for any window.
   - An error: the page leaves `link.pages`, and the AI gets
     `{"event": "failed", "page": name, "why": <the error>}`.
   - **The race:** an answer can arrive between the timeout and the entry in `late`. Both
     sides take one small lock of the `_Link`: `_answer`, holding it, looks into the queue
     once more before it writes `late`; `_read`, holding it, checks `late` before it
     queues.
3. **A page that never opens fails out loud** (decision 3). When a page has been opening
   for `OPENING_SECONDS`, 60, the addon sends `close` for it without waiting for the
   answer, takes it out of `link.pages`, and the AI gets `{"event": "failed", "page": name,
   "why": "the window didn't open within 60 seconds"}`. A `threading.Timer`, started when
   the page is marked opening, cancelled when its answer comes.
4. **The other functions say "still opening"** for such a page (decision 4). Until its
   answer comes, Qt's thread is still busy with the window, so any question would only
   time out after 2 seconds with "the web engine doesn't answer":
   - `open_page` of the same app returns `{"page": name, "starting": true}` again, without
     asking;
   - `reload`, `reply`, `tell` and `close_page` fail at once with "the page kittystory is
     still opening: wait for its loaded event";
   - `stop()` works as now: it ends the child, and the window with it;
   - the page counts toward the 2 windows at a time.
5. **The window the user closes** while it is still opening sends `closed`, which already
   takes the page out of `link.pages`; it also leaves the opening mark.
6. **The manual** (`prompt()`) gets one sentence under `open_page`: "It may return
   `"starting": true`: the web engine is still starting, and the window follows in a few
   seconds; its loaded or failed event tells you how it went. Until then the page's other
   functions say it is still opening." That keeps the AI from telling the user the app
   failed.
7. **The log** gets one line when a page goes to "starting" and one when its late answer
   comes, with the seconds it took. That shows in the user's next runs how long a cold
   start really is.
8. **`OPEN_SECONDS` stays 5.** Hallux gives a call 10 seconds (`hallux/addons.py`,
   `TIMEOUT`), and the child's start can take up to 9 of them when the child starts in the
   same call. Raising it can't fix a cold start.

## Tests

With `fake_child` (a script that plays the child), and `OPEN_SECONDS` and `OPENING_SECONDS`
made short:

- A child that answers `open` after 1.5 seconds, with `OPEN_SECONDS` at 0.5:
  `open_page` returns `starting`; the page is in `link.pages`; a second `open_page`
  returns `starting` without a message to the child; `reply`, `tell`, `reload` and
  `close_page` fail with "still opening"; after the late `ok`, `reply` reaches the child.
- The late answer is an error: a `failed` event with that error, and the page is gone.
- No answer at all, `OPENING_SECONDS` at 1: a `failed` event that says 1 second, the page
  gone, and the child got a `close` for it.
- The race: an answer put in the queue just before `late` is written is taken as the
  page's answer, not lost (by calling the two halves directly, not by timing).
- `closed` from the child while the page is opening: the page is gone, and the timer
  doesn't fire.
- The old behaviour where it was right: a window that opens in time returns
  `{"page": name}`, as `test_open_page_returns_at_once_and_loaded_follows` checks now.
- The real child, offscreen: the existing tests pass unchanged.

## Done when

- The tests pass, and the whole suite (`--deselect tests/test_sandbox.py`).
- **By hand, the user's:** restart WSL (`wsl --shutdown` in Windows, then open the
  terminal again), start Hallux in `danika` and run `kittystory`. The window opens, and
  the AI says nothing failed. The log has the "starting" line and the seconds the window
  took.

## Decisions of this fix

My proposals, 2026-10-26; not confirmed yet.

| # | Proposal | Why |
|---|---|---|
| 1 | **A window that is slow is "starting", not failed:** `open_page` returns `{"page": name, "starting": true}` after `OPEN_SECONDS` | What the design asked for in 8a; the window does come, so an error is wrong |
| 2 | **The reader thread takes late answers,** through a table of the seqs given up on | Today a late answer is dropped at the next question, so a late error would never be told |
| 3 | **60 seconds, then a loud `failed`** and a `close` for the window | A window that never comes must not wait in silence (the user's "fail loudly"); 60 is far beyond the 9.1 seconds of a first start ever measured |
| 4 | **"Still opening" at once,** for every function but `stop()` and `open_page` | Asking would only time out after 2 seconds with a less clear error |
| 5 | **No change in the child** | It can't answer while it builds the window; everything it sends already says enough |

## As built (2026-10-26)

- **`_Link.ask_or_later(message, seconds, later)`** is the one new way to ask: it waits as
  `ask` does, and on a timeout looks into the queue once more under `late_lock`; if the
  answer still isn't there, `later(seq)`, called under that lock, returns the function that
  takes the answer. `_read` gives an answer whose seq is in `late` to that function, outside
  the lock, and queues the rest. Fix 02's `warm` can use it as it is.
- **The timeout is an error of its own,** `_NoAnswer`, a `WebError` with the same words, so
  `ask_or_later` tells it from a child that is gone. `ask` still raises it as before.
- **`window_later(name, folder, seq)`** puts the page in `pages` and `opening`, and starts the
  timer, all under `late_lock`, so the late answer can't come before the page is marked.
- **`_never_opened`** (the 60 seconds) takes `_lock`, then `late_lock`, the same order as every
  call; it drops the page's entry in `late`, so a window that comes after all has its answer
  dropped, and sends `close` with a zero wait through `ask_or_later`. The event says "the
  window didn't open within 60 seconds".
- **The "still opening" check is in `_folder_of`,** which `reload`, `reply`, `tell` and
  `close_page` already call: one place.
- **The log:** the addon writes to `hallux.web`, under Hallux's own logger, so its lines land
  in the world's `hallux.log`: "the window takes longer than 5 s; it is starting", then
  "the window came after N s", or a warning when it failed or never came. No addon logged
  before; it uses only Python's `logging`, nothing of Hallux.
- **One test of the plan was wrong:** "the window the user closes while it is still
  opening" can't happen with the real child: Qt's thread is busy making the window, so the
  user's close comes after the answer. The test sends `closed` just before the late answer
  instead, and the code handles both orders.
- **Tests:** 7 new in `tests/test_addon_web.py` (53 in all), six with a stand-in child that
  is slow to make its window (`slow_child`), and one with the real engine, given 1 ms to make
  its window. All 7 fail with the old `web.py` and pass with the new. The whole suite: 2399
  passed; one failure is not this fix's: `test_hpm_store.py::test_the_store_is_found_from_the_three_variables`
  reads the user's real `~/.config/hallux/hpm.toml` (its `store_home({...})` names no
  `HPM_CONFIG`), which exists since 2026-10-25.
- **Not checked:** a real cold start. That is the user's try in "Done when".
