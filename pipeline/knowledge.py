"""Knowledge layer: raw BBF preservation, metadata enrichment, insights."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

import pandas as pd

from llm import chat_json, llm_available
from utils import PROCESSED_DIR, RAW_DIR, get_logger, read_csv_file, sha256

log = get_logger("pipeline.knowledge")

SOURCES_PATH = PROCESSED_DIR / "grant_program_sources.json"
METADATA_PATH = PROCESSED_DIR / "grant_program_metadata.json"
INSIGHTS_PATH = PROCESSED_DIR / "grant_insights.json"


def _content_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def _row_to_payload(row: pd.Series) -> dict:
    return {str(k): (None if pd.isna(v) else v) for k, v in row.items()}


def _pick_name_from_raw(row: dict) -> str:
    for key in (
        "name", "program_name", "Title - English", "Title - EN",
        "title_en", "Program Name", "program_name_en",
    ):
        v = row.get(key)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def build_program_sources(program_ids_by_name: dict[str, str]) -> list[dict]:
    """Preserve full raw BBF rows alongside canonical program ids."""
    raw_path = PROCESSED_DIR / "bbf_raw.json"
    if not raw_path.exists():
        log.warning("No bbf_raw.json — skipping sources")
        return []
    raw_rows = json.loads(raw_path.read_text(encoding="utf-8"))
    sources: list[dict] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        name = _pick_name_from_raw(row)
        if not name:
            continue
        # Match normalized name via enrich output
        pid = program_ids_by_name.get(name)
        if not pid:
            # Fuzzy: try case-insensitive
            for k, v in program_ids_by_name.items():
                if k.lower() == name.lower():
                    pid = v
                    break
        if not pid:
            continue
        payload = {str(k): (None if v is None else v) for k, v in row.items()}
        sources.append({
            "grant_program_id": pid,
            "source": "bbf",
            "external_id": str(row.get("id") or row.get("program_id") or ""),
            "raw_payload": payload,
            "content_hash": _content_hash(payload),
        })
    return sources


def _heuristic_metadata(name: str, desc: str, stats: Optional[dict]) -> dict:
    text = f"{name}. {desc}"
    words = re.findall(r"[a-z]{4,}", text.lower())
    keywords = sorted(set(w for w in words if w not in {
        "program", "available", "canada", "funding", "grant", "business",
        "companies", "employees", "dollars", "national", "research",
    }))[:12]
    summary = desc[:180].strip()
    if summary and not summary.endswith("."):
        summary += "…"
    steps = ["Review eligibility on the program website"]
    if stats and stats.get("award_count", 0) > 0:
        steps.append("Prepare project plan aligned with previously funded awards")
    steps.append("Gather financial statements and incorporation documents")
    if "r&d" in text.lower() or "research" in text.lower():
        steps.append("Document R&D activities; review SR&ED overlap with tax advisor")
    return {
        "summary_1liner": summary or name,
        "eligibility_narrative": desc[:600] if desc else None,
        "target_audience": "Canadian businesses meeting program eligibility criteria",
        "application_steps": steps,
        "typical_projects": [],
        "stacking_notes": (
            "May coordinate with SR&ED tax credits for R&D activities."
            if "r&d" in text.lower() or "research" in text.lower() else None
        ),
        "keywords": keywords,
        "enrichment_model": "heuristic",
    }


async def _llm_metadata(name: str, desc: str, stats: Optional[dict]) -> dict:
    stats_hint = ""
    if stats:
        stats_hint = (
            f"Award history: {stats.get('award_count', 0)} awards, "
            f"${stats.get('total_disbursed', 0):,.0f} total, "
            f"median ${stats.get('median_award', 0):,.0f}."
        )
    prompt = f"""Analyze this Canadian government grant program and return JSON:
{{
  "summary_1liner": "one sentence value prop",
  "eligibility_narrative": "2-3 sentence eligibility summary",
  "target_audience": "who should apply",
  "application_steps": ["step1", "step2", ...],
  "typical_projects": ["example1", "example2"],
  "stacking_notes": "SR&ED/tax credit notes or null",
  "keywords": ["keyword1", ...]
}}

Program: {name}
Description: {desc[:2000]}
{stats_hint}"""
    try:
        res = await chat_json([{"role": "user", "content": prompt}])
        res["enrichment_model"] = "gpt-4o-mini"
        return res
    except Exception as e:
        log.warning("LLM metadata failed for %s: %s", name, e)
        return _heuristic_metadata(name, desc, stats)


async def enrich_metadata(
    programs: list[dict],
    stats_by_id: dict[str, dict],
) -> list[dict]:
    """Build grant_program_metadata rows."""
    import asyncio
    import os

    use_llm = llm_available() and os.getenv("SKIP_LLM_METADATA", "0") != "1"
    # LLM per-program is costly at scale; heuristic is default for large catalogues
    if use_llm and len(programs) > 100:
        log.info("Catalogue has %s programs — using heuristic metadata (set SKIP_LLM_METADATA=0 and batch separately for LLM)", len(programs))
        use_llm = False

    async def one(p: dict) -> dict:
        pid = p["id"]
        name = p.get("name") or ""
        desc = p.get("description") or p.get("long_description") or ""
        stats = stats_by_id.get(pid)
        if use_llm:
            meta = await _llm_metadata(name, desc, stats)
        else:
            meta = _heuristic_metadata(name, desc, stats)
        return {"grant_program_id": pid, **meta}

    out = []
    batch_size = 50
    for i in range(0, len(programs), batch_size):
        batch = programs[i:i + batch_size]
        out.extend(await asyncio.gather(*[one(p) for p in batch]))
    log.info("Enriched metadata for %s programs (llm=%s)", len(out), use_llm)
    return out


def build_insights(programs: list[dict], stats_by_id: dict[str, dict]) -> list[dict]:
    """Generate cached insight cards from stats (no LLM required)."""
    insights = []
    for p in programs:
        pid = p["id"]
        stats = stats_by_id.get(pid)
        if not stats or stats.get("award_count", 0) == 0:
            continue
        insights.append({
            "grant_program_id": pid,
            "insight_type": "funding_benchmark",
            "audience": {},
            "content": (
                f"{p['name']} has disbursed ${stats['total_disbursed']:,.0f} across "
                f"{stats['award_count']} awards to {stats['recipient_count']} recipients. "
                f"Typical award: ${stats['median_award']:,.0f} (median), "
                f"up to ${stats['largest_award']:,.0f}."
            ),
            "evidence": stats,
            "model": "stats",
        })
        if stats.get("yoy_growth_pct") and stats["yoy_growth_pct"] > 20:
            insights.append({
                "grant_program_id": pid,
                "insight_type": "trending",
                "audience": {},
                "content": (
                    f"Award volume grew {stats['yoy_growth_pct']}% year-over-year — "
                    f"increasing disbursement activity."
                ),
                "evidence": {"yoy_growth_pct": stats["yoy_growth_pct"]},
                "model": "stats",
            })
    log.info("Built %s insight cards", len(insights))
    return insights


def save_knowledge(
    sources: list[dict],
    metadata: list[dict],
    insights: list[dict],
) -> None:
    SOURCES_PATH.write_text(json.dumps(sources, indent=2, default=str), encoding="utf-8")
    METADATA_PATH.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    INSIGHTS_PATH.write_text(json.dumps(insights, indent=2, default=str), encoding="utf-8")
    log.info("Wrote knowledge snapshots: sources, metadata, insights")


async def run(ctx) -> None:
    """Full knowledge pass after stats are computed."""
    from stats import load_stats

    stats_by_id = load_stats()
    id_by_name = {p["name"]: p["id"] for p in ctx.programs}
    sources = build_program_sources(id_by_name)

    # Merge metadata fields onto program records for search
    metadata = await enrich_metadata(ctx.programs, stats_by_id)
    meta_by_id = {m["grant_program_id"]: m for m in metadata}
    for p in ctx.programs:
        m = meta_by_id.get(p["id"], {})
        p["summary_1liner"] = m.get("summary_1liner")
        p["eligibility_narrative"] = m.get("eligibility_narrative")
        p["target_audience"] = m.get("target_audience")
        p["application_steps"] = m.get("application_steps")
        p["stacking_notes"] = m.get("stacking_notes")
        p["keywords"] = m.get("keywords")
        p["content_hash"] = next(
            (s["content_hash"] for s in sources if s["grant_program_id"] == p["id"]),
            None,
        )

    insights = build_insights(ctx.programs, stats_by_id)
    save_knowledge(sources, metadata, insights)
