import random

from werewolf.engine.setup import DEFAULT_ROLES, new_game
from werewolf.engine.types import Phase, Role


def test_new_game_assigns_all_roles():
    names = ["A", "B", "C", "D", "E", "F", "G"]
    state = new_game(names, rng=random.Random(0))
    roles = sorted(p.role for p in state.players)
    assert roles == sorted(DEFAULT_ROLES)
    assert len(state.players) == 7
    assert all(p.alive for p in state.players)
    assert state.phase == Phase.NIGHT
    assert state.day == 1


def test_new_game_has_two_werewolves():
    names = ["A", "B", "C", "D", "E", "F", "G"]
    state = new_game(names, rng=random.Random(0))
    assert sum(1 for p in state.players if p.role == Role.WEREWOLF) == 2


def test_new_game_is_seeded_deterministic():
    names = ["A", "B", "C", "D", "E", "F", "G"]
    s1 = new_game(names, rng=random.Random(42))
    s2 = new_game(names, rng=random.Random(42))
    assert [(p.name, p.role) for p in s1.players] == [(p.name, p.role) for p in s2.players]


def test_new_game_rejects_wrong_player_count():
    import pytest

    with pytest.raises(ValueError):
        new_game(["A", "B"], rng=random.Random(0))
