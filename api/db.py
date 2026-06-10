"""Data access layer for the API.

Two interchangeable backends behind one Repository interface:

  * PgRepository   — asyncpg + SQL against DATABASE_URL (Supabase / Postgres).
                     This is the production path.
  * JsonRepository — reads the pipeline's data/processed/db_*.json snapshot into
                     memory. Lets the whole app be demoed with zero infra.

get_repo() picks Postgres when DATABASE_URL is set, otherwise the snapshot.
Every method returns plain JSON-serializable dicts/lists so routes stay thin.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from features import (
    answer_grant_question,
    browse_programs,
    build_recipient_summaries,
    compute_alerts,
    enrich_program,
    overlap_flags,
    program_naics_prefixes,
    readiness_checklist,
    score_program,
    similar_recipients,
)

ROOT = Path(__file__).resolve().parent.parent
load_dotenv()
load_dotenv(ROOT / ".env.local", override=True)

PROCESSED_DIR = ROOT / "data" / "processed"

log = __import__("logging").getLogger("api.db")


# ===========================================================================
# JSON snapshot backend
# ===========================================================================
class JsonRepository:
    backend = "json-snapshot"

    REQUIRED_SNAPSHOTS = (
        "db_grant_programs.json",
        "db_grant_awards.json",
        "db_recipients.json",
    )

    def __init__(self) -> None:
        missing = [
            name for name in self.REQUIRED_SNAPSHOTS
            if not (PROCESSED_DIR / name).exists()
        ]
        self.data_ready = not missing
        self.data_error = (
            "Processed data not found. Run `python pipeline/run_all.py` first. "
            f"Missing: {', '.join(missing)}"
            if missing
            else None
        )

        self.recipients = self._load("db_recipients.json") if self.data_ready else []
        raw_programs = self._load("db_grant_programs.json") if self.data_ready else []
        self.awards = self._load("db_grant_awards.json") if self.data_ready else []
        self.runs = self._load_runs()
        naics_by_prog = program_naics_prefixes(self.awards)
        self.programs = [
            enrich_program(p, naics_by_prog.get(p["id"], [])) for p in raw_programs
        ]
        self.programs_by_id = {p["id"]: p for p in self.programs}
        self.recipient_summaries = build_recipient_summaries(self.recipients, self.awards)
        self.profiles: dict[str, dict] = {}
        self._profiles_path = PROCESSED_DIR / "db_company_profiles.json"
        if self._profiles_path.exists():
            for p in json.loads(self._profiles_path.read_text()):
                self.profiles[p["session_id"]] = p
        self.watchlist: list[dict] = self._load("db_watchlist_items.json")
        self._watchlist_path = PROCESSED_DIR / "db_watchlist_items.json"
        self.stats_by_id = {
            s["grant_program_id"]: s for s in self._load("db_grant_program_stats.json")
        }
        self.insights_by_program: dict[str, list[dict]] = {}
        for ins in self._load("db_grant_insights.json"):
            self.insights_by_program.setdefault(ins["grant_program_id"], []).append(ins)
        for p in self.programs:
            if p["id"] in self.stats_by_id:
                p["stats"] = self.stats_by_id[p["id"]]

    @staticmethod
    def _load(name: str) -> list[dict]:
        path = PROCESSED_DIR / name
        return json.loads(path.read_text()) if path.exists() else []

    def _load_runs(self) -> list[dict]:
        path = PROCESSED_DIR / "pipeline_runs.jsonl"
        if not path.exists():
            return []
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        return rows

    async def connect(self):  # parity with Pg backend
        return self

    async def close(self):
        return None

    # --- helpers ---
    def _recent_fiscal_years(self, n: int = 2) -> list[str]:
        years = sorted({a.get("fiscal_year") for a in self.awards if a.get("fiscal_year")})
        return years[-n:] if years else []

    def _recent_program_ids(self, n: int = 2) -> set:
        years = set(self._recent_fiscal_years(n))
        return {a["program_id"] for a in self.awards
                if a.get("program_id") and a.get("fiscal_year") in years}

    def _latest_awards(self) -> list[dict]:
        return [a for a in self.awards if a.get("is_latest_amendment")]

    # --- endpoints ---
    async def match_programs(self, profile: dict, limit: int = 10) -> list[dict]:
        recent = self._recent_program_ids()
        scored = []
        for p in self.programs:
            s = score_program(profile, p, recent)
            if s["score"] > 0:
                scored.append({**p, **s})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    async def search_programs(
        self,
        *,
        profile: Optional[dict] = None,
        q: Optional[str] = None,
        sector: Optional[str] = None,
        province: Optional[str] = None,
        size_band: Optional[str] = None,
        program_type: Optional[str] = None,
        is_open: Optional[bool] = None,
        activity: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        sort: str = "score",
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        recent = self._recent_program_ids()
        programs, total = browse_programs(
            self.programs,
            recent,
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
        return {"programs": programs, "total": total}

    async def sector_summary(self, sector: str, province: Optional[str], years: int = 2) -> dict:
        recent = set(self._recent_fiscal_years(years))
        rows = [a for a in self._latest_awards()
                if a.get("sector_normalized") == sector
                and a.get("fiscal_year") in recent
                and a.get("amount") is not None
                and (province is None or a.get("province") == province)]
        total = sum(a["amount"] for a in rows)
        count = len(rows)

        def agg(key):
            d: dict[str, float] = {}
            for a in rows:
                k = a.get(key)
                if k:
                    d[k] = d.get(k, 0) + a["amount"]
            return d

        prog = agg("program_name_raw")
        top_programs = [{"name": k, "total": v,
                         "count": sum(1 for a in rows if a.get("program_name_raw") == k)}
                        for k, v in sorted(prog.items(), key=lambda x: -x[1])[:5]]
        by_fy = [{"year": y, "total": sum(a["amount"] for a in rows if a.get("fiscal_year") == y)}
                 for y in sorted({a["fiscal_year"] for a in rows if a.get("fiscal_year")})]

        rec_totals: dict[str, float] = {}
        for a in rows:
            rid = a.get("recipient_id")
            if rid:
                rec_totals[rid] = rec_totals.get(rid, 0) + a["amount"]
        name_by_id = {r["id"]: r["name_normalized"] for r in self.recipients}
        top_recipients = [{"name": name_by_id.get(rid, "Unknown"), "total": v}
                          for rid, v in sorted(rec_totals.items(), key=lambda x: -x[1])[:5]]

        return {
            "sector": sector, "province": province,
            "total_amount": total, "award_count": count,
            "avg_amount": round(total / count, 2) if count else 0,
            "top_programs": top_programs, "by_fiscal_year": by_fy,
            "top_recipients": top_recipients,
        }

    async def program_detail(self, program_id: str, limit: int, offset: int) -> dict:
        program = next(
            (p for p in self.programs if str(p.get("id")) == str(program_id)),
            None,
        )
        if program is None:
            return {"program": None, "awards": [], "total": 0, "insights": []}
        awards = [
            a for a in self._latest_awards()
            if str(a.get("program_id")) == str(program_id)
        ]
        awards.sort(key=lambda a: a.get("amount") or 0, reverse=True)
        total = len(awards)
        page = awards[offset:offset + limit]
        name_by_id = {r["id"]: r["name_normalized"] for r in self.recipients}
        page = [{**a, "recipient_name": name_by_id.get(a.get("recipient_id"),
                                                       a.get("recipient_name_raw"))} for a in page]
        insights = self.insights_by_program.get(program_id, [])
        return {"program": program, "awards": page, "total": total, "insights": insights}

    async def program_insights(self, program_id: str) -> list[dict]:
        return self.insights_by_program.get(program_id, [])

    async def search_recipients(self, q: str, province: Optional[str], limit: int = 10) -> list[dict]:
        ql = (q or "").lower().strip()
        totals: dict[str, dict] = {}
        for a in self._latest_awards():
            rid = a.get("recipient_id")
            if not rid:
                continue
            t = totals.setdefault(rid, {"count": 0, "total": 0.0})
            t["count"] += 1
            t["total"] += a.get("amount") or 0
        out = []
        for r in self.recipients:
            if ql and ql not in (r["name_normalized"] or "").lower():
                continue
            if province and r.get("province") != province:
                continue
            t = totals.get(r["id"], {"count": 0, "total": 0.0})
            out.append({"id": r["id"], "name": r["name_normalized"],
                        "province": r.get("province"), "city": r.get("city"),
                        "award_count": t["count"], "total_amount": t["total"]})
        out.sort(key=lambda x: x["total_amount"], reverse=True)
        return out[:limit]

    async def recipient_awards(self, recipient_id: str) -> dict:
        recipient = next((r for r in self.recipients if r["id"] == recipient_id), None)
        if recipient is None:
            return {"recipient": None, "awards": [], "by_fiscal_year": []}
        awards = [a for a in self._latest_awards() if a.get("recipient_id") == recipient_id]
        awards.sort(key=lambda a: (a.get("fiscal_year") or "", a.get("amount") or 0), reverse=True)
        by_fy: dict[str, dict] = {}
        for a in awards:
            fy = a.get("fiscal_year") or "Unknown"
            g = by_fy.setdefault(fy, {"year": fy, "total": 0.0, "count": 0})
            g["total"] += a.get("amount") or 0
            g["count"] += 1
        total = sum(a.get("amount") or 0 for a in awards)
        provinces = sorted({a.get("province") for a in awards if a.get("province")})
        return {
            "recipient": {**recipient, "total_received": total,
                          "award_count": len(awards), "provinces": provinces},
            "awards": awards,
            "by_fiscal_year": sorted(by_fy.values(), key=lambda x: x["year"], reverse=True),
        }

    async def trending_programs(self, sector: Optional[str], province: Optional[str]) -> list[dict]:
        years = self._recent_fiscal_years(2)
        if len(years) < 2:
            return []
        prev_fy, latest_fy = years[0], years[1]
        rows = [a for a in self._latest_awards()
                if a.get("amount") is not None
                and (sector is None or a.get("sector_normalized") == sector)
                and (province is None or a.get("province") == province)]
        prog_name = {p["id"]: p["name"] for p in self.programs}
        agg: dict[str, dict] = {}
        for a in rows:
            pid = a.get("program_id")
            key = pid or a.get("program_name_raw")
            if not key:
                continue
            g = agg.setdefault(key, {"latest": 0.0, "prev": 0.0,
                                     "name": prog_name.get(pid, a.get("program_name_raw")),
                                     "program_id": pid})
            if a.get("fiscal_year") == latest_fy:
                g["latest"] += a["amount"]
            elif a.get("fiscal_year") == prev_fy:
                g["prev"] += a["amount"]
        out = []
        for g in agg.values():
            if g["prev"] > 0 and g["latest"] > g["prev"] * 1.2:
                yoy = (g["latest"] - g["prev"]) / g["prev"] * 100
                out.append({"name": g["name"], "program_id": g["program_id"],
                            "latest_total": g["latest"], "previous_total": g["prev"],
                            "yoy_change_pct": round(yoy, 1),
                            "latest_fiscal_year": latest_fy})
        out.sort(key=lambda x: x["yoy_change_pct"], reverse=True)
        return out

    async def get_profile(self, session_id: str) -> Optional[dict]:
        return self.profiles.get(session_id)

    async def create_profile(self, profile: dict) -> dict:
        self.profiles[profile["session_id"]] = profile
        self._profiles_path.write_text(
            json.dumps(list(self.profiles.values()), indent=2, default=str)
        )
        return profile

    async def pipeline_status(self, limit: int = 5) -> list[dict]:
        return list(reversed(self.runs))[:limit]

    async def get_alerts(self, profile: dict, days: int = 90) -> list[dict]:
        matches = await self.match_programs(profile, limit=50)
        return compute_alerts(matches, days)

    async def get_similar_recipients(self, profile: dict, limit: int = 8) -> list[dict]:
        return similar_recipients(
            profile, self.recipient_summaries, self.programs_by_id, limit
        )

    async def program_readiness(self, profile: dict, program_id: str) -> Optional[dict]:
        program = self.programs_by_id.get(program_id)
        if not program:
            return None
        return readiness_checklist(profile, program)

    async def program_overlap(self, profile: dict, program_id: str) -> list[dict]:
        program = self.programs_by_id.get(program_id)
        if not program:
            return []
        return overlap_flags(profile, program, self.programs)

    async def get_watchlist(self, session_id: str) -> dict:
        items = [w for w in self.watchlist if w["session_id"] == session_id]
        programs = [self.programs_by_id[w["entity_id"]] for w in items
                    if w["entity_type"] == "program" and w["entity_id"] in self.programs_by_id]
        rec_ids = {w["entity_id"] for w in items if w["entity_type"] == "recipient"}
        recipients = []
        for rid in rec_ids:
            s = self.recipient_summaries.get(rid)
            if s:
                recipients.append({
                    "id": s["id"], "name": s["name"], "province": s.get("province"),
                    "city": s.get("city"), "award_count": s["award_count"],
                    "total_amount": s["total_amount"],
                })
        return {"programs": programs, "recipients": recipients}

    async def add_watchlist_item(self, session_id: str, entity_type: str, entity_id: str) -> dict:
        key = (session_id, entity_type, entity_id)
        if not any((w["session_id"], w["entity_type"], w["entity_id"]) == key for w in self.watchlist):
            item = {"session_id": session_id, "entity_type": entity_type, "entity_id": entity_id}
            self.watchlist.append(item)
            self._watchlist_path.write_text(json.dumps(self.watchlist, indent=2))
        return {"ok": True}

    async def remove_watchlist_item(self, session_id: str, entity_type: str, entity_id: str) -> dict:
        self.watchlist = [
            w for w in self.watchlist
            if not (w["session_id"] == session_id and w["entity_type"] == entity_type
                    and w["entity_id"] == entity_id)
        ]
        self._watchlist_path.write_text(json.dumps(self.watchlist, indent=2))
        return {"ok": True}

    async def ask_grants(self, question: str, profile: Optional[dict]) -> dict:
        recent = self._recent_program_ids()
        return answer_grant_question(
            question, profile, self.programs, recent,
            self.stats_by_id, self.insights_by_program,
        )


# ===========================================================================
# Postgres backend
# ===========================================================================
class PgRepository:
    backend = "postgres"

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool = None
        self._programs_cache: Optional[list[dict]] = None

    async def connect(self):
        import asyncpg
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
        return self

    async def _fetchrow_write(self, query: str, *args: Any):
        """Run a write query on Supabase pooler connections (default read-only tx)."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET TRANSACTION READ WRITE")
                return await conn.fetchrow(query, *args)

    async def _execute_write(self, query: str, *args: Any):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET TRANSACTION READ WRITE")
                return await conn.execute(query, *args)

    async def _ensure_caches(self):
        count = int(await self.pool.fetchval("SELECT COUNT(*) FROM grant_programs") or 0)
        if self._programs_cache and len(self._programs_cache) == count:
            return
        self._programs_cache = None
        if count == 0:
            self._programs_cache = []
            return
        rows = await self.pool.fetch("SELECT * FROM grant_programs")
        programs = [self._row(r) for r in rows]
        naics_by_prog: dict[str, list[str]] = {}
        award_count = int(await self.pool.fetchval("SELECT COUNT(*) FROM grant_awards") or 0)
        if award_count:
            prefix_rows = await self.pool.fetch(
                "SELECT program_id, LEFT(naics_code, 4) AS prefix "
                "FROM grant_awards "
                "WHERE program_id IS NOT NULL AND naics_code IS NOT NULL AND is_latest_amendment "
                "GROUP BY program_id, LEFT(naics_code, 4)"
            )
            for r in prefix_rows:
                pid = str(r["program_id"])
                prefix = str(r["prefix"])
                bucket = naics_by_prog.setdefault(pid, [])
                if prefix not in bucket:
                    bucket.append(prefix)
            for pid in naics_by_prog:
                naics_by_prog[pid] = sorted(naics_by_prog[pid])
        self._programs_cache = [
            enrich_program(p, naics_by_prog.get(p["id"], [])) for p in programs
        ]

    async def _programs_by_id(self) -> dict[str, dict]:
        await self._ensure_caches()
        return {p["id"]: p for p in self._programs_cache}

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def _recent_fiscal_years(self, n: int = 2) -> list[str]:
        rows = await self.pool.fetch(
            "SELECT DISTINCT fiscal_year FROM grant_awards "
            "WHERE fiscal_year IS NOT NULL ORDER BY fiscal_year DESC LIMIT $1", n)
        return [r["fiscal_year"] for r in rows][::-1]

    async def _recent_program_ids(self, n: int = 2) -> set:
        years = await self._recent_fiscal_years(n)
        if not years:
            return set()
        rows = await self.pool.fetch(
            "SELECT DISTINCT program_id FROM grant_awards "
            "WHERE program_id IS NOT NULL AND fiscal_year = ANY($1::text[])", years)
        return {str(r["program_id"]) for r in rows}

    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
            elif str(type(v)) == "<class 'uuid.UUID'>":
                d[k] = str(v)
        return d

    async def match_programs(self, profile: dict, limit: int = 10) -> list[dict]:
        recent = await self._recent_program_ids()
        rows = await self.pool.fetch("SELECT * FROM grant_programs")
        scored = []
        for r in rows:
            p = self._row(r)
            s = score_program(profile, p, recent)
            if s["score"] > 0:
                scored.append({**p, **s})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    async def search_programs(
        self,
        *,
        profile: Optional[dict] = None,
        q: Optional[str] = None,
        sector: Optional[str] = None,
        province: Optional[str] = None,
        size_band: Optional[str] = None,
        program_type: Optional[str] = None,
        is_open: Optional[bool] = None,
        activity: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        sort: str = "score",
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        await self._ensure_caches()
        recent = await self._recent_program_ids()
        programs, total = browse_programs(
            self._programs_cache or [],
            recent,
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
        return {"programs": programs, "total": total}

    async def sector_summary(self, sector: str, province: Optional[str], years: int = 2) -> dict:
        fys = await self._recent_fiscal_years(years)
        if not fys:
            return {"sector": sector, "province": province, "total_amount": 0,
                    "award_count": 0, "avg_amount": 0, "top_programs": [],
                    "by_fiscal_year": [], "top_recipients": []}
        cond = ("a.sector_normalized = $1 AND a.fiscal_year = ANY($2::text[]) "
                "AND a.is_latest_amendment AND a.amount IS NOT NULL")
        args: list[Any] = [sector, fys]
        if province:
            cond += " AND a.province = $3"
            args.append(province)

        agg = await self.pool.fetchrow(
            f"SELECT COALESCE(SUM(a.amount),0) total, COUNT(*) cnt, COALESCE(AVG(a.amount),0) avg "
            f"FROM grant_awards a WHERE {cond}", *args)
        top_programs = await self.pool.fetch(
            f"SELECT a.program_name_raw AS pname, SUM(a.amount) AS total_amt, COUNT(*) AS cnt "
            f"FROM grant_awards a WHERE {cond} GROUP BY a.program_name_raw "
            f"ORDER BY total_amt DESC LIMIT 5", *args)
        by_fy = await self.pool.fetch(
            f"SELECT a.fiscal_year AS fy, SUM(a.amount) AS total_amt FROM grant_awards a WHERE {cond} "
            f"GROUP BY a.fiscal_year ORDER BY a.fiscal_year", *args)
        top_recipients = await self.pool.fetch(
            f"SELECT r.name_normalized AS pname, SUM(a.amount) AS total_amt FROM grant_awards a "
            f"JOIN recipients r ON r.id = a.recipient_id WHERE {cond} "
            f"GROUP BY r.name_normalized ORDER BY total_amt DESC LIMIT 5", *args)

        return {
            "sector": sector, "province": province,
            "total_amount": float(agg["total"]), "award_count": agg["cnt"],
            "avg_amount": round(float(agg["avg"]), 2),
            "top_programs": [{"name": r["pname"], "total": float(r["total_amt"]), "count": r["cnt"]}
                             for r in top_programs],
            "by_fiscal_year": [{"year": r["fy"], "total": float(r["total_amt"])} for r in by_fy],
            "top_recipients": [{"name": r["pname"], "total": float(r["total_amt"])}
                               for r in top_recipients],
        }

    async def program_detail(self, program_id: str, limit: int, offset: int) -> dict:
        prow = await self.pool.fetchrow("SELECT * FROM grant_programs WHERE id = $1", program_id)
        if prow is None:
            return {"program": None, "awards": [], "total": 0, "insights": []}
        program = self._row(prow)
        stats_row = await self.pool.fetchrow(
            "SELECT * FROM grant_program_stats WHERE grant_program_id = $1", program_id)
        if stats_row:
            program["stats"] = self._row(stats_row)
        insight_rows = await self.pool.fetch(
            "SELECT * FROM grant_insights WHERE grant_program_id = $1", program_id)
        insights = [self._row(r) for r in insight_rows]
        total = await self.pool.fetchval(
            "SELECT COUNT(*) FROM grant_awards WHERE program_id = $1 AND is_latest_amendment",
            program_id)
        rows = await self.pool.fetch(
            "SELECT a.*, COALESCE(r.name_normalized, a.recipient_name_raw) recipient_name "
            "FROM grant_awards a LEFT JOIN recipients r ON r.id = a.recipient_id "
            "WHERE a.program_id = $1 AND a.is_latest_amendment "
            "ORDER BY a.amount DESC NULLS LAST LIMIT $2 OFFSET $3", program_id, limit, offset)
        return {
            "program": program,
            "awards": [self._row(r) for r in rows],
            "total": total,
            "insights": insights,
        }

    async def program_insights(self, program_id: str) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM grant_insights WHERE grant_program_id = $1", program_id)
        return [self._row(r) for r in rows]

    async def search_recipients(self, q: str, province: Optional[str], limit: int = 10) -> list[dict]:
        cond = "to_tsvector('english', r.name_normalized) @@ plainto_tsquery('english', $1)"
        args: list[Any] = [q]
        if not (q or "").strip():
            cond = "TRUE"
            args = []
        prov_sql = ""
        if province:
            prov_sql = f" AND r.province = ${len(args) + 1}"
            args.append(province)
        rows = await self.pool.fetch(
            f"SELECT r.id, r.name_normalized name, r.province, r.city, "
            f"COUNT(a.id) award_count, COALESCE(SUM(a.amount),0) total_amount "
            f"FROM recipients r "
            f"LEFT JOIN grant_awards a ON a.recipient_id = r.id AND a.is_latest_amendment "
            f"WHERE {cond}{prov_sql} GROUP BY r.id "
            f"ORDER BY total_amount DESC LIMIT {limit}", *args)
        return [self._row(r) for r in rows]

    async def recipient_awards(self, recipient_id: str) -> dict:
        rrow = await self.pool.fetchrow("SELECT * FROM recipients WHERE id = $1", recipient_id)
        if rrow is None:
            return {"recipient": None, "awards": [], "by_fiscal_year": []}
        awards = await self.pool.fetch(
            "SELECT a.*, p.apply_url AS program_apply_url "
            "FROM grant_awards a "
            "LEFT JOIN grant_programs p ON p.id = a.program_id "
            "WHERE a.recipient_id = $1 AND a.is_latest_amendment "
            "ORDER BY a.fiscal_year DESC, amount DESC NULLS LAST", recipient_id)
        by_fy = await self.pool.fetch(
            "SELECT fiscal_year AS fy, SUM(amount) AS total_amt, COUNT(*) AS cnt "
            "FROM grant_awards "
            "WHERE recipient_id = $1 AND is_latest_amendment GROUP BY fiscal_year "
            "ORDER BY fiscal_year DESC", recipient_id)
        meta = await self.pool.fetchrow(
            "SELECT COALESCE(SUM(amount),0) total, COUNT(*) cnt, "
            "ARRAY_AGG(DISTINCT province) FILTER (WHERE province IS NOT NULL) provinces "
            "FROM grant_awards WHERE recipient_id = $1 AND is_latest_amendment", recipient_id)
        rec = self._row(rrow)
        rec.update({"total_received": float(meta["total"]), "award_count": meta["cnt"],
                    "provinces": list(meta["provinces"] or [])})
        return {
            "recipient": rec,
            "awards": [self._row(a) for a in awards],
            "by_fiscal_year": [{"year": r["fy"], "total": float(r["total_amt"]), "count": r["cnt"]}
                               for r in by_fy],
        }

    async def trending_programs(self, sector: Optional[str], province: Optional[str]) -> list[dict]:
        fys = await self._recent_fiscal_years(2)
        if len(fys) < 2:
            return []
        prev_fy, latest_fy = fys[0], fys[1]
        cond = "is_latest_amendment AND amount IS NOT NULL AND program_id IS NOT NULL"
        args: list[Any] = [latest_fy, prev_fy]
        if sector:
            cond += f" AND sector_normalized = ${len(args) + 1}"
            args.append(sector)
        if province:
            cond += f" AND province = ${len(args) + 1}"
            args.append(province)
        rows = await self.pool.fetch(
            f"SELECT a.program_id, p.name, "
            f"SUM(amount) FILTER (WHERE fiscal_year = $1) latest, "
            f"SUM(amount) FILTER (WHERE fiscal_year = $2) prev "
            f"FROM grant_awards a JOIN grant_programs p ON p.id = a.program_id "
            f"WHERE {cond} GROUP BY a.program_id, p.name", *args)
        out = []
        for r in rows:
            latest = float(r["latest"] or 0)
            prev = float(r["prev"] or 0)
            if prev > 0 and latest > prev * 1.2:
                out.append({"name": r["name"], "program_id": str(r["program_id"]),
                            "latest_total": latest, "previous_total": prev,
                            "yoy_change_pct": round((latest - prev) / prev * 100, 1),
                            "latest_fiscal_year": latest_fy})
        out.sort(key=lambda x: x["yoy_change_pct"], reverse=True)
        return out

    async def get_profile(self, session_id: str) -> Optional[dict]:
        row = await self.pool.fetchrow(
            "SELECT * FROM company_profiles WHERE session_id = $1", session_id)
        return self._row(row) if row else None

    async def create_profile(self, profile: dict) -> dict:
        row = await self._fetchrow_write(
            "INSERT INTO company_profiles "
            "(session_id, name, sector, province, size_band, activities, naics_code) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (session_id) DO UPDATE SET "
            "name=EXCLUDED.name, sector=EXCLUDED.sector, province=EXCLUDED.province, "
            "size_band=EXCLUDED.size_band, activities=EXCLUDED.activities, "
            "naics_code=EXCLUDED.naics_code RETURNING *",
            profile["session_id"], profile.get("name"), profile.get("sector"),
            profile.get("province"), profile.get("size_band"),
            profile.get("activities") or [], profile.get("naics_code"),
        )
        return self._row(row)

    async def pipeline_status(self, limit: int = 5) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM pipeline_runs ORDER BY run_at DESC LIMIT $1", limit)
        return [self._row(r) for r in rows]

    async def stats(self) -> dict[str, int]:
        programs = await self.pool.fetchval("SELECT COUNT(*) FROM grant_programs")
        recipients = await self.pool.fetchval("SELECT COUNT(*) FROM recipients")
        awards = await self.pool.fetchval("SELECT COUNT(*) FROM grant_awards")
        return {
            "programs": int(programs or 0),
            "recipients": int(recipients or 0),
            "awards": int(awards or 0),
        }

    async def get_alerts(self, profile: dict, days: int = 90) -> list[dict]:
        matches = await self.match_programs(profile, limit=50)
        return compute_alerts(matches, days)

    async def get_similar_recipients(self, profile: dict, limit: int = 8) -> list[dict]:
        sector = profile.get("sector")
        province = profile.get("province")
        cond = ["a.is_latest_amendment"]
        args: list[Any] = []
        if sector:
            args.append(sector)
            cond.append(f"a.sector_normalized = ${len(args)}")
        if province:
            args.append(province)
            cond.append(f"r.province = ${len(args)}")
        where = " AND ".join(cond)
        rows = await self.pool.fetch(
            f"SELECT r.id, r.name_normalized name, r.province, r.city, "
            f"COUNT(a.id) award_count, COALESCE(SUM(a.amount),0) total_amount, "
            f"(ARRAY_AGG(a.sector_normalized ORDER BY a.amount DESC NULLS LAST) "
            f" FILTER (WHERE a.sector_normalized IS NOT NULL))[1] primary_sector, "
            f"(ARRAY_AGG(a.naics_code ORDER BY a.amount DESC NULLS LAST) "
            f" FILTER (WHERE a.naics_code IS NOT NULL))[1] primary_naics, "
            f"ARRAY_AGG(DISTINCT a.program_id) FILTER (WHERE a.program_id IS NOT NULL) program_ids "
            f"FROM recipients r JOIN grant_awards a ON a.recipient_id = r.id "
            f"WHERE {where} "
            f"GROUP BY r.id HAVING COALESCE(SUM(a.amount),0) > 0 "
            f"ORDER BY total_amount DESC LIMIT 200",
            *args,
        )
        summaries: dict[str, dict] = {}
        for r in rows:
            summaries[str(r["id"])] = {
                "id": str(r["id"]),
                "name": r["name"],
                "province": r["province"],
                "city": r["city"],
                "primary_sector": r["primary_sector"],
                "primary_naics": r["primary_naics"],
                "award_count": r["award_count"],
                "total_amount": float(r["total_amount"]),
                "program_ids": [str(x) for x in (r["program_ids"] or [])],
            }
        programs_by_id = await self._programs_by_id()
        return similar_recipients(profile, summaries, programs_by_id, limit)

    async def program_readiness(self, profile: dict, program_id: str) -> Optional[dict]:
        programs = await self._programs_by_id()
        program = programs.get(program_id)
        if not program:
            return None
        return readiness_checklist(profile, program)

    async def program_overlap(self, profile: dict, program_id: str) -> list[dict]:
        programs = await self._programs_by_id()
        program = programs.get(program_id)
        if not program:
            return []
        return overlap_flags(profile, program, list(programs.values()))

    async def get_watchlist(self, session_id: str) -> dict:
        rows = await self.pool.fetch(
            "SELECT entity_type, entity_id FROM watchlist_items WHERE session_id = $1",
            session_id,
        )
        programs_by_id = await self._programs_by_id()
        programs = [
            programs_by_id[str(r["entity_id"])]
            for r in rows
            if r["entity_type"] == "program" and str(r["entity_id"]) in programs_by_id
        ]
        rec_rows = await self.pool.fetch(
            "SELECT r.id, r.name_normalized name, r.province, r.city, "
            "COUNT(a.id) award_count, COALESCE(SUM(a.amount), 0) total_amount "
            "FROM watchlist_items w "
            "JOIN recipients r ON r.id = w.entity_id "
            "LEFT JOIN grant_awards a ON a.recipient_id = r.id AND a.is_latest_amendment "
            "WHERE w.session_id = $1 AND w.entity_type = 'recipient' "
            "GROUP BY r.id",
            session_id,
        )
        recipients = [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "province": r["province"],
                "city": r["city"],
                "award_count": r["award_count"],
                "total_amount": float(r["total_amount"]),
            }
            for r in rec_rows
        ]
        return {"programs": programs, "recipients": recipients}

    async def add_watchlist_item(self, session_id: str, entity_type: str, entity_id: str) -> dict:
        await self._execute_write(
            "INSERT INTO watchlist_items (session_id, entity_type, entity_id) "
            "VALUES ($1, $2, $3) ON CONFLICT (session_id, entity_type, entity_id) DO NOTHING",
            session_id, entity_type, entity_id,
        )
        return {"ok": True}

    async def remove_watchlist_item(self, session_id: str, entity_type: str, entity_id: str) -> dict:
        await self._execute_write(
            "DELETE FROM watchlist_items WHERE session_id = $1 AND entity_type = $2 AND entity_id = $3",
            session_id, entity_type, entity_id,
        )
        return {"ok": True}

    async def ask_grants(self, question: str, profile: Optional[dict]) -> dict:
        await self._ensure_caches()
        stats_rows = await self.pool.fetch("SELECT * FROM grant_program_stats")
        stats_by_id = {str(r["grant_program_id"]): self._row(r) for r in stats_rows}
        insight_rows = await self.pool.fetch("SELECT * FROM grant_insights")
        insights_by_program: dict[str, list[dict]] = {}
        for r in insight_rows:
            pid = str(r["grant_program_id"])
            insights_by_program.setdefault(pid, []).append(self._row(r))
        recent = await self._recent_program_ids()
        return answer_grant_question(
            question, profile, self._programs_cache or [], recent,
            stats_by_id, insights_by_program,
        )


# ---------------------------------------------------------------------------
# Factory + dashboard aggregation
# ---------------------------------------------------------------------------
_repo: Optional[Any] = None


async def get_repo():
    global _repo
    if _repo is None:
        dsn = os.getenv("DATABASE_URL")
        if dsn:
            log.info("Connecting to Supabase/Postgres via DATABASE_URL")
            _repo = await PgRepository(dsn).connect()
        elif os.getenv("SUPABASE_URL"):
            raise RuntimeError(
                "SUPABASE_URL is set but DATABASE_URL is missing. "
                "Add the Session pooler Postgres URI to .env.local so the API reads from Supabase."
            )
        else:
            log.warning("DATABASE_URL not set — using local JSON snapshot in data/processed/")
            _repo = await JsonRepository().connect()
    return _repo


async def close_repo():
    global _repo
    if _repo is not None:
        await _repo.close()
        _repo = None


def reset_repo_cache():
    """Clear the singleton so the next request reconnects (e.g. after a DB reload)."""
    global _repo
    _repo = None
