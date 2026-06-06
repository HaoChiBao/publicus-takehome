"""Stage 5 — Load cleaned + enriched data into Supabase (Postgres).

Reads the processed checkpoints produced by the earlier stages and writes the
final relational records into `recipients`, `grant_programs`, and `grant_awards`,
wiring up the foreign keys (recipient_id, program_id) along the way.

Connection: uses DATABASE_URL (asyncpg). A Supabase pooler URL works directly.
A local JSON snapshot of every table is always written to data/processed/ so the
load is inspectable and the frontend can be demoed without a live DB.

Offline mode (USE_SAMPLE_DATA=1 or no DATABASE_URL): snapshot only, no DB writes.
"""
from __future__ import annotations

import ast
import json
import os
import uuid
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from utils import (
    PROCESSED_DIR, USE_SAMPLE_DATA, get_logger, log_pipeline_run,
)

log = get_logger("pipeline.load")


def _as_list(value: Any) -> Optional[list]:
    """Parse a cell that may hold a Python-list repr string, JSON, or scalar."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, list):
        return value
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        parsed = ast.literal_eval(s)
        return list(parsed) if isinstance(parsed, (list, tuple)) else [parsed]
    except (ValueError, SyntaxError):
        return [s]


def _num(value: Any) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _str(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s or None


def _loose_key(name: str) -> str:
    """Loose program key: drop parentheticals + punctuation for fuzzy joins.

    e.g. 'Industrial Research Assistance Program (IRAP)' -> 'industrial research
    assistance program', which then matches award names lacking the acronym.
    """
    import re
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)          # drop "(IRAP)" etc.
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Build relational records (with generated UUIDs + FK wiring)
# ---------------------------------------------------------------------------
def build_records() -> dict[str, list[dict]]:
    awards_df = pd.read_csv(PROCESSED_DIR / "awards_clean.csv")
    rec_df = pd.read_csv(PROCESSED_DIR / "recipients.csv")
    prog_path = PROCESSED_DIR / "programs_enriched.csv"
    prog_df = pd.read_csv(prog_path) if prog_path.exists() else pd.DataFrame()

    # --- recipients ---
    recipients, recipient_id_by_name = [], {}
    for _, r in rec_df.iterrows():
        rid = str(uuid.uuid4())
        name = _str(r["name_normalized"])
        recipient_id_by_name[name] = rid
        recipients.append({
            "id": rid,
            "name_normalized": name,
            "names_raw": _as_list(r.get("names_raw")),
            "business_number": _str(r.get("business_number")),
            "province": _str(r.get("province")),
            "city": _str(r.get("city")),
        })

    # --- programs: derive eligible_sectors from award sectors on the same name ---
    awards_df["_loose_prog"] = awards_df["program_name_raw"].fillna("").map(_loose_key)
    sectors_by_prog = (
        awards_df[awards_df["_loose_prog"] != ""]
        .groupby("_loose_prog")["sector_normalized"]
        .agg(lambda s: sorted(set(x for x in s if isinstance(x, str))))
        .to_dict()
    )
    programs, program_id_by_norm, program_id_by_loose = [], {}, {}
    for _, p in prog_df.iterrows():
        pid = str(uuid.uuid4())
        name = _str(p.get("program_name")) or _str(p.get("name"))
        norm = (name or "").lower().strip()
        program_id_by_norm[norm] = pid
        program_id_by_loose[_loose_key(name or "")] = pid
        programs.append({
            "id": pid,
            "source": "bbf",
            "name": name,
            "department": _str(p.get("department")),
            "program_type": _str(p.get("program_type")),
            "description": _str(p.get("description")),
            "min_amount": _num(p.get("min_amount")),
            "max_amount": _num(p.get("max_amount")),
            "eligible_provinces": _as_list(p.get("eligible_provinces")),
            "eligible_sectors": sectors_by_prog.get(_loose_key(name or "")) or [],
            "eligible_sizes": _as_list(p.get("eligible_sizes")),
            "eligible_activities": _as_list(p.get("eligible_activities")),
            "deadline": None,
            "is_open": True,
            "apply_url": _str(p.get("apply_url")),
            "last_updated": pd.Timestamp.now().date().isoformat(),
        })

    # --- awards: wire recipient_id + best-effort program_id ---
    awards = []
    for _, a in awards_df.iterrows():
        canonical = _str(a.get("recipient_canonical"))
        norm = _str(a.get("program_name_normalized")) or ""
        pid = program_id_by_norm.get(norm) or program_id_by_loose.get(
            _loose_key(_str(a.get("program_name_raw")) or "")
        )
        awards.append({
            "id": str(uuid.uuid4()),
            "source": _str(a.get("source")),
            "ref_number": _str(a.get("ref_number")),
            "amendment_number": int(a.get("amendment_number") or 0),
            "is_latest_amendment": bool(a.get("is_latest_amendment")),
            "recipient_id": recipient_id_by_name.get(canonical),
            "recipient_name_raw": _str(a.get("recipient_name_raw")),
            "department": _str(a.get("department")),
            "program_name_raw": _str(a.get("program_name_raw")),
            "program_name_normalized": norm or None,
            "program_id": pid,
            "agreement_type": _str(a.get("agreement_type")),
            "amount": _num(a.get("amount")),
            "province": _str(a.get("province")),
            "city": _str(a.get("city")),
            "naics_code": _str(a.get("naics_code")),
            "sector_normalized": _str(a.get("sector_normalized")),
            "fiscal_year": _str(a.get("fiscal_year")),
            "start_date": _str(a.get("start_date")),
            "end_date": _str(a.get("end_date")),
            "description": _str(a.get("description")),
        })

    return {"recipients": recipients, "grant_programs": programs, "grant_awards": awards}


# ---------------------------------------------------------------------------
# Snapshot (always) + DB write (when configured)
# ---------------------------------------------------------------------------
def write_snapshot(records: dict[str, list[dict]]) -> None:
    for table, rows in records.items():
        path = PROCESSED_DIR / f"db_{table}.json"
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
        log.info("Snapshot: %s rows -> %s", len(rows), path.name)


async def write_to_db(records: dict[str, list[dict]]) -> None:
    import asyncpg

    dsn = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(dsn)
    try:
        # Idempotent reload — clear in FK-safe order.
        await conn.execute(
            "TRUNCATE grant_awards, grant_programs, recipients RESTART IDENTITY CASCADE"
        )

        await conn.executemany(
            """INSERT INTO recipients (id, name_normalized, names_raw, business_number, province, city)
               VALUES ($1,$2,$3,$4,$5,$6)""",
            [(r["id"], r["name_normalized"], r["names_raw"], r["business_number"],
              r["province"], r["city"]) for r in records["recipients"]],
        )
        log.info("Inserted %s recipients", len(records["recipients"]))

        await conn.executemany(
            """INSERT INTO grant_programs
               (id, source, name, department, program_type, description, min_amount, max_amount,
                eligible_provinces, eligible_sectors, eligible_sizes, eligible_activities,
                deadline, is_open, apply_url, last_updated)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)""",
            [(p["id"], p["source"], p["name"], p["department"], p["program_type"], p["description"],
              p["min_amount"], p["max_amount"], p["eligible_provinces"], p["eligible_sectors"],
              p["eligible_sizes"], p["eligible_activities"],
              _date(p["deadline"]), p["is_open"], p["apply_url"], _date(p["last_updated"]))
             for p in records["grant_programs"]],
        )
        log.info("Inserted %s grant_programs", len(records["grant_programs"]))

        await conn.executemany(
            """INSERT INTO grant_awards
               (id, source, ref_number, amendment_number, is_latest_amendment, recipient_id,
                recipient_name_raw, department, program_name_raw, program_name_normalized, program_id,
                agreement_type, amount, province, city, naics_code, sector_normalized, fiscal_year,
                start_date, end_date, description)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)""",
            [(a["id"], a["source"], a["ref_number"], a["amendment_number"], a["is_latest_amendment"],
              a["recipient_id"], a["recipient_name_raw"], a["department"], a["program_name_raw"],
              a["program_name_normalized"], a["program_id"], a["agreement_type"], a["amount"],
              a["province"], a["city"], a["naics_code"], a["sector_normalized"], a["fiscal_year"],
              _date(a["start_date"]), _date(a["end_date"]), a["description"])
             for a in records["grant_awards"]],
        )
        log.info("Inserted %s grant_awards", len(records["grant_awards"]))
    finally:
        await conn.close()


def _date(value):
    """asyncpg wants a date object for DATE columns; pass None through."""
    if not value:
        return None
    from datetime import date, datetime
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


async def run() -> None:
    records = build_records()
    write_snapshot(records)

    has_db = bool(os.getenv("DATABASE_URL")) and not USE_SAMPLE_DATA
    if has_db:
        try:
            await write_to_db(records)
        except Exception as e:  # noqa: BLE001
            log.error("DB load failed (%s). Snapshot is still available locally.", e)
            raise
    else:
        log.info("No DATABASE_URL / offline mode — wrote local snapshot only.")

    log_pipeline_run(
        "load",
        sum(len(v) for v in records.values()),
        sum(len(v) for v in records.values()),
        0,
        {k: len(v) for k, v in records.items()},
    )


if __name__ == "__main__":
    import asyncio
    asyncio.run(run())
