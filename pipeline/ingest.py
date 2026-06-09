"""Stage 1 — Ingest.

Download raw source files and save them to data/raw/ with timestamps.
This stage does NOT transform anything; it only fetches bytes and records
raw row counts to pipeline_runs.

Sources:
  1. Open Canada Grants CSV (primary award history)
  2. Business Benefits Finder (BBF) program catalogue, via the CKAN API
  3. NRC-IRAP fiscal-year grants & contributions CSVs (2021-22 .. 2023-24)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import requests

from utils import (
    RAW_DIR,
    get_logger,
    log_pipeline_run,
    requests_verify,
    timestamp,
)

log = get_logger("pipeline.ingest")

OPEN_CANADA_CSV = (
    "https://open.canada.ca/data/dataset/432527ab-7aac-45b5-81d6-7597107a7013/"
    "resource/1d15a62f-5656-49ad-8c88-f40ce689d831/download/grants.csv"
)
BBF_PACKAGE_API = (
    "https://open.canada.ca/data/api/3/action/package_show?"
    "id=4e75337e-70d0-4ed7-92d1-3b85192ec6b1"
)
IRAP_FISCAL_YEARS = ["2021_22", "2022_23", "2023_24"]
IRAP_URL_TEMPLATE = (
    "https://ftp.maps.canada.ca/pub/nrc_cnrc/Innovation_Innovation/"
    "{year}_grants_and_contributions/{year}_grants_and_contributions.csv"
)

HTTP_TIMEOUT = 120
MIN_OPEN_CANADA_BYTES = 500_000_000  # ~500 MB — sanity check for a real download
CHUNK_SIZE = 1024 * 1024  # 1 MB


def _has_cached_raw_data() -> bool:
    """True when a prior ingest left usable raw files (skip re-downloading multi-GB CSVs)."""
    oc_files = sorted(RAW_DIR.glob("open_canada_grants_*.csv"))
    if not oc_files or oc_files[-1].stat().st_size < MIN_OPEN_CANADA_BYTES:
        return False
    if not list(RAW_DIR.glob("nrc_irap_*.csv")):
        return False
    if not list(RAW_DIR.glob("bbf_programs_*")):
        return False
    return True


def _format_bytes(n: int) -> str:
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f} GB"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def _progress_line(label: str, downloaded: int, total: int, width: int = 36) -> str:
    if total > 0:
        pct = min(downloaded / total, 1.0)
        filled = int(width * pct)
        bar = "=" * filled + (">" if filled < width else "") + " " * (width - filled - (1 if filled < width else 0))
        return (
            f"  {label}: [{bar}] {pct * 100:5.1f}% "
            f"({_format_bytes(downloaded)} / {_format_bytes(total)})"
        )
    return f"  {label}: {_format_bytes(downloaded)} downloaded..."


def _count_csv_rows(path: Path) -> int:
    """Row count excluding the header, tolerant of encoding quirks."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return max(sum(1 for _ in f) - 1, 0)


def _count_bbf_rows(path: Path) -> int:
    import pandas as pd

    if path.suffix.lower() in {".xlsx", ".xls"}:
        return len(pd.read_excel(path))
    return _count_csv_rows(path)


def _validate_download(dest: Path, *, min_bytes: int) -> None:
    """Reject captive-portal HTML pages and truncated downloads."""
    size = dest.stat().st_size
    head = dest.read_bytes()[:512].lower()
    if b"<html" in head or head.lstrip().startswith(b"<!doctype html"):
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"Download of {dest.name} returned HTML instead of data. "
            "Your network may be blocking external downloads (captive portal / proxy). "
            "Download the file manually into data/raw/ and rerun with SKIP_INGEST=1."
        )
    if size < min_bytes:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"Download of {dest.name} is too small ({_format_bytes(size)}). "
            f"Expected at least {_format_bytes(min_bytes)}."
        )


def _download(url: str, dest: Path, *, min_bytes: int = 1024) -> None:
    log.info("Downloading %s", url)
    headers = {"User-Agent": "publicus-takehome-pipeline/1.0"}
    with requests.get(
        url,
        timeout=HTTP_TIMEOUT,
        stream=True,
        verify=requests_verify(),
        headers=headers,
        allow_redirects=True,
    ) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        label = dest.name

        with dest.open("wb") as out:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                out.write(chunk)
                downloaded += len(chunk)
                sys.stderr.write("\r" + _progress_line(label, downloaded, total))
                sys.stderr.flush()

    sys.stderr.write("\r" + _progress_line(label, downloaded, total or downloaded) + "\n")
    sys.stderr.flush()
    _validate_download(dest, min_bytes=min_bytes)
    log.info("Saved %s (%s)", dest.name, _format_bytes(dest.stat().st_size))


def ingest_open_canada() -> Optional[Path]:
    dest = RAW_DIR / f"open_canada_grants_{timestamp()}.csv"
    try:
        _download(OPEN_CANADA_CSV, dest, min_bytes=MIN_OPEN_CANADA_BYTES)
        rows = _count_csv_rows(dest)
        log.info("Open Canada grants: %s rows", rows)
        log_pipeline_run("open_canada:ingest", rows, rows, 0, {"file": dest.name})
        return dest
    except Exception as e:  # noqa: BLE001
        log.error("Open Canada ingest failed: %s", e)
        log_pipeline_run("open_canada:ingest", 0, 0, 0, {"error": str(e)})
        return None


def _find_latest_bbf_resource() -> Optional[str]:
    """Parse the CKAN package and return the newest XLSX resource URL."""
    headers = {"User-Agent": "publicus-takehome-pipeline/1.0"}
    resp = requests.get(
        BBF_PACKAGE_API, timeout=HTTP_TIMEOUT, verify=requests_verify(), headers=headers
    )
    resp.raise_for_status()
    if not resp.text.lstrip().startswith("{"):
        raise RuntimeError(
            "BBF metadata request returned non-JSON (network proxy/captive portal?). "
            "Download the latest BBF .xlsx manually into data/raw/."
        )
    resources = resp.json()["result"]["resources"]
    excel = [
        r for r in resources
        if (r.get("format", "").upper() in {"XLSX", "XLS"})
        or str(r.get("url", "")).lower().endswith((".xlsx", ".xls"))
    ]
    if not excel:
        return None
    excel.sort(key=lambda r: r.get("last_modified") or r.get("created") or "", reverse=True)
    return excel[0]["url"]


def ingest_bbf() -> Optional[Path]:
    dest = RAW_DIR / f"bbf_programs_{timestamp()}.xlsx"
    try:
        url = _find_latest_bbf_resource()
        if not url:
            raise RuntimeError("No Excel resource found in BBF CKAN package")
        _download(url, dest, min_bytes=50_000)
        rows = _count_bbf_rows(dest)
        log.info("BBF programs: %s rows", rows)
        log_pipeline_run("bbf:ingest", rows, rows, 0, {"file": dest.name, "resource_url": url})
        return dest
    except Exception as e:  # noqa: BLE001
        log.error("BBF ingest failed: %s", e)
        log_pipeline_run("bbf:ingest", 0, 0, 0, {"error": str(e)})
        return None


def ingest_irap() -> list[Path]:
    saved: list[Path] = []
    for year in IRAP_FISCAL_YEARS:
        dest = RAW_DIR / f"nrc_irap_{year}.csv"
        try:
            _download(IRAP_URL_TEMPLATE.format(year=year), dest, min_bytes=10_000)
            rows = _count_csv_rows(dest)
            log.info("IRAP %s: %s rows", year, rows)
            log_pipeline_run(f"nrc_irap:{year}:ingest", rows, rows, 0, {"file": dest.name})
            saved.append(dest)
        except Exception as e:  # noqa: BLE001
            log.error("IRAP %s ingest failed: %s", year, e)
            log_pipeline_run(f"nrc_irap:{year}:ingest", 0, 0, 0, {"error": str(e)})
    return saved


def main() -> None:
    force = os.getenv("FORCE_INGEST", "0") == "1"
    skip = os.getenv("SKIP_INGEST", "0") == "1" or (not force and _has_cached_raw_data())

    log.info("=== INGEST (skip=%s) ===", skip)
    if skip:
        log.info(
            "Skipping ingest — raw files already in %s. Set FORCE_INGEST=1 to re-download.",
            RAW_DIR,
        )
        return

    ingest_open_canada()
    ingest_bbf()
    ingest_irap()
    log.info("Ingest complete. Raw files in %s", RAW_DIR)


if __name__ == "__main__":
    main()
