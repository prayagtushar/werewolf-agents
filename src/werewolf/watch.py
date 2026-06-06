"""Play ONE AI Werewolf game and stream it to the terminal — no browser, no build.

    uv run python -m werewolf.watch                 # balanced-9, random cast
    uv run python -m werewolf.watch --seed 7        # reproducible game (great for a GIF)
    uv run python -m werewolf.watch --preset classic-7

Each agent's private reasoning (🔒) prints right next to its public statement (💬),
so the deception is visible in a plain terminal recording.
"""
from __future__ import annotations

import argparse
import asyncio
import random

from werewolf.engine.setup import DEFAULT_PRESET, PRESETS
from werewolf.events import GameEvent
from werewolf.llm.ollama_client import OllamaClient
from werewolf.names import pick_names
from werewolf.orchestrator import GameRunner


def format_event(ev: GameEvent) -> str | None:
    """Render a single game event as a terminal line, or None to print nothing."""
    if ev.kind == "setup":
        players = ", ".join(ev.data.get("players", []))
        return f"\nCast: {players}"
    if ev.kind == "phase":
        if ev.text == "no_elimination":
            return "   ⚖  a tie — no one was eliminated"
        return f"\n{'═' * 8} {str(ev.text).upper()} {ev.day} {'═' * 8}"
    if ev.kind == "reasoning":
        return f"   🔒 {ev.actor} (private): {ev.text}"
    if ev.kind == "speak":
        return f"   💬 {ev.actor}: {ev.text}"
    if ev.kind == "vote":
        return f"   🗳  {ev.actor} → {ev.text}"
    if ev.kind == "save":
        return f"   ✚  {ev.text}"
    if ev.kind == "death":
        return f"   💀 {ev.text}"
    if ev.kind == "result":
        decisions = ev.data.get("decisions", 0)
        fallbacks = ev.data.get("fallbacks", 0)
        tail = f"   ({decisions} decisions, {fallbacks} fallbacks)" if decisions else ""
        return f"\n🏆 {ev.text}{tail}"
    # "thinking" and anything else is terminal noise — skip it
    return None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Play one AI Werewolf game in the terminal.")
    parser.add_argument("--preset", choices=list(PRESETS), default=DEFAULT_PRESET)
    parser.add_argument("--seed", type=int, default=None, help="fix the RNG for a reproducible game")
    args = parser.parse_args()

    preset = PRESETS[args.preset]
    rng = random.Random(args.seed)
    runner = GameRunner(
        names=pick_names(rng, preset.size),
        llm=OllamaClient(),
        rng=rng,
        discussion_rounds=2,
        roles=preset.roles,
        first_night_kill=preset.first_night_kill,
    )
    print(f"AI Werewolf — {preset.label}")
    async for ev in runner.run():
        line = format_event(ev)
        if line is not None:
            print(line, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
