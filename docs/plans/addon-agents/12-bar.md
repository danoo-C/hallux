# Step 12: the status bar and the costs

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), sections 11
and 15

**Needs:** step 10. **Changes:** `hallux/statusbar.py`, `hallux/terminal.py`,
`hallux/machine.py`, `hallux/script.py`, `hallux/app.py`, `hallux/panel_tabs/config.py`,
`tests/test_statusbar.py`, `tests/test_terminal.py`, `tests/test_script.py`,
`tests/test_panel_config.py`.

A job spends money while nobody looks at it. The bar is where Hallux says so: which job
runs, for how long, with how many tokens, and what everything has cost. This step also
gives scripts a way to wait for a job, which the scripted run of step 13 needs.

## Build

**Jobs on the bar:**

```text
 • music: balancing the mix · 0:48 · 21k tok          opus 5.5 · low · ~$1.42 · 2.1s
 ⠹ reading /etc/os-release · 1 job                    opus 5.5 · low · ~$1.42 · 0.8s
```

| The main agent is | The left side |
|---|---|
| Idle, one job running | The addon, the job's status line, its time, its tokens |
| Idle, more jobs | `2 jobs: music, gui` |
| Working | Its own activity, then `· 1 job` |

- An error and a note still come first, as today.
- **A job's line comes before `listening: …`,** which the bar shows today when nothing
  else is to say (`hallux/statusbar.py:95-96`). The AI often listens to an addon just to
  hear its job end, and the job's line says more.
- **When the line is too long, the status is cut.** The time and the tokens stay: they are
  what moves. The bar's own shortening cuts from the end (`hallux/statusbar.py:139-148`),
  which would take them first.
- **The bar's words for the new tools:** `list_processes` and `kill_process` get verbs, as
  the other tools have (`hallux/statusbar.py:29`). A verb isn't enough for the kill: the bar
  shows a tool's `path`, `src` or `name` after the verb (`hallux/statusbar.py:45`), and a
  kill has a `pid`. It is shown as `killing 30001`.

**The `~`.** The cost becomes `~$1.42`. The number is what the tokens would cost at the
API's list prices; with a Claude subscription nobody is billed that amount. The README
says what the `~` means, in step 17.

- **The Config tab's notes of what was spent get it too:** `spent in this boot: ~$0.12`.
  They are the same kind of number, and the Agents tab beside them shows `~$0.19`
  (step 16). A limit the user typed stays without it: `$2.00`.

**The total** on the bar is the main session's sum plus the jobs' sum, which the machine
keeps apart (step 8). A job is in it from the moment it has ended; a job that was killed
counts too.

- **Three tests pin the cost without the `~`** (`tests/test_statusbar.py:17,44,52`) and
  change with it. So do the tests of the Config tab's notes.

**The bar moves while the prompt waits.** Today it is drawn while the AI works, or when
something is printed. A job's time and tokens change while the user sits at the prompt.

- While a job runs and the main agent is idle, the bar is drawn again once a second.
- When no job runs, nothing is drawn, as today.
- **One timer, in the terminal.** The panel's two tabs (step 16) need the same beat for
  their times. Whichever of the two steps is built first makes the timer, and the other uses
  it.
- **Drawing again goes through one function of the terminal.** It has it already, for the
  bar's light: it draws the bar at the shell, block mode's screen in a full-screen program,
  and the panel while one is open at the shell (`hallux/terminal.py:319-325`). It becomes a
  method that others may call. The timer calls it, and so does the machine when `Jobs`
  says that a job reported (step 7). `Panel.invalidate()` alone isn't enough: over a
  full-screen program the panel is a layer in block mode's app and has none of its own
  (`hallux/panel.py:139-142`). Tried on 2026-10-05: it drew nothing again there.
- Whether that disturbs typing is one of the design's open measurements. It is tried in
  the live run of step 13. If it does, the bar is drawn only when a job's status line or
  state changes.

**Scripts:**

- **`@wait jobs 180`** is a new script line: the script goes on when no job runs, or after
  that many seconds. Without it a script would end, the machine would halt, and the job
  would be killed.
- **The summary** at the end of a scripted run counts the jobs: how many, and their cost in
  the total. The cost comes from the jobs' own sum. It isn't booked to a line of the script:
  the scripted terminal books every rise of the bar's cost to the line that was typed last
  (`hallux/script.py:128-130`), and a job's cost would land on whatever that was. So the
  bar's cost that the scripted terminal is told stays the main session's.
- **`run_script` gives the jobs' numbers back with the records.** Today it returns the
  records alone, and `app.py` makes the summary from them (`hallux/app.py:145-152`).

## Tests

In `tests/test_statusbar.py`:

- idle with one job: the addon, the status, `0:48`, `21k tok`;
- idle with two jobs; working with one job;
- an error and a note win over a job, and a job wins over `listening`;
- the cost has the `~`, with and without jobs;
- a job's line that is too long for the bar: the status is cut, the time and the tokens are
  there, and the hardware on the right stays;
- the two new tools have their words.

In `tests/test_terminal.py`. A terminal on a pipe pins no bar and writes none
(`hallux/terminal.py:436-440`), so these tests pin it by hand, as the panel's tests of the
bar do.

- with a job running, the bar is written again within two seconds while the prompt waits,
  and what was typed is still the line;
- with no job, nothing is written while the prompt waits.

In `tests/test_panel_config.py`:

- the notes of what was spent have the `~`, and the limits don't.

In `tests/test_script.py` and `tests/test_machine.py`:

- `@wait jobs` holds the script until the stand-in worker ends, and no longer;
- it gives up after its seconds, and the transcript says so;
- the summary counts the job's cost;
- the bar's total grows when a job ends, by what the job cost.

## Before the user tries it

A check on a pseudo-terminal, with a terminal emulator drawing the screen, as for the
panel's steps 6 and 7: the real terminal with the bar pinned, half a line typed at the
prompt, a stand-in job running for a few seconds. The bar is on the last row only, its time
has moved, and the typed line and the cursor are where they were. The one bug of the panel
was of this kind, and no test on a pipe saw it.

## Done when

The tests pass, the check on the pseudo-terminal holds, and a scripted run with a stand-in
job waits for it and reports its cost.

## As built

Built on 2026-10-06, on the branch `addon-agents`. 24 new tests, 1489 in all. Decided while
building:

**The bar**

- **The bar is told two things about the jobs:** `jobs`, the ones that run, and
  `jobs_cost`, what the ended ones cost. The machine tells it whenever a job reports or
  ends, and only when something changed (`Machine.show_jobs()`).
- **A running job on the bar is a `Running`:** the addon, the status line, when it began
  and its tokens. The bar works out the time itself at every draw, so it moves between two
  reports.
- **How the numbers are written:** `0:48`, and past an hour the minutes run on, `62:05`.
  Tokens are `900 tok`, `21k tok`, `1.2M tok`.
- **While the AI works, its activity is what is cut,** and `· 1 job` stays.
- **The cost is the main session's sum plus the jobs' sum,** added on the bar. The machine
  keeps telling the session's sum by itself, as before, which is what the scripted
  terminal books to its lines.
- **With the `~` the bar's right side is one character longer.** The idle hint loses its
  parts one column earlier.

**The beat**

- **`Terminal.refresh()`** is the one function that draws again; it was `_refresh`.
- **The beat is a task of the terminal,** once a second. It starts when the bar is told of
  a running job and ends by itself when none runs. While the AI works it draws nothing:
  the bar's light draws the bar many times a second then.

**Scripts**

- **`@wait jobs` without seconds waits as long as a job runs.** The jobs' own timeout
  bounds that.
- **After a wait the machine looks for what ended.** The scripted terminal hands the
  prompt back as interrupted, or a `wake` in a full-screen program. So a listening AI hears
  of the job by itself before the next line, and otherwise the event is in front of that
  line. Step 10 asked for both.
- **A wait is a record in the transcript,** with its seconds, the line `[1 job still
  running after 180 s]` when it gave up, and the output of an `<events>` message that
  follows it. It is no round trip in the summary.
- **`run_script()` returns the records and a `JobsRun`:** how many jobs were started, and
  what they cost. The summary ends `…, $0.33 (1 job: $0.21)`.
- **The summary keeps its plain `$`.** The plan gives the `~` to the bar, the Agents tab
  and the Config tab's notes.
- **`Jobs.running()` and `Jobs.started`** are new: the jobs that haven't ended, and how
  many were started.

**Old tests that changed, all with the behaviour:** four of the bar's pin the cost, now
with the `~`, and one of them its widths, each a column more. The Config tab's tests of
what was spent have the `~` in sixteen places. The stand-in for `run_script` in the
addons' tests returns the two things.

**How I checked the tests themselves:** ten wrong versions, one at a time: a beat that
never starts, a beat that draws with no job, a bar that isn't told of the jobs, the jobs'
cost put into the session's sum, a long job line cut from its end, `listening` before a
job, a wait that doesn't wait, a wait that never gives up, a summary without the jobs'
cost, no look after a wait. Each fails a test.

**The check on a pseudo-terminal, before the user tries it.** The real machine with the
real terminal, its bar and its panel, on a pseudo-terminal of 24 rows and 80 columns, with
a pretend model and a stand-in worker that works for seven seconds. The bytes were
replayed through a terminal emulator (`pyte`).

| Run | What the screen showed |
|---|---|
| Half a line typed at the prompt, `ls -l`, and no Enter | The bar went from the idle hint to `music: balancing the mix · 0:00 · 21k tok`, and to `0:02` two seconds on, by itself. It was on row 24 only. Every row above it, and the cursor behind `ls -l`, stayed where they were |
| When the job had ended | The bar's cost went from `~$0.05` to `~$0.26`, the idle hint came back, and nothing more was drawn. `a` and Enter then sent `ls -la`, and the text came in order |
| The same, with the beat switched off | The job's time stood at `0:00` three seconds on. So the check can fail |
| In a full-screen program | The bar is the program's last row there. Its time moved, and the program's rows and the cursor stayed |
| With the panel open at the shell | The bar is the panel's last row there, and its time moved. The row `Budget per boot` went to `spent in this boot: ~$0.26` when the job ended; no other row changed. After Esc the typed line was back |

**What the check taught about checking.** A real terminal answers a request for the
cursor's position. My first run didn't, and prompt_toolkit printed a warning and drew its
prompt a row lower after two seconds at the prompt. That was the check's fault, not the
bar's. The check now answers the request from where the emulator has the cursor.

**What I couldn't check**

- **Whether the bar's redraw disturbs typing on a real terminal.** The emulator shows that
  nothing moves; it can't show a flicker. It is tried in the live run of step 13.
- **A scripted run from the command line with a real model.** `run_script()` is tested
  with a pretend model and a stand-in worker; the first real one is step 13's.
