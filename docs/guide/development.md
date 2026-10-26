# Developing Hallux

How the code is laid out, how to run the tests, and how changes are made. To write an addon
you don't need any of this: see the [addons guide](addons.md).

[Back to the README](../../README.md) · [How Hallux works](how-it-works.md)

---

## 1. Set up

```bash
git clone https://github.com/danoo-C/hallux.git
cd hallux
python install.py          # .venv, with Hallux installed editable and pytest
```

Hallux is installed **editable** (`pip install -e ".[dev]"`), so a change to the code works at
once, without installing again. `.venv/bin/hallux` and `.venv/bin/hpm` are the two commands;
`python hallux.py` switches into `.venv` by itself. For the addons, add their extras:

```bash
.venv/bin/python -m pip install -e ".[dev,window,music,web]"
```

## 2. The layout

```text
hallux.py            the launcher (switches into .venv)
install.py           makes .venv and installs everything
hallux/
  app.py             the command line: interactive, --script, --check
  machine.py         one agent session per boot; the main loop
  protocol.py        the wire format, streaming, and the terminal-code filter
  terminal.py        real terminal I/O, keys, the hard exit, the status bar's row
  blockmode.py       full-screen programs: block mode and raw mode
  statusbar.py       the bottom status row
  panel.py           Hallux's own panel (Ctrl+F12): the host with its tab row
  panel_tabs/        the panel's tabs, one file each: agents, details, files, packages, config
  importing.py       files dragged onto the window: reading the drop, the tree, the copy
  disk.py, tools.py  the path jail and the agent's tools
  addons.py          loading addons, calling their functions, their events
  agents.py          the addons' agents: background jobs, their caps and their sessions
  jobdisk.py         a job's fenced disk: one folder, private copies, the landing
  passwords.py       password prompts: checked locally, never sent to the AI
  prompt.md          the system prompt: most of the machine's behavior
  prompt_jobs.md     its last section, for a machine that can start a job
  agent.md           the rules every background worker gets
  script.py          headless runs and the reboot check
  sandbox.py         the optional bubblewrap wrapper
  config.py          config.toml and the flags
  hpm/               the package manager: manifest, archive, store, engine, migrations,
                     friends' stores on GitHub, its AI's session and prompts
addons/              window.py, gui.py, web.py, music.py and music_engine/
docs/                the guides (docs/guide/), designs, plans and their reviews
tests/               unit and integration tests, with no model calls
```

**Most of the machine's behavior is in `hallux/prompt.md`,** not in Python. A change to how
the machine acts (how it answers, what it writes to memory, how it draws a program) usually
starts there.

## 3. Tests

```bash
TMPDIR=/tmp .venv/bin/python -m pytest -q
```

- **No test calls a model.** The machine is driven by a fake model, the terminal through
  prompt_toolkit's pipes, and the addons offscreen. `HALLUX_NO_REAL_MODEL` (set by
  `tests/conftest.py`) stops any test from reaching the real one.
- **No test touches your own files.** `conftest.py` points hpm's store and config at
  temporary paths (`HPM_HOME`, `HPM_CONFIG`).
- **Pass `TMPDIR` on.** A pytest started without it may write `pytest-of-<you>/` into the
  repo's folder.
- **The addons' tests are skipped** when their Python package isn't installed.
- **Behavior that depends on the model,** such as how faithful the machine is and whether
  it survives a reboot, is checked with real runs:

  ```bash
  python hallux.py ~/scratch-world --script commands.txt   # type a file's lines, headless
  python hallux.py ~/new-world --check reboot              # build a machine, reboot it, compare
  ```

  These cost money: use a dedicated world, and `--model` with a cheap model.

**A change that draws on the terminal** (the status bar, the panel, full-screen programs)
should also be looked at on a real terminal, or on a pseudo-terminal through a terminal
emulator such as `pyte` or tmux: the pipe tests don't pin the bar or redraw the screen.

## 4. How changes are made

Hallux grows in small, explicit steps, each written down before it is built:

1. **A design** in `docs/` says what the feature is and why, with its open questions and
   the answers they got (for example [config-panel.md](../config-panel.md) or
   [hpm/](../hpm/README.md)).
2. **A plan** in `docs/plans/<feature>/` cuts it into steps, one file each, with the files a
   step changes, its tests and when it is done. Its README has a table with each step's
   status.
3. **Each step is built and committed by itself.** When it is built, its file gets an
   "As built" section: what was decided while building, what differs from the plan, what
   was checked and what couldn't be.
4. **A live run** by a person, with a checklist, ends a feature: the things only real
   windows, a real model or a real terminal show.
5. **Fixes found later** get a plan of their own, in the feature's `fixes/` folder.

Some rules hold everywhere:

- **Fail loudly.** Where something is missing or wrong, give a readable error, never a
  quiet fallback or nothing at all.
- **Hallux's own code knows nothing of any addon.** An addon uses only what every addon has.
- **The machine never learns of Hallux's own parts:** the status bar, the panel, the config.
- **Every path goes through the jail** (`hallux/disk.py`). An addon reads the machine's
  files through its `disk` handle.

## 5. Where the rest is

- **[docs/roadmap.md](../roadmap.md):** what is built and what may come.
- **[docs/concept.md](../concept.md):** the whole design and its reasoning.
- **[docs/plans/](../plans/):** every plan, step by step, with what was built.
