"""Core value types for the Werewolf engine. Pure data, no logic, no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    WEREWOLF = "werewolf"
    SEER = "seer"
    DOCTOR = "doctor"
    VILLAGER = "villager"


class Team(str, Enum):
    VILLAGE = "village"
    WEREWOLF = "werewolf"


class Phase(str, Enum):
    NIGHT = "night"
    DAY = "day"
    GAME_OVER = "game_over"


class ActionType(str, Enum):
    SPEAK = "speak"
    VOTE = "vote"
    NIGHT_KILL = "night_kill"
    INVESTIGATE = "investigate"
    PROTECT = "protect"


ROLE_TEAM: dict[Role, Team] = {
    Role.WEREWOLF: Team.WEREWOLF,
    Role.SEER: Team.VILLAGE,
    Role.DOCTOR: Team.VILLAGE,
    Role.VILLAGER: Team.VILLAGE,
}


@dataclass
class Player:
    name: str
    role: Role
    alive: bool = True

    @property
    def team(self) -> Team:
        return ROLE_TEAM[self.role]


@dataclass
class PublicAction:
    """What an agent does in the open (or its chosen night action)."""

    type: ActionType
    content: str | None = None  # used for SPEAK
    target: str | None = None  # player name for VOTE / night actions


@dataclass
class TranscriptEntry:
    day: int
    phase: Phase
    speaker: str
    text: str


@dataclass
class GameState:
    players: list[Player]
    phase: Phase = Phase.NIGHT
    day: int = 1
    transcript: list[TranscriptEntry] = field(default_factory=list)
    winner: Team | None = None

    def by_name(self, name: str) -> Player:
        for p in self.players:
            if p.name == name:
                return p
        raise KeyError(name)

    def living(self) -> list[Player]:
        return [p for p in self.players if p.alive]

    def living_names(self) -> list[str]:
        return [p.name for p in self.living()]

    def living_werewolves(self) -> list[Player]:
        return [p for p in self.living() if p.role == Role.WEREWOLF]
