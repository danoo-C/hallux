# Fix 05: the docs say hpm's AI writes no log line, and it does

[The fixes](README.md) · [the plan](../README.md) · about [step 6](../06-ai-session.md)

**Status:** planned 2026-10-24. A docs fix only; no code. **Done** 2026-10-24: both files say it.

**Changes:** `docs/hpm/tutorial.md`, `docs/plans/hpm/live-run-checklist.md`.

## What happened

On 2026-10-24 I "corrected" the tutorial and the checklist to say that from a terminal hpm
writes nothing to `.hallux/hallux.log`. That was wrong. Each AI session writes one line
there when it ends (`_ended` in `hallux/hpm/ai.py`, built in step 6, and step 6's "As built"
says so). `danika`'s log has them:

```
2026-10-24 00:18:22 INFO hpm init: done, ~$0.4462, model claude-opus-5-5
2026-10-24 02:34:22 INFO hpm changelog: done, ~$0.2446, model claude-opus-5-5
```

The same wrong claim was in fix 01's "Also seen"; that bullet now points here.

## What to change

- `docs/hpm/tutorial.md`, under the errors table: "Every AI part prints what it cost when
  it ends … In the Packages tab, a migration also writes a line in the world's log" becomes:
  each AI part prints its cost, and writes a line in the world's log, `.hallux/hallux.log`
  (`hpm init: done, ~$0.4462, model …`), from a terminal or the tab. `grep "hpm "
  .hallux/hallux.log` lists what the AI cost in that world.
- `docs/plans/hpm/live-run-checklist.md`, "If something looks wrong": the parenthesis
  "(From a terminal, hpm writes nothing to the world's log …)" becomes: each AI session
  also writes a line with its cost in `.hallux/hallux.log`.

## Done when

Both files say it, and nothing under `docs/` says the opposite
(`grep -rn "writes nothing to the world's log" docs/` is empty).
