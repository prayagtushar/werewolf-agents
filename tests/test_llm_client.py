import asyncio

import pytest

from werewolf.engine.types import ActionType
from werewolf.llm.base import AgentResponse
from werewolf.llm.ollama_client import (
    OllamaClient,
    ParseError,
    parse_agent_response,
    response_format,
)


def test_parse_valid_json():
    raw = (
        '{"private_reasoning": "I am a wolf, deflect.",'
        ' "public_action": {"type": "speak", "content": "I trust Bob.", "target": null}}'
    )
    resp = parse_agent_response(raw)
    assert isinstance(resp, AgentResponse)
    assert resp.public_action.type == ActionType.SPEAK
    assert resp.private_reasoning.startswith("I am a wolf")


def test_parsed_response_defaults_to_not_a_fallback():
    resp = parse_agent_response(
        '{"private_reasoning":"x","public_action":{"type":"vote","target":"A"}}'
    )
    assert resp.fallback is False


def test_parse_strips_markdown_fences():
    raw = '```json\n{"private_reasoning": "x", "public_action": {"type": "vote", "target": "A"}}\n```'
    resp = parse_agent_response(raw)
    assert resp.public_action.type == ActionType.VOTE
    assert resp.public_action.target == "A"


def test_parse_invalid_raises():
    with pytest.raises(ParseError):
        parse_agent_response("not json at all")


def test_response_format_describes_the_agent_contract():
    fmt = response_format()
    props = fmt["properties"]
    assert "private_reasoning" in props
    assert "public_action" in props
    # the model must NOT be able to set the internal fallback flag
    assert "fallback" not in props


async def test_complete_json_enforces_timeout(monkeypatch):
    # A model call that outlives the timeout must raise instead of hanging forever.
    client = OllamaClient(timeout=0.01)

    async def slow(system: str, user: str) -> str:
        await asyncio.sleep(1.0)
        return "{}"

    monkeypatch.setattr(client, "_chat", slow, raising=False)
    with pytest.raises(asyncio.TimeoutError):
        await client.complete_json("system", "user")
