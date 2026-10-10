# Step 13: the composer

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), sections 3,
4 and 15

**Needs:** steps 2, 11 and 12. **Changes:** `addons/music.py`,
`tests/test_addon_music.py`, `tests/test_music_manual.py`.

The first agent: a composer for the music addon. `compose` returns in a second, and the
song is written in the background, at a higher effort than the shell runs at. From this
step on a user can start a job. It ends with a scripted run and the first live run, where
the numbers of the design get measured.

## Build

**In `addons/music.py`:**

| Part | What |
|---|---|
| `agent()` | The declaration: `name` is `composer`, its prompt, `tools` is `[check]`, `effort` is `high`, `status` is `composing…` |
| `compose(spawn, request, folder, edit=[])` | Starts the composer and returns `{"pid": …}`. Its docstring is what the AI is told |
| `EXPOSED` | `[play, stop, check, compose]` |

- **`compose` builds the brief** from the request. The request is the main agent's text and
  is passed on as it is; the limit of 2000 characters is `spawn`'s.
- **`folder` and `edit` go to `spawn` unchanged.** What Hallux refuses there reaches the AI
  as Hallux says it.

**The manual is split in two.** Two places in its second part are reworded, so that the
part reads right for a reader that has `check` and not `play`:

| Today (`addons/music.py:184-191`) | Reworded |
|---|---|
| The heading "WHAT PLAY RETURNS" | It names both: what `play` and `check` return |
| "Fix them all, then play again." | "Fix them all, then try again." |

Nothing else of the text changes. The manual's tests pin the old heading in three places
(`tests/test_music_manual.py:25,86,304`), and those change with it.

| Part | Who reads it |
|---|---|
| The functions: `play`, `stop`, `check`, `compose`, and the events | The main agent |
| Writing a score: the format, the recipes, what `play` returns, the limits | The main agent and the composer |

- `prompt()` returns both parts, as today with the new lines.
- **The composer's prompt** is its role, then the second part, then what `check` does. It
  doesn't get the lines on `play`, `stop` and `compose`: it can't call them.

**What the manual says that is new,** for the main agent:

- `compose(request, folder, edit)` has a composer write a new song into the folder, or
  change the scores listed in `edit`. It returns a pid at once;
- the song isn't there yet: never wait for it, and never imagine it;
- its end arrives as an event, `{"event": "job", …}`, with the files that were written.
  Listen to the addon to hear it at once;
- the folder has to exist, and it can't be a home folder itself.

**The composer's role,** a draft of what it says, not of its words:

- you write one song as a score file, in the folder you are given;
- name the file after the song, in lowercase with dashes, ending in `.score`;
- `check` it, fix what it reports, and check again. Stop when it is clean and the peak is
  between 50 and 100, or after four rounds;
- say what you are doing with `set_status`.

**The manual's size.** It grows by about 400 characters. Step 2 moved the limit to 8500.

## Tests

In `tests/test_addon_music.py` and `tests/test_music_manual.py`:

- the file passes every check of the loader, with its agent;
- the schema of `compose` has `request`, `folder`, an optional `edit` as a list, and no
  `spawn`;
- `compose` with a stand-in `spawn`: the brief holds the request, and the folder and the
  list arrive unchanged;
- a refusal of `spawn` reaches the AI as `EAGAIN`;
- the composer's prompt holds the score format and `check`, and none of the lines that
  describe `play`, `stop` or `compose` as functions to call. It doesn't tell its reader to
  play anything;
- the manual is under its limit, and still holds everything the tests of the manual look
  for today, under the heading's new name;
- with a stand-in worker that writes the design's drum beat: `compose` returns a pid, the
  worker's `check` reads its own copy and returns the beat's numbers, the file lands, and
  the event names it.

## The scripted run

With a real model, in a new world:

```text
hallux install a program called compose: "compose WORDS" has the music addon compose …
mkdir Music
compose a short drum loop
echo still here
@wait jobs 180
ls Music
```

The proof is in `hallux.log`: the `echo` round trip lies between the job's start and its
end, the `compose` round trip took seconds, and the new file is in the last listing.

## The first live run

By the user, in `test-hallux`. It measures what the design left open. If step 16 is built
by then, the panel's Details tab shows each round of `check` as it happens, which is the
quickest way to see what the composer's prompt needs.

1. **What a composition costs and how long it takes,** at high effort. The budgets and the
   timeout are set again from it.
2. **Whether the shell stays quick** while the composer works.
3. **Whether the AI prints the `Done` line** and keeps the pids apart, without being asked.
4. **A player that composes:** it shows "composing…", the song arrives, and it plays,
   without a key being pressed.
5. **`ps` and `htop`** while a job runs.
6. **`kill`** of a running composer: the folder is as it was.
7. **The bar while typing:** does the redraw once a second disturb?
8. **A second `compose`** while one runs, and one after the budget is used up: what does
   the program print?

## Done when

The scripted run passes, the live run is written up below, and the defaults of the six
settings are what the live run says they should be.

## As built

### The code, on 2026-10-06

Built on the branch `addon-agents`, with no model call. 9 new tests, 1527 in all. **The
step isn't done:** its scripted run waits for the user's go, and its live run is the
user's. Decided while building:

- **The manual is two texts in `addons/music.py`,** `FUNCTIONS` and `WRITING`, and
  `prompt()` joins them. It has 8,492 characters, of the 8,500 it may have.
- **The lines on `compose` are four,** shorter than the plan's list. What the main prompt's
  section on jobs says already is said in half a line here: never wait for the song, never
  imagine it. For hearing its end at once the manual names the tool: `addon_listen brings
  it at once`.
- **The composer's prompt is three texts:** its role (`COMPOSER`), then `WRITING`, then
  what `check` does (`CHECKING`). 8,166 characters; Hallux's rules for a worker go in
  front.
- **The role says two things beyond the plan's draft:** a score it was given is changed in
  its own file, and the manual's second part is all it knows of the format, so it uses
  nothing that part doesn't name.
- **`compose` hands the request on as the brief, unchanged,** with the folder and the list.
- **`check` is the composer's one tool of the sound card.** It can't call `play`, `stop` or
  `compose`, and no line of its prompt tells it to.

**What changes for a running machine.** From here on every machine that has the music
addon gets the section JOBS at the end of its prompt, the tools `list_processes`,
`kill_process` and `compose`, and the six rows in the Config tab. The panel's Agents and
Details tabs are live there, and a line in `hallux.log` at the start names the composer's
model and effort.

**Old tests that changed, all with the behaviour:** the addon's lists of functions and of
tools have `compose`; the manual's tests have the heading's new name in three places; and
the test that said no real addon has an agent says that music has its composer.

**How I checked the tests themselves:** five wrong versions of the addon, one at a time: a
line in the second part that tells its reader to call `play`, a `compose` that changes
what it hands on, a composer that gets the whole manual, a composer that may call `play`,
and `compose` not exposed. Each fails a test.

**What I couldn't check:** whether the composer's prompt makes a good composer. That takes
a real model: the scripted run shows that a song is written at all, and the live run how
many rounds of `check` it needs and what it costs.

### The scripted run

Not run. Its three proofs are in the log of the user's first live run, below, on the real
model: the `compose` round trip took 12.5 seconds, `echo hi` was answered between the job's
start and its end, and the file was in the folder afterwards. What no run with a real model
has shown yet is `@wait jobs` and the summary's count of the jobs; both are tested with a
pretend model. Whether the scripted run is still wanted is the user's to say.

## What the live run taught

### The first run, by the user, on 2026-10-07

In a new world, with the defaults: Opus for the machine at effort low, and the composer on
the same model at effort high. What follows is from that world's `hallux.log`. The request
was a drum solo in four parts, on a kit with five toms, three crashes, a ride, a hi-hat and
a splash.

| Point of the list | What the log shows |
|---|---|
| 1. What a composition costs, and how long it takes | **$0.78 and 265 seconds,** in 16 turns and 164,050 tokens. The cap per job was $1.00 and the timeout 600 seconds |
| 2. Whether the shell stays quick | `echo hi` took 2.5 seconds, `cd` 2.2, an `ls` 4.5. One `ls` took 11.4 |
| 3. The `Done` line, and the pids | The AI listened to the addon by itself, right after `compose`. The event went out the moment the job ended, and the AI printed `[1]+  Done  compose …` and `compose: job 30001 wrote ~/Music/drum-solo.score (265 s)`, with the right pid |

- **`compose` returned in 12.5 seconds,** for $0.06: the AI read the manual, looked at the
  folder, called `compose` and `addon_listen`, and printed `compose: job 30001 started`.
- **The file wasn't in the folder while the job worked.** Two `ls` in `Music` during the
  job listed nothing.
- **The composer thought for almost three minutes before its first tool call.** Its first
  status line came 174 seconds after its start. Until then its row said `composing…`.
- **It made two rounds of `check`.** The first said peak 312, turned down to 32 percent. It
  then changed ten lines with ten calls of `edit_file`, one model turn each, and the second
  check was clean: 71.2 seconds, peak 57.
- **The song landed and plays:** 335 lines, 7.4 KB. `play` returned 71.2 seconds and peak
  57, and the `finished` event came 73 seconds later.
- **The whole run cost $1.13:** $0.35 for the machine's own session, 15 round trips, and
  $0.78 for the job.
- **Nothing in the log is a warning or an error.**
- **The user raised four budgets in the panel while the job ran,** and saved them: events
  and ticks to $10, all jobs to $20, one job to $10. They hold from the next job on; the
  job that ran kept its $1.00.

**What the run suggests about the cap,** for the user to decide: the cap per job is tight
at $1.00. This composition used 78 cents of it with two rounds. A third round would have
passed the cap, and a job that is killed loses all of its work.

**Decided by the user on 2026-10-10:** the defaults are $2.00 a job and $4.00 for all jobs.
The timeout stays 600 seconds. They are in `hallux/config.py`, and the design's table has
them. A world whose `config.toml` names its own budgets keeps those.

### Two lines for the composer's prompt

**Decided by the user on 2026-10-07:** the suggestion is written down here, and it is built
with the next step of the plan, [step 14](14-kept-screens.md). That step's file says what
is built and how it is tested. Nothing of it is built yet.

**What the run showed:**

| | In the log |
|---|---|
| The first status line | 174 seconds after the job's start. The composer thought first, and called `set_status` only when it began to write. Until then its row said `composing…`, the line its declaration gives it |
| The first write | 207 seconds after the start: the whole score, in one `write_file` |
| The changes after the first `check` | Ten calls of `edit_file`, each in a model turn of its own, within 15 seconds. They were 10 of the job's 16 turns |

**The two lines,** both for the composer's role, the text `COMPOSER` in `addons/music.py`:

| | What the role says today | What it would say |
|---|---|---|
| A status line first | "Say what you are doing with set_status, in a few words: sketching the drums, balancing the mix." It is the last of three points | It becomes the first point: before anything else, call `set_status` with what you are about to write, in a few words. Then call it again whenever you start something new |
| The changes of a round in one turn | "Check it with check, fix everything it reports, and check again." | It adds: make all the changes of a round in one turn, with several `edit_file` calls together, or with one `write_file` of the whole score when most of its lines change |

**Why "in one turn", and not "in one write".** My first wording of the suggestion was one
write of the whole file in place of ten edits. That saves nine turns too, and has a price:
the composer writes all 335 lines again, where an edit writes one. Several edits in one
turn save the same nine turns without it. So the line names both, and says when the whole
score is the better one.

**What it is expected to change, and what nobody knows yet:**

- **Fewer turns, for certain,** if the composer follows it: 7 in place of 16 for a run like
  this one. Every turn sends the whole conversation to the model again, and a job has 60
  turns at most.
- **How many cents that saves isn't in the log.** The log has a job's cost as one number.
  The ten edits were short turns, and most of this job's cost was probably its thinking and
  the first write.
- **Whether a model at high effort sets a status line before it thinks** is something only
  a run shows. It thinks at the start of a turn, and the line asks it to make a small turn
  first.
- **The row is never empty either way.** It says `composing…` from the job's start. The
  line makes it say what is being composed, a few seconds in.

It is tried in the next live run of a composition.

**Still to try,** from the list above: a player that composes (4), `ps` and `htop` while a
job runs (5), `kill` of a running composer (6), whether the bar's redraw disturbs typing
(7), and a second `compose` while one runs or after the budget is used up (8). The log
can't answer 7; only the user can.

### The second run, by the user, on 2026-10-10

In `test-hallux`, with [the checklist](live-run-checklist.md) of step 17. What every point
of that list showed is in [step 17's file](17-live-run.md). For this step's own list:

| Point of the list | What the run showed |
|---|---|
| 4. A player that composes | The player showed the job's pid and time from its ticks. When the job ended, the player was woken at once, the AI answered as the player, and the song played without a key |
| 5. `ps` and `htop` while a job runs | Both read `list_processes`, and `htop`'s ticks carried the job's row |
| 6. `kill` of a running composer | `kill 30005` ended it. Nothing was written, and the folder was as before |
| 7. The bar while typing | It doesn't disturb: the user ticked it |
| 8. A second `compose` | Refused while one ran, and the program said `compose: composer busy`. One after the budget is used up can't be reached at the shell: every typed line fills that budget |

**Four compositions:** 124, 141 and 124 seconds for three new songs, at $0.42, $0.42 and
$0.37, each in 14 turns, and 22 seconds and $0.10 for a change to one of them. That is
about half of the first run's time and cost, and a fifth of the new cap per job.

**The two lines for the composer's prompt,** which step 14 built:

| The line | What the composer did |
|---|---|
| A status line before anything else | Its first call was `set_status`, as the line asks. But it thought first: the call came 82 seconds after its start, where the first run had 174. In a later job of the same day, which changed a score, it came after 3 seconds |
| The changes of a round in one turn | It didn't. After its first `check` it made seven `edit_file` calls, one a second, each in a turn of its own |

So the role's words don't change how the model works here: it thinks before it calls
anything, and it calls one tool a turn. Neither costs much: the turns of the edits took a
second each.

**What is left of this step:** the scripted run, which was never run. Whether it is still
wanted is the user's to say.
