"""Ollama-backed LLM client + tolerant JSON parsing for agent responses.

Provider-swap point (aligns with 01-foundations/llm-client): v1 ships Ollama only,
but the model/host are read from the environment so a different local model — or a
future Gemini/Groq free-tier client implementing the same ``LLMClient`` protocol —
can drop in without touching callers. To add another provider later: write a class
with ``async def complete_json(self, system, user) -> str`` and select it here on an
env var (e.g. ``WEREWOLF_LLM_PROVIDER``). Not built now on purpose (YAGNI).
"""
from __future__ import annotations

import json
import os
import re

from pydantic import ValidationError

from werewolf.llm.base import AgentResponse

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

DEFAULT_MODEL = os.environ.get("WEREWOLF_OLLAMA_MODEL", "qwen2.5:3b")
DEFAULT_HOST = os.environ.get("WEREWOLF_OLLAMA_HOST")  # None -> ollama library default


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

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        host: str | None = DEFAULT_HOST,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.host = host

    async def complete_json(self, system: str, user: str) -> str:
        import ollama  # imported lazily so tests don't need the server

        client = ollama.AsyncClient(host=self.host) if self.host else ollama.AsyncClient()
        resp = await client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            format="json",
            options={"temperature": 0.8},
        )
        content = resp["message"]["content"]
        return str(content)
