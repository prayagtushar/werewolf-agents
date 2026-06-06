from pathlib import Path

from werewolf.engine.setup import PRESETS
from werewolf.evals.run_batch import play_one


class ScriptedLLM:
    """Acts on the first legal target; says a fixed line. No Ollama needed."""

    async def complete_json(self, system: str, user: str) -> str:
        for action in ("night_kill", "investigate", "protect", "vote"):
            if f"type='{action}'" in user:
                for marker in ("one of: ", "'target' to: "):
                    if marker in user:
                        target = user.split(marker, 1)[1].split(",")[0].split(".")[0].strip()
                        return (
                            f'{{"private_reasoning":"r","public_action":'
                            f'{{"type":"{action}","target":"{target}"}}}}'
                        )
        return '{"private_reasoning":"r","public_action":{"type":"speak","content":"hi"}}'


async def test_play_one_uses_the_preset_roster_and_records_a_game(tmp_path: Path):
    preset = PRESETS["balanced-9"]  # 9 players, not the old hardcoded 7
    rec = await play_one(
        seed=1, log_path=tmp_path / "games.jsonl", preset=preset, llm=ScriptedLLM()
    )
    assert rec.winner in {"village", "werewolf", "none"}
    assert rec.days > 0
    assert rec.decisions > 0  # the observability counters were captured
