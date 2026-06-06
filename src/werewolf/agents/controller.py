"""AgentController: assemble prompt -> call LLM -> parse + validate -> fallback."""
from __future__ import annotations

import random

from werewolf.agents.memory import AgentMemory
from werewolf.agents.prompts import build_system_prompt, build_user_prompt
from werewolf.engine.types import ActionType, Role
from werewolf.llm.base import AgentResponse, LLMClient, PublicActionModel
from werewolf.llm.ollama_client import parse_agent_response

_LEGAL_INSTRUCTIONS = {
    ActionType.SPEAK: "Speak to the group. Set type='speak' and put your statement in 'content'.",
    ActionType.VOTE: (
        "Vote to eliminate ONE living player. Set type='vote' and 'target' to: {targets}."
    ),
    ActionType.NIGHT_KILL: (
        "Choose ONE player to eliminate tonight. type='night_kill', target one of: {targets}."
    ),
    ActionType.INVESTIGATE: (
        "Choose ONE player to investigate. type='investigate', target one of: {targets}."
    ),
    ActionType.PROTECT: (
        "Choose ONE player to protect tonight. type='protect', target one of: {targets}."
    ),
}


class AgentController:
    def __init__(
        self,
        name: str,
        role: Role,
        llm: LLMClient,
        memory: AgentMemory,
        num_players: int,
        max_retries: int = 2,
        rng: random.Random | None = None,
    ) -> None:
        self.name = name
        self.role = role
        self.llm = llm
        self.memory = memory
        self.max_retries = max_retries
        self.rng = rng or random.Random()
        self.system = build_system_prompt(name, role, num_players)

    async def act(
        self,
        phase_label: str,
        living: list[str],
        transcript: str,
        action_type: ActionType,
        legal_targets: list[str],
    ) -> AgentResponse:
        instruction = _LEGAL_INSTRUCTIONS[action_type].format(targets=", ".join(legal_targets))
        user = build_user_prompt(
            phase_label=phase_label,
            living=living,
            memory=self.memory.render(),
            transcript=transcript,
            legal_instruction=instruction,
        )
        for _ in range(self.max_retries + 1):
            try:
                raw = await self.llm.complete_json(self.system, user)
                resp = parse_agent_response(raw)
            except Exception:
                # A bad generation (ParseError) OR a timeout/transport failure must
                # never crash the game — retry, then fall back to a random legal move
                # below. CancelledError is a BaseException, so it still propagates.
                continue
            if self._is_valid(resp, action_type, legal_targets):
                return resp
        return self._fallback(action_type, legal_targets)

    def _is_valid(
        self, resp: AgentResponse, action_type: ActionType, legal_targets: list[str]
    ) -> bool:
        action = resp.public_action
        if action.type != action_type:
            return False
        if action_type == ActionType.SPEAK:
            return bool(action.content)
        return action.target in legal_targets

    def _fallback(self, action_type: ActionType, legal_targets: list[str]) -> AgentResponse:
        if action_type == ActionType.SPEAK:
            return AgentResponse(
                private_reasoning="(fallback) model failed to produce valid output",
                public_action=PublicActionModel(type=ActionType.SPEAK, content="I'm not sure yet."),
                fallback=True,
            )
        # abstain (target=None) rather than crash if there is nothing legal to pick
        target = self.rng.choice(legal_targets) if legal_targets else None
        return AgentResponse(
            private_reasoning="(fallback) random legal action",
            public_action=PublicActionModel(type=action_type, target=target),
            fallback=True,
        )
