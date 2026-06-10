"""Shared helpers for the Publicus grants data pipeline.

Everything here is deliberately dependency-light and side-effect free (other than
the explicit Supabase / filesystem helpers) so the individual pipeline stages
stay readable and testable.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, date
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv()  # .env
load_dotenv(ROOT / ".env.local", override=True)  # local overrides (Supabase keys, etc.)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
PROCESSED_DIR = DATA_DIR / "processed"

for _d in (RAW_DIR, CACHE_DIR, PROCESSED_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def requests_verify() -> bool:
    """Whether HTTPS downloads should verify TLS certificates."""
    return os.getenv("SSL_VERIFY", "1") != "0"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


log = get_logger("pipeline.utils")


# ---------------------------------------------------------------------------
# Terminal progress (stderr — safe alongside logging on stdout)
# ---------------------------------------------------------------------------
def count_csv_rows(path: Path) -> int:
    """Row count excluding the header."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return max(sum(1 for _ in f) - 1, 0)


def _format_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def progress_bar(label: str, current: int, total: int, width: int = 40) -> str:
    if total > 0:
        pct = min(current / total, 1.0)
        filled = int(width * pct)
        bar = "=" * filled + (">" if filled < width else "") + " " * max(
            width - filled - (1 if filled < width else 0), 0
        )
        return (
            f"  {label}: [{bar}] {pct * 100:5.1f}% "
            f"({_format_count(current)} / {_format_count(total)})"
        )
    return f"  {label}: {_format_count(current)} rows..."


def show_progress(label: str, current: int, total: int) -> None:
    import sys

    sys.stderr.write("\r" + progress_bar(label, current, total))
    sys.stderr.flush()


def finish_progress() -> None:
    import sys

    sys.stderr.write("\n")
    sys.stderr.flush()


def phase_banner(phase: int, total_phases: int, title: str) -> None:
    import sys

    sys.stderr.write(f"\n{'=' * 60}\n  [{phase}/{total_phases}] {title}\n{'=' * 60}\n")
    sys.stderr.flush()


def timestamp() -> str:
    """Filesystem-friendly timestamp, e.g. 20240605_171930."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# Encodings seen across Canadian open-data exports (Open Canada = UTF-8; IRAP FTP = cp1252).
CSV_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin-1")


def read_csv_file(path: Path, **kwargs: Any):
    """Read a CSV, trying common encodings used by federal open-data sources."""
    import pandas as pd

    opts = _csv_read_kwargs(kwargs)
    last_err: UnicodeDecodeError | None = None
    for encoding in CSV_ENCODINGS:
        try:
            df = pd.read_csv(path, encoding=encoding, **opts)
            if encoding not in {"utf-8", "utf-8-sig"}:
                log.info("Read %s with encoding %s", path.name, encoding)
            return df
        except UnicodeDecodeError as e:
            last_err = e
    if last_err:
        raise last_err
    raise UnicodeDecodeError("unknown", b"", 0, 0, "unable to decode CSV")


def _csv_read_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    opts = dict(kwargs)
    opts.setdefault("dtype", str)
    opts.setdefault("keep_default_na", False)
    opts.setdefault("na_values", [""])
    opts.setdefault("low_memory", False)
    return opts


def iter_csv_chunks(path: Path, chunksize: int = 100_000, **kwargs: Any):
    """Yield chunks from a large CSV without loading the whole file into memory."""
    import pandas as pd

    opts = _csv_read_kwargs(kwargs)
    last_err: UnicodeDecodeError | None = None
    for encoding in CSV_ENCODINGS:
        try:
            reader = pd.read_csv(
                path, encoding=encoding, chunksize=chunksize, **opts,
            )
            for chunk in reader:
                yield chunk
            if encoding not in {"utf-8", "utf-8-sig"}:
                log.info("Read %s in chunks with encoding %s", path.name, encoding)
            return
        except UnicodeDecodeError as e:
            last_err = e
    if last_err:
        raise last_err
    raise UnicodeDecodeError("unknown", b"", 0, 0, "unable to decode CSV")


def rewrite_csv_in_chunks(
    path: Path,
    transform: Callable[[Any], Any],
    chunksize: int = 100_000,
    **read_kwargs: Any,
) -> int:
    """Apply a transform to each chunk and atomically replace the source CSV."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    total = 0
    first = True
    try:
        for chunk in iter_csv_chunks(path, chunksize=chunksize, **read_kwargs):
            out = transform(chunk)
            out.to_csv(tmp, mode="w" if first else "a", header=first, index=False)
            first = False
            total += len(out)
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    return total


# ---------------------------------------------------------------------------
# Reference data / normalization maps
# ---------------------------------------------------------------------------
SECTORS = [
    "IT_SOFTWARE", "ENGINEERING", "CYBERSECURITY", "MANAGEMENT_CONSULTING",
    "LIFE_SCIENCES", "CLEAN_TECH", "MANUFACTURING", "AGRICULTURE",
    "ARTS_CULTURE", "EDUCATION", "FINANCIAL_SERVICES", "OTHER",
]

SIZE_BANDS = ["1-10", "11-50", "51-200", "200+"]

ACTIVITIES = [
    "R&D", "Export", "Hiring", "Digital Transformation",
    "Equipment", "Clean Tech", "Indigenous", "Other",
]

VALID_PROVINCE_CODES = {
    "ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE", "NT", "NU", "YT",
}

PROVINCE_MAP = {
    "ontario": "ON", "on": "ON",
    "quebec": "QC", "québec": "QC", "qc": "QC",
    "british columbia": "BC", "bc": "BC", "colombie-britannique": "BC",
    "alberta": "AB", "ab": "AB",
    "manitoba": "MB", "mb": "MB",
    "saskatchewan": "SK", "sk": "SK",
    "nova scotia": "NS", "ns": "NS", "nouvelle-écosse": "NS",
    "new brunswick": "NB", "nb": "NB", "nouveau-brunswick": "NB",
    "newfoundland": "NL", "nl": "NL", "newfoundland and labrador": "NL",
    "prince edward island": "PE", "pei": "PE", "pe": "PE",
    "northwest territories": "NT", "nt": "NT",
    "nunavut": "NU", "nu": "NU",
    "yukon": "YT", "yt": "YT",
}

DEPT_MAP = {
    "nrc-cnrc": "National Research Council",
    "ised-isde": "Innovation, Science and Economic Development",
    "feddevontario": "FedDev Ontario",
    "acoa-apeca": "Atlantic Canada Opportunities Agency",
    "ced-dec": "Canada Economic Development for Quebec",
    "pracan": "Prairies Economic Development Canada",
    "pacican": "Pacific Economic Development Canada",
    "cannor": "Canadian Northern Economic Development Agency",
    "tc": "Transport Canada",
    "agr": "Agriculture and Agri-Food Canada",
    "wd": "Western Economic Diversification Canada",
    "esdc-edsc": "Employment and Social Development Canada",
    "ssc-spc": "Shared Services Canada",
    "ec": "Environment and Climate Change Canada",
}


def normalize_province(value: Optional[str]) -> Optional[str]:
    """Map a free-text province string to a two-letter code. None if unknown."""
    if value is None:
        return None
    key = str(value).strip().lower()
    if not key:
        return None
    return PROVINCE_MAP.get(key)


def normalize_department(value: Optional[str]) -> Optional[str]:
    """Map an owner_org code to a clean department name. Falls back to the input."""
    if value is None:
        return None
    key = str(value).strip().lower()
    if not key:
        return None
    return DEPT_MAP.get(key, str(value).strip())


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y"]


def parse_date(value: Any) -> Optional[date]:
    """Parse the documented input formats into a date. None if unparseable.

    Formats handled (in priority order): YYYY-MM-DD, DD/MM/YYYY, YYYY/MM/DD, MM/DD/YYYY.
    Note: DD/MM vs MM/DD is genuinely ambiguous for day <= 12; we prefer DD/MM
    (the Canadian/ISO-adjacent convention) and only fall back to MM/DD.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "nat", "none", "null"}:
        return None
    s = s.split(" ")[0]  # drop any time component
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def derive_fiscal_year(d: Optional[date]) -> Optional[str]:
    """Canadian federal fiscal year (April 1 – March 31) as 'YYYY-YY'."""
    if d is None:
        return None
    if d.month >= 4:
        start = d.year
    else:
        start = d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------
def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dedup_hash(recipient_legal_name: Optional[str], amount: Any, start_date: Any) -> str:
    """Fingerprint for cross-source duplicate detection."""
    name = (recipient_legal_name or "").strip().lower()
    return sha256(f"{name}|{amount}|{start_date}")


# ---------------------------------------------------------------------------
# JSON cache helpers
# ---------------------------------------------------------------------------
def load_json_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            log.warning("Cache %s was corrupt — starting fresh", path)
    return {}


def save_json_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Supabase access (REST client, used by the pipeline for writes)
# ---------------------------------------------------------------------------
def get_supabase():
    """Return a Supabase client authenticated with the service role key.

    Imported lazily so that scripts that don't touch the DB (e.g. ingest in
    sample mode) don't require the dependency or credentials.
    """
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def log_pipeline_run(
    source: str,
    records_raw: int,
    records_clean: int,
    records_skipped: int,
    issues: Optional[dict] = None,
) -> None:
    """Insert a row into pipeline_runs. Best-effort: never crash the pipeline."""
    payload = {
        "source": source,
        "records_raw": int(records_raw),
        "records_clean": int(records_clean),
        "records_skipped": int(records_skipped),
        "issues": issues or {},
    }
    if not os.getenv("SUPABASE_URL"):
        # No DB configured — persist locally so pipeline status still works.
        local = PROCESSED_DIR / "pipeline_runs.jsonl"
        with local.open("a") as f:
            f.write(json.dumps({**payload, "run_at": datetime.now().isoformat()}) + "\n")
        log.info("[pipeline_runs] (local) %s: raw=%s clean=%s skipped=%s",
                 source, records_raw, records_clean, records_skipped)
        return
    try:
        get_supabase().table("pipeline_runs").insert(payload).execute()
        log.info("[pipeline_runs] %s: raw=%s clean=%s skipped=%s",
                 source, records_raw, records_clean, records_skipped)
    except Exception as e:  # noqa: BLE001 - logging only, must not abort pipeline
        log.error("Failed to write pipeline_runs row for %s: %s", source, e)


def chunked(seq: list, size: int) -> Iterable[list]:
    """Yield successive `size`-length chunks from a list."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
