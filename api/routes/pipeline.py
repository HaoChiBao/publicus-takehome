"""Pipeline observability route — surfaces data-quality awareness in the demo."""
from __future__ import annotations

from fastapi import APIRouter

from db import get_repo

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.get("/status")
async def pipeline_status():
    """The 5 most recent pipeline runs with raw/clean counts + issue breakdown."""
    repo = await get_repo()
    return {"runs": await repo.pipeline_status(limit=5)}
