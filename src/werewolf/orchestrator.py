"""GameRunner: drives the night/day loop and yields GameEvents. Async generator."""
from __future__ import annotations

import random
from collections.abc import AsyncIterator

from werewolf.agents.controller import AgentController
from werewolf.agents.memory import AgentMemory
from werewolf.engine.engine import GameEngine
from werewolf.engine.setup import new_game
from werewolf.engine.types import ActionType, Phase, Role
from werewolf.events import GameEvent
from werewolf.llm.base import LLMClient


class GameRunner:
    def __init__(
        self,
        names: list[str],
        llm: LLMClient,
        rng: random.Random,
        discussion_rounds: int = 2,
        max_days: int = 20,
    ) -> None:
        self.engine = GameEngine(new_game(names, rng=rng), rng=rng)
        self.rng = rng
        self.discussion_rounds = discussion_rounds
        self.max_days = max_days
        self.agents: dict[str, AgentController] = {
            p.name: AgentController(p.name, p.role, llm, AgentMemory(), rng=rng)
            for p in self.engine.state.players
        }
        # seed each agent's memory with its own role
        for p in self.engine.state.players:
            self.agents[p.name].memory.add(f"You are the {p.role.value}.")
        # werewolves know each other
        wolves = [p.name for p in self.engine.state.players if p.role == Role.WEREWOLF]
        for w in wolves:
            others = [o for o in wolves if o != w]
            self.agents[w].memory.add(f"Your fellow werewolf is: {', '.join(others)}.")

    def _transcript_text(self) -> str:
        return "\n".join(
            f"{e.speaker}: {e.text}"
            for e in self.engine.state.transcript
            if e.phase == Phase.DAY
        )

    async def _ask(
        self, name: str, action: ActionType
    ) -> tuple[str | None, str, str | None]:
        """Returns (target, private_reasoning, content) for the agent's chosen action."""
        ctrl = self.agents[name]
        targets = self.engine.legal_targets(name, action)
        resp = await ctrl.act(
            phase_label=f"{self.engine.state.phase.value.title()} {self.engine.state.day}",
            living=self.engine.state.living_names(),
            transcript=self._transcript_text(),
            action_type=action,
            legal_targets=targets,
        )
        return resp.public_action.target, resp.private_reasoning, resp.public_action.content

    async def run(self) -> AsyncIterator[GameEvent]:
        state = self.engine.state
        # announce the roster first so the UI can build itself around these players
        yield GameEvent(kind="setup", day=state.day, data={"players": state.living_names()})
        while state.winner is None and state.day <= self.max_days:
            # ---------- NIGHT ----------
            yield GameEvent(kind="phase", day=state.day, text="night")
            kill: str | None = None
            protect: str | None = None
            investigate: str | None = None
            for name in list(state.living_names()):
                role = state.by_name(name).role
                if role == Role.WEREWOLF and kill is None:
                    yield self._thinking(name)
                    kill, reasoning, _ = await self._ask(name, ActionType.NIGHT_KILL)
                    yield GameEvent(kind="reasoning", day=state.day, actor=name, text=reasoning)
                elif role == Role.SEER:
                    yield self._thinking(name)
                    investigate, reasoning, _ = await self._ask(name, ActionType.INVESTIGATE)
                    yield GameEvent(kind="reasoning", day=state.day, actor=name, text=reasoning)
                    if investigate is not None:
                        is_wolf = self.engine.investigate(investigate)
                        verdict = "IS a werewolf" if is_wolf else "is NOT a werewolf"
                        self.agents[name].memory.add(
                            f"Night {state.day}: you investigated {investigate} -> {verdict}."
                        )
                elif role == Role.DOCTOR:
                    yield self._thinking(name)
                    protect, reasoning, _ = await self._ask(name, ActionType.PROTECT)
                    yield GameEvent(kind="reasoning", day=state.day, actor=name, text=reasoning)
            died = self.engine.resolve_night(kill, protect, investigate)
            if died is not None:
                role_name = state.by_name(died).role.value
                yield GameEvent(
                    kind="death",
                    day=state.day,
                    actor=died,
                    text=f"{died} ({role_name}) was killed in the night.",
                )
                self._broadcast(f"{died} was found dead. They were a {role_name}.")
            if state.winner is not None:
                break

            # ---------- DAY: discussion ----------
            yield GameEvent(kind="phase", day=state.day, text="day")
            for _ in range(self.discussion_rounds):
                for name in list(state.living_names()):
                    yield self._thinking(name)
                    _, reasoning, content = await self._ask(name, ActionType.SPEAK)
                    yield GameEvent(kind="reasoning", day=state.day, actor=name, text=reasoning)
                    text = content or "..."
                    self.engine.record(name, text)
                    self.agents[name].memory.add(f"Day {state.day}: you said '{text}'.")
                    yield GameEvent(kind="speak", day=state.day, actor=name, text=text)

            # ---------- DAY: vote ----------
            votes: dict[str, str] = {}
            for name in list(state.living_names()):
                yield self._thinking(name)
                target, reasoning, _ = await self._ask(name, ActionType.VOTE)
                yield GameEvent(kind="reasoning", day=state.day, actor=name, text=reasoning)
                if target is not None:
                    votes[name] = target
                    yield GameEvent(kind="vote", day=state.day, actor=name, text=target)
            eliminated = self.engine.tally_votes(votes)
            if eliminated is not None:
                role_name = state.by_name(eliminated).role.value
                self.engine.eliminate(eliminated)
                yield GameEvent(
                    kind="death",
                    day=state.day,
                    actor=eliminated,
                    text=f"{eliminated} was voted out. They were a {role_name}.",
                )
                self._broadcast(f"{eliminated} was voted out. They were a {role_name}.")
            else:
                yield GameEvent(kind="phase", day=state.day, text="no_elimination")

            self.engine.start_next_night()

        winner = state.winner.value if state.winner else "none"
        yield GameEvent(
            kind="result", day=state.day, text=f"{winner} wins", data={"winner": winner}
        )

    def _thinking(self, name: str) -> GameEvent:
        """Signal that an agent is deciding — emitted right before its LLM call."""
        return GameEvent(kind="thinking", day=self.engine.state.day, actor=name)

    def _broadcast(self, note: str) -> None:
        """Add a public fact to every living agent's memory."""
        for name in self.engine.state.living_names():
            self.agents[name].memory.add(note)
