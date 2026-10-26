# Fix 02: start the web engine while Hallux boots

[The fixes](README.md) · [the plan](../README.md) · built on [step 1](../01-addon-and-child.md)
(the child) and [fix 01](01-dont-wait-for-the-window.md) (late answers)

**Status:** planned 2026-10-26, from a read-only look at the user's report (the fixes'
[README](README.md) has it). The user chose this fix; the decisions at the end were my
proposals, and the user's "okay, please do fix 2" took them as they are. **It begins with
a check** (free, no model), because two things it rests on were not measured. **Built**
2026-10-26 on branch `web-fixes`, after the check: see "As built" at the end.

**Changes:** `addons/web.py` (`connect` starts the engine in a thread; a `warm` command in
the child; one key in `addons/web.toml`), `tests/test_addon_web.py`,
`docs/web-addon/web-engine.md` and `docs/web-addon/apps.md` (their "As built").

## What happens

The child starts only at the first `open_page`, and Chromium only when the child builds the
first window (fix 01, "What happens"). So the first window of every Hallux run pays for
both: from a few seconds with warm caches to more than 5 after a restart. By the time the
AI calls `open_page`, Hallux has been running for a while: the boot alone took 23 seconds
on 2026-10-26, and kittystory's first launch spends a minute and more reading its files
before it opens the window. The engine could be started in that time.

With fix 01 the slow first window no longer fails, but it still makes the user wait.

## The check, before anything is built

In a throwaway script in the session's scratch folder, with the real child and a real
window (WSLg), nothing of the project changed:

1. **Where the time goes:** from start to hello; from `open` to the window, the first time
   and the second; and whether making a profile and a page and loading `about:blank`,
   with no window shown, takes most of the first window's time away.
2. **Whether it lasts:** if the warm page is closed again, is the next first window still
   fast? (Whether Chromium's processes stay while no page is left.)
3. **What it costs:** memory of the warm engine with no window (the child and Chromium's
   processes together), next to the 700 MB a window takes.

With warm caches the numbers are small; a cold start can't be made from inside the session
(it needs `wsl --shutdown`). So the check answers 2 and 3 and the shape of 1; the user's
by-hand run gives the cold numbers.

The check decides decision 3 below (keep the warm page, or close it). If warming saves
little, the fix stops there, written up in this file, and only fix 01 is built.

### What the check found (2026-10-26, part 1: offscreen)

A throwaway script (`warmcheck.py`, in the session's scratch folder; the project not
touched) made, in a fresh process each time: a window with nothing before it (`none`); a
warm page, kept, then a window (`keep`); a warm page, closed again, then a window
(`close`). Three runs of each. The session's sandbox keeps it from the display, so it ran
with `QT_QPA_PLATFORM=offscreen`; turning the sandbox off for it was refused.

| | none | keep | close |
|---|---|---|---|
| Making the warm page (profile, page, `about:blank` loaded) | | 0.05 s | 0.05 s |
| Making the window (what blocks the answer to `open`) | 0.04–0.05 s | 0.00 s | 0.00 s |
| The window loaded | 0.09–0.14 s | 0.03 s | 0.03 s |
| Memory with no window (the child and Chromium's processes) | 77 MB | 471 MB | 388 MB |
| Memory with the window | 484 MB | 571 MB | 485 MB |

- **The gain lasts when the warm page is closed:** Chromium's processes stay, and the
  window after it was made at once. So decision 3: **close it.**
- **What it costs:** about 310 MB while no window is open (388 against 77), from Hallux's
  start to its end. With a window open it costs nothing more (485 against 484).
- **Offscreen shows no slow start at all,** with warm caches: 0.05 s, where the user's logs
  show more than 5 s. The slow part is what offscreen leaves out (the display, Wayland,
  the GPU process in software) or cold caches. Part 2, on the real display, is the user's
  to run.

### Part 2: the real display (the user, 2026-10-26)

The user ran `warmcheck.py none` in their own terminal, on WSLg, with warm caches:

```text
MESA: error: ZINK: failed to choose pdev
{"scenario": "none", "platform": "wayland", "app_ready": 0.11, "rss_start": 79,
 "window_built": 0.29, "window_loaded": 0.39, "rss_window": 604}
```

- **The display costs little:** 0.29 s for the first window, against 0.05 s offscreen. So
  the 5 seconds and more in the logs are most likely **cold caches** after a restart of
  the PC or WSL (Chromium's libraries and resources, some 265 MB, read from the disk), not
  the display. Not measured: that needs a run right after `wsl --shutdown`.
- **That is what warming at boot moves:** whatever the first window costs, the warm page
  pays it first, in the background, during the boot (23 seconds on 2026-10-26) and the AI's
  turns before `open_page`. Part 1 showed a window made after the warm takes no time.
- **A window on the real display takes more memory,** 604 MB against 484 offscreen.
- **The verdict:** built, with decision 3 as "close the warm page". The cold numbers come
  from the user's by-hand try (the "Done when").

## What to build

1. **`connect(emit)` starts the engine in a thread of its own** (decision 1), a daemon
   thread, so Hallux's boot doesn't wait for it. `connect` is called when the addon loads,
   at power on. The thread:
   - makes the `_Link` **outside `_lock`**, so a call or `stop()` never waits for the
     child's hello (up to 9 seconds; the hard exit gives all addons 0.5);
   - then, holding `_lock`: if `stop()` came meanwhile, or a call already made a link,
     closes its own; otherwise it becomes `_link`;
   - sends `warm` and doesn't wait: the seq goes into fix 01's `late` table, and the
     answer, when it comes, writes a log line with the seconds it took. An error is a
     warning in the log, and the next `open_page` starts the child again as today.
2. **The child's `warm`** (decision 3, after the check): a profile off the record with the
   same settings off as a window's, an interceptor that lets nothing through, a page, and
   `about:blank`. Never shown, no bridge, no scheme handler, and no `loaded` event: nothing
   is told for it. Kept or closed, as the check says. It doesn't count as a page.
3. **Only where a window can be shown** (decision 2): stdin and stdout are terminals, and
   `WAYLAND_DISPLAY` or `DISPLAY` is set. So the tests (pytest takes stdout) and a run
   with `--script -` start nothing. To look at while building: whether hpm's test install
   or `hallux --script FILE` from a terminal would still warm. If so, it costs a second of
   CPU and ends with the run; say so in the "As built".
4. **A key in `addons/web.toml`** (decision 4): `start_engine_at_boot = true`, the default.
   `false` keeps today's start at the first `open_page`, for a user who rarely opens a web
   app and wants the memory back. `read_config` checks it as it checks
   `ask_timeout_seconds`: a value that isn't true or false stops the addon from loading,
   with the reason.
5. **The log** says when the engine was started at boot, and how long the warm took.

## Tests

- `connect` with a display and terminals (both faked): a child starts, and gets `warm`;
  `open_page` right after uses that child, not a new one.
- `stop()` while the thread waits for hello: `stop()` returns at once, and the child the
  thread made is closed, not kept.
- `open_page` before the thread is done: one child in the end, not two, and the page opens.
- No display, or stdout not a terminal: `connect` starts nothing.
- `start_engine_at_boot = false`: nothing at `connect`; a bad value: the addon doesn't load,
  and says why.
- The child's `warm` (offscreen, the real child): it answers `ok`, sends no event, and a
  window opened after it works as before; `report` of that window is unchanged.
- The warm page reaches no network: the `trap` test of step 2 with the warm page in place.

## Done when

- The check is written up in this file, and decision 3 taken from it.
- The tests pass, and the whole suite (`--deselect tests/test_sandbox.py`).
- **By hand, the user's:** after `wsl --shutdown`, start Hallux in `danika`, wait for the
  prompt, and run `kittymusic -w` (it opens its window soonest). The window comes without
  "starting", or with it and soon after. The log has the warm's seconds.

## Decisions of this fix

My proposals, 2026-10-26; not confirmed yet.

| # | Proposal | Why |
|---|---|---|
| 1 | **Start the engine when the addon loads,** in a thread | Hallux's own code knows nothing of this addon, and loading is the only moment the addon gets (`connect`); the boot gives it 20 seconds and more |
| 2 | **Only with terminals and a display** | Tests and scripted runs open no window, and must not start Chromium for nothing |
| 3 | **Keep or close the warm page: the check decides** | Keeping it costs memory all the time; closing it may lose the gain |
| 4 | **On by default, `start_engine_at_boot = false` to turn it off** | The user's worlds use web apps often; the memory is the price, and it's one line to give it back |
| 5 | **Not the AI's business:** nothing in the manual changes | The AI calls `open_page` as before; only the wait is shorter |

## As built (2026-10-26)

- **`connect(emit)`** starts the thread `_start_early` once (`_early`), when
  `start_engine_at_boot` is on and `_can_show()`. A second `connect`, as the tests make,
  starts nothing more.
- **`_can_show()`:** stdin and stdout are terminals, `WAYLAND_DISPLAY` or `DISPLAY` is set,
  and `QT_QPA_PLATFORM` isn't `offscreen` (the tests set it; nothing could be shown
  there). Streams that are replaced or closed count as no terminal.
- **`_start_early`** makes the `_Link` outside `_lock`. Then, holding it: if `_link` exists
  (a call started its own meanwhile) or `stop()` ran since it began (`_stops`, a counter
  `stop()` raises), it closes its child; otherwise it becomes `_link` and sends `warm`
  through fix 01's `ask_or_later` with a zero wait, so the answer goes to a function that
  writes the log line. A child that doesn't start is a warning in the log, and the first
  `open_page` starts one as before.
- **The child's `warm`:** a profile with the settings a window has off, an interceptor
  that blocks everything (`Shut`), a page that loads `about:blank`, never shown, no
  bridge, no scheme handler, no event. Once loaded, the page and then its profile are
  deleted. It answers `ok` right after making them: making the first profile is what
  starts Chromium, so the answer comes when the slow part is done.
- **The log:** "the engine started at boot in N s", then "Chromium warmed in N s", both
  counted from the thread's start; or a warning.
- **Scripted runs:** hpm's test install runs `run_script` with no addons, so it starts
  nothing. `hallux --script FILE` from a terminal loads the addons and passes
  `_can_show()`, so it warms too: a second of work, ended with the run. `--script -` fed
  through a pipe doesn't.
- **Tests:** 6 new in `tests/test_addon_web.py`, and `test_web_toml` got the new key (59
  in all): the start and the warm with a stand-in child (`boot_child`, which writes each
  child's process number), `stop()` while the child is still starting, a call during the
  start, nothing without a display or with the setting off, `_can_show()` itself, and the
  real engine's `warm` with a window after it (and the `trap` server untouched). All 7 fail
  with fix 01's `web.py` and pass with this one. The whole suite: 2405 passed; the one
  failure is the hpm test fix 01's "As built" names, not this fix's.
- **Not checked:** a real start in a terminal, on a display: the session's sandbox keeps it
  from the display. That and the cold numbers are the user's try in "Done when".
