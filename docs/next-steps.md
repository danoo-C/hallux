# Next steps

What comes after the hardening pass, in the order I'd do it. Each part has a goal, a design
sketch, the costs and risks, and open questions with my recommendations. The short list
lives in [roadmap.md](roadmap.md); the design behind everything is in [concept.md](concept.md).

---

## 1. Raw mode: `top`, live updates, games (roadmap 6b)

**Goal:** programs that need every key, or that change on their own:
- `top` / `htop` with numbers that tick;
- a snake game;
- a menu you steer with single keys.

Today they draw one frame and return to the prompt.

**Why block mode isn't enough:** block mode lets you edit fields locally and only calls the AI
on action keys. That's perfect for nano, but a game reacts to *every* key, and `top` changes
with *no* key at all.

**Design sketch:**
- **Entering and leaving:** the AI enters raw mode with `<tty mode="raw"/>` (the machine's
  `stty raw`) and leaves it with `<tty mode="cooked"/>`. The reply parser already reads that
  tag.
- **Every key goes to the AI** as an event: `<keys><text>jj</text><key>Up</key></keys>`.
- **Type-ahead batching:** keys pressed while the AI is answering are sent together in the next
  message, so a fast typist costs one call, not ten. Block mode already holds keys this way.
- **Live updates:** while raw mode is on, the terminal sends `<tick/>` every N seconds, and the
  AI redraws (`top`'s clock and numbers). Each tick is one model call.
- **Full screen:** the screen is drawn the way block mode draws it, as a full-screen layout
  with the status bar below.
- **Mouse:** clicks become `<mouse button="left" col="42" row="7"/>` events.
- **The way out:** Ctrl-C reaches the program (it decides), and the hard exit works as always.

**Costs and risks:**
- **Every burst of keys is a round trip of 2–7 s**, so this suits turn-based games, menus and
  slow dashboards, not action games. The status bar's spinner shows when the machine is
  "thinking".
- **Ticks cost money while you watch.** At one tick per 3 s on Opus 5.5 at `low` effort, that's
  very roughly $0.20 per minute, so ticks need a budget.

**Questions:**
- **How often should `top` tick?** My recommendation: every 3 s (real `top`'s default), only
  while the program is on screen, and capped by a `tick_budget_usd` per program run (default
  $0.25), after which it freezes with a note on the status bar.
- **Should raw mode use a cheaper model?** My recommendation: yes, optionally. A
  `raw_mode_model = "claude-haiku-4-5"` config setting, because speed matters more than depth
  for a game frame. It needs a second session, so it's a later refinement.
- **What happens when a game ends?** The program prints its last frame and leaves with
  `<tty mode="cooked"/>`, and the shell comes back exactly as with block mode.

---

## 2. Tuning and measurement (roadmap 7)

**Goal:** know, with numbers, how faithful, fast and cheap each model and effort is, and
improve the system prompt against those numbers instead of by feel.

**What exists:** `--script FILE` (headless runs) and `--check reboot` (persistence).

**Design sketch:**
- **The diff test (fidelity):**
  1. A command list (`ls -la`, `cat /etc/os-release`, `wc -l`, `grep`, `find`, a small Python
     script, error cases) runs in a real Debian 12 container (`docker run debian:12`), and in a
     fresh hallux machine seeded with the same files.
  2. A comparison scores each command: identical, equivalent (same lines in another order, or
     whitespace), plausible, or wrong.
  3. The output is a table per model and effort.
- **A model comparison:** the same scripts on Haiku 4.5, Sonnet 5.5 and Opus 5.5 at `low` and
  `medium`, recording time per command, cost per command, boot times and the diff score.
  `summary()` in `hallux/script.py` already measures most of this.
- **Prompt work:** every prompt change gets re-run against the diff test and the reboot check,
  so improvements are measured and regressions are caught.
- **Prompt caching:** check that the system prompt and the history are being cached (the log
  can show cache reads). The prompt is long and identical for every call, so caching it is
  most of the remaining cost win.

**Costs and risks:** each full comparison is a few hundred round trips. That's a few dollars
per run, so it's run deliberately, not on every change. It needs Docker for the real bash
side.

**Questions:**
- **Which commands go into the diff test?** My recommendation: about 30, grouped as files
  (grounded), text tools, errors, Python, and machine identity, written so they're
  deterministic on a real machine (no dates or PIDs).
- **Should the default model change after the comparison?** My recommendation: decide from
  the numbers. My guess is Sonnet 5.5 at `low` as the default for speed, with Opus 5.5 for
  people who want maximum fidelity.

---

## 3. Polish (roadmap 8)

### Hidden password input (`sudo`, `passwd`, `ssh`)

**Problem:** when the machine asks for a password, what you type is visible, because the
terminal echoes your keys. A real terminal hides it.

**Sketch:** the AI marks the prompt as secret, `<prompt secret="yes">[sudo] password for
user: </prompt>`, and the terminal reads that line with echo off (prompt_toolkit's password
mode). The typed text still goes to the AI, because the machine decides whether the
password is right.

**Question: should the password be sent to the AI at all?** My recommendation: yes, but
replaced by `•` characters of the same length. The machine only needs to "check" it against
the password in its memory, and that check can be done by hallux locally: right or wrong is
sent instead of the password. That keeps real passwords you might type by habit out of the
API.

### Full-screen programs and window resizes

**Problem:** when you resize the window inside nano, the field positions stay as they were
computed for the old size.

**Sketch:** on a resize, block mode sends `<action key="resize" cols=".." rows="..">` and the
AI redraws. The footer and `height="0"` fields already adapt; the AI only has to re-lay out
the title bar and pad the bars.

### Partial redraws in block mode

**Problem:** every nano action costs 4–7 s and about $0.015–0.02, mostly because the AI
redraws the whole screen each time.

**Sketch:** the AI may send only the rows that changed, for example
`<row n="-3">[ Wrote 3 lines ]</row>`. The terminal patches its copy of the screen, and the
footer and fields are kept. In nano, most actions only change the status line.

**Question: what if a patch doesn't fit the screen?** My recommendation: rows outside the
screen are ignored, and the AI can always send a whole screen instead.

---

## 4. Hardening leftovers

- **Less traffic from Claude Code itself:** Claude Code sends telemetry and error reports on
  its own. Setting `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` for hallux's Claude Code
  process turns that off. My recommendation: a `quiet = true` config setting, on by default.
- **Hyperlinks:** OSC 8 links are dropped today, because a link's text can hide where it goes.
  If `ls --hyperlink` ever matters, they could be allowed only for `file://` links into the
  world folder.
- **Warning about hard links and mount points:** at boot, hallux could scan the world folder
  for hard links (more than one link to a file) and mount points, and show a warning on the
  status bar, since those are the two ways a world folder can reach outside itself.
- **A container instead of bubblewrap:** for people on macOS (no bubblewrap), a
  `docker run` wrapper could play the same role as `os_sandbox`.
