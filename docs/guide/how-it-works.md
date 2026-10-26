# How Hallux works

What happens between your keyboard and the machine, how the machine remembers itself, and
what keeps it in its folder. To use Hallux, the [tutorial](tutorial.md) is enough; this is
for when you want to know why it behaves as it does. The full design, with its reasoning and
the alternatives that were turned down, is [docs/concept.md](../concept.md).

[Back to the README](../../README.md)

---

## The idea

1. **Every character on the machine's screen comes from the AI.** There is no shortcut and no
   local fast path: even `pwd`, `clear` and an empty Enter go to the model. Hallux itself is
   a dumb terminal that passes keys in and text out. Three things are not the machine's: the
   characters you type, which your terminal echoes; the **status bar** on the bottom row;
   and the **panel** (Ctrl+F12). Those two are the front of the computer's case, not its
   screen, and the AI never draws on them or learns of them.
2. **The disk is real.** `echo hi > a.txt`, `rm`, or a script that writes `out.txt` really
   change files, in the world's folder only.
3. **Everything else is imagined, and consistent:** the OS, the kernel, the CPU, the network,
   the processes, the installed packages and what programs print.
4. **The machine survives a reboot.** What defines it is written down in its folder.
5. **You choose the hardware:** the model and its effort. The machine can't change them.

The AI is a Claude agent, run through the Claude Agent SDK (Claude Code as a Python library),
with every built-in tool of Claude Code switched off. It has only Hallux's own tools.

## How one command runs

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

1. **You type a line.** Line editing (arrows, Backspace, ↑ for the last lines) happens in the
   terminal, as the kernel's line editing does on real Linux.
2. **Hallux wraps it** with what the AI shouldn't have to remember:
   ```text
   <input cwd="/home/user" time="2026-09-30T21:14:03+02:00" cols="120" rows="32">python3 fib.py</input>
   ```
3. **The agent works out what a real machine would do.** It reads `fib.py` with its
   `read_file` tool, imagines the run, and writes any file the program would write.
4. **It answers with the exact screen output and the next prompt:**
   ```text
   <screen>
   [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
   </screen><prompt>␛[1;35mcow daysi moo>␛[0m </prompt>
   ```
5. **Hallux shows it as it is written** (streaming), turns the `␛` into a real escape byte,
   keeps only the escape codes that are safe, and uses the prompt for your next line.

**Every envelope carries the window's size,** without the status bar's row, so the machine
lays out full-screen programs for your window and knows what sits under a click.

## The machine's memory

Each fact lives in exactly one place, so there is never a second, different version of it.

**1. The disk, the Unix way.** What a real machine keeps in a file, the machine keeps in that
file:

| What | Where |
|---|---|
| Hostname, OS release | `/etc/hostname`, `/etc/os-release` |
| Users | `/etc/passwd`, `/home/<user>/` |
| The prompt, aliases, exported variables, shell functions | `~/.bashrc` |
| Command history | `~/.bash_history`, written at logout as real bash does |
| Your files, scripts and invented programs | wherever they live |

**2. The memory file, `/.hallux/memory.md`,** for what a real machine never writes down but
the illusion needs: which OS it pretends to be, its invented hardware and stable facts, the
packages installed and removed, and the rules from `hallux …`. The AI reads it first at every
boot and keeps it short. The machine's OS can't see it: `ls -a /` doesn't show it, `cat`
can't read it and `rm -rf /` can't delete it. Only two memory tools reach it.

**Next to it, `/.hallux/config.toml` is the real hardware:** the model, the effort, the
budgets. No tool reaches it. The memory is the machine's soul, which the AI writes; the
config is its hardware, which only you write.

### A base image that is never written out

A real Debian has thousands of files. Hallux doesn't create them; it works like Linux's
overlayfs:

- **The lower layer is imagined:** the stock Debian 12 the memory names, known to the AI.
- **The upper layer is the real folder.** Everything that changes lands there.
- **A file is copied up the first time it is read.** `cat /etc/passwd` writes a plausible
  `/etc/passwd` to the disk first, and from then on it is real and doesn't change by
  accident.
- **Listings are merged:** `ls /usr/bin` shows the base image's usual programs and what is
  really on the disk.
- **A deleted base file is recorded** in the memory, so it stays gone.

### A boot

`reboot` and starting Hallux again are the same thing: a new agent session with an empty
context, like empty RAM. The first message brings the memory and the files that define the
machine (`/etc/hostname`, `/etc/os-release`, `/etc/passwd`, every `.bashrc` and a few more),
so a normal boot needs no tool calls, just one answer. A new machine writes its memory and
first files in that answer too.

**Memory is written as things happen:** a rule, an installed package, a fact invented that
matters (the IP address `ip a` made up), a new program. Closing the terminal never loses it.

## Programs

**The AI is the CPU.** There are three kinds of programs:

| Kind | Where it lives | How it runs |
|---|---|---|
| **Standard programs:** `ls`, `grep`, `python3`, `git`, `apt`, `htop` | The imagined base image | The AI knows how they behave, in the versions of the OS (Debian 12 means Python 3.11.2) |
| **Your scripts:** `fib.py`, `build.sh` | Real files | The AI reads the source and acts the run out faithfully |
| **Invented programs,** from `hallux install …` | A program card in `/usr/local/bin/<name>` | The AI reads the card and acts the program out |

- **Side effects are real.** A script's `open("out.txt", "w")` becomes a real write; only what
  it prints is imagined.
- **A program changes a file only when that is what the command is for:** an editor, a
  redirect, `sed -i`, a program that saves.
- **Line-based programs just work:** the `python3` prompt, `sqlite3`, `bc` and text
  adventures keep their state while they run.
- **Installs are bookkeeping.** `apt install cowsay` prints a believable log and records the
  package in the memory. There is no real network, so `requests.get(...)` gets an imagined
  answer.
- **The honest limit:** hashes, crypto, big numeric loops and exact floating point are
  invented. They stay consistent within a session, but they aren't correct.

A program card is a plain text file:

```text
#!hallux
name: moonbase
version: 0.3
A text adventure on an abandoned moon base. Starts in the airlock.
Full-screen: map on the left, room text on the right, clickable exits.
Commands: look, go <dir>, take <item>, inventory, quit.
Saves progress to ~/.moonbase/save.txt (really written to disk).
```

## Full-screen programs

Sending every key to the AI would cost seconds and money per key. Hallux solves it the way
IBM's 3270 mainframe terminals did in the 1970s.

### Block mode: `nano`, `vim`, `less`, `man`

The AI draws the whole screen and declares **fields** on it: an editor, a single line, or a
read-only pager. You type, move, scroll and click inside the fields **locally**, with no
model call. Only the keys that do something (`^O`, `^X`, `q`, …) go to the AI, with each
field's text and cursor. `nano`, `vi` and `emacs` keymaps add their local editing keys.

**A file you edit never passes through the AI.** Hallux loads it into the field from the
disk, and a save writes the field's exact text back. So big files stay cheap, and the AI
can't garble them by typing them out again.

### Raw mode: `top`, `htop`, games, menus

For programs that need every key, or that change by themselves:

- **Every key and click goes to the AI.** Keys pressed while it answers go out together with
  the next one, so a fast typist costs one call, not ten.
- **Ticks:** a program can ask to be woken every few seconds, so `top`'s numbers move. Ticks
  stop when `tick_budget_usd` is spent; the program then updates on every key.
- **Ctrl-C** reaches the program as a key.

### Job control

Ctrl-Z puts a full-screen program aside, and `fg` brings it back. **Hallux keeps the screen
and everything typed into it,** so the AI doesn't have to draw it again, and unsaved text
survives.

### Only partial redraws

Once a program is on screen, the AI sends only the rows that change. In a live check that
took about half the time of a whole screen.

## The terminal

- **Only harmless escape codes reach your terminal:** colors, cursor movement, erasing and
  window titles. Clipboard writes, answer-back queries and mode switches are dropped, so the
  machine can't reach out of your terminal.
- **The status bar** is pinned to the bottom row. Hallux's own messages go there, such as a
  network problem or an expired login: that's the hardware talking, not the machine.
- **The keyboard is read even while the AI works,** so Ctrl-C interrupts an answer, and the
  hard exit (Ctrl+Shift+Del, or Ctrl-C three times) always works.
- **Passwords** are read with echo off and checked by Hallux, against a salted hash. The AI
  only hears whether they were right.

## Addons and background jobs

**An addon is real hardware:** one Python file in `addons/`, whose functions become tools of
the AI. A window on your desktop, a sound card, a web engine. The machine learns of its
addons at boot and reads an addon's manual before it uses it. An addon can report
**events** (a button pressed), which the machine hears once it has asked to listen.

**An addon can bring an agent:** a second Claude session that does a long task in the
background, in one folder, without a screen, while you go on at the shell. Its work lands
when it ends well. `ps` and `jobs` list it, and `kill` ends it.

Both are in the [addons guide](addons.md).

## Safety

- **The agent has no built-in tools,** so it has no shell and no file access of its own. It
  can only call Hallux's tools, and every path goes through one jail. Paths outside the
  world, symlinks pointing out of it, and the machine's own `/.hallux` folder are refused.
- **Only harmless terminal codes reach your terminal** (see above).
- **No transcript is kept by Claude Code** unless you set `keep_transcripts`. Hallux keeps
  its own log in `<world>/.hallux/hallux.log`.
- **`os_sandbox = true`** runs the Claude Code process under bubblewrap: the filesystem
  read-only, your home folder hidden except Claude Code's login, and a private `/tmp`.
- **Passwords stay on your computer** (see above).
- **Addons are the exception to the jail.** An addon is Python code that runs with your full
  rights, and what it returns goes to the model. Hallux loads addons only from `addons/` in
  its own folder, never from a folder a machine can write to.
- **A background job reaches less than the machine does.** It works in one folder the
  machine names, never `/`, a home folder itself or a system folder. It creates new files
  and changes only the files it was given. Its work stays in private copies until it ends
  well, and never replaces a file somebody changed meanwhile. It has no screen and no
  access to the memory, and it can't start a job.
- **Everything the machine reads is sent to Anthropic's API,** because that's where the model
  runs; a job's reads too. Don't put real secrets into a world.

## Where to read more

The design documents in `docs/` record how each part was decided and built:

| Document | What |
|---|---|
| [concept.md](../concept.md) | The whole design and its reasoning |
| [light-and-keys.md](../light-and-keys.md) | The status bar, the hard exit and which keys go where |
| [config-panel.md](../config-panel.md) | The panel |
| [addons.md](../addons.md), [addon-events.md](../addon-events.md) | Addons and their events |
| [addon-agents.md](../addon-agents.md) | Agents, background jobs and job control |
| [addon-music.md](../addon-music.md) | The music addon and its score format |
| [gui-addon/](../gui-addon/README.md), [web-addon/](../web-addon/README.md) | The window and web addons |
| [hpm/](../hpm/README.md) | hpm, the package manager |
| [roadmap.md](../roadmap.md) | What is built and what may come |
