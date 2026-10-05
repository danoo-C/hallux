# Step 12: the status bar and the costs

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), sections 11
and 15

**Needs:** step 10. **Changes:** `hallux/statusbar.py`, `hallux/terminal.py`,
`hallux/machine.py`, `hallux/script.py`, `tests/test_statusbar.py`,
`tests/test_terminal.py`, `tests/test_script.py`.

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
- **The bar's words for the new tools:** `list_processes` and `kill_process` get verbs, as
  the other tools have (`hallux/statusbar.py:25`). A verb isn't enough for the kill: the bar
  shows a tool's `path`, `src` or `name` after the verb (`hallux/statusbar.py:41`), and a
  kill has a `pid`. It is shown as `killing 30001`.

**The `~`.** The cost becomes `~$1.42`. The number is what the tokens would cost at the
API's list prices; with a Claude subscription nobody is billed that amount. The README
says what the `~` means, in step 17.

**The total** on the bar is the main session's sum plus the jobs' sum, which the machine
keeps apart (step 8). A job is in it from the moment it has ended; a job that was killed
counts too.

- **Three tests pin `$0.00` without the `~`** (`tests/test_statusbar.py:17,25,33`) and
  change with it.

**The bar moves while the prompt waits.** Today it is drawn while the AI works, or when
something is printed. A job's time and tokens change while the user sits at the prompt.

- While a job runs and the main agent is idle, the bar is drawn again once a second.
- When no job runs, nothing is drawn, as today.
- **One timer, in the terminal.** The panel's two tabs (step 16) need the same beat for
  their times. Whichever of the two steps is built first makes the timer, and the other uses
  it.
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
  (`hallux/script.py:124-126`), and a job's cost would land on whatever that was. So the
  bar's cost that the scripted terminal is told stays the main session's.

## Tests

In `tests/test_statusbar.py`:

- idle with one job: the addon, the status, `0:48`, `21k tok`;
- idle with two jobs; working with one job;
- an error and a note win over a job;
- the cost has the `~`, with and without jobs;
- a job's line that is too long for the bar is cut, and the hardware on the right stays;
- the two new tools have their words.

In `tests/test_terminal.py`:

- with a job running, the bar is written again within two seconds while the prompt waits,
  and what was typed is still the line;
- with no job, nothing is written while the prompt waits.

In `tests/test_script.py` and `tests/test_machine.py`:

- `@wait jobs` holds the script until the stand-in worker ends, and no longer;
- it gives up after its seconds, and the transcript says so;
- the summary counts the job's cost;
- the bar's total grows when a job ends, by what the job cost.

## Done when

The tests pass, and a scripted run with a stand-in job waits for it and reports its cost.
