# Addon agents: review of the design

**Reviewed on 2026-10-03:** [addon-agents.md](addon-agents.md) as committed in c293f90 on the
branch `multi-agent`, checked against the code on that branch, the installed
`claude-agent-sdk` (0.2.163) and the notes of the music addon's live run
([plans/addon-music/10-live-run.md](plans/addon-music/10-live-run.md)). Nothing was changed
while reviewing.

Most of the design's factual claims hold up. Five things will cause real trouble, and about
a dozen are missing or slightly wrong.

SDK paths below are inside `.venv/lib/python3.13/site-packages/claude_agent_sdk/`.

---

## Will cause problems

**1. A job's cost isn't known until it ends.** The SDK gives dollars only on
`ResultMessage` (`types.py:1350`), and a job is one query, so that arrives once, at the end.
`AssistantMessage.usage` (`types.py:1146`) gives tokens only. Three parts of the design rely
on a cost that doesn't exist yet:
- the live table row with `"state": "waiting" … "cost_usd": 0.21` (§7);
- "the bar's total includes the jobs" (§11);
- `agent_budget_usd`, which can only count jobs that have already ended.

Killed jobs are the bigger hole. "Marks the row at once and closes in the background" (§9)
must first read the result that `interrupt()` produces, or a job ended by `kill`, timeout or
budget is never counted. Those are the expensive ones. "Still to find out" covers live
tokens, but not this.

**2. `check` "in a child of its own" opens the sound card.** The music child opens pygame's
mixer before it says hello (`addons/music_engine/__main__.py:42`,
`addons/music_engine/player.py:29`). So a silent `check`:
- fails with "no sound device" on a machine without audio;
- opens a second audio stream next to the song that is playing;
- needs SDL's disk driver in its tests (§15), which is the symptom.

The child needs a mode that doesn't open the mixer.

**3. Music's `stop` has two jobs.** It is the AI's tool and also the boot-end hook
(`addons/music.py:230,244`; the loader takes `module.stop` at `hallux/addons.py:271`). If
`stop()` ends the check child, then the main agent stopping the sound also kills a running
job's `check` mid-render. If it doesn't, the check child outlives the boot. A short-lived
child per `check` would avoid this.

**4. §7 and §12 contradict each other.** `list_processes` exists "only on a machine that has
an addon with an agent" (§7). Job control "needs nothing from the agents" (§12), yet `jobs`
reads the kept screens through `list_processes`. On a machine without an agent addon, `jobs`
has nothing to read.

**5. The motivating use case runs into the tick budget.** In a full-screen program the job's
event only arrives with the next key, action or tick (§8):
- A form with fields has no ticks, so the user must press a key.
- A ticking player pays about 1–2¢ per tick, every 4–5 s. The default $0.25 covered about
  100 s in the live run (`plans/addon-music/10-live-run.md:125-127`).
- The low-effort agent took 17–63 s per song; at high effort a composition is likely longer.

So kittymusic probably exhausts its tick budget and sits on "composing…" until a key is
pressed. Letting a job event wake a full-screen program once, like a tick and charged to the
event budget, would fix it. [addon-events.md](addon-events.md) already lists that as
"later".

---

## Gaps to settle before the plan

6. **`.new` collisions.** There is no rule for when `neon.score.new` already exists, for
   example from an earlier conflict. Without one, "Nobody's work is lost" (§10) is false.
7. **Landing.**
   - Several renames are not atomic: a crash in the middle leaves part of the set landed.
   - "Copies left over from a crash … are deleted" (§9) then silently throws away the rest,
     so "land together or not at all" is overstated.
   - The job's folder being deleted, moved or replaced by a symlink while the job runs isn't
     covered. Landing should go through `Disk.real()` again.
8. **`agent_budget_usd` only stops new jobs from starting.** Running jobs spend on, so it is
   not "what all jobs together may cost": the worst case is the budget plus each running
   job's own budget. The wording should say so.
9. **`spawn` runs in the addon's worker thread** (`hallux/addons.py:384`).
   - The process table then needs a lock, and the session has to be handed to the event
     loop in a thread-safe way.
   - Today `_run` would turn the raised error into
     `"OSError: [Errno 11] Resource temporarily unavailable"` (`hallux/addons.py:439`), not
     `{"error": "EAGAIN"}`. It needs a refusal path like `DiskHandle.refusal`.
   - It isn't said where `spawn` goes when a function also takes `disk`, which must be
     first.
10. **The file-name rule** (letters, digits, `.`, `-`, `_`; §8): where is it enforced? A
    user's `My Song.score` passed in `edit` would break it. The table's `tool` field
    (`"check midnight-cello.score"`) also carries paths the job chose. Enforcing the rule
    when the job creates a file, and exempting files it was given, covers both.
11. **Subfolders.** Hallux's `write_file` has `parents=true`. Can a job create subfolders? If
    so, directories also have to land and count against the limits.
12. **Write-then-rename** (§10, §16) only names `write_file`. `edit_file` also writes in
    place (`hallux/disk.py:177`). Append mode needs handling, and the file's mode should be
    kept, since `mkstemp` creates files as `0600`.
13. **The folder check only refuses `/`.** A folder of `/usr/local/bin` or `/home` lets a
    misled job create program cards, or a new home whose `.bashrc` is put into `<boot>`. The
    main agent treats those files as behaviour, so "files like any other" (§14) understates
    it. Consider refusing folders that hold machine-defining files.
14. **A job killed by timeout or budget throws away work that may be finished.** With the
    limits still guessed, that is a likely outcome of the first runs. It follows from the
    decision on what a job may write; it is listed here so it isn't a surprise.

---

## Small corrections

- `pyproject.toml:42` package-data lists only `prompt.md`, so the new `agent.md` has to be
  added. The §16 table also misses `pyproject.toml`, the README (the `~` and the six
  settings in its config example) and `statusbar.VERBS`.
- §5: the jail doesn't refuse `..`; it normalizes it at `/` (`hallux/disk.py:66`). The new
  fence is what will refuse it.
- §15: a new machine has no `/home/user/Music` (`hallux/disk.py:28`), so `compose` fails the
  folder check unless the program card creates it first.
- Haiku: `model_effort` drops effort for Haiku (`hallux/config.py:34`). `agent_model` needs
  the same rule.
- §12: "`[1]+ Done kittymusic` … because a job's event says so" mixes imagined bash jobs with
  real addon jobs.
- §3's `ps` shows `pts/0`, while §2 says a job has "no controlling terminal".
- §9: "What the job wrote is still in hallux.log", but the log rotates at 1 MB × 3
  (`hallux/app.py:132`).
- `sandbox.wrapper()` rewrites its script every time options are built
  (`hallux/sandbox.py:45`). With sessions starting at different times, it should be written
  once per run.
- [addons.md](addons.md) §8 and the [roadmap](roadmap.md) still describe the old sketch.

---

## Checked and correct

- The schema takes scalars only (`hallux/addons.py:49`), and `agent()` is reserved in
  addons.md's table.
- Events from addons nobody listens to are dropped, and events wait while a full-screen
  program runs (`hallux/machine.py:168-176`).
- `addon_listen("music")` works, because music has `connect()`.
- Music reads the score through the disk handle and passes the text to its child, so private
  copies do work for `check`.
- Hallux has three dollar budgets today. `max_turns`, `max_budget_usd` and `effort` all exist
  in the SDK.
- Tool handlers run on the event loop, not in threads, so "one call is never cut in half"
  holds.
- The hard exit sends SIGTERM to every direct child (`hallux/terminal.py:378`). Job CLIs are
  direct children, since the SDK doesn't start a new session, and the SDK also has an atexit
  cleanup.
- The Ctrl-Z claims, and the form being thrown away on leaving block mode
  (`hallux/blockmode.py:297`), are right.
- The live-run figures are right: 17–63 s from Enter to sound, and about 2.5 s per tick.
- The fake client for tests exists (`client_factory` in `hallux/machine.py:102`).
