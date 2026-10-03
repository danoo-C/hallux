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
- **If the switch fails,** the bar shows the error as it shows a model that failed, the
  message is sent on the old model, and the name stays waiting for the next message.
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
- a switch that raises: the error is on the bar, the message went out, and the next message
  tries again;
- after a reboot the session starts on the new model, and nothing waits.

## Done when

The check is written up below, and a test machine answers one line on one model and the
next line on another.

## As built

Not built. The check hasn't run.
