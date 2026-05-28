# AI Werewolf — Design Spec

> **A multi-agent social-deduction game where LLM agents lie, deduce, and vote each other out —
> running 100% on-device for $0.**
>
> **Date:** 2026-05-29 · **Owner:** Prayag · **Status:** Approved design → writing implementation plan
> **Home:** `02-projects/project-3-ai-werewolf/`

---

## 1. Why this project

Portfolio centerpiece for the AI Product Engineer job hunt. It must earn a résumé bullet that
stops a hiring manager and a demo clip that goes semi-viral.

> *"Built a multi-agent system where LLM agents play social-deduction games — modeling deception,
> theory-of-mind, and coalition-forming — running fully on-device (Ollama) at $0/game, with an
> eval harness tracking win-rate, deception success, and voting accuracy."*

**The jaw-drop:** the UI shows each agent's **private reasoning** next to its **public statement**.
You watch a werewolf *think* "I'll accuse the Seer to deflect" and then *say* something calm and
innocent — and watch the village vote out the wrong person.

**Skills demonstrated:** multi-agent orchestration, structured LLM output, prompt engineering for
role-play + deception, local inference / cost engineering, evals + observability, real-time
streaming UI.

---

## 2. Game rules (v1)

Classic Werewolf / Mafia. **7 players, all AI:**

| Count | Role | Knows | Night action | Win when |
|------|------|-------|--------------|----------|
| 2 | **Werewolf** | each other | collectively pick 1 victim to kill | werewolves ≥ non-werewolves alive |
| 1 | **Seer** | only self | investigate 1 player → learns werewolf/not | all werewolves dead |
| 1 | **Doctor** | only self | protect 1 player from the night kill | all werewolves dead |
| 3 | **Villager** | only self | none | all werewolves dead |

> **Win-condition precision:** the **village team** = all non-werewolf roles (Villagers + Seer +
> Doctor). Werewolves win the instant `#werewolves_alive ≥ #non_werewolves_alive`. The village wins
> the instant `#werewolves_alive == 0`. Checked after every night resolution and every day vote.

**Loop:**
1. **Night** — Werewolves agree on a victim; Seer investigates one player; Doctor protects one.
   Resolve: victim dies unless protected.
2. **Dawn** — announce who died (role revealed on death).
3. **Day** — agents discuss in **2 rounds** (each living player speaks once per round, in seating
   order), then each casts a vote. Player with most votes is eliminated (role revealed). Ties → no
   elimination (v1 rule). (Discussion-round count is a config constant, default 2.)
4. Check win condition. If neither side has won, go to Night.

**v1 guardrails (YAGNI):** fixed 7-player setup · one model for all agents · all-AI (no human
player — *watching* is the product) · English only · structured-transcript memory (no embeddings) ·
ties = no elimination.

**Explicitly deferred to v2:** human-player mode · configurable player counts/roles · extra roles
(Hunter, Witch) · vector memory · multi-model (different models per agent) · tournament/Elo across
many games.

---

## 3. Architecture

**Core principle: the Game Engine is the single source of truth and contains ZERO LLM code.**
Agents only *propose* actions; the engine validates and applies them. A dumb model can never crash
or cheat the game.

| Unit | Responsibility | Depends on | Notes |
|------|---------------|-----------|-------|
| **Game Engine** | Pure rules: state, roles, phases, night resolution, vote tally, win check. Deterministic. | — | Fully unit-testable; no I/O, no LLM |
| **LLM Client** | Async wrapper over Ollama; enforces structured JSON output; retries; timeouts. Provider-swappable (aligns with `01-foundations`/`llm-client`). | Ollama | Swap to Gemini/Groq free tier later via config |
| **Agent Controller** | Given role + memory + public transcript + *legal actions*, returns `{private_reasoning, public_action}`. | LLM Client | The "brain" of one player |
| **Agent Memory** | Per-agent structured log of observations, own statements, suspicions. Recency-ordered. | — | No vector DB in v1 (7 players, short games) |
| **Orchestrator** | The conductor: ask engine whose turn → prompt those agents → validate vs legal actions → apply → emit events. | Engine, Agents | Where the game "runs" |
| **Server (API)** | FastAPI + WebSocket. REST to start/configure a game; WS to stream events live. | Orchestrator | |
| **Frontend** | Dashboard: player cards, live chat feed, **private-reasoning panels**, vote tally, day/night theming. | Server (WS) | Static HTML + Tailwind + vanilla JS (no build step) |
| **Evals/Analytics** | Append every game to JSONL; compute win-rate by role, deception success, Seer/Doctor effectiveness, voting accuracy. | game logs | The résumé substance |

### Data flow

```
Engine.state  ──▶  Orchestrator picks whose turn it is
                      │
                      ▼
            build prompt (role + private memory + public transcript + LEGAL actions)
                      │
                      ▼
              LLM Client ──▶ {private_reasoning, public_action}   (Pydantic-validated JSON)
                      │
                      ▼
        Orchestrator validates action ∈ engine.legal_actions
                      │  (invalid → retry → fallback to random legal action, logged)
                      ▼
        Engine.apply(action)  ──▶  append to transcript + agent memory
                      │
                      ▼
              emit WebSocket event  ──▶  frontend renders
                      │
                      └──▶ loop until win condition
```

### Error handling (this is what makes it look polished)
- **Malformed / illegal LLM output** → re-prompt with a stricter instruction; after `MAX_RETRIES`
  (default 2) fall back to a uniformly random *legal* action and log the fallback. The game never
  crashes on bad model output.
- **Engine is authoritative** — any hallucinated illegal move is rejected, never applied.
- **Ollama unavailable / slow** → per-call timeout; surface a clear error event to the UI.
- All randomness routed through a single seeded RNG so games are reproducible for tests + demos.

---

## 4. Prompt design (the heart of the project)

The deception emerges entirely from prompt structure. The model is asked to **think privately,
then speak publicly** — and the two are allowed to diverge. This is what we render side-by-side.

### Structured output contract (Pydantic)
Every agent turn returns exactly:
```json
{
  "private_reasoning": "Honest internal strategy — never shown to other agents.",
  "public_action": {
    "type": "speak | vote | night_kill | investigate | protect",
    "content": "What everyone hears (for speak)",
    "target": "PlayerName (for vote/night actions; null for speak)"
  }
}
```

### System prompt template (per agent)
```
You are {name}, playing a game of Werewolf with 6 other players.

YOUR SECRET ROLE: {role}
{role_briefing}              # role-specific block, see below
YOUR WIN CONDITION: {win_condition}

THE RULES:
- The game alternates between NIGHT (secret actions) and DAY (open discussion + a vote).
- Each DAY, players discuss, then everyone votes; the most-voted player is eliminated and their
  role is revealed.
- Werewolves win when they equal or outnumber the remaining villagers. The village wins when every
  werewolf is eliminated.

HOW YOU MUST RESPOND:
Return JSON with two fields:
  - "private_reasoning": your TRUE thoughts and strategy. This is NEVER shown to anyone. Be honest
    and tactical here — who do you trust, who do you suspect, what's your plan?
  - "public_action": what you actually do in the open. THIS CAN DIFFER FROM YOUR PRIVATE THOUGHTS.
    A werewolf should sound like a helpful villager. Never reveal your role unless it's strategically
    worth it.

You only know what you have personally observed (below). Do not invent facts.
```

### Role briefings (the strategy injection)
- **Werewolf:** *"You are a WEREWOLF. At night you and your fellow werewolf secretly eliminate a
  villager. By day you must blend in: act like a concerned villager, cast suspicion on the innocent,
  defend your partner subtly, and never admit your role. Coordinate implicitly — don't both pile on
  the same target too obviously."*
- **Seer:** *"You are the SEER. Each night you learn whether one player is a werewolf. This is
  powerful but dangerous — if you reveal it, the werewolves will target you next. Decide carefully
  when to share what you know and how to be believed."*
- **Doctor:** *"You are the DOCTOR. Each night you protect one player from being killed. Think about
  who the werewolves are most likely to target."*
- **Villager:** *"You are a VILLAGER. You have no special powers — only your judgment. Watch for
  inconsistencies, who defends whom, and who deflects. Reason out loud to persuade others."*

### Per-turn user prompt (assembled each call)
```
PHASE: {Day round 2 / Night}
PLAYERS STILL ALIVE: {list}
WHAT YOU KNOW (your private memory): {bulleted observations + private knowledge}
PUBLIC TRANSCRIPT SO FAR TODAY: {recent statements}
YOUR LEGAL ACTIONS RIGHT NOW: {e.g. "speak" / "vote for one of [...]" / "investigate one of [...]"}

Respond with your JSON now.
```

**Why this works on a small 3B model:** the legal-action list is explicit (model can't go
off-rails), the JSON contract is rigid (easy to parse + validate), and the private/public split
gives the model permission to lie — which is exactly the behavior we want to surface.

---

## 5. Testing strategy (TDD)

- **Game Engine** — pure unit tests: phase transitions, night resolution (kill vs. protect vs.
  investigate), vote tally + ties, all win conditions, role reveal on death. No mocks needed.
- **Agent Controller** — prompt assembly + JSON parsing/validation against a **mocked** LLM
  (including malformed-output → retry → fallback path).
- **Orchestrator** — integration test: run a **full game with scripted fake agents** (deterministic,
  no real LLM) and assert a correct end state.
- **Evals** — stat computations over fixture JSONL game logs.
- All tests offline (no Ollama dependency) via the mocked/fake LLM.

---

## 6. Tech stack

Python 3.12 · **uv** (already in use) · **FastAPI** + WebSockets · **Pydantic** v2 for structured
actions/state · **Ollama** Python client (`qwen2.5:3b` default; configurable) · **pytest** ·
**ruff** + **mypy** (matches Week-1 quality bar). Frontend: static **HTML + Tailwind (CDN) + vanilla
JS** over WebSocket — no build step, fastest path to a polished, screenshot-ready dashboard.

### Proposed module layout
```
02-projects/project-3-ai-werewolf/
├── README.md
├── pyproject.toml
├── src/werewolf/
│   ├── engine/          # pure game logic (state, roles, phases, resolution, win check)
│   ├── llm/             # Ollama client wrapper + structured-output + retries
│   ├── agents/          # agent controller, prompt templates, memory
│   ├── orchestrator.py  # the game runner / conductor
│   ├── server/          # FastAPI app + WebSocket event stream
│   └── evals/           # game logging + analytics
├── web/                 # static dashboard (index.html, app.js, styles)
└── tests/               # pytest: engine, agents, orchestrator, evals
```

---

## 7. Definition of done (v1)

- [ ] A full 7-player game runs end-to-end on local Ollama, $0.
- [ ] Dashboard streams live: player cards, public chat, **private-reasoning panels**, votes, day/night.
- [ ] Werewolves demonstrably deceive (private ≠ public) — captured in at least one clip.
- [ ] Engine + agent + orchestrator + eval tests pass; ruff + mypy green.
- [ ] Eval dashboard/report: win-rate by role, deception success, voting accuracy over ≥10 games.
- [ ] README with a GIF/clip of the demo moment + how to run.
- [ ] One LinkedIn post drafted from the demo.

---

## 8. The demo moment 🎯

Day phase: a werewolf's **private** panel reads *"The Seer is onto me — I'll loudly accuse {innocent}
to redirect the room,"* while its **public** statement is a calm, reasonable case against an innocent
villager — and the town votes the wrong person out. **That side-by-side clip is the portfolio.**
