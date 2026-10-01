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
- [ ] **Later:**
  - smarter AI tab completion;
  - a "CPU" subagent;
  - a standalone MCP server;
  - shared machines.
