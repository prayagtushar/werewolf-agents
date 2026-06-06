"""A shared pool of distinct, single-token player names + a sampler.

Single-token and non-overlapping (no name is a substring of another) so the UI's
name-mention graph and the eval role parsing stay unambiguous. Used by both the
live server and the headless benchmark so they cast games from the same source.
"""
from __future__ import annotations

import random

NAME_POOL: list[str] = [
    "Ava", "Ben", "Cleo", "Dax", "Eve", "Finn", "Greta", "Hugo", "Iris", "Jonas",
    "Kira", "Liam", "Mira", "Noor", "Otis", "Petra", "Quinn", "Rosa", "Soren", "Talia",
    "Uma", "Viktor", "Wren", "Xander", "Yara", "Zane",
]


def pick_names(rng: random.Random, count: int) -> list[str]:
    """Distinct random names so the cast looks different every game."""
    if count > len(NAME_POOL):
        raise ValueError(f"need {count} names but the pool has only {len(NAME_POOL)}")
    return rng.sample(NAME_POOL, count)
