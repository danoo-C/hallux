# Roadmap

A short plan. The design behind every step is in [concept.md](concept.md).

- [x] **0. Environment:** `install.py`, `.venv`, editable install, `hallux.py` launcher.
- [x] **1. Disk and tools:** the path jail, file tools and memory tools as SDK tools, with tests.
  The code is in `hallux/disk.py` and `hallux/tools.py`.
- [ ] **2. The tty in cooked mode:**
  - envelopes, the reply parser and control pictures;
  - boot, halt and reboot;
  - model and effort configuration.
- [ ] **3. First boot and memory:** creating a new machine, the memory format, copy-up,
  whiteouts, and the reboot test.
- [ ] **4. The `hallux` command:** rules, dotfile changes, listing and forgetting rules.
- [ ] **5. Programs:** script simulation, the Python REPL, package installs, program cards.
- [ ] **6. Raw mode and the mouse:** full-screen programs, key and click events, clean exits.
- [ ] **7. Prompt tuning:** the diff test and the reboot test, run on each model.
- [ ] **8. Polish:** streaming, Ctrl-C, a log file, window resizing.
- [ ] **Later:**
  - AI tab completion;
  - live programs (`<tick/>`);
  - partial redraws;
  - a "CPU" subagent;
  - a standalone MCP server;
  - shared machines.
