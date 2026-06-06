import random

from werewolf.engine.engine import GameEngine
from werewolf.engine.setup import new_game
from werewolf.engine.types import ActionType, Phase, Role


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


def test_pack_kill_picks_majority_target():
    eng = _engine()
    assert eng.resolve_pack_kill({"A": "C", "B": "C", "D": "E"}) == "C"


def test_pack_kill_single_wolf_kills_their_target():
    eng = _engine()
    assert eng.resolve_pack_kill({"A": "C"}) == "C"


def test_pack_kill_breaks_tie_so_pack_always_strikes():
    eng = _engine()  # seeded rng
    result = eng.resolve_pack_kill({"A": "C", "B": "E"})
    assert result in {"C", "E"}  # a definite victim, never a no-op tie


def test_pack_kill_empty_returns_none():
    eng = _engine()
    assert eng.resolve_pack_kill({}) is None


def test_was_saved_true_when_doctor_protects_the_kill_target():
    eng = _engine()
    assert eng.was_saved("C", "C") is True


def test_was_saved_false_when_no_kill():
    eng = _engine()
    assert eng.was_saved(None, "C") is False


def test_was_saved_false_when_protect_misses():
    eng = _engine()
    assert eng.was_saved("C", "D") is False


def test_night_kill_targets_exclude_fellow_werewolves():
    # The pack must never be able to kill its own — a wolf's legal kill targets
    # are the living non-wolves only.
    eng = _engine()
    wolves = {w.name for w in eng.state.living_werewolves()}
    actor = next(iter(wolves))
    targets = eng.legal_targets(actor, ActionType.NIGHT_KILL)
    assert wolves.isdisjoint(targets)
    assert len(targets) > 0
