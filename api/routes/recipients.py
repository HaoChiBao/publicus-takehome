"""Recipient search + full award history routes (the competitor-intel views)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from db import get_repo

router = APIRouter(prefix="/api/recipients", tags=["recipients"])


@router.get("/search")
async def search_recipients(q: str = "", province: Optional[str] = None):
    """Full-text search over canonical recipient names."""
    repo = await get_repo()
    return {"recipients": await repo.search_recipients(q, province, limit=10)}


@router.get("/similar")
async def similar_recipients(session_id: str):
    """Recipients most similar to the session company profile."""
    repo = await get_repo()
    profile = await repo.get_profile(session_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    peers = await repo.get_similar_recipients(profile, limit=8)
    return {"peers": peers}


@router.get("/{recipient_id}/awards")
async def recipient_awards(recipient_id: str):
    """Complete award history for a recipient, grouped by fiscal year."""
    repo = await get_repo()
    result = await repo.recipient_awards(recipient_id)
    if result["recipient"] is None:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return result
