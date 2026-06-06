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
    Role.WEREWOLF: (
        "Werewolves win when they equal or outnumber the remaining non-werewolf players."
    ),
    Role.SEER: "The village wins when every werewolf is eliminated.",
    Role.DOCTOR: "The village wins when every werewolf is eliminated.",
    Role.VILLAGER: "The village wins when every werewolf is eliminated.",
}

SYSTEM_TEMPLATE = """You are {name}, playing a game of Werewolf with {others} other players.

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


def build_system_prompt(name: str, role: Role, num_players: int) -> str:
    return SYSTEM_TEMPLATE.format(
        name=name,
        role=role.value,
        others=num_players - 1,
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
