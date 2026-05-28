"""FastAPI app: serve the dashboard and stream a live game over WebSocket."""
from __future__ import annotations

import random
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from werewolf.llm.ollama_client import OllamaClient
from werewolf.orchestrator import GameRunner

# src/werewolf/server/app.py -> parents[3] is the repo root, where web/ lives.
WEB_DIR = Path(__file__).resolve().parents[3] / "web"

app = FastAPI(title="AI Werewolf")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

DEFAULT_NAMES = ["Ava", "Ben", "Cleo", "Dan", "Eve", "Finn", "Gwen"]


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.websocket("/ws/game")
async def game_ws(ws: WebSocket) -> None:
    await ws.accept()
    runner = GameRunner(
        names=DEFAULT_NAMES,
        llm=OllamaClient(),
        rng=random.Random(),
        discussion_rounds=2,
    )
    try:
        async for event in runner.run():
            await ws.send_json(event.model_dump())
    except WebSocketDisconnect:
        return
