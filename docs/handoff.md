# Handoff: where Hallux stands (2026-10-01)

Read this first when picking the work back up. It's the state of the project, how to run and
test it, and what to do next. To resume with Claude, say: *"read docs/handoff.md and continue
with …"*.

## In one paragraph

Hallux is a hallucinated Linux machine. You type into a real terminal, and a Claude agent (Claude
Code through the Claude Agent SDK) *is* the machine. It answers every command by imagining
the output. A real folder is its disk, so files are real, and it remembers itself across
reboots. Every character on the machine's screen comes from the AI. The only exceptions are
your own typing and hallux's status bar on the bottom row. The full design is in
[concept.md](concept.md).

## State

- **Branch `dev`**, with the last commit `f0792b2` (partial redraws). Everything up to raw mode
  is pushed to GitHub. `f0792b2` and this handoff are local, so push when you like: `git push`.
  `main` has only the first two commits; merge `dev` into it whenever you want.
- **160 tests pass:** `.venv/bin/python -m pytest -q`. They need no model calls.
- **All roadmap steps up to 7c are done and live-tested,** plus partial redraws. The checklist
  is [roadmap.md](roadmap.md).

## Running it

```bash
python install.py                              # once; again after dependency changes
python hallux.py test-hallux                   # the machine in your terminal
python hallux.py test-reboot --check reboot    # build a new machine, check it survives a reboot
python hallux.py test-x --script cmds.txt      # headless: one command per line
```

- **World folders** named `test-*/` are git-ignored. Keep any other world outside the repo.
- **The hard exit** is Ctrl+Shift+Del, or Ctrl-C three times within a second.
- **Per-machine settings** go in `<world>/.hallux/config.toml`:
  - `model`, `effort` (defaults: Opus 5.5, `low`);
  - `fallback_model`, `max_budget_usd`;
  - `status_bar`, `keep_transcripts`, `os_sandbox`;
  - `tick_budget_usd`.

  `test-hallux` currently has `os_sandbox = true`.
- **Everything the AI received and answered** is logged in `<world>/.hallux/hallux.log`, with
  timing and cost per answer. That's the first place to look when something looks wrong.

## The code

| File | What it does |
|---|---|
| `hallux.py` / `install.py` | Launcher (switches into `.venv`) and setup |
| `hallux/app.py` | The command line: interactive, `--script`, `--check reboot` |
| `hallux/machine.py` | One agent session per boot: boot message, sending input, block-mode loop, costs, status updates |
| `hallux/protocol.py` | The wire: envelopes, reply parsing (`<screen>`, `<prompt>`, `<form>`, `<patch>`, `<file>`, `<cwd>`, `<memory>`, `<edit>`), `ScreenStream` for streaming, and `decode()`/`safe()`, the filter for what may reach your terminal |
| `hallux/terminal.py` | The real terminal: prompt_toolkit input, the key rule, the keyboard watcher while the AI works, the hard exit, status bar pinning |
| `hallux/blockmode.py` | Full-screen programs: fields (`editor`, `line`, `pager`), raw mode (every key, ticks, mouse), screen fitting, patches |
| `hallux/statusbar.py` | The bottom bar: spinner, activity, model, cost, notes |
| `hallux/disk.py` / `hallux/tools.py` | The path jail and the agent's tools (files, memory, `save_field`) |
| `hallux/script.py` | The headless terminal, the reboot check |
| `hallux/sandbox.py` | The optional bubblewrap wrapper for Claude Code |
| `hallux/config.py` | `config.toml` and flags |
| `hallux/prompt.md` | **The system prompt.** Most behavior lives here; tune it with the reboot check and logs |

## Numbers from the last live sessions (Opus 5.5, effort `low`)

| What | Time | Cost |
|---|---|---|
| First boot | ~14 s, 1 round trip | ~$0.04–0.07 |
| Reboot | ~6–7 s, no tool calls | ~$0.03 |
| Shell command | ~2–5 s | ~$0.004–0.03 |
| Full-screen answer, whole screen | ~10–25 s | ~$0.04–0.07 |
| Full-screen answer, patch | ~12 s median | ~$0.045 |
| The reboot check | 23 round trips, ~85 s | ~$0.27 |

## Lessons worth remembering

- **The AI is faithful, sometimes too faithful.** Ctrl-C in nano shows the cursor position, `apt`
  without sudo fails, and `reboot` as a normal user is refused. When something "doesn't work",
  check the log before assuming a bug.
- **Models miscount rows and drop rare characters.** hallux compensates:
  - `fit_screen` handles screens drawn too tall;
  - bare color codes like `[38;5;218m` are repaired;
  - kept fields inherit what the AI doesn't restate.
- **Claude's own sandbox** puts placeholder files into a folder it uses as its working
  directory. That happened in `test-hallux/.hallux/.claude`. They're harmless and can be
  deleted, and Claude shouldn't `cd` into worlds.

## What's next

**First, a quick task: add the license (decided: MIT, see below).**
- Create `LICENSE` with the standard MIT text, `Copyright (c) 2026 Daniel Danko`.
- Add a short "License" section at the end of `README.MD` that links to it.
- Set `license = "MIT"` in `pyproject.toml` under `[project]`.

The details for everything after that, with design sketches and open questions, are in
[next-steps.md](next-steps.md). In the order I'd suggest:

1. **Tuning (roadmap 7):**
   - a fidelity test against real bash in Docker;
   - a model comparison: Sonnet 5.5 vs Opus 5.5 at `low`/`medium`, on speed, cost and fidelity.

   That decides the default model by numbers. Each full run costs a few dollars, so agree on
   the budget first.
2. **Hidden password input (polish):** `sudo` currently echoes your password and sends it to the
   API. The plan is a `secret` prompt with echo off, checked locally.
3. **Window resizes in full-screen programs (polish):** a `resize` action, so the AI re-lays out
   the screen.
4. **Patching part of a row** (a `col` attribute), for split-screen programs like `lt-love`,
   where only one side changes.
5. **The hardening leftovers:**
   - silencing Claude Code's own telemetry (`quiet`);
   - warning about hard links or mount points in a world;
   - a container option for macOS.

## Decisions made

- **License: MIT** (2026-10-01). It's simple, permissive and widely understood: anyone may use,
  change and share the code, as long as the copyright notice stays. Apache-2.0 (which adds a
  patent grant) and GPL-style licenses (which keep derivatives open) were considered and
  passed over.

## Open decisions for you

- **The default model,** after the tuning numbers.
- **Whether to merge `dev` into `main` now,** or keep developing on `dev`.
- **Whether the password should still be sent to the AI** in some masked form, or only
  "right/wrong". The recommendation in next-steps is right/wrong only.
