# 🐺 werewolf-agents

**A multi-agent social-deduction game where LLM agents lie, deduce, and vote each other out — running 100% on-device for $0.**

[![CI](https://github.com/prayagtushar/werewolf-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/prayagtushar/werewolf-agents/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![mypy: strict](https://img.shields.io/badge/mypy-strict-blue)

> **Status:** ✅ v1 runs end-to-end. Built task-by-task (TDD) per the [implementation plan](docs/superpowers/plans/ai-werewolf-implementation-plan.md); a full game (7–9 players) plays locally on Ollama, streamed live to a dashboard or the terminal. 65 tests green · ruff + mypy strict clean.

---

## Highlights

- Multi-agent social-deduction game: 7 or 9 LLM agents across 4 roles (werewolf, seer, doctor, villager).
- **Dual-channel output** per turn — `private_reasoning` vs `public_action` (JSON-schema-constrained Pydantic) — so model intent vs behavior is fully observable.
- **The werewolf pack coordinates**: every wolf acts at night, sees its packmates' picks in private memory, and the kill is the pack's majority vote (ties broken fairly).
- **Deterministic game engine fully separated from the LLM**: malformed output *or a model timeout/transport error* is re-prompted, then falls back to a random legal move — so a bad or slow model never crashes a game.
- AsyncIO orchestrator streaming `GameEvent`s over **WebSocket** to a live dashboard; per-agent memory across turns.
- **Eval harness**: win-rate, voting accuracy, deception proxy, doctor-save rate, first-blood, and the model's **fallback / valid-output rate** over batch runs; 65 tests, mypy-strict.
- Runs at **$0 on local Ollama** (`qwen2.5:3b`); 3 balanced presets selectable via env var.

---

## The jaw-drop

The dashboard shows each agent's **private reasoning** right next to its **public statement**.

You watch a werewolf *think* — *"The Seer is onto me, I'll loudly accuse Dan to redirect the room"* — and then *say* something calm and reasonable. Then you watch the village vote out the wrong person.

That side-by-side — secret intent vs. spoken word — is the whole point.

> **Demo clip:** _add a GIF/MP4 here._ Run the dashboard (below), play a game, and screen-record a moment where a werewolf's amber **Intercepted** reasoning reveals a cover story (flagged `⚠ COVER STORY`, linked by a red thread to its calm public statement) while the town's votes climb on an innocent. Save it under `demo/`.

---

## Why this exists

A portfolio piece demonstrating the things that actually matter for building agentic systems:

- **Multi-agent orchestration** — a deterministic engine drives N LLM agents through a night/day loop.
- **Structured LLM output** — every turn is Pydantic-validated JSON (`private_reasoning` + `public_action`).
- **Prompt engineering for role-play & deception** — theory-of-mind and coalition behavior emerge from prompt structure alone.
- **Local inference / cost engineering** — runs fully on-device via Ollama at **$0/game**.
- **Evals & observability** — every game is logged; win-rate, deception success, and voting accuracy are tracked over many games.
- **Real-time streaming UI** — FastAPI + WebSocket streaming to a zero-build dashboard.

## The game

Classic Werewolf / Mafia, all-AI, with a **random cast each game** and a **configurable, balanced roster**:

| Count | Role | Knows | Night action | Village team? |
|------:|------|-------|--------------|:-------------:|
| 2 | **Werewolf** | each other | collectively kill 1 victim | ✗ |
| 1 | **Seer** | only self | investigate 1 player → werewolf or not | ✓ |
| 1 | **Doctor** | only self | protect 1 player from the kill | ✓ |
| n | **Villager** | only self | — | ✓ |

**Loop:** Night (wolves kill, seer investigates, doctor protects) → Dawn (reveal the death) → Day (2 discussion rounds, then a vote; ties = no elimination) → check win → repeat.

**Win:** Werewolves win the instant `#wolves ≥ #non-wolves`. The village wins the instant all wolves are dead.

**Balance presets** (`src/werewolf/engine/setup.py`), selected via `WEREWOLF_PRESET`:
`classic-7` (2 wolves on 5 — wolf-favored), **`balanced-9`** (2 wolves on 7 — the default; fairer and longer), and `merciful-7` (7 players, *no first-night kill* so the town deduces before anyone dies). Because the only way to kill a wolf is a day vote and wolves win at parity, the 7-player classic is genuinely wolf-sided — hence the fairer default.

## Architecture

**Core principle: the Game Engine is the single source of truth and contains ZERO LLM code.** Agents only *propose* actions; the engine validates and applies them. A dumb model can never crash or cheat the game.

```
engine/        pure, deterministic rules — state, roles, phases, resolution, win check (no I/O, no LLM)
llm/           async Ollama client — JSON-schema-constrained output, real timeouts, retries
agents/        agent controller (the "brain"), prompt templates, per-agent memory
orchestrator   the conductor: ask engine whose turn → prompt agents → validate vs legal moves → apply → emit events
server/        FastAPI + WebSocket live event stream
web/           static dashboard (HTML + Tailwind CDN + vanilla JS) — public chat + private-reasoning panels
evals/         JSONL game logging + win-rate / deception / voting-accuracy analytics
```

Bad model output — **or a model timeout / transport failure** — never crashes the game: it's re-prompted, then falls back to a random *legal* action (counted as a fallback for the eval metrics). All randomness flows through one seeded RNG, so games are reproducible for tests and demos.

## Run it

```bash
ollama pull qwen2.5:3b          # one-time, ~2GB
uv sync
uv run uvicorn werewolf.server.app:app --port 8000
# open http://localhost:8000 and click "Start game"
```

Prefer the terminal? Watch one game stream as text — each agent's private reasoning
printed right beside its public statement:

```bash
uv run python -m werewolf.watch --seed 7      # reproducible; --preset picks the roster
```

## Benchmark

```bash
uv run python -m werewolf.evals.run_batch -n 10 --preset balanced-9
```

Plays N headless games (no UI; `--preset` matches the live server's `WEREWOLF_PRESET`) and
writes each to `data/games.jsonl`, then prints a summary: win-rate by team, average game
length, **voting accuracy** (share of day-votes that ejected an actual werewolf), a
**deception proxy** (how often the town was fooled into lynching an innocent),
**doctor-save rate**, **first-blood**, and the model's **fallback / valid-output rate**
(how often a generation was unusable and had to fall back). The voting/deception figures
are honest proxies, not ground-truth measures of intent.

## Tests

```bash
uv run pytest -q && uv run ruff check src tests && uv run mypy src
```

All tests are offline — the LLM is mocked/scripted, so no Ollama is needed to run the suite.

## Tech stack

Python 3.12 · [uv](https://docs.astral.sh/uv/) · FastAPI + WebSockets · Pydantic v2 · [Ollama](https://ollama.com/) (`qwen2.5:3b`, configurable) · pytest · ruff · mypy. Frontend: static HTML + Tailwind (CDN) + vanilla JS — no build step.

## Roadmap

**v1 (in progress):** full 7-player local game · live private-vs-public dashboard · engine/agent/orchestrator/eval tests green · eval report over ≥10 games · demo clip.

**Deferred to v2:** human-player mode · configurable player counts/roles · extra roles (Hunter, Witch) · vector memory · multi-model (different model per agent) · tournament / Elo.

## Design docs

- [Design spec](docs/superpowers/specs/2026-05-29-ai-werewolf-design.md)
- [Implementation plan](docs/superpowers/plans/ai-werewolf-implementation-plan.md)
