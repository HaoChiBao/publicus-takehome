"""Stage 2 — Clean & normalize the Open Canada award history (+ IRAP, same schema).

This is the most important stage. Transformations are applied in a fixed order
and every record is preserved: when a field fails a cleaning step we null the
offending field and record an issue flag rather than dropping the row.

Steps:
  1. Amendment deduplication  (keep max amendment per ref_number, flag the rest)
  2. Amount cleaning          (float cast; null/zero/negative/unparseable flags)
  3. Date normalization       (multi-format -> ISO; derive fiscal_year)
  4. Province normalization   (free text -> 2-letter code)
  5. Department normalization (owner_org code -> clean name)
  6. Dedup fingerprint        (sha256 fingerprint; flag cross-source duplicates)

Output: data/processed/awards_clean.csv  (raw columns preserved alongside
normalized ones) and a pipeline_runs row with per-issue counts.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Optional

import pandas as pd

from utils import (
    PROCESSED_DIR, RAW_DIR,
    dedup_hash, derive_fiscal_year, get_logger, log_pipeline_run,
    normalize_department, normalize_province, parse_date,
)

log = get_logger("pipeline.clean")

AGREEMENT_TYPE_MAP = {"g": "Grant", "c": "Contribution", "o": "Other"}

# Raw columns the Open Canada / IRAP CSVs are expected to carry. We only rely on
# this subset; anything else is ignored but preserved is not required by load.
EXPECTED_COLS = [
    "ref_number", "amendment_number", "agreement_type",
    "recipient_legal_name", "recipient_operating_name", "recipient_business_number",
    "recipient_province", "recipient_city", "prog_name_en", "prog_purpose_en",
    "agreement_value", "agreement_start_date", "agreement_end_date",
    "description_en", "naics_identifier", "owner_org", "owner_org_title",
]


def _latest_raw(prefix: str) -> Optional[Path]:
    files = sorted(RAW_DIR.glob(f"{prefix}*.csv"))
    return files[-1] if files else None


def _read_source(path: Path, source: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    for col in EXPECTED_COLS:
        if col not in df.columns:
            df[col] = None
    df["source"] = source
    log.info("Loaded %s rows from %s (source=%s)", len(df), path.name, source)
    return df


# ---------------------------------------------------------------------------
# Step 1 — amendment deduplication
# ---------------------------------------------------------------------------
def step1_amendments(df: pd.DataFrame) -> pd.DataFrame:
    df["amendment_number"] = (
        pd.to_numeric(df["amendment_number"], errors="coerce").fillna(0).astype(int)
    )
    df["is_latest_amendment"] = False
    # Within each ref_number, the row with the max amendment number is "latest".
    # Rows without a ref_number are each treated as their own latest.
    has_ref = df["ref_number"].notna() & (df["ref_number"].astype(str).str.len() > 0)
    idx_latest = (
        df[has_ref]
        .groupby("ref_number")["amendment_number"]
        .idxmax()
        .tolist()
    )
    df.loc[idx_latest, "is_latest_amendment"] = True
    df.loc[~has_ref, "is_latest_amendment"] = True
    superseded = int((~df["is_latest_amendment"]).sum())
    log.info("Step 1: flagged %s superseded amendment rows", superseded)
    return df


# ---------------------------------------------------------------------------
# Step 2 — amount cleaning
# ---------------------------------------------------------------------------
def step2_amounts(df: pd.DataFrame, issues: Counter) -> pd.DataFrame:
    amounts, flags = [], []
    for raw in df["agreement_value"]:
        flag = None
        if raw is None or (isinstance(raw, float) and pd.isna(raw)) or str(raw).strip() == "":
            amounts.append(None)
            flag = "null_amount"
        else:
            try:
                val = float(str(raw).replace(",", "").replace("$", "").strip())
                if val == 0:
                    amounts.append(0.0)
                    flag = "zero_amount"
                elif val < 0:
                    amounts.append(abs(val))      # credit amendment -> store magnitude
                    flag = "negative_amount"
                else:
                    amounts.append(val)
            except (ValueError, TypeError):
                amounts.append(None)
                flag = "unparseable_amount"
        flags.append(flag)
        if flag:
            issues[flag] += 1
    df["amount"] = amounts
    df["amount_flag"] = flags
    log.info("Step 2: amount issues -> %s", {k: issues[k] for k in
             ("null_amount", "zero_amount", "negative_amount", "unparseable_amount") if issues[k]})
    return df


# ---------------------------------------------------------------------------
# Step 3 — date normalization + fiscal year
# ---------------------------------------------------------------------------
def step3_dates(df: pd.DataFrame, issues: Counter) -> pd.DataFrame:
    def norm(col: str) -> list:
        out = []
        for raw in df[col]:
            d = parse_date(raw)
            if d is None and raw is not None and str(raw).strip() != "":
                issues["bad_date"] += 1
            out.append(d.isoformat() if d else None)
        return out

    df["start_date"] = norm("agreement_start_date")
    df["end_date"] = norm("agreement_end_date")
    df["fiscal_year"] = [
        derive_fiscal_year(parse_date(raw)) for raw in df["agreement_start_date"]
    ]
    log.info("Step 3: bad_date=%s", issues["bad_date"])
    return df


# ---------------------------------------------------------------------------
# Step 4 — province normalization
# ---------------------------------------------------------------------------
def step4_provinces(df: pd.DataFrame, issues: Counter) -> pd.DataFrame:
    out = []
    for raw in df["recipient_province"]:
        code = normalize_province(raw)
        if code is None and raw is not None and str(raw).strip() != "":
            issues["unknown_province"] += 1
        out.append(code)
    df["province"] = out
    log.info("Step 4: unknown_province=%s", issues["unknown_province"])
    return df


# ---------------------------------------------------------------------------
# Step 5 — department normalization
# ---------------------------------------------------------------------------
def step5_departments(df: pd.DataFrame) -> pd.DataFrame:
    df["department"] = df["owner_org"].apply(normalize_department)
    return df


# ---------------------------------------------------------------------------
# Step 6 — dedup fingerprint + cross-source duplicate detection
# ---------------------------------------------------------------------------
def step6_fingerprint(df: pd.DataFrame, issues: Counter) -> pd.DataFrame:
    df["dedup_hash"] = [
        dedup_hash(name, amt, sd)
        for name, amt, sd in zip(df["recipient_legal_name"], df["amount"], df["start_date"])
    ]
    counts = df["dedup_hash"].value_counts()
    dup_hashes = set(counts[counts > 1].index)
    df["is_cross_source_dup"] = df["dedup_hash"].isin(dup_hashes)
    issues["cross_source_duplicate"] = int(df["is_cross_source_dup"].sum())
    log.info("Step 6: cross_source_duplicate=%s", issues["cross_source_duplicate"])
    return df


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    """Project to the columns load.py needs, preserving raw values alongside."""
    df["agreement_type"] = (
        df["agreement_type"].astype(str).str.strip().str.lower()
        .map(AGREEMENT_TYPE_MAP).fillna("Other")
    )
    df["recipient_name_raw"] = df["recipient_legal_name"]
    df["program_name_raw"] = df["prog_name_en"]
    df["city"] = df["recipient_city"]
    df["naics_code"] = df["naics_identifier"]
    df["description"] = df["description_en"]
    return df


def clean() -> pd.DataFrame:
    frames = []
    oc = _latest_raw("open_canada_grants_")
    if oc:
        frames.append(_read_source(oc, "open_canada"))
    for irap in sorted(RAW_DIR.glob("nrc_irap_*.csv")):
        frames.append(_read_source(irap, "nrc_irap"))

    if not frames:
        raise FileNotFoundError(
            "No raw award files found in data/raw/. Run ingest.py first "
            "(USE_SAMPLE_DATA=1 for the offline fixtures)."
        )

    df = pd.concat(frames, ignore_index=True)
    records_raw = len(df)
    issues: Counter = Counter()

    df = step1_amendments(df)
    df = step2_amounts(df, issues)
    df = step3_dates(df, issues)
    df = step4_provinces(df, issues)
    df = step5_departments(df)
    df = step6_fingerprint(df, issues)
    df = _finalize(df)

    # "Clean" = rows we'd surface as a usable latest-amendment award with an amount.
    records_clean = int((df["is_latest_amendment"] & df["amount"].notna()).sum())
    records_skipped = records_raw - records_clean

    out_path = PROCESSED_DIR / "awards_clean.csv"
    df.to_csv(out_path, index=False)
    log.info("Wrote %s cleaned rows -> %s", len(df), out_path)

    log_pipeline_run(
        "open_canada:clean", records_raw, records_clean, records_skipped, dict(issues)
    )
    return df


if __name__ == "__main__":
    clean()
