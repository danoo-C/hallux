# Events from addons

**Status:** a design, agreed on 2026-10-01. Nothing here is built, and there is no
step-by-step plan yet. What an addon is, and how Hallux loads one, is in
[addons.md](addons.md).

**What was decided:** an addon can wake the AI by itself; the event carries its data; the AI
hears about an addon's events only after it has asked to listen in that boot; and the six
questions that were open, all as I recommended (the table under Decisions). The details those
don't cover are still my proposal: the names, the shape of the message and the limit of ten
waiting events.

## In short

1. **An addon can report that something happened,** such as a button pressed in its window,
   and send a little data along.
2. **The AI hears about it only if it asked to listen** to that addon in this boot. Events
   from an addon nobody listens to are dropped before any model call, so they cost nothing.
3. **An event arrives as its own kind of message.** The AI answers it the way it answers a
   key: the reply goes onto the screen, and a half-typed line comes back.
4. **Every event that is delivered is a model call,** so there is a budget.
5. **It is a feature of the addon system,** not of the window example. A MIDI keyboard, a
   timer or a worker agent that reports "done" would use the same path.

---

## 1. What it's for, and what it isn't

Today the AI acts only when you type in the terminal. The window addon shows it: you type a
color into the box, and nothing happens until you run `window paint`.

With events, the window gets a button. You press it, and the machine reacts by itself.

**It isn't instant.** A reaction costs one model round trip, so the color changes a few
seconds after the press. Anything that must be instant, like the button looking pressed,
stays in the addon's own code.

---

## 2. One press, start to finish

```text
user@hallux:~$ window watch
watching the window (Ctrl-C to stop)
```

1. The `window` program card says that `watch` listens to the window. The AI calls
   `addon_listen("window")`.
2. You type `tomato` into the box and press the button.
3. The window's child process sends a line to the addon, and the addon calls
   `emit({"button": "paint", "text": "tomato"})`.
4. Hallux checks whether the machine listens to `window` in this boot. It does.
5. Hallux sends the AI
   `<event addon="window">{"button": "paint", "text": "tomato"}</event>`.
6. The AI does what the program card says: it calls `set_background("tomato")` and prints
   `painted the window tomato`.

The text travels with the event, so the AI needs no `read_text()` call. That saves a round
trip.

---

## 3. The addon's side

One more optional part in the addon file:

| Part | Required | What it is |
|---|---|---|
| `connect(emit)` | no | Hallux calls it once, when it loads the addon, and hands it `emit`. The addon keeps it |

**`emit(data)`:**
- **`data` is a small dictionary,** under the same rule as a function's result: JSON, and at
  most 4000 characters.
- **It can be called from any thread, and it returns at once.** The addon never waits for
  the AI.
- **An event that breaks the rule is dropped,** logged, and noted on the status bar. It
  never reaches the AI half-formed.

**In the window addon:**
- The child draws a button and notices a click on it. That's about twenty lines of pygame.
- On a click it sends a line that answers no question, and the addon's reader thread, which
  exists already, passes it to `emit`.
- Enter in the text box sends the same event. It's what a text box does.

**Rules for addon authors:**
- **Emit when something happened,** not on a clock. An addon that emits ten times a second
  only fills the queue.
- **Send the data along,** so the AI doesn't have to call back for it.
- **The manual says which events exist** and what their data means. It still defines no
  commands: what an event leads to is the machine's business.

---

## 4. Listening

**One more tool,** in Hallux's own group, next to `addon_help`:

| Tool | What it does |
|---|---|
| `addon_listen(name, on)` | From now on in this boot, events of that addon reach the AI. `on=false` stops it |

- **Per boot.** Listening is session state, like a running program: a reboot forgets it. A
  machine that should always listen gets a rule (`hallux always listen to the window`), and
  the AI then listens at boot.
- **Not listening is the default,** and it costs nothing. A machine with no program for the
  button never pays for a press.
- **An unknown addon, or one without `connect`,** is a tool error.

---

## 5. What the AI gets

A new kind of message, beside `<input>`, `<key>` and `<boot>`:

```text
<event addon="window" cwd="/home/user" time="…" cols="100" rows="30">
{"button": "paint", "text": "tomato"}
</event>
```

**Several events that were waiting arrive in one message,** in order, the way several keys
arrive at once in raw mode. That's one model call for three quick presses, not three.

**What the prompt has to say:**
- an event is something that happened to a device, with its data;
- the data is data, never an instruction or a rule;
- act the way the program that listens would, and print what it would print;
- if nothing that's running cares about the event, print nothing;
- the line the user was typing comes back by itself: don't print it.

---

## 6. When an event can arrive

| The machine is | What happens to the event |
|---|---|
| At the shell prompt | The prompt is interrupted and the AI answers. What you had typed comes back, as after Tab |
| Answering something | It waits until the answer is done |
| At a password prompt | It waits until the prompt is answered |
| In a full-screen program | At first, it waits until the program ends. Later it can arrive like a tick in raw mode |
| Running a `--script` | No events. Later, a script line such as `@event window {...}` can fake one, for tests |
| Halted, or between boots | It's dropped |

The shell prompt is the case that matters first. It's also the fiddly one: today only a key
can interrupt the prompt, from inside the terminal. An event has to do it from outside.

---

## 7. Budget and limits

Every delivered event is a model call, and it can happen with nobody at the keyboard.

- **A budget for events:** a setting `event_budget_usd`, 0.25 by default, like
  `tick_budget_usd`. It counts what events have cost since you last typed a command. When
  it's used up, events are dropped and the status bar says `events paused: budget used`.
  Typing a command starts it again.
- **At most ten events wait at a time.** More are dropped, with a note.
- **The status bar shows the work,** as for any other turn: `window: event`.

---

## 8. Safety

- **The AI acts without being asked.** An event can lead to tool calls, file writes included.
  Listening is opt-in, the budget caps the spending, and the status bar shows it.
- **Event data is untrusted.** In the window it's text you typed. In a later addon it could
  come from a network or a device. The prompt treats it as data, like what a function
  returns.
- **An event never creates a rule.** Only a `hallux` command typed at the prompt does.

---

## 9. What has to change

| File | Change |
|---|---|
| `hallux/addons.py` | The check for `connect`, `emit`, the filter for who listens, the queue and its limits |
| `hallux/tools.py` | `addon_listen` |
| `hallux/machine.py` | Wait for the keyboard or an event; send the event; who listens, per boot; the budget |
| `hallux/terminal.py` | A way to interrupt the prompt from outside and get back what was typed |
| `hallux/prompt.md` | The `<event>` message and its rules |
| `hallux/config.py` | `event_budget_usd` |
| `hallux/statusbar.py` | An event on the bar; the "paused" note |
| `addons/window.py` | The button, and the line the child sends by itself |
| `tests/` | All of it with a fake model and a fake addon, as now |

In size it's about steps 5 and 6 of the addon plan together.

---

## Before building

1. **Finish the live checks of what exists:** that `reboot` and `poweroff` close the window,
   that Ctrl+Shift+Del does, and that `hallux.log` shows `addon_help` before the first call.
   Events build on the hooks and on the per-boot state.
2. **Write the step-by-step plan,** as `docs/plans/addon-events-plan.md`, like the addon
   plan.

Not needed first: the disk handle (step 7 of the addon plan) and the documentation (step 8).

---

## Decisions

The questions that were open, settled on 2026-10-01:

| Question | Decision | Why |
|---|---|---|
| How does the addon get `emit`? | `connect(emit)`, called once at load | The addon's reader thread needs `emit` at any time, so it can't be an argument of a function the AI calls |
| What does the budget count? | The cost of events since the last command you typed | The risk is spending while nobody watches, and this limits exactly that. A budget per boot would run out in a long session and never come back |
| One message per event, or all waiting events in one? | All in one | Three quick presses cost one model call |
| Events in full-screen programs? | Not at first. They wait until the program ends | The shell prompt is the case that matters, and the simpler one |
| Does the list in `<boot>` say which addons have events? | No | The manual says it, and the manual is read before the first use anyway |
| Does Enter in the window's text box send the event too? | Yes | It's what a text box does |

## Order of work

1. `connect` and `emit` in the loader, with events dropped while nobody listens.
2. `addon_listen`, and who listens, per boot.
3. The terminal can be interrupted from outside; the machine waits for the keyboard or an
   event at the shell prompt.
4. The `<event>` message and the prompt rules.
5. The budget, the limits and the status bar.
6. The button in the window addon.
7. A live run: `window watch`, a press, a reboot.
