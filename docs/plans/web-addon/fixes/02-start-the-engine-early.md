# Fix 02: start the web engine while Hallux boots

[The fixes](README.md) · [the plan](../README.md) · built on [step 1](../01-addon-and-child.md)
(the child) and [fix 01](01-dont-wait-for-the-window.md) (late answers)

**Status:** planned 2026-10-26, from a read-only look at the user's report (the fixes'
[README](README.md) has it). The user chose this fix; the decisions at the end are my
proposals, not confirmed yet. **It begins with a check** (free, no model), because two
things it rests on are not measured yet.

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
