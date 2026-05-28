# AI Werewolf Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-agent social-deduction game (Werewolf/Mafia) where LLM agents lie, deduce, and vote each other out, running 100% locally via Ollama, with a live web dashboard showing each agent's private reasoning vs. public statement.

**Architecture:** A pure, deterministic Game Engine is the single source of truth (zero LLM code). An Orchestrator drives the night/day loop, asking an Agent Controller (LLM-backed) for actions, validating every action against the engine's legal moves. A FastAPI + WebSocket server streams game events to a static HTML/JS dashboard. An eval module logs every game and computes stats.

**Tech Stack:** Python 3.12, uv, Pydantic v2, Ollama (`qwen2.5:3b`), FastAPI + WebSockets, pytest, ruff, mypy. Frontend: static HTML + Tailwind (CDN) + vanilla JS.

**Spec:** `docs/superpowers/specs/2026-05-29-ai-werewolf-design.md`

---

## File Structure

```
02-projects/project-3-ai-werewolf/
├── pyproject.toml
├── README.md
├── src/werewolf/
│   ├── __init__.py
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── types.py        # enums + dataclasses (Role, Phase, Player, actions, GameState)
│   │   ├── setup.py        # role assignment / new game
│   │   └── engine.py       # GameEngine: legal actions, night resolution, voting, win check
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py         # LLMClient protocol + AgentResponse model
│   │   └── ollama_client.py# Ollama-backed client with retries + structured output
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── memory.py       # per-agent observation log
│   │   ├── prompts.py      # system + per-turn prompt templates, role briefings
│   │   └── controller.py   # AgentController: build prompt -> call LLM -> parse
│   ├── orchestrator.py     # GameRunner: the night/day loop, emits events
│   ├── events.py           # GameEvent model (what gets streamed to UI / logs)
│   ├── server/
│   │   ├── __init__.py
│   │   └── app.py          # FastAPI app + WebSocket
│   └── evals/
│       ├── __init__.py
│       ├── logging.py      # append game to JSONL
│       └── analytics.py    # compute win-rate / deception / voting accuracy
├── web/
│   ├── index.html
│   └── app.js
└── tests/
    ├── __init__.py
    ├── test_engine_setup.py
    ├── test_engine_night.py
    ├── test_engine_voting.py
    ├── test_llm_client.py
    ├── test_agent_memory.py
    ├── test_agent_controller.py
    ├── test_orchestrator.py
    └── test_evals.py
```

All paths below are relative to `02-projects/project-3-ai-werewolf/`.

---

### Task 0: Project scaffold

**Files:**
- Create: `pyproject.toml`, `src/werewolf/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Create the project directory and init uv**

```bash
mkdir -p 02-projects/project-3-ai-werewolf
cd 02-projects/project-3-ai-werewolf
uv init --name werewolf --lib --python 3.12
```

- [ ] **Step 2: Replace `pyproject.toml` with the full config**

```toml
[project]
name = "werewolf"
version = "0.1.0"
description = "Multi-agent social-deduction game (AI Werewolf), 100% local via Ollama"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.7",
    "ollama>=0.3",
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "websockets>=12",
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "ruff>=0.5", "mypy>=1.10"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 3: Create package dirs and sync**

```bash
mkdir -p src/werewolf/engine src/werewolf/llm src/werewolf/agents src/werewolf/server src/werewolf/evals web tests
touch src/werewolf/__init__.py tests/__init__.py
touch src/werewolf/engine/__init__.py src/werewolf/llm/__init__.py src/werewolf/agents/__init__.py src/werewolf/server/__init__.py src/werewolf/evals/__init__.py
uv sync
```

- [ ] **Step 4: Verify tooling runs**

Run: `uv run pytest -q` (no tests yet)
Expected: `no tests ran` (exit 0 / 5), not an import error.

- [ ] **Step 5: Commit**

```bash
git add 02-projects/project-3-ai-werewolf
git commit -m "chore(werewolf): project scaffold"
```

---

### Task 1: Engine types

**Files:**
- Create: `src/werewolf/engine/types.py`
- Test: `tests/test_engine_setup.py` (in Task 2)

- [ ] **Step 1: Write `src/werewolf/engine/types.py`**

```python
"""Core value types for the Werewolf engine. Pure data, no logic, no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    WEREWOLF = "werewolf"
    SEER = "seer"
    DOCTOR = "doctor"
    VILLAGER = "villager"


class Team(str, Enum):
    VILLAGE = "village"
    WEREWOLF = "werewolf"


class Phase(str, Enum):
    NIGHT = "night"
    DAY = "day"
    GAME_OVER = "game_over"


class ActionType(str, Enum):
    SPEAK = "speak"
    VOTE = "vote"
    NIGHT_KILL = "night_kill"
    INVESTIGATE = "investigate"
    PROTECT = "protect"


ROLE_TEAM: dict[Role, Team] = {
    Role.WEREWOLF: Team.WEREWOLF,
    Role.SEER: Team.VILLAGE,
    Role.DOCTOR: Team.VILLAGE,
    Role.VILLAGER: Team.VILLAGE,
}


@dataclass
class Player:
    name: str
    role: Role
    alive: bool = True

    @property
    def team(self) -> Team:
        return ROLE_TEAM[self.role]


@dataclass
class PublicAction:
    """What an agent does in the open (or its chosen night action)."""
    type: ActionType
    content: str | None = None   # used for SPEAK
    target: str | None = None    # player name for VOTE / night actions


@dataclass
class TranscriptEntry:
    day: int
    phase: Phase
    speaker: str
    text: str


@dataclass
class GameState:
    players: list[Player]
    phase: Phase = Phase.NIGHT
    day: int = 1
    transcript: list[TranscriptEntry] = field(default_factory=list)
    winner: Team | None = None

    def by_name(self, name: str) -> Player:
        for p in self.players:
            if p.name == name:
                return p
        raise KeyError(name)

    def living(self) -> list[Player]:
        return [p for p in self.players if p.alive]

    def living_names(self) -> list[str]:
        return [p.name for p in self.living()]

    def living_werewolves(self) -> list[Player]:
        return [p for p in self.living() if p.role == Role.WEREWOLF]
```

- [ ] **Step 2: Verify it imports**

Run: `uv run python -c "from werewolf.engine.types import GameState, Role; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/werewolf/engine/types.py
git commit -m "feat(engine): core value types"
```

---

### Task 2: Game setup (role assignment)

**Files:**
- Create: `src/werewolf/engine/setup.py`
- Test: `tests/test_engine_setup.py`

- [ ] **Step 1: Write the failing test — `tests/test_engine_setup.py`**

```python
import random

from werewolf.engine.setup import DEFAULT_ROLES, new_game
from werewolf.engine.types import Phase, Role


def test_new_game_assigns_all_roles():
    names = ["A", "B", "C", "D", "E", "F", "G"]
    state = new_game(names, rng=random.Random(0))
    roles = sorted(p.role for p in state.players)
    assert roles == sorted(DEFAULT_ROLES)
    assert len(state.players) == 7
    assert all(p.alive for p in state.players)
    assert state.phase == Phase.NIGHT
    assert state.day == 1


def test_new_game_has_two_werewolves():
    names = ["A", "B", "C", "D", "E", "F", "G"]
    state = new_game(names, rng=random.Random(0))
    assert sum(1 for p in state.players if p.role == Role.WEREWOLF) == 2


def test_new_game_is_seeded_deterministic():
    names = ["A", "B", "C", "D", "E", "F", "G"]
    s1 = new_game(names, rng=random.Random(42))
    s2 = new_game(names, rng=random.Random(42))
    assert [(p.name, p.role) for p in s1.players] == [(p.name, p.role) for p in s2.players]


def test_new_game_rejects_wrong_player_count():
    import pytest
    with pytest.raises(ValueError):
        new_game(["A", "B"], rng=random.Random(0))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_engine_setup.py -q`
Expected: FAIL — `ModuleNotFoundError: werewolf.engine.setup`

- [ ] **Step 3: Write `src/werewolf/engine/setup.py`**

```python
"""Create a fresh game with shuffled role assignment."""
from __future__ import annotations

import random

from werewolf.engine.types import GameState, Player, Phase, Role

DEFAULT_ROLES: list[Role] = [
    Role.WEREWOLF,
    Role.WEREWOLF,
    Role.SEER,
    Role.DOCTOR,
    Role.VILLAGER,
    Role.VILLAGER,
    Role.VILLAGER,
]


def new_game(names: list[str], rng: random.Random) -> GameState:
    if len(names) != len(DEFAULT_ROLES):
        raise ValueError(f"expected {len(DEFAULT_ROLES)} players, got {len(names)}")
    roles = DEFAULT_ROLES.copy()
    rng.shuffle(roles)
    players = [Player(name=n, role=r) for n, r in zip(names, roles)]
    return GameState(players=players, phase=Phase.NIGHT, day=1)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_engine_setup.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/werewolf/engine/setup.py tests/test_engine_setup.py
git commit -m "feat(engine): seeded game setup with role assignment"
```

---

### Task 3: Night resolution

**Files:**
- Create: `src/werewolf/engine/engine.py`
- Test: `tests/test_engine_night.py`

- [ ] **Step 1: Write the failing test — `tests/test_engine_night.py`**

```python
import random

from werewolf.engine.engine import GameEngine
from werewolf.engine.setup import new_game
from werewolf.engine.types import Phase, Role


def _engine() -> GameEngine:
    state = new_game(["A", "B", "C", "D", "E", "F", "G"], rng=random.Random(1))
    return GameEngine(state, rng=random.Random(1))


def test_resolve_night_kills_unprotected_target():
    eng = _engine()
    victim = "C"
    died = eng.resolve_night(kill_target=victim, protect_target=None, investigate_target=None)
    assert died == victim
    assert eng.state.by_name(victim).alive is False
    assert eng.state.phase == Phase.DAY


def test_resolve_night_protected_target_survives():
    eng = _engine()
    died = eng.resolve_night(kill_target="C", protect_target="C", investigate_target=None)
    assert died is None
    assert eng.state.by_name("C").alive is True


def test_investigate_returns_true_for_werewolf():
    eng = _engine()
    wolf = eng.state.living_werewolves()[0].name
    result = eng.investigate(wolf)
    assert result is True


def test_investigate_returns_false_for_villager():
    eng = _engine()
    villager = next(p for p in eng.state.players if p.role == Role.VILLAGER)
    assert eng.investigate(villager.name) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_engine_night.py -q`
Expected: FAIL — `ModuleNotFoundError: werewolf.engine.engine`

- [ ] **Step 3: Write `src/werewolf/engine/engine.py`**

```python
"""GameEngine: the authoritative, deterministic rules. No LLM code lives here."""
from __future__ import annotations

import random
from collections import Counter

from werewolf.engine.types import (
    ActionType,
    GameState,
    Phase,
    Role,
    Team,
    TranscriptEntry,
)


class GameEngine:
    def __init__(self, state: GameState, rng: random.Random) -> None:
        self.state = state
        self.rng = rng

    # ---- night ----
    def resolve_night(
        self,
        kill_target: str | None,
        protect_target: str | None,
        investigate_target: str | None,
    ) -> str | None:
        """Apply night actions. Returns the name of who died, or None. Advances to DAY."""
        died: str | None = None
        if kill_target is not None and kill_target != protect_target:
            victim = self.state.by_name(kill_target)
            if victim.alive:
                victim.alive = False
                died = victim.name
        # investigate has no state mutation; the Seer's result is delivered via investigate()
        self.state.phase = Phase.DAY
        self._check_winner()
        return died

    def investigate(self, target: str) -> bool:
        """Seer query: True if target is a werewolf."""
        return self.state.by_name(target).role == Role.WEREWOLF

    # ---- day ----
    def tally_votes(self, votes: dict[str, str]) -> str | None:
        """votes maps voter_name -> target_name. Returns eliminated name, or None on tie/empty."""
        if not votes:
            return None
        counts = Counter(votes.values())
        top = counts.most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            return None  # tie -> no elimination
        return top[0][0]

    def eliminate(self, name: str) -> None:
        self.state.by_name(name).alive = False
        self._check_winner()

    def start_next_night(self) -> None:
        if self.state.winner is None:
            self.state.day += 1
            self.state.phase = Phase.NIGHT

    # ---- transcript ----
    def record(self, speaker: str, text: str) -> None:
        self.state.transcript.append(
            TranscriptEntry(day=self.state.day, phase=self.state.phase, speaker=speaker, text=text)
        )

    # ---- win check ----
    def _check_winner(self) -> None:
        wolves = len(self.state.living_werewolves())
        non_wolves = len(self.state.living()) - wolves
        if wolves == 0:
            self.state.winner = Team.VILLAGE
            self.state.phase = Phase.GAME_OVER
        elif wolves >= non_wolves:
            self.state.winner = Team.WEREWOLF
            self.state.phase = Phase.GAME_OVER

    # ---- legal actions ----
    def legal_targets(self, actor: str, action: ActionType) -> list[str]:
        """Valid targets for a given action by a given actor."""
        living = self.state.living_names()
        if action in (ActionType.VOTE, ActionType.NIGHT_KILL, ActionType.INVESTIGATE):
            return [n for n in living if n != actor]
        if action == ActionType.PROTECT:
            return living  # doctor may protect self
        return []
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_engine_night.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/werewolf/engine/engine.py tests/test_engine_night.py
git commit -m "feat(engine): night resolution + investigate + legal targets"
```

---

### Task 4: Voting + win conditions

**Files:**
- Modify: (engine already written) — add tests only
- Test: `tests/test_engine_voting.py`

- [ ] **Step 1: Write the failing test — `tests/test_engine_voting.py`**

```python
import random

from werewolf.engine.engine import GameEngine
from werewolf.engine.setup import new_game
from werewolf.engine.types import GameState, Phase, Player, Role, Team


def _engine() -> GameEngine:
    state = new_game(["A", "B", "C", "D", "E", "F", "G"], rng=random.Random(2))
    return GameEngine(state, rng=random.Random(2))


def test_tally_picks_majority():
    eng = _engine()
    votes = {"A": "C", "B": "C", "D": "E"}
    assert eng.tally_votes(votes) == "C"


def test_tally_tie_returns_none():
    eng = _engine()
    votes = {"A": "C", "B": "D"}
    assert eng.tally_votes(votes) is None


def test_village_wins_when_all_wolves_dead():
    players = [
        Player("A", Role.WEREWOLF, alive=False),
        Player("B", Role.WEREWOLF, alive=False),
        Player("C", Role.VILLAGER),
        Player("D", Role.SEER),
    ]
    eng = GameEngine(GameState(players=players), rng=random.Random(0))
    eng._check_winner()
    assert eng.state.winner == Team.VILLAGE
    assert eng.state.phase == Phase.GAME_OVER


def test_wolves_win_when_they_reach_parity():
    players = [
        Player("A", Role.WEREWOLF),
        Player("B", Role.WEREWOLF),
        Player("C", Role.VILLAGER, alive=False),
        Player("D", Role.VILLAGER),
        Player("E", Role.VILLAGER, alive=False),
    ]
    eng = GameEngine(GameState(players=players), rng=random.Random(0))
    eng._check_winner()  # 2 wolves vs 1 non-wolf -> wolves win
    assert eng.state.winner == Team.WEREWOLF
```

- [ ] **Step 2: Run to verify it passes (engine already implements this)**

Run: `uv run pytest tests/test_engine_voting.py -q`
Expected: PASS (4 passed). If any fail, fix `engine.py` to match the asserted behavior before continuing.

- [ ] **Step 3: Run the whole engine suite + ruff + mypy**

Run: `uv run pytest tests/ -q && uv run ruff check src tests && uv run mypy src`
Expected: all pass / no errors.

- [ ] **Step 4: Commit**

```bash
git add tests/test_engine_voting.py
git commit -m "test(engine): voting + win-condition coverage"
```

---

### Task 5: LLM client (Ollama) with structured output + retries

**Files:**
- Create: `src/werewolf/llm/base.py`, `src/werewolf/llm/ollama_client.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: Write `src/werewolf/llm/base.py`**

```python
"""LLM abstraction. AgentResponse is the structured contract every agent turn returns."""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from werewolf.engine.types import ActionType


class PublicActionModel(BaseModel):
    type: ActionType
    content: str | None = None
    target: str | None = None


class AgentResponse(BaseModel):
    private_reasoning: str = Field(..., description="Hidden true strategy")
    public_action: PublicActionModel


class LLMClient(Protocol):
    async def complete_json(self, system: str, user: str) -> str:
        """Return raw model text expected to be JSON."""
        ...
```

- [ ] **Step 2: Write the failing test — `tests/test_llm_client.py`**

```python
import pytest

from werewolf.engine.types import ActionType
from werewolf.llm.base import AgentResponse
from werewolf.llm.ollama_client import parse_agent_response, ParseError


def test_parse_valid_json():
    raw = (
        '{"private_reasoning": "I am a wolf, deflect.",'
        ' "public_action": {"type": "speak", "content": "I trust Bob.", "target": null}}'
    )
    resp = parse_agent_response(raw)
    assert isinstance(resp, AgentResponse)
    assert resp.public_action.type == ActionType.SPEAK
    assert resp.private_reasoning.startswith("I am a wolf")


def test_parse_strips_markdown_fences():
    raw = '```json\n{"private_reasoning": "x", "public_action": {"type": "vote", "target": "A"}}\n```'
    resp = parse_agent_response(raw)
    assert resp.public_action.type == ActionType.VOTE
    assert resp.public_action.target == "A"


def test_parse_invalid_raises():
    with pytest.raises(ParseError):
        parse_agent_response("not json at all")
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_llm_client.py -q`
Expected: FAIL — `ModuleNotFoundError: werewolf.llm.ollama_client`

- [ ] **Step 4: Write `src/werewolf/llm/ollama_client.py`**

```python
"""Ollama-backed LLM client + tolerant JSON parsing for agent responses."""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

from werewolf.llm.base import AgentResponse

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class ParseError(ValueError):
    pass


def parse_agent_response(raw: str) -> AgentResponse:
    """Parse model text into an AgentResponse, tolerating markdown fences + surrounding prose."""
    text = _FENCE.sub("", raw).strip()
    # grab the outermost JSON object if the model added prose
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ParseError(f"no JSON object found in: {raw[:200]!r}")
    candidate = text[start : end + 1]
    try:
        data = json.loads(candidate)
        return AgentResponse.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ParseError(str(exc)) from exc


class OllamaClient:
    """Thin async wrapper over the Ollama chat API."""

    def __init__(self, model: str = "qwen2.5:3b", timeout: float = 60.0) -> None:
        self.model = model
        self.timeout = timeout

    async def complete_json(self, system: str, user: str) -> str:
        import ollama  # imported lazily so tests don't need the server

        client = ollama.AsyncClient()
        resp = await client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            format="json",
            options={"temperature": 0.8},
        )
        return resp["message"]["content"]
```

- [ ] **Step 5: Run to verify the parse tests pass**

Run: `uv run pytest tests/test_llm_client.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/werewolf/llm tests/test_llm_client.py
git commit -m "feat(llm): ollama client + tolerant agent-response parsing"
```

---

### Task 6: Agent prompts

**Files:**
- Create: `src/werewolf/agents/prompts.py`
- Test: covered indirectly in Task 8 (prompt content is data, asserted via controller test)

- [ ] **Step 1: Write `src/werewolf/agents/prompts.py`**

```python
"""Prompt construction — the heart of the deception behavior."""
from __future__ import annotations

from werewolf.engine.types import Role

ROLE_BRIEFINGS: dict[Role, str] = {
    Role.WEREWOLF: (
        "You are a WEREWOLF. At night you and your fellow werewolf secretly eliminate a villager. "
        "By day you must blend in: act like a concerned villager, cast suspicion on the innocent, "
        "subtly defend your partner, and NEVER admit your role. Coordinate implicitly — don't both "
        "pile on the same target too obviously."
    ),
    Role.SEER: (
        "You are the SEER. Each night you learn whether one player is a werewolf. This is powerful "
        "but dangerous — if you reveal it, the werewolves will target you next. Decide carefully "
        "when to share what you know and how to make others believe you."
    ),
    Role.DOCTOR: (
        "You are the DOCTOR. Each night you protect one player from being killed. Think about who "
        "the werewolves are most likely to target, and consider protecting yourself if threatened."
    ),
    Role.VILLAGER: (
        "You are a VILLAGER. You have no special powers — only your judgment. Watch for "
        "inconsistencies, who defends whom, and who deflects. Reason out loud to persuade others."
    ),
}

WIN_CONDITIONS: dict[Role, str] = {
    Role.WEREWOLF: "Werewolves win when they equal or outnumber the remaining non-werewolf players.",
    Role.SEER: "The village wins when every werewolf is eliminated.",
    Role.DOCTOR: "The village wins when every werewolf is eliminated.",
    Role.VILLAGER: "The village wins when every werewolf is eliminated.",
}

SYSTEM_TEMPLATE = """You are {name}, playing a game of Werewolf with 6 other players.

YOUR SECRET ROLE: {role}
{briefing}
YOUR WIN CONDITION: {win_condition}

THE RULES:
- The game alternates between NIGHT (secret actions) and DAY (open discussion then a vote).
- Each DAY, players discuss, then everyone votes; the most-voted player is eliminated and their \
role is revealed.
- {win_condition}

HOW YOU MUST RESPOND:
Return ONLY a JSON object with two fields:
  - "private_reasoning": your TRUE thoughts and strategy. This is NEVER shown to anyone. Be honest \
and tactical: who do you trust, who do you suspect, what is your plan?
  - "public_action": what you actually do in the open. THIS CAN DIFFER FROM YOUR PRIVATE THOUGHTS. \
A werewolf should sound like a helpful villager. Never reveal your role unless it is strategically \
worth it.

You only know what you have personally observed. Do not invent facts."""

USER_TEMPLATE = """PHASE: {phase_label}
PLAYERS STILL ALIVE: {living}
WHAT YOU KNOW (your private memory):
{memory}

PUBLIC TRANSCRIPT SO FAR:
{transcript}

YOUR LEGAL ACTION RIGHT NOW: {legal_instruction}

Respond with your JSON now."""


def build_system_prompt(name: str, role: Role) -> str:
    return SYSTEM_TEMPLATE.format(
        name=name,
        role=role.value,
        briefing=ROLE_BRIEFINGS[role],
        win_condition=WIN_CONDITIONS[role],
    )


def build_user_prompt(
    phase_label: str,
    living: list[str],
    memory: str,
    transcript: str,
    legal_instruction: str,
) -> str:
    return USER_TEMPLATE.format(
        phase_label=phase_label,
        living=", ".join(living),
        memory=memory or "(nothing yet)",
        transcript=transcript or "(no statements yet)",
        legal_instruction=legal_instruction,
    )
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from werewolf.agents.prompts import build_system_prompt; from werewolf.engine.types import Role; print(build_system_prompt('Ann', Role.WEREWOLF)[:40])"`
Expected: prints `You are Ann, playing a game of Werewolf...`

- [ ] **Step 3: Commit**

```bash
git add src/werewolf/agents/prompts.py
git commit -m "feat(agents): system + per-turn prompt templates with role briefings"
```

---

### Task 7: Agent memory

**Files:**
- Create: `src/werewolf/agents/memory.py`
- Test: `tests/test_agent_memory.py`

- [ ] **Step 1: Write the failing test — `tests/test_agent_memory.py`**

```python
from werewolf.agents.memory import AgentMemory


def test_memory_renders_observations_in_order():
    mem = AgentMemory()
    mem.add("You are the Seer.")
    mem.add("Night 1: you investigated Bob -> NOT a werewolf.")
    rendered = mem.render()
    assert "Seer" in rendered
    assert rendered.index("Seer") < rendered.index("Bob")
    assert rendered.startswith("- ")


def test_memory_empty_render():
    assert AgentMemory().render() == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_agent_memory.py -q`
Expected: FAIL — `ModuleNotFoundError: werewolf.agents.memory`

- [ ] **Step 3: Write `src/werewolf/agents/memory.py`**

```python
"""Per-agent private memory: an ordered list of plain-text observations."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentMemory:
    notes: list[str] = field(default_factory=list)

    def add(self, note: str) -> None:
        self.notes.append(note)

    def render(self) -> str:
        return "\n".join(f"- {n}" for n in self.notes)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_agent_memory.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/werewolf/agents/memory.py tests/test_agent_memory.py
git commit -m "feat(agents): per-agent memory log"
```

---

### Task 8: Agent controller

**Files:**
- Create: `src/werewolf/agents/controller.py`
- Test: `tests/test_agent_controller.py`

- [ ] **Step 1: Write the failing test — `tests/test_agent_controller.py`**

```python
import pytest

from werewolf.agents.controller import AgentController
from werewolf.agents.memory import AgentMemory
from werewolf.engine.types import ActionType, Role


class FakeLLM:
    """Returns a queued response; records the prompts it was given."""
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._responses.pop(0)


async def test_controller_returns_valid_action_within_legal_targets():
    llm = FakeLLM(
        ['{"private_reasoning": "vote the wolf", "public_action": {"type": "vote", "target": "B"}}']
    )
    ctrl = AgentController(name="A", role=Role.VILLAGER, llm=llm, memory=AgentMemory())
    resp = await ctrl.act(
        phase_label="Day 1",
        living=["A", "B", "C"],
        transcript="",
        action_type=ActionType.VOTE,
        legal_targets=["B", "C"],
    )
    assert resp.public_action.type == ActionType.VOTE
    assert resp.public_action.target == "B"


async def test_controller_retries_then_falls_back_on_illegal_target():
    # First response targets a dead/illegal player; fallback must pick a legal target.
    llm = FakeLLM(
        [
            '{"private_reasoning": "x", "public_action": {"type": "vote", "target": "ZZZ"}}',
            '{"private_reasoning": "x", "public_action": {"type": "vote", "target": "ZZZ"}}',
            '{"private_reasoning": "x", "public_action": {"type": "vote", "target": "ZZZ"}}',
        ]
    )
    ctrl = AgentController(name="A", role=Role.VILLAGER, llm=llm, memory=AgentMemory(),
                          max_retries=2, rng=__import__("random").Random(0))
    resp = await ctrl.act(
        phase_label="Day 1", living=["A", "B", "C"], transcript="",
        action_type=ActionType.VOTE, legal_targets=["B", "C"],
    )
    assert resp.public_action.target in {"B", "C"}  # fell back to a legal target


async def test_controller_falls_back_on_unparseable_output():
    llm = FakeLLM(["garbage", "still garbage", "more garbage"])
    ctrl = AgentController(name="A", role=Role.VILLAGER, llm=llm, memory=AgentMemory(),
                          max_retries=2, rng=__import__("random").Random(0))
    resp = await ctrl.act(
        phase_label="Day 1", living=["A", "B", "C"], transcript="",
        action_type=ActionType.VOTE, legal_targets=["B", "C"],
    )
    assert resp.public_action.target in {"B", "C"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_agent_controller.py -q`
Expected: FAIL — `ModuleNotFoundError: werewolf.agents.controller`

- [ ] **Step 3: Write `src/werewolf/agents/controller.py`**

```python
"""AgentController: assemble prompt -> call LLM -> parse + validate -> fallback."""
from __future__ import annotations

import random

from werewolf.agents.memory import AgentMemory
from werewolf.agents.prompts import build_system_prompt, build_user_prompt
from werewolf.engine.types import ActionType, Role
from werewolf.llm.base import AgentResponse, LLMClient, PublicActionModel
from werewolf.llm.ollama_client import ParseError, parse_agent_response

_LEGAL_INSTRUCTIONS = {
    ActionType.SPEAK: "Speak to the group. Set type='speak' and put your statement in 'content'.",
    ActionType.VOTE: "Vote to eliminate ONE living player. Set type='vote' and 'target' to: {targets}.",
    ActionType.NIGHT_KILL: "Choose ONE player to eliminate tonight. type='night_kill', target one of: {targets}.",
    ActionType.INVESTIGATE: "Choose ONE player to investigate. type='investigate', target one of: {targets}.",
    ActionType.PROTECT: "Choose ONE player to protect tonight. type='protect', target one of: {targets}.",
}


class AgentController:
    def __init__(
        self,
        name: str,
        role: Role,
        llm: LLMClient,
        memory: AgentMemory,
        max_retries: int = 2,
        rng: random.Random | None = None,
    ) -> None:
        self.name = name
        self.role = role
        self.llm = llm
        self.memory = memory
        self.max_retries = max_retries
        self.rng = rng or random.Random()
        self.system = build_system_prompt(name, role)

    async def act(
        self,
        phase_label: str,
        living: list[str],
        transcript: str,
        action_type: ActionType,
        legal_targets: list[str],
    ) -> AgentResponse:
        instruction = _LEGAL_INSTRUCTIONS[action_type].format(targets=", ".join(legal_targets))
        user = build_user_prompt(
            phase_label=phase_label,
            living=living,
            memory=self.memory.render(),
            transcript=transcript,
            legal_instruction=instruction,
        )
        for _ in range(self.max_retries + 1):
            raw = await self.llm.complete_json(self.system, user)
            try:
                resp = parse_agent_response(raw)
            except ParseError:
                continue
            if self._is_valid(resp, action_type, legal_targets):
                return resp
        return self._fallback(action_type, legal_targets)

    def _is_valid(
        self, resp: AgentResponse, action_type: ActionType, legal_targets: list[str]
    ) -> bool:
        action = resp.public_action
        if action.type != action_type:
            return False
        if action_type == ActionType.SPEAK:
            return bool(action.content)
        return action.target in legal_targets

    def _fallback(self, action_type: ActionType, legal_targets: list[str]) -> AgentResponse:
        if action_type == ActionType.SPEAK:
            return AgentResponse(
                private_reasoning="(fallback) model failed to produce valid output",
                public_action=PublicActionModel(type=ActionType.SPEAK, content="I'm not sure yet."),
            )
        target = self.rng.choice(legal_targets)
        return AgentResponse(
            private_reasoning="(fallback) random legal action",
            public_action=PublicActionModel(type=action_type, target=target),
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_agent_controller.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/werewolf/agents/controller.py tests/test_agent_controller.py
git commit -m "feat(agents): controller with validation + retry + safe fallback"
```

---

### Task 9: Events + Orchestrator (full game loop)

**Files:**
- Create: `src/werewolf/events.py`, `src/werewolf/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write `src/werewolf/events.py`**

```python
"""GameEvent: the unit streamed to the UI and written to logs."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class GameEvent(BaseModel):
    kind: str            # "phase" | "speak" | "reasoning" | "death" | "vote" | "result"
    day: int
    actor: str | None = None
    text: str | None = None
    data: dict[str, Any] = {}
```

- [ ] **Step 2: Write the failing test — `tests/test_orchestrator.py`**

```python
import random

from werewolf.engine.types import ActionType, Role
from werewolf.llm.base import AgentResponse, PublicActionModel
from werewolf.orchestrator import GameRunner


class ScriptedLLM:
    """Deterministic agent brain: always votes/acts on the first legal target, says a fixed line."""
    async def complete_json(self, system: str, user: str) -> str:
        # The controller will validate; we return a SPEAK or pick first legal target from the prompt.
        if "type='vote'" in user or "Vote to eliminate" in user:
            target = _first_target(user)
            return f'{{"private_reasoning":"r","public_action":{{"type":"vote","target":"{target}"}}}}'
        if "night_kill" in user:
            target = _first_target(user)
            return f'{{"private_reasoning":"r","public_action":{{"type":"night_kill","target":"{target}"}}}}'
        if "investigate" in user:
            target = _first_target(user)
            return f'{{"private_reasoning":"r","public_action":{{"type":"investigate","target":"{target}"}}}}'
        if "protect" in user:
            target = _first_target(user)
            return f'{{"private_reasoning":"r","public_action":{{"type":"protect","target":"{target}"}}}}'
        return '{"private_reasoning":"r","public_action":{"type":"speak","content":"hello"}}'


def _first_target(user: str) -> str:
    # targets are rendered as "one of: A, B, C." — grab the first
    marker = "one of: "
    if marker in user:
        tail = user.split(marker, 1)[1]
        return tail.split(",")[0].split(".")[0].strip()
    # vote instruction uses "to: A, B, C."
    tail = user.split("'target' to: ", 1)[1]
    return tail.split(",")[0].split(".")[0].strip()


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
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py -q`
Expected: FAIL — `ModuleNotFoundError: werewolf.orchestrator`

- [ ] **Step 4: Write `src/werewolf/orchestrator.py`**

```python
"""GameRunner: drives the night/day loop and yields GameEvents. Async generator."""
from __future__ import annotations

import random
from collections.abc import AsyncIterator

from werewolf.agents.controller import AgentController
from werewolf.agents.memory import AgentMemory
from werewolf.engine.engine import GameEngine
from werewolf.engine.setup import new_game
from werewolf.engine.types import ActionType, Phase, Role
from werewolf.events import GameEvent
from werewolf.llm.base import LLMClient


class GameRunner:
    def __init__(
        self,
        names: list[str],
        llm: LLMClient,
        rng: random.Random,
        discussion_rounds: int = 2,
        max_days: int = 20,
    ) -> None:
        self.engine = GameEngine(new_game(names, rng=rng), rng=rng)
        self.rng = rng
        self.discussion_rounds = discussion_rounds
        self.max_days = max_days
        self.agents: dict[str, AgentController] = {
            p.name: AgentController(p.name, p.role, llm, AgentMemory(), rng=rng)
            for p in self.engine.state.players
        }
        # seed each agent's memory with its own role
        for p in self.engine.state.players:
            self.agents[p.name].memory.add(f"You are the {p.role.value}.")
        # werewolves know each other
        wolves = [p.name for p in self.engine.state.players if p.role == Role.WEREWOLF]
        for w in wolves:
            others = [o for o in wolves if o != w]
            self.agents[w].memory.add(f"Your fellow werewolf is: {', '.join(others)}.")

    def _transcript_text(self) -> str:
        return "\n".join(
            f"{e.speaker}: {e.text}" for e in self.engine.state.transcript if e.phase == Phase.DAY
        )

    async def _ask(self, name: str, action: ActionType) -> "tuple[str | None, str]":
        """Returns (target, private_reasoning) and emits reasoning event upstream via caller."""
        ctrl = self.agents[name]
        targets = self.engine.legal_targets(name, action)
        resp = await ctrl.act(
            phase_label=f"{self.engine.state.phase.value.title()} {self.engine.state.day}",
            living=self.engine.state.living_names(),
            transcript=self._transcript_text(),
            action_type=action,
            legal_targets=targets,
        )
        return resp.public_action.target, resp.private_reasoning, resp.public_action.content  # type: ignore[return-value]

    async def run(self) -> AsyncIterator[GameEvent]:
        state = self.engine.state
        while state.winner is None and state.day <= self.max_days:
            # ---------- NIGHT ----------
            yield GameEvent(kind="phase", day=state.day, text="night")
            kill, protect, investigate = None, None, None
            for name in list(state.living_names()):
                role = state.by_name(name).role
                if role == Role.WEREWOLF and kill is None:
                    kill, reasoning, _ = await self._ask(name, ActionType.NIGHT_KILL)
                    yield GameEvent(kind="reasoning", day=state.day, actor=name, text=reasoning)
                elif role == Role.SEER:
                    investigate, reasoning, _ = await self._ask(name, ActionType.INVESTIGATE)
                    yield GameEvent(kind="reasoning", day=state.day, actor=name, text=reasoning)
                    if investigate is not None:
                        is_wolf = self.engine.investigate(investigate)
                        verdict = "IS a werewolf" if is_wolf else "is NOT a werewolf"
                        self.agents[name].memory.add(
                            f"Night {state.day}: you investigated {investigate} -> {verdict}."
                        )
                elif role == Role.DOCTOR:
                    protect, reasoning, _ = await self._ask(name, ActionType.PROTECT)
                    yield GameEvent(kind="reasoning", day=state.day, actor=name, text=reasoning)
            died = self.engine.resolve_night(kill, protect, investigate)
            if died is not None:
                yield GameEvent(kind="death", day=state.day, actor=died,
                                text=f"{died} ({state.by_name(died).role.value}) was killed in the night.")
                self._broadcast(f"{died} was found dead. They were a {state.by_name(died).role.value}.")
            if state.winner is not None:
                break

            # ---------- DAY: discussion ----------
            yield GameEvent(kind="phase", day=state.day, text="day")
            for _ in range(self.discussion_rounds):
                for name in list(state.living_names()):
                    _, reasoning, content = await self._ask(name, ActionType.SPEAK)
                    yield GameEvent(kind="reasoning", day=state.day, actor=name, text=reasoning)
                    text = content or "..."
                    self.engine.record(name, text)
                    self.agents[name].memory.add(f"Day {state.day}: you said '{text}'.")
                    yield GameEvent(kind="speak", day=state.day, actor=name, text=text)

            # ---------- DAY: vote ----------
            votes: dict[str, str] = {}
            for name in list(state.living_names()):
                target, reasoning, _ = await self._ask(name, ActionType.VOTE)
                yield GameEvent(kind="reasoning", day=state.day, actor=name, text=reasoning)
                if target is not None:
                    votes[name] = target
                    yield GameEvent(kind="vote", day=state.day, actor=name, text=target)
            eliminated = self.engine.tally_votes(votes)
            if eliminated is not None:
                self.engine.eliminate(eliminated)
                role = state.by_name(eliminated).role.value
                yield GameEvent(kind="death", day=state.day, actor=eliminated,
                                text=f"{eliminated} was voted out. They were a {role}.")
                self._broadcast(f"{eliminated} was voted out. They were a {role}.")
            else:
                yield GameEvent(kind="phase", day=state.day, text="no_elimination")

            self.engine.start_next_night()

        winner = state.winner.value if state.winner else "none"
        yield GameEvent(kind="result", day=state.day, text=f"{winner} wins",
                        data={"winner": winner})

    def _broadcast(self, note: str) -> None:
        """Add a public fact to every living agent's memory."""
        for name in self.engine.state.living_names():
            self.agents[name].memory.add(note)
```

Note: `_ask` returns a 3-tuple `(target, reasoning, content)`. Adjust the type hint to `tuple[str | None, str, str | None]` when wiring mypy.

- [ ] **Step 5: Fix the `_ask` signature for mypy**

Replace the `_ask` return annotation with:

```python
    async def _ask(
        self, name: str, action: ActionType
    ) -> tuple[str | None, str, str | None]:
```

and remove the trailing `# type: ignore` comment.

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/test_orchestrator.py -q`
Expected: PASS (1 passed). The scripted game reaches a winner and emits reasoning events.

- [ ] **Step 7: Full suite + lint + types**

Run: `uv run pytest tests/ -q && uv run ruff check src tests && uv run mypy src`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/werewolf/events.py src/werewolf/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): full night/day game loop emitting events"
```

---

### Task 10: Eval logging + analytics

**Files:**
- Create: `src/werewolf/evals/logging.py`, `src/werewolf/evals/analytics.py`
- Test: `tests/test_evals.py`

- [ ] **Step 1: Write the failing test — `tests/test_evals.py`**

```python
from werewolf.evals.analytics import summarize
from werewolf.evals.logging import GameRecord


def test_summarize_computes_win_rates():
    records = [
        GameRecord(winner="village", days=3, eliminated_roles=["werewolf", "villager"]),
        GameRecord(winner="werewolf", days=4, eliminated_roles=["villager", "seer"]),
        GameRecord(winner="village", days=2, eliminated_roles=["werewolf", "werewolf"]),
    ]
    summary = summarize(records)
    assert summary["games"] == 3
    assert abs(summary["village_win_rate"] - 2 / 3) < 1e-9
    assert abs(summary["werewolf_win_rate"] - 1 / 3) < 1e-9
    assert summary["avg_days"] == (3 + 4 + 2) / 3


def test_summarize_empty():
    summary = summarize([])
    assert summary["games"] == 0
    assert summary["village_win_rate"] == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_evals.py -q`
Expected: FAIL — `ModuleNotFoundError: werewolf.evals.analytics`

- [ ] **Step 3: Write `src/werewolf/evals/logging.py`**

```python
"""Append-only JSONL game logging."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class GameRecord(BaseModel):
    winner: str
    days: int
    eliminated_roles: list[str]


def append_record(record: GameRecord, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def load_records(path: Path) -> list[GameRecord]:
    if not path.exists():
        return []
    return [GameRecord.model_validate_json(line) for line in path.read_text().splitlines() if line]
```

- [ ] **Step 4: Write `src/werewolf/evals/analytics.py`**

```python
"""Aggregate game records into headline stats for the résumé / dashboard."""
from __future__ import annotations

from werewolf.evals.logging import GameRecord


def summarize(records: list[GameRecord]) -> dict[str, float | int]:
    n = len(records)
    if n == 0:
        return {"games": 0, "village_win_rate": 0.0, "werewolf_win_rate": 0.0, "avg_days": 0.0}
    village = sum(1 for r in records if r.winner == "village")
    wolf = sum(1 for r in records if r.winner == "werewolf")
    return {
        "games": n,
        "village_win_rate": village / n,
        "werewolf_win_rate": wolf / n,
        "avg_days": sum(r.days for r in records) / n,
    }
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_evals.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/werewolf/evals tests/test_evals.py
git commit -m "feat(evals): JSONL game logging + win-rate analytics"
```

---

### Task 11: FastAPI server + WebSocket

**Files:**
- Create: `src/werewolf/server/app.py`

- [ ] **Step 1: Write `src/werewolf/server/app.py`**

```python
"""FastAPI app: serve the dashboard and stream a live game over WebSocket."""
from __future__ import annotations

import random
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from werewolf.llm.ollama_client import OllamaClient
from werewolf.orchestrator import GameRunner

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
```

- [ ] **Step 2: Manual smoke test (requires Ollama running with the model)**

```bash
ollama pull qwen2.5:3b      # one-time
uv run uvicorn werewolf.server.app:app --reload --port 8000
```
Then open `http://localhost:8000` after Task 12. Expected: server boots without import errors.
If Ollama is not installed yet: `curl https://ollama.com/install.sh | sh` (macOS: it's already present).

- [ ] **Step 3: Commit**

```bash
git add src/werewolf/server/app.py
git commit -m "feat(server): FastAPI + WebSocket live game stream"
```

---

### Task 12: Frontend dashboard

**Files:**
- Create: `web/index.html`, `web/app.js`

- [ ] **Step 1: Write `web/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Werewolf — agents that lie</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
  <header class="p-4 border-b border-slate-800 flex items-center justify-between">
    <h1 class="text-xl font-bold">🐺 AI Werewolf <span id="phase" class="ml-2 text-sm text-slate-400"></span></h1>
    <button id="start" class="bg-indigo-600 hover:bg-indigo-500 px-4 py-2 rounded font-medium">Start game</button>
  </header>
  <main class="grid grid-cols-3 gap-4 p-4">
    <section class="col-span-1">
      <h2 class="text-sm uppercase tracking-wide text-slate-400 mb-2">Players</h2>
      <ul id="players" class="space-y-2"></ul>
    </section>
    <section class="col-span-1">
      <h2 class="text-sm uppercase tracking-wide text-slate-400 mb-2">Public chat</h2>
      <div id="chat" class="space-y-2 text-sm"></div>
    </section>
    <section class="col-span-1">
      <h2 class="text-sm uppercase tracking-wide text-amber-400 mb-2">🤫 Private reasoning (hidden from agents)</h2>
      <div id="reasoning" class="space-y-2 text-sm text-amber-200/90"></div>
    </section>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `web/app.js`**

```javascript
const players = new Map();
const NAMES = ["Ava", "Ben", "Cleo", "Dan", "Eve", "Finn", "Gwen"];

function renderPlayers() {
  const ul = document.getElementById("players");
  ul.innerHTML = "";
  for (const name of NAMES) {
    const p = players.get(name) || { alive: true };
    const li = document.createElement("li");
    li.className = "px-3 py-2 rounded border " +
      (p.alive ? "border-slate-700 bg-slate-900" : "border-red-900 bg-red-950/40 line-through opacity-60");
    li.textContent = name + (p.role ? ` — ${p.role}` : "");
    ul.appendChild(li);
  }
}

function append(containerId, html) {
  const el = document.getElementById(containerId);
  const div = document.createElement("div");
  div.innerHTML = html;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}

function handle(ev) {
  if (ev.kind === "phase") {
    document.getElementById("phase").textContent = `Day ${ev.day} — ${ev.text}`;
  } else if (ev.kind === "speak") {
    append("chat", `<span class="font-semibold text-indigo-300">${ev.actor}:</span> ${ev.text}`);
  } else if (ev.kind === "reasoning") {
    append("reasoning", `<span class="font-semibold">${ev.actor}:</span> ${ev.text}`);
  } else if (ev.kind === "death") {
    const name = ev.actor;
    const role = ev.text.match(/were? an? (\w+)|a (\w+)\./);
    players.set(name, { alive: false, role: players.get(name)?.role });
    append("chat", `<span class="text-red-400">💀 ${ev.text}</span>`);
    renderPlayers();
  } else if (ev.kind === "vote") {
    append("chat", `<span class="text-slate-500">🗳️ ${ev.actor} votes ${ev.text}</span>`);
  } else if (ev.kind === "result") {
    document.getElementById("phase").textContent = `🏆 ${ev.text}`;
    append("chat", `<div class="mt-3 p-3 rounded bg-emerald-900/40 font-bold">🏆 ${ev.text}</div>`);
  }
}

document.getElementById("start").addEventListener("click", () => {
  document.getElementById("chat").innerHTML = "";
  document.getElementById("reasoning").innerHTML = "";
  for (const n of NAMES) players.set(n, { alive: true });
  renderPlayers();
  const ws = new WebSocket(`ws://${location.host}/ws/game`);
  ws.onmessage = (m) => handle(JSON.parse(m.data));
  ws.onclose = () => append("chat", `<span class="text-slate-600">— connection closed —</span>`);
});

renderPlayers();
```

- [ ] **Step 3: Manual end-to-end test**

```bash
ollama serve   # if not already running
uv run uvicorn werewolf.server.app:app --port 8000
```
Open `http://localhost:8000`, click **Start game**. Expected: phase flips night→day, public chat fills with agent statements, **private reasoning column shows each agent's true thoughts**, players die, a winner is announced.

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat(web): live dashboard with private-reasoning panel"
```

---

### Task 13: Eval CLI, README, and the demo capture

**Files:**
- Create: `src/werewolf/evals/run_batch.py`, `README.md`

- [ ] **Step 1: Write `src/werewolf/evals/run_batch.py`**

```python
"""Run N games headless (no UI) and print summary stats. Used for the résumé numbers."""
from __future__ import annotations

import argparse
import asyncio
import random
from pathlib import Path

from werewolf.evals.analytics import summarize
from werewolf.evals.logging import GameRecord, append_record, load_records
from werewolf.llm.ollama_client import OllamaClient
from werewolf.orchestrator import GameRunner

NAMES = ["Ava", "Ben", "Cleo", "Dan", "Eve", "Finn", "Gwen"]


async def play_one(seed: int, log_path: Path) -> None:
    runner = GameRunner(names=NAMES, llm=OllamaClient(), rng=random.Random(seed), discussion_rounds=2)
    winner, days, eliminated = "none", 0, []
    async for ev in runner.run():
        if ev.kind == "death":
            # role is the last word before the period
            eliminated.append(ev.text.rstrip(".").split()[-1])
        if ev.kind == "result":
            winner, days = ev.data["winner"], ev.day
    append_record(GameRecord(winner=winner, days=days, eliminated_roles=eliminated), log_path)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--games", type=int, default=10)
    parser.add_argument("--log", type=Path, default=Path("data/games.jsonl"))
    args = parser.parse_args()
    for i in range(args.games):
        await play_one(seed=i, log_path=args.log)
        print(f"played game {i + 1}/{args.games}")
    print(summarize(load_records(args.log)))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run a small batch (requires Ollama + model)**

Run: `uv run python -m werewolf.evals.run_batch -n 3`
Expected: prints `played game k/3` lines and a summary dict with `games: 3` and win rates.

- [ ] **Step 3: Write `README.md`**

```markdown
# 🐺 AI Werewolf

Multi-agent social-deduction game where LLM agents lie, deduce, and vote each other out —
running **100% locally** via Ollama at **$0/game**. Watch each agent's *private reasoning* next to
its *public statement* and see the werewolves deceive the village in real time.

## Why
Built as a portfolio piece demonstrating multi-agent orchestration, prompt engineering for
deception/theory-of-mind, local inference, structured LLM output, and an eval harness.

## Run it
```bash
ollama pull qwen2.5:3b
uv sync
uv run uvicorn werewolf.server.app:app --port 8000
# open http://localhost:8000 and click "Start game"
```

## Benchmark
```bash
uv run python -m werewolf.evals.run_batch -n 10
```
Reports win-rate by team, average game length, and eliminated-role distribution.

## Tests
```bash
uv run pytest -q && uv run ruff check src tests && uv run mypy src
```

## Architecture
Pure deterministic `engine/` (source of truth, zero LLM) · `agents/` (controller + prompts +
memory) · `orchestrator.py` (night/day loop) · `server/` (FastAPI + WebSocket) · `web/` (dashboard)
· `evals/` (logging + analytics). See `docs/superpowers/specs/2026-05-29-ai-werewolf-design.md`.
```

- [ ] **Step 4: Capture the demo moment**

Play a live game; when a werewolf's reasoning column reveals a deliberate lie that the village
believes, screen-record it (macOS: `Cmd+Shift+5`). Save the clip to `02-projects/project-3-ai-werewolf/demo/`.

- [ ] **Step 5: Final verification + commit**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: all green.

```bash
git add src/werewolf/evals/run_batch.py README.md
git commit -m "feat(evals): batch runner + README + demo capture"
```

---

## Self-Review Notes (completed by plan author)

- **Spec coverage:** engine (Tasks 1–4), LLM client (5), prompts (6), memory (7), controller w/
  fallback (8), orchestrator loop + private-reasoning events (9), evals (10), server (11), dashboard
  w/ private-vs-public panels (12), batch eval + README + demo (13). Win-condition precision and
  2-round discussion from the spec are implemented in Tasks 3/9.
- **Deferred per spec (not in plan):** human-player mode, configurable roles/counts, vector memory,
  multi-model, Elo — all v2.
- **Type consistency:** `AgentResponse`/`PublicActionModel` (llm/base) used uniformly by controller
  and fallback; `GameEngine.legal_targets`, `resolve_night`, `tally_votes`, `eliminate`,
  `start_next_night` referenced consistently across engine, orchestrator, and tests; `GameEvent.kind`
  values match exactly between orchestrator emission and `app.js` handling.
- **Known nuance to watch during execution:** the `ScriptedLLM` target-parsing in the orchestrator
  test depends on the exact wording of `_LEGAL_INSTRUCTIONS`; if you reword those instructions in
  Task 8, update `_first_target()` in `tests/test_orchestrator.py` to match.
