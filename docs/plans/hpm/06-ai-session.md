# Step 6: hpm's AI session

[The plan](README.md) · the design: [hpm.md](../../hpm/hpm.md), sections 5, 7 and 11;
[sharing.md](../../hpm/sharing.md), sections 3 and 4; plan decisions 9, 10, 16, 17

**Needs:** step 4 (step 5 for merging from the tab). **Changes:** new `hallux/hpm/ai.py`,
`hallux/hpm/prompts/{init,changelog,merge,review}.md`; `hallux/hpm/cli.py`,
`hallux/hpm/engine.py` (merge), `hallux/panel_tabs/packages.py` (merge);
`pyproject.toml` (the prompts as package data); `tests/test_hpm_ai.py`.

After this step the AI does the parts that need judgement: the manifest's first draft, each
changelog's draft, merging memories, and reviewing a card. The test install runs too.

## Build

**`ai.py`: one session per job,** built like `hallux.agents.Session`: the SDK's client
(`client_factory`, so the tests use a stand-in), `shared_options` (no tools of Claude Code's,
none of your settings, the OS sandbox when the world has it on), the job's prompt, its own
tools (decision 9), and the cap of the store's `config.toml` as `max_budget_usd`. When it ends
it prints the cost, and the log of the world gets a line.

| Job | Reads | May write | Gives back |
|---|---|---|---|
| `init` | the whole world (read-only tools) | `/usr/local/share/hpm/<name>/hpm.toml` only | a manifest; hpm checks it (step 1) and shows its problems to the AI once, then to you |
| `changelog` | the last release (unpacked into a temporary folder it may read) and the world | nothing | the entry's text, put into `$EDITOR` for you |
| `merge` | the two files | nothing | the merged text; hpm writes it, after showing it |
| `review` | the card and the manifest | nothing | a list: what reaches beyond the package's paths, rules, memory, other cards |

**`hpm init NAME`:** asks the AI for a manifest from the card `/usr/local/bin/<name>` and the
memory's line about it, shows it, opens `$EDITOR` on it, checks it again, saves it. It
suggests the extras (packs, characters, memories) and marks a memories package private
(sharing.md section 3), and asks the AI for a clean seed where a seed holds a chat.

**Publish** (step 2) now offers the AI's changelog draft, and, with `--test`, the test
install (decision 17): a copy of `base_world` from the store's `config.toml` into a temporary
folder, `hpm install` into it with every default extra, then `run_script` with the app's name
as the only line, the screen and the cost shown. The copy is removed afterwards.

**Merge** comes into the conflict screens of step 4 and the tab: for `memory.md` and
`shared.md`, `m` shows the merged text before it is written.

**Review** runs at `hpm publish` for each package with a card, and its list is saved in the
archive as `review.md`; the install's `v` shows it (sharing.md section 4).

## Tests

All with a stand-in client; no model is called.

- Each job's tools: the writes it may do and the ones it may not (a write elsewhere is
  refused; no `remove`, no `memory_edit`).
- The cap reaches the session's options; the cost is printed.
- `init`: a bad manifest from the AI shown to it once, then to the user.
- The test install: the copy made and removed, the one line typed, the screen shown.
- Merge: the merged text shown, written only after yes.

## Done when

One paid run, after the user says go: `hpm init kittystory` on a copy of `test-hallux` with
the default model, the manifest it drafts compared with the one written by hand in step 2,
and the cost noted in "As built".
