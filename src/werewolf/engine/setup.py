"""Create a fresh game with a configurable, shuffled role assignment.

The role composition is configurable so the game can be rebalanced without code
changes. ``PRESETS`` bundles a composition with a rule lever (``first_night_kill``)
for quick selection; ``new_game`` accepts any explicit ``roles`` list.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from werewolf.engine.types import GameState, Phase, Player, Role

# 7-player classic: 2 wolves on 5 villagers. Wolf-favored (wolves reach parity fast).
CLASSIC_7: list[Role] = [
    Role.WEREWOLF,
    Role.WEREWOLF,
    Role.SEER,
    Role.DOCTOR,
    Role.VILLAGER,
    Role.VILLAGER,
    Role.VILLAGER,
]

# 9-player balanced: 2 wolves on 7 villagers (~22% wolves). Fairer + longer games.
BALANCED_9: list[Role] = CLASSIC_7 + [Role.VILLAGER, Role.VILLAGER]

# Back-compat alias used across older tests/callers.
DEFAULT_ROLES: list[Role] = CLASSIC_7


@dataclass(frozen=True)
class Preset:
    """A named, rebalanced game configuration."""

    label: str
    roles: list[Role]
    # When False, no one dies on the first night — the town gets a full day to
    # deduce before losing a player (a classic village-favoring rule lever).
    first_night_kill: bool = True

    @property
    def size(self) -> int:
        return len(self.roles)


PRESETS: dict[str, Preset] = {
    "classic-7": Preset("Classic · 7 (wolf-favored)", CLASSIC_7, first_night_kill=True),
    "balanced-9": Preset("Balanced · 9 players", BALANCED_9, first_night_kill=True),
    "merciful-7": Preset("Mercy · 7, no first-night kill", CLASSIC_7, first_night_kill=False),
}

DEFAULT_PRESET = "balanced-9"


def new_game(
    names: list[str],
    rng: random.Random,
    roles: list[Role] | None = None,
) -> GameState:
    """Create a game. ``roles`` defaults to the classic 7 composition; its length
    must match ``names``."""
    roles = list(roles if roles is not None else DEFAULT_ROLES)
    if len(names) != len(roles):
        raise ValueError(f"expected {len(roles)} players for this role set, got {len(names)}")
    rng.shuffle(roles)
    players = [Player(name=n, role=r) for n, r in zip(names, roles)]
    return GameState(players=players, phase=Phase.NIGHT, day=1)
