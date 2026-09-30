"""The machine's hardware: which Claude model runs it, and at what effort.

Layers, later ones win: the defaults below < <root>/.hallux/config.toml < command-line flags.
No tool reaches config.toml, so the machine can't pick its own hardware.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path

EFFORTS = ("low", "medium", "high", "xhigh", "max")
CONFIG_FILE = Path(".hallux") / "config.toml"


@dataclass(frozen=True)
class Hardware:
    model: str = "claude-opus-5-5"
    effort: str | None = "low"
    fallback_model: str | None = None
    max_budget_usd: float | None = None       # spending cap per boot
    status_bar: bool = True                   # hallux's own bottom row: activity, model, cost

    @property
    def model_effort(self) -> str | None:
        """The effort to send: Haiku 4.5 has no effort levels, so it gets none."""
        return None if "haiku" in self.model else self.effort


def load(root: Path, **flags: object) -> Hardware:
    """Read the hardware for the machine in `root`. Raises ValueError with a readable message."""
    hardware = Hardware()
    path = Path(root) / CONFIG_FILE
    if path.exists():
        try:
            settings = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"{path}: {e}") from None
        known = {f.name for f in fields(Hardware)}
        if unknown := sorted(set(settings) - known):
            raise ValueError(f"{path}: unknown setting {', '.join(unknown)} "
                             f"(known: {', '.join(sorted(known))})")
        hardware = replace(hardware, **settings)
    hardware = replace(hardware, **{k: v for k, v in flags.items() if v is not None})
    _validate(hardware, path)
    return hardware


def _validate(hw: Hardware, path: Path) -> None:
    if not isinstance(hw.model, str) or not hw.model:
        raise ValueError(f"{path}: model must be a model name like claude-opus-5-5")
    if hw.effort is not None and hw.effort not in EFFORTS:
        raise ValueError(f"{path}: effort must be one of {', '.join(EFFORTS)}, not {hw.effort!r}")
    if hw.fallback_model is not None and not isinstance(hw.fallback_model, str):
        raise ValueError(f"{path}: fallback_model must be a model name")
    if not isinstance(hw.status_bar, bool):
        raise ValueError(f"{path}: status_bar must be true or false")
    budget = hw.max_budget_usd
    if budget is not None and (isinstance(budget, bool) or not isinstance(budget, int | float)
                               or budget <= 0):
        raise ValueError(f"{path}: max_budget_usd must be a positive number")
