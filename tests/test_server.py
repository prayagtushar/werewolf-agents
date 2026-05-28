"""Offline coverage for the FastAPI server: index served + a full game streamed
over the WebSocket, with the Ollama client swapped for a deterministic scripted brain."""
from fastapi.testclient import TestClient

from werewolf.server import app as server_app


class _Scripted:
    """Deterministic agent brain: acts on the first legal target, says a fixed line."""

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
    for marker in ("one of: ", "'target' to: "):
        if marker in user:
            tail = user.split(marker, 1)[1]
            return tail.split(",")[0].split(".")[0].strip()
    raise AssertionError(f"no target marker in: {user!r}")


def test_index_is_served():
    client = TestClient(server_app.app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "AI Werewolf" in resp.text


def test_ws_streams_a_full_game(monkeypatch):
    monkeypatch.setattr(server_app, "OllamaClient", lambda *a, **k: _Scripted())
    client = TestClient(server_app.app)
    events: list[dict] = []
    with client.websocket_connect("/ws/game") as ws:
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["kind"] == "result":
                assert ev["data"]["winner"] in {"village", "werewolf"}
                break
    kinds = [e["kind"] for e in events]
    assert "reasoning" in kinds
    assert "speak" in kinds
    assert "thinking" in kinds


def test_thinking_precedes_each_reasoning(monkeypatch):
    """The dashboard's 'thinking' indicator relies on a thinking event for an actor
    immediately preceding that actor's reasoning."""
    monkeypatch.setattr(server_app, "OllamaClient", lambda *a, **k: _Scripted())
    client = TestClient(server_app.app)
    events: list[dict] = []
    with client.websocket_connect("/ws/game") as ws:
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["kind"] == "result":
                break
    for i, ev in enumerate(events):
        if ev["kind"] == "reasoning":
            prev = events[i - 1]
            assert prev["kind"] == "thinking" and prev["actor"] == ev["actor"]
