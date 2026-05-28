import pytest

from werewolf.engine.types import ActionType
from werewolf.llm.base import AgentResponse
from werewolf.llm.ollama_client import ParseError, parse_agent_response


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
