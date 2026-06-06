"""Stage 1 — Ingest.

Download raw source files and save them to data/raw/ with timestamps.
This stage does NOT transform anything; it only fetches bytes and records
raw row counts to pipeline_runs.

Sources:
  1. Open Canada Grants CSV (primary award history)
  2. Business Benefits Finder (BBF) program catalogue, via the CKAN API
  3. NRC-IRAP fiscal-year grants & contributions CSVs (2021-22 .. 2023-24)

Set USE_SAMPLE_DATA=1 to copy the bundled fixtures in data/sample/ into
data/raw/ instead of hitting the network — useful for an offline demo.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import requests

from utils import (
    RAW_DIR, SAMPLE_DIR, USE_SAMPLE_DATA,
    get_logger, log_pipeline_run, timestamp,
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


def _count_csv_rows(path: Path) -> int:
    """Row count excluding the header, tolerant of encoding quirks."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return max(sum(1 for _ in f) - 1, 0)


def _download(url: str, dest: Path) -> None:
    log.info("Downloading %s", url)
    resp = requests.get(url, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    log.info("Saved %s (%.1f KB)", dest.name, len(resp.content) / 1024)


# ---------------------------------------------------------------------------
# Open Canada grants
# ---------------------------------------------------------------------------
def ingest_open_canada() -> Optional[Path]:
    dest = RAW_DIR / f"open_canada_grants_{timestamp()}.csv"
    try:
        if USE_SAMPLE_DATA:
            shutil.copy(SAMPLE_DIR / "open_canada_grants.csv", dest)
            log.info("[sample] copied open_canada_grants.csv -> %s", dest.name)
        else:
            _download(OPEN_CANADA_CSV, dest)
        rows = _count_csv_rows(dest)
        log.info("Open Canada grants: %s rows", rows)
        log_pipeline_run("open_canada:ingest", rows, rows, 0, {"file": dest.name})
        return dest
    except Exception as e:  # noqa: BLE001
        log.error("Open Canada ingest failed: %s", e)
        log_pipeline_run("open_canada:ingest", 0, 0, 0, {"error": str(e)})
        return None


# ---------------------------------------------------------------------------
# Business Benefits Finder (CKAN -> latest Excel resource)
# ---------------------------------------------------------------------------
def _find_latest_bbf_resource() -> Optional[str]:
    """Parse the CKAN package and return the newest XLSX resource URL."""
    resp = requests.get(BBF_PACKAGE_API, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
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
        if USE_SAMPLE_DATA:
            # Fixture is a CSV; keep the .csv extension so clean.py reads it correctly.
            dest = RAW_DIR / f"bbf_programs_{timestamp()}.csv"
            shutil.copy(SAMPLE_DIR / "bbf_programs.csv", dest)
            rows = _count_csv_rows(dest)
            log.info("[sample] copied bbf_programs.csv -> %s (%s rows)", dest.name, rows)
            log_pipeline_run("bbf:ingest", rows, rows, 0, {"file": dest.name})
            return dest

        url = _find_latest_bbf_resource()
        if not url:
            raise RuntimeError("No Excel resource found in BBF CKAN package")
        _download(url, dest)
        log_pipeline_run("bbf:ingest", 0, 0, 0, {"file": dest.name, "resource_url": url})
        return dest
    except Exception as e:  # noqa: BLE001
        log.error("BBF ingest failed: %s", e)
        log_pipeline_run("bbf:ingest", 0, 0, 0, {"error": str(e)})
        return None


# ---------------------------------------------------------------------------
# NRC-IRAP fiscal year CSVs
# ---------------------------------------------------------------------------
def ingest_irap() -> list[Path]:
    saved: list[Path] = []
    for year in IRAP_FISCAL_YEARS:
        dest = RAW_DIR / f"nrc_irap_{year}.csv"
        try:
            if USE_SAMPLE_DATA:
                sample = SAMPLE_DIR / f"nrc_irap_{year}.csv"
                if not sample.exists():
                    log.info("[sample] no IRAP fixture for %s — skipping", year)
                    continue
                shutil.copy(sample, dest)
            else:
                _download(IRAP_URL_TEMPLATE.format(year=year), dest)
            rows = _count_csv_rows(dest)
            log.info("IRAP %s: %s rows", year, rows)
            log_pipeline_run(f"nrc_irap:{year}:ingest", rows, rows, 0, {"file": dest.name})
            saved.append(dest)
        except Exception as e:  # noqa: BLE001
            log.error("IRAP %s ingest failed: %s", year, e)
            log_pipeline_run(f"nrc_irap:{year}:ingest", 0, 0, 0, {"error": str(e)})
    return saved


def main() -> None:
    log.info("=== INGEST (sample_mode=%s) ===", USE_SAMPLE_DATA)
    ingest_open_canada()
    ingest_bbf()
    ingest_irap()
    log.info("Ingest complete. Raw files in %s", RAW_DIR)


if __name__ == "__main__":
    main()
