# Addon agents and job control: what to try by hand

[The plan](README.md) · [step 17](17-live-run.md), whose live run this is

**What this is:** every point that only a person at a real terminal, with a real model, can
show. The tests can't: they use a pretend model and a terminal emulator. The list holds
what is left of the live runs of steps 13, 15 and 17, and what steps 11, 12, 14 and 16
couldn't check.

**How to use it:**

- **It works as described:** tick the box, `[x]`. Nothing else is needed.
- **It doesn't, or you aren't sure:** leave the box empty and write what you saw on the
  line "If not" under it. A few words are enough.
- **A few points ask for a number.** They have a line for it, and say where to read it.
- **An empty box with an empty line** means "not tried yet".

When you are through, or stuck, tell me. I read this file, fix what failed, and write the
results into the steps.

**If something looks wrong:** the point's number and what you saw are all I need. A
screenshot helps, and so does the world's log, `.hallux/hallux.log`.

---

## Before you start

- **Start Hallux on a test world that has the music addon,** as usual:

  ```bash
  python hallux.py ./test-hallux/
  ```

- **The panel's keys:** Ctrl+F12 opens and closes it. `a`, `d` and `c` choose a tab, ↑ ↓
  move, Enter opens a row or presses a button, Esc goes back or closes.
- **The world needs a program that starts a composition.** If it has none:

  ```text
  hallux install a program called compose: "compose WHAT" has the music addon's composer
  write that song into ~/Music, in the background, and prints the job's pid. If WHAT names
  a score that exists, it passes that file in edit, so the composer changes it.
  ```

- **For part D it needs a player that can compose.** If yours can't yet, for kittymusic:

  ```text
  hallux kittymusic gets a key c: it asks for a song in one line, has the composer write
  it, shows "composing…" with the job's status line while it waits, and plays the song as
  soon as it arrives
  ```

**What it costs.** Part A and part I cost what short commands cost. Everything else starts
compositions, and a composition is a second session with its own cost: the first one was
$0.78 on Opus at high effort, and a job is killed at $2.00.

| Parts | Compositions | How to spend less |
|---|---|---|
| B, C, D, E | Four that run to their end | Run B on your usual model: it looks at how the composer works. For C, D and E a cheaper model does: set **Agent model** in the panel's Config tab |
| F, G, H | Six that are ended after seconds | Set **Agent model** to `claude-haiku-4-5` |

A change in the panel lasts until Hallux quits, unless you press Save.

---

## A. Job control, without a composition

### A1. Ctrl-Z puts nano aside

1. `nano notes.txt`, type two lines, and don't save.
2. Press Ctrl-Z.

**Should happen:** within a few seconds the shell's screen is back, as it was before nano.
Under it stands a line like `[1]+  Stopped                 nano notes.txt`, then the
prompt. Hallux's bar is on the last row, and only there.

- [x] Works
- If not:

### A2. The shell works meanwhile

1. `ls`
2. `jobs`

**Should happen:** `ls` answers as always. `jobs` lists nano as `Stopped`.

- [x] Works
- If not:

### A3. `fg` brings it back as it was

1. `fg`
2. Type a few more words, save with Ctrl-O and Enter, leave with Ctrl-X.
3. `cat notes.txt`

**Should happen:** nano is back within the time of one short answer, all at once and not
line by line. Your two lines are there, and the cursor is where you left it. The file has
what you typed before and after the Ctrl-Z.

- [x] Works
- If not:

### A4. vim comes back in the mode it was in

1. `vim notes.txt`, press Esc so that it is in normal mode, then Ctrl-Z.
2. `fg`, then press `x`.
3. Leave with `:q!`.

**Should happen:** the `x` deletes the character under the cursor. It isn't typed into the
text.

- [x] Works
- If not:

### A5. A program that updates by itself

1. `top`, and wait until it has updated once.
2. Ctrl-Z, then `echo hi`, then `fg`.
3. Watch for ten seconds, then `q`.

**Should happen:** `top` is back at once, and its clock and numbers are brought up to date
within a few seconds of the `fg`, without a key. It goes on updating.

- [x] Works
- If not:

### A6. Two programs

1. `nano a.txt`, type a word, Ctrl-Z.
2. `less /etc/os-release`, Ctrl-Z.
3. `jobs`
4. `fg %1`, leave nano with Ctrl-X and `n`.
5. `fg`, leave less with `q`.

**Should happen:** `jobs` lists both, as `[1]` and `[2]`. `fg %1` brings nano with its
word, and the last `fg` brings less.

- [ ] Works
- If not:

### A7. Killing a suspended program

1. `nano b.txt`, type a word, Ctrl-Z.
2. `kill %1`
3. `jobs`, then `fg`.

**Should happen:** the shell says that the job was terminated. After that `jobs` doesn't
list it, and `fg` says that there is no such job. No editor appears.

- [x] Works
- If not:

### A8. The window changes its size in between

1. `nano notes.txt`, Ctrl-Z.
2. Make the terminal window clearly narrower and lower.
3. `fg`

**Should happen:** nano fits the new window. Its help lines are at the bottom, above the
bar, and the text is all there.

- [x] Works
- If not:

### A9. A reboot drops what was suspended

1. `nano c.txt`, Ctrl-Z.
2. `reboot`
3. After the boot: `jobs`, then `fg`.

**Should happen:** `jobs` lists nothing, and `fg` says that there is no such job.

- [x] Works
- If not:

---

## B. One composition, watched from the shell

Start it, and do B2 to B11 while it runs. It takes some minutes. What you don't get to
can be looked at during part C's composition.

### B1. `compose` returns at once

1. `compose a slow blues in twelve bars with a walking bass`

**Should happen:** within about fifteen seconds the shell prints the job's pid, a number
from 30001 up, and the prompt is back.

- [ ] Works
- If not:

### B2. The bar shows the job

**Should happen:** the left side of the bar reads like
`music: sketching the drums · 0:48 · 21k tok`. The time counts up every second.

- [x] Works
- If not:

### B3. Typing while the bar counts

1. Type a long line slowly, and don't press Enter. Move in it with ← and →.
2. Drop it with Ctrl-C.

**Should happen:** every character lands where the cursor is. Nothing jumps or flickers in
a way that disturbs.

- [x] Works
- If not:

### B4. The shell stays quick

1. `echo hi`
2. `ls ~/Music`

**Should happen:** each answers in a few seconds, as without a job. The new song isn't in
the folder yet.

- [x] Works
- If not:

### B5. `ps` and `htop` know the real job

1. `ps aux`
2. `htop`, look at its list, and leave with `q`.

**Should happen:** among the processes is one with the job's pid, the one `compose`
printed, in both. No other process has a pid from 30001 up.

- [x] Works
- If not:

### B6. The panel opens on the jobs

1. Press Ctrl+F12.

**Should happen:** the panel opens on the Agents tab. One row has the job's pid, `music`,
`composer`, `running` or `waiting`, a time that counts, tokens that grow, and its status
line.

- [x] Works
- If not:

### B7. The composer says what it does before it thinks

1. Press Enter on the job's row.

**Should happen:** the Details tab shows the job's lines, each with its time. The first
line is a `status`, within the first seconds: `0:05`, not `2:54`.

- [x] Works
- If not, and the time of the first `status` line:

### B8. The composer makes a round's changes together

Keep the Details tab open until a `check` has reported problems.

**Should happen:** the `edit_file` lines that follow that check all have the same time, or
there is one `write_file` of the whole score. They don't come one by one, seconds apart.
If the first `check` was clean, there is nothing to see: tick the box.

- [x] Works
- If not:

### B9. The mouse in the tabs

1. In Details, turn the wheel up and down.
2. Esc, then click on a row of the Agents tab, then on the tab titles at the top.

**Should happen:** the wheel scrolls the lines, a click picks the row, and a click on a
title shows that tab.

- [x] Works
- If not:

### B10. The screen after the panel

1. Close the panel with Esc.

**Should happen:** the shell's screen is as it was before the panel, with the prompt.

- [x] Works
- If not:

### B11. The memory of the computer

In a second terminal, on your computer and not in Hallux, while the job runs:

```bash
ps -eo rss,args | grep '[c]laude_agent_sdk'
```

**Should happen:** two lines, one for the machine's session and one for the job's. The
first column is each one's memory in kilobytes.

- [ ] Done
- The two numbers:

### B12. The job's end comes by itself

Press nothing when the bar's time is near four or five minutes.

**Should happen:** when the job ends, the shell prints by itself a `Done` line and what
the job wrote, with the right pid and the file's name. What you had typed so far is back
at the prompt.

- [x] Works
- If not:

### B13. The refill button

Right after B12, **before you type a line:**

1. Ctrl+F12, `c` for Config. Open "Budget, all jobs" and enter `2`.
2. `a` for Agents, and look at the row of the idle composer.
3. `c`, go to **Refill budgets**, Enter.
4. `a`, and look at the row again.
5. `c`, set "Budget, all jobs" back to `4`. Close the panel.

**Should happen:** in 1 the row says `spent since you typed:` with what the job cost. In 2
the composer's row says `can't start: jobs budget used`. In 3 the panel says
`budgets refilled`. In 4 the row says `ready · effort high`.

- [x] Works
- If not:

### B14. The song, and what it cost

1. `ls ~/Music`, then play the new score.
2. Ctrl+F12, and read the ended job's row in the Agents tab.

**Should happen:** the score is in the folder now, and it plays. The row says `done`, with
its time and its cost, and the cost is under $2.00.

- [x] Works
- The time and the cost:
- If not:

---

## C. A composition while you write in nano

### C1. Two things at once

1. `compose a short lullaby for a music box`
2. At once: `nano draft.txt`, and type a few lines. Don't save.

**Should happen:** nano opens and takes your typing as always, while the bar under it
shows the job.

- [x] Works
- If not:

### C2. The job ends, and nano is left alone

Stay in nano, with unsaved text, until the bar shows no job any more.

**Should happen:** nothing on nano's screen changes when the job ends. Your text is as you
typed it.

- [x] Works
- If not:

### C3. The news comes when nano is left

1. Leave nano with Ctrl-X and `n`.

**Should happen:** back at the shell, the `Done` line and the file's name are printed, with
the answer to leaving nano or right after it.

- [x] Works
- If not:

---

## D. A player that composes

### D1. The player starts a composition

1. Start your player, and start a composition in it.

**Should happen:** the player says that it is composing, and stays on screen. The bar
shows the job.

- [x] Works
- If not:

### D2. Ctrl-Z, with a job running

1. Ctrl-Z.
2. `jobs`, then `ps aux`.

**Should happen:** the shell is back with a `Stopped` line for the player. `jobs` lists the
player as stopped, and `ps aux` has the composer with its real pid.

- [x] Works
- If not:

### D3. `fg` brings the player back

1. `fg`

**Should happen:** the player is back as it was, still composing.

- [x] Works
- If not:

### D4. The song arrives without a key

Sit in the player, and press nothing.

**Should happen:** when the job ends, the player changes by itself: it shows the new song
and starts to play it. It stays on screen: the answer is the player's, not a `Done` line
at the shell.

- [x] Works
- If not:

---

## E. Changing a song that somebody else changes too

Pick a score that exists, such as the one from part B. Below it is `SONG.score`.

### E1. The composer is given the file

1. `compose make the bass louder in ~/Music/SONG.score`
2. Ctrl+F12, Enter on the job's row, and read the second line of the Details tab. Close
   the panel.

**Should happen:** the line says `may change: SONG.score`.

- [x] Works
- If not:

### E2. Your own change is kept

1. While the job runs: `nano ~/Music/SONG.score`, change the number behind `BPM =` by one,
   save with Ctrl-O and Enter, leave with Ctrl-X.
2. Wait for the job's end, then `ls ~/Music` and `grep BPM ~/Music/SONG.score`.

**Should happen:** `SONG.score` has your tempo. The composer's version is beside it, as
`SONG.score.new`, and the shell said so when the job ended.

- [x] Works
- If not:

---

## F. Ending a job

### F1. A second composition while one runs

1. `compose a march`, and right after it `compose a waltz`.

**Should happen:** the second one is refused. The program prints an error, such as
`Resource temporarily unavailable`, and `ps aux` shows one composer.

- [x] Works
- If not, and what the program printed:

### F2. `kill` from the shell

1. `kill` with the pid of the job that runs.
2. `ls ~/Music`

**Should happen:** the job ends within seconds, and the shell prints what it prints for a
killed job. The folder is as it was: no march, and no half-written file.

- [x] Works
- If not:

### F3. `k` in the panel

1. `compose a polka`
2. Ctrl+F12, then `k`. The foot asks `kill 30005? y/n`, with the job's pid. Press `y`.
3. Close the panel, and `ls ~/Music`.

**Should happen:** the row says `killed`. When the panel is closed, or with your next
line, the shell prints what it prints for a killed job. The folder is as it was.

- [x] Works
- If not:

---

## G. A job and the end of a boot

`.hallux/jobs` is in the world's folder on your computer, such as
`test-hallux/.hallux/jobs`. Look at it from a second terminal.

### G1. A reboot

1. `compose a tango`, and when the bar shows the job: `reboot`.
2. After the boot: `ls ~/Music` and `ps aux`. Outside: `ls test-hallux/.hallux/jobs`.

**Should happen:** the reboot doesn't wait for the song. Afterwards the folder has no
tango, `ps aux` has no pid from 30001 up, and `.hallux/jobs` is empty or not there.

- [x] Works
- If not:

### G2. A power-off

1. `compose a tango`, and when the bar shows the job: `poweroff`.
2. Outside: `ls test-hallux/.hallux/jobs`.

**Should happen:** Hallux quits within a few seconds. `.hallux/jobs` is empty or not
there.

- [x] Works
- If not:

### G3. The hard exit

1. Start Hallux, `compose a tango`.
2. Ctrl+F12, Enter on the job, and wait for the first `write_file` line. Then press
   Ctrl+Shift+Del.
3. Outside: `ls test-hallux/.hallux/jobs`. Then start Hallux again, and outside:
   `grep "left over" test-hallux/.hallux/hallux.log`

**Should happen:** Hallux quits at once. In 3 the folder first has one entry, the job's
pid. After the new start the log has
`job 30001: its copies were left over, and are deleted`, with that pid, and the folder is
empty. `~/Music` has no tango.

- [x] Works
- If not:

---

## H. A job that uses up its budget

### H1. The cap kills it, and nothing lands

1. Ctrl+F12, `c`. Set "Budget per job" to `0.05`, then "Budget, all jobs" to `0.05`. Close
   the panel.
2. `compose a fanfare`, and wait.
3. When the shell says that the job has ended: Ctrl+F12, and read its row. `ls ~/Music`.
4. Set "Budget, all jobs" back to `4`, and then "Budget per job" back to `2`.

**Should happen:** the job is ended after one of its first answers. Its row says `killed`
and `budget`, with a cost above $0.05: a job can pass its cap by one answer of the model.
The folder has no fanfare.

- [ ] Works
- The cost in the row:
- If not:

---

## I. A machine without an agent

### I1. The tabs say why they are empty

1. Start Hallux on a world whose `config.toml` has `addons = []`.
2. Ctrl+F12, then press `a`.
3. Close the panel. `nano x.txt`, Ctrl-Z, `jobs`, `fg`, Ctrl-X.

**Should happen:** the panel opens on Config, and the titles Agents and Details are grey.
After `a` the foot says `no attached addon has an agent` for a few seconds. Config has no
rows for agents. Job control works as in part A.

- [x] Works
- If not:
