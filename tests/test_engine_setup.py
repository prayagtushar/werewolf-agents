import random

import pytest

from werewolf.engine.setup import BALANCED_9, DEFAULT_ROLES, PRESETS, new_game
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
    with pytest.raises(ValueError):
        new_game(["A", "B"], rng=random.Random(0))


def test_new_game_accepts_custom_roles():
    names = [f"P{i}" for i in range(9)]
    state = new_game(names, rng=random.Random(0), roles=BALANCED_9)
    assert len(state.players) == 9
    assert sum(1 for p in state.players if p.role == Role.WEREWOLF) == 2
    assert sorted(p.role for p in state.players) == sorted(BALANCED_9)


def test_new_game_roles_length_must_match_names():
    with pytest.raises(ValueError):
        new_game(["A", "B", "C"], rng=random.Random(0), roles=BALANCED_9)


def test_presets_are_well_formed():
    assert PRESETS["balanced-9"].size == 9
    assert sum(1 for r in PRESETS["balanced-9"].roles if r == Role.WEREWOLF) == 2
    assert PRESETS["classic-7"].size == 7
    assert PRESETS["merciful-7"].first_night_kill is False
    assert PRESETS["classic-7"].first_night_kill is True
