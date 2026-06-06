"""Run the full pipeline end-to-end: ingest -> clean -> enrich -> normalize -> load.

Usage:
    python pipeline/run_all.py
    USE_SAMPLE_DATA=1 python pipeline/run_all.py   # offline demo with fixtures
"""
from __future__ import annotations

import asyncio

import clean
import enrich
import ingest
import load
import normalize_recipients
from utils import USE_SAMPLE_DATA, get_logger

log = get_logger("pipeline.run_all")


async def main() -> None:
    log.info("########## PIPELINE START (sample_mode=%s) ##########", USE_SAMPLE_DATA)
    ingest.main()
    clean.clean()
    await enrich.run()
    await normalize_recipients.resolve()
    await load.run()
    log.info("########## PIPELINE COMPLETE ##########")


if __name__ == "__main__":
    asyncio.run(main())
