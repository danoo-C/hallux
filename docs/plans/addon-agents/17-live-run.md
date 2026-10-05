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
| `README.MD`, "Cost and speed" | What the `~` means, on the bar and in the panel; that a job is a second session with its own cost |
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

Not run yet.
