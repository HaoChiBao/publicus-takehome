"""Optional OpenAI helper for apply-guide chat (falls back to heuristics without a key)."""
from __future__ import annotations

import json
import os
from typing import Any, Optional

MODEL = "gpt-4o-mini"


def llm_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


_client = None


def _client_or_none():
    global _client
    if not llm_available():
        return None
    if _client is None:
        from openai import OpenAI
        _client = OpenAI()
    return _client


async def chat_json(
    messages: list[dict],
    temperature: float = 0.2,
) -> Optional[dict[str, Any]]:
    import asyncio

    client = _client_or_none()
    if client is None:
        return None

    def _call():
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content or "{}")

    try:
        return await asyncio.to_thread(_call)
    except Exception:
        return None
