"""GameEngine: the authoritative, deterministic rules. No LLM code lives here."""
from __future__ import annotations

import random
from collections import Counter

from werewolf.engine.types import (
    ActionType,
    GameState,
    Phase,
    Role,
    Team,
    TranscriptEntry,
)


class GameEngine:
    def __init__(self, state: GameState, rng: random.Random) -> None:
        self.state = state
        self.rng = rng

    # ---- night ----
    def resolve_night(
        self,
        kill_target: str | None,
        protect_target: str | None,
        investigate_target: str | None,
    ) -> str | None:
        """Apply night actions. Returns the name of who died, or None. Advances to DAY."""
        died: str | None = None
        if kill_target is not None and kill_target != protect_target:
            victim = self.state.by_name(kill_target)
            if victim.alive:
                victim.alive = False
                died = victim.name
        # investigate has no state mutation; the Seer's result is delivered via investigate()
        self.state.phase = Phase.DAY
        self._check_winner()
        return died

    def investigate(self, target: str) -> bool:
        """Seer query: True if target is a werewolf."""
        return self.state.by_name(target).role == Role.WEREWOLF

    # ---- day ----
    def tally_votes(self, votes: dict[str, str]) -> str | None:
        """votes maps voter_name -> target_name. Returns eliminated name, or None on tie/empty."""
        if not votes:
            return None
        counts = Counter(votes.values())
        top = counts.most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            return None  # tie -> no elimination
        return top[0][0]

    def eliminate(self, name: str) -> None:
        self.state.by_name(name).alive = False
        self._check_winner()

    def start_next_night(self) -> None:
        if self.state.winner is None:
            self.state.day += 1
            self.state.phase = Phase.NIGHT

    # ---- transcript ----
    def record(self, speaker: str, text: str) -> None:
        self.state.transcript.append(
            TranscriptEntry(
                day=self.state.day, phase=self.state.phase, speaker=speaker, text=text
            )
        )

    # ---- win check ----
    def _check_winner(self) -> None:
        wolves = len(self.state.living_werewolves())
        non_wolves = len(self.state.living()) - wolves
        if wolves == 0:
            self.state.winner = Team.VILLAGE
            self.state.phase = Phase.GAME_OVER
        elif wolves >= non_wolves:
            self.state.winner = Team.WEREWOLF
            self.state.phase = Phase.GAME_OVER

    # ---- legal actions ----
    def legal_targets(self, actor: str, action: ActionType) -> list[str]:
        """Valid targets for a given action by a given actor."""
        living = self.state.living_names()
        if action in (ActionType.VOTE, ActionType.NIGHT_KILL, ActionType.INVESTIGATE):
            return [n for n in living if n != actor]
        if action == ActionType.PROTECT:
            return living  # doctor may protect self
        return []
