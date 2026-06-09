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

Large Open Canada downloads (1.9M+ rows) are processed in chunks with only the
columns we need, so the stage fits in memory on a typical laptop.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Optional

import pandas as pd

from utils import (
    PROCESSED_DIR, RAW_DIR,
    dedup_hash, derive_fiscal_year, get_logger, iter_csv_chunks, log_pipeline_run,
    normalize_department, normalize_province, parse_date, read_csv_file,
)

log = get_logger("pipeline.clean")

CHUNK_SIZE = 100_000

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

# Live NRC-IRAP FTP exports use different headers than Open Canada (fixtures match OC).
IRAP_COLUMN_MAP = {
    "Reference Number": "ref_number",
    "Amendment Number": "amendment_number",
    "Agreement Type (English| FrenContribution|Contribution)": "agreement_type",
    "Recipient Legal Name (English|French)": "recipient_legal_name",
    "Recipient Operating Name (English|French)": "recipient_operating_name",
    "Recipient Business Number": "recipient_business_number",
    "Recipient Province or Territory": "recipient_province",
    "Recipient City (English)": "recipient_city",
    "Program Name (English)": "prog_name_en",
    "Program Purpose (English)": "prog_purpose_en",
    "Agreement Value in CAD": "agreement_value",
    "Agreement Start Date": "agreement_start_date",
    "Projected Agreement End Date": "agreement_end_date",
    "Description (English)": "description_en",
    "NAICS Identifier": "naics_identifier",
}

# Fixed output schema so Open Canada + IRAP rows append cleanly to the same CSV.
AWARDS_CLEAN_COLS = [
    *EXPECTED_COLS,
    "source", "is_latest_amendment", "amount", "amount_flag",
    "start_date", "end_date", "fiscal_year", "province", "department",
    "dedup_hash", "is_cross_source_dup",
    "recipient_name_raw", "program_name_raw", "city", "naics_code", "description",
]


def _latest_raw(prefix: str) -> Optional[Path]:
    files = sorted(RAW_DIR.glob(f"{prefix}*.csv"))
    return files[-1] if files else None


def _source_paths() -> list[tuple[Path, str]]:
    paths: list[tuple[Path, str]] = []
    oc = _latest_raw("open_canada_grants_")
    if oc:
        paths.append((oc, "open_canada"))
    for irap in sorted(RAW_DIR.glob("nrc_irap_*.csv")):
        paths.append((irap, "nrc_irap"))
    return paths


def _is_irap(path: Path) -> bool:
    return path.name.startswith("nrc_irap_")


def _normalize_irap(chunk: pd.DataFrame) -> pd.DataFrame:
    chunk = chunk.rename(columns=IRAP_COLUMN_MAP)
    chunk["owner_org"] = "nrc-cnrc"
    chunk["owner_org_title"] = "National Research Council"
    return chunk


def _iter_award_chunks(path: Path, source: str):
    """Yield normalized award chunks with only EXPECTED_COLS populated."""
    if _is_irap(path):
        for chunk in iter_csv_chunks(path, chunksize=CHUNK_SIZE):
            yield _prepare_chunk(_normalize_irap(chunk), source)
    else:
        for chunk in iter_csv_chunks(path, chunksize=CHUNK_SIZE, usecols=EXPECTED_COLS):
            yield _prepare_chunk(chunk, source)


def _build_max_amendments(paths: list[tuple[Path, str]]) -> dict[str, int]:
    """Pass 1 — scan all sources for the max amendment_number per ref_number."""
    max_by_ref: dict[str, int] = {}
    for path, _source in paths:
        if _is_irap(path):
            cols = ["Reference Number", "Amendment Number"]
            renames = {"Reference Number": "ref_number", "Amendment Number": "amendment_number"}
        else:
            cols = ["ref_number", "amendment_number"]
            renames = {}
        for chunk in iter_csv_chunks(path, chunksize=CHUNK_SIZE, usecols=cols):
            if renames:
                chunk = chunk.rename(columns=renames)
            chunk["amendment_number"] = (
                pd.to_numeric(chunk["amendment_number"], errors="coerce").fillna(0).astype(int)
            )
            has_ref = chunk["ref_number"].astype(str).str.strip() != ""
            grouped = chunk.loc[has_ref].groupby("ref_number")["amendment_number"].max()
            for ref, mx in grouped.items():
                max_by_ref[ref] = max(max_by_ref.get(ref, 0), int(mx))
    log.info("Latest-amendment index: %s distinct ref_numbers", len(max_by_ref))
    return max_by_ref


def _project_output(df: pd.DataFrame) -> pd.DataFrame:
    for col in AWARDS_CLEAN_COLS:
        if col not in df.columns:
            df[col] = ""
    return df[AWARDS_CLEAN_COLS]


def _prepare_chunk(chunk: pd.DataFrame, source: str) -> pd.DataFrame:
    for col in EXPECTED_COLS:
        if col not in chunk.columns:
            chunk[col] = ""
    chunk["source"] = source
    return chunk


# ---------------------------------------------------------------------------
# Step 1 — amendment deduplication
# ---------------------------------------------------------------------------
def step1_amendments(
    df: pd.DataFrame, max_by_ref: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    df["amendment_number"] = (
        pd.to_numeric(df["amendment_number"], errors="coerce").fillna(0).astype(int)
    )
    has_ref = df["ref_number"].astype(str).str.strip() != ""
    df["is_latest_amendment"] = True

    if max_by_ref is not None:
        df.loc[has_ref, "is_latest_amendment"] = (
            df.loc[has_ref, "amendment_number"]
            == df.loc[has_ref, "ref_number"].map(max_by_ref)
        )
    else:
        idx_latest = (
            df[has_ref]
            .groupby("ref_number")["amendment_number"]
            .idxmax()
            .tolist()
        )
        df.loc[idx_latest, "is_latest_amendment"] = True
        df.loc[~has_ref, "is_latest_amendment"] = True

    superseded = int((~df["is_latest_amendment"]).sum())
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
    return df


# ---------------------------------------------------------------------------
# Step 5 — department normalization
# ---------------------------------------------------------------------------
def step5_departments(df: pd.DataFrame) -> pd.DataFrame:
    df["department"] = df["owner_org"].apply(normalize_department)
    return df


# ---------------------------------------------------------------------------
# Chunk transform (shared by fingerprint scan + final write)
# ---------------------------------------------------------------------------
def _transform_chunk(
    chunk: pd.DataFrame,
    max_by_ref: dict[str, int],
    issues: Counter,
    dup_hashes: set[str] | None = None,
) -> pd.DataFrame:
    chunk = step1_amendments(chunk, max_by_ref)
    chunk = step2_amounts(chunk, issues)
    chunk = step3_dates(chunk, issues)
    chunk = step4_provinces(chunk, issues)
    chunk = step5_departments(chunk)
    chunk["dedup_hash"] = [
        dedup_hash(name, amt, sd)
        for name, amt, sd in zip(chunk["recipient_legal_name"], chunk["amount"], chunk["start_date"])
    ]
    if dup_hashes is not None:
        chunk["is_cross_source_dup"] = chunk["dedup_hash"].isin(dup_hashes)
    out = _project_output(_finalize(chunk))
    return out


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


def _collect_dup_hashes(
    paths: list[tuple[Path, str]], max_by_ref: dict[str, int],
) -> tuple[Counter, set[str]]:
    """Pass 2 — scan sources in chunks to count fingerprint frequencies (no temp file)."""
    hash_counts: Counter = Counter()
    silent = Counter()
    for path, source in paths:
        log.info("Fingerprint scan: %s (source=%s)", path.name, source)
        for chunk in _iter_award_chunks(path, source):
            out = _transform_chunk(chunk, max_by_ref, silent)
            hash_counts.update(out["dedup_hash"])
    dup_hashes = {h for h, c in hash_counts.items() if c > 1}
    return hash_counts, dup_hashes


def clean() -> pd.DataFrame:
    paths = _source_paths()
    if not paths:
        raise FileNotFoundError(
            "No raw award files found in data/raw/. Run `python pipeline/ingest.py` first."
        )

    issues: Counter = Counter()
    max_by_ref = _build_max_amendments(paths)

    hash_counts, dup_hashes = _collect_dup_hashes(paths, max_by_ref)
    issues["cross_source_duplicate"] = sum(
        c for h, c in hash_counts.items() if h in dup_hashes
    )
    log.info("Step 6: cross_source_duplicate=%s", issues["cross_source_duplicate"])

    out_path = PROCESSED_DIR / "awards_clean.csv"
    tmp = PROCESSED_DIR / "awards_clean.tmp.csv"
    for stale in (out_path, tmp, tmp.with_suffix(tmp.suffix + ".tmp")):
        if stale.exists():
            stale.unlink()

    records_raw = 0
    records_clean = 0
    first = True
    for path, source in paths:
        log.info("Writing %s (source=%s) in %s-row chunks", path.name, source, CHUNK_SIZE)
        for chunk in _iter_award_chunks(path, source):
            out = _transform_chunk(chunk, max_by_ref, issues, dup_hashes)
            records_raw += len(out)
            records_clean += int((out["is_latest_amendment"] & out["amount"].notna()).sum())
            out.to_csv(out_path, mode="w" if first else "a", header=first, index=False)
            first = False

    log.info(
        "Wrote %s cleaned rows -> %s (amount issues: %s, bad_date=%s, unknown_province=%s)",
        records_raw, out_path,
        {k: issues[k] for k in ("null_amount", "zero_amount", "negative_amount", "unparseable_amount") if issues[k]},
        issues["bad_date"], issues["unknown_province"],
    )

    records_skipped = records_raw - records_clean
    log_pipeline_run(
        "open_canada:clean", records_raw, records_clean, records_skipped, dict(issues)
    )
    # Return a small head sample so callers/tests can inspect schema without OOM.
    return read_csv_file(out_path, nrows=5)


if __name__ == "__main__":
    clean()
