import asyncio
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


class RaisingLLM:
    """Always raises — simulates a timed-out or unreachable model server."""

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def complete_json(self, system: str, user: str) -> str:
        self.calls += 1
        raise self.exc


async def test_controller_falls_back_when_llm_call_raises():
    # A timeout/transport error from the model must NOT crash the turn:
    # the controller retries, then returns a legal fallback action.
    llm = RaisingLLM(asyncio.TimeoutError())
    ctrl = AgentController(
        name="A",
        role=Role.VILLAGER,
        llm=llm,
        memory=AgentMemory(),
        num_players=3,
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
    assert resp.public_action.target in {"B", "C"}  # fell back, did not propagate
    assert llm.calls == 3  # tried (max_retries + 1) times before falling back


async def test_controller_returns_valid_action_within_legal_targets():
    llm = FakeLLM(
        ['{"private_reasoning": "vote the wolf", "public_action": {"type": "vote", "target": "B"}}']
    )
    ctrl = AgentController(
        name="A", role=Role.VILLAGER, llm=llm, memory=AgentMemory(), num_players=3
    )
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
        num_players=3,
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


async def test_fallback_response_is_flagged_as_fallback():
    # When the model never produces usable output, the synthesized fallback must
    # be marked so the eval harness can measure how often the model failed.
    llm = FakeLLM(["garbage", "garbage", "garbage"])
    ctrl = AgentController(
        name="A",
        role=Role.VILLAGER,
        llm=llm,
        memory=AgentMemory(),
        num_players=3,
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
    assert resp.fallback is True


async def test_fallback_with_no_legal_targets_does_not_crash():
    # The fallback path exists so a turn never crashes — it must also survive the
    # degenerate case of zero legal targets (abstain instead of raising IndexError).
    llm = FakeLLM(["garbage", "garbage", "garbage"])
    ctrl = AgentController(
        name="A",
        role=Role.VILLAGER,
        llm=llm,
        memory=AgentMemory(),
        num_players=3,
        max_retries=2,
        rng=random.Random(0),
    )
    resp = await ctrl.act(
        phase_label="Day 1",
        living=["A"],
        transcript="",
        action_type=ActionType.VOTE,
        legal_targets=[],
    )
    assert resp.public_action.target is None
    assert resp.fallback is True


async def test_valid_response_is_not_flagged_as_fallback():
    llm = FakeLLM(
        ['{"private_reasoning": "ok", "public_action": {"type": "vote", "target": "B"}}']
    )
    ctrl = AgentController(
        name="A", role=Role.VILLAGER, llm=llm, memory=AgentMemory(), num_players=3
    )
    resp = await ctrl.act(
        phase_label="Day 1",
        living=["A", "B", "C"],
        transcript="",
        action_type=ActionType.VOTE,
        legal_targets=["B", "C"],
    )
    assert resp.fallback is False


async def test_controller_falls_back_on_unparseable_output():
    llm = FakeLLM(["garbage", "still garbage", "more garbage"])
    ctrl = AgentController(
        name="A",
        role=Role.VILLAGER,
        llm=llm,
        memory=AgentMemory(),
        num_players=3,
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
