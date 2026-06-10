"""FastAPI entrypoint for the Publicus grants intelligence API.

Run locally:
    uvicorn api.main:app --reload --port 8000   (from repo root)
or:
    cd api && uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import close_repo, get_repo
from routes import awards, dashboard, pipeline, programs, recipients, watchlist

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv()
load_dotenv(_ROOT / ".env.local", override=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    repo = await get_repo()
    backend = getattr(repo, "backend", "unknown")
    if backend == "postgres" and hasattr(repo, "stats"):
        counts = await repo.stats()
        log.info(
            "API ready — Supabase/Postgres (%s programs, %s recipients, %s awards)",
            counts["programs"], counts["recipients"], counts["awards"],
        )
    else:
        log.info("API ready — backend=%s", backend)
    yield
    await close_repo()


log = __import__("logging").getLogger("api.main")


app = FastAPI(
    title="Publicus Grants Intelligence API",
    version="1.0.0",
    description="Discover eligible Canadian government grants and competitor award intelligence.",
    lifespan=lifespan,
)

# CORS — allow the Next.js frontend (configurable for the deployed origin).
origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(programs.router)
app.include_router(awards.router)
app.include_router(recipients.router)
app.include_router(pipeline.router)
app.include_router(dashboard.router)
app.include_router(watchlist.router)


@app.get("/")
async def root():
    return {"service": "publicus-grants-api", "status": "ok", "docs": "/docs"}


@app.get("/api/health")
async def health():
    try:
        repo = await get_repo()
        backend = getattr(repo, "backend", "unknown")
        if backend == "postgres" and hasattr(repo, "stats"):
            counts = await repo.stats()
            return {
                "status": "ok",
                "backend": backend,
                **counts,
            }
        programs = len(getattr(repo, "programs", []))
        awards = len(getattr(repo, "awards", []))
        recipients = len(getattr(repo, "recipients", []))
        payload = {
            "status": "ok" if getattr(repo, "data_ready", True) else "no_data",
            "backend": backend,
            "programs": programs,
            "awards": awards,
            "recipients": recipients,
        }
        if getattr(repo, "data_error", None):
            payload["error"] = repo.data_error
            payload["hint"] = "Run `python pipeline/run_all.py` or set DATABASE_URL for Supabase."
        return payload
    except Exception as e:
        return {
            "status": "error",
            "backend": "postgres" if os.getenv("DATABASE_URL") else "json-snapshot",
            "error": str(e),
            "hint": "Set DATABASE_URL in .env.local to your Supabase Session pooler URI.",
        }
