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
            "fallback_rate": 0.0,
            "valid_output_rate": 1.0,
            "avg_saves": 0.0,
            "first_blood_wolf_rate": 0.0,
        }
    village = sum(1 for r in records if r.winner == "village")
    wolf = sum(1 for r in records if r.winner == "werewolf")

    day_votes = [role for rec in records for role in rec.day_vote_roles]
    if day_votes:
        wolf_hits = sum(1 for role in day_votes if role == "werewolf")
        accuracy = wolf_hits / len(day_votes)
    else:
        accuracy = 0.0

    total_decisions = sum(r.decisions for r in records)
    total_fallbacks = sum(r.fallbacks for r in records)
    fallback_rate = (total_fallbacks / total_decisions) if total_decisions else 0.0

    first_deaths = [r.eliminated_roles[0] for r in records if r.eliminated_roles]
    first_blood_wolf_rate = (
        sum(1 for d in first_deaths if d == "werewolf") / len(first_deaths)
        if first_deaths
        else 0.0
    )

    return {
        "games": n,
        "village_win_rate": village / n,
        "werewolf_win_rate": wolf / n,
        "avg_days": sum(r.days for r in records) / n,
        "village_voting_accuracy": accuracy,
        "deception_proxy": (1.0 - accuracy) if day_votes else 0.0,
        "fallback_rate": fallback_rate,
        "valid_output_rate": 1.0 - fallback_rate,
        "avg_saves": sum(r.saves for r in records) / n,
        "first_blood_wolf_rate": first_blood_wolf_rate,
    }
