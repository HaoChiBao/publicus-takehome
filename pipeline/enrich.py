"""Stage 3 — LLM enrichment.

Two independent enrichment steps, both with deterministic fallbacks so
the pipeline runs end-to-end without an OpenAI key:

  Step 1 — Sector classification of every unique award program name into one of
           12 sectors. Cached by sha256(prog_name_en) so a name is never
           classified twice. Low-confidence / invalid results retry once with a
           stricter prompt, then fall back to OTHER.

  Step 2 — Eligibility extraction from the Business Benefits Finder program
           descriptions via function calling, with strict validation of every
           returned field before it's trusted.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pandas as pd

from llm import chat_json, llm_available
from utils import (
    ACTIVITIES, CACHE_DIR, PROCESSED_DIR, RAW_DIR, SIZE_BANDS, SECTORS,
    VALID_PROVINCE_CODES, chunked, get_logger, load_json_cache,
    log_pipeline_run, normalize_province, read_csv_file,
    save_json_cache, sha256,
)

SECTOR_MAP_PATH = PROCESSED_DIR / "program_sector_map.json"

log = get_logger("pipeline.enrich")

SECTOR_CACHE = CACHE_DIR / "sector_cache.json"

CLASSIFY_PROMPT = """You are classifying Canadian government grant programs by industry sector.

Program name: {name}
Program description (if available): {desc}

Classify this into exactly one of these sectors:
IT_SOFTWARE, ENGINEERING, CYBERSECURITY, MANAGEMENT_CONSULTING,
LIFE_SCIENCES, CLEAN_TECH, MANUFACTURING, AGRICULTURE,
ARTS_CULTURE, EDUCATION, FINANCIAL_SERVICES, OTHER

Return JSON: {{"sector": "<SECTOR>", "confidence": "<high|medium|low>"}}"""

STRICT_SUFFIX = (
    "\n\nIMPORTANT: You MUST return one of exactly these 12 values and nothing else: "
    + ", ".join(SECTORS)
)

# Keyword heuristic used as the offline fallback (and a sanity check).
SECTOR_KEYWORDS = {
    "CYBERSECURITY": ["cyber", "security", "zero-trust", "threat"],
    "IT_SOFTWARE": ["software", "digital", "saas", "cloud", "data", "analytics", "app", "it "],
    "ENGINEERING": ["engineering", "aerospace", "robotics", "marine", "mechanical"],
    "MANAGEMENT_CONSULTING": ["advisory", "consulting", "management", "strategy"],
    "LIFE_SCIENCES": ["genomic", "biohealth", "health", "bio", "life science", "medical"],
    "CLEAN_TECH": ["clean", "carbon", "energy", "climate", "green", "emission"],
    "MANUFACTURING": ["manufactur", "assembly", "production", "industrial fund"],
    "AGRICULTURE": ["agri", "farm", "crop", "agriculture"],
    "ARTS_CULTURE": ["art", "culture", "cultural", "heritage", "media"],
    "EDUCATION": ["education", "learning", "school", "training", "skills"],
    "FINANCIAL_SERVICES": ["fintech", "financial", "payments", "banking", "insurance"],
}


def _heuristic_sector(name: str, desc: str) -> str:
    text = f"{name} {desc}".lower()
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(kw in text for kw in kws):
            return sector
    return "OTHER"


# ---------------------------------------------------------------------------
# Step 1 — sector classification
# ---------------------------------------------------------------------------
async def _classify_one(name: str, desc: str, issues: dict) -> str:
    desc = (desc or "")[:300]
    if not llm_available():
        return _heuristic_sector(name, desc)

    async def ask(prompt: str) -> dict:
        return await chat_json([{"role": "user", "content": prompt}])

    try:
        res = await ask(CLASSIFY_PROMPT.format(name=name, desc=desc))
        sector = str(res.get("sector", "")).upper()
        confidence = str(res.get("confidence", "low")).lower()
        if confidence == "low" or sector not in SECTORS:
            res = await ask(CLASSIFY_PROMPT.format(name=name, desc=desc) + STRICT_SUFFIX)
            sector = str(res.get("sector", "")).upper()
        if sector not in SECTORS:
            issues["classification_failed"] = issues.get("classification_failed", 0) + 1
            return "OTHER"
        return sector
    except Exception as e:  # noqa: BLE001
        log.warning("Classification failed for %r: %s", name, e)
        issues["classification_failed"] = issues.get("classification_failed", 0) + 1
        return "OTHER"


async def classify_sectors(program_names: list[tuple[str, str]], issues: dict) -> dict[str, str]:
    """program_names: list of (prog_name_en, description). Returns name -> sector."""
    cache = load_json_cache(SECTOR_CACHE)
    # Unique by name; never classify the same program name twice.
    unique: dict[str, str] = {}
    for name, desc in program_names:
        name = str(name or "").strip()
        if name and name not in unique:
            unique[name] = str(desc or "")

    result: dict[str, str] = {}
    todo: list[tuple[str, str]] = []
    for name, desc in unique.items():
        key = sha256(name)
        if key in cache:
            result[name] = cache[key]
        else:
            todo.append((name, desc))

    log.info("Sector classification: %s cached, %s to classify (llm=%s)",
             len(result), len(todo), llm_available())

    for batch in chunked(todo, 50):
        sectors = await asyncio.gather(*[_classify_one(n, d, issues) for n, d in batch])
        for (name, _), sector in zip(batch, sectors):
            result[name] = sector
            cache[sha256(name)] = sector

    save_json_cache(SECTOR_CACHE, cache)
    return result


# ---------------------------------------------------------------------------
# Step 2 — eligibility extraction (BBF programs)
# ---------------------------------------------------------------------------
ELIGIBILITY_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_eligibility",
        "description": "Extract structured eligibility criteria from a program description.",
        "parameters": {
            "type": "object",
            "properties": {
                "eligible_provinces": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Two-letter province codes, or ['ALL'] if national",
                },
                "eligible_sizes": {
                    "type": "array",
                    "items": {"type": "string", "enum": SIZE_BANDS},
                },
                "eligible_activities": {
                    "type": "array",
                    "items": {"type": "string", "enum": ACTIVITIES},
                },
                "min_amount": {"type": "number"},
                "max_amount": {"type": "number"},
                "program_type": {
                    "type": "string",
                    "enum": ["Grant", "Loan", "Tax Credit", "Advisory", "Other"],
                },
            },
        },
    },
}

PROVINCE_NAME_RE = {
    "ON": "ontario", "QC": "quebec", "BC": "british columbia", "AB": "alberta",
    "MB": "manitoba", "SK": "saskatchewan", "NS": "nova scotia", "NB": "new brunswick",
    "NL": "newfoundland", "PE": "prince edward island", "NT": "northwest territories",
    "NU": "nunavut", "YT": "yukon",
}


def _heuristic_eligibility(desc: str) -> dict:
    text = (desc or "").lower()
    provinces = [code for code, name in PROVINCE_NAME_RE.items() if name in text]
    if not provinces or "nationally" in text or "all provinces" in text or "across canada" in text:
        provinces = ["ALL"]

    sizes = []
    m = re.search(r"(\d+)\s*to\s*(\d+)\s*employees", text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        for band in SIZE_BANDS:
            blo = int(band.split("-")[0]) if "-" in band else 200
            bhi = int(band.split("-")[1]) if "-" in band else 10_000
            if blo <= hi and bhi >= lo:
                sizes.append(band)
    if not sizes:
        sizes = list(SIZE_BANDS)

    activities = []
    for kw, act in [("r&d", "R&D"), ("research", "R&D"), ("export", "Export"),
                    ("hiring", "Hiring"), ("digital", "Digital Transformation"),
                    ("equipment", "Equipment"), ("clean tech", "Clean Tech"),
                    ("indigenous", "Indigenous")]:
        if kw in text and act not in activities:
            activities.append(act)

    # Catch "X to Y dollars", "between X and Y dollars", and bare "Y dollars".
    rng = re.search(r"(\d[\d,]{3,})\s*(?:to|and|-)\s*(\d[\d,]{3,})\s*dollars", text)
    if rng:
        min_amount = int(rng.group(1).replace(",", ""))
        max_amount = int(rng.group(2).replace(",", ""))
    else:
        amounts = [int(a.replace(",", "")) for a in re.findall(r"(\d[\d,]{3,})\s*dollars", text)]
        min_amount = min(amounts) if amounts else None
        max_amount = max(amounts) if amounts else None

    ptype = "Grant"
    if "loan" in text or "repayable" in text:
        ptype = "Loan"
    elif "tax credit" in text or "sred" in text or "sr&ed" in text:
        ptype = "Tax Credit"
    elif "advisory" in text:
        ptype = "Advisory"

    sred_related = bool(re.search(r"sred|sr&ed|scientific research|experimental development", text))
    tax_credit_type = "SR&ED" if re.search(r"sred|sr&ed", text) else ("OTHER" if "tax credit" in text else None)

    deadline = None
    dm = re.search(r"deadline[:\s]+(\d{4}-\d{2}-\d{2})", text)
    if dm:
        deadline = dm.group(1)

    return {
        "eligible_provinces": provinces, "eligible_sizes": sizes,
        "eligible_activities": activities or ["Other"],
        "min_amount": min_amount, "max_amount": max_amount, "program_type": ptype,
        "sred_related": sred_related, "tax_credit_type": tax_credit_type,
        "deadline": deadline,
    }


def _validate_eligibility(raw: dict, issues: dict) -> dict:
    """Validate every LLM-returned field; null out anything that fails."""
    out: dict = {}

    provinces = raw.get("eligible_provinces") or []
    if provinces == ["ALL"] or all(p in VALID_PROVINCE_CODES for p in provinces):
        out["eligible_provinces"] = provinces
    else:
        bad = [p for p in provinces if p != "ALL" and p not in VALID_PROVINCE_CODES]
        # Try to rescue by normalizing names; drop the rest.
        rescued = [normalize_province(p) or p for p in provinces]
        rescued = [p for p in rescued if p in VALID_PROVINCE_CODES or p == "ALL"]
        out["eligible_provinces"] = rescued or None
        issues["invalid_province"] = issues.get("invalid_province", 0) + len(bad)

    sizes = raw.get("eligible_sizes") or []
    valid_sizes = [s for s in sizes if s in SIZE_BANDS]
    if len(valid_sizes) != len(sizes):
        issues["invalid_size"] = issues.get("invalid_size", 0) + (len(sizes) - len(valid_sizes))
    out["eligible_sizes"] = valid_sizes or None

    acts = raw.get("eligible_activities") or []
    out["eligible_activities"] = [a for a in acts if a in ACTIVITIES] or None

    min_a, max_a = raw.get("min_amount"), raw.get("max_amount")
    if min_a is not None and max_a is not None and min_a > max_a:
        issues["min_gt_max"] = issues.get("min_gt_max", 0) + 1
        min_a = max_a = None
    out["min_amount"] = min_a
    out["max_amount"] = max_a

    out["program_type"] = raw.get("program_type") or "Other"
    return out


async def _extract_one(desc: str, issues: dict) -> dict:
    if not llm_available():
        return _validate_eligibility(_heuristic_eligibility(desc), issues)
    try:
        raw = await chat_json(
            messages=[
                {"role": "system", "content": "Extract eligibility criteria. Use the tool."},
                {"role": "user", "content": (desc or "")[:1500]},
            ],
            tools=[ELIGIBILITY_TOOL],
            tool_choice={"type": "function", "function": {"name": "extract_eligibility"}},
        )
        return _validate_eligibility(raw, issues)
    except Exception as e:  # noqa: BLE001
        log.warning("Eligibility extraction failed: %s", e)
        issues["extraction_failed"] = issues.get("extraction_failed", 0) + 1
        return _validate_eligibility(_heuristic_eligibility(desc), issues)


def _latest_bbf() -> Path | None:
    files = sorted(RAW_DIR.glob("bbf_programs_*"))
    return files[-1] if files else None


def _pick_column(df: pd.DataFrame, *candidates: str) -> pd.Series:
    for col in candidates:
        if col in df.columns:
            return df[col].fillna("").astype(str)
    return pd.Series([""] * len(df), index=df.index)


def _pick_column_fuzzy(df: pd.DataFrame, *substrings: str) -> pd.Series:
    """Pick the first column whose normalized name contains all substrings."""
    for col in df.columns:
        key = str(col).lower()
        if all(s in key for s in substrings):
            return df[col].fillna("").astype(str)
    return pd.Series([""] * len(df), index=df.index)


def _normalize_bbf_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map Innovation Canada / BBF export columns to our canonical schema."""
    df = df.copy()
    df.columns = [
        str(c).strip().lower().replace(" ", "_").replace("(", "").replace(")", "")
        for c in df.columns
    ]

    name = _pick_column(
        df,
        "program_name",
        "name",
        "title",
        "title_en",
        "title_english",
        "program_title",
        "program_title_en",
        "program_name_en",
    )
    if name.str.strip().eq("").all():
        name = _pick_column_fuzzy(df, "title", "english")
    department = _pick_column(
        df,
        "department",
        "organization",
        "organization_name",
        "organization_name_en",
        "department_en",
        "owner_org",
        "administering_department",
    )
    if department.str.strip().eq("").all():
        department = _pick_column_fuzzy(df, "organization", "english")
    description = _pick_column(
        df,
        "description",
        "description_en",
        "long_description",
        "long_description_en",
        "program_description",
        "program_description_en",
        "short_description",
    )
    if description.str.strip().eq("").all():
        description = _pick_column_fuzzy(df, "description", "english")
    apply_url = _pick_column(
        df,
        "apply_url",
        "url",
        "link",
        "link_en",
        "website",
        "program_url",
        "application_url",
        "business_benefits_finder_link",
    )
    if apply_url.str.strip().eq("").all():
        apply_url = _pick_column_fuzzy(df, "organization", "url", "english")
    deadline = _pick_column(df, "deadline", "application_deadline", "closing_date")
    status = _pick_column(df, "status", "program_status", "availability")

    out = pd.DataFrame(
        {
            "name": name.str.strip(),
            "department": department.str.strip(),
            "description": description.str.strip(),
            "apply_url": apply_url.str.strip(),
            "deadline": deadline.str.strip(),
            "status": status.str.strip(),
        }
    )
    template_markers = ("titre -", "title -", "description courte", "short description")
    mask = out["name"].str.lower().apply(
        lambda s: not any(m in s for m in template_markers)
    )
    out = out[mask & (out["name"] != "")].reset_index(drop=True)
    return out


def _read_bbf(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        df = read_csv_file(path)
    return _normalize_bbf_columns(df)


async def enrich_programs(issues: dict) -> pd.DataFrame:
    path = _latest_bbf()
    if path is None:
        log.warning("No BBF file found; skipping program enrichment")
        return pd.DataFrame()
    df = _read_bbf(path)
    log.info("Enriching %s BBF programs (llm=%s)", len(df), llm_available())

    descs = df.get("description", pd.Series([""] * len(df))).fillna("").tolist()
    results = []
    for batch in chunked(list(descs), 50):
        results.extend(await asyncio.gather(*[_extract_one(d, issues) for d in batch]))

    enriched = pd.DataFrame(results)
    out = pd.concat([df.reset_index(drop=True), enriched.reset_index(drop=True)], axis=1)
    out_path = PROCESSED_DIR / "programs_enriched.csv"
    # Serialize list columns as JSON-ish strings for the CSV checkpoint.
    out.to_csv(out_path, index=False)
    log.info("Wrote %s enriched programs -> %s", len(out), out_path)
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
async def run() -> None:
    issues: dict = {}
    awards_path = PROCESSED_DIR / "awards_clean.csv"

    # Classify unique program names only — not every award row (1.3M+).
    names_df = read_csv_file(
        awards_path,
        usecols=["program_name_raw", "description"],
    )
    unique = names_df.drop_duplicates(subset=["program_name_raw"], keep="first").copy()
    unique["program_name_raw"] = unique["program_name_raw"].fillna("").astype(str)
    unique["description"] = unique["description"].fillna("").astype(str)
    unique = unique[unique["program_name_raw"].str.strip() != ""]
    pairs = list(zip(unique["program_name_raw"], unique["description"]))
    del names_df, unique

    sector_map = await classify_sectors(pairs, issues)

    SECTOR_MAP_PATH.write_text(
        json.dumps(sector_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info(
        "Saved sector map for %s programs -> %s (applied at load time; no CSV rewrite)",
        len(sector_map), SECTOR_MAP_PATH.name,
    )

    await enrich_programs(issues)

    log_pipeline_run("enrich", len(sector_map), len(sector_map), 0, issues)


if __name__ == "__main__":
    asyncio.run(run())
