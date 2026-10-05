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

## What the live run taught

Not run yet.
