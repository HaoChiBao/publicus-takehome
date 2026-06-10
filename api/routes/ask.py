"""Natural-language grant search and Q&A."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_repo

router = APIRouter(prefix="/api/grants", tags=["grants-ai"])


class AskIn(BaseModel):
    question: str
    session_id: Optional[str] = None


@router.post("/ask")
async def ask_grants(body: AskIn):
    """Hybrid search + stats-backed answer with program citations."""
    if not (body.question or "").strip():
        raise HTTPException(status_code=400, detail="question is required")
    repo = await get_repo()
    profile = None
    if body.session_id:
        profile = await repo.get_profile(body.session_id)
    return await repo.ask_grants(body.question.strip(), profile)
