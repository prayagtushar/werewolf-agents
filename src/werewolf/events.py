"""GameEvent: the unit streamed to the UI and written to logs."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GameEvent(BaseModel):
    kind: str  # "phase" | "thinking" | "reasoning" | "speak" | "vote" | "death" | "result"
    day: int
    actor: str | None = None
    text: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
