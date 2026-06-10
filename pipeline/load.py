"""Stage 5 — Load cleaned + enriched data into Supabase (Postgres).

Reads the processed checkpoints produced by the earlier stages and writes the
final relational records into `recipients`, `grant_programs`, and `grant_awards`,
wiring up the foreign keys (recipient_id, program_id) along the way.

Connection: uses DATABASE_URL (asyncpg). A Supabase pooler URL works directly.
A local JSON snapshot of recipients + programs is written to data/processed/.
Award rows are streamed from awards_clean.csv (too large to hold in memory).

When DATABASE_URL is unset, writes local snapshots only (no DB writes).
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
    PROCESSED_DIR, VALID_PROVINCE_CODES, get_logger, iter_csv_chunks,
    log_pipeline_run, normalize_province, read_csv_file,
)
from enrich import _normalize_bbf_columns

log = get_logger("pipeline.load")

AWARD_BATCH = 5_000
INSERT_BATCH = 2_000


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
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    return s


def _province_code(value: Any) -> Optional[str]:
    """Normalize to a 2-letter province code for CHAR(2) columns, or NULL."""
    s = _str(value)
    if not s:
        return None
    code = s.upper()
    if len(code) == 2 and code in VALID_PROVINCE_CODES:
        return code
    mapped = normalize_province(s)
    if mapped and mapped in VALID_PROVINCE_CODES:
        return mapped
    return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _bbf_is_open(row: Any) -> bool:
    status = _str(row.get("status")) or ""
    if not status:
        return True
    lowered = status.lower()
    if any(x in lowered for x in ("closed", "expired", "not available", "inactive")):
        return False
    return True


def _loose_key(name: str) -> str:
    """Loose program key: drop parentheticals + punctuation for fuzzy joins."""
    import re
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _date(value):
    """asyncpg wants a date object for DATE columns; pass None through."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null", "nat"}:
        return None
    from datetime import date, datetime
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(s).date()


class LoadContext:
    """Lookup tables produced while building recipients + programs."""

    def __init__(
        self,
        recipients: list[dict],
        programs: list[dict],
        recipient_id_by_name: dict[str, str],
        program_id_by_norm: dict[str, str],
        program_id_by_loose: dict[str, str],
        sector_map: dict[str, str],
    ):
        self.recipients = recipients
        self.programs = programs
        self.recipient_id_by_name = recipient_id_by_name
        self.program_id_by_norm = program_id_by_norm
        self.program_id_by_loose = program_id_by_loose
        self.sector_map = sector_map
        self.award_count = 0


def _snapshot_ids(filename: str, key: str) -> dict[str, str]:
    """Reuse UUIDs from a prior db_*.json snapshot so IDs stay stable across reloads."""
    path = PROCESSED_DIR / filename
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out: dict[str, str] = {}
    for row in rows:
        k = row.get(key)
        rid = row.get("id")
        if k and rid:
            out[str(k).strip()] = str(rid)
    return out


def _read_programs_df() -> pd.DataFrame:
    """Load programs_enriched.csv, normalizing raw BBF column names when needed."""
    prog_path = PROCESSED_DIR / "programs_enriched.csv"
    if not prog_path.exists():
        return pd.DataFrame()
    raw = read_csv_file(prog_path)
    if "name" in raw.columns and raw["name"].fillna("").astype(str).str.strip().ne("").any():
        return raw
    base = _normalize_bbf_columns(raw)
    for col in (
        "eligible_provinces", "eligible_sizes", "eligible_activities",
        "min_amount", "max_amount", "program_type", "sred_related", "tax_credit_type",
    ):
        if col in raw.columns:
            aligned = raw.loc[raw.index.isin(base.index), col] if len(base) == len(raw) else raw[col]
            if len(aligned) == len(base):
                base[col] = aligned.values
            else:
                # Re-align by position after template-row drop
                trimmed = raw.iloc[: len(base)][col] if len(raw) >= len(base) else raw[col]
                base[col] = trimmed.reset_index(drop=True).values[: len(base)]
    return base


def build_context() -> LoadContext:
    rec_df = read_csv_file(PROCESSED_DIR / "recipients.csv")
    prog_df = _read_programs_df()

    sector_map: dict[str, str] = {}
    sector_map_path = PROCESSED_DIR / "program_sector_map.json"
    if sector_map_path.exists():
        sector_map = json.loads(sector_map_path.read_text(encoding="utf-8"))

    recipient_ids = _snapshot_ids("db_recipients.json", "name_normalized")
    program_ids = _snapshot_ids("db_grant_programs.json", "name")

    recipients, recipient_id_by_name = [], {}
    skipped_recipients = 0
    for _, r in rec_df.iterrows():
        name = _str(r["name_normalized"])
        if not name:
            skipped_recipients += 1
            continue
        rid = recipient_ids.get(name) or str(uuid.uuid4())
        recipient_id_by_name[name] = rid
        recipients.append({
            "id": rid,
            "name_normalized": name,
            "names_raw": _as_list(r.get("names_raw")),
            "business_number": _str(r.get("business_number")),
            "province": _province_code(r.get("province")),
            "city": _str(r.get("city")),
        })
    if skipped_recipients:
        log.warning("Skipped %s recipients with empty name_normalized", skipped_recipients)

    sectors_by_prog: dict[str, list[str]] = {}
    for prog_name, sector in sector_map.items():
        key = _loose_key(prog_name)
        if not key or not sector:
            continue
        bucket = sectors_by_prog.setdefault(key, [])
        if sector not in bucket:
            bucket.append(sector)
    for key in sectors_by_prog:
        sectors_by_prog[key] = sorted(sectors_by_prog[key])

    programs, program_id_by_norm, program_id_by_loose = [], {}, {}
    skipped_programs = 0
    seen_program_names: set[str] = set()
    for _, p in prog_df.iterrows():
        name = _str(p.get("name")) or _str(p.get("program_name"))
        if not name:
            skipped_programs += 1
            continue
        norm = name.lower().strip()
        if norm in seen_program_names:
            skipped_programs += 1
            continue
        seen_program_names.add(norm)
        pid = program_ids.get(name) or str(uuid.uuid4())
        program_id_by_norm[norm] = pid
        program_id_by_loose[_loose_key(name)] = pid
        desc = _str(p.get("description"))
        programs.append({
            "id": pid,
            "source": "bbf",
            "name": name,
            "department": _str(p.get("department")),
            "program_type": _str(p.get("program_type")),
            "description": desc,
            "short_description": desc[:300] if desc else None,
            "long_description": desc,
            "min_amount": _num(p.get("min_amount")),
            "max_amount": _num(p.get("max_amount")),
            "eligible_provinces": _as_list(p.get("eligible_provinces")),
            "eligible_sectors": sectors_by_prog.get(_loose_key(name)) or [],
            "eligible_sizes": _as_list(p.get("eligible_sizes")),
            "eligible_activities": _as_list(p.get("eligible_activities")),
            "deadline": _str(p.get("deadline")) or None,
            "status": _str(p.get("status")),
            "is_open": _bbf_is_open(p),
            "sred_related": bool(p.get("sred_related")),
            "tax_credit_type": _str(p.get("tax_credit_type")),
            "apply_url": _str(p.get("apply_url")),
            "source_url": _str(p.get("apply_url")),
            "last_updated": pd.Timestamp.now().date().isoformat(),
        })
    if skipped_programs:
        log.warning("Skipped %s programs with empty name", skipped_programs)

    return LoadContext(
        recipients, programs, recipient_id_by_name,
        program_id_by_norm, program_id_by_loose, sector_map,
    )


def _award_row(a: Any, ctx: LoadContext) -> tuple:
    canonical = _str(a.get("recipient_canonical"))
    prog_raw = _str(a.get("program_name_raw"))
    norm = (prog_raw or "").lower().strip()
    sector = ctx.sector_map.get(prog_raw or "", "OTHER")
    pid = ctx.program_id_by_norm.get(norm) or ctx.program_id_by_loose.get(
        _loose_key(prog_raw or "")
    )
    return (
        str(uuid.uuid4()),
        _str(a.get("source")),
        _str(a.get("ref_number")),
        int(a.get("amendment_number") or 0),
        _bool(a.get("is_latest_amendment")),
        ctx.recipient_id_by_name.get(canonical),
        _str(a.get("recipient_name_raw")),
        _str(a.get("department")),
        prog_raw,
        norm or None,
        pid,
        _str(a.get("agreement_type")),
        _num(a.get("amount")),
        _province_code(a.get("province")),
        _str(a.get("city")),
        _str(a.get("naics_code")),
        sector,
        _str(a.get("fiscal_year")),
        _date(a.get("start_date")),
        _date(a.get("end_date")),
        _str(a.get("description")),
    )


def write_snapshot(ctx: LoadContext) -> None:
    for table, rows in (
        ("recipients", ctx.recipients),
        ("grant_programs", ctx.programs),
    ):
        path = PROCESSED_DIR / f"db_{table}.json"
        path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        log.info("Snapshot: %s rows -> %s", len(rows), path.name)

    for extra in (
        "grant_program_stats.json",
        "grant_program_sources.json",
        "grant_program_metadata.json",
        "grant_insights.json",
        "grant_content_chunks.json",
        "grant_embeddings.json",
    ):
        src = PROCESSED_DIR / extra
        if src.exists():
            dst = PROCESSED_DIR / f"db_{extra}"
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            log.info("Snapshot: %s", dst.name)


async def _executemany_batched(conn, sql: str, rows: list[tuple], label: str) -> None:
    for i in range(0, len(rows), INSERT_BATCH):
        batch = rows[i:i + INSERT_BATCH]
        await conn.executemany(sql, batch)
        log.info("Inserted %s %s (%s / %s)", len(batch), label, i + len(batch), len(rows))


async def write_to_db(ctx: LoadContext) -> None:
    import asyncpg

    dsn = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(dsn)
    awards_path = PROCESSED_DIR / "awards_clean.csv"
    insert_awards_sql = """
        INSERT INTO grant_awards
        (id, source, ref_number, amendment_number, is_latest_amendment, recipient_id,
         recipient_name_raw, department, program_name_raw, program_name_normalized, program_id,
         agreement_type, amount, province, city, naics_code, sector_normalized, fiscal_year,
         start_date, end_date, description)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)
    """
    awards_only = os.getenv("LOAD_AWARDS_ONLY")
    skip_awards = os.getenv("SKIP_AWARDS")
    try:
        if awards_only:
            log.info("LOAD_AWARDS_ONLY=1 — uploading grant_awards only")
            await conn.execute("TRUNCATE grant_awards RESTART IDENTITY")
        else:
            await conn.execute("""
                TRUNCATE grant_embeddings, grant_content_chunks, grant_insights,
                         grant_program_metadata, grant_program_sources, grant_program_stats,
                         grant_awards, grant_programs, recipients RESTART IDENTITY CASCADE
            """)

            # Programs first (small) so grant search works even if later stages are slow.
            await _executemany_batched(
                conn,
                """INSERT INTO grant_programs
                   (id, source, name, department, program_type, description,
                    short_description, long_description, status,
                    min_amount, max_amount, eligible_provinces, eligible_sectors,
                    eligible_sizes, eligible_activities, eligible_naics_prefixes,
                    deadline, is_open, sred_related, tax_credit_type, apply_url, source_url,
                    summary_1liner, eligibility_narrative, target_audience,
                    application_steps, stacking_notes, keywords, content_hash, last_updated)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                           $17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30)""",
                [(p["id"], p["source"], p["name"], p["department"], p["program_type"],
                  p.get("description"), p.get("short_description"), p.get("long_description"),
                  p.get("status"), p["min_amount"], p["max_amount"],
                  p["eligible_provinces"], p["eligible_sectors"], p["eligible_sizes"],
                  p["eligible_activities"], p.get("eligible_naics_prefixes"),
                  _date(p["deadline"]), p["is_open"], p.get("sred_related", False),
                  p.get("tax_credit_type"), p["apply_url"], p.get("source_url"),
                  p.get("summary_1liner"), p.get("eligibility_narrative"),
                  p.get("target_audience"), p.get("application_steps"),
                  p.get("stacking_notes"), p.get("keywords"), p.get("content_hash"),
                  _date(p["last_updated"]))
                 for p in ctx.programs],
                "grant_programs",
            )

            for p in ctx.programs:
                await conn.execute("SELECT refresh_program_search_vector($1)", p["id"])

            await _load_knowledge_tables(conn)

            await _executemany_batched(
                conn,
                """INSERT INTO recipients (id, name_normalized, names_raw, business_number, province, city)
                   VALUES ($1,$2,$3,$4,$5,$6)""",
                [(r["id"], r["name_normalized"], r["names_raw"], r["business_number"],
                  r["province"], r["city"]) for r in ctx.recipients],
                "recipients",
            )

        if awards_only or not skip_awards:
            batch: list[tuple] = []
            for chunk in iter_csv_chunks(awards_path, chunksize=100_000):
                for _, a in chunk.iterrows():
                    batch.append(_award_row(a, ctx))
                    if len(batch) >= AWARD_BATCH:
                        await conn.executemany(insert_awards_sql, batch)
                        ctx.award_count += len(batch)
                        log.info("Inserted %s grant_awards so far", ctx.award_count)
                        batch.clear()
            if batch:
                await conn.executemany(insert_awards_sql, batch)
                ctx.award_count += len(batch)
                log.info("Inserted %s grant_awards total", ctx.award_count)
        elif skip_awards:
            log.info("SKIP_AWARDS=1 — skipping grant_awards upload")

        if not awards_only:
            await _migrate_session_data(conn)
    finally:
        await conn.close()


async def _load_json(name: str) -> list:
    path = PROCESSED_DIR / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


async def _load_knowledge_tables(conn) -> None:
    """Load stats, sources, metadata, chunks, embeddings, insights into Postgres."""
    try:
        await conn.fetchval("SELECT 1 FROM grant_program_stats LIMIT 1")
    except Exception:
        log.warning(
            "Knowledge tables missing — run supabase/migrations/002_search_and_knowledge.sql first"
        )
        return

    stats = await _load_json("grant_program_stats.json")
    if stats:
        await conn.executemany(
            """INSERT INTO grant_program_stats
               (grant_program_id, total_disbursed, award_count, recipient_count,
                avg_award, median_award, p90_award, largest_award,
                provinces_active, sectors_active, naics_top_prefixes,
                yoy_growth_pct, last_award_date, award_by_fiscal_year, top_recipient_names)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)""",
            [(s["grant_program_id"], s["total_disbursed"], s["award_count"],
              s["recipient_count"], s["avg_award"], s["median_award"], s["p90_award"],
              s["largest_award"], s["provinces_active"], s["sectors_active"],
              s["naics_top_prefixes"], s.get("yoy_growth_pct"),
              _date(s.get("last_award_date")),
              json.dumps(s.get("award_by_fiscal_year", [])),
              s.get("top_recipient_names") or []) for s in stats],
        )
        log.info("Inserted %s grant_program_stats", len(stats))

    sources = await _load_json("grant_program_sources.json")
    if sources:
        await conn.executemany(
            """INSERT INTO grant_program_sources
               (grant_program_id, source, external_id, raw_payload, content_hash)
               VALUES ($1,$2,$3,$4::jsonb,$5)""",
            [(s["grant_program_id"], s["source"], s.get("external_id") or None,
              json.dumps(s["raw_payload"], default=str), s["content_hash"]) for s in sources],
        )
        log.info("Inserted %s grant_program_sources", len(sources))

    metadata = await _load_json("grant_program_metadata.json")
    if metadata:
        await conn.executemany(
            """INSERT INTO grant_program_metadata
               (grant_program_id, summary_1liner, eligibility_narrative, target_audience,
                application_steps, typical_projects, stacking_notes, keywords, enrichment_model)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            [(m["grant_program_id"], m.get("summary_1liner"), m.get("eligibility_narrative"),
              m.get("target_audience"), m.get("application_steps"),
              m.get("typical_projects"), m.get("stacking_notes"),
              m.get("keywords"), m.get("enrichment_model")) for m in metadata],
        )
        log.info("Inserted %s grant_program_metadata", len(metadata))

    chunks = await _load_json("grant_content_chunks.json")
    if chunks:
        import uuid as _uuid
        await conn.executemany(
            """INSERT INTO grant_content_chunks
               (id, grant_program_id, chunk_index, chunk_type, content, token_estimate)
               VALUES ($1,$2,$3,$4,$5,$6)""",
            [(str(_uuid.uuid4()), c["grant_program_id"], c["chunk_index"],
              c["chunk_type"], c["content"], c.get("token_estimate")) for c in chunks],
        )
        log.info("Inserted %s grant_content_chunks", len(chunks))

    embeddings = await _load_json("grant_embeddings.json")
    if embeddings:
        import uuid as _uuid
        await conn.executemany(
            """INSERT INTO grant_embeddings
               (id, entity_type, entity_id, model, embedding, content_text, metadata)
               VALUES ($1,$2,$3,$4,$5::vector,$6,$7::jsonb)""",
            [(str(_uuid.uuid4()), e["entity_type"], e["entity_id"], e["model"],
              str(e["embedding"]), e.get("content_text"), "{}") for e in embeddings],
        )
        log.info("Inserted %s grant_embeddings", len(embeddings))

    insights = await _load_json("grant_insights.json")
    if insights:
        import uuid as _uuid
        await conn.executemany(
            """INSERT INTO grant_insights
               (id, grant_program_id, insight_type, audience, content, evidence, model)
               VALUES ($1,$2,$3,$4::jsonb,$5,$6::jsonb,$7)""",
            [(str(_uuid.uuid4()), i["grant_program_id"], i["insight_type"],
              json.dumps(i.get("audience", {})), i["content"],
              json.dumps(i.get("evidence", {}), default=str), i.get("model")) for i in insights],
        )
        log.info("Inserted %s grant_insights", len(insights))


async def _migrate_session_data(conn) -> None:
    """Import company profiles + watchlist from local JSON snapshots into Postgres."""
    profiles_path = PROCESSED_DIR / "db_company_profiles.json"
    if profiles_path.exists():
        profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
        for p in profiles:
            sid = p.get("session_id")
            if not sid:
                continue
            await conn.execute(
                """INSERT INTO company_profiles
                   (session_id, name, sector, province, size_band, activities, naics_code)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)
                   ON CONFLICT (session_id) DO UPDATE SET
                     name=EXCLUDED.name, sector=EXCLUDED.sector, province=EXCLUDED.province,
                     size_band=EXCLUDED.size_band, activities=EXCLUDED.activities,
                     naics_code=EXCLUDED.naics_code""",
                sid, p.get("name"), p.get("sector"), _province_code(p.get("province")),
                p.get("size_band"), p.get("activities") or [], p.get("naics_code"),
            )
        log.info("Migrated %s company profiles from db_company_profiles.json", len(profiles))

    watchlist_path = PROCESSED_DIR / "db_watchlist_items.json"
    if watchlist_path.exists():
        items = json.loads(watchlist_path.read_text(encoding="utf-8"))
        valid_programs = {
            str(r["id"])
            for r in await conn.fetch("SELECT id FROM grant_programs")
        }
        valid_recipients = {
            str(r["id"])
            for r in await conn.fetch("SELECT id FROM recipients")
        }
        migrated = 0
        for w in items:
            sid = w.get("session_id")
            etype = w.get("entity_type")
            eid = str(w.get("entity_id", ""))
            if not sid or etype not in ("program", "recipient") or not eid:
                continue
            valid = valid_programs if etype == "program" else valid_recipients
            if eid not in valid:
                continue
            await conn.execute(
                """INSERT INTO watchlist_items (session_id, entity_type, entity_id)
                   VALUES ($1,$2,$3)
                   ON CONFLICT (session_id, entity_type, entity_id) DO NOTHING""",
                sid, etype, eid,
            )
            migrated += 1
        log.info("Migrated %s watchlist items from db_watchlist_items.json", migrated)


async def run() -> None:
    ctx = build_context()
    awards_only = os.getenv("LOAD_AWARDS_ONLY") == "1"

    if awards_only:
        log.info("LOAD_AWARDS_ONLY=1 — skipping stats/knowledge/index; uploading awards only")
    else:
        import knowledge
        import index_search
        import stats as stats_mod

        program_stats = stats_mod.compute_program_stats(ctx)
        stats_mod.save_stats(program_stats)

        stats_by_id = {s["grant_program_id"]: s for s in program_stats}
        for p in ctx.programs:
            s = stats_by_id.get(p["id"])
            if s:
                p["eligible_naics_prefixes"] = s.get("naics_top_prefixes") or []

        await knowledge.run(ctx)
        await index_search.run(ctx)
        write_snapshot(ctx)

    if os.getenv("DATABASE_URL"):
        try:
            await write_to_db(ctx)
        except Exception as e:  # noqa: BLE001
            log.error("DB load failed (%s). Local snapshots for recipients/programs remain.", e)
            raise
    else:
        log.info("No DATABASE_URL — wrote local snapshots only (awards not snapshotted).")

    total = len(ctx.recipients) + len(ctx.programs) + ctx.award_count
    log_pipeline_run(
        "load",
        total,
        total,
        0,
        {
            "recipients": len(ctx.recipients),
            "grant_programs": len(ctx.programs),
            "grant_awards": ctx.award_count,
        },
    )


if __name__ == "__main__":
    import asyncio
    asyncio.run(run())
