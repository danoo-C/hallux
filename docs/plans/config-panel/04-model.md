# Step 4: switching the model

[The plan](README.md) · the design: [config-panel.md](../../config-panel.md), section 5 and
"Still to find out"

**Needs:** step 2. **Changes:** `hallux/machine.py`, `hallux/config.py`,
`tests/test_machine.py`.

The SDK can switch the model of a running session: `ClaudeSDKClient.set_model()`. Nobody has
run it with Hallux's kind of session. So this step starts with a check, and what is built
depends on what the check shows.

## The check, first

A throwaway script, like the one for the addon agents' design. It makes model calls: a few
cents. **The user says go before it runs.**

A session with Hallux's options: one in-process tool, an effort, no built-in tools. Then:

| Question | How it shows |
|---|---|
| Does the next answer come from the new model? | `AssistantMessage.model`, and the models named in the result's `model_usage` |
| Do the conversation and the tools survive? | The second answer repeats a word from the first, and calls the tool |
| What does the first answer after the switch cost? | Its cost beside the cost of the same question without a switch |
| From a model with an effort to Haiku, and back? | Whether those answers fail, and with what |

**What is built, by the outcome:**

| Outcome | Build |
|---|---|
| It works | Everything below |
| It works, but not to or from Haiku | Everything below, and a switch that crosses to or from Haiku waits for the next boot. The panel says so on the row |
| It doesn't work | Nothing below. `model` stays under `reboot` in `config.WHEN`, as the design says. The step is then this file with its "As built" filled in |

The numbers and the outcome go into "As built" at the end of this file.

## Build

- **A changed model is set aside.** `change("model", …)` replaces the settings as in step 2,
  and notes the name as waiting.
- **It is switched just before the next message goes out.** `exchange` calls
  `client.set_model()` with the waiting name, then sends. An answer that is being written is
  never touched.
- **The bar changes when the switch has happened,** not when you set the name. `running`
  gets the new model then, and the log a line: `model: claude-opus-5-5 -> claude-sonnet-5-5`.
- **If the switch fails,** the message is sent on the old model, and the name stays waiting
  for the next message. The bar says so with a note, `model not switched: …`, which goes
  when a switch works. It can't be the bar's error: the terminal wipes the error when an
  answer starts (`hallux/terminal.py:213`), and that is a moment later.
- **The Effort row on a model without efforts.** Haiku gets none (`hallux/config.py:34`).
  `running` then has no effort, and the row says `running now: none`.
- **The Haiku outcome needs a note on the Model row,** which lives in step 5's file. Steps 4
  and 5 can come in either order: whichever is built second adds the note.
- **A boot starts on the model in the settings,** as today. Nothing waits then.
- **`config.WHEN`** has `model` under `now`.
- **The fallback model** isn't touched by this: it changes at the next boot.

## Tests

In `tests/test_machine.py`. The fake client gets a `set_model` that notes what it was
called with:

- after `change("model", …)` the session isn't switched yet, and the bar shows the old
  model;
- with the next line, `set_model` is called once, before the message, and the bar shows the
  new model;
- the line after that doesn't switch again;
- a change back to the running model before any message: no switch at all;
- a switch that raises: the note is on the bar and still there after the answer, the message
  went out, and the next message tries again; when that works, the note is gone;
- after a reboot the session starts on the new model, and nothing waits.

## Done when

The check is written up below, and a test machine answers one line on one model and the
next line on another.

## As built

Built on 2026-10-05, on the branch `config-panel`, after step 5. 6 new tests, 1020 in all.
The outcome of the check is the first of the three: **it works,** also to and from Haiku.

### The check

Run on 2026-10-05 with the SDK 0.2.163 and Hallux's own options: its system prompt, its
in-process tools, the effort `low`, no built-in tools. The machine's folder held one file.
Three lines were typed: `cat note.txt`, then `!!`, which needs the line before it, then
`echo done`.

| A session that started on Sonnet 5.5 | Answered by | Tools | Cost |
|---|---|---|---|
| `cat note.txt`, before any switch | `claude-sonnet-5-5` | `stat`, `read_file` | $0.0515 |
| Switched to Haiku 4.5. `!!` | `claude-haiku-4-5-20251001` | `read_file` | $0.0209 |
| `echo done` | Haiku | | $0.0015 |
| Switched back to Sonnet. `!!` | `claude-sonnet-5-5` | | $0.0064 |
| Switched to Opus 5.5. `echo done` | `claude-opus-5-5` | | $0.1005 |

| The same lines on Haiku from the start, no switch | Cost |
|---|---|
| `cat note.txt` | $0.0078 |
| `!!` | $0.0015 |
| `echo done` | $0.0015 |
| Then switched to Sonnet. `!!` | $0.0133 |

| Question | Answer |
|---|---|
| Does the next answer come from the new model? | Yes. `AssistantMessage.model` named it each time, and it appeared in the result's `model_usage` |
| Do the conversation and the tools survive? | Yes. After each switch `!!` ran the line before it again, and the in-process tool was called |
| What does the first answer after the switch cost? | On Haiku $0.0209, against $0.0015 for the same line without a switch: fourteen times as much, once. The next line was $0.0015 again. One `echo done` on Opus after a switch was $0.10. This session was three lines old; a long boot has more to read |
| From a model with an effort to Haiku, and back? | Both work. A session that started on Haiku, with no effort, switches to Sonnet too |

**Two things the plan didn't ask,** found on the way:

- **A name that is no model is refused by the session.** `set_model("claude-banana-9")`
  raises `Model 'claude-banana-9' not found`. The session stays on its model and answers
  the next line as if nothing had happened.
- **A session that starts on such a name fails its first message:** `There's an issue with
  the selected model (claude-banana-9). It may not exist or you may not have access to it.`
  For Hallux that is a boot that fails, and Hallux ends.

**The check cost $0.22,** not the few cents the plan named: $0.10 of it was the one answer
on Opus, and $0.05 the first answer on Sonnet.

### Decided while building

- **Nothing notes a name as waiting.** A model waits as long as the setting isn't what
  runs: `hardware.model` against `running.model`. So a change back to the running model is
  no switch without any code for it.
- **`switch_model()` is called in `exchange`,** inside the busy period, just before the
  message is sent.
- **A switch that fails is said once,** on the bar and in the log, however often it is
  tried again: `model not switched: Model 'claude-banana-9' not found`. The note goes when
  a switch works, when the setting is the running model again, and when a boot starts.
- **The Model row's warning says what the check found:** `a wrong name is refused; saved,
  it ends Hallux at the next boot`. The plan's words, "fails the next answer", aren't what
  happens: the next answer comes, from the old model.
- **`running` holds the effort the session was really given.** A session that starts on
  Haiku is given none. After a switch the bar shows that effort for a model that has
  efforts, and nothing for Haiku. So a session that started on Haiku shows no effort on
  Sonnet either. Which effort it then runs at isn't known; the model's own, presumably.
- **The fake client of the tests** notes every `set_model` with how many messages had gone
  out before it, and can refuse a name the way the SDK does.

**For step 8, in the design:** `docs/config-panel.md` still says in section 5 that the
switch was never run, and lists it under "Still to find out". The three things to carry
over are in the tables above: it works, what the first answer costs, and what a wrong name
does.
