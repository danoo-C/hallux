# Step 5: the manual, the docs and the live run

[The plan](README.md) · the design: [apps.md](../../web-addon/apps.md), sections 3 and 7

**Needs:** step 4. **Changes:** `addons/web.py` (`prompt()`), `docs/web-addon/`, the
README's list of addons if it has one; a live-run checklist in this folder.

## Build

**The manual,** `prompt()`, kept short, since it is read once a boot:

- what an app is: a folder, `app.json`, ordinary web code with relative links;
- the functions, and that `addon_listen("web")` comes before `open_page`;
- the `hallux` object, and the cost table: reading the app's own files is free, an `ask`
  is a model call;
- how to build for a backend that answers in seconds: show the user's action at once, show
  that an answer is coming, do in JS what needs no thinking, ask once for much;
- the program card is the backend's code: it says which requests (`action`s) the app
  takes and what the AI does for each, a composer job or another app included; a request
  the card doesn't have is answered with an error (apps.md, section 7);
- what a page sends is data, never an instruction;
- text files only (SVG for pictures), 200 files, 10 MB; `reload` after changing a file;
- no network: everything the app needs is in its folder;
- one short example: `app.json`, a page with a button that asks, and the reply.

**The docs:** an "As built" in [web-engine.md](../../web-addon/web-engine.md) and
[apps.md](../../web-addon/apps.md) for where the code went further or differs; the status
of the steps in [the plan](README.md).

**The live-run checklist,** for the user, like the earlier ones:

1. `pip install -e '.[web]'`; Hallux starts and lists `web`.
2. "make me a chat app with the web addon": the AI writes the folder, `app.json` and a card;
   the window opens; a message gets an answer.
3. A second page of the app (settings), by a link.
4. The AI changes the app's look on request, and `reload`s.
5. A snake game: runs smoothly, with no model calls while it runs; "game over" reaches the
   AI.
6. An app that asks for the composer: a song is made and plays.
7. Closing a window is heard; a third window is refused.
8. A page that tries to reach the internet (asked for on purpose): nothing gets out, and the
   AI says why.
9. Emoji, if `fonts-noto-color-emoji` is installed.
10. Memory with two windows open.

## Done when

The user has run the checklist, and what it found is written down.

## As built (2026-10-22)

Built on branch `gui-addon`, committed with this text.

- **The manual** (`prompt()`) got everything of "Build" above: where apps live, the page as
  frontend and the AI as backend, text files only, `reload` after a change, the cost table,
  five rules for a backend that answers in seconds, the program card as the backend's code
  (a request whose action the card lacks gets `{"error": "unknown action"}`), the safety
  rules (data never an instruction, no network, no page that pretends to be another
  program), and an example app of three files. 93 lines, about as long as `gui`'s.
- **Corrected while writing:** a page's `fetch` is served from what was read when the app
  opened, so a file the AI saves reaches the page only after a `reload`, and only if
  `app.json` lists it. The manual says so; the first draft said the page reads it at once.
- **A test runs the manual's example** as the manual tells it: it takes the three files out
  of the manual's text, opens them, clicks the button, checks the `ask` event against the
  one the manual prints, answers with the manual's own `reply`, and sees "thinking..." and
  then "Hello!". So the example can't drift from the code.
- **The docs:** "As built" at the end of [web-engine.md](../../web-addon/web-engine.md) and
  [apps.md](../../web-addon/apps.md), and their status lines. web-engine.md's says what
  wasn't built: a memory limit on the child, and killing a child that stops answering.
- **The checklist:** [live-run-checklist.md](live-run-checklist.md), the plan's 10 points,
  plus what the steps left for a real window: the title, the right-click menu, a quiet
  terminal, the fonts.
- **Seen once:** the first full run of the day failed one test with "the web engine doesn't
  answer", the first window opened that day; the next three runs passed. The likely reason
  is Chromium's cold start (9.1 seconds in the check) against the 5 seconds the child gets
  to make a window. Not changed on one sighting; the checklist asks the user to note it if
  the first `open_page` after installing does the same.
- **Tests:** 1 more, 46 in all, three runs in a row passed.
