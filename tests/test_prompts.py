from werewolf.agents.prompts import build_system_prompt
from werewolf.engine.types import Role


def test_system_prompt_states_actual_other_player_count():
    # The agent must be told the true table size, not a hardcoded number.
    for total, others in [(7, 6), (9, 8), (5, 4)]:
        prompt = build_system_prompt("Ava", Role.WEREWOLF, num_players=total)
        assert f"{others} other players" in prompt


def test_system_prompt_includes_role_briefing_and_name():
    prompt = build_system_prompt("Ava", Role.SEER, num_players=7)
    assert "Ava" in prompt
    assert "SEER" in prompt
