import random

from werewolf.engine.engine import GameEngine
from werewolf.engine.setup import new_game
from werewolf.engine.types import Phase, Role


def _engine() -> GameEngine:
    state = new_game(["A", "B", "C", "D", "E", "F", "G"], rng=random.Random(1))
    return GameEngine(state, rng=random.Random(1))


def test_resolve_night_kills_unprotected_target():
    eng = _engine()
    victim = "C"
    died = eng.resolve_night(kill_target=victim, protect_target=None, investigate_target=None)
    assert died == victim
    assert eng.state.by_name(victim).alive is False
    assert eng.state.phase == Phase.DAY


def test_resolve_night_protected_target_survives():
    eng = _engine()
    died = eng.resolve_night(kill_target="C", protect_target="C", investigate_target=None)
    assert died is None
    assert eng.state.by_name("C").alive is True


def test_investigate_returns_true_for_werewolf():
    eng = _engine()
    wolf = eng.state.living_werewolves()[0].name
    result = eng.investigate(wolf)
    assert result is True


def test_investigate_returns_false_for_villager():
    eng = _engine()
    villager = next(p for p in eng.state.players if p.role == Role.VILLAGER)
    assert eng.investigate(villager.name) is False
