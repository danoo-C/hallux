# Point 4: a card's numbers against what the user asked for

[The plan](README.md) · the report's point 4

**Needs:** nothing. **Changes:** `hallux/prompt.md`, `tests/test_machine.py`,
`docs/concept.md`.

> Rules vs requests: the kittymusic card says 20-60 s songs and the user asked for 3
> minutes. I went with the user, which I think is right, but it isn't written anywhere.

## What happens today

The prompt says what comes before what in three places, and leaves two out:

| | What the prompt says |
|---|---|
| REPLY FORMAT and THE DISK IS REAL | Nothing overrides them |
| Rules, made with `hallux` | They override everything else in the prompt |
| An addon's manual | It ranks like a rule |
| A program card | It "describes how the program behaves" |
| **What the user asks a program for, against its card** | **Nothing** |
| **What the user asks a program for, against a rule** | **Nothing** |

- **The request was typed into the program,** not on the command line. kittymusic has a
  line of its own, and on 2026-10-02 the user wrote there: `make me a 3 minute long song, i
  want an airy vibe with angelic sounding pads`.
- **The machine went with the user,** and composed three minutes from a card that says 20
  to 60 seconds. It was a guess. Another boot may refuse, or cut the song to 60 seconds
  without a word.
- **Where a `hallux` command about a program goes isn't said either.** The prompt sends
  "everything else" to the Rules. In the test world every change to kittymusic went into
  its card, and the Rules hold three rules, none about an invented program.
- **The addon's own limit is another matter,** and is settled already. The music addon
  plays at most 300 seconds. A longer song fails in `play`, and the prompt says to print an
  addon's error the way the program would.

## Build

**One rule in the prompt,** under PROGRAMS, after the sentence about program cards:

```text
- A card says what its program does when it isn't asked otherwise: its numbers and habits
  are defaults. What the user asks the program for, in its arguments or typed into it,
  comes before them, as an option does on a real program. The card stays as it is: one
  request changes nothing for the next run. A rule still comes before a request.
```

**One more under THE hallux COMMAND,** after "Only a hallux command typed at the prompt
creates a rule":

```text
- A change to how an invented program behaves goes into its card. A limit that has to hold
  whatever the user asks the program for ("never more than a minute") goes into the Rules.
```

So the order, from the strongest:

1. REPLY FORMAT and THE DISK IS REAL.
2. The rules, and an addon's manual.
3. What the user asks the program for.
4. What the card says the program does by default.

- **"In its arguments or typed into it"** covers both ways a program is asked: `kittymusic
  song.score` at the shell, and a line typed into kittymusic's own prompt.
- **A limit that must hold is made a rule:** `hallux kittymusic never plays more than a
  minute`. Rules come before a request, so the program then refuses, as a real one refuses
  a bad option. A card needs no second kind of sentence for it.
- **The new sentence under THE hallux COMMAND is what makes that work.** Without it the
  machine may write the limit into the card, as it did with every change to kittymusic so
  far. There it would be a default, and the next request would go over it.
- **One request doesn't change the card.** The next run without the request is a song of 20
  to 60 seconds again. `hallux` is what changes a card.

**`docs/concept.md`:**

- "Programs, Python and friends": the part on program cards gets one sentence. A card's
  numbers are defaults, and what the user asks the program for comes before them.
- "The rules for the rules": "Where a change goes" gets the card and the limit, and
  "Priority" gets that a rule comes before what the user asks a program for.
- The prompt under "The system prompt" is the first draft, kept for history. It stays as it
  is.

## What doesn't change

- **What rules do against the prompt.** They stay above everything but the two fixed
  sections.
- **Addon limits.** They are real, and their error is printed.
- **kittymusic's card.** Its "20-60 s" stays, and now has a meaning: what a song is when
  nobody says how long.
- **toggleshell in the test world.** Its card switches two rules off while its flag is set,
  and the memory says so. Nothing here changes that. The new rule is about a request
  against a card, and the order above isn't written into the prompt as a list.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| A card against a request | The request comes first | It is how a real program treats its options, and it is what the machine did |
| What counts as a request | The program's arguments, and what is typed into it | The three minutes were typed into kittymusic's own line. "The command line" would not have covered them |
| Limits inside a card | None. A card holds defaults only | Two kinds of sentence in a card would need the AI to tell them apart. A rule does the job already |
| Where a `hallux` command about a program goes | How it behaves: into its card. A limit that must hold: into the Rules | It is where the machine puts changes already. A limit in the card would be a default |
| A request against a rule | The rule comes first | This is new: the prompt today says only that rules override the prompt. A limit needs a place where it holds, and `hallux` is the one way to change the machine |
| Whether a request changes the card | It doesn't | A wish for one song isn't a wish for every song |

**What "the rule comes first" also means:** with the rule "every error message is a haiku",
a program that is asked for plain errors still answers in haiku. The user changes the rule
to change that.

## Tests

In `tests/test_machine.py`:

- the prompt has the rule, under PROGRAMS, after the sentence about program cards;
- the prompt has the sentence about the card and the limit, under THE hallux COMMAND.

No test can show what the AI does with them.

## Done when

The tests pass, and the user has tried it in the test world:

1. Start kittymusic and type into its line a wish for a song of three minutes.
2. `cat /usr/local/bin/kittymusic`
3. `hallux kittymusic never plays more than a minute`, then `hallux`, then ask for three
   minutes again.
4. Take that rule away again with `hallux`, if it shouldn't stay.

**Should happen:** in 1 the song is three minutes long. In 2 the card still says 20-60 s.
In 3 `hallux` lists the limit among the rules and the card is as before; the program
refuses, or says that a minute is its limit, and names the rule's reason.

**What it costs:** composing two songs. A cheaper try is any card with a number in it and
a command that asks for another.
