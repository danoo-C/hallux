"""hpm's AI (hallux/hpm/ai.py, hallux/hpm/assist.py): its session, tools and settings, and
init, the changelog's draft, the review, merging memories and the test install. All with a
stand-in client: no model is called (conftest sets HALLUX_NO_REAL_MODEL, and the real
client then refuses)."""
import asyncio
import json
import os
import re

import pytest
from test_machine import FakeModel, result, screen

from hallux.disk import Disk
from hallux.hpm import ai, assist, cli
from hallux.hpm.archive import listing, read_member
from hallux.hpm.engine import MERGE, Want, apply, plan_install
from hallux.hpm.publish import Questions
from hallux.hpm.running import ASKING, DONE, Installs
from hallux.hpm.store import Store
from hallux.hpm.world import HpmError

CARD = "# kittystory\nchat with characters from packs; ~/.kittystory/\n"
GOOD = '''name = "kittystory"
version = "1.0"
summary = "Chat with characters"
memory_line = "kittystory: chat with characters made from packs"
[files]
app = ["/usr/local/bin/kittystory", "/usr/local/share/apps/kittystory/**"]
seed = ["/usr/local/share/apps/kittystory/data/state.json"]
[extras]
packs = { package = "kittystory-packs", default = true }
memories = { package = "kittystory-memories", default = false }
'''
PACKS = 'name = "kittystory-packs"\nversion = "1.0"\nfor = "kittystory"\n[files]\n' \
        'data = ["~/.kittystory/packs/*.pack"]\n'
MEMORIES = 'name = "kittystory-memories"\nversion = "1.0"\nfor = "kittystory"\n[files]\n' \
           'data = ["~/.kittystory/chars/*/memory.md"]\n'


class StandIn:
    """A client factory whose model is a list of turns: each is called with the session and
    the message, may call the session's tools, and returns what the model says."""

    def __init__(self, *turns, cost=0.01):
        self.turns, self.cost = list(turns), cost
        self.messages, self.options, self.session = [], [], None

    def __call__(self, options):
        self.options.append(options)
        return _Client(self)


class _Client:
    def __init__(self, stand_in):
        self.stand_in = stand_in

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def query(self, message):
        self.stand_in.messages.append(message)
        self.said = await self.stand_in.turns.pop(0)(self.stand_in.session, message)

    async def receive_response(self):
        for message in result(self.said, total=self.stand_in.cost * len(self.stand_in.messages)):
            yield message


@pytest.fixture(autouse=True)
def hand_over(monkeypatch):
    """Each session tells its stand-in about itself, so a turn can call its tools."""
    real = ai.Session.__init__

    def init(self, world, job, settings, client_factory=None):
        real(self, world, job, settings, client_factory)
        if isinstance(client_factory, StandIn):
            client_factory.session = self
    monkeypatch.setattr(ai.Session, "__init__", init)


async def call(session, name, **args):
    found = await session.tools[f"mcp__hpm__{name}"].handler(args)
    return found["content"][0]["text"]


def writes(*files):
    """A turn that writes these (path, text) and says it is done."""
    async def turn(session, message):
        for path, text in files:
            await call(session, "write_file", path=path, content=text)
        return "drafted"
    return turn


def says(text):
    async def turn(session, message):
        return text
    return turn


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "test-hallux"
    files = {
        ".hallux/memory.md": "## Invented programs\n- kittystory: chat with characters\n",
        "etc/passwd": "danika:x:1000:1000::/home/danika:/bin/bash\n",
        "usr/local/bin/kittystory": CARD,
        "usr/local/share/apps/kittystory/index.html": "<html></html>\n",
        "usr/local/share/apps/kittystory/data/state.json": '{"chat": ["hi Emma"]}\n',
        "home/danika/.kittystory/packs/tsundere.pack": "tsundere\n",
        "home/danika/.kittystory/chars/Emma/memory.md": "2026-10-03 met the user\n",
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "store")


class Said(Questions):
    def __init__(self, *answers, interactive=False):
        super().__init__(interactive=interactive)
        self.answers, self.said = list(answers), []

    def say(self, text):
        self.said.append(text)

    def confirm(self, question, default, flag):
        self._needs_terminal(question, flag)
        self.said.append(f"? {question}")
        return self.answers.pop(0) if self.answers else default

    def edit(self, template, flag):
        return template


# ---------------------------------------------------------------- the real client is refused

def test_no_test_reaches_the_real_model(world, store):
    with pytest.raises(RuntimeError, match="a test reached for the real model"):
        ai.Session(world, ai.review_job("x", "card", "manifest"), ai.Settings())


# ---------------------------------------------------------------- the store's settings

def test_settings_default_and_from_the_file(store):
    assert ai.settings(store) == ai.Settings(path=store.home / "config.toml")
    store.home.mkdir(parents=True)
    (store.home / "config.toml").write_text('model = "claude-haiku-4-5"\neffort = "low"\n'
                                            'cap_usd = 0.5\nbase_world = "~/hallux-distros/x"\n')
    found = ai.settings(store)
    assert (found.model, found.effort, found.cap_usd, found.base_world) == (
        "claude-haiku-4-5", "low", 0.5, "~/hallux-distros/x")


def test_bad_settings_are_told_all_at_once(store):
    store.home.mkdir(parents=True)
    (store.home / "config.toml").write_text('effort = "huge"\ncap_usd = -1\ncolour = "pink"\n')
    with pytest.raises(HpmError, match="unknown key 'colour'; effort must be one of .*; "
                                       "cap_usd must be a number"):
        ai.settings(store)


def test_the_model_is_the_worlds_without_one_set(world):
    (world / ".hallux/config.toml").write_text('model = "claude-sonnet-5-5"\n')
    assert ai.Settings().model_for(world) == "claude-sonnet-5-5"
    assert ai.Settings(model="claude-haiku-4-5").model_for(world) == "claude-haiku-4-5"


# ---------------------------------------------------------------- a session

def test_the_session_gets_its_prompt_its_tools_and_the_cap(world):
    stand_in = StandIn(says("ok"))
    session = ai.Session(world, ai.init_job("kittystory", CARD, None),
                         ai.Settings(effort="high", cap_usd=0.75), stand_in)
    asyncio.run(session.ask())
    options = stand_in.options[0]
    assert options.max_budget_usd == 0.75 and options.effort == "high"
    assert options.system_prompt == ai.prompt("init")
    assert sorted(options.allowed_tools) == [
        "mcp__hpm__find", "mcp__hpm__list_dir", "mcp__hpm__read_file", "mcp__hpm__stat",
        "mcp__hpm__write_file"]                       # no remove, no memory_edit, no shell
    assert options.tools == [] and options.setting_sources == []    # nothing of Claude Code's


def test_haiku_gets_no_effort(world):
    stand_in = StandIn(says("ok"))
    asyncio.run(ai.Session(world, ai.review_job("x", "c", "m"),
                           ai.Settings(model="claude-haiku-4-5"), stand_in).ask())
    assert stand_in.options[0].effort is None and stand_in.options[0].allowed_tools == []


def test_init_may_write_only_its_manifests_and_seeds(world):
    async def turn(session, message):
        answers = [await call(session, "write_file", path=path, content="x")
                   for path in ("/usr/local/share/hpm/kittystory/hpm.toml",
                                "/usr/local/share/hpm/kittystory-packs/hpm.toml",
                                "/usr/local/share/hpm/kittystory/seed/usr/local/x.json",
                                "/usr/local/bin/kittystory", "/usr/local/share/hpm/other/hpm.toml",
                                "/etc/motd", "/.hallux/memory.md")]
        return json.dumps(answers)
    stand_in = StandIn(turn)
    answer = asyncio.run(ai.Session(world, ai.init_job("kittystory", CARD, None), ai.Settings(),
                                    stand_in).ask())
    results = json.loads(answer.text)
    assert ["EACCES" not in r for r in results] == [True, True, True, False, False, False, False]
    assert answer.wrote == ["/usr/local/share/hpm/kittystory/hpm.toml",
                            "/usr/local/share/hpm/kittystory-packs/hpm.toml",
                            "/usr/local/share/hpm/kittystory/seed/usr/local/x.json"]
    assert (world / "usr/local/bin/kittystory").read_text() == CARD
    assert "kittystory" in (world / ".hallux/memory.md").read_text()


def test_the_read_tools_see_the_world_not_its_hidden_folder(world):
    async def turn(session, message):
        return json.dumps([await call(session, "read_file", path="/usr/local/bin/kittystory"),
                           await call(session, "read_file", path="/.hallux/memory.md")])
    answer = asyncio.run(ai.Session(world, ai.init_job("kittystory", CARD, None), ai.Settings(),
                                    StandIn(turn)).ask())
    card, hidden = json.loads(answer.text)
    assert "chat with characters" in card and "ENOENT" in hidden


def test_a_session_that_reaches_its_cap(world):
    stand_in = StandIn(says("…"))
    session = ai.Session(world, ai.review_job("x", "c", "m"), ai.Settings(cap_usd=0.01), stand_in)
    real = _Client.receive_response

    async def capped(self):
        async for message in real(self):
            if type(message).__name__ == "ResultMessage":
                message.subtype = "error_max_budget_usd"
            yield message
    _Client.receive_response = capped
    try:
        answer = asyncio.run(session.ask())
    finally:
        _Client.receive_response = real
    assert not answer.ok and answer.why == "it reached the cap of $0.01"


def test_each_session_has_a_line_in_the_worlds_log(world):
    asyncio.run(ai.Session(world, ai.review_job("x", "c", "m"), ai.Settings(), StandIn(says("-"))).ask())
    line = (world / ".hallux/hallux.log").read_text().splitlines()[-1]
    assert "hpm review: done, ~$0.0100, model" in line


# ---------------------------------------------------------------- hpm init

def run_init(world, store, *turns, q=None, yes=True):
    stand_in = StandIn(*turns)
    q = q or Said()
    return assist.init(world, store, "kittystory", q, yes=yes, client_factory=stand_in), q, stand_in


def test_init_keeps_a_good_draft_and_marks_memories_private(world, store):
    written, q, stand_in = run_init(world, store, writes(
        ("/usr/local/share/hpm/kittystory/hpm.toml", GOOD),
        ("/usr/local/share/hpm/kittystory-packs/hpm.toml", PACKS),
        ("/usr/local/share/hpm/kittystory-memories/hpm.toml", MEMORIES)))
    assert written == ["/usr/local/share/hpm/kittystory-memories/hpm.toml",
                       "/usr/local/share/hpm/kittystory-packs/hpm.toml",
                       "/usr/local/share/hpm/kittystory/hpm.toml"]
    assert "private = true" in (world / "usr/local/share/hpm/kittystory-memories/hpm.toml").read_text()
    assert any("marked private" in line for line in q.said)
    assert q.said[-1] == "the AI's part cost ~$0.0100"
    first = stand_in.messages[0]
    assert "/usr/local/bin/kittystory" in first and CARD.strip() in first
    assert "kittystory: chat with characters" in first             # the memory's line


def test_init_gives_the_ai_the_line_without_its_tag(world, store):
    """Fix 02: after an install or a publish the only line is hpm's, tagged."""
    (world / ".hallux/memory.md").write_text(
        "## Invented programs\n- kittystory: chat with characters [hpm kittystory 1.0]\n")
    _, _, stand_in = run_init(world, store, writes(
        ("/usr/local/share/hpm/kittystory/hpm.toml", GOOD),
        ("/usr/local/share/hpm/kittystory-packs/hpm.toml", PACKS),
        ("/usr/local/share/hpm/kittystory-memories/hpm.toml", MEMORIES)))
    first = stand_in.messages[0]
    assert "\nkittystory: chat with characters\n" in first
    assert "[hpm" not in first and "- kittystory: chat" not in first


def test_init_shows_the_problems_to_the_ai_once(world, store):
    bad = GOOD.replace('"/usr/local/share/apps/kittystory/**"', '"/usr/local/share/apps/gone/**"')
    written, q, stand_in = run_init(world, store,
                                    writes(("/usr/local/share/hpm/kittystory/hpm.toml", bad)),
                                    writes(("/usr/local/share/hpm/kittystory/hpm.toml", GOOD)))
    assert len(stand_in.messages) == 2
    assert "/usr/local/share/apps/gone/** matches nothing" in stand_in.messages[1]
    assert (world / "usr/local/share/hpm/kittystory/hpm.toml").read_text() == GOOD


def test_init_tells_you_what_the_ai_left_wrong(world, store):
    bad = 'name = "kittystory"\n'
    with pytest.raises(HpmError, match="still have problems.*version is missing"):
        run_init(world, store, writes(("/usr/local/share/hpm/kittystory/hpm.toml", bad)),
                 writes(("/usr/local/share/hpm/kittystory/hpm.toml", bad)))
    assert (world / "usr/local/share/hpm/kittystory/hpm.toml").exists()   # left, to fix by hand


def test_init_asks_first_and_needs_a_card(world, store):
    with pytest.raises(HpmError, match="needs the AI: pass --yes"):
        run_init(world, store, yes=False)                   # no terminal, no --yes
    q = Said(False, interactive=True)
    with pytest.raises(HpmError, match="needs the AI"):
        run_init(world, store, q=q, yes=False)
    assert "at most $1.00" in q.said[0]
    os.remove(world / "usr/local/bin/kittystory")
    with pytest.raises(HpmError, match="no card /usr/local/bin/kittystory"):
        run_init(world, store)


def test_init_never_over_a_manifest(world, store):
    (world / "usr/local/share/hpm/kittystory").mkdir(parents=True)
    (world / "usr/local/share/hpm/kittystory/hpm.toml").write_text(GOOD)
    with pytest.raises(HpmError, match="has a manifest already"):
        run_init(world, store)


# ---------------------------------------------------------------- init: the family (fix 01)

SPRITE = "/usr/local/share/apps/kittystory/sprites/emma.svg"
CHARS = ('name = "kittystory-chars"\nversion = "1.0"\nfor = "kittystory"\n[files]\n'
         f'data = ["{SPRITE}"]\n')
WITH_CHARS = GOOD.replace('memories = { package = "kittystory-memories", default = false }\n',
                          'chars = { package = "kittystory-chars", default = true }\n')
OWN_FILES = WITH_CHARS.replace('"/usr/local/share/apps/kittystory/**"',
                               '"/usr/local/share/apps/kittystory/index.html"')
SHARED = f"{SPRITE} is in kittystory and in kittystory-chars; one package must carry it"


@pytest.fixture
def sprite(world):
    (world / SPRITE.lstrip("/")).parent.mkdir(parents=True)
    (world / SPRITE.lstrip("/")).write_text("<svg/>\n")
    return world


def test_init_shows_the_ai_a_file_two_packages_carry(sprite, store):
    written, q, stand_in = run_init(sprite, store, writes(
        ("/usr/local/share/hpm/kittystory/hpm.toml", WITH_CHARS),
        ("/usr/local/share/hpm/kittystory-packs/hpm.toml", PACKS),
        ("/usr/local/share/hpm/kittystory-chars/hpm.toml", CHARS)),
        writes(("/usr/local/share/hpm/kittystory/hpm.toml", OWN_FILES)))
    assert len(stand_in.messages) == 2 and SHARED in stand_in.messages[1]
    assert (sprite / "usr/local/share/hpm/kittystory/hpm.toml").read_text() == OWN_FILES
    assert "/usr/local/share/hpm/kittystory-chars/hpm.toml" in written


def test_a_shared_file_left_is_inits_error(sprite, store):
    draft = writes(("/usr/local/share/hpm/kittystory/hpm.toml", WITH_CHARS),
                   ("/usr/local/share/hpm/kittystory-packs/hpm.toml", PACKS),
                   ("/usr/local/share/hpm/kittystory-chars/hpm.toml", CHARS))
    with pytest.raises(HpmError, match="still have problems.*" + re.escape(SHARED)):
        run_init(sprite, store, draft, draft)
    assert (sprite / "usr/local/share/hpm/kittystory-chars/hpm.toml").exists()


def test_init_checks_and_shows_the_manifests_from_before(sprite, store):
    """The user's run: only the program's manifest was moved away; the extras' stayed."""
    for name, text in (("kittystory-chars", CHARS), ("kittystory-packs", PACKS)):
        (sprite / f"usr/local/share/hpm/{name}").mkdir(parents=True)
        (sprite / f"usr/local/share/hpm/{name}/hpm.toml").write_text(text)
    q = Said()
    with pytest.raises(HpmError, match="still have problems"):
        run_init(sprite, store, writes(("/usr/local/share/hpm/kittystory/hpm.toml", WITH_CHARS)),
                 writes(("/usr/local/share/hpm/kittystory/hpm.toml", WITH_CHARS)), q=q)
    assert any(line.startswith("there from before") and "kittystory-chars" in line
               for line in q.said)
    assert any(line.startswith("\n--- /usr/local/share/hpm/kittystory-chars/hpm.toml")
               for line in q.said)                              # shown, though not written now


def test_an_extra_the_program_doesnt_list(sprite, store):
    stray = CHARS.replace("kittystory-chars", "kittystory-extra")
    draft = writes(("/usr/local/share/hpm/kittystory/hpm.toml", OWN_FILES.replace(
                        'chars = { package = "kittystory-chars", default = true }\n', "")),
                   ("/usr/local/share/hpm/kittystory-packs/hpm.toml", PACKS),
                   ("/usr/local/share/hpm/kittystory-extra/hpm.toml", stray))
    with pytest.raises(HpmError, match="kittystory-extra/hpm.toml is not listed under "
                                       r"\[extras\] of kittystory's manifest"):
        run_init(sprite, store, draft, draft)


# ---------------------------------------------------------------- publish: draft, review, seed

def publish(world, store, *args, stand_in=None, q=None):
    q = q or Said()
    code = cli.main(["publish", "kittystory", "--world", str(world), *args], questions=q,
                    store=store, client_factory=stand_in)
    return code, q


def manifests(world):
    for name, text in (("kittystory", GOOD), ("kittystory-packs", PACKS)):
        (world / f"usr/local/share/hpm/{name}").mkdir(parents=True, exist_ok=True)
        (world / f"usr/local/share/hpm/{name}/hpm.toml").write_text(
            text.replace('memories = { package = "kittystory-memories", default = false }\n', ""))


def test_a_clean_seed_is_published_in_place_of_yours(world, store):
    manifests(world)
    clean = world / "usr/local/share/hpm/kittystory/seed/usr/local/share/apps/kittystory/data"
    clean.mkdir(parents=True)
    (clean / "state.json").write_text('{"chat": []}\n')
    publish(world, store, "--version", "1.0", "--changelog", "first")
    release = store.latest("kittystory")
    assert read_member(release.path, "files/root/usr/local/share/apps/kittystory/data/state.json") \
        == b'{"chat": []}\n'


def test_the_changelog_drafted_by_the_ai(world, store):
    manifests(world)
    publish(world, store, "--version", "1.0", "--changelog", "first")
    (world / "usr/local/share/apps/kittystory/index.html").write_text("<html>new</html>\n")

    async def turn(session, message):
        old = await call(session, "release_read_file",
                         path="/usr/local/share/apps/kittystory/index.html")
        assert "<html></html>" in old
        return "- the start page is new"
    stand_in = StandIn(turn)
    code, q = publish(world, store, "--yes", "--draft", stand_in=stand_in)
    assert code == 0
    assert "Changed:\n  /usr/local/share/apps/kittystory/index.html" in stand_in.messages[0]
    changelog = (world / "usr/local/share/hpm/kittystory/CHANGELOG.md").read_text()
    assert changelog.startswith("## 1.1 (") and "- the start page is new" in changelog


def test_the_draft_names_what_in_the_manifest_disagrees(world, store):
    """Fix 03: the block after "Manifest:" is said, and kept out of the entry."""
    manifests(world)
    publish(world, store, "--version", "1.0", "--changelog", "first")
    (world / "usr/local/share/apps/kittystory/index.html").write_text("<html>new</html>\n")
    stand_in = StandIn(says("- the start page is new\n\nManifest:\n"
                            "- memory_line still mentions packs, which this version removes"))
    code, q = publish(world, store, "--yes", "--draft", stand_in=stand_in)
    assert code == 0
    assert 'memory_line = "kittystory: chat with characters made from packs"' in stand_in.messages[0]
    changelog = (world / "usr/local/share/hpm/kittystory/CHANGELOG.md").read_text()
    assert "- the start page is new" in changelog and "Manifest" not in changelog
    assert "memory_line still mentions" not in changelog
    assert any("the manifest disagrees" in line and "memory_line still mentions packs" in line
               for line in q.said)


def test_split_manifest_block():
    assert assist.split_manifest_block("- a\n- b\n") == ("- a\n- b", "")
    assert assist.split_manifest_block("- a\nManifest:\n- x\n") == ("- a", "- x")


def test_the_review_goes_with_the_release(world, store):
    manifests(world)
    stand_in = StandIn(says("- nothing reaches beyond the program"))
    code, q = publish(world, store, "--version", "1.0", "--changelog", "first", "--review",
                      stand_in=stand_in)
    assert code == 0 and CARD.strip() in stand_in.messages[0]
    assert read_member(store.latest("kittystory").path, "review.md") == \
        b"- nothing reaches beyond the program\n"
    plan = plan_install(world, store, [Want("kittystory", extras=())])
    plan.close()


def test_without_a_flag_or_a_terminal_nothing_asks_the_ai(world, store):
    manifests(world)
    code, q = publish(world, store, "--version", "1.0", "--changelog", "first")
    assert code == 0 and "review.md" not in listing(store.latest("kittystory").path)


def test_on_a_terminal_the_ai_is_asked_for_first(world, store):
    manifests(world)
    q = Said(False, interactive=True)                 # no review; no test install
    publish(world, store, "--version", "1.0", "--changelog", "first", q=q)
    asked = [line for line in q.said if line.startswith("? ")]
    assert asked[0].startswith("? have kittystory's card reviewed") and "at most $1.00" in asked[0]
    assert asked[-1].startswith("? try kittystory 1.0 in a copy of the base world")


# ---------------------------------------------------------------- merging memories

def test_a_merge_keeps_every_line(world, store):
    text, answer = assist.merge(world, store, "/x/memory.md", "a\nb\n", "b\nc\n",
                                client_factory=StandIn(says("```\na\nb\nc\n```")))
    assert text == "a\nb\nc\n"


def test_a_merge_that_loses_a_line_is_refused(world, store):
    text, answer = assist.merge(world, store, "/x/memory.md", "a\nb\n", "c\n",
                                client_factory=StandIn(says("a\nc\n")))
    assert text is None and "left out 1 line(s), such as 'b'" in answer.why


def test_merge_on_the_conflict_screen(world, store, tmp_path):
    manifests(world)
    (world / "usr/local/share/hpm/kittystory-memories").mkdir(parents=True)
    (world / "usr/local/share/hpm/kittystory-memories/hpm.toml").write_text(
        MEMORIES)
    for name in ("kittystory", "kittystory-packs", "kittystory-memories"):
        cli.main(["publish", name, "--world", str(world), "--version", "1.0", "--changelog",
                  "x", "--private", "no"], questions=Said(), store=store)
    other = tmp_path / "other"
    (other / ".hallux").mkdir(parents=True)
    (other / "etc").mkdir()
    (other / "etc/passwd").write_text("user:x:1000:1000::/home/user:/bin/sh\n")
    (other / "home/user/.kittystory/chars/Emma").mkdir(parents=True)
    (other / "home/user/.kittystory/chars/Emma/memory.md").write_text("2026-10-20 a walk\n")

    class Screens:
        def checkboxes(self, choices, title=""):
            return None

        def conflicts(self, groups):
            return {q.path: MERGE for qs in groups.values() for q in qs}

    stand_in = StandIn(says("2026-10-03 met the user\n2026-10-20 a walk\n"))
    q = Said(True, interactive=True)                  # write the merged text: yes
    code = cli.main(["install", "kittystory-memories", "--world", str(other), "--yes",
                     "--extras", "none"], questions=q, store=store, screens=Screens(),
                    client_factory=stand_in)
    assert code == 0
    assert (other / "home/user/.kittystory/chars/Emma/memory.md").read_text() == (
        "2026-10-03 met the user\n2026-10-20 a walk\n")
    assert any("merged" in line for line in q.said)


def test_merge_from_the_tab(world, store, tmp_path):
    manifests(world)
    (world / "usr/local/share/hpm/kittystory-memories").mkdir(parents=True)
    (world / "usr/local/share/hpm/kittystory-memories/hpm.toml").write_text(MEMORIES)
    for name in ("kittystory", "kittystory-packs", "kittystory-memories"):
        cli.main(["publish", name, "--world", str(world), "--version", "1.0", "--changelog",
                  "x", "--private", "no"], questions=Said(), store=store)
    other = tmp_path / "other"
    (other / ".hallux").mkdir(parents=True)
    (other / "home/user/.kittystory/chars/Emma").mkdir(parents=True)
    (other / "home/user/.kittystory/chars/Emma/memory.md").write_text("2026-10-20 a walk\n")
    for path, text in (("usr/local/bin/kittystory", CARD),):
        (other / path).parent.mkdir(parents=True, exist_ok=True)
        (other / path).write_text(text)
    installs = Installs(Disk(other), store)
    installs.client_factory = StandIn(says("2026-10-03 met the user\n2026-10-20 a walk\n"))

    async def go():
        installs.plan_install([Want("kittystory-memories")])
        await until(installs, ASKING)
        question = [q for q in installs.watch().plan.questions if q.path.endswith("memory.md")][0]
        answers = {q.path: "skip" for q in installs.watch().plan.questions} | {question.path: MERGE}
        installs.go(answers)                          # the AI merges: asked again, with the text
        await until(installs, ASKING, after=0.05)
        assert installs.watch().merged[question.path].startswith("2026-10-03")
        installs.go(answers)                          # Enter again: written
        await until(installs, DONE)
    asyncio.run(asyncio.wait_for(go(), 10))
    assert (other / "home/user/.kittystory/chars/Emma/memory.md").read_text() == (
        "2026-10-03 met the user\n2026-10-20 a walk\n")


async def until(installs, state, seconds=5, after=0.0):
    await asyncio.sleep(after)
    for _ in range(int(seconds / 0.02)):
        if installs.watch().state == state and not installs.watch().merging:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"still {installs.watch().state}")


# ---------------------------------------------------------------- the test install

def test_the_test_install(world, store, tmp_path):
    manifests(world)
    publish(world, store, "--version", "1.0", "--changelog", "first")
    base = tmp_path / "base"
    (base / ".hallux").mkdir(parents=True)
    (base / ".hallux/memory.md").write_text("# a base world\n")
    (base / "home/user").mkdir(parents=True)
    store.home.mkdir(parents=True, exist_ok=True)
    (store.home / "config.toml").write_text(f'model = "claude-sonnet-5-5"\neffort = "low"\n'
                                            f'cap_usd = 0.4\nbase_world = "{base}"\n')
    model = FakeModel(screen("booted\n"), screen("kittystory: chat\n"),
                      screen("", prompt="", tail="<halt/>"))    # Ctrl-D, as a script ends
    q = Said()
    assist.test_install(store, store.latest("kittystory"), q, client_factory=model)
    assert "$ kittystory\nkittystory: chat" in q.said
    assert "the test install leaves out kittystory-packs: not in the store yet" in q.said
    assert model.sessions[0][1].endswith(">kittystory</input>")
    options = model.options[0]
    assert options.model == "claude-sonnet-5-5"
    assert sorted(base.iterdir()) == [base / ".hallux", base / "home"]   # the base is untouched
    assert not (base / "usr").exists()


def test_the_test_install_needs_a_base_world(world, store):
    manifests(world)
    publish(world, store, "--version", "1.0", "--changelog", "first")
    with pytest.raises(HpmError, match="set base_world in"):
        assist.test_install(store, store.latest("kittystory"), Said())
