"""The Agents and Details tabs of hallux's own panel. What they draw is tested from made-up
jobs, without a pipe. What they do is tested in a real panel on a pipe, around a Jobs whose
workers are stand-ins."""
import asyncio
import contextlib

import pytest

pytest.importorskip("prompt_toolkit")

from prompt_toolkit.input import create_pipe_input  # noqa: E402
from test_agents import GUI, HERE, MAIL, MUSIC, ROOMY, WELL, World  # noqa: E402
from test_agents import music, root  # noqa: E402,F401  (fixtures)
from test_panel import ESC, Screen, StandIn, click, drawn, style_at  # noqa: E402

from hallux.agents import Declared, Jobs, Line, Outcome, Seen, Watched  # noqa: E402
from hallux.config import Hardware  # noqa: E402
from hallux.disk import Disk  # noqa: E402
from hallux.panel import Panel  # noqa: E402
from hallux.panel_tabs import agents, details  # noqa: E402
from hallux.panel_tabs.agents import AgentsTab  # noqa: E402
from hallux.panel_tabs.details import DetailsTab  # noqa: E402
from hallux.statusbar import DIM  # noqa: E402

UP, DOWN, LEFT, RIGHT, ENTER = "\x1b[A", "\x1b[B", "\x1b[D", "\x1b[C", "\r"
PAGE_UP, PAGE_DOWN = "\x1b[5~", "\x1b[6~"


# ---------------------------------------------------------------- what the tabs draw

def a_row(pid, addon, agent, state, seconds, tokens, status, **more):
    return {"pid": pid, "addon": addon, "agent": agent, "state": state,
            "started": "2026-10-06T21:14:03+02:00", "seconds": seconds, "tokens": tokens,
            "folder": "/home/user/Music", "status": status} | more


LINES = (Line(2.4, "status", "sketching the drums"), Line(3.1, "write_file", ""),
         Line(3.2, "→", '{"ok": true, "size": 812}'), Line(11.0, "check", "midnight-cello.score"),
         Line(11.6, "→", '{"error": "line 16: unknown instrument or variable: kik"}'),
         Line(12.2, "says", "The kick's name is misspelled in bar 3. Fixing it, and then I will "
                            "run the check again to see whether the mix still peaks."),
         Line(31.0, "status", "balancing the mix"), Line(47.0, "check", "midnight-cello.score"))
WATCHED = Watched(
    jobs=(Seen(a_row(30005, "music", "composer", "waiting", 48, 21340, "balancing the mix",
                     tool="check midnight-cello.score"),
               ("/home/user/Music/neon.score",), LINES, None),
          Seen(a_row(30004, "mail", "sorter", "done", 92, 18200, "filing", cost_usd=0.19), (),
               (Line(92.0, "end", "done: inbox.txt"),), "inbox.txt"),
          Seen(a_row(30003, "backup", "archiver", "killed", 600, 140000, "packing", why="timeout",
                     cost_usd=1.0), (), (), "timeout"),
          Seen(a_row(30002, "backup", "archiver", "failed", 12, 900, "packing", why="folder",
                     cost_usd="unknown"), (), (), "folder")),
    agents=(Declared("music", "composer", "You compose one song.\nKeep it short.", ("check",),
                     "high", "claude-opus-5-5", "high", "already running"),
            Declared("gui", "designer", "You design.", (), "max", "claude-opus-5-5", "high", None),
            Declared("web", "researcher", "You research.", ("fetch", "read"), None,
                     "claude-haiku-4-5", None, "jobs budget used")),
    spent_boot=1.19)


def agents_text(watched=WATCHED, pick=None, width=100, **state):
    drawn_ = agents.draw(watched, agents.State(**state), pick, width)
    return ["".join(text for _, text, _ in line).rstrip()
            for line in (drawn_.head, *drawn_.rows, drawn_.under)]


def details_text(pick, watched=WATCHED, width=80):
    listed = agents.rows(watched)
    drawn_ = details.draw(listed[agents.picked(listed, pick)] if listed else None, width)
    return [text for _, text in drawn_.head], [text for _, text in drawn_.body]


def test_the_agents_tab_as_it_is_drawn():
    assert agents_text() == [
        "   PID  ADDON   AGENT       STATE    TIME TOKENS    COST  STATUS",
        " 30005  music   composer    waiting  0:48    21k       ·  balancing the mix",
        " 30004  mail    sorter      done     1:32    18k  ~$0.19  inbox.txt",       # how it ended
        " 30003  backup  archiver    killed  10:00   140k  ~$1.00  timeout",
        " 30002  backup  archiver    failed   0:12    900       ?  folder",          # cost unknown
        "     ·  gui     designer    idle        ·      ·       ·  ready · effort high",
        "     ·  web     researcher  idle        ·      ·       ·  can't start: jobs budget used",
        " 1 running · 3 ended · jobs in this boot: ~$1.19"]


def test_the_picked_row_is_in_reverse_and_the_first_is_picked_when_none_is():
    def reversed_rows(pick):
        drawn_ = agents.draw(WATCHED, agents.State(), pick, 80)
        return [at for at, line in enumerate(drawn_.rows) if line[0][0] == "reverse"], drawn_.cursor.y

    assert reversed_rows(None) == ([0], 0) and reversed_rows(30003) == ([2], 2)
    assert reversed_rows("web") == ([5], 5) and reversed_rows(4711) == ([0], 0)
    assert reversed_rows("music") == ([0], 0)            # its job runs: it is no idle row
    [whole] = agents.draw(WATCHED, agents.State(), 30004, 80).rows[1]
    assert len(whole[1]) == 79 and whole[2] == 30004     # the whole row, and a click picks it


def test_i_hides_the_idle_agents_in_what_is_drawn():
    hidden = agents_text(hide_idle=True)
    assert len(hidden) == 6 and not any(" idle " in line for line in hidden)
    assert hidden[-1] == " 1 running · 3 ended · jobs in this boot: ~$1.19"


def test_a_narrow_agents_tab_cuts_the_status_and_long_names():
    narrow = agents_text(width=80)
    assert all(len(line) <= 79 for line in narrow)
    assert narrow[6] == "     ·  web     researcher  idle        ·      ·       ·  can't start: jobs bu…"
    long = Watched((), (Declared("a_very_long_addon_name", "the_agent_of_it", "x", (), None,
                                 "claude-opus-5-5", "low", None),), 0.0)
    assert agents_text(long)[1] == ("     ·  a_very_long…  the_agent_o…  idle        ·      ·"
                                    "       ·  ready · effort low")
    assert agents_text(Watched((), (), 0.0)) == [
        "   PID  ADDON  AGENT  STATE    TIME TOKENS    COST  STATUS",
        " 0 running · 0 ended · jobs in this boot: ~$0.00"]


def test_the_details_of_a_job_as_they_are_drawn():
    head, body = details_text(30005)
    assert head == [" 30005 · music · composer · waiting in check · 0:48 · 21k tok",
                    " folder /home/user/Music · may change: neon.score"]
    assert body == [
        "  0:02  status      sketching the drums",
        "  0:03  write_file  ",
        '                    → {"ok": true, "size": 812}',
        "  0:11  check       midnight-cello.score",
        '                    → {"error": "line 16: unknown instrument or variable: kik"}',
        "  0:12  says        The kick's name is misspelled in bar 3. Fixing it, and then",
        "                    I will run the check again to see whether the mix still",
        "                    peaks.",
        "  0:31  status      balancing the mix",
        "  0:47  check       midnight-cello.score"]


def test_the_details_of_an_ended_job_have_its_cost_and_how_it_ended():
    head, body = details_text(30004)
    assert head == [" 30004 · mail · sorter · done · 1:32 · 18k tok · ~$0.19",
                    " folder /home/user/Music · creates files only"]
    assert body == ["  1:32  end     done: inbox.txt"]
    assert details_text(30002)[0][0] == " 30002 · backup · archiver · failed · 0:12 · 900 tok · ?"


def test_the_details_of_an_idle_agent_are_what_it_is():
    head, body = details_text("gui")
    assert head == [" gui · designer · idle · ready · effort high",
                    " asks for effort max · gets claude-opus-5-5, effort high"]
    assert body == [" tools: none of its addon's", "", " instructions", " You design."]
    head, body = details_text("web")
    assert head == [" web · researcher · idle · can't start: jobs budget used",
                    " asks for no effort · gets claude-haiku-4-5, no effort"]
    assert body[0] == " tools: fetch, read"
    assert details_text(None, Watched((), (), 0.0)) == (["", ""], [])       # nothing to show


# ---------------------------------------------------------------- what the tabs do, in a real panel

THREE = Hardware(agent_budget_usd=1000, agent_max_running=3)       # room for a job of each addon
MOVE = "\x1b[<35;20;6M"                                           # the mouse moves, no button


def watching(root, scenario, hardware=THREE, rows=24, columns=100, addons=None):
    """Run `scenario(world, panel, show)`: a Jobs with stand-in workers, and a real panel with
    the two tabs and a stand-in Config around it. `await show()` shows the panel on a pipe and
    returns `press`, which types keys and waits until the panel has drawn again. A job that
    reports draws the panel again, as the terminal does for the real one."""
    async def main():
        world = World(root, hardware)
        if addons is not None:
            world.jobs.addons = tuple(addons)
        panel = Panel([AgentsTab(world.jobs.watch, world.jobs.kill),
                       DetailsTab(world.jobs.watch, world.jobs.kill), StandIn("Config")])
        world.jobs.on_report = panel.invalidate
        with create_pipe_input() as pipe:
            showing = []

            async def show():
                showing.append(asyncio.ensure_future(panel.run(pipe, Screen(rows, columns))))
                await asyncio.sleep(0.1)

                async def press(keys, wait=0.06):
                    drawn_again = asyncio.Event()
                    note = lambda app: drawn_again.set()               # noqa: E731
                    if panel.app is not None:
                        panel.app.after_render += note
                    pipe.send_text(keys)
                    with contextlib.suppress(asyncio.TimeoutError):    # a slow computer
                        await asyncio.wait_for(drawn_again.wait(), 2)
                    if panel.app is not None:
                        panel.app.after_render -= note
                    await asyncio.sleep(wait)
                return press

            try:
                return await scenario(world, panel, show)
            finally:
                panel.close()
                for task in showing:
                    await task
    return asyncio.run(asyncio.wait_for(main(), 20))


async def seen_on(panel, condition, seconds=3):
    """Wait until the panel has drawn what the condition wants, and return the screen."""
    deadline = asyncio.get_running_loop().time() + seconds
    while not condition(rows := drawn(panel)):
        assert asyncio.get_running_loop().time() < deadline, "\n".join(rows)
        await asyncio.sleep(0.02)
    return rows


async def a_job(world, *script, addon=MUSIC, **more):
    """Start a job that waits, and wait until its worker is at that wait."""
    gate = asyncio.Event()
    count = len(world.workers)
    pid = world.spawn(*script, ("wait", gate), addon=addon, **more)
    await world.until(lambda: len(world.workers) > count
                      and world.row(pid)["state"] in ("running", "waiting"))
    await asyncio.sleep(0.02)                            # its script up to the wait has run
    return pid, gate


def test_the_panel_opens_on_agents_while_a_job_runs_and_on_config_when_none_does(root):
    async def scenario(world, panel, show):
        await show()
        idle = panel.tab.title, drawn(panel)[0]
        panel.close()
        await asyncio.sleep(0.1)
        await a_job(world, ("status", "balancing the mix"))
        await show()
        return (idle, panel.tab.title, drawn(panel),
                ["reverse" in style_at(panel, row, 5) for row in (3, 4)])

    (idle, tab_row), running, rows, in_reverse = watching(root, scenario)
    assert idle == "Config" and tab_row.endswith("  Agents     Details   [ Config ]")
    assert running == "Agents" and rows[0].endswith("[ Agents ]   Details     Config")
    assert rows[2].startswith("   PID  ADDON  AGENT     STATE")
    assert rows[3].startswith(" 30001  music  composer  running  0:00      0       ·  balancing")
    assert rows[4].lstrip().startswith("·  mail   sorter    idle") and "ready · effort low" in rows[4]
    assert rows[7] == " 1 running · 0 ended · jobs in this boot: ~$0.00"
    assert rows[-1] == (" ↑ ↓ pick · Enter details · k kill · i hide idle agents · a d c tabs "
                        "· Esc close")
    assert in_reverse == [True, False]                   # the first row is the picked one


def test_a_row_follows_its_job_without_a_key(root):
    async def scenario(world, panel, show):
        pid, gate = await a_job(world, ("status", "sketching the drums"))
        await show()
        before = drawn(panel)[3]
        job = world.jobs._live[pid]
        job.set_status("balancing the mix")              # the job reports: no key is pressed
        job.tokens_so_far(21340)
        world.now += 48
        moved = (await seen_on(panel, lambda rows: "balancing" in rows[3]))[3]
        gate.set()
        ended = (await seen_on(panel, lambda rows: " done " in rows[3]))
        return before, moved, ended[3], ended[4], ended[8]

    before, moved, ended, idle_again, under = watching(root, scenario)
    assert before.startswith(" 30001  music  composer  running  0:00      0       ·  sketching")
    assert moved.startswith(" 30001  music  composer  running  0:48    21k       ·  balancing the mix")
    assert ended.startswith(" 30001  music  composer  done     0:48    21k  ~$0.21  nothing written")
    assert idle_again.lstrip().startswith("·  music  composer  idle")    # its agent is free
    assert under == " 0 running · 1 ended · jobs in this boot: ~$0.21"


def test_i_hides_the_idle_agents_and_shows_them_again(root):
    async def scenario(world, panel, show):
        await a_job(world)
        press = await show()
        shown = drawn(panel)
        await press("i")
        hidden = drawn(panel)
        await press("i")
        again = drawn(panel)
        await press("i")
        await press("c")                                 # away, and back: they are shown again
        await press("a")
        return shown, hidden, again, drawn(panel)

    shown, hidden, again, back = watching(root, scenario)
    assert sum(" idle " in row for row in shown[:-1]) == 2 and shown == again == back
    assert not any(" idle " in row for row in hidden[:-1]) and "i show idle agents" in hidden[-1]
    assert hidden[3] == shown[3] and "i hide idle agents" in shown[-1]


def test_down_and_enter_show_the_details_of_that_row_and_the_arrows_the_next(root):
    async def scenario(world, panel, show):
        await a_job(world, ("status", "sketching the drums"))
        await a_job(world, ("status", "sorting"), addon=MAIL, folder="/tmp/work")
        press = await show()
        first = panel.pick, drawn(panel)[3][:13]         # nothing is picked: the first row is
        await press(DOWN + ENTER)
        details_ = panel.tab.title, panel.pick, drawn(panel)
        await press(RIGHT)
        idle = panel.pick, drawn(panel)
        await press(RIGHT + RIGHT)                       # there is no row after the last
        await press(LEFT + LEFT)
        return first, details_, idle, panel.pick, drawn(panel)[2]

    first, (tab, pick, rows), (agent, idle), back, head = watching(root, scenario)
    assert first == (None, " 30002  mail ")              # the newest job is on top
    assert tab == "Details" and pick == 30001
    assert rows[0].endswith("  Agents   [ Details ]   Config")
    assert rows[2] == " 30001 · music · composer · running · 0:00 · 0 tok"
    assert rows[3] == " folder /home/user/Music · creates files only"
    assert rows[5] == "  0:00  status  sketching the drums"
    assert rows[-1] == " ← → other agent · ↑ ↓ scroll · k kill · a d c tabs · Esc back"
    assert agent == "gui" and idle[2] == " gui · designer · idle · ready · effort low"
    assert idle[5:9] == [" tools: none of its addon's", "", " instructions", " You design."]
    assert back == 30002 and head == " 30002 · mail · sorter · running · 0:00 · 0 tok"


def test_the_details_follow_new_lines_until_the_view_is_scrolled_up(root):
    async def scenario(world, panel, show):
        script = [("status", f"line {n}") for n in range(1, 31)]
        pid, _ = await a_job(world, *script)
        press = await show()                             # 16 rows: ten lines of the job fit
        await press(ENTER)
        job = world.jobs._live[pid]
        bottom = drawn(panel)[5:15]
        job.set_status("line 31")                        # it arrives, and is drawn
        followed = (await seen_on(panel, lambda rows: "line 31" in rows[14]))[5:15]
        await press(UP + UP)
        up = drawn(panel)[5:15]
        job.set_status("line 32")                        # the view stays where it is
        await asyncio.sleep(0.2)
        stays = drawn(panel)[5:15]
        await press(PAGE_UP)
        page = drawn(panel)[5]
        await press(PAGE_DOWN + DOWN + DOWN + DOWN)      # back at the bottom
        job.set_status("line 33")                        # and it follows again
        last = (await seen_on(panel, lambda rows: "line 33" in rows[14]))[5:15]
        return bottom, followed, up, stays, page, last

    def numbers(rows):
        return [int(row.rsplit(" ", 1)[1]) for row in rows]

    bottom, followed, up, stays, page, last = watching(root, scenario, rows=16)
    assert numbers(bottom) == list(range(21, 31)) and numbers(followed) == list(range(22, 32))
    assert numbers(up) == numbers(stays) == list(range(20, 30))
    assert page == "  0:00  status  line 11" and numbers(last) == list(range(24, 34))


def test_k_asks_in_the_foot_and_y_kills_the_job(root):
    async def scenario(world, panel, show):
        pid, _ = await a_job(world, ("status", "balancing the mix"))
        press = await show()
        await press("k")
        asked = drawn(panel)[-1], panel.tab.typing, world.row(pid)["state"]
        await press("y")
        row = await world.ended(pid)
        rows = await seen_on(panel, lambda rows: " killed " in rows[3])
        return asked, row, rows, world.events()

    asked, row, rows, events = watching(root, scenario)
    assert asked == (" kill 30001? y/n", True, "running")            # the question, alone
    assert (row["state"], row["why"], row["cost_usd"]) == ("killed", "kill", 0.07)
    assert rows[3].startswith(" 30001  music  composer  killed   0:00    900  ~$0.07  kill")
    assert rows[-1].startswith(" ↑ ↓ pick")                          # the hint is back
    assert events == [("music", {"event": "job", "pid": 30001, "agent": "composer",
                                 "state": "killed", "why": "kill", "written": 0, "seconds": 0})]


def test_any_key_but_y_drops_the_question_and_no_letter_is_the_hosts_while_it_is_asked(root):
    async def scenario(world, panel, show):
        pid, _ = await a_job(world)
        press = await show()
        seen = []
        for key in ("n", "d", "c", DOWN, ESC):           # d and c would switch the tab
            await press("k")
            asked = drawn(panel)[-1]
            await press(key)
            seen.append((asked, panel.tab.title, panel.tab.typing, panel.is_open,
                         drawn(panel)[-1][:9], world.row(pid)["state"]))
        return seen, panel.pick

    seen, pick = watching(root, scenario)
    assert seen == [(" kill 30001? y/n", "Agents", False, True, " ↑ ↓ pick", "running")] * 5
    assert pick is None                                  # the arrow dropped it, and moved nothing


def test_a_move_of_the_mouse_keeps_the_question_and_a_click_on_another_row_drops_it(root):
    async def scenario(world, panel, show):
        pid, _ = await a_job(world)
        press = await show()
        await press("k")
        await press(MOVE)
        moved = drawn(panel)[-1], panel.tab.typing
        await press(click(4, 10))                        # the row under it: an idle agent
        clicked = drawn(panel)[-1][:9], panel.tab.typing, panel.pick, world.row(pid)["state"]
        await press(click(3, 10) + "k")
        await press(click(3, 10))                        # the same row: it stays
        return moved, clicked, drawn(panel)[-1], panel.pick

    moved, clicked, same_row, pick = watching(root, scenario)
    assert moved == (" kill 30001? y/n", True)
    assert clicked == (" ↑ ↓ pick", False, "mail", "running")        # and nothing was killed
    assert same_row == " kill 30001? y/n" and pick == 30001


def test_k_does_nothing_on_an_ended_job_or_an_idle_agent(root):
    async def scenario(world, panel, show):
        pid = world.spawn(("end", WELL))
        await world.ended(pid)
        press = await show()
        await press("a" + "k")
        on_ended = panel.pick, panel.tab.typing, drawn(panel)[-1][:9]
        await press(DOWN + "k")
        on_idle = panel.pick, panel.tab.typing
        await press(ENTER + "k")                         # and in the Details tab the same
        return on_ended, on_idle, panel.tab.title, panel.tab.typing

    assert watching(root, scenario) == ((None, False, " ↑ ↓ pick"), ("music", False),
                                        "Details", False)


def test_k_in_the_details_asks_too_and_esc_goes_back_to_agents_and_then_closes(root):
    async def scenario(world, panel, show):
        pid, _ = await a_job(world, ("status", "balancing the mix"))
        press = await show()
        await press(ENTER + "k")
        asked = panel.tab.title, drawn(panel)[-1]
        await press(ESC)                                 # drops the question, and no more
        dropped = panel.tab.title, drawn(panel)[-1][:16], world.row(pid)["state"]
        await press("k" + "y")
        await world.ended(pid)
        killed = (await seen_on(panel, lambda rows: "killed" in rows[2]))[2]
        await press(ESC)
        back = panel.tab.title, panel.is_open
        await press(ESC)
        return asked, dropped, killed, back, panel.is_open

    asked, dropped, killed, back, still_open = watching(root, scenario)
    assert asked == ("Details", " kill 30001? y/n")
    assert dropped == ("Details", " ← → other agent", "running")
    assert killed == " 30001 · music · composer · killed · 0:00 · 900 tok · ~$0.07"
    assert back == ("Agents", True) and still_open is False


def test_what_a_job_says_is_drawn_without_its_escape_codes(root):
    async def scenario(world, panel, show):
        pid, _ = await a_job(world, ("status", "mix\x1b[31m red ␛[2J now"))
        world.jobs._live[pid].says("Done.\x1b[2J\x07 All of it.")
        press = await show()
        row = drawn(panel)[3]
        await press(ENTER)
        return row, drawn(panel)[5:7]

    row, lines = watching(root, scenario)
    assert row.endswith("·  mix red now")
    assert lines == ["  0:00  status  mix red now", "  0:00  says    Done. All of it."]


def test_without_an_agent_both_tabs_are_grey_and_say_why(root):
    plain = MUSIC.__class__("plain", "A thing.", "the manual", {})

    async def scenario(world, panel, show):
        press = await show()
        await press("a")
        foot = drawn(panel)[-1]
        await press("d")
        return (panel.tab.title, foot, drawn(panel)[-1], drawn(panel)[0],
                style_at(panel, 0, drawn(panel)[0].index("Agents")),
                style_at(panel, 0, drawn(panel)[0].index("Details")))

    tab, foot, again, tab_row, agents_style, details_style = watching(root, scenario,
                                                                     addons=[plain])
    assert tab == "Config" and tab_row.endswith("  Agents     Details   [ Config ]")
    assert foot == again == " no attached addon has an agent"
    assert DIM in agents_style and DIM in details_style


def test_over_a_full_screen_program_a_row_follows_its_job_when_block_mode_draws(root):
    """Over a program the panel is a layer in block mode's app and has none of its own, so
    Panel.invalidate() draws nothing there. Tried on 2026-10-05. The terminal's refresh()
    draws block mode's app then."""
    from test_blockmode import CTRL_F12, on_screen

    from hallux.blockmode import BlockMode
    from hallux.protocol import Form

    async def main():
        world = World(root, THREE)
        panel = Panel([AgentsTab(world.jobs.watch, world.jobs.kill),
                       DetailsTab(world.jobs.watch, world.jobs.kill), StandIn("Config")])
        with create_pipe_input() as pipe:
            block = BlockMode(input=pipe, output=Screen(24, 100))
            block.panel = panel
            try:
                pid, _ = await a_job(world, ("status", "sketching the drums"))
                await block.show("player\ncomposing…\n", Form((), raw=True))
                pipe.send_text(CTRL_F12)
                await asyncio.sleep(0.3)
                before = on_screen(block)
                world.jobs.on_report = panel.invalidate          # the panel alone: nothing
                world.jobs._live[pid].set_status("balancing the mix")
                await asyncio.sleep(0.3)
                not_drawn = on_screen(block)[3]
                world.jobs.on_report = block.invalidate          # as Terminal.refresh() does
                world.jobs._live[pid].tokens_so_far(21340)
                await asyncio.sleep(0.3)
                return before, not_drawn, on_screen(block)[3]
            finally:
                await block.end()

    before, not_drawn, drawn_ = asyncio.run(asyncio.wait_for(main(), 15))
    assert before[0].endswith("[ Agents ]   Details     Config")     # it opened on Agents
    assert before[3].startswith(" 30001  music  composer  running  0:00      0       ·  sketching")
    assert not_drawn == before[3]
    assert drawn_.startswith(" 30001  music  composer  running  0:00    21k       ·  balancing")


def test_done_when_a_job_is_watched_and_killed_in_the_panel_and_the_ai_hears_of_it(tmp_path):
    """The step's "Done when", with the real terminal on a pipe, the machine, the panel as
    app.py builds it, a pretend model and a stand-in worker."""
    from test_agents import StandIn as Worker
    from test_machine import FakeModel, screen
    from test_terminal import CTRL_F12, typed_in, with_terminal

    from hallux.machine import Machine
    from hallux.panel_tabs.config import ConfigTab
    from hallux.statusbar import StatusBar

    model = FakeModel(screen("", prompt="$ "), screen("[1]+  Killed\n", prompt="$ "),
                      screen("logout\n", prompt="", tail="<halt/>"))
    bar = StatusBar("claude-opus-5-5", "low")
    script = (("status", "sketching the drums"), ("wait", asyncio.Event()))

    async def run(terminal, type_keys):
        machine = Machine(tmp_path, ROOMY, terminal, client_factory=model, addons=[MUSIC],
                          worker_factory=lambda job: Worker(job, script))
        panel = Panel([AgentsTab(machine.jobs.watch, machine.jobs.kill),
                       DetailsTab(machine.jobs.watch, machine.jobs.kill),
                       ConfigTab(machine.view, machine.change, machine.save, machine.refill,
                                 agents=True)], bar=bar)
        terminal.set_panel(panel)
        running = asyncio.ensure_future(machine.run())
        type_keys("ls")
        await typed_in(terminal, "ls")
        pid = machine.jobs.spawn(MUSIC, "a song", "/tmp")
        while machine.jobs._live[pid].status != "sketching the drums":
            await asyncio.sleep(0.01)
        type_keys(CTRL_F12)                              # at the prompt, with half a line typed
        while panel.app is None:
            await asyncio.sleep(0.01)
        opened = (await seen_on(panel, lambda rows: "30001" in rows[3]))
        opened = panel.tab.title, opened[3], opened[-1]  # the last row is the bar
        type_keys(ENTER)
        await seen_on(panel, lambda rows: "sketching the drums" in rows[5])
        machine.jobs._live[pid].set_status("balancing the mix")      # a line arrives
        arrived = (await seen_on(panel, lambda rows: "balancing" in rows[6]))[5:7]
        machine.jobs._live[pid].says("The kick is too loud.")        # nothing of the bar's
        said = (await seen_on(panel, lambda rows: "says" in rows[7], 0.6))[7]    # changes: it
        type_keys("k")
        asked = (await seen_on(panel, lambda rows: rows[-2].startswith(" kill")))[-2]
        type_keys("y")
        killed = (await seen_on(panel, lambda rows: "killed" in rows[2]))[2]
        sent_meanwhile = len(model.sessions[0])          # nothing new goes to the AI meanwhile
        type_keys(ESC)
        await seen_on(panel, lambda rows: rows[0].endswith("[ Agents ]   Details     Config"))
        type_keys(ESC)
        await typed_in(terminal, "ls")                   # the line is back at the prompt
        type_keys("\r")
        while len(model.sessions[0]) < 2:
            await asyncio.sleep(0.01)
        type_keys("\x04")
        await running
        return opened, arrived, said, asked, killed, sent_meanwhile

    opened, arrived, said, asked, killed, sent_meanwhile = with_terminal(run, bar=bar)
    assert said[8:] == "says    The kick is too loud."   # at once, not at the next beat
    assert opened[0] == "Agents" and opened[1].startswith(" 30001  music  composer  running")
    assert "music: sketching the drums · 0:0" in opened[2] and "opus 5.5" in opened[2]
    assert [line[8:] for line in arrived] == ["status  sketching the drums",
                                              "status  balancing the mix"]
    assert asked == " kill 30001? y/n" and sent_meanwhile == 1
    assert killed.startswith(" 30001 · music · composer · killed · 0:0")
    _, ls, _ = model.sessions[0]                         # the next message starts with it
    assert ls.startswith('<events>\n<event addon="music">{"event": "job", "pid": 30001, '
                         '"agent": "composer", "state": "killed", "why": "kill", "written": 0')
    assert ls.endswith(">ls</input>")
