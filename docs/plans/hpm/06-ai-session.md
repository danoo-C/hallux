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

**`hpm init NAME`** (it works on a running world: it writes only the manifest, under
`/usr/local/share/hpm/<name>/`): asks the AI for a manifest from the card `/usr/local/bin/<name>` and the
memory's line about it, shows it, opens `$EDITOR` on it, checks it again, saves it. It
suggests the extras (packs, characters, memories) and marks a memories package private
(sharing.md section 3), and asks the AI for a clean seed where a seed holds a chat.

**Publish** (step 2) now offers the AI's changelog draft, and, with `--test`, the test
install (decision 17): a copy of `base_world` from the store's `config.toml` into a temporary
folder, `hpm install` into it with every default extra, then `run_script` with the app's name
as the only line, the screen and the cost shown. The copy is removed afterwards. It is a
whole machine (a boot, then the line), so it costs more than a job: it runs on the copy's
own `config.toml` with the model and effort of hpm's `config.toml` put in, and with hpm's
cap as the boot's `max_budget_usd` (a setting `Hardware` has already). The question before
it says that it is a boot and a line, and the cap.

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
- The test install: the copy made and removed, the one line typed, the screen shown; the
  model, effort and cap of hpm's `config.toml` in the copy's `Hardware`.
- Merge: the merged text shown, written only after yes.

## Done when

One paid run, after the user says go: `hpm init kittystory` on a copy of `test-hallux` with
the default model, the manifest it drafts compared with the one written by hand in step 2,
and the cost noted in "As built".

## As built

Built 2026-10-23, **without the paid run** (it waits for the user's go): `hallux/hpm/ai.py`
(the session, its tools, the store's settings), `hallux/hpm/assist.py` (init, the
changelog's draft, the review, the merge, the test install),
`hallux/hpm/prompts/{init,changelog,merge,review}.md` (package data in `pyproject.toml`);
`hpm init` and publish's `--draft`, `--review` and `--test` in `cli.py`; merge in the
engine, the conflict screens and the Packages tab; `review.md` in a package, shown by `v`;
`tests/test_hpm_ai.py` (26 tests). The whole suite: 2248 passed, the sandbox test left out
as before; one web addon test (`test_a_hostile_page_gets_nothing_out`) failed once under the
full suite's load and its file passed twice on its own afterwards.

**No test can reach the model.** While this step was built, a test whose scripted terminal
answered every question with its default said yes to the new "have the card reviewed?" and
reached for the real client. The session's sandbox refused every connection to
`api.anthropic.com`, so nothing was sent or spent. Since then `ai.real_client()` refuses
when `HALLUX_NO_REAL_MODEL` is set, and `tests/conftest.py` sets it: a test that reaches
for the model fails loudly instead.

**The paid run, still to do** (after the user says go): `hpm init kittystory` on a copy of
`test-hallux` with the default model (the world's, `claude-opus-5-5` there, at effort
`medium`, the cap $1.00), the manifest it drafts compared with the one written by hand in
step 2, and its cost noted here.

What the code does that the step above didn't say, or says differently:

- **Every AI part asks first,** with the model and the cap in the question: `hpm init`
  (or `--yes`), the changelog's draft (`--draft`), the review (`--review`), the test install
  (`--test`; its question defaults to no). Without a terminal and without the flag, the AI
  isn't asked: init stops and says so; publish goes on without the draft or the review.
- **The review is asked for at publish,** not always run: it costs a model call each time.
  Step 8's push reviews a version that has none.
- **init's tools** read the world (`list_dir`, `stat`, `read_file`, `find`) and write only
  `/usr/local/share/hpm/<name>/hpm.toml`, `/usr/local/share/hpm/<name>-<part>/hpm.toml`
  (the extras) and files under `/usr/local/share/hpm/<name>/seed/`. Its problems (a manifest
  that doesn't read, a pattern that matches nothing, a manifest in the wrong folder) go back
  to the AI once, in the same session; what is still wrong after that is told to you, and
  the files are left to fix by hand.
- **A data package that holds memories or a chat is marked private by hpm's code,** whatever
  the AI wrote.
- **A clean seed:** a file at `/usr/local/share/hpm/<name>/seed/<the seed's path>` is
  published in place of the world's own seed (so kittystory's `state.json` with your chat
  stays home). init's prompt asks the AI to write one where a seed holds your data.
- **The changelog's draft** is told which files were added, changed and removed, and can
  read the last release (`release_list_dir`, `release_read_file`, the release laid out as a
  world). On a terminal the draft opens in `$EDITOR`; with `--draft` and no terminal it is
  the entry.
- **A merge** is checked by hpm's code: every line of both files must be in what the AI
  gives back, or the merge is refused and the file skipped. On a terminal the merged text is
  shown and written only on yes; in the Packages tab the first Enter has the AI merge (in a
  thread) and shows the text, the second Enter writes it.
- **The test install** copies `base_world` (from the store's `config.toml`), installs the
  release with those of its default extras that are in the store (it says which it leaves
  out), and runs the copy headless with the program's name as the one line: a boot, the
  line, and the Ctrl-D a script ends with. Only the line's screen is shown, and the cost.
- **The store's `config.toml`** has `model`, `effort`, `cap_usd` and `base_world`; an
  unknown key or a wrong value is an error that names the file.
- **Each session** writes a line into the world's `.hallux/hallux.log`: the job, done or why
  not, its cost and model.
