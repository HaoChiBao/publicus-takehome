"""Award intelligence routes: sector summary + per-program history."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db import get_repo

router = APIRouter(prefix="/api/awards", tags=["awards"])


@router.get("/sector-summary")
async def sector_summary(
    sector: str,
    province: Optional[str] = None,
    years: int = 2,
):
    """Aggregate award intelligence for a sector (optionally a province)."""
    repo = await get_repo()
    return await repo.sector_summary(sector, province, years)


@router.get("/program/{program_id}")
async def program_awards(
    program_id: str,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Program metadata + paginated historical awards, sorted by amount desc."""
    repo = await get_repo()
    result = await repo.program_detail(program_id, limit, offset)
    if result["program"] is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return result
