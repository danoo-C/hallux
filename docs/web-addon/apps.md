# Web apps: many files, many pages, and the AI as the backend

**Status:** a proposal, 2026-10-21. Nothing is built. Its questions are decided (see
[Decisions](#decisions)); [the plan](../plans/web-addon/README.md) is next. It builds on
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
