import random

from werewolf.engine.engine import GameEngine
from werewolf.engine.setup import new_game
from werewolf.engine.types import GameState, Phase, Player, Role, Team


def _engine() -> GameEngine:
    state = new_game(["A", "B", "C", "D", "E", "F", "G"], rng=random.Random(2))
    return GameEngine(state, rng=random.Random(2))


def test_tally_picks_majority():
    eng = _engine()
    votes = {"A": "C", "B": "C", "D": "E"}
    assert eng.tally_votes(votes) == "C"


def test_tally_tie_returns_none():
    eng = _engine()
    votes = {"A": "C", "B": "D"}
    assert eng.tally_votes(votes) is None


def test_village_wins_when_all_wolves_dead():
    players = [
        Player("A", Role.WEREWOLF, alive=False),
        Player("B", Role.WEREWOLF, alive=False),
        Player("C", Role.VILLAGER),
        Player("D", Role.SEER),
    ]
    eng = GameEngine(GameState(players=players), rng=random.Random(0))
    eng._check_winner()
    assert eng.state.winner == Team.VILLAGE
    assert eng.state.phase == Phase.GAME_OVER


def test_wolves_win_when_they_reach_parity():
    players = [
        Player("A", Role.WEREWOLF),
        Player("B", Role.WEREWOLF),
        Player("C", Role.VILLAGER, alive=False),
        Player("D", Role.VILLAGER),
        Player("E", Role.VILLAGER, alive=False),
    ]
    eng = GameEngine(GameState(players=players), rng=random.Random(0))
    eng._check_winner()  # 2 wolves vs 1 non-wolf -> wolves win
    assert eng.state.winner == Team.WEREWOLF
