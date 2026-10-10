# Step 17: the documentation and the live run

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), "Still to
find out"

**Needs:** steps 13, 15 and 16. **Changes:** `README.MD`, `docs/`.

Everything is built by now, and the composer has had its first live run in step 13. This
step writes the documentation, and ends with a run of the whole feature together: jobs,
their events and job control in one sitting.

## Build

**The documentation:**

| File | What changes |
|---|---|
| `README.MD`, "Features" and "Addons" | An addon can bring an agent; the composer; `check` |
| `README.MD`, "Configuration" | The six settings, with their defaults; that jobs count towards `max_budget_usd`, each when it has ended, so a boot can pass its cap by what the running jobs spend, at most the budget for all jobs (step 8) |
| `README.MD`, "Cost and speed" | What the `~` means, on the bar and in the panel; that a job is a second session with its own cost. From step 9's check: a job can pass `agent_job_budget_usd` by one model message, since the cap is looked at after each; and what a killed job cost can be short by the one message that was cut |
| `README.MD`, "Safety and privacy" | What a job can reach, and that what it reads in its folder goes to the API like everything the machine reads |
| `README.MD`, "Keys" | Ctrl-Z and `fg` in full-screen programs; the panel's Agents and Details tabs on Ctrl+F12 |
| `README.MD`, "Writing an addon" | `agent()`, `spawn`, and what a job can reach |
| `README.MD`, "Project layout" | `agents.py`, `jobdisk.py`, `agent.md`, `prompt_jobs.md`, `panel_tabs/` |
| `docs/addons.md`, section 8 | It describes the old sketch, where the main agent waits for its worker. It points to the design instead |
| `docs/roadmap.md` | An entry for addon agents and one for job control; "worker agents" leaves the "Later" list. Events inside full-screen programs stay there, with a note that a job's end already arrives |
| `docs/addon-music.md` | `check` and `compose` |
| `docs/addon-agents.md`, this plan | The status lines; the answers to "Still to find out" |

## The live run

By the user, in a real terminal. Each line is something the tests can't show.

1. **Two things at once:** a composition runs while the user edits a file in nano. The song
   arrives, and nano's text is untouched.
2. **A player and the shell:** the player composes, Ctrl-Z, a command at the shell, `fg`.
   The player is back as it was, and shows the song when it is ready.
3. **`jobs`, `ps` and `htop`** with a suspended player and a running composer: the real job
   has its real pid and time, and the suspended program is listed.
4. **A song that is changed:** `compose` with a score in `edit`, while the same score is
   open in nano and saved there. The job's version lands as `.new`, and the program says so.
5. **The budgets:** jobs until one is refused, then a key press, then one more. What does
   the user see?
6. **A reboot and a power-off** with a job running: nothing is left in the folder, and
   nothing in `.hallux/jobs`.
7. **The hard exit** with a job running, then a new start: the log names what was swept.
8. **The config panel:** the jobs' budget raised while a job is refused. Then jobs until one
   is refused again, and **Refill budgets**, once: no real run has pressed that button yet
   (the panel's live run).
9. **The memory of the computer:** how much each Claude Code process takes, with two jobs
   running.
10. **Watching a job:** Ctrl+F12 while a composer works. The list moves, the Details tab
    follows the job line by line, and after Esc the screen is as it was.
11. **A kill from the panel:** `k`, `y`. The folder is as it was, and the shell prints what
    a killed job prints.
12. **A machine without the music addon:** the two tabs are grey and say why.
13. **A job's end and an editor:** a composition ends while nano is open with unsaved text,
    and the AI listens to the music addon. Nothing happens on the screen, and the text is
    as it was: a program with fields isn't woken (step 11). Does the `Done` line come when
    nano is left?

## Done when

The live run is written up below, the status lines say "built", and each point of the
design's "Still to find out" has an answer, or says that it is still open.

## What the live run taught

### The run of 2026-10-10, by the user

In `test-hallux`, from 12:35 to 13:12, with [the checklist](live-run-checklist.md). The
machine ran on Opus at effort low, the composer on Opus at effort high. **The user ticked
36 of the 40 boxes and wrote nothing on any line:** no "If not", and no number. The user's
word for the run: everything works.

What follows sets the ticks beside that world's `hallux.log`, which has every message, every
tool call and every job. **Nothing in the log is an error.** Its one warning is the hard
exit that part G asks for. But a tick and the log don't always say the same: some ticked
points weren't run as the checklist describes them, and two that aren't ticked ran well.

**The compositions:**

| Job | What | Time | Turns | Cost |
|---|---|---|---|---|
| 30001 | A slow blues, at the shell | 124 s | 14 | $0.42 |
| 30002 | A fast metal song, at the shell | 141 s | 14 | $0.42 |
| 30003 | A song asked for in the player | 124 s | 14 | $0.37 |
| 30004 | A change to one of them | 22 s | 10 | $0.10 |
| 30005, 30006, 30007 | Ended after 67, 16 and 30 seconds | | 2 each | $0.001 each |

Each new song cost about half of the first composition of 2026-10-07, $0.78 in 265
seconds, and a fifth of the cap per job. The machine's own session cost $4.41 in the same
time, about $2.00 of it while the player was open: its ticks came every four seconds.

**Part A, job control.** In the first boot, without a job.

| Point | Ticked | What the log shows |
|---|---|---|
| A1, A2, A3 | Yes | nano, Ctrl-Z: answered in 3 seconds with `<suspend job="1"/>` and the `Stopped` line. `jobs` read `list_processes` first. `fg`: answered in 1 second with `<resume job="1"/>`. When nano was left, the AI sent `<forget job="1"/>` by itself |
| A4, vim | Yes | No `vim` was typed in the run |
| A5, `top` | Yes | Ctrl-Z, `echo hi`, `fg`: the program came back, and its tick went out 1 second after the `fg` |
| A6, two programs | **No** | It ran as described: nano was job 1 and less job 2, `fg %1` brought the first and `fg` the second |
| A7, `kill %1` | Yes | No `kill %1` was typed in the run |
| A8, another size | Yes | The window went from 120 to 86 columns between the Ctrl-Z and the `fg`, and stayed 29 rows high |
| A9, a reboot | Yes | The AI sent `<forget job="1"/>` with its answer to `reboot`. After the boot `jobs` printed nothing |

**Part B, one composition at the shell.**

| Point | Ticked | What the log shows |
|---|---|---|
| B1 | **No** | `compose` answered in 7.0 seconds, with `[1] 30001` and the prompt |
| B2, B3, B4 | Yes | A half-typed line was dropped with Ctrl-C. `rcho hi`, a slip of the keys, was answered at once. The log can't show the bar |
| B5 | Yes | `htop` read `list_processes`, and its ticks carried the job's row. `ps aux` was typed later, in part D |
| B6, B9, B10 | Yes | Nothing: the panel leaves no line in the log, as it should. Nothing was typed for two minutes |
| B7, a status line first | Yes | **Not as described.** The first `set_status` came 82 seconds after the job's start, not within the first seconds. It was the composer's first call: it thought first, as on 2026-10-07, when it took 174 seconds |
| B8, a round's changes together | Yes | **Not as described.** After its first `check` the composer made seven `edit_file` calls, one a second, each in a turn of its own: 13 calls and the last message are its 14 turns |
| B11, the memory | **No** | The `ps` line was typed into Hallux, three times, so the machine answered it and not the computer. No number |
| B12, the end by itself | Yes | **Not as described.** The AI hadn't asked to listen, so the job's end waited 110 seconds for the next typed line, and the `Done` line came with that. For job 30002 it was the same |
| B13, Refill budgets | Yes | No setting was changed and no refill was pressed in the whole run |
| B14 | Yes | 124 seconds and $0.42. The song was never played at the shell |

**Part C, a composition and nano.** All three are ticked. nano was opened 8 seconds after
the job had ended, so the job didn't end under an open editor. What the log does show: the
AI got the job's end in front of `nano aaaa`, opened nano, and printed the `Done` line when
nano was left.

**Part D, a player that composes.** All four are ticked, and the log has all four.

- The player's ticks carried the job's row, and it showed the pid and the time.
- Ctrl-Z was answered with `<suspend job="1"/>` and `[1]+  Stopped  kittymusic`. `ps aux`
  read `list_processes`. `fg` brought the player back, and its tick went out at once.
- **The job's end woke the player,** the moment the job ended. The AI answered as the
  player: a whole screen, which took 29 seconds, and on the next tick it called `play`.
  It didn't print a `Done` line and didn't leave the program. That is what step 11
  couldn't check.

**Part E, a song that is changed.** Both are ticked. `compose` passed the score in `edit`.
The user's own change was saved 30 seconds before the job started, not while it ran, so
there was no conflict: the composer changed the file in place, and no `.new` was made.

**Part F, ending a job.** All three are ticked, and the log has all three.

- The second `compose` was refused, and the program said so: `compose: composer busy`.
- `kill 30005` called `kill_process`. The job's end said `killed`, `why: kill`, and that
  nothing was written.
- Job 30006 ended as `killed` without a tool call: from the panel.

**Part G, the end of a boot.**

| Point | Ticked | What the log shows |
|---|---|---|
| G1, a reboot | Yes | Job 30007 ended as `killed (boot)` one second before the new boot. The `ls` of `.hallux/jobs` was typed into Hallux; on the computer the folder is empty |
| G2, a power-off | Yes | No `poweroff` was typed with a job running |
| G3, the hard exit | Yes | The key was pressed 43 seconds after the job's start, before its first write. So it had no copies, and the next start had nothing to delete and wrote no line |

**Part H** isn't ticked and wasn't run. **Part I** is ticked; it is another world, whose
log I didn't read.

**What the run settles:**

- **Job control works with the real model,** on a real terminal: the three tags, `jobs`
  through `list_processes`, a program that ticks, two programs at once, a narrower window.
  Step 15 is done.
- **A job's end wakes a full-screen program without fields,** and the AI answers as that
  program.
- **The shell stays usable while a job runs,** and the bar's redraw doesn't disturb typing:
  the user's tick on B3.
- **A kill, from the shell and from the panel, and a reboot** end a job and leave nothing.
- **A second `compose` is refused,** and a program says so in its own words.
- **The new caps hold a composition four times over.**

**What it found that isn't as planned.** None of it is a fault of the code.

- **The composer still thinks before its first status line.** The line is its first call,
  as its role asks, but the call comes after the thinking: 82 seconds here. Until then the
  row says `composing…`.
- **The composer still makes one change a turn.** Its role asks for a round's changes in
  one turn. The turns are short, about a second each, and the whole job cost $0.42.
- **At the shell the AI didn't listen for a job's end,** twice out of twice, so the `Done`
  line came with the next typed line. On 2026-10-07 it had listened by itself. In the
  player it listens, because the player's card says so. The manual says that
  `addon_listen` brings a job's end at once, and leaves the choice to the AI.

**Declared working by the user, on 2026-10-10,** after reading this write-up: "they dont
need another try. we can declare this working". So the points below stay as they are:
tested with a pretend model, and not seen in a real run.

**What has no result:**

| | Why |
|---|---|
| A4, vim's mode, and A7, `kill %1` | Not typed in the run |
| B11, the memory of each process | The command has to run on the computer, in a second terminal |
| B13, Refill budgets | Not pressed. No real run has pressed that button yet |
| C2, a job that ends under an open editor | The editor was opened after the job's end |
| E2, a change by somebody else while the job runs | The change was saved before the job started |
| G2, a power-off with a job | Not typed |
| G3, the copies that a hard exit leaves | The exit came before the job's first write |
| H1, a job that uses up its budget | Not run |

**Beside the list:** the user saved a screenshot,
`panel_bug_when_resising_in_htop_and_ctrl-C.png`, and set it aside for after this
write-up. It isn't looked at here.

## As built

### The documentation, on 2026-10-10

Written on the branch `addon-agents`. No code changed, and 1578 tests pass, as after step
15. One of them reads the README's example of `config.toml` and loads it: it expects the
example's `agent_model` now. The live run followed the same day, and with it the step was
done.

| File | What it says now |
|---|---|
| `README.MD`, "Features" | Job control under the full-screen programs, the panel's two more tabs, and a point of its own for background jobs |
| `README.MD`, "Keys" | A row for Ctrl-Z and `fg` in a full-screen program; the row for Ctrl+F12 names the three tabs |
| `README.MD`, "Addons" | That an addon can bring an agent; `check` and `compose` under the music addon, with a composition at the shell |
| `README.MD`, "Background jobs" | New, between the music addon and "Writing an addon": what a job is for the user |
| `README.MD`, "Writing an addon" | `list[str]` as a type hint; an addon with an agent, with an example; `agent()`, `spawn`, and what a job can reach |
| `README.MD`, "Configuration" | The six settings in the example file, a row for when a change of them takes effect, and three points on the jobs' budgets |
| `README.MD`, "Cost and speed" | The `~`; a job as a second session; the cap passed by one message; a killed job's cost short by one |
| `README.MD`, "Safety and privacy" | What a job can reach, and that what it reads goes to the API |
| `README.MD`, "Project layout" and "Documentation" | `agents.py`, `jobdisk.py`, `prompt_jobs.md`, `agent.md`, the three tabs; links to the design and to the music addon's document |
| `docs/addons.md` | Section 8 says first that it is the old sketch and wasn't built, and points to the design. The status lines and point 5 of "In short" say the same |
| `docs/roadmap.md` | Entry 11 for addon agents and entry 12 for job control, both with the live run named as open. "Worker agents" left the "Later" list; events inside full-screen programs stay, with what a job's end already does |
| `docs/addon-music.md` | `check` and `compose` in section 1, with the composer; the status lines and "In short" name them; the manual's limit is 8500 |
| `docs/addon-agents.md` | The status says built, with the live run open. Each point of "Still to find out" has its answer: seven are answered, two in part, two are open |
| `README.md` of this plan | The status, and this step's row |

Decided while writing:

- **The README has a section "Background jobs".** The plan put jobs under "Features" and
  "Addons" only. What a job is for the user, its pid, its end and the panel's tabs, had no
  place of its own there.
- **The example of an addon with an agent is a poet,** 20 lines. I loaded it once with the
  real loader and had its function start a job with a stand-in worker: it loads, returns
  `{"pid": 30001}`, and the job's file lands. No test holds it, as none holds the die of
  the first example.
- **The numbers of the first composition are in the README and in the roadmap:** 265
  seconds and $0.78. They are one run.
- **The roadmap marks both entries as built,** and says under each that the run by hand is
  open.

### The checklist

[live-run-checklist.md](live-run-checklist.md) has 40 points in nine parts. Each has what
to do, what should happen, one box, and a line for what happened if it didn't. Where its
points come from:

| From | Point | In the checklist |
|---|---|---|
| This step | 1. Two things at once; 13. A job's end and an editor | C1 to C3 |
| | 2. A player and the shell | D1 to D4 |
| | 3. `jobs`, `ps` and `htop` | B5, D2 |
| | 4. A song that is changed | E1, E2 |
| | 5. The budgets; 8. The config panel | B13, H1 |
| | 6. A reboot and a power-off; 7. The hard exit | G1 to G3 |
| | 9. The memory of the computer | B11 |
| | 10. Watching a job | B6 to B10 |
| | 11. A kill from the panel | F3 |
| | 12. A machine without the music addon | I1 |
| Step 13 | 4. A player that composes | D1, D4 |
| | 5. `ps` and `htop` | B5 |
| | 6. `kill` | F2 |
| | 7. The bar while typing | B3 |
| | 8. A second `compose` | F1 |
| Step 14 | A status line first, and a round's changes in one turn | B7, B8 |
| Step 15 | Its "Done when", and what a real model does with the three tags | A1 to A9 |
| Step 11 | What a real model answers to a wake | D4 |
| Step 12 | Whether the bar's redraw disturbs typing | B3 |
| Step 16 | The tabs on a real terminal, and the mouse | B6, B9, B10 |

**What the checklist changes or leaves out:**

- **A start that is refused for the budget can't be seen at the shell.** Every typed line
  fills the budget for all jobs, so the `compose` that was just typed always fits. The
  budget bites only when nobody is at the keyboard. B13 shows it in the panel instead: the
  idle composer says `can't start: jobs budget used`, and Refill budgets takes that away.
- **H1 is new:** a job that uses up its budget is killed, and nothing lands. No list had
  it, and no run has shown it.
- **The memory is read with one job running, not two.** Two jobs at once need two addons
  with an agent, and only the music addon has one.
- **The timeout isn't tried:** it is ten minutes.
- **Part A goes beyond step 15's "Done when":** vim's mode, a program that ticks, two
  programs, `kill %1`, a window that changed its size, and a reboot.
