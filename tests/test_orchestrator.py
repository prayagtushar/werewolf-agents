import random

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
