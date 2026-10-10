# Roadmap

A short plan. The design behind every step is in [concept.md](concept.md). What comes
next, in detail, is in [next-steps.md](next-steps.md).

- [x] **0. Environment:** `install.py`, `.venv`, editable install, `hallux.py` launcher.
- [x] **1. Disk and tools:** the path jail, file tools and memory tools as SDK tools, with tests.
  The code is in `hallux/disk.py` and `hallux/tools.py`.
- [x] **2. The tty in cooked mode:**
  - envelopes, the reply parser and control pictures (`hallux/protocol.py`);
  - boot, halt, reboot, Ctrl-C/D/L and the system prompt (`hallux/machine.py`,
    `hallux/terminal.py`, `hallux/prompt.md`);
  - model, effort and budget configuration (`hallux/config.py`);
  - a log of envelopes, replies, tool calls and cost in `<root>/.hallux/hallux.log`.
- [x] **3. First boot and memory:** the first boot takes 14 s and 1 round trip (before:
  23–27 s and 11), a reboot 6 s with no tool calls, and the reboot check passes.
  - `<boot>` carries the memory and the machine's key files, so a normal boot needs no tool
    calls;
  - a new machine starts from an empty directory tree;
  - `<cwd>` and `write_file(parents=true)` save round trips;
  - `--script FILE` drives hallux headless;
  - `--check reboot` runs the reboot test (`hallux/script.py`).
- [ ] **4. The `hallux` command:** rules, dotfile changes, listing and forgetting rules.
- [ ] **5. Programs:** script simulation, the Python REPL, package installs, program cards.
- [x] **6. Block mode:**
  - full-screen programs as 3270-style forms: `editor`, `line` and `pager` fields,
    edited locally;
  - only action keys and clicks reach the AI;
  - `file=` fields loaded from the disk, and the `save_field` tool;
  - `nano`, `vi` and `emacs` keymaps;
  - pagers as menus. The code is in `hallux/blockmode.py`.
- [x] **6b. Raw mode:**
  - a form with `raw="yes"` sends every key and click to the AI, batched while it answers;
  - `tick="3"` gives live updates, within `tick_budget_usd`;
  - for `top`, `htop`, `watch`, games and single-key menus.
- [x] **6c. Status bar, hard exit, key rule:**
  - a bottom status bar with activity, model, cost and a spinner (`hallux/statusbar.py`);
  - Ctrl+Shift+Del and Ctrl-C ×3 as the hard exit;
  - keys for the machine (Ctrl-C, Tab, Ctrl-Z, ...) are sent to the AI, which may answer with
    `<edit>`;
  - the keyboard is read even while the AI works.

  The design is in [light-and-keys.md](light-and-keys.md).
- [ ] **7. Prompt tuning:** the diff test and the reboot test, run on each model.
- [x] **7b. Streaming:** the shell shows the AI's
  output while it's being written (`ScreenStream` in `hallux/protocol.py`). Full-screen
  programs put their form first and appear whole.
- [x] **7c. Hardening:**
  - only harmless terminal codes reach your terminal (no clipboard writes, no answer-back
    queries, no mode switches);
  - Claude Code keeps no transcript of hallux sessions;
  - optional `os_sandbox` runs Claude Code under bubblewrap.
- [ ] **8. Polish:**
  - [x] partial redraws: `<patch>` with only the changed rows (live: about half the time of a
    whole screen);
  - [x] hidden password input: `<prompt secret="user">` is read with echo off, and the
    password is checked by hallux and never sent to the AI (`hallux/passwords.py`);
  - window resizing inside full-screen programs.
- [x] **9. Addons:** real abilities for the machine, one Python file each in `addons/`. The
  design is in [addons.md](addons.md), the steps in [plans/addons-plan.md](plans/addons-plan.md).
  - a loader that checks every addon and skips a broken one with a note (`hallux/addons.py`);
  - an addon's functions as tools, in a group of its own, with schemas from the type hints;
  - the list of addons in `<boot>`, `list_addons` and `addon_help`;
  - `addons = [...]` per world in `config.toml`;
  - `stop()` hooks on halt, reboot and the hard exit;
  - a disk handle, so that an addon reads the machine's files through the jail;
  - the example: a real window with a text box (`addons/window.py`).
- [x] **9b. Events from addons:** an addon wakes the machine by itself, such as with a button
  in its window. The design is in [addon-events.md](addon-events.md).
  - `connect(emit)` in the addon, and the `addon_listen` tool for the AI;
  - an event interrupts the shell prompt, and the half-typed line comes back;
  - `event_budget_usd` limits what events spend while nobody types.
- [x] **9c. The music addon:** a real sound card. The AI writes a score file and calls
  `play`. The design is in [addon-music.md](addon-music.md), the ten steps in
  [plans/addon-music/](plans/addon-music/README.md).
  - a score file: tempo, variables, instruments, patterns and a song, checked with every
    problem reported by its line;
  - instruments as expressions in the style of bytebeat, at 44100 Hz and 16 bits, with
    `sin`, `saw`, `square`, `tri`, `noise` and `decay`;
  - a child process that renders the whole song with numpy and plays it through pygame's
    mixer; `play`, `stop`, looping and the `finished` event;
  - a manual of under 8000 characters that the AI writes its scores from: in the live run
    seven new songs each played on the first try.
- [x] **10. The settings panel:** Ctrl+F12 opens hallux's own panel over the shell or a
  full-screen program. The design is in [config-panel.md](config-panel.md), the eight steps in
  [plans/config-panel/](plans/config-panel/README.md).
  - a host with a tab row and one tab, Config; a tab is a file of its own
    (`hallux/panel.py`, `hallux/panel_tabs/`);
  - the budgets and the model change while the machine runs, the effort at the next reboot;
  - Save changes `config.toml` line by line and keeps its comments;
  - `max_budget_usd` is hallux's own check now: a boot over it holds its messages back, and
    Refill budgets or a higher number lets them through;
  - the shell's screen and a program's screen come back as they were.
- [x] **11. Addon agents:** an addon brings an agent, and its work runs in the background
  as a job while the machine goes on answering. The design is in
  [addon-agents.md](addon-agents.md), the seventeen steps in
  [plans/addon-agents/](plans/addon-agents/README.md).
  - `agent()` in the addon, and a function with `spawn` that starts a job
    (`hallux/addons.py`); a job is a Claude session of its own (`hallux/agents.py`);
  - a fenced disk for each job: one folder, new files and the files it was given, private
    copies that land when it ends well (`hallux/jobdisk.py`);
  - a process table with real pids, `list_processes` and `kill_process`, and a job's end
    as an event, also inside a full-screen program without fields;
  - six settings: the model, the effort, how many jobs, and what they may cost and how
    long they may run;
  - the jobs on the status bar, and two tabs in the panel that show them live: Agents and
    Details;
  - the music addon's composer, with `check` and `compose`: its first song took 265
    seconds and cost $0.78.

  Run by hand on 2026-10-10, and declared working by the user that day. What the run
  showed, and the few points it didn't try, is in
  [step 17](plans/addon-agents/17-live-run.md).
- [x] **12. Job control:** Ctrl-Z puts a full-screen program aside and `fg` brings it back
  as it was, with no redraw by the AI.
  - the terminal keeps a suspended program's screen, its fields and what was typed into
    them, at most eight (`hallux/blockmode.py`);
  - three tags in the AI's answer: `<suspend>`, `<resume>` and `<forget>`
    (`hallux/protocol.py`);
  - Ctrl-Z always reaches the AI in a full-screen program, and `jobs` reads the kept
    screens through `list_processes`.

  Tried by hand on 2026-10-10, with the real model.
- [ ] **Later:**
  - events inside full-screen programs, and a script line that fakes an event. A job's end
    already arrives in a program without fields; an addon's own events still wait until
    the program is left;
  - smarter AI tab completion;
  - a "CPU" subagent;
  - a standalone MCP server;
  - shared machines.
