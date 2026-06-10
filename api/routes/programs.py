"""Program matching + trending routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db import get_repo
from features import lookup_naics

router = APIRouter(prefix="/api/programs", tags=["programs"])


class ApplyChatIn(BaseModel):
    question: str
    session_id: Optional[str] = None
    history: list[dict] = []


@router.get("")
async def list_programs(
    q: Optional[str] = None,
    sector: Optional[str] = None,
    province: Optional[str] = None,
    size_band: Optional[str] = None,
    program_type: Optional[str] = None,
    is_open: Optional[bool] = None,
    activity: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    session_id: Optional[str] = None,
    sort: str = "score",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Browse all grant programs with filters, sorting, and pagination."""
    repo = await get_repo()
    profile = None
    if session_id:
        profile = await repo.get_profile(session_id)
    return await repo.search_programs(
        profile=profile,
        q=q,
        sector=sector,
        province=province,
        size_band=size_band,
        program_type=program_type,
        is_open=is_open,
        activity=activity,
        min_amount=min_amount,
        max_amount=max_amount,
        sort=sort,
        limit=limit,
        offset=offset,
    )


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


@router.get("/naics/lookup")
async def naics_lookup(q: str = ""):
    """Look up NAICS codes by prefix or title keyword."""
    return {"codes": lookup_naics(q)}


@router.get("/{program_id}")
async def get_program(program_id: str):
    """Program catalogue record with stats and insights (no award history)."""
    repo = await get_repo()
    detail = await repo.program_detail(program_id, limit=0, offset=0)
    if detail["program"] is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return {
        "program": detail["program"],
        "insights": detail.get("insights") or [],
    }


@router.post("/{program_id}/apply-guide")
async def program_apply_guide(program_id: str, session_id: Optional[str] = None):
    """AI-assisted how-to-apply guide: steps, documents, blockers, and chat seed."""
    repo = await get_repo()
    profile = await repo.get_profile(session_id) if session_id else None
    guide = await repo.program_apply_guide(program_id, profile)
    if guide is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return guide


@router.post("/{program_id}/apply-chat")
async def program_apply_chat(program_id: str, body: ApplyChatIn):
    """Follow-up Q&A in the apply-guide chat for a specific program."""
    if not (body.question or "").strip():
        raise HTTPException(status_code=400, detail="question is required")
    repo = await get_repo()
    profile = None
    if body.session_id:
        profile = await repo.get_profile(body.session_id)
    result = await repo.program_apply_chat(
        program_id, profile, body.question.strip(), body.history or []
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return result


@router.get("/{program_id}/insights")
async def program_insights(program_id: str):
    """Precomputed funding benchmarks and eligibility insights for a program."""
    repo = await get_repo()
    detail = await repo.program_detail(program_id, limit=0, offset=0)
    if detail["program"] is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return {"insights": detail.get("insights") or await repo.program_insights(program_id)}


@router.get("/{program_id}/readiness")
async def program_readiness(program_id: str, session_id: str):
    """Application readiness checklist for a profile × program."""
    repo = await get_repo()
    profile = await repo.get_profile(session_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    result = await repo.program_readiness(profile, program_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return result


@router.get("/{program_id}/overlap")
async def program_overlap(program_id: str, session_id: str):
    """SR&ED / tax credit overlap flags for a profile × program."""
    repo = await get_repo()
    profile = await repo.get_profile(session_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    flags = await repo.program_overlap(profile, program_id)
    return {"flags": flags}
