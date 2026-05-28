"""Run N games headless (no UI) and print summary stats. Used for the résumé numbers."""
from __future__ import annotations

import argparse
import asyncio
import random
import re
from pathlib import Path

from werewolf.evals.analytics import summarize
from werewolf.evals.logging import GameRecord, append_record, load_records
from werewolf.llm.ollama_client import OllamaClient
from werewolf.orchestrator import GameRunner

NAMES = ["Ava", "Ben", "Cleo", "Dan", "Eve", "Finn", "Gwen"]
_ROLE_RE = re.compile(r"(werewolf|seer|doctor|villager)", re.IGNORECASE)


def _role(text: str | None) -> str | None:
    m = _ROLE_RE.search(text or "")
    return m.group(1).lower() if m else None


async def play_one(seed: int, log_path: Path) -> GameRecord:
    runner = GameRunner(
        names=NAMES, llm=OllamaClient(), rng=random.Random(seed), discussion_rounds=2
    )
    winner, days = "none", 0
    eliminated: list[str] = []
    day_votes: list[str] = []
    async for ev in runner.run():
        if ev.kind == "death":
            role = _role(ev.text)
            if role:
                eliminated.append(role)
                if "voted out" in (ev.text or ""):
                    day_votes.append(role)
        elif ev.kind == "result":
            winner, days = ev.data["winner"], ev.day
    record = GameRecord(
        winner=winner, days=days, eliminated_roles=eliminated, day_vote_roles=day_votes
    )
    append_record(record, log_path)
    return record


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run N headless AI Werewolf games.")
    parser.add_argument("-n", "--games", type=int, default=10)
    parser.add_argument("--log", type=Path, default=Path("data/games.jsonl"))
    args = parser.parse_args()
    for i in range(args.games):
        rec = await play_one(seed=i, log_path=args.log)
        print(f"played game {i + 1}/{args.games}: {rec.winner} in {rec.days} days")
    print(summarize(load_records(args.log)))


if __name__ == "__main__":
    asyncio.run(main())
