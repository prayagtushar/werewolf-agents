"""Append-only JSONL game logging."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class GameRecord(BaseModel):
    winner: str
    days: int
    eliminated_roles: list[str] = Field(default_factory=list)  # all deaths (night + day vote)
    day_vote_roles: list[str] = Field(default_factory=list)  # roles removed by the DAY vote only
    decisions: int = 0  # total agent decisions this game
    fallbacks: int = 0  # decisions where the model produced nothing usable
    saves: int = 0  # nights the doctor's protect blocked the wolves' kill


def append_record(record: GameRecord, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def load_records(path: Path) -> list[GameRecord]:
    if not path.exists():
        return []
    return [
        GameRecord.model_validate_json(line) for line in path.read_text().splitlines() if line
    ]
