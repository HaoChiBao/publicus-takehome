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

load_dotenv()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await get_repo()      # warm the connection pool / load the snapshot
    yield
    await close_repo()


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
    backend = "postgres" if os.getenv("DATABASE_URL") else "json-snapshot"
    try:
        repo = await get_repo()
        if backend == "json-snapshot":
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
                payload["hint"] = "Run `python pipeline/run_all.py` to download and process grants data."
            return payload
        return {"status": "ok", "backend": backend}
    except Exception as e:
        return {
            "status": "no_data",
            "backend": backend,
            "error": str(e),
            "hint": "Run `python pipeline/run_all.py` to download and process grants data.",
        }
