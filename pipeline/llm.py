"""Thin OpenAI wrapper shared by enrich.py and normalize_recipients.py.

Keeps LLM access in one place so the rest of the pipeline can ask `llm_available()`
and fall back to deterministic heuristics when there's no key / offline demo.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from utils import USE_SAMPLE_DATA, get_logger

log = get_logger("pipeline.llm")

MODEL = "gpt-4o-mini"


def llm_available() -> bool:
    """True only when we should actually call OpenAI."""
    return bool(os.getenv("OPENAI_API_KEY")) and not USE_SAMPLE_DATA


_client = None


def get_openai():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI()
    return _client


async def chat_json(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    tool_choice: Optional[dict] = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Run a chat completion and return parsed JSON.

    Supports two modes:
      - function/tool calling (pass `tools` + `tool_choice`) -> parsed arguments
      - JSON mode (no tools) -> parsed message content
    Runs the blocking SDK call in a thread so callers can gather() concurrently.
    """
    import asyncio

    def _call():
        client = get_openai()
        kwargs: dict[str, Any] = {
            "model": MODEL,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice
        else:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        if tools and msg.tool_calls:
            return json.loads(msg.tool_calls[0].function.arguments)
        return json.loads(msg.content)

    return await asyncio.to_thread(_call)
