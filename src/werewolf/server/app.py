"""FastAPI app: serve the dashboard and stream a live game over WebSocket."""
from __future__ import annotations

import random
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import os

from werewolf.engine.setup import DEFAULT_PRESET, PRESETS
from werewolf.llm.ollama_client import OllamaClient
from werewolf.orchestrator import GameRunner

# Pick the balance preset from the environment (default: the fairer 'balanced-9').
ACTIVE_PRESET = PRESETS.get(os.environ.get("WEREWOLF_PRESET", DEFAULT_PRESET), PRESETS[DEFAULT_PRESET])

# src/werewolf/server/app.py -> parents[3] is the repo root, where web/ lives.
WEB_DIR = Path(__file__).resolve().parents[3] / "web"

app = FastAPI(title="AI Werewolf")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

# A pool of distinct, single-token names so each game has a fresh, non-repeating cast.
# Kept single-token (no substrings of one another) so the UI's name-mention graph stays clean.
NAME_POOL = [
    "Ava", "Ben", "Cleo", "Dax", "Eve", "Finn", "Greta", "Hugo", "Iris", "Jonas",
    "Kira", "Liam", "Mira", "Noor", "Otis", "Petra", "Quinn", "Rosa", "Soren", "Talia",
    "Uma", "Viktor", "Wren", "Xander", "Yara", "Zane",
]
def pick_names(rng: random.Random, count: int) -> list[str]:
    """Distinct random names so the cast looks different every game."""
    return rng.sample(NAME_POOL, count)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.websocket("/ws/game")
async def game_ws(ws: WebSocket) -> None:
    await ws.accept()
    rng = random.Random()
    runner = GameRunner(
        names=pick_names(rng, ACTIVE_PRESET.size),
        llm=OllamaClient(),
        rng=rng,
        discussion_rounds=2,
        roles=ACTIVE_PRESET.roles,
        first_night_kill=ACTIVE_PRESET.first_night_kill,
    )
    try:
        async for event in runner.run():
            await ws.send_json(event.model_dump())
    except WebSocketDisconnect:
        return
