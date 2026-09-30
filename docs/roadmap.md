# Roadmap

A short plan. The design behind every step is in [concept.md](concept.md).

- [x] **0. Environment:** `install.py`, `.venv`, editable install, `hallux.py` launcher.
- [x] **1. Disk and tools:** the path jail, file tools and memory tools as SDK tools, with tests.
  The code is in `hallux/disk.py` and `hallux/tools.py`.
- [x] **2. The tty in cooked mode:**
  - envelopes, the reply parser and control pictures (`hallux/protocol.py`);
  - boot, halt, reboot, Ctrl-C/D/L and the system prompt (`hallux/machine.py`,
    `hallux/terminal.py`, `hallux/prompt.md`);
  - model, effort and budget configuration (`hallux/config.py`);
  - a log of envelopes, replies, tool calls and cost in `<root>/.hallux/hallux.log`.
- [ ] **3. First boot and memory:** creating a new machine, the memory format, copy-up,
  whiteouts, and the reboot test.
- [ ] **4. The `hallux` command:** rules, dotfile changes, listing and forgetting rules.
- [ ] **5. Programs:** script simulation, the Python REPL, package installs, program cards.
- [x] **6. Block mode:**
  - full-screen programs as 3270-style forms: `editor`, `line` and `pager` fields,
    edited locally;
  - only action keys and clicks reach the AI;
  - `file=` fields loaded from the disk, and the `save_field` tool;
  - `nano`, `vi` and `emacs` keymaps;
  - pagers as menus. The code is in `hallux/blockmode.py`.
- [ ] **6b. Raw mode:** every key to the AI, for programs that need it (`top`, action games),
  with live updates (`<tick/>`).
- [x] **6c. Status bar, hard exit, key rule:**
  - a bottom status bar with activity, model, cost and a spinner (`hallux/statusbar.py`);
  - Ctrl+Shift+Del and Ctrl-C ×3 as the hard exit;
  - keys for the machine (Ctrl-C, Tab, Ctrl-Z, ...) are sent to the AI, which may answer with
    `<edit>`;
  - the keyboard is read even while the AI works.

  The design is in [light-and-keys.md](light-and-keys.md).
- [ ] **7. Prompt tuning:** the diff test and the reboot test, run on each model.
- [ ] **8. Polish:** streaming, Ctrl-C while the AI works, window resizing.
- [ ] **Later:**
  - AI tab completion;
  - partial redraws;
  - a "CPU" subagent;
  - a standalone MCP server;
  - shared machines.
