# Web apps: many files, many pages, and the AI as the backend

**Status:** built 2026-10-21 and 2026-10-22 on branch `gui-addon`; where the code differs,
see [As built](#as-built-2026-10-22). Proposed 2026-10-21. Its questions are decided (see
[Decisions](#decisions)); [the plan](../plans/web-addon/README.md) built it. It builds on
[web-engine.md](web-engine.md), whose decisions it takes as given: the `web` addon is a
second addon beside `gui`, the engine is Qt WebEngine, and a page may load more than one
file, from its own folder only.

**Where it came from:** the user asked how the AI could make apps of several files and
pages ("we mount a hallux folder and then the AI will know exactly what addresses to
encode?"), and found the AI being the backend "kinda beautiful".

## In short

1. **An app is a folder on the machine's disk.** `open_page(folder)` mounts it as the root
   of the app's own address, `hallux://<name>/`, and shows its `index.html`.
2. **The AI writes ordinary web code.** Relative links, `<link>`, `<script src>`, `fetch()`
   of its own files: all just work. There are no special addresses to learn.
3. **The page is the frontend, the AI the backend, the machine's disk the database.**
   `hallux.ask({...})` is a request; the AI answers it with `reply`.
4. **Reading costs nothing, thinking costs a model call.** A page reads its own files
   straight from the disk. Only what needs a mind goes to the AI.
5. **Writing goes through the AI, at first.** A page can't change a file by itself.

---

## 1. An app is a folder

```
/usr/local/share/apps/chat/
  index.html
  style.css
  app.js
  settings.html
  icons/send.svg
  data/messages.json
```

- **`open_page("/usr/local/share/apps/chat")`** opens a window showing
  `hallux://chat/index.html`. The app's name is the folder's last part, under the rule for
  names (letters, digits, `_` and `-`, at most 30).
- **The folder is the root of the app's address.** `href="settings.html"`,
  `src="icons/send.svg"`, `fetch("data/messages.json")` and `/style.css` all resolve inside
  it. The AI writes the web code it already knows.
- **Every file is read only when the page asks for it,** through the disk handle, so the
  path jail holds. A path that leaves the folder (`../`, an encoded `%2e%2e`, a link
  elsewhere) is refused by the addon first; the jail is the second wall behind it.
- **Each app is its own origin.** `hallux://chat/` and `hallux://snake/` can't see each
  other's files, storage or windows.
- **Several pages work both ways:** real links between `.html` files, or one page that
  switches its views in JS. A link inside the app is followed; one that leaves it is
  blocked by the interceptor ([web-engine.md](web-engine.md), section 6).

### Two limits

- **Text files only.** The disk handle reads text: HTML, CSS, JS, SVG, JSON, plain text.
  PNG, JPEG and font files can't be served. SVG covers icons and pictures, and the engine
  has the system's fonts. Reading binary files would need a change to the disk handle,
  which is Hallux's own code, so it isn't part of this design.
- **A page doesn't see files change.** After the AI edits `app.js`, it calls
  `reload(page)`. The manual says so.

## 2. The functions

| Function | What it does |
|---|---|
| `open_page(folder)` | Opens the app in a window of its own. Returns `{"page": name}` |
| `reload(page)` | Loads the page again from the disk, after the AI changed its files |
| `reply(page, id, data)` | Answers a request the page made with `hallux.ask` |
| `tell(page, data)` | Sends the page something it didn't ask for |
| `close_page(page)` / `stop()` | Closes one window, or all |

And in the page, the `hallux` object the addon puts there:

| In the page | What it does |
|---|---|
| `await hallux.ask({...})` | A request to the AI. Resolves with what `reply` sends, or fails after a time limit |
| `hallux.emit({...})` | Something happened, and nobody waits for an answer ("game over") |
| `hallux.on("message", fn)` | What `tell` sends |

## 3. The AI as the backend

A web app sends a request to a server, which runs code and answers. Here the "server code"
is the AI: it reads the request and decides what to do, and it can do everything it can
do anyway. It reads and writes the machine's files, uses other addons (a song from the
music addon, a job from an addon agent), and remembers through the machine's memory.

```js
// app.js of a notes app
const reply = await hallux.ask({action: "summarize", file: "data/notes/today.md"});
summary.textContent = reply.summary;
```

The AI gets:

```text
<events ...>
<event addon="web">{"event": "ask", "page": "notes", "id": 7,
 "data": {"action": "summarize", "file": "data/notes/today.md"}}</event>
</events>
```

and answers with `reply("notes", 7, {"summary": "..."})`.

### Reading costs nothing, thinking costs a call

| What the page does | Who does it | Cost |
|---|---|---|
| Show, animate, check a form, compute, play | The page's JS | Nothing |
| Read its own files: `fetch("data/messages.json")` | The addon, from the disk | Nothing, at once |
| Anything that needs a mind: an answer in a chat, a move, a summary, a decision | The AI, through `ask` | A model call: seconds and cents |
| Save something | The AI, through `ask` (section 4) | A model call |

### State lives on the disk, not in the AI's head

The AI shouldn't keep an app's state in its context: that is lost at a reboot, costs
tokens and can't be read by the page. An app's data lives in its folder (`data/`), where
the page reads it for nothing and where it survives a reboot. The AI reads it when it
answers, as a server reads its database.

### Apps for a backend that thinks slowly

An answer takes seconds, not milliseconds. The manual teaches what web apps do with a slow
server anyway:

- show the user's own action at once (a sent message appears before the answer);
- show that something is coming (a spinner, "thinking…");
- do in JS everything that needs no thinking;
- ask once for much rather than often for little.

Apps that suit it: a chat, games against the AI, a dungeon master, a tutor, writing
tools, anything where the answer is worth a few seconds. Apps that don't: anything that
needs an answer on every key.

## 4. Writing: through the AI, at first

A page can't write a file by itself. It asks, and the AI decides what is saved and where.

- **Why:** writing is the one power a hostile page could abuse inside its own folder:
  filling the disk, or rewriting the app's own code so that the next start does something
  else. With the AI in between, every write is a decision someone made.
- **What it costs:** a save is a model call. For a notes app that saves each keystroke, too
  slow; for one that saves when asked, fine.
- **Later, if apps need it:** `hallux.save(path, text)`, only under the app's `data/`
  folder, never its code, with a size limit per file and in all. An open question below.

## 5. Safety, beyond web-engine.md

[web-engine.md](web-engine.md), section 6, holds as it is. Mounting a folder adds:

1. **The folder is the wall.** Paths are normalized before anything is read, and any that
   leaves the folder is refused. The disk handle's jail stands behind it.
2. **Limits on what is served:** a file at most 1 MB (the disk handle's own limit), at most
   about 500 files and 20 MB in all per window. A page that asks for more gets errors.
3. **Requests are limited like events:** at most one `ask` a second, at most 10 waiting.
   They go through Hallux's event budget, so an app can't spend money in a loop.
4. **An answer that never comes:** an `ask` fails in the page after 2 minutes. The app shows
   it; nothing hangs.
5. **No storage of its own, at first.** The engine's profile is kept in memory only
   (Qt's "off the record"): no cookies, `localStorage` or cache survive the window. What an
   app keeps, it keeps in its files, through the AI.

## 6. How it fits Hallux

- **A program card points to its app.** `kittychat` in `/usr/local/bin` says: open
  `/usr/local/share/apps/kittychat`, listen to `web`, answer its requests like this. The
  card is the backend's code, the folder the frontend's.
- **The user can read and change every file** in nano, inside the machine, like any other.
- **A reboot loses nothing:** the app is files, its data is files.

---

## 7. A page asking the AI to run something

Only the AI opens windows, starts jobs and uses other addons. But a page can ask for it,
like any other request:

```js
await hallux.ask({action: "compose", request: "a calm piano song for the menu"});
```

- **The program card says which requests the app's backend takes,** and what the AI does
  for each: start the composer, open another app, play a song. The card is the backend's
  code; the page only sends requests to it.
- **What a page sends is still data, never an instruction.** The AI does what the card
  says for an action, not what the text in the request tells it to. A page that asks for
  something its card doesn't have gets an error back, like a server answering 404.
- So "composer: make me a song" from an app works: the card of that app has a `compose`
  action, and the AI starts the composer's job, as the user typing `compose` would.

## Decisions

Settled by the user on 2026-10-21. Questions they left unanswered take my recommendation,
as they said ("no answer == recommendation").

| Question | Decision |
|---|---|
| 1. May a page save files by itself, under `data/`? | No, not at first. Writes go through `ask`; direct saves later, if apps need them |
| 2. Where do apps live? | Anywhere on the machine's disk; the manual suggests `/usr/local/share/apps/<name>/` |
| 3. Storage that survives the window? | No. The profile stays in memory; what lasts is in files |
| 4. The same app open twice? | No. `open_page` on an open app brings its window forward |
| 5. How long may an `ask` wait? | **The user configures it** (the user: "we let the user configure it"). 2 minutes by default. Where the setting lives is a decision of [the plan](../plans/web-addon/README.md) |
| 6. May a page open another app? | **Not by itself, but it can ask the AI to run things** (the user: "it can ask the AI to execute an app, but no running by itself. like for example when an app sends 'composer: make me a song...' hallux should be able to execute that"). Section 7 |

## Order of work

These come after the check and the first build of [web-engine.md](web-engine.md):

1. Mounting a folder: the scheme handler serving files from the disk handle, the path
   checks, the limits, with tests of paths that try to leave.
2. `ask` and `reply`, with ids, the time limit and the rate limit.
3. `reload`.
4. The manual: an app's folder, the three `hallux` calls, the cost table of section 3, how
   to build for a slow backend, a short example app.
5. A live try by the user: a chat app of several pages, with its history in `data/`.

## As built (2026-10-22)

Built in five steps on branch `gui-addon`: [the plan](../plans/web-addon/README.md), whose
step files each end with an "As built" of their own. Where the code differs from this
document:

- **An app lists its files in `app.json`,** and they are all read when the app opens or
  reloads, not when the page asks for them (the plan's decision 1): the disk handle works
  only during the call it was given for, and can't list a folder. A file not listed doesn't
  exist for the page. A `fetch` is served from what was read, so a page sees a file the AI
  saved only after a `reload`, and only if it is listed.
- **The app's name comes from `app.json`,** not from the folder's last part. `app.json`
  holds `name`, `title` (default: the name), `size` (default: 800 × 600) and `files`.
  Unknown keys, a path listed twice, `app.json` listing itself and paths that aren't plain
  are refused, all problems in one error.
- **The limits** (section 5, point 2): 200 files, 1 MB each, 10 MB in all, not about 500
  and 20 MB.
- **Paths:** the scheme handler decodes a path, `%2e%2e` included, and takes `..` away, so no
  path climbs out of the app; `/` is `index.html`, `folder/` is `folder/index.html`.
- **The time limit of an `ask`** (decision 5) lives in `addons/web.toml`,
  `ask_timeout_seconds`, from 10 to 3600, 120 without the file. A bad file keeps the addon
  from loading, with the reason. **Since [fix 02](../plans/web-addon/fixes/02-start-the-engine-early.md)
  (2026-10-26)** it also has `start_engine_at_boot`, true by default: the engine starts
  and warms Chromium while Hallux boots, for about 310 MB while no window is open; `false`
  starts it at the first `open_page`, as before.
- **`reply` and `tell` take any JSON value,** as a string, not only an object: a reply is
  often one string. At most 3800 characters of JSON each way. `reply` says why an ask can't
  be answered: answered already, timed out, never made, or the page reloaded or closed.
- **The rate limits** are one ask and one emit a second per window, at most 10 asks waiting
  (section 5, point 3). An ask nobody listens to fails at its time limit: an addon can't see
  who listens.
- **`open_page` returns at once,** `{"page": name}`, or `{"page": name, "open": "already"}`
  when the app is open; `loaded` or `failed` follows as an event. A refused navigation and
  a window the user closed are not failures; the user's close is a `closed` event.
  **Since [fix 01](../plans/web-addon/fixes/01-dont-wait-for-the-window.md) (2026-10-26):**
  a window the engine hasn't made within 5 seconds (the first one starts Chromium) returns
  `{"page": name, "starting": true}` instead of failing; its `loaded` or `failed` follows
  as for any window, and a window that hasn't come in 60 seconds is a `failed` event. Until
  then `reload`, `reply`, `tell` and `close_page` say the page is still opening.
- **The manual** (`prompt()` in `addons/web.py`) has the cost table of section 3, how to
  build for a slow backend, the card as the backend's code (section 7), that what a page
  sends is data, no network, and a short example app. A test runs that example as the
  manual tells it.
