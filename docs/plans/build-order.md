# Build order: the config panel, then addon agents

**What this is:** the one page to read before building either feature. It says in which
order the steps of the two plans are built, what has to happen before some of them, and how
a step is worked. It holds no status: each plan's README has a table for that, and those
two tables are the only place that says what is built.

**Where things stand, on 2026-10-05:** both features are designed, planned and reviewed.
Nothing is built. No code has been written for either.

| | The config panel | Addon agents |
|---|---|---|
| The design | [config-panel.md](../config-panel.md) | [addon-agents.md](../addon-agents.md) |
| The plan | [config-panel/README.md](config-panel/README.md), 8 steps | [addon-agents/README.md](addon-agents/README.md), 17 steps |
| The review of both | [plans-review-2026-10-04.md](../plans-review-2026-10-04.md) | The same |

---

## In short

1. **The config panel first,** its steps 1 to 8 in their order.
2. **Then a short check of the agents plan against the code,** because the panel has moved
   the lines it cites.
3. **Then addon agents,** its steps in their order, with one swap: step 16 before step 13.

Two steps of the agents plan touch no file the panel touches and can be built at any time,
also before the panel: its step 1 (whole-file writes) and its step 2 (`check`).

---

## How a step is worked

These are the user's rules for this project. They hold for every step.

- **One step at a time, and only when the user asks for it.** Don't start the next one
  because the last one went well.
- **Read three things first:** this page, the plan's README, and the step's own file. The
  README holds the decisions the steps share.
- **Commit only when asked.** The user pushes and opens pull requests.
- **Ask which branch to build on.** The designs and plans are on `multi-agent`. Earlier
  features each had a branch of their own.
- **A step is done** when its tests pass with all the old ones, its "Done when" holds, its
  status in the README's table says so, and what was decided while building is written into
  the step's file under "As built".
- **Say what could not be checked.** No real terminal and no sound can be reached from the
  sandbox. Steps that need them end with something for the user to try.
- **A paid check waits for the user's go.** There are two, below.
- **Make a mistake loud.** Where something an author left out would get a quiet fallback,
  make it a failed check with a readable reason.

**The tests:** `env -u FORCE_COLOR .venv/bin/python -m pytest -q`. There are 838 today. With
`FORCE_COLOR` set in the shell two of them fail, because Python then colours a child's
traceback; that is in the code today and no step of the panel's plan touches it.

**The plans' own decisions.** Each README has a table of decisions the plan took by itself.
The user hasn't gone through them one by one. Building a step means accepting the ones it
uses; if one looks wrong when its step comes, say so before building it.

**Line numbers** in the steps are the code's of 2026-10-04. Each reference also names what
stands there, so find it by that.

---

## Part 1: the config panel

In the order of its plan. "P3" is step 3 of the panel's plan.

| Order | Step | Needs | Before it |
|---|---|---|---|
| 1 | P1. Checking and saving a setting | | |
| 2 | P2. A setting changes in a running machine | P1 | |
| 3 | P3. The budget per boot | P2 | |
| 4 | P4. Switching the model | P2 | **A paid check,** a few cents: does `set_model()` switch a running session, and what about Haiku. The step's file says what is built for each outcome |
| 5 | P5. The panel by itself | P2 | |
| 6 | P6. The panel at the shell | P5 | The key check is done: Ctrl+F12 arrives as `^[[24;5~` in the user's terminal |
| 7 | P7. The panel over a full-screen program | P3, P6 | |
| 8 | P8. The bar, the documentation and the live run | P4, P7 | The live run is the user's |

- **P3, P4 and P5 don't depend on each other.** If the paid check has to wait, P4 can move
  to any place before P8.
- **From P3 on a running machine behaves differently,** also without a panel: a boot that
  has used its budget holds messages back. Ctrl-D still leaves it.
- **Nobody can open the panel before P6.**

---

## Part 2: the check between the two

When the panel is built, before the first step of addon agents that needs it:

- **Read the agents plan against the code as it is then.** Its line references are from
  before the panel. It is a read, and fixes to the plan's text; no code.
- **Look hardest at its steps 10, 11 and 16.** They use what the panel built: the Config
  tab's rows, `keep_form`, the wait that can be started again, and the host that hands a
  tab `show`, `close` and the picked job. Check that the names and shapes in the plan are
  the ones that were really built.
- **Carry over what the panel's live run taught,** if it changes anything the agents plan
  assumes.

---

## Part 3: addon agents

"A7" is step 7 of the agents plan. The order is the plan's, with A16 moved in front of A13.

| Order | Step | Needs | Before it |
|---|---|---|---|
| 1 | A1. Whole-file writes | | Can be built any time, also before the panel |
| 2 | A2. `check` | | The same |
| 3 | A3. The six settings | P1 | |
| 4 | A4. The fenced disk | A1 | |
| 5 | A5. The landing | A4 | |
| 6 | A6. The declaration | | After the panel: it changes `config.py`, as the panel does |
| 7 | A7. The jobs, with a stand-in worker | A3, A5, A6 | |
| 8 | A8. The caps | A7, P3 | |
| 9 | A9. A job's real session | A6, A7 | **A paid check,** a few cents, with three questions about the SDK: the cost after `interrupt()`, where live tokens come from, whether the dollar cap stops mid-turn |
| 10 | A10. The main agent's side | A8, A9, P5 | |
| 11 | A11. A job's end in a full-screen program | A10, P3, P7 | |
| 12 | A12. The status bar and the costs | A10 | |
| 13 | A16. The panel's two tabs | A10, P5 to P7 | |
| 14 | A13. The composer | A2, A11, A12 | The scripted run costs a little. The first live run is the user's, and sets the budgets again |
| 15 | A14. Keeping a screen | | After the panel: it changes `blockmode.py` and `terminal.py` |
| 16 | A15. Job control | A10, A14 | |
| 17 | A17. The documentation and the live run | A13, A15, A16 | The live run is the user's |

- **Why A16 before A13:** the Details tab shows each round of the composer's `check` as it
  happens. That is the quickest way to see what the composer's prompt needs in its first
  live run.
- **A1 to A9 need no model** for their tests. A stand-in worker runs the jobs until A9
  brings the real session.
- **No machine can start a job before A10.** The first job a user can start is a
  composition, in A13.
- **A14 needs nothing of the other steps.** It can come earlier, any time after the panel.

---

## What stays open until a live run

No step can close these; the last step of each plan does.

| | Closed by |
|---|---|
| Whether the shell's screen comes back exactly after the panel | P8 |
| Whether the short wait after Esc is safe over a slow line | P8 |
| What the first answer after a model switch costs | P4's check, then P8 |
| What a composition at high effort costs, and how long it takes | A13 |
| Whether a second session slows the first | A13 |
| Whether the bar's redraw once a second disturbs typing | A13 |
| Whether a kept screen comes back exactly | A15, then A17 |
| How much memory each Claude Code process takes | A17 |
