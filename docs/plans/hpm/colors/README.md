# hpm: colors on the command line

[The hpm plan](../README.md) · a plan for making hpm's terminal output colorful, so that
what worked, what needs a look and what failed stand out at a glance.

**Status:** planned 2026-10-25 at the user's request ("can we make the hpm cli colorfull and
make successes/warinings/errors more visible? can you please write a plan for the colors").
Decisions confirmed by the user 2026-10-25 ("go as proposed").

| Step | What | Status |
|---|---|---|
| [01](01-paint.md) | `hallux/hpm/paint.py`: the colors, and when they are on | **Built** 2026-10-25 |
| [02](02-every-line-its-kind.md) | Every line hpm says gets its kind: success, warning, note, error, loud, AI, question | **Built** 2026-10-25 |
| [03](03-lists-and-the-look.md) | `list`, `show`, `search` and `store list` get their highlights; docs; the look checked on a real terminal | Planned |

## What hpm prints today

All plain text, through two places:

- `Questions.say` in `hallux/hpm/publish.py` (`print(text)`): every line of every command,
  57 call sites in `cli.py`, `publish.py`, `assist.py`, `remote.py`. The questions
  (`ask`, `confirm`, `choose`) go through `input()` in the same class.
- `main` in `hallux/hpm/cli.py`: the error, `hpm: …`, and `hpm: stopped`, on stderr.

The words already carry their kind, mostly at the start of the line:

| Kind | How a line looks now | Examples |
|---|---|---|
| success | `✓ …`, `published …`, the summary `1 updated · 2 installed` | `  ✓ kittystory 1.1 updated (was 1.0), 4 files` · `published kittystory 1.1: 10 files, 48.2 KB` · `✓ pushed kittystory 1.1 to danika` |
| failure of one package | `✗ …` | `✗ kittystory-chars: it carries files its manifest doesn't list: …` |
| skipped | `– …` | `  – kittystory-memories skipped: its migration was cancelled` |
| error (the command stops) | `hpm: …` on stderr | `hpm: kittystory: nothing changed since 1.1; nothing to publish` |
| warning | `warning: …` | `warning: kittystory holds what may be your own memories or chats: …` |
| note | `note: …` | `note: published the clean seed …; the world's own state.json differs` |
| loud (read before you go on) | `!! …` | `!! kittystory-theme: it adds rules, which change the whole machine: …` |
| the AI | `the AI is …`, `… cost ~$…` | `the AI is drafting kittystory's manifest…` · `the AI's part cost ~$0.4462` |
| question | `… [Y/n]:`, `… [1.2]:`, `r, w or s:` | `mark kittystory-memories private, so that hpm push never sends it? [Y/n]:` |
| plain | everything else | listings, `--- path` headers with a manifest under them, "everything is up to date" |

So most of the work is in one place: the line's kind is known from its first characters,
and only a few lines need to be told their kind (decision 2).

## The colors

Sixteen-color ANSI only, as the full-screen pickers in `hallux/hpm/screens.py` already use
(`ansigreen`, `ansired`, `ansibrightblack`): they follow the terminal's own theme, so they
read on a dark and a light background, in Windows Terminal and VS Code's terminal alike
(decision 1).

| Kind | Marker | The rest of the line |
|---|---|---|
| success | `✓` and `published` bold green | green |
| failure of one package | `✗` bold red | red |
| skipped | `–` | dim (bright black) |
| error | `hpm:` bold red | red |
| warning | `warning:` bold yellow | yellow |
| note | `note:` bold cyan | as it is |
| loud | `!!` bold red | bold |
| the AI | | magenta; the cost (`~$0.4462`) bold |
| question | | bold; the default in brackets (`[Y/n]`, `[1.2]`) dim |
| plain | | as it is |

Only the marker and the line's own text are colored. The text never changes: no new
words, no new symbols, so a copied line is the same with and without colors, and every
test that reads what hpm said stays as it is.

A sketch of `hpm update` with colors (the kind in brackets stands for the color):

```
[loud]    !! kittystory-theme: it adds rules, which change the whole machine: Everything is pink.
[ai]      the AI migrates, into a staging folder…
[success]   ✓ kittystory 1.1 updated (was 1.0), 4 files
[failure]   ✗ kittystory-chars 1.1 failed: the disk is full
[skipped]   – kittystory-memories skipped: its migration was cancelled
[plain]   1 updated · 1 failed: kittystory-chars (the disk is full)  [dim](backup: 2026-10-25T…)
```

The summary line is colored by what it says: green if nothing failed, red if something did.

## When colors are on

Only on a terminal, and never when asked not to (decision 3):

- **stdout for `say`, stderr for the error, each on its own.** `hpm list | less` and
  `hpm … 2> errors.txt` get plain text; the screen keeps its colors.
- **`NO_COLOR`** set to anything but empty: off ([no-color.org](https://no-color.org)).
- **`TERM=dumb`:** off.
- **`HPM_COLOR=always`** (for `hpm list | less -R`) or **`HPM_COLOR=never`** override the
  above.

What stays plain whatever the switch says: the world's log (`.hallux/hallux.log`), files
hpm writes (manifests, changelogs), the text handed to `$EDITOR`, the Packages tab (it draws
its own screen; this plan doesn't touch it), and the machine's own output shown by
`publish --test`.

## Decisions of this plan

| # | Decision | Why |
|---|---|---|
| 1 | **Sixteen ANSI colors, not RGB** | They follow the user's terminal theme, like `screens.py`; RGB pink on a light theme can be unreadable |
| 2 | **A line's kind comes from its marker (`✓`, `✗`, `–`, `!!`, `warning:`, `note:`, `the AI `); the few lines without one say their kind: `say(text, kind="ok")`** | The words already follow these markers, so 57 call sites mostly stay; an explicit kind where there is none keeps the guess out of the rest |
| 3 | **On only when the stream is a terminal; `NO_COLOR`, `TERM=dumb` and `HPM_COLOR` decide the rest. No `--color` flag** | The usual rules of command-line tools; one environment variable is enough for the rare `less -R` |
| 4 | **The text never changes, only its color** | Copy-paste and every existing test stay as they are; a line means the same in a pipe |
| 5 | **The AI's lines in magenta, its cost bold** | Each AI part costs money; the user should see when one starts and what it cost |
| 6 | **The Packages tab is left as it is** | It draws its own screen with prompt_toolkit; a second plan if it should match |
