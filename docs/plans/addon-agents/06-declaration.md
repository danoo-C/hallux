# Step 6: the declaration

[The plan](README.md) · the design: [addon-agents.md](../../addon-agents.md), section 4

**Needs:** nothing. **Changes:** `hallux/addons.py`, `hallux/tools.py`, `hallux/config.py`,
`tests/test_addons.py`.

An addon says that it has an agent with `agent()`, and starts a job from a function that
takes `spawn`. This step teaches the loader both, and a list as an argument. Nothing starts
a job yet: the `spawn` an addon gets comes from whoever calls, and in this step that is a
test.

## Build

**`agent()`** returns a plain dictionary. The loader calls it once and checks it.

| Key | Required | The check |
|---|---|---|
| `name` | yes | By the rule for addon names |
| `prompt` | yes | Text, not empty |
| `tools` | yes | A list of plain functions, each passing the checks of an exposed function. It may be empty |
| `effort` | no | One of the five efforts |
| `status` | no | One line, at most 80 characters |

**Each of these skips the addon,** with a note that names the reason:

- `agent()` raises, or returns something that isn't a dictionary;
- a key that isn't in the table, or a required one missing;
- a function in `tools` that takes `spawn`: a job can't start a job;
- `agent()` without an exposed function that takes `spawn`, or the other way round;
- `spawn` in the wrong place: it is the first parameter, or the second after `disk`.

- **Where the five effort names live.** `hallux/config.py` has them today, and it imports
  from `hallux/addons.py` (`hallux/config.py:15`), so the loader can't import from
  `config.py`. The names move to `addons.py`, and `config.py` takes them from there.
- **`connect()` stays the last check** (`hallux/addons.py:275-280`): only an addon that
  loads may report. The checks of `agent()` come before it.

**The loaded addon** holds the declaration. `has_events` is true for an addon with
`connect()` or with an agent, so `addon_listen` takes both kinds.

**`spawn`** is handled like `disk` (`hallux/addons.py:339,355`):

- it needs no type hint and isn't in the schema, so the AI never sees it and can't pass it;
- `call()` takes a `spawn` beside the `disk`, and hands it to a function that asks for it.
  A function that asks and gets none fails, as one that needs the disk does today.
- **It works for one call.** `call()` wraps the `spawn` it was given. When the function has
  returned, or the 10 seconds are over and Hallux has stopped waiting
  (`hallux/addons.py:386-389`), the wrapper is dead: it raises `Refused`. A thread that runs
  on can't start a job behind everyone's back.

**`Refused`,** raised by Hallux's `spawn` when a job can't start:

| Raised with | The AI gets |
|---|---|
| A code | `{"error": "EAGAIN"}` |
| A code and a path | `{"error": "ENOENT", "path": "/home/user/Music/a.score"}` |

- The call wrapper answers it that way, without the name of the Python error in front and
  without a warning in the log: a refusal is no fault of the addon's.
- An addon can catch it, like any error.

**A list as an argument.** A parameter with the hint `list[str]` becomes
`{"type": "array", "items": {"type": "string"}}` in the tool's schema. The other four kinds
stay. The message for a hint that can't become a schema names the list as well.

- **The hint is compared by `==`.** Today a hint is matched with `is`
  (`hallux/addons.py:345`), which works for `str` and `int`. `list[str] is list[str]` is
  false in Python: each is a new object.
- **One test pins the old message** (`tests/test_addons.py:161`) and changes with it.

## Tests

In `tests/test_addons.py`, with fake addons in a temporary folder, as the others:

- a good declaration loads, and the addon holds its name, prompt, tools, effort and status;
- each bad one skips the addon with its reason: every row of the list above;
- an addon with an agent and no `connect()` has events;
- the schema of a function with `spawn` has no `spawn`, and a call that passes one is
  refused;
- a function with `disk` and `spawn` gets both; `spawn` before `disk` skips the addon;
- a function calls its `spawn` and returns `{"pid": …}`;
- `spawn` raises `Refused("EAGAIN")`: the AI gets `{"error": "EAGAIN"}`, and the log has no
  warning;
- `Refused` with a path: both are in the answer;
- a function keeps its `spawn` and calls it after it has returned: `Refused`;
- a function that is still running after Hallux stopped waiting calls its `spawn`:
  `Refused`;
- the config tests still pass with the effort names in their new place;
- `edit: list[str] = []` in the schema: optional, an array of strings; a call with a list
  reaches the function as a list;
- a hint of `list[int]` or a bare `list` skips the addon, with the message;
- every addon that exists loads as before.

## Done when

A fake addon with `agent()` and a `compose(spawn, request, folder, edit)` loads, and a call
through its tool reaches a stand-in `spawn` with the request, the folder and the list.

## As built

Built on 2026-10-05, on the branch `addon-agents`. 52 new tests, 1319 in all. One old test
changed, the one this file names: its message now ends with `bool or list[str]`. Decided
while building:

- **The loaded addon holds an `Agent`:** `addon.agent` has the name, the prompt, the tools
  by name, the effort and the status. Effort and status are `None` when the declaration
  leaves them out. An addon without `agent()` has `None` there.
- **`agent` has to be a function that works without arguments.** Anything else skips the
  addon, as a `stop()` that needs arguments does.
- **A status is one line of 1 to 80 characters.** An empty one is refused.
- **A tool of the agent needn't be in `EXPOSED`.** `EXPOSED` and `tools` are checked by the
  same code, and a refusal names the list it found the problem in.
- **A `spawn` that is dead raises `Refused("ESTALE")`.** The plan named no code. It is the
  name the fenced disk has for a handle that outlived its job.
- **The `spawn` of a call ends twice over:** in the function's own thread as soon as the
  function returns, and in the event loop when Hallux stops waiting. Ending it takes a lock
  that a start also takes. So once the AI has been told `timed out`, no job can start, not
  even one that was being started in that moment.
- **A function that takes `spawn`, called without one, fails loudly:**
  `compose starts a job, and this call can't start one`, with a line in the log. That is
  what every machine says until step 10 wires `spawn` up.
- **`build_addon_tools` takes the `spawn`.** The machine doesn't pass one before step 10,
  and `build_addon_servers` is as it was.
- **A hint is compared by `==`,** and each schema gets a copy of its own. `list[int]`, a
  bare `list` and `list[list[str]]` are refused.
- **`hallux/config.py` takes the five effort names from `hallux/addons.py`.** `app.py` and
  the Config tab read `config.EFFORTS` as before.

**The "Done when" is a test:** a fake addon with `agent()` and
`compose(spawn, request, folder, edit)` loads, and a call through its tool reaches a
stand-in `spawn` with the request, the folder and the list, as a list.

**Nothing here needs a terminal or a model.** No real addon has an agent before step 13:
the last test loads the real addons folder and finds none.

**The lines of `addons.py` moved.** The design's references into the file, and step 10's
one into its tests, are set again.
