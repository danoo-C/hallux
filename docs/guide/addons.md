# Addons

An addon gives the machine a real ability it can't imagine, the way a sound card does: a
window on your desktop, real sound, a web app in a window of its own. This guide shows the
addons that come with Hallux, background jobs, and how to write your own.

[Back to the README](../../README.md) · [Tutorial](tutorial.md) · [How Hallux works](how-it-works.md)

---

## 1. What an addon is

An addon is **one Python file in `addons/`,** at the root of the Hallux folder. The AI gets
its functions as tools, and decides itself what to do with them. **An addon brings
functions, not commands:** you ask the machine for the program that uses them.

- **The machine learns of its addons at boot,** and reads an addon's manual before it first
  uses it.
- **Every machine gets every addon that loads.** A world names the ones it wants with
  `addons = ["window"]` in its `config.toml`, or none with `addons = []`. Each addon adds its
  tools to every request, so a world with fewer addons is cheaper.
- **A broken addon is skipped.** The status bar shows a note, the reason is in the world's
  log, and the machine starts without it. Most often a Python package is missing: each
  addon below says what to install.
- **An addon can report events,** such as a button pressed in its window. The machine hears
  them only once it has asked to listen, and each event it hears is a model call: the budget
  `event_budget_usd` limits what events may spend while you aren't typing.

> **An addon runs with your full rights.** It runs inside Hallux, outside the path jail and
> outside `os_sandbox`. Putting a file into `addons/` is the same as running it, so only add
> addons you trust. No machine can write to that folder.

## 2. The addons that come with Hallux

| Addon | What it gives the machine | Install |
|---|---|---|
| `window` | One window with a text box and a Send button: the smallest example | `.venv/bin/python -m pip install -e ".[window]"` (pygame) |
| `gui` | Windows built from a layout file: buttons, inputs, sliders, lists, tabs | the same as `window` |
| `web` | Web apps in HTML, CSS and JavaScript, in a window of their own, with the AI as their backend | `.venv/bin/python -m pip install -e ".[web]"` (PySide6, about 690 MB) |
| `music` | A real sound card that plays score files, and a composer that writes songs in the background | `.venv/bin/python -m pip install -e ".[music]"` (numpy and pygame) |

### The window: the smallest example

`addons/window.py` opens a window with a text box and a `Send` button. The machine can read
the box and paint the window.

```text
user@hallux:~$ hallux install a program called window: "window open" opens the addon's
window, "window paint" reads its text box and paints the background that color, "window
watch" listens to the window and paints it whatever is sent, until Ctrl-C
user@hallux:~$ window open
user@hallux:~$ window paint                               # after typing tomato into the box
painted the window tomato
user@hallux:~$ window watch                               # now Send, or Enter, paints by itself
```

### gui: windows from a layout file

`addons/gui.py` draws real windows from a layout file that the machine writes on its own
disk: buttons, inputs, text areas, checkboxes, lists, sliders, groups and tabs. You click and
type in them for real; a button press comes to the machine as an event.

```text
user@hallux:~$ hallux install a calculator called calc with a real window: two inputs,
buttons for + - * /, and the result in a label
user@hallux:~$ calc
```

At most 4 windows are open at a time. The design is in
[docs/gui-addon/](../gui-addon/README.md).

### web: web apps, with the AI as the backend

`addons/web.py` opens apps the machine writes in HTML, CSS and JavaScript, each in a window of
its own. An app is a folder on the machine's disk with an `app.json` that lists its files.
**The page is the frontend, and the machine is its backend:** the page draws and animates by
itself, for free, and when it needs a mind (a chat, a story, a game's next level) it asks
with `hallux.ask`, which the machine answers.

```text
user@hallux:~$ hallux make me a demo web addon app that will showcase the web addon
user@hallux:~$ webdemo
```

That is what the GIF in the README shows.

- **The page reaches nothing outside its own app.** No network, no other app's files, no
  downloads, no camera or microphone. Storage is gone when its window closes.
- **At most 2 windows at a time;** each takes some 600 to 700 MB of memory.
- **The engine starts in the background while Hallux boots,** so the first window doesn't
  wait for it. It holds about 310 MB while no window is open.
- **Settings,** in an optional `addons/web.toml` beside the addon:

  ```toml
  ask_timeout_seconds = 120     # how long a page waits for the machine's answer: 10 to 3600
  start_engine_at_boot = true   # false: start the engine at the first window, and save the memory
  ```

The design is in [docs/web-addon/](../web-addon/README.md).

## 3. The music addon

`addons/music.py` plays music through your speakers. A song is a score file on the machine's
disk: a small text format with a tempo, instruments, patterns and a song. An instrument is
one expression in the style of bytebeat, computed for every sample at 44100 Hz and 16 bits.
The machine writes a score, calls `play`, and the sound is real. It needs numpy and pygame:

```bash
.venv/bin/python -m pip install -e ".[music]"
```

A short score:

```text
BPM = 120

INSTRUMENT pluck:
    sin(p) * decay(t, 5000) * vel >> 24

PATTERN riff 32:
    (0, 8, C4, pluck, 150)
    (+, 8, G4, pluck, 150)
    (+, 16, C5, pluck, 150)

SONG:
    (0, riff, 0, 2)
    (+, riff, -5)
    (+, riff)
```

- **`play(path, loop)`** checks the score, renders the whole song and starts it. It returns
  the length and the peak, or every problem of the score with its line. **`stop()`** stops
  the sound, and so does a halt or a reboot.
- **Ask the machine for the program you want:**

  ```text
  user@hallux:~$ hallux install a program called play: "play FILE" plays a score file with
  the music addon, "play -l FILE" loops it, "play stop" stops the sound
  user@hallux:~$ hallux write a short tune with a bass, chords and a melody to tune.score
  user@hallux:~$ play tune.score
  tune.score: 16.8 s, peak 64%
  ```

- **`check(path, loop)`** renders a score without a sound and returns what `play` would
  return for it. A song that is playing plays on.
- **`compose(request, folder, edit)`** has the composer write a song: the addon's agent,
  which works in the background (section 4). It writes one score file into the folder, or
  changes the scores listed in `edit`, and checks its work until the score is clean.

  ```text
  user@hallux:~$ hallux install a program called compose: "compose WHAT" has the music
  addon's composer write that song into ~/Music, in the background
  user@hallux:~$ compose a drum solo in four parts
  compose: job 30001 started
  user@hallux:~$ ls ~/Music                                 # the shell is free meanwhile
  user@hallux:~$
  [1]+  Done                    compose a drum solo in four parts
  compose: job 30001 wrote ~/Music/drum-solo.score (265 s)
  user@hallux:~$ play ~/Music/drum-solo.score
  ```

- **A score is an ordinary file.** It survives a reboot, you can edit it in `nano`, and
  playing it again costs one call.
- **Writing a score is the slow part:** half a minute or so for a song the machine writes
  itself, some minutes for one the composer writes at high effort. Rendering takes a
  fraction of a second.
- **To hear a score without the machine:** `.venv/bin/python tests/music_play.py FILE`.

The format, the instruments and the limits are in [docs/addon-music.md](../addon-music.md).

## 4. Background jobs

A job is real work that an addon's agent does while the machine goes on answering you. The
machine starts it by calling an addon function, such as the music addon's `compose`. The
agent is a Claude session of its own, with its own instructions, working in one folder,
without a screen.

- **A job has a pid, from 30001 up,** and it is real. `ps`, `top` and `jobs` show it among
  the processes the machine imagines, and `kill 30001` ends it.
- **The status bar shows a running job:** `music: balancing the mix · 0:48 · 21k tok`.
- **Its work lands when it ends well.** Until then nothing of it is in the folder. A job
  that is killed or fails leaves the folder as it was.
- **Its end is an event.** A machine that listens to the addon hears it at once, and bash
  prints its `Done` line. Otherwise it comes with your next line.
- **Ctrl+F12 shows the jobs.** The Agents tab lists every job and every agent that could
  start one. Enter opens Details: what the job is doing, call by call, as it happens. `k`
  kills a running job.
- **Limits:** one agent per addon, one job of it at a time, and two jobs at once over all
  addons. Each job has a budget and a time limit, and all jobs together have one: the
  `agent_…` settings in the [tutorial](tutorial.md#10-settings). By default $2.00 a job,
  $4.00 for all of them, 600 seconds.
- **A reboot or a power-off ends every job.**

The design is in [docs/addon-agents.md](../addon-agents.md).

## 5. Writing an addon

The smallest addon that loads:

```python
# addons/dice.py
"""A die: real random numbers."""
import random


def prompt() -> str:
    return "roll(sides) throws a die with that many sides and returns the number."


def roll(sides: int = 6) -> dict:
    """Throw a die."""
    return {"value": random.randint(1, sides)}


EXPOSED = [roll]
```

Save it, start Hallux again, and ask: `hallux install a program called roll that throws the
dice addon's die`.

- **The first line of the docstring** is the summary the machine sees at boot.
- **`prompt()`** returns the manual, which the machine reads before it first uses the addon.
- **`EXPOSED`** lists the functions the AI may call. Nothing else in the file is reachable.
- **Each function** needs a docstring and type hints (`str`, `int`, `float`, `bool` or
  `list[str]`). It returns a small dictionary, and it returns quickly: after 10 seconds the
  AI gets an error.
- **A file of the machine** is read through a handle, never opened by the addon itself: that
  would go around the path jail. A function whose first parameter is called `disk`, as in
  `def play(disk, path: str)`, gets one with `read_text(path)` and `write_text(path, content)`.
  The AI never sees that parameter.
- **Optional:** `stop()`, called when a boot ends, to close whatever is still open;
  `connect(emit)`, to report events; and `agent()`, for work in the background.
- **Fail loudly.** Raise an exception with a readable reason: the AI gets it as the error,
  and prints it the way the program would.

### Events

An addon that defines `connect(emit)` gets a function to report with, when it loads. Each
call reports one event, a small dictionary such as `{"event": "send", "text": "hi"}`. The
machine hears it if it listens to the addon (its tool `addon_listen`), and each event it
hears is one model call. Say in the manual which events there are. The design is in
[docs/addon-events.md](../addon-events.md).

### An addon with an agent

It has two more parts: `agent()`, which says who the agent is, and a function with a
parameter called `spawn`, which starts its job.

```python
# addons/poet.py
"""A poet: writes a poem into a folder while you go on working."""


def prompt() -> str:
    return ("write(request, folder) has the poet write a poem into that folder. It returns "
            "a pid at once, and the poem isn't there yet. Its end comes as an event.")


def agent() -> dict:
    return {
        "name": "poet",                          # how its jobs show in ps and in the panel
        "prompt": "Write the poem you are asked for as one text file in your folder.",
        "tools": [],                             # the functions of this file it may call
    }


def write(spawn, request: str, folder: str) -> dict:
    """Have the poet write a poem into this folder. Returns the pid of its job at once."""
    return {"pid": spawn(request, folder)}


EXPOSED = [write]
```

- **`agent()`** returns a dictionary. `name`, `prompt` and `tools` are required. `effort`
  asks for an effort, and `status` is the job's status line until it sets one itself.
- **`tools`** lists the functions of the addon that the agent may call. It is separate from
  `EXPOSED`: a function can be for the agent, for the machine, or for both.
- **`spawn(brief, folder, edit)`** starts a job and returns its pid at once. The AI never
  sees the parameter. A function that takes `disk` too has `disk` first.
  - `brief` is the job's task, as text: at most 2000 characters.
  - `folder` is where the job works. It has to exist, and can't be `/`, a home folder
    itself or a system folder.
  - `edit` lists up to 8 files in that folder that the job may change. Without it the job
    can only create files.
  - It raises when the job can't start, and the AI gets the reason as an error name:
    `EAGAIN` when the agent's job already runs or a budget is used up.
- **What a job can reach:** four file tools in its folder (`list_dir`, `read_file`,
  `write_file`, `edit_file`), `set_status` for one line of text, and the functions in
  `tools`. It has no screen, no memory tools, no other addon, and it can't start a job.
- **What it writes goes to private copies.** They are put in place when the job ends well:
  at most 16 files and 1 MB. If somebody changed one of the files meanwhile, nothing is
  replaced: the job's versions land beside them, with `.new` added to their names.
- **The model and the limits aren't the addon's.** The world's `config.toml` decides them.

### A window or a process of its own

An addon that shows a window, or uses a heavy library, should run it in a **child process**
and talk to it over a pipe, as `window.py`, `gui.py` and `web.py` do: one line of JSON per
message. Then a crash or a hang of the library can't take Hallux down, and Hallux itself
never imports it. Those three files are worked examples to copy from.

The design of the addon system is in [docs/addons.md](../addons.md).
