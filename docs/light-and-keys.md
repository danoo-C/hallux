# Status bar, hard exit and keys

**Status:** proposal, no code yet. Every question comes with my recommendation, so you can
answer "OK" or overrule it. The ones that shape the design most are **Q1, Q2, Q7 and Q9**.

## In short

1. **A status bar: one row at the bottom that belongs to hallux, not the AI.** It shows an
   activity light (gray when idle, a green↔yellow spinner while the AI works) and what's
   happening (`thinking…`, `reading /etc/os-release`, `saving hello.txt`). On the right: the
   model, the effort and what the session has cost so far. The AI is never told the row exists
   and can't draw on it. It replaces my earlier "top-right corner light" idea, and it's a better
   design.
2. **A hard exit that always works:** Ctrl+Shift+Del, with triple Ctrl-C as a fallback. It pulls
   the plug: the model stops, your terminal is restored, and hallux quits.
3. **Keys to the AI:** one clear rule. Line editing stays local. Every other Ctrl/Alt/F-key goes
   to the machine as a key event. The hard exit is reserved for hallux.
4. **Underneath all three:** hallux has to read the keyboard at all times, including while the
   AI is thinking.

---

## 0. What happened with Ctrl-C in nano

From `test-hallux/.hallux/hallux.log`:

```text
23:33:45  nano anytext.txt   → nano opens                      4.4 s
23:33:57  C-c                → "[ line 3/3 (100%), col 1/1 … ]"  5.2 s
23:34:05  C-c                → "[ line 6/7 (85%), col 1/1 … ]"   7.3 s
 …        C-c ×4 more        → the same status line again       4–6 s each
23:37:07  C-x                → "Save modified buffer?"           3.6 s
23:37:14  Enter              → back at the shell                 2.5 s
```

It wasn't a bug in hallux. **In real nano, Ctrl-C doesn't quit: it shows the cursor
position**, and the AI did exactly that, six times. What was really missing:

- **A way out** that always works, whatever the AI is simulating. That's the hard exit (section 2).
- **Feedback.** Each press took 4–7 s with nothing on screen to show that anything was
  happening. That's the status bar (section 1).

(The screen was probably also hard to read at the time, because I was changing the code while
you tested.)

---

## 1. The status bar

### How it looks

```text
┌──(user㉿hallux)-[~]
└─$ nano hello.txt
                                          ⋮  (the machine's screen: rows 1 … rows-1)
 ⠹ reading /home/user/hello.txt                         opus 5.5 · low · $0.21 · 4.4s
```

The bar is one row, always at the bottom, and always visible:

| Part | Idle | Busy |
|---|---|---|
| **Light** | `•` gray | braille spinner `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`, 80 ms per frame, fading green `#5fd787` ↔ yellow `#d7d75f` |
| **Activity** | a dim hint: `ctrl+shift+del: power off` | what the AI is doing right now (see the table below) |
| **Right side** | model · effort · session cost · last response time | model · effort · session cost · a running timer |

What the activity text says. hallux knows all of this from the SDK's message stream, because
each tool call arrives as it happens:

| Moment | Text |
|---|---|
| Boot | `booting…` |
| Waiting for the model's first move | `thinking…` |
| `read_file` / `list_dir` / `find` / `stat` | `reading /etc/os-release`, `listing /home/user`, `searching /usr` |
| `write_file` / `edit_file` / `make_dir` / `remove` / `move` / `copy` | `writing notes.txt`, `editing ~/.bashrc`, `removing /tmp/x` … |
| `memory_read` / `memory_edit` | `remembering…` |
| `save_field` | `saving hello.txt` |
| After Ctrl-C | `interrupted` (briefly) |
| The model failed | **red:** `model failed: overloaded (HTTP 529)`. This replaces today's line on stderr, which scribbles over the screen. |

### Why it's allowed to exist

Principle 1 says every character on screen comes from the AI. The bar is the one exception, and
it's honest about it. It isn't part of the machine's screen at all. It's the **front panel of the
case**, like the small LCD and LEDs on a server. The machine can't write to it, and the bar never
pretends to be the machine. It's configurable like any other hardware, in
`.hallux/config.toml`: `status_bar = true`.

### How it stays out of the AI's reach

Nothing is changed in the AI's world except its screen size:

1. **The AI is told the screen is one row shorter** (`rows - 1`). Its screens, `clear`s and
   full-screen layouts all fit above the bar.
2. **In the scrolling shell, a scroll region** (`ESC[1;{rows-1}r`) makes rows 1…rows-1 scroll
   while the last row stays put. The region starts at row 1, so scrolled lines still go into
   your scrollback in xterm-style terminals. *This must be verified on your terminal (Q1).*
3. **hallux redraws the bar after every piece of AI output.** Even if the AI managed to draw
   there (with an absolute cursor move, or `clear`, which erases the whole screen), the damage
   lasts milliseconds.
4. **The AI's output is filtered** for the few codes that would break the layout: scroll
   regions, full reset (`ESC c`) and origin mode. The bar's layout is hallux's business.
5. **prompt_toolkit is told the screen is one row shorter too,** so its prompt rendering never
   reaches the bar.
6. **In block mode it's trivial.** The full-screen layout becomes "the AI's screen on top, the
   bar below" (an `HSplit` in prompt_toolkit), and prompt_toolkit draws both.
7. **When the window is resized,** hallux moves the region and the bar. **On exit,** normal or
   hard, it removes the region and clears the bar, so your real shell is left clean.

Risks, and what happens if they bite:

- **Scrollback:** some terminals drop scrolled lines when a scroll region is set. If yours does,
  the fallbacks are: show the bar only while the AI is busy, or put the status in the tab title.
- **Style changes:** a program that changes the terminal's own settings could briefly disturb
  the bar, but the redraw after every piece of output fixes it.

### Alternatives I considered

| Option | Why not (as the main design) |
|---|---|
| A top-right corner light (my first proposal) | Covers the AI's text and leaves dots in scrollback, and there's no room for messages |
| The tab/title bar only | No colors and no room, and it's easy to miss. Still a good fallback. |
| hallux as a full-screen app with its own terminal emulator (like tmux) | You'd lose your terminal's native scrollback, selection and copy. It's a big project. |

### Questions

- **Q1. Which terminal app do you use?** My recommendation: I'll assume Windows Terminal with
  WSL, based on your screenshots, and verify it with a small test script first. The script
  checks three things: whether scrollback survives a scroll region, 24-bit colors and braille
  glyphs, and what Ctrl+Shift+Del sends.
- **Q2. What should the bar show?** My recommendation: exactly the layout above.
  - left: the light and the activity;
  - right: model · effort · session cost · response time;
  - when idle, a dim hint about the hard exit, since nobody should get stuck again.
- **Q3. How should it look?** My recommendation: quiet by default, so the machine's colors stay
  the star.
  - no background, or a very dark one (`#1c1c1c`), with gray text;
  - color only for the spinner and for errors, which are red.
- **Q4. How detailed should the activity be?** My recommendation: one short line per tool call,
  with paths shortened to fit (`reading …/share/doc/copyright`). Plus a small counter when the
  AI makes several calls in one turn (`writing /etc/hosts (4)`).
- **Q5. Should the AI be able to post its own messages to the bar** (for example
  `status("compiling…")`)? My recommendation: **no.** The bar is trustworthy precisely because
  the machine can't touch it. The machine already has its own screen for that.
- **Q6. Should it be optional?** My recommendation: yes, `status_bar = false` in
  `.hallux/config.toml` for anyone who wants a completely pure screen. It's on by default.

---

## 2. The hard exit

### What it does: "pull the plug"

- **Immediately:** stop the model by killing the Claude Code process it runs in, leave block
  mode, remove the scroll region and restore your terminal (normal line mode, cursor visible,
  colors reset). Then quit.
- **Nothing graceful:** no shutdown messages from the AI, and `~/.bash_history` isn't written,
  just like a real power cut.
- **Nothing important is lost.** Memory and files are written the moment they change, so a hard
  exit loses only what a real reboot loses: the current directory, variables typed at the
  prompt, and running programs.

### Which key

A terminal program only ever sees the bytes your terminal app sends for a key:

- **Ctrl+Shift+Del:** xterm-style terminals send `ESC[3;6~`, and prompt_toolkit recognizes it
  (`c-s-delete`). I believe Windows Terminal doesn't use it itself, but that needs checking (Q1).
  On many laptops, Del is Fn+Backspace.
- **Ctrl-C three times within a second:** works in every terminal, and it's what people do
  anyway when stuck. Each press still reaches the machine as usual; the third one quits.

### Questions

- **Q7. Which keys?** My recommendation: Ctrl+Shift+Del plus triple Ctrl-C, with the idle status
  bar showing the hint. (Ctrl-\\, the Unix "quit hard", is a possible third.)
- **Q8. Should there also be a graceful power button?** A short press asks the AI to shut down
  properly, and a second press pulls the plug, like a real PC's power button. My
  recommendation: later. The hard exit fixes the real problem, and the graceful version is just
  a nicety.

---

## 3. Passing keys to the AI

### What happens today

| Key | Now |
|---|---|
| Ctrl-C at the prompt | Sends `<signal>SIGINT</signal>`, and the AI shows a new prompt |
| Ctrl-C while the AI works | Interrupts the model's turn, then sends `<signal>SIGINT</signal>` |
| Ctrl-D on an empty line | Sends `<eof>` |
| Ctrl-L | Sends `<key name="C-l">typed line</key>`; the AI clears, and your line comes back |
| In block mode | The form's action keys, and Ctrl-C always. That's how nano got your ^C. |
| Everything else | Handled locally by prompt_toolkit (emacs-style editing), or ignored |

So yes, the AI already sees Ctrl-C. At the prompt it arrives as a signal, and in nano as a key.

### Proposal: one clear key rule

| Who owns the key | Keys | Why |
|---|---|---|
| **The keyboard side** (local and instant) | Printable characters, Backspace, Delete, ←/→, Home/End, ↑/↓ recall of lines you typed, Ctrl-A/E/K/U/W | Editing a line is the terminal's job, just like the kernel's line editing on real Linux |
| **The machine** (sent to the AI) | Ctrl-C, Ctrl-D, Ctrl-L, Ctrl-Z, Ctrl-R, Tab, Alt+anything, F-keys, and anything else your terminal reports | The AI decides what they mean, the way bash (or nano) would |
| **hallux** (never reaches the AI) | The hard exit | A way out that always works |

- Every key for the machine arrives the same way: `<key name="C-r">what you had typed</key>`.
  That replaces today's special `<signal>` and `<eof>` messages. Names use `C-`, `M-` (Alt) and
  `S-` (Shift), for example `C-S-Left`.
- **Every such key is a model round trip,** which takes seconds. The status bar shows it
  (`thinking…`), so it no longer feels frozen.
- **What terminals can report is limited:**
  - Ctrl+Shift+letter usually looks exactly like Ctrl+letter.
  - Ctrl+1…9 often sends nothing at all.
  - Ctrl+Shift+C/V are copy and paste in Windows Terminal.

  Terminals that support the *kitty keyboard protocol* report every combination, and hallux can
  switch it on where it's available.

### Questions

- **Q9. What should Ctrl-C mean at the prompt?** My recommendation: **keep the Unix meaning**,
  which is to interrupt whatever runs inside the machine. The nano episode shows that the AI
  being faithful is the fun part. The way out shouldn't be Ctrl-C bending reality. It should be
  the hard exit, which is outside reality.
- **Q10. Tab completion by the AI?** My recommendation: after the key rule is in, because each
  Tab costs a few seconds. The status bar will say `completing…`.

---

## 4. hallux must read the keyboard at all times

**Today:**
1. The prompt reads your line.
2. While the AI thinks, your terminal is back in normal line mode. Keys you press are echoed
   into the spot where the AI's output will appear, and Ctrl-C arrives only as a signal.
3. The next prompt starts.

**Proposal:** while the AI thinks, hallux keeps the terminal in raw mode and reads every key
itself.
- **Normal keys** are kept as type-ahead for the next prompt or screen, and aren't echoed into
  the output. Block mode already does this.
- **Ctrl-C** stops the AI's turn.
- **The hard exit** pulls the plug.
- **The status bar's spinner** animates from the same loop.

One input loop serves all three features.

---

## 5. Side notes from the logs

- **Boots are slow:** 23–27 s and 11 tool calls. The AI writes `/etc/hostname` before `/etc`
  exists, gets `ENOENT`, creates the folder, and writes the files again. It could start from a
  small ready-made skeleton (`/etc`, `/home/user`, `/tmp`), or be told to create parent folders
  first. That's roadmap step 3.
- **Each nano action costs 4–7 s and about $0.015–0.02,** mostly because the AI redraws the whole
  120×30 screen every time. Partial redraws, meaning only the lines that change such as the
  status line, would help later.
- **The log's `$` column is misleading:** it shows the session's running total (that's what the
  SDK reports), not the cost of that turn. I'll log the per-turn difference instead. The status
  bar shows the running total, which is the useful number there.

---

## Suggested order

1. **A terminal check script.** It answers Q1 and Q7 with facts: whether scrollback survives a
   scroll region, 24-bit colors and braille, and what Ctrl+Shift+Del sends.
2. **Reading the keyboard at all times** (section 4).
3. **The hard exit.**
4. **The status bar:** block mode first (easy), then the scroll region in the shell.
5. **The key rule:** one `<key>` message for everything that goes to the machine.
