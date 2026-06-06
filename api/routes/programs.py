"""Program matching + trending routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from db import get_repo

router = APIRouter(prefix="/api/programs", tags=["programs"])


@router.get("/match")
async def match_programs(
    sector: Optional[str] = None,
    province: Optional[str] = None,
    size_band: Optional[str] = None,
    activities: Optional[str] = Query(None, description="Comma-separated activity list"),
):
    """Top 10 programs scored against a company profile, with match reasons."""
    profile = {
        "sector": sector,
        "province": province,
        "size_band": size_band,
        "activities": [a.strip() for a in activities.split(",")] if activities else [],
    }
    repo = await get_repo()
    return {"programs": await repo.match_programs(profile, limit=10)}


@router.get("/trending")
async def trending_programs(
    sector: Optional[str] = None,
    province: Optional[str] = None,
):
    """Programs whose latest-FY award volume is >20% above the prior year."""
    repo = await get_repo()
    return {"programs": await repo.trending_programs(sector, province)}
