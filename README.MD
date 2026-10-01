# Hallux

**A hallucinated Linux machine in your terminal.**

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)
![Claude Agent SDK](https://img.shields.io/badge/built%20with-Claude%20Agent%20SDK-d97757)
![Platform: Linux / WSL](https://img.shields.io/badge/platform-Linux%20%7C%20WSL-555)

Hallux looks and feels like a shell, but nothing you type is executed. A Claude agent *is* the
machine: its kernel, its shell and every program on it. It imagines what a real Linux system
would print, character by character, while a real folder on your computer serves as its disk.
Files you create really exist, and the machine remembers who it is across reboots. You can
reshape it in plain language.

```text
$ python hallux.py ~/hallux-world
[    0.000000] Linux version 6.1.0-25-amd64 (debian-kernel@lists.debian.org) ...
[  OK  ] Reached target multi-user.target - Multi-User System.

Debian GNU/Linux 12 hallux tty1

user@hallux:~$ echo "print(sum(range(10)))" > sum.py      # a real file appears on disk
user@hallux:~$ python3 sum.py                             # ...and its run is imagined
45
user@hallux:~$ hallux make my prompt green and bold
hallux: prompt saved to ~/.bashrc
user@hallux:~$ sudo apt install -y cowsay
...
user@hallux:~$ cowsay moo
 _____
< moo >
 -----
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\
                ||----w |
                ||     ||
```

## Features

- **Every character comes from the AI:** the boot log, the prompt, program output and error
  messages. The terminal only passes your keys in and the AI's text out.
- **A real disk:** the machine's `/` is a folder you choose. Redirects, `rm`, `mv`, and the
  file I/O of programs it simulates all happen for real, inside that folder only.
- **Memory across reboots:**
  - The OS it pretends to be, its packages and its invented hardware are written down in the
    folder.
  - Settings live where Linux keeps them (`/etc/hostname`, `~/.bashrc`).
  - `reboot` brings back the same machine.
- **`hallux <anything>`:** talk to the machine's maker. Change the prompt, the mood, the OS, or
  the rules of reality, and the change persists.
- **Full-screen programs:**
  - **Block mode**, for `nano`, `vim`, `less` and `man`: editing happens locally, and only
    action keys go to the AI.
  - **Raw mode**, for `top`, `htop`, games and menus: every key and click goes to the AI, with
    optional live updates.
- **A modern terminal:**
  - colors and window titles;
  - streaming output, shown while it's being written;
  - Tab, Ctrl-C, Ctrl-L and other keys are handled by the machine;
  - mouse clicks in full-screen programs.
- **A status bar:** a bottom row owned by Hallux shows what the AI is doing, the model, the cost
  so far and how long the last answer took. The AI can never draw on it.
- **Addons:** real hardware for the machine, one Python file each. The example opens a real
  window on your desktop that the machine can read and paint.
- **Safe by construction:**
  - the AI has no tools except Hallux's own and the addons you install;
  - every path is jailed to the machine's folder;
  - only harmless escape codes reach your terminal;
  - optionally, the Claude Code process runs under bubblewrap.

## How it works

```text
  you ──keys──▶  hallux.py  ──<input>ls</input>──▶  Claude agent (the "machine")
                (terminal)  ◀──<screen>…</screen>──  no built-in tools; only hallux's:
                    │                                     │
                    ▼                                     ▼
             your terminal app                  path-jailed file tools
             (colors, mouse,                    + the machine's memory
              status bar)                                 │
                                                          ▼
                                            ~/hallux-world/  (the machine's "/")
```

1. **The terminal wraps each line** with the current directory, the time and the screen size,
   and sends it to the agent.
2. **The agent decides what a real machine would do.** It reads and writes the folder through
   a small set of tools (`list_dir`, `read_file`, `write_file`, …), imagines everything else,
   and answers with the exact screen output and the next prompt.
3. **The terminal shows the answer as it's written.** It keeps only safe escape codes and pins
   its status bar to the bottom row.

The full design, including block mode, raw mode, the memory model and the security model, is
in [docs/concept.md](docs/concept.md).

## Requirements

- **Python 3.11+**
- **Linux, or Windows through WSL.** macOS will likely work but hasn't been tested.
- **A modern terminal** with Unicode and 24-bit color: Windows Terminal, GNOME Terminal, kitty,
  WezTerm, iTerm2, …
- **Access to Claude:** a logged-in [Claude Code](https://claude.com/claude-code) on the same
  machine, or an Anthropic API key in `ANTHROPIC_API_KEY`. The Claude Agent SDK, which ships
  Claude Code, is installed for you.
- **Optional:** [bubblewrap](https://github.com/containers/bubblewrap) (`bwrap`) for the OS-level
  sandbox.
- **Optional:** pygame, for the example addon (see [Addons](#addons)).

## Installation

```bash
git clone https://github.com/danoo-C/hallux.git
cd hallux
python install.py
```

`install.py` creates a virtual environment in `.venv` and installs Hallux and its dependencies
into it. `hallux.py` switches into that environment by itself, so there's nothing to activate.

## Usage

```bash
python hallux.py ~/hallux-world                         # power on (the folder is created if needed)
python hallux.py ~/hallux-world --model claude-sonnet-5-5 --effort medium
python hallux.py ~/hallux-world --script commands.txt   # run commands from a file, headless
python hallux.py ~/new-world --check reboot             # build a machine, check it survives a reboot
```

The first boot invents a new machine (a minimal Debian 12 by default). Later boots bring the
same machine back.

> **Use a dedicated folder.** The machine can change or delete anything inside it, and that's
> the point. Hallux refuses to use your home folder. Running `git init` in the world folder gives
> you snapshots of the whole machine.

### Keys

| Keys | What happens |
|---|---|
| Typing, arrows, Backspace, Home/End, ↑/↓ | Line editing, handled instantly by the terminal |
| Ctrl-C, Ctrl-D, Ctrl-Z, Ctrl-L, Ctrl-R, Tab, F1–F12, … | Sent to the machine, which reacts like bash or the running program would |
| **Ctrl+Shift+Del**, or **Ctrl-C three times within a second** | Hard power-off: Hallux quits immediately, whatever the AI is doing |

### The `hallux` command

```text
hallux make my prompt green and bold
hallux every error message should rhyme
hallux this machine actually runs Arch Linux
hallux install a text adventure called dungeon
hallux                                   # list the active rules
hallux forget the rhyming thing
```

Settings that bash can express go into `~/.bashrc`; everything else becomes a rule in the
machine's memory. Either way, the change survives a reboot.

## Addons

An addon gives the machine a real ability it can't imagine, the way a sound card does. It is
one Python file in `addons/`, at the root of this repo. The AI gets the addon's functions as
tools and decides what to do with them. An addon defines no commands.

- **The machine learns about its addons at boot,** and reads an addon's manual before it
  first uses it.
- **Every machine gets every addon that loads.** A world names the ones it wants with
  `addons = ["window"]` in its `config.toml`, or none with `addons = []`.
- **A broken addon is skipped.** The status bar shows a note, and the reason is in the log.
  It never keeps the machine from starting.
- **An addon can report events,** such as a button pressed in its window. The AI hears them
  only after it has asked to listen, and each event it hears is a model call. A budget,
  `event_budget_usd`, limits what events may spend while you aren't typing.

### The example: a real window

`addons/window.py` opens a window on your desktop, with a text box and a `Send` button. The
machine can read the box and paint the window. It needs pygame:

```bash
.venv/bin/python -m pip install -e ".[window]"
```

The addon brings functions, not commands, so you create the program that uses them:

```text
user@hallux:~$ hallux install a program called window: "window open" opens the addon's
window, "window paint" reads its text box and paints the background that color, "window
watch" listens to the window and paints it whatever is sent, until Ctrl-C
user@hallux:~$ window open
user@hallux:~$ window paint                               # after typing tomato into the box
painted the window tomato
user@hallux:~$ window watch                               # now Send, or Enter, paints by itself
```

### Writing an addon

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

- **The first line of the docstring** is the summary the machine sees at boot.
- **`prompt()`** returns the manual.
- **`EXPOSED`** lists the functions the AI may call. Nothing else in the file is reachable.
- **Each function** needs a docstring and type hints (`str`, `int`, `float` or `bool`). It
  returns a small dictionary, and it returns quickly: after 10 seconds the AI gets an error.
- **Optional:** `stop()`, called when a boot ends, to close whatever is still open; and
  `connect(emit)`, to report events.

The design is in [docs/addons.md](docs/addons.md) and [docs/addon-events.md](docs/addon-events.md).

> **An addon runs with your full rights.** It runs inside Hallux, outside the path jail and
> outside `os_sandbox`. Putting a file into `addons/` is the same as running it, so only
> install addons you trust. No machine can write to that folder.

## Configuration

Each machine reads optional settings from `<world>/.hallux/config.toml`. Command-line flags
override them. The machine itself can't see or change this file.

```toml
# Every setting is optional. Defaults: Opus 5.5 at low effort, no budget cap, status bar on.
model = "claude-opus-5-5"        # which Claude model runs the machine
effort = "low"                   # low, medium, high, xhigh, max
fallback_model = "claude-haiku-4-5"
max_budget_usd = 2.0             # stop a boot after spending this much
status_bar = true                # the bottom status row
tick_budget_usd = 0.25           # live updates in raw mode, per program run
event_budget_usd = 0.25          # addon events, since the last line you typed
addons = ["window"]              # the addons this machine gets; left out: all that loaded
keep_transcripts = false         # let Claude Code also keep its own session transcript
os_sandbox = false               # run Claude Code under bubblewrap
```

## Cost and speed

**Every command is a call to a Claude model.** It usually takes a few seconds, and it costs
tokens. The status bar shows the running cost of the session, and the per-answer cost is in
the machine's log. A few ways to keep it in check:
- **Choose a faster model,** such as Sonnet or Haiku, or a lower effort.
- **Set `max_budget_usd`** to cap what a boot can spend.
- **Rely on partial redraws:** full-screen programs only resend the rows that change.
- **Give a machine only the addons it uses.** Each addon adds its tools to every request,
  and every event it reports to a listening machine is a call of its own.

## Safety and privacy

- **The agent has no built-in tools,** so it has no shell and no file access of its own. It
  can only call Hallux's tools, and every path goes through a single jail. Paths outside the
  world folder, symlinks pointing out of it, and the machine's own memory folder are all
  refused.
- **Only harmless terminal codes reach your terminal:** colors, cursor movement, erasing and
  titles. Clipboard writes, answer-back queries, mode changes and similar codes are dropped.
- **No transcript is kept by Claude Code** unless you enable `keep_transcripts`. Hallux keeps
  its own log in `<world>/.hallux/hallux.log`.
- **`os_sandbox = true`** runs the Claude Code process under bubblewrap. The filesystem is
  read-only, your home folder is hidden except Claude Code's login, and `/tmp` is private.
- **Passwords stay on your computer.** At a password prompt (`sudo`, `passwd`, `ssh`) nothing
  you type is shown, and Hallux checks it itself against a salted hash in
  `<world>/.hallux/passwords.json`. The AI only learns whether it was right. A new machine
  has no password and accepts any; `passwd` sets one.
- **Addons are the exception to the jail.** An addon is Python code that runs with your full
  rights, and what it returns goes to the model. Hallux only loads addons from `addons/` in
  this repo, never from a folder a machine can write to. See [Addons](#addons).
- **Everything else the machine reads is sent to Anthropic's API,** because that's where the
  model runs. Don't put real secrets into a world folder.

## Project layout

```text
hallux.py            launcher (switches into .venv)
install.py           creates .venv and installs everything
hallux/
  app.py             command line: interactive, --script, --check
  machine.py         one agent session per boot; the main loop
  protocol.py        the wire format, streaming, and the terminal-code filter
  terminal.py        real terminal I/O, keys, hard exit, status bar pinning
  blockmode.py       full-screen programs: block mode and raw mode
  statusbar.py       the bottom status row
  disk.py, tools.py  the path jail and the agent's tools
  addons.py          loading addons, calling their functions, their events
  passwords.py       password prompts: checked locally, never sent to the AI
  prompt.md          the system prompt: most of the machine's behavior
  script.py          headless runs and the reboot check
  sandbox.py         optional bubblewrap wrapper
  config.py          config.toml and flags
addons/              the addons: window.py is the example
docs/                design, roadmap and next steps
tests/               unit and integration tests (no model calls)
```

## Development

```bash
.venv/bin/python -m pytest -q
```

The test suite runs without any model calls. It drives the terminal through prompt_toolkit pipes
and the machine through a fake model. Behavior that depends on the model itself, like fidelity
and persistence, is checked with `--check reboot` and `--script`.

## Documentation

- [docs/concept.md](docs/concept.md): the full design and its reasoning
- [docs/roadmap.md](docs/roadmap.md): what's built and what's planned
- [docs/next-steps.md](docs/next-steps.md): the upcoming features, in detail
- [docs/light-and-keys.md](docs/light-and-keys.md): the status bar, the hard exit and the key rule
- [docs/addons.md](docs/addons.md): addons, and [docs/addon-events.md](docs/addon-events.md):
  their events

## License

MIT. See [LICENSE](LICENSE).
