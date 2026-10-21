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
