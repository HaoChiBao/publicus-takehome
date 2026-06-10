"""Profile creation + the aggregated dashboard endpoint.

The dashboard endpoint reads the company profile for a session and fans out to
the match / sector-summary / trending logic, returning everything the dashboard
needs in a single request. Results are cached in-memory for 1 hour per session.
"""
from __future__ import annotations

import csv
import io
import time
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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
    naics_code: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/profile")
async def create_profile(profile: ProfileIn):
    """Create (or upsert) a session-based company profile."""
    repo = await get_repo()
    session_id = profile.session_id or f"sess_{uuid.uuid4().hex[:16]}"
    saved = await repo.create_profile({**profile.model_dump(), "session_id": session_id})
    _CACHE.pop(session_id, None)
    return {"session_id": session_id, "profile": saved}


@router.get("/dashboard/{session_id}")
async def dashboard(session_id: str):
    """Aggregated dashboard payload with matches, intel, alerts, and peers."""
    cached = _CACHE.get(session_id)
    if cached and time.time() - cached[0] < _TTL_SECONDS:
        return cached[1]

    repo = await get_repo()
    profile = await repo.get_profile(session_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    sector = profile.get("sector")
    province = profile.get("province")
    matches = await repo.match_programs(profile, limit=10)
    summary = (
        await repo.sector_summary(sector, province, years=2)
        if sector
        else {
            "sector": sector,
            "province": province,
            "total_amount": 0,
            "award_count": 0,
            "avg_amount": 0,
            "top_programs": [],
            "by_fiscal_year": [],
            "top_recipients": [],
        }
    )
    trending = (
        await repo.trending_programs(sector, province) if sector else []
    )
    alerts = await repo.get_alerts(profile, days=90)
    peers = await repo.get_similar_recipients(profile, limit=8)

    payload = {
        "profile": profile,
        "matches": matches,
        "sector_summary": summary,
        "trending": trending,
        "alerts": alerts,
        "peers": peers,
    }
    _CACHE[session_id] = (time.time(), payload)
    return payload


@router.get("/dashboard/{session_id}/export")
async def export_dashboard(session_id: str):
    """CSV export of dashboard intelligence for board / investor reports."""
    repo = await get_repo()
    profile = await repo.get_profile(session_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    matches = await repo.match_programs(profile, limit=50)
    summary = await repo.sector_summary(profile["sector"], profile.get("province"), years=2)
    trending = await repo.trending_programs(profile["sector"], profile.get("province"))
    peers = await repo.get_similar_recipients(profile, limit=20)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Publicus Grants Intelligence Report"])
    w.writerow(["Generated", date.today().isoformat()])
    w.writerow([])

    w.writerow(["Company Profile"])
    w.writerow(["Name", profile.get("name") or ""])
    w.writerow(["Sector", profile.get("sector") or ""])
    w.writerow(["Province", profile.get("province") or ""])
    w.writerow(["Size Band", profile.get("size_band") or ""])
    w.writerow(["NAICS", profile.get("naics_code") or ""])
    w.writerow(["Activities", ", ".join(profile.get("activities") or [])])
    w.writerow([])

    w.writerow(["Grant Matches"])
    w.writerow(["Program", "Score", "Department", "Type", "Min", "Max", "Deadline", "Apply URL", "Reasons"])
    for m in matches:
        w.writerow([
            m.get("name"), m.get("score"), m.get("department"), m.get("program_type"),
            m.get("min_amount"), m.get("max_amount"), m.get("deadline"),
            m.get("apply_url"), "; ".join(m.get("match_reasons") or []),
        ])
    w.writerow([])

    w.writerow(["Sector Intelligence"])
    w.writerow(["Total Disbursed", summary.get("total_amount")])
    w.writerow(["Award Count", summary.get("award_count")])
    w.writerow(["Average Award", summary.get("avg_amount")])
    w.writerow([])

    w.writerow(["Trending Programs"])
    w.writerow(["Program", "YoY %", "Latest FY Total", "Previous FY Total"])
    for t in trending:
        w.writerow([t.get("name"), t.get("yoy_change_pct"), t.get("latest_total"), t.get("previous_total")])
    w.writerow([])

    w.writerow(["Similar Companies"])
    w.writerow(["Company", "Similarity", "Province", "Total Received", "Awards", "Programs Won"])
    for p in peers:
        w.writerow([
            p.get("name"), p.get("similarity_score"), p.get("province"),
            p.get("total_amount"), p.get("award_count"),
            "; ".join(p.get("programs_in_common") or []),
        ])

    buf.seek(0)
    filename = f"publicus-grants-report-{session_id[:12]}-{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
