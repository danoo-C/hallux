# GUI addon: scripts that run in the window

**Status:** a proposal for the user to review, 2026-10-21. Nothing here is built. It builds
on the GUI addon as committed on branch `gui-addon` (c0b4f2d): [addon-gui.md](addon-gui.md),
[gui-fix.md](gui-fix.md), [gui-features.md](gui-features.md). As before, everything stays
inside `addons/gui.py` and its tests: Hallux's own code is not changed.

**Replaced in part, 2026-10-21:** step 2 (QuickJS in a `screen` widget) is replaced by
[web-engine.md](../web-addon/web-engine.md), HTML apps in a window of their own, for everything that
covers. Step 1 (timers and keys for `gui`) still stands: the user confirmed it is wanted
(2026-10-21).

**Where it came from:** the user asked what could move from the AI into Python, so that the
window can run more complex games such as snake, and how to keep that safe.

## In short

1. **Today every reaction that needs thinking is a model call:** seconds and cents. Local
   actions (`do`) cover what needs no thinking, but a game like snake needs a clock, state
   and logic.
2. **So the window runs a small program that the AI writes once.** The AI becomes the
   programmer, no longer the CPU. It is woken only for what deserves a model call: "game
   over, score 42".
3. **The program is JavaScript, run by QuickJS,** an engine that can reach nothing but what
   the addon hands it: no files, no network, no processes.
4. **First a cheap step with no new dependency:** timers and keys for local actions.
5. **Safety assumes the script is hostile,** and limits what it *can* do, not what it should.

---

## 1. What snake needs that the window can't do yet

| Snake needs | Today |
|---|---|
| A clock: the snake moves every 150 ms, with nobody clicking | Nothing happens without a click |
| State: the body, the direction, the food, the score | Widgets hold texts and values, no data |
| Logic: collisions, growing, random food, game over | Local actions set and append text, nothing more |
| Keys: arrows turn the snake | Keys reach inputs only |

## 2. The ways it could be done

| Way | Good | Bad | Verdict |
|---|---|---|---|
| **Local actions with timers, keys, variables and conditions** | No dependency | Snake needs lists, loops and conditions: a language, and a poorly designed one, learned from the manual | A first step, a dead end for games |
| **Python that the AI writes** | The AI writes it well | Python can't be sandboxed inside Python: `__subclasses__`, frames, `ctypes` all lead out. Safe only in an OS sandbox (bubblewrap, no files, no network, rlimits), Linux only, and one mistake in the setup runs AI code with the user's rights | Turned down |
| **A language of our own,** like the music addon's expressions | Safe by design: only what we build exists | Much work; the AI learns it from the manual and makes mistakes | Safe but costly |
| **JavaScript in QuickJS** | No reach of its own; a memory limit and an interrupt built in; the AI writes JavaScript as well as Python; a whole language: snake, Tetris, Pong, Minesweeper are easy | A new dependency, the `quickjs` package (a C extension) | **Recommended** |
| **Lua in `lupa`** | Small and fast | Its sandbox is weaker: the standard library must be stripped by hand, and loading bytecode is a known way out; the AI writes it less well | The fallback, if QuickJS fails the checks in section 8 |

---

## 3. Step 1: timers and keys, with no dependency

Small additions to the local actions of [gui-features.md](gui-features.md), enough for a
stopwatch, a countdown, a keyboard-driven calculator. Built first because they are cheap
and help even without scripts.

- **A `timer` widget,** never drawn: `{"id": "clock", "type": "timer", "every": 1000,
  "do": [...], "running": false}`. `every` is in milliseconds, at least 50.
- **Steps to drive it:** `["start", id]`, `["stop", id]`.
- **A step that counts:** `["count", id, n]` adds n to a widget whose text is a number (a
  stopwatch's seconds, a score). A text that isn't a number becomes `n`.
- **A key for a button:** `"key": "Enter"` or `"key": "7"` presses the button when that key
  is pressed while no input has the focus. A calculator works from the keyboard.
- **A timer never wakes the AI,** whatever its steps: a clock that called a model each
  second would use up the event budget in minutes.

## 4. Step 2: a `screen` widget that runs a script

```json
{"id": "board", "type": "screen", "pos": [10, 10], "size": [400, 400],
 "script": "/usr/local/share/snake/game.js", "grid": [20, 20]}
```

- **The script is a file on the machine's disk,** read through the disk handle like the
  layout. It survives a reboot, the user can read and change it in nano, and starting the
  game again costs no tokens.
- **`grid`** divides the screen into cells (here 20 × 20 pixels each) for games on a board;
  without it, the script draws in pixels.
- **The script starts when the window shows it,** and stops when the window closes, when
  `show` reads the file again, or when it calls `stop()`.

A snake, to show the size of it:

```js
let snake = [[5, 5]], dir = [1, 0], food = [10, 7], score = 0;
on("key", k => {
  const turn = {Up: [0, -1], Down: [0, 1], Left: [-1, 0], Right: [1, 0]}[k];
  if (turn && turn[0] !== -dir[0]) dir = turn;
});
every(120, () => {
  const head = [snake[0][0] + dir[0], snake[0][1] + dir[1]];
  if (outside(head) || snake.some(([x, y]) => x === head[0] && y === head[1])) {
    emit({event: "game_over", score}); stop(); return;
  }
  snake.unshift(head);
  if (head[0] === food[0] && head[1] === food[1]) { score++; set("score", {text: `${score}`}); food = place(); }
  else snake.pop();
  clear(); snake.forEach(([x, y]) => cell(x, y, "#3c3")); cell(...food, "red");
});
```

### What a script can call, and nothing else

| Function | What it does |
|---|---|
| `clear(color?)`, `cell(x, y, color)`, `rect(x, y, w, h, color)`, `text(x, y, string, color, size?)` | Draw on its own screen. Drawn once a tick, after the script has run |
| `get(id)`, `set(id, {keys})` | Read and change other widgets of the window, with the keys `update` takes. A score stays a label the AI can read |
| `on("key", fn)`, `on("click", fn)`, `on("message", fn)` | A key while the window has the focus; a click on the screen, in cells or pixels; a message from the AI (section 6) |
| `every(ms, fn)`, `after(ms, fn)` | Timers; at most 60 calls a second in all |
| `random()`, `now()` | A number from 0 to 1; milliseconds since the script started |
| `emit({...})` | Wakes the AI with an event `{"event": "script", "id": "board", "data": {...}}` |
| `stop()` | Ends the script; the screen keeps what it shows |

There is no `print`, no `eval` of anything outside the engine, no `require`, no clock of
the real world beyond `now()`, no access to the disk.

### What stays with the AI

- Writing the game, and fixing it: an error in the script reaches the AI as an event with
  the message and the line, `{"event": "script_error", ...}`.
- Everything with meaning: a story, characters, what a dialogue says.
- Saving: the script can't write a file. It `emit`s the high score, and the AI writes it.

## 5. Safety

The script must be treated as hostile. The AI may have been led to write it by text in a
file it read, and a user may be handed a script from anywhere. So the question is never
what a script should do, only what it could.

1. **No reach of its own.** No files, no network, no processes, no clipboard: only the
   functions of the table above. This is the wall that matters, and QuickJS gives it by
   default, which Python can't.
2. **Its own process.** The engine runs in the window's child, as the window does now. A
   crash or a hang takes one window down, never Hallux or the terminal.
3. **Limits:**

   | Limit | Value | When it is passed |
   |---|---|---|
   | Time of one call (a tick, a key) | 20 ms | Interrupted; three times in a row ends the script with `script_error` |
   | Memory of the engine | 32 MB | The call fails; the script ends with `script_error` |
   | Timers | 60 calls a second in all | Later ones wait their turn |
   | Size of a script | 50,000 characters | `show` refuses it |
   | Drawing | 5,000 calls a tick | The rest of the tick is dropped |
   | The child stops answering | as today | The addon kills it, as for a window that hangs |

4. **Waking the AI is costly, so it is rare.** At most one `emit` a second; more are
   dropped with a note. Then the event budget and the queue limit of Hallux hold, as for
   every event, so a script can't spend money in a loop.
5. **Keys only while the window has the focus.** pygame gets keys only then, so a script
   can't read what is typed anywhere else.
6. **A window can look like anything.** That is already so with layouts (a fake password
   box), and scripts don't make it worse. The manual says so, and every window gets a mark
   in its title: `— hallux`.
7. **A second wall, if wanted:** the child inside bubblewrap or with seccomp, as
   `os_sandbox` does for Claude Code, on Linux. Not needed while wall 1 holds; cheap where
   bubblewrap is installed.

## 6. The AI talking to a running script

A chess opponent, a quiz master, the AI's own move in a turn-based game: the AI thinks, the
script plays.

- **A new function, `tell(window, id, data)`,** hands a JSON object to the script of that
  screen, which gets it in `on("message", fn)`.
- **The script answers with `emit`,** as for anything else.
- So a game splits cleanly: the script does what is fast and dull (moving, drawing,
  counting), the AI what needs a mind, at a turn's pace.

## 7. A choice of principle

Until now, everything on a Hallux machine is imagined, except what goes through a real
tool; addons are bridges, not programs. A script that really runs makes the AI's programs
real, inside a window. I think that fits: the window is a sandbox with its own clear walls,
and nothing in it reaches the machine's disk or Hallux. But it's a change in what Hallux
is, so it's the user's call, and the answer belongs in [concept.md](../concept.md) or the
addon docs.

## 8. To check before building step 2

- That `quickjs` from PyPI installs from a wheel, without a compiler, on Linux (WSL) and on
  Windows, for the Python Hallux uses (3.13 here).
- That its memory limit and its time limit really stop a script: `while(true){}`, an array
  that grows forever, deep recursion.
- That an exception in a callback reaches Python with the message and the line.
- How fast a call into the engine is: 60 ticks a second of a few hundred `cell` calls must
  fit in a frame.
- If any of it fails: Lua in `lupa`, with its standard library stripped, checked the same
  way.

---

## Open questions

1. **Is a real program in a window acceptable for Hallux (section 7)?** My recommendation:
   yes, confined to the window, and written down as such.
2. **QuickJS, or Lua?** My recommendation: QuickJS, if it passes section 8.
3. **The script in a file, or written into the layout?** My recommendation: a file. It
   survives a reboot, the user can edit it, and the layout stays short.
4. **What if `quickjs` isn't installed?** My recommendation: the addon still loads, and a
   layout with a `screen` is refused with "scripts need the quickjs package (pip install
   quickjs)". Everything else works as now.
5. **`tell`, the AI talking to a script (section 6): now, or later?** My recommendation:
   with step 2. Without it, a script can only be started and listened to.
6. **The second wall (bubblewrap or seccomp)?** My recommendation: later, as an option,
   once scripts are used.
7. **A `— hallux` mark in every window's title?** My recommendation: yes. It costs nothing
   and says where a window comes from.

## Order of work

1. Step 1: the `timer` widget, `start`, `stop`, `count`, and `key` on buttons, with tests.
2. The checks of section 8, in a scratch folder, before anything depends on QuickJS.
3. Step 2: the `screen` widget, the engine in the child, the functions of section 4, the
   limits of section 5, `script_error`, with tests that run hostile scripts.
4. `tell` (section 6).
5. The manual: how to write a script, what it can call, its limits, a short example.
6. A live try by the user: snake, then a game where the AI plays a turn.
