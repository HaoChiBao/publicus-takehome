"""Compute pre-aggregated grant_program_stats from award history."""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date
from typing import Any, Optional

import pandas as pd

from load import LoadContext, _loose_key
from utils import PROCESSED_DIR, get_logger, iter_csv_chunks

log = get_logger("pipeline.stats")
STATS_PATH = PROCESSED_DIR / "grant_program_stats.json"


def _fiscal_years_sorted(years: list[str]) -> list[str]:
    return sorted({y for y in years if y})


def compute_program_stats(ctx: LoadContext) -> list[dict]:
    """Aggregate award metrics per grant_program id."""
    awards_path = PROCESSED_DIR / "awards_clean.csv"
    if not awards_path.exists():
        log.warning("No awards_clean.csv — skipping stats")
        return []

    # Map loose program name -> program id
    name_to_id: dict[str, str] = {}
    for p in ctx.programs:
        name_to_id[_loose_key(p["name"])] = p["id"]

    usecols = [
        "program_name_raw", "amount", "province", "naics_code", "fiscal_year",
        "end_date", "recipient_canonical", "is_latest_amendment",
    ]
    agg: dict[str, dict[str, Any]] = {}
    for chunk in iter_csv_chunks(awards_path, chunksize=100_000, usecols=usecols):
        for _, a in chunk.iterrows():
            if not a.get("is_latest_amendment"):
                continue
            key = _loose_key(str(a.get("program_name_raw") or ""))
            pid = name_to_id.get(key)
            if not pid:
                continue
            g = agg.setdefault(pid, {
                "amounts": [],
                "provinces": set(),
                "sectors": set(),
                "naics": set(),
                "recipients": set(),
                "by_fy": defaultdict(float),
                "last_date": None,
            })
            amt = a.get("amount")
            if amt is not None and not (isinstance(amt, float) and pd.isna(amt)):
                try:
                    val = float(amt)
                    if val > 0:
                        g["amounts"].append(val)
                        fy = a.get("fiscal_year")
                        if fy and not (isinstance(fy, float) and pd.isna(fy)):
                            g["by_fy"][str(fy)] += val
                except (TypeError, ValueError):
                    pass
            prog_raw = str(a.get("program_name_raw") or "")
            sect_from_map = ctx.sector_map.get(prog_raw)
            if sect_from_map:
                g["sectors"].add(sect_from_map)
            prov = a.get("province")
            if prov and str(prov) not in ("nan", "None", ""):
                g["provinces"].add(str(prov))
            # sector applied at load via sector_map; optional column if present
            sect = a.get("sector_normalized") if "sector_normalized" in a.index else None
            if sect and str(sect) not in ("nan", "None", ""):
                g["sectors"].add(str(sect))
            naics = a.get("naics_code")
            if naics and str(naics) not in ("nan", "None", ""):
                g["naics"].add(str(naics)[:4])
            rec = a.get("recipient_canonical")
            if rec and str(rec) not in ("nan", "None", ""):
                g["recipients"].add(str(rec))
            end = a.get("end_date")
            if end and str(end) not in ("nan", "None", "", "NaT"):
                try:
                    d = pd.to_datetime(end).date()
                    if g["last_date"] is None or d > g["last_date"]:
                        g["last_date"] = d
                except Exception:
                    pass

    out: list[dict] = []
    for pid, g in agg.items():
        amounts = g["amounts"]
        if not amounts:
            continue
        amounts_sorted = sorted(amounts)
        n = len(amounts_sorted)
        median = statistics.median(amounts_sorted)
        p90_idx = min(n - 1, int(n * 0.9))
        by_fy = dict(g["by_fy"])
        years = _fiscal_years_sorted(list(by_fy.keys()))
        yoy = None
        if len(years) >= 2:
            prev, latest = years[-2], years[-1]
            prev_t, latest_t = by_fy.get(prev, 0), by_fy.get(latest, 0)
            if prev_t > 0:
                yoy = round((latest_t - prev_t) / prev_t * 100, 2)

        out.append({
            "grant_program_id": pid,
            "total_disbursed": round(sum(amounts), 2),
            "award_count": n,
            "recipient_count": len(g["recipients"]),
            "avg_award": round(sum(amounts) / n, 2),
            "median_award": round(median, 2),
            "p90_award": round(amounts_sorted[p90_idx], 2),
            "largest_award": round(max(amounts), 2),
            "provinces_active": sorted(g["provinces"]),
            "sectors_active": sorted(g["sectors"]),
            "naics_top_prefixes": sorted(g["naics"])[:10],
            "yoy_growth_pct": yoy,
            "last_award_date": g["last_date"].isoformat() if g["last_date"] else None,
            "award_by_fiscal_year": [
                {"year": y, "total": round(by_fy[y], 2)} for y in years
            ],
            "top_recipient_names": [],
        })

    log.info("Computed stats for %s programs with award history", len(out))
    return out


def save_stats(stats: list[dict]) -> None:
    STATS_PATH.write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s -> %s", len(stats), STATS_PATH.name)


def load_stats() -> dict[str, dict]:
    if not STATS_PATH.exists():
        return {}
    rows = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    return {r["grant_program_id"]: r for r in rows}
