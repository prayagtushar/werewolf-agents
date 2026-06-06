"""Run N games headless (no UI) and print summary stats. Used for the résumé numbers."""
from __future__ import annotations

import argparse
import asyncio
import random
import re
from pathlib import Path

from werewolf.engine.setup import DEFAULT_PRESET, PRESETS, Preset
from werewolf.evals.analytics import summarize
from werewolf.evals.logging import GameRecord, append_record, load_records
from werewolf.llm.base import LLMClient
from werewolf.llm.ollama_client import OllamaClient
from werewolf.names import pick_names
from werewolf.orchestrator import GameRunner

_ROLE_RE = re.compile(r"(werewolf|seer|doctor|villager)", re.IGNORECASE)


def _role(text: str | None) -> str | None:
    m = _ROLE_RE.search(text or "")
    return m.group(1).lower() if m else None


async def play_one(
    seed: int,
    log_path: Path,
    preset: Preset = PRESETS[DEFAULT_PRESET],
    llm: LLMClient | None = None,
) -> GameRecord:
    rng = random.Random(seed)
    runner = GameRunner(
        names=pick_names(rng, preset.size),
        llm=llm or OllamaClient(),
        rng=rng,
        discussion_rounds=2,
        roles=preset.roles,
        first_night_kill=preset.first_night_kill,
    )
    winner, days = "none", 0
    decisions, fallbacks = 0, 0
    eliminated: list[str] = []
    day_votes: list[str] = []
    saves = 0
    async for ev in runner.run():
        if ev.kind == "death":
            role = _role(ev.text)
            if role:
                eliminated.append(role)
                if "voted out" in (ev.text or ""):
                    day_votes.append(role)
        elif ev.kind == "save":
            saves += 1
        elif ev.kind == "result":
            winner, days = ev.data["winner"], ev.day
            decisions = int(ev.data.get("decisions", 0))
            fallbacks = int(ev.data.get("fallbacks", 0))
    record = GameRecord(
        winner=winner,
        days=days,
        eliminated_roles=eliminated,
        day_vote_roles=day_votes,
        decisions=decisions,
        fallbacks=fallbacks,
        saves=saves,
    )
    append_record(record, log_path)
    return record


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run N headless AI Werewolf games.")
    parser.add_argument("-n", "--games", type=int, default=10)
    parser.add_argument("--log", type=Path, default=Path("data/games.jsonl"))
    parser.add_argument(
        "--preset",
        choices=list(PRESETS),
        default=DEFAULT_PRESET,
        help="balance preset to benchmark (matches the live server's WEREWOLF_PRESET)",
    )
    args = parser.parse_args()
    preset = PRESETS[args.preset]
    print(f"preset: {preset.label} ({preset.size} players)")
    for i in range(args.games):
        rec = await play_one(seed=i, log_path=args.log, preset=preset)
        print(f"played game {i + 1}/{args.games}: {rec.winner} in {rec.days} days")
    print(summarize(load_records(args.log)))


if __name__ == "__main__":
    asyncio.run(main())
