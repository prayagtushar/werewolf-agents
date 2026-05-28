"""Per-agent private memory: an ordered list of plain-text observations."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentMemory:
    notes: list[str] = field(default_factory=list)

    def add(self, note: str) -> None:
        self.notes.append(note)

    def render(self) -> str:
        return "\n".join(f"- {n}" for n in self.notes)
