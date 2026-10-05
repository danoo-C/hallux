# Point 4: a card's numbers against what the user asked for

[The plan](README.md) · the report's point 4

**Needs:** nothing. **Changes:** `hallux/prompt.md`, `tests/test_machine.py`,
`docs/concept.md`.

> Rules vs requests: the kittymusic card says 20-60 s songs and the user asked for 3
> minutes. I went with the user, which I think is right, but it isn't written anywhere.

## What happens today

The prompt says what comes before what in three places, and leaves one out:

| | What the prompt says |
|---|---|
| REPLY FORMAT and THE DISK IS REAL | Nothing overrides them |
| Rules, made with `hallux` | They override everything else in the prompt |
| An addon's manual | It ranks like a rule |
| A program card | It "describes how the program behaves" |
| **What the user asks for on the command line** | **Nothing** |

- **The machine went with the user,** and gave a song of three minutes from a program whose
  card says 20 to 60 seconds. It was a guess. Another boot may refuse, or cut the song to
  60 seconds without a word.
- **The addon's own limit is another matter,** and is settled already. The music addon
  plays at most 300 seconds. A longer song fails in `play`, and the prompt says to print an
  addon's error the way the program would.

## Build

**One rule in the prompt,** under PROGRAMS, after the sentence about program cards:

```text
- A card says what its program does when it isn't asked otherwise: its numbers and habits
  are defaults. What the user asks for on the command line comes before them, as an
  option does on a real program. The card stays as it is: one request changes nothing for
  the next run. A rule still comes before a request.
```

So the order, from the strongest:

1. REPLY FORMAT and THE DISK IS REAL.
2. The rules, and an addon's manual.
3. What the user asks for on the command line.
4. What the card says the program does by default.

- **A limit that must hold is made a rule:** `hallux kittymusic never plays more than a
  minute`. Rules come before a request, so the program then refuses, as a real one refuses
  a bad option. A card needs no second kind of sentence for it.
- **One request doesn't change the card.** The next run without the request is a song of 20
  to 60 seconds again. `hallux` is what changes a card.

**`docs/concept.md`:** the copy of PROGRAMS under "The system prompt" gets the rule, and
the section on program cards one sentence: a card's numbers are defaults.

## What doesn't change

- **What rules do.** They stay above everything but the two fixed sections.
- **Addon limits.** They are real, and their error is printed.
- **kittymusic's card.** Its "20-60 s" stays, and now has a meaning: what a song is when
  nobody says how long.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| A card against the command line | The command line comes first | It is how a real program treats its options, and it is what the machine did |
| Limits inside a card | None. A card holds defaults only | Two kinds of sentence in a card would need the AI to tell them apart. A rule does the job already |
| A request against a rule | The rule comes first | It is what the prompt says today, and `hallux` is the one way to change the machine |
| Whether a request changes the card | It doesn't | A wish for one song isn't a wish for every song |

## Tests

In `tests/test_machine.py`:

- the prompt has the rule, under PROGRAMS, after the sentence about program cards.

No test can show what the AI does with it.

## Done when

The test passes, and the user has tried it in the test world:

1. Ask kittymusic for a song of three minutes.
2. `cat /usr/local/bin/kittymusic`
3. `hallux kittymusic never plays more than a minute`, then ask for three minutes again.
4. Take that rule away again with `hallux`, if it shouldn't stay.

**Should happen:** in 1 the song is three minutes long. In 2 the card still says 20-60 s.
In 3 the program refuses, or says that a minute is its limit, and names the rule's reason.

**What it costs:** composing two songs. A cheaper try is any card with a number in it and
a command that asks for another.
