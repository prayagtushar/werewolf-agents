# Demo assets

Drop the demo clip (`werewolf.gif` / `werewolf.mp4`) here and reference it from the
top-level `README.md`.

## Capturing a clip

**Option A — the live dashboard (best visual):**

```bash
ollama pull qwen2.5:3b
uv sync
uv run uvicorn werewolf.server.app:app --port 8000
# open http://localhost:8000, click "Start game", screen-record a moment where a
# werewolf's amber "Intercepted" reasoning (⚠ cover story) is linked by the red
# thread to its calm public statement while the town votes out an innocent.
```

**Option B — the terminal (smallest file, easy to GIF):**

```bash
uv run python -m werewolf.watch --seed 7
```

Each agent's private reasoning (🔒) prints next to its public line (💬). `--seed`
makes the game reproducible so you can re-record the same moment. Capture with
[`vhs`](https://github.com/charmbracelet/vhs), `asciinema`, or any screen recorder.

Keep the file small (≤ ~5 MB) so it loads inline on GitHub.
