"""Create a fresh game with shuffled role assignment."""
from __future__ import annotations

import random

from werewolf.engine.types import GameState, Phase, Player, Role

DEFAULT_ROLES: list[Role] = [
    Role.WEREWOLF,
    Role.WEREWOLF,
    Role.SEER,
    Role.DOCTOR,
    Role.VILLAGER,
    Role.VILLAGER,
    Role.VILLAGER,
]


def new_game(names: list[str], rng: random.Random) -> GameState:
    if len(names) != len(DEFAULT_ROLES):
        raise ValueError(f"expected {len(DEFAULT_ROLES)} players, got {len(names)}")
    roles = DEFAULT_ROLES.copy()
    rng.shuffle(roles)
    players = [Player(name=n, role=r) for n, r in zip(names, roles)]
    return GameState(players=players, phase=Phase.NIGHT, day=1)
