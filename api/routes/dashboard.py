"""Profile creation + the aggregated dashboard endpoint.

The dashboard endpoint reads the company profile for a session and fans out to
the match / sector-summary / trending logic, returning everything the dashboard
needs in a single request. Results are cached in-memory for 1 hour per session.
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_repo

router = APIRouter(prefix="/api", tags=["dashboard"])

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL_SECONDS = 3600


class ProfileIn(BaseModel):
    name: Optional[str] = None
    sector: Optional[str] = None
    province: Optional[str] = None
    size_band: Optional[str] = None
    activities: list[str] = []
    session_id: Optional[str] = None


@router.post("/profile")
async def create_profile(profile: ProfileIn):
    """Create (or upsert) a session-based company profile."""
    repo = await get_repo()
    session_id = profile.session_id or f"sess_{uuid.uuid4().hex[:16]}"
    saved = await repo.create_profile({**profile.model_dump(), "session_id": session_id})
    _CACHE.pop(session_id, None)  # invalidate any stale dashboard cache
    return {"session_id": session_id, "profile": saved}


@router.get("/dashboard/{session_id}")
async def dashboard(session_id: str):
    """Aggregated dashboard payload: matches + sector intel + trending."""
    cached = _CACHE.get(session_id)
    if cached and time.time() - cached[0] < _TTL_SECONDS:
        return cached[1]

    repo = await get_repo()
    profile = await repo.get_profile(session_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    matches = await repo.match_programs(profile, limit=10)
    summary = await repo.sector_summary(profile["sector"], profile.get("province"), years=2)
    trending = await repo.trending_programs(profile["sector"], profile.get("province"))

    payload = {
        "profile": profile,
        "matches": matches,
        "sector_summary": summary,
        "trending": trending,
    }
    _CACHE[session_id] = (time.time(), payload)
    return payload
