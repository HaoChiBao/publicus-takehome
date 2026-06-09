"""Run the full pipeline end-to-end: ingest -> clean -> enrich -> normalize -> load.

Usage:
    python pipeline/run_all.py
    FORCE_INGEST=1 python pipeline/run_all.py   # re-download raw sources
    SKIP_INGEST=1 python pipeline/run_all.py    # reuse cached data/raw files
"""
from __future__ import annotations

import asyncio

import clean
import enrich
import ingest
import load
import normalize_recipients
from utils import get_logger

log = get_logger("pipeline.run_all")


async def main() -> None:
    log.info("########## PIPELINE START ##########")
    ingest.main()
    clean.clean()
    await enrich.run()
    await normalize_recipients.resolve()
    await load.run()
    log.info("########## PIPELINE COMPLETE ##########")


if __name__ == "__main__":
    asyncio.run(main())
