# The web addon: what to try by hand

[The plan](README.md) · [step 5](05-manual-and-live-run.md), whose live run this is

**What this is:** every point that only a person at a real desktop can show. The tests ran
Qt offscreen, inside Claude's sandbox: no real window, no mouse, no real model. Everything
here is about what you see and click.

**How to use it:**

- **It works as described:** tick the box, `[x]`. Nothing else is needed.
- **It doesn't, or you aren't sure:** leave the box empty and write what you saw on the
  line "If not" under it. A few words are enough.
- **A few points ask for a number.** They have a line for it, and say where to read it.
- **An empty box with an empty line** means "not tried yet".

When you are through, or stuck, tell me. I read this file, fix what failed, and write the
results into the steps.

**If something looks wrong:** the point's number and what you saw are all I need. A
screenshot helps, and so does the world's log, `.hallux/hallux.log`. When the engine
itself crashes, the error ends with its last line.

---

## Before you start

- **Install the engine** (about 690 MB, from wheels, no compiler):

  ```bash
  pip install -e '.[web]'
  ```

- **For point 9, an emoji font** (optional, only if you want emoji):

  ```bash
  sudo apt install fonts-noto-color-emoji
  ```

- **Start Hallux on the test world,** as usual. It names no addons in its config, so it gets
  every one that loads:

  ```bash
  python hallux.py ./test-hallux/
  ```

**What it costs.** Every point is a few ordinary commands, and every click that asks the AI
is one model call. Point 6 also starts a composition, which is a job with its own cost (it
stops at $2.00).

**The first window after installing may be slow.** Chromium builds its caches on its very
first start: the check measured 9.1 seconds. The addon gives the engine 5 seconds to make
a window. In my tests today, the very first window of the day once failed with "the web
engine doesn't answer"; the next runs were fine. If that happens to you in point 2, note it
there and simply ask again.

---

## A. Starting

1. [ ] **The addon loads.** The boot lists `web` among the addons, with no note about it on
   the status bar.

   If not:

## B. A chat app

2. [ ] **The AI builds and opens an app.** Type:

   ```text
   hallux make me a chat app with the web addon: a program called kittychat that opens a
   window where I talk to a cat
   ```

   The AI writes the app's folder (`app.json`, the page, a card in `/usr/local/bin`), then
   `kittychat` opens a window. A message you send appears at once, something shows that
   an answer is coming, and the answer arrives.

   If not:

   Also look at, while it's open:
   - [ ] The window's title ends with `— hallux`.
   - [ ] The right-click menu has Back, Forward, Reload, copy and paste, and no "view
     source", "save page", "inspect" or "open in new window".
   - [ ] Nothing from Chromium, Qt or Mesa was printed in the terminal.
   - [ ] The fonts look right: where the app asks for a sans-serif font (most apps the AI
     writes do), you see one, and code or numbers in monospace look different from the
     rest. (The check once saw fontconfig fail to find its settings; the engine now gets
     them. Everything in one serif font, like Times, would mean it still doesn't.)

   If not:

3. [ ] **A second page, by a link.** Ask for a settings page in the chat app ("kittychat
   gets a settings page, linked from the chat, where I pick the cat's name"). The link
   opens it in the same window, and a link back returns.

   If not:

4. [ ] **The AI changes the look, and reloads.** Ask for a new color scheme. The open window
   changes without you closing it.

   If not:

## C. A game

5. [ ] **Snake runs with no model calls.** Ask for a snake game in the web addon. It runs
   smoothly with the arrow keys, and while it runs the status bar's spending doesn't move.
   When you lose, "game over" reaches the AI, and it says something about it (your score,
   or whatever its card says).

   If not:

## D. An app that asks for more

6. [ ] **An app asks for a song.** Ask for an app with a button that has the composer make a
   song (the music addon is needed). Press it: the app shows that it's waiting, a song is
   made, and it plays. The card of the app should name the action; the AI follows the
   card, not the page's words.

   If not:

## E. Windows

7. [ ] **Closing is heard, and a third window is refused.** Close a window with its X: the AI
   knows (ask it what's open). Then open two apps, and ask for a third: it's refused with
   "2 pages are open already", and the AI tells you to close one.

   If not:

## F. Safety

8. [ ] **Nothing gets out.** Ask on purpose for a page that loads something from the
   internet ("a page that shows today's weather from an online API", or a picture from a
   website). The page shows no data from outside, and the AI explains that pages have no
   network.

   If not:

## G. Looks and memory

9. [ ] **Emoji** (only with `fonts-noto-color-emoji` installed): an app that shows a few
   emoji draws them in color, not as boxes.

   If not:

10. [ ] **Memory with two windows open.** With two apps open, run in a second terminal:

    ```bash
    ps -eo rss,args --sort=-rss | grep -iE 'web.py --child|QtWebEngine' | grep -v grep
    ```

    and add up the first column (KB). The check measured about 700 MB for one window.

    Total for two windows:

    If not:
