"""Shared business logic for grants intelligence features."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

# NAICS prefix → sector (common Canadian SMB codes)
NAICS_SECTOR_MAP: dict[str, str] = {
    "5415": "IT_SOFTWARE",
    "5416": "MANAGEMENT_CONSULTING",
    "5413": "ENGINEERING",
    "5417": "LIFE_SCIENCES",
    "5414": "LIFE_SCIENCES",
    "5419": "OTHER",
    "54151": "IT_SOFTWARE",
    "541512": "CYBERSECURITY",
    "541330": "ENGINEERING",
    "541620": "CLEAN_TECH",
    "541714": "LIFE_SCIENCES",
    "111": "AGRICULTURE",
    "112": "AGRICULTURE",
    "221": "CLEAN_TECH",
    "333": "ENGINEERING",
    "334": "IT_SOFTWARE",
    "511": "IT_SOFTWARE",
    "518": "IT_SOFTWARE",
}

NAICS_TITLES: dict[str, str] = {
    "541510": "Computer Systems Design and Related Services",
    "541512": "Computer Systems Design Services",
    "541330": "Engineering Services",
    "541512": "Computer Systems Design Services",
    "541620": "Environmental Consulting Services",
    "541611": "Administrative Management Consulting",
    "541714": "R&D in Biotechnology",
    "541715": "R&D in Physical, Engineering and Life Sciences",
    "333": "Machinery Manufacturing",
    "334": "Computer and Electronic Product Manufacturing",
}

SR_ED_KEYWORDS = re.compile(
    r"sred|sr&ed|scientific research|experimental development|tax credit",
    re.I,
)


def naics_to_sector(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    code = str(code).strip()
    for length in (6, 5, 4, 3):
        prefix = code[:length]
        if prefix in NAICS_SECTOR_MAP:
            return NAICS_SECTOR_MAP[prefix]
    return None


def lookup_naics(q: str) -> list[dict]:
    q = (q or "").strip()
    if not q:
        return []
    out = []
    for code, title in NAICS_TITLES.items():
        if q in code or q.lower() in title.lower():
            out.append({
                "code": code,
                "title": title,
                "sector": naics_to_sector(code),
            })
    return out[:10]


def enrich_program(program: dict, naics_prefixes: Optional[list[str]] = None) -> dict:
    """Add derived metadata used by matching, alerts, and overlap flags."""
    text = f"{program.get('name', '')} {program.get('description', '')}".lower()
    ptype = program.get("program_type") or ""
    sred = bool(SR_ED_KEYWORDS.search(text))
    tax_type = None
    if "sred" in text or "sr&ed" in text:
        tax_type = "SR&ED"
    elif "tax credit" in text:
        tax_type = "OTHER"

    return {
        **program,
        "sred_related": program.get("sred_related", sred),
        "tax_credit_type": program.get("tax_credit_type", tax_type),
        "eligible_naics_prefixes": naics_prefixes or program.get("eligible_naics_prefixes") or [],
    }


def naics_match(profile: dict, program: dict) -> bool:
    code = profile.get("naics_code")
    prefixes = program.get("eligible_naics_prefixes") or []
    if not code or not prefixes:
        return True
    return any(str(code).startswith(p) for p in prefixes)


def activities_match(profile: dict, program: dict) -> bool:
    profile_acts = set(profile.get("activities") or [])
    elig = set(program.get("eligible_activities") or [])
    if not profile_acts or not elig or "Other" in elig:
        return True
    return bool(profile_acts & elig)


def score_program(
    profile: dict,
    program: dict,
    recent_program_ids: set,
    *,
    zero_closed: bool = True,
) -> dict:
    """Weighted match score with NAICS and activities."""
    province = profile.get("province")
    sector = profile.get("sector")
    size_band = profile.get("size_band")

    elig_prov = program.get("eligible_provinces") or []
    elig_sect = program.get("eligible_sectors") or []
    elig_size = program.get("eligible_sizes") or []

    province_ok = province in elig_prov or "ALL" in elig_prov
    sector_ok = sector in elig_sect
    size_ok = size_band in elig_size
    naics_ok = naics_match(profile, program)
    activities_ok = activities_match(profile, program)
    history_ok = program.get("id") in recent_program_ids

    raw = (
        province_ok * 0.28
        + sector_ok * 0.22
        + size_ok * 0.15
        + naics_ok * 0.15
        + activities_ok * 0.10
        + history_ok * 0.10
    )
    score = raw * (1 if program.get("is_open") or not zero_closed else 0)

    reasons = []
    if province_ok:
        reasons.append(f"Open to {province}" if province in elig_prov else "Available nationally")
    if sector_ok:
        reasons.append(f"Funds {sector.replace('_', ' ').title()} companies")
    if size_ok:
        reasons.append(f"Fits {size_band}-employee firms")
    if naics_ok and profile.get("naics_code"):
        reasons.append(f"NAICS {profile['naics_code']} aligns with program history")
    if activities_ok and profile.get("activities"):
        reasons.append("Your activities match program focus")
    if history_ok:
        reasons.append("Actively awarded in the last 2 fiscal years")

    return {
        "score": round(score, 3),
        "match": {
            "province": province_ok,
            "sector": sector_ok,
            "size": size_ok,
            "naics": naics_ok,
            "activities": activities_ok,
            "hasHistory": history_ok,
        },
        "match_reasons": reasons,
    }


def _program_passes_filters(
    program: dict,
    *,
    q: Optional[str] = None,
    sector: Optional[str] = None,
    province: Optional[str] = None,
    size_band: Optional[str] = None,
    program_type: Optional[str] = None,
    is_open: Optional[bool] = None,
    activity: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
) -> bool:
    if q:
        q_lower = q.lower()
        haystack = " ".join(
            filter(
                None,
                [
                    program.get("name"),
                    program.get("department"),
                    program.get("description"),
                ],
            )
        ).lower()
        if q_lower not in haystack:
            return False

    if sector:
        elig = program.get("eligible_sectors") or []
        if sector not in elig:
            return False

    if province:
        elig = program.get("eligible_provinces") or []
        if province not in elig and "ALL" not in elig:
            return False

    if size_band:
        elig = program.get("eligible_sizes") or []
        if size_band not in elig:
            return False

    if program_type and program.get("program_type") != program_type:
        return False

    if is_open is not None and bool(program.get("is_open")) != is_open:
        return False

    if activity:
        elig = program.get("eligible_activities") or []
        if activity not in elig and "Other" not in elig:
            return False

    if min_amount is not None:
        prog_max = program.get("max_amount")
        if prog_max is not None and float(prog_max) < min_amount:
            return False

    if max_amount is not None:
        prog_min = program.get("min_amount")
        if prog_min is not None and float(prog_min) > max_amount:
            return False

    return True


def _sort_key(program: dict, sort: str):
    if sort == "name":
        return (program.get("name") or "").lower()
    if sort == "amount":
        amt = program.get("max_amount")
        return (-float(amt) if amt is not None else float("inf"),)
    if sort == "deadline":
        dl = program.get("deadline")
        return (dl is None, dl or "")
    return (-(program.get("score") or 0),)


def browse_programs(
    programs: list[dict],
    recent_program_ids: set,
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
) -> tuple[list[dict], int]:
    """Filter, score, sort, and paginate the full program catalog."""
    filtered = [
        p
        for p in programs
        if _program_passes_filters(
            p,
            q=q,
            sector=sector,
            province=province,
            size_band=size_band,
            program_type=program_type,
            is_open=is_open,
            activity=activity,
            min_amount=min_amount,
            max_amount=max_amount,
        )
    ]

    scored: list[dict] = []
    for p in filtered:
        row = dict(p)
        if profile:
            row.update(
                score_program(profile, p, recent_program_ids, zero_closed=False)
            )
        else:
            row["score"] = 0
        scored.append(row)

    reverse = sort in ("score", "amount")
    scored.sort(key=lambda p: _sort_key(p, sort), reverse=reverse)
    total = len(scored)
    return scored[offset : offset + limit], total


def readiness_checklist(profile: dict, program: dict) -> dict:
    """Structured application readiness for a profile × program pair."""
    elig_prov = program.get("eligible_provinces") or []
    elig_sect = program.get("eligible_sectors") or []
    elig_size = program.get("eligible_sizes") or []
    elig_acts = program.get("eligible_activities") or []
    profile_acts = profile.get("activities") or []

    province = profile.get("province")
    sector = profile.get("sector")
    size_band = profile.get("size_band")

    province_ok = province in elig_prov or "ALL" in elig_prov
    sector_ok = sector in elig_sect
    size_ok = size_band in elig_size
    naics_ok = naics_match(profile, program)
    acts_overlap = bool(set(profile_acts) & set(elig_acts)) if elig_acts else True
    has_apply = bool(program.get("apply_url"))
    is_open = program.get("is_open", True)
    has_deadline = bool(program.get("deadline"))

    items = [
        {"key": "province", "label": f"Province ({province})", "status": "pass" if province_ok else "fail", "required": True},
        {"key": "sector", "label": f"Sector ({sector.replace('_', ' ')})", "status": "pass" if sector_ok else "fail", "required": True},
        {"key": "size", "label": f"Company size ({size_band})", "status": "pass" if size_ok else "fail", "required": True},
        {"key": "naics", "label": f"NAICS code ({profile.get('naics_code') or 'not set'})",
         "status": "pass" if naics_ok else ("unknown" if not profile.get("naics_code") else "fail"), "required": False},
        {"key": "activities", "label": "Activity alignment",
         "status": "pass" if acts_overlap else "partial", "required": False,
         "detail": f"Program funds: {', '.join(elig_acts) or '—'}"},
        {"key": "open", "label": "Program accepting applications",
         "status": "pass" if is_open else "fail", "required": True},
        {"key": "apply_url", "label": "Application portal available",
         "status": "pass" if has_apply else "fail", "required": True},
        {"key": "deadline", "label": "Deadline known",
         "status": "pass" if has_deadline else "unknown", "required": False},
    ]

    required = [i for i in items if i["required"]]
    passed = sum(1 for i in required if i["status"] == "pass")
    readiness_score = round(passed / len(required), 2) if required else 0

    blockers = [i["label"] for i in items if i["required"] and i["status"] == "fail"]
    next_steps = []
    if not has_deadline:
        next_steps.append("Confirm application deadline on the program website")
    if profile.get("activities") and "R&D" in profile["activities"]:
        next_steps.append("Review SR&ED overlap before applying")
    if not profile.get("naics_code"):
        next_steps.append("Add your NAICS code to improve match precision")
    if has_apply:
        next_steps.append("Gather financial statements and project plan")

    return {
        "readiness_score": readiness_score,
        "items": items,
        "blockers": blockers,
        "next_steps": next_steps,
    }


def overlap_flags(profile: dict, program: dict, all_programs: list[dict]) -> list[dict]:
    """SR&ED / tax credit overlap warnings."""
    flags = []
    profile_acts = set(profile.get("activities") or [])
    elig_acts = set(program.get("eligible_activities") or [])
    ptype = program.get("program_type") or ""
    funds_rd = "R&D" in elig_acts or "R&D" in profile_acts

    if funds_rd and "R&D" in profile_acts and ptype in ("Grant", "Contribution", "Advisory", "Loan"):
        flags.append({
            "type": "sred_overlap",
            "severity": "warning",
            "message": (
                "This program funds R&D activities that may also qualify for SR&ED tax credits. "
                "Coordinate claim timing with your tax advisor."
            ),
        })

    if program.get("sred_related") or program.get("tax_credit_type") == "SR&ED":
        flags.append({
            "type": "sred_program",
            "severity": "info",
            "message": "This is an SR&ED-related program. Ensure your R&D activities meet CRA eligibility criteria.",
        })

    related = [
        {"id": p["id"], "name": p["name"], "program_type": p.get("program_type")}
        for p in all_programs
        if p.get("tax_credit_type") == "SR&ED" and p["id"] != program.get("id")
    ]
    if related and funds_rd:
        flags.append({
            "type": "related_tax_credits",
            "severity": "info",
            "message": "Related SR&ED tax credit programs are also available.",
            "related_programs": related[:3],
        })

    return flags


def _parse_deadline(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def compute_alerts(matched_programs: list[dict], days: int = 90) -> list[dict]:
    """In-app deadline alerts for matched programs."""
    today = date.today()
    alerts = []
    for p in matched_programs:
        dl = _parse_deadline(p.get("deadline"))
        if not dl or not p.get("is_open"):
            continue
        remaining = (dl - today).days
        if remaining < 0 or remaining > days:
            continue
        urgency = "critical" if remaining <= 14 else ("warning" if remaining <= 45 else "info")
        alerts.append({
            "program_id": p["id"],
            "name": p["name"],
            "deadline": dl.isoformat(),
            "days_remaining": remaining,
            "urgency": urgency,
            "apply_url": p.get("apply_url"),
        })
    alerts.sort(key=lambda x: x["days_remaining"])
    return alerts


def build_recipient_summaries(recipients: list[dict], awards: list[dict]) -> dict[str, dict]:
    """Aggregate award stats per recipient for peer matching."""
    latest = [a for a in awards if a.get("is_latest_amendment")]
    summaries: dict[str, dict] = {}
    for a in latest:
        rid = a.get("recipient_id")
        if not rid:
            continue
        s = summaries.setdefault(rid, {
            "award_count": 0,
            "total_amount": 0.0,
            "sectors": set(),
            "provinces": set(),
            "naics_codes": set(),
            "program_ids": set(),
        })
        s["award_count"] += 1
        s["total_amount"] += a.get("amount") or 0
        if a.get("sector_normalized"):
            s["sectors"].add(a["sector_normalized"])
        if a.get("province"):
            s["provinces"].add(a["province"])
        if a.get("naics_code"):
            s["naics_codes"].add(str(a["naics_code"]))
        if a.get("program_id"):
            s["program_ids"].add(a["program_id"])

    out = {}
    rec_by_id = {r["id"]: r for r in recipients}
    for rid, s in summaries.items():
        rec = rec_by_id.get(rid, {})
        primary_naics = sorted(s["naics_codes"])[0] if s["naics_codes"] else None
        out[rid] = {
            "id": rid,
            "name": rec.get("name_normalized", "Unknown"),
            "province": rec.get("province"),
            "city": rec.get("city"),
            "primary_sector": sorted(s["sectors"])[0] if s["sectors"] else None,
            "primary_naics": primary_naics,
            "award_count": s["award_count"],
            "total_amount": s["total_amount"],
            "program_ids": list(s["program_ids"]),
        }
    return out


def score_peer(profile: dict, peer: dict) -> tuple[float, list[str]]:
    """Similarity score between company profile and a recipient."""
    score = 0.0
    reasons = []

    if profile.get("province") and peer.get("province") == profile["province"]:
        score += 0.25
        reasons.append("Same province")

    if profile.get("sector") and peer.get("primary_sector") == profile["sector"]:
        score += 0.30
        reasons.append("Same sector")

    profile_naics = profile.get("naics_code")
    peer_naics = peer.get("primary_naics")
    if profile_naics and peer_naics:
        if str(profile_naics)[:4] == str(peer_naics)[:4]:
            score += 0.20
            reasons.append("Similar NAICS code")
        elif str(profile_naics)[:2] == str(peer_naics)[:2]:
            score += 0.10
            reasons.append("Related industry (NAICS)")

    if profile.get("size_band"):
        # Proxy: peers with moderate award counts resemble SMBs
        count = peer.get("award_count", 0)
        band = profile["size_band"]
        if band in ("1-10", "11-50") and count <= 5:
            score += 0.15
            reasons.append("Similar company scale")
        elif band in ("51-200", "200+") and count > 3:
            score += 0.15
            reasons.append("Similar company scale")

    if peer.get("total_amount", 0) > 0:
        score += 0.10
        reasons.append("Active grant recipient")

    return round(min(score, 1.0), 2), reasons


def similar_recipients(
    profile: dict,
    summaries: dict[str, dict],
    programs_by_id: dict[str, dict],
    limit: int = 8,
) -> list[dict]:
    """Rank recipients most similar to the company profile."""
    scored = []
    for rid, peer in summaries.items():
        sim, reasons = score_peer(profile, peer)
        if sim < 0.25:
            continue
        prog_names = []
        for pid in peer.get("program_ids", [])[:5]:
            prog = programs_by_id.get(pid)
            if prog:
                prog_names.append(prog["name"])
        scored.append({
            **peer,
            "similarity_score": sim,
            "match_reasons": reasons,
            "programs_in_common": prog_names,
        })
    scored.sort(key=lambda x: (-x["similarity_score"], -x["total_amount"]))
    return scored[:limit]


def program_naics_prefixes(awards: list[dict]) -> dict[str, list[str]]:
    """Derive eligible NAICS prefixes per program from award history."""
    by_prog: dict[str, set[str]] = {}
    for a in awards:
        if not a.get("is_latest_amendment"):
            continue
        pid = a.get("program_id")
        code = a.get("naics_code")
        if pid and code:
            prefix = str(code)[:4]
            by_prog.setdefault(pid, set()).add(prefix)
    return {pid: sorted(prefixes) for pid, prefixes in by_prog.items()}
