# The web addon: fixes after the build

[The plan](../README.md) · fixes for what the user's own use of the web addon turned up,
after the five steps were built. One file per fix; each says what went wrong, why, and
what to build.

| Fix | What | Status |
|---|---|---|
| [01](01-dont-wait-for-the-window.md) | The first window after Hallux starts often fails with "the web engine doesn't answer", and then opens anyway, cut off from Hallux | **Built** 2026-10-26 (see its "As built"); the user's cold-start try is still to come |
| [02](02-start-the-engine-early.md) | The first window waits for Chromium to start; start it while Hallux boots | **Built** 2026-10-26 (see its "As built"); the user's cold-start try is still to come |

Both come from a read-only look at the user's report on 2026-10-26: "when [I] restart
hallux, open a big app like kittystory, it says web doesnt respond, the window stays open
and then after i close the window manually and then start kittystory again, it launches
fast and it works". The user chose both fixes ("1 and 2 sounds good").

**Build 01 first.** It makes a slow start harmless; 02 makes it shorter, and uses 01's way
of taking an answer that comes late. 01 alone fixes the bug.

Both change only `addons/web.py`, its tests and the docs: no file of Hallux itself.

## What the logs show

Every world's `hallux.log` under `~/hallux-distros/` was read, from 2026-10-22 on:

- **10 failures, all on the first `open_page` after Hallux started** (danika, test-kittystory,
  oliver-hpm, oliver-tab). Of 21 first windows in that time, 10 failed this way, and one
  more for a bad `app.json`. No later window ever failed so.
- **The newest one** (danika, 2026-10-26): `open_page` of kittymusic at 10:29:02.238, the
  error at 10:29:07.776. That is the child's start and hello (about half a second) and the
  5 seconds `open_page` waits for the window (`OPEN_SECONDS`). The app is 24 KB, so the size
  of what is sent plays no part.
- **The second try is fast** (test-kittystory, 2026-10-25): the first `kittystory` failed at
  16:01:12; the next, 13 seconds later, opened its window in 3 seconds.

## Why the first `kittystory` is slow anyway

Most of it is the AI, not the engine. The first `kittystory` of 2026-10-25 took **88
seconds, 32 model turns, $0.45**: the AI read some 25 files (every character's card,
memory and looks, the packs, the places) and wrote the first `state.json` and `tree.json`,
which alone took about 50 seconds. Only then did it call `open_page`. The second took 5.6
seconds, 3 turns, $0.03: it had all that already. Making that shorter is kittystory's own
work (what its program card tells the AI to do at start), not one of these fixes.
