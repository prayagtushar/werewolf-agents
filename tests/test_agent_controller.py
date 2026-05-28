import random

from werewolf.agents.controller import AgentController
from werewolf.agents.memory import AgentMemory
from werewolf.engine.types import ActionType, Role


class FakeLLM:
    """Returns a queued response; records the prompts it was given."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._responses.pop(0)


async def test_controller_returns_valid_action_within_legal_targets():
    llm = FakeLLM(
        ['{"private_reasoning": "vote the wolf", "public_action": {"type": "vote", "target": "B"}}']
    )
    ctrl = AgentController(name="A", role=Role.VILLAGER, llm=llm, memory=AgentMemory())
    resp = await ctrl.act(
        phase_label="Day 1",
        living=["A", "B", "C"],
        transcript="",
        action_type=ActionType.VOTE,
        legal_targets=["B", "C"],
    )
    assert resp.public_action.type == ActionType.VOTE
    assert resp.public_action.target == "B"


async def test_controller_retries_then_falls_back_on_illegal_target():
    # First response targets a dead/illegal player; fallback must pick a legal target.
    llm = FakeLLM(
        [
            '{"private_reasoning": "x", "public_action": {"type": "vote", "target": "ZZZ"}}',
            '{"private_reasoning": "x", "public_action": {"type": "vote", "target": "ZZZ"}}',
            '{"private_reasoning": "x", "public_action": {"type": "vote", "target": "ZZZ"}}',
        ]
    )
    ctrl = AgentController(
        name="A",
        role=Role.VILLAGER,
        llm=llm,
        memory=AgentMemory(),
        max_retries=2,
        rng=random.Random(0),
    )
    resp = await ctrl.act(
        phase_label="Day 1",
        living=["A", "B", "C"],
        transcript="",
        action_type=ActionType.VOTE,
        legal_targets=["B", "C"],
    )
    assert resp.public_action.target in {"B", "C"}  # fell back to a legal target


async def test_controller_falls_back_on_unparseable_output():
    llm = FakeLLM(["garbage", "still garbage", "more garbage"])
    ctrl = AgentController(
        name="A",
        role=Role.VILLAGER,
        llm=llm,
        memory=AgentMemory(),
        max_retries=2,
        rng=random.Random(0),
    )
    resp = await ctrl.act(
        phase_label="Day 1",
        living=["A", "B", "C"],
        transcript="",
        action_type=ActionType.VOTE,
        legal_targets=["B", "C"],
    )
    assert resp.public_action.target in {"B", "C"}
