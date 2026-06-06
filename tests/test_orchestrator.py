import random

from werewolf.engine.setup import BALANCED_9
from werewolf.engine.types import Role
from werewolf.orchestrator import GameRunner


class ScriptedLLM:
    """Deterministic agent brain: acts on the first legal target, says a fixed line.

    Action type is detected from the exact ``type='...'`` token in the legal-action
    instruction line — NOT bare words, which can leak in from agent memory (e.g. the
    Seer's "you investigated X" note would otherwise misroute a speak turn).
    """

    async def complete_json(self, system: str, user: str) -> str:
        for action in ("night_kill", "investigate", "protect", "vote"):
            if f"type='{action}'" in user:
                target = _first_target(user)
                return (
                    f'{{"private_reasoning":"r","public_action":'
                    f'{{"type":"{action}","target":"{target}"}}}}'
                )
        return '{"private_reasoning":"r","public_action":{"type":"speak","content":"hello"}}'


def _first_target(user: str) -> str:
    # night actions render targets as "one of: A, B, C."; vote uses "'target' to: A, B, C."
    for marker in ("one of: ", "'target' to: "):
        if marker in user:
            tail = user.split(marker, 1)[1]
            return tail.split(",")[0].split(".")[0].strip()
    raise AssertionError(f"no target marker found in instruction: {user!r}")


def _legal_targets(user: str) -> list[str]:
    for marker in ("one of: ", "'target' to: "):
        if marker in user:
            chunk = user.split(marker, 1)[1].split(".", 1)[0]
            return [t.strip() for t in chunk.split(",")]
    return []


class FixedTargetLLM:
    """Every targeted action aims at ``self.victim`` when legal, else the first
    legal target. Lets a test force the doctor and wolves onto the same player."""

    victim: str | None = None

    async def complete_json(self, system: str, user: str) -> str:
        for action in ("night_kill", "investigate", "protect", "vote"):
            if f"type='{action}'" in user:
                targets = _legal_targets(user)
                target = self.victim if self.victim in targets else targets[0]
                return (
                    f'{{"private_reasoning":"r","public_action":'
                    f'{{"type":"{action}","target":"{target}"}}}}'
                )
        return '{"private_reasoning":"r","public_action":{"type":"speak","content":"hello"}}'


async def test_save_event_emitted_when_doctor_protects_the_kill_target():
    llm = FixedTargetLLM()
    runner = GameRunner(
        names=["A", "B", "C", "D", "E", "F", "G"],
        llm=llm,
        rng=random.Random(7),
        discussion_rounds=1,
        max_days=1,
    )
    # a villager can be targeted by both wolves and protected by the doctor
    llm.victim = next(p.name for p in runner.engine.state.players if p.role == Role.VILLAGER)
    events = [e async for e in runner.run()]
    assert any(e.kind == "save" for e in events)
    # and the protected villager survived night 1
    night1_deaths = [
        e for e in events if e.kind == "death" and e.day == 1 and "night" in (e.text or "")
    ]
    assert night1_deaths == []


async def test_full_game_runs_to_a_winner():
    runner = GameRunner(
        names=["A", "B", "C", "D", "E", "F", "G"],
        llm=ScriptedLLM(),
        rng=random.Random(7),
        discussion_rounds=1,
        max_days=20,
    )
    events = [e async for e in runner.run()]
    results = [e for e in events if e.kind == "result"]
    assert len(results) == 1
    assert results[0].data["winner"] in {"village", "werewolf"}
    # reasoning events are emitted (the private-vs-public feature)
    assert any(e.kind == "reasoning" for e in events)


async def test_both_werewolves_act_during_the_night():
    # Regression: previously only the first wolf in turn-order ever decided the
    # kill; the pack's second wolf never got a night turn. Both must now act.
    runner = GameRunner(
        names=["A", "B", "C", "D", "E", "F", "G"],
        llm=ScriptedLLM(),
        rng=random.Random(7),
        discussion_rounds=1,
    )
    wolves = {p.name for p in runner.engine.state.players if p.role == Role.WEREWOLF}
    assert len(wolves) == 2  # sanity: classic-7 has two wolves

    events = [e async for e in runner.run()]
    phase: str | None = None
    night1_reasoners: set[str] = set()
    for e in events:
        if e.kind == "phase":
            phase = e.text
        elif e.kind == "reasoning" and phase == "night" and e.day == 1:
            night1_reasoners.add(e.actor or "")
    assert wolves <= night1_reasoners  # BOTH wolves reasoned on night 1


async def test_packmate_kill_choice_is_shared_with_the_other_wolf():
    # Coordination: after a wolf proposes a victim, the rest of the pack must be
    # able to see it (it lands in their private memory) before the night resolves.
    runner = GameRunner(
        names=["A", "B", "C", "D", "E", "F", "G"],
        llm=ScriptedLLM(),
        rng=random.Random(7),
        discussion_rounds=1,
    )
    wolves = [p.name for p in runner.engine.state.players if p.role == Role.WEREWOLF]
    _ = [e async for e in runner.run()]
    pack_notes = [
        note
        for w in wolves
        for note in runner.agents[w].memory.notes
        if "packmate" in note or "pack" in note
    ]
    assert pack_notes  # the wolves coordinated through shared memory


async def test_result_day_never_exceeds_max_days():
    # Regression: hitting the day cap without a winner used to report max_days + 1
    # (a day that was never played), inflating avg_days in the eval harness.
    runner = GameRunner(
        names=["A", "B", "C", "D", "E", "F", "G"],
        llm=ScriptedLLM(),
        rng=random.Random(7),
        discussion_rounds=1,
        max_days=1,
    )
    events = [e async for e in runner.run()]
    result = next(e for e in events if e.kind == "result")
    assert result.day <= 1


async def test_result_event_reports_decision_and_fallback_counts():
    runner = GameRunner(
        names=["A", "B", "C", "D", "E", "F", "G"],
        llm=ScriptedLLM(),
        rng=random.Random(7),
        discussion_rounds=1,
    )
    events = [e async for e in runner.run()]
    result = next(e for e in events if e.kind == "result")
    assert result.data["decisions"] > 0
    assert result.data["fallbacks"] == 0  # ScriptedLLM always returns valid output


async def test_no_first_night_kill_spares_everyone_night_one():
    runner = GameRunner(
        names=[f"P{i}" for i in range(9)],
        llm=ScriptedLLM(),
        rng=random.Random(3),
        discussion_rounds=1,
        roles=BALANCED_9,
        first_night_kill=False,
    )
    events = [e async for e in runner.run()]
    # with the lever off, nobody dies in the night on day 1
    night1_deaths = [
        e for e in events if e.kind == "death" and e.day == 1 and "night" in (e.text or "")
    ]
    assert night1_deaths == []
    assert any(e.kind == "result" for e in events)
