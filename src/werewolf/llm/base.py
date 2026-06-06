"""LLM abstraction. AgentResponse is the structured contract every agent turn returns."""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from werewolf.engine.types import ActionType


class PublicActionModel(BaseModel):
    type: ActionType
    content: str | None = None
    target: str | None = None


class AgentResponse(BaseModel):
    private_reasoning: str = Field(..., description="Hidden true strategy")
    public_action: PublicActionModel
    # True only for controller-synthesized fallbacks (model produced nothing usable).
    # Never set by the model; lets the eval harness measure model-failure rate.
    fallback: bool = False


class LLMClient(Protocol):
    async def complete_json(self, system: str, user: str) -> str:
        """Return raw model text expected to be JSON."""
        ...
