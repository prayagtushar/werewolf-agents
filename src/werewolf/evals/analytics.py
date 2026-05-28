"""Aggregate game records into headline stats for the résumé / dashboard.

Note on honesty: ``village_voting_accuracy`` and ``deception_proxy`` are *proxies*.
Accuracy = share of day-vote eliminations that removed an actual werewolf. The
deception proxy is its complement: how often the town was fooled into lynching an
innocent (village-team) player. Neither is a ground-truth measure of intent.
"""
from __future__ import annotations

from werewolf.evals.logging import GameRecord


def summarize(records: list[GameRecord]) -> dict[str, float | int]:
    n = len(records)
    if n == 0:
        return {
            "games": 0,
            "village_win_rate": 0.0,
            "werewolf_win_rate": 0.0,
            "avg_days": 0.0,
            "village_voting_accuracy": 0.0,
            "deception_proxy": 0.0,
        }
    village = sum(1 for r in records if r.winner == "village")
    wolf = sum(1 for r in records if r.winner == "werewolf")

    day_votes = [role for rec in records for role in rec.day_vote_roles]
    if day_votes:
        wolf_hits = sum(1 for role in day_votes if role == "werewolf")
        accuracy = wolf_hits / len(day_votes)
    else:
        accuracy = 0.0

    return {
        "games": n,
        "village_win_rate": village / n,
        "werewolf_win_rate": wolf / n,
        "avg_days": sum(r.days for r in records) / n,
        "village_voting_accuracy": accuracy,
        "deception_proxy": (1.0 - accuracy) if day_votes else 0.0,
    }
