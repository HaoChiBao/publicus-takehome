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

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"


# ---------------------------------------------------------------------------
# Shared scoring helper (used by both backends + dashboard)
# ---------------------------------------------------------------------------
def score_program(profile: dict, program: dict, recent_program_ids: set) -> dict:
    """Implements the documented weighted match score + human-readable reasons."""
    province = profile.get("province")
    sector = profile.get("sector")
    size_band = profile.get("size_band")

    elig_prov = program.get("eligible_provinces") or []
    elig_sect = program.get("eligible_sectors") or []
    elig_size = program.get("eligible_sizes") or []

    province_ok = province in elig_prov or "ALL" in elig_prov
    sector_ok = sector in elig_sect
    size_ok = size_band in elig_size
    history_ok = program.get("id") in recent_program_ids

    raw = (
        province_ok * 0.4
        + sector_ok * 0.3
        + size_ok * 0.2
        + history_ok * 0.1
    )
    score = raw * (1 if program.get("is_open") else 0)

    reasons = []
    if province_ok:
        reasons.append(f"Open to {province}" if province in elig_prov else "Available nationally")
    if sector_ok:
        reasons.append(f"Funds {sector.replace('_', ' ').title()} companies")
    if size_ok:
        reasons.append(f"Fits {size_band}-employee firms")
    if history_ok:
        reasons.append("Actively awarded in the last 2 fiscal years")

    return {
        "score": round(score, 3),
        "match": {
            "province": province_ok, "sector": sector_ok,
            "size": size_ok, "hasHistory": history_ok,
        },
        "match_reasons": reasons,
    }


# ===========================================================================
# JSON snapshot backend
# ===========================================================================
class JsonRepository:
    def __init__(self) -> None:
        self.recipients = self._load("db_recipients.json")
        self.programs = self._load("db_grant_programs.json")
        self.awards = self._load("db_grant_awards.json")
        self.runs = self._load_runs()
        self.profiles: dict[str, dict] = {}
        self._profiles_path = PROCESSED_DIR / "db_company_profiles.json"
        if self._profiles_path.exists():
            for p in json.loads(self._profiles_path.read_text()):
                self.profiles[p["session_id"]] = p

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
        program = next((p for p in self.programs if p["id"] == program_id), None)
        if program is None:
            return {"program": None, "awards": [], "total": 0}
        awards = [a for a in self._latest_awards() if a.get("program_id") == program_id]
        awards.sort(key=lambda a: a.get("amount") or 0, reverse=True)
        total = len(awards)
        page = awards[offset:offset + limit]
        name_by_id = {r["id"]: r["name_normalized"] for r in self.recipients}
        page = [{**a, "recipient_name": name_by_id.get(a.get("recipient_id"),
                                                       a.get("recipient_name_raw"))} for a in page]
        return {"program": program, "awards": page, "total": total}

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


# ===========================================================================
# Postgres backend
# ===========================================================================
class PgRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        import asyncpg
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
        return self

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

    async def sector_summary(self, sector: str, province: Optional[str], years: int = 2) -> dict:
        fys = await self._recent_fiscal_years(years)
        if not fys:
            return {"sector": sector, "province": province, "total_amount": 0,
                    "award_count": 0, "avg_amount": 0, "top_programs": [],
                    "by_fiscal_year": [], "top_recipients": []}
        cond = ("sector_normalized = $1 AND fiscal_year = ANY($2::text[]) "
                "AND is_latest_amendment AND amount IS NOT NULL")
        args: list[Any] = [sector, fys]
        if province:
            cond += " AND province = $3"
            args.append(province)

        agg = await self.pool.fetchrow(
            f"SELECT COALESCE(SUM(amount),0) total, COUNT(*) cnt, COALESCE(AVG(amount),0) avg "
            f"FROM grant_awards WHERE {cond}", *args)
        top_programs = await self.pool.fetch(
            f"SELECT program_name_raw name, SUM(amount) total, COUNT(*) count "
            f"FROM grant_awards WHERE {cond} GROUP BY program_name_raw "
            f"ORDER BY total DESC LIMIT 5", *args)
        by_fy = await self.pool.fetch(
            f"SELECT fiscal_year year, SUM(amount) total FROM grant_awards WHERE {cond} "
            f"GROUP BY fiscal_year ORDER BY fiscal_year", *args)
        top_recipients = await self.pool.fetch(
            f"SELECT r.name_normalized name, SUM(a.amount) total FROM grant_awards a "
            f"JOIN recipients r ON r.id = a.recipient_id WHERE {cond} "
            f"GROUP BY r.name_normalized ORDER BY total DESC LIMIT 5", *args)

        return {
            "sector": sector, "province": province,
            "total_amount": float(agg["total"]), "award_count": agg["cnt"],
            "avg_amount": round(float(agg["avg"]), 2),
            "top_programs": [{"name": r["name"], "total": float(r["total"]), "count": r["count"]}
                             for r in top_programs],
            "by_fiscal_year": [{"year": r["year"], "total": float(r["total"])} for r in by_fy],
            "top_recipients": [{"name": r["name"], "total": float(r["total"])}
                               for r in top_recipients],
        }

    async def program_detail(self, program_id: str, limit: int, offset: int) -> dict:
        prow = await self.pool.fetchrow("SELECT * FROM grant_programs WHERE id = $1", program_id)
        if prow is None:
            return {"program": None, "awards": [], "total": 0}
        total = await self.pool.fetchval(
            "SELECT COUNT(*) FROM grant_awards WHERE program_id = $1 AND is_latest_amendment",
            program_id)
        rows = await self.pool.fetch(
            "SELECT a.*, COALESCE(r.name_normalized, a.recipient_name_raw) recipient_name "
            "FROM grant_awards a LEFT JOIN recipients r ON r.id = a.recipient_id "
            "WHERE a.program_id = $1 AND a.is_latest_amendment "
            "ORDER BY a.amount DESC NULLS LAST LIMIT $2 OFFSET $3", program_id, limit, offset)
        return {"program": self._row(prow), "awards": [self._row(r) for r in rows], "total": total}

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
            "SELECT * FROM grant_awards WHERE recipient_id = $1 AND is_latest_amendment "
            "ORDER BY fiscal_year DESC, amount DESC NULLS LAST", recipient_id)
        by_fy = await self.pool.fetch(
            "SELECT fiscal_year year, SUM(amount) total, COUNT(*) count FROM grant_awards "
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
            "by_fiscal_year": [{"year": r["year"], "total": float(r["total"]), "count": r["count"]}
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
        row = await self.pool.fetchrow(
            "INSERT INTO company_profiles (session_id, name, sector, province, size_band, activities) "
            "VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (session_id) DO UPDATE SET "
            "name=EXCLUDED.name, sector=EXCLUDED.sector, province=EXCLUDED.province, "
            "size_band=EXCLUDED.size_band, activities=EXCLUDED.activities RETURNING *",
            profile["session_id"], profile.get("name"), profile.get("sector"),
            profile.get("province"), profile.get("size_band"), profile.get("activities") or [])
        return self._row(row)

    async def pipeline_status(self, limit: int = 5) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM pipeline_runs ORDER BY run_at DESC LIMIT $1", limit)
        return [self._row(r) for r in rows]


# ---------------------------------------------------------------------------
# Factory + dashboard aggregation
# ---------------------------------------------------------------------------
_repo: Optional[Any] = None


async def get_repo():
    global _repo
    if _repo is None:
        dsn = os.getenv("DATABASE_URL")
        if dsn:
            _repo = await PgRepository(dsn).connect()
        else:
            _repo = await JsonRepository().connect()
    return _repo


async def close_repo():
    global _repo
    if _repo is not None:
        await _repo.close()
        _repo = None
