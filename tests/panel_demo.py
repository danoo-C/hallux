"""The panel by itself, in your own terminal:

    .venv/bin/python tests/panel_demo.py

Nothing in Hallux opens its panel before step 6 of the plan (docs/plans/config-panel). This
shows it around a machine that is switched off, in a folder that is thrown away. The rows
change that machine's settings, Save writes a real config.toml, and when the panel closes the
file and the machine's log are printed. No model is called, and nothing here costs anything.
"""
import asyncio
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hallux.config import CONFIG_FILE, Hardware  # noqa: E402
from hallux.machine import Machine  # noqa: E402
from hallux.panel import Panel  # noqa: E402
from hallux.panel_tabs.config import ConfigTab  # noqa: E402
from hallux.statusbar import StatusBar  # noqa: E402


class Bar:
    """What the machine takes for its terminal here: only the status bar is real."""

    status_bar = True

    def __init__(self, bar: StatusBar) -> None:
        self.bar, self.panel = bar, None

    def set_status(self, **changes: object) -> None:
        self.bar.update(**changes)
        if self.panel is not None:
            self.panel.invalidate()


async def show(root: Path, input=None, output=None) -> None:
    hardware = Hardware(max_budget_usd=2.0)
    bar = StatusBar(hardware.model, hardware.model_effort)
    terminal = Bar(bar)
    machine = Machine(root, hardware, terminal, from_flags=["effort"])
    # As if a boot had spent $1.42, and a program on screen had used up its ticks.
    machine.session_spent = machine.spent = 1.42
    machine.event_spent = 0.10
    machine.in_form, machine.tick_spent = True, 0.25
    machine.note("tick_budget_usd", "live updates paused: tick budget used")
    bar.update(cost=machine.spent, seconds=0.8)
    tab = ConfigTab(machine.view, machine.change, machine.save, machine.refill)
    terminal.panel = panel = Panel([tab], bar=bar)
    await panel.run(input, output)


def main() -> None:
    lines: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: lines.append(record.getMessage())
    logging.getLogger("hallux").addHandler(handler)
    logging.getLogger("hallux").setLevel(logging.INFO)
    with tempfile.TemporaryDirectory(prefix="hallux-panel-demo-") as folder:
        root = Path(folder) / "demo-world"
        root.mkdir()
        asyncio.run(show(root))
        saved = root / CONFIG_FILE
        print("config.toml, as Save wrote it:" if saved.exists() else "Nothing was saved.")
        if saved.exists():
            print("".join(f"    {line}" for line in saved.read_text().splitlines(keepends=True)))
    print("The machine's log:" if lines else "The machine logged nothing.")
    for line in lines:
        print(f"    {line}")


if __name__ == "__main__":
    main()
