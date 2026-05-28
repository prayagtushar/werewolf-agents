from werewolf.evals.analytics import summarize
from werewolf.evals.logging import GameRecord


def test_summarize_computes_win_rates():
    records = [
        GameRecord(winner="village", days=3, eliminated_roles=["werewolf", "villager"]),
        GameRecord(winner="werewolf", days=4, eliminated_roles=["villager", "seer"]),
        GameRecord(winner="village", days=2, eliminated_roles=["werewolf", "werewolf"]),
    ]
    summary = summarize(records)
    assert summary["games"] == 3
    assert abs(summary["village_win_rate"] - 2 / 3) < 1e-9
    assert abs(summary["werewolf_win_rate"] - 1 / 3) < 1e-9
    assert summary["avg_days"] == (3 + 4 + 2) / 3


def test_summarize_empty():
    summary = summarize([])
    assert summary["games"] == 0
    assert summary["village_win_rate"] == 0.0
    assert summary["village_voting_accuracy"] == 0.0
    assert summary["deception_proxy"] == 0.0


def test_summarize_voting_accuracy_and_deception_proxy():
    records = [
        # 4 day-vote eliminations total; 1 hit a werewolf -> 25% accuracy
        GameRecord(winner="werewolf", days=3, day_vote_roles=["villager", "seer"]),
        GameRecord(winner="village", days=4, day_vote_roles=["werewolf", "villager"]),
    ]
    summary = summarize(records)
    assert abs(summary["village_voting_accuracy"] - 0.25) < 1e-9
    assert abs(summary["deception_proxy"] - 0.75) < 1e-9


def test_voting_accuracy_zero_when_no_day_votes():
    records = [GameRecord(winner="village", days=2, eliminated_roles=["werewolf"])]
    summary = summarize(records)
    assert summary["village_voting_accuracy"] == 0.0
    assert summary["deception_proxy"] == 0.0
