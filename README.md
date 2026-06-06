# Publicus — Canadian Grants Intelligence

A full-stack prototype that helps SMBs selling to the Canadian government
**discover grants they're eligible for** and **see what similar companies are
winning**. The heart of the project is a Python data pipeline that ingests raw,
messy federal grants data and turns it into a clean, queryable intelligence layer.

```
Open Canada CSV ─┐
BBF (CKAN) ──────┼─► ingest ─► clean ─► enrich ─► normalize_recipients ─► load ─► Postgres/Supabase
NRC-IRAP CSVs ───┘                                                                      │
                                                                                  FastAPI (8 endpoints)
                                                                                        │
                                                                                  Next.js 14 frontend
```

## Why this is interesting

The pipeline handles the realities of government open data: amendment chains,
amounts that are null/zero/negative/garbage, four different date formats,
free-text province names in English and French, department codes, cross-source
duplicates, and — the hardest part — **the same company spelled a dozen different
ways across hundreds of thousands of rows**. See
[`pipeline/normalize_recipients.py`](pipeline/normalize_recipients.py) for the
entity-resolution logic (blocking → fuzzy match → LLM confirmation → clustering).

## Quick start (offline demo — no DB or API keys needed)

The pipeline ships with realistic sample fixtures and can run fully offline,
writing a JSON snapshot that the API serves directly.

```bash
# 1. Python deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Run the whole pipeline against the bundled fixtures
USE_SAMPLE_DATA=1 python pipeline/run_all.py
#    -> writes data/processed/db_*.json

# 3. Start the API (auto-detects no DATABASE_URL -> serves the JSON snapshot)
cd api && uvicorn main:app --reload --port 8000
#    -> http://localhost:8000/docs

# 4. Start the frontend (new terminal)
cd frontend && cp .env.local.example .env.local && npm install && npm run dev
#    -> http://localhost:3000
```

## Full setup (Supabase + live data + LLM enrichment)

1. **Create a Supabase project** (free tier) and run
   [`supabase/schema.sql`](supabase/schema.sql) in the SQL editor.
2. **Configure env** — copy `.env.example` to `.env` and fill in:
   - `DATABASE_URL` — Supabase → Project Settings → Database → Connection string
     (the pooler/session string works with asyncpg)
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — for pipeline logging
   - `OPENAI_API_KEY` — enables real GPT-4o-mini enrichment (omit to use the
     deterministic heuristic fallbacks)
3. **Run the pipeline against live sources** (downloads from Open Canada, CKAN,
   and NRC-IRAP):
   ```bash
   python pipeline/run_all.py        # USE_SAMPLE_DATA unset / 0
   ```
4. **Run the API** — with `DATABASE_URL` set it queries Postgres via asyncpg.

## Data pipeline stages

| Stage | File | What it does |
|-------|------|--------------|
| Ingest | [`ingest.py`](pipeline/ingest.py) | Downloads raw Open Canada / BBF / IRAP files to `data/raw/` with timestamps. No transformation. |
| Clean | [`clean.py`](pipeline/clean.py) | Amendment dedup → amount cleaning → date normalization + fiscal year → province codes → department names → dedup fingerprint. **Never drops a row** — flags issues and nulls bad fields. |
| Enrich | [`enrich.py`](pipeline/enrich.py) | LLM sector classification (cached, retries, validated) + structured eligibility extraction from BBF descriptions (function calling + validation). |
| Normalize | [`normalize_recipients.py`](pipeline/normalize_recipients.py) | Entity resolution: preprocess → block → rapidfuzz → LLM confirm ambiguous pairs → union-find clustering → canonical records. |
| Load | [`load.py`](pipeline/load.py) | Wires FKs (recipient_id, program_id) and writes to Postgres; always emits an inspectable JSON snapshot. |

Every stage writes a row to `pipeline_runs` with raw/clean/skipped counts and a
per-issue-type breakdown, surfaced at `GET /api/pipeline/status`.

### Design principles enforced in code
- **Preserve raw data.** Normalized columns sit alongside originals
  (`recipient_name_raw` + canonical `recipient_id`, raw province + 2-letter code).
- **Never silently drop records.** Failed cleaning steps null the field and log a
  flag; counts show up on the pipeline status page.
- **LLM outputs are untrusted.** Sector results are validated against the 12
  allowed values (retry → `OTHER`); eligibility fields are validated against
  enums and nulled if invalid.

## API (FastAPI, 8 endpoints)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/programs/match` | Weighted match score (province .4 / sector .3 / size .2 / recent-history .1) × is_open, top 10 with reasons |
| `GET /api/awards/sector-summary` | Total/avg/count, top programs, by-fiscal-year, top recipients |
| `GET /api/awards/program/{id}` | Program metadata + paginated award history |
| `GET /api/recipients/search` | Postgres full-text search with award counts/totals |
| `GET /api/recipients/{id}/awards` | Full award history grouped by fiscal year |
| `GET /api/programs/trending` | Programs with >20% YoY award-volume growth |
| `GET /api/dashboard/{session_id}` | Aggregated dashboard payload, cached 1h in-memory |
| `GET /api/pipeline/status` | 5 most recent pipeline runs + issue breakdown |

The data layer ([`api/db.py`](api/db.py)) has two interchangeable backends behind
one interface: **`PgRepository`** (asyncpg + SQL, production) and
**`JsonRepository`** (in-memory over the snapshot, zero-infra demo). `get_repo()`
picks Postgres when `DATABASE_URL` is set.

## Frontend (Next.js 14, App Router + Tailwind)

| Route | Page |
|-------|------|
| `/` | Landing + onboarding form → creates a session profile |
| `/dashboard` | 3-panel: matches · sector intelligence hero · trending |
| `/program/[id]` | Program detail + structured eligibility + award history |
| `/recipients` | Debounced recipient search |
| `/recipients/[id]` | Full competitor grant history |

Key components: `MatchScore`, `SectorIntelCard` (hero with CSS bar chart + SVG
sparkline), `RecipientTable` (sortable, paginated).

## Deployment

- **Frontend → Vercel.** New project, root directory `frontend`, set
  `NEXT_PUBLIC_API_URL` to the deployed API URL.
- **API → Vercel** (root `vercel.json` + [`api/index.py`](api/index.py) ASGI
  entry) **or Render** ([`render.yaml`](render.yaml)) **or Docker**
  ([`api/Dockerfile`](api/Dockerfile)). Set `DATABASE_URL`, `OPENAI_API_KEY`,
  and `CORS_ORIGINS` (the frontend origin).
- **Database → Supabase.** Run `supabase/schema.sql`, then `python pipeline/load.py`.

## Project layout

```
pipeline/   ingest · clean · enrich · normalize_recipients · load · utils · llm · run_all
api/        main · db (Pg + Json repos) · routes/{programs,awards,recipients,pipeline,dashboard}
frontend/   app/{page,dashboard,program/[id],recipients,recipients/[id]} · components · lib
supabase/   schema.sql
data/sample/  offline fixtures that exercise every cleaning branch
```

## Notes & trade-offs

- **Offline-first by design.** Sample fixtures + JSON-snapshot backend let the
  whole stack run with no external dependencies, which doubles as a deterministic
  test bed for the pipeline. The same code paths hit live sources / Postgres /
  OpenAI when configured.
- **Heuristic fallbacks** for both LLM steps keep the pipeline runnable without an
  OpenAI key; with a key, the GPT-4o-mini paths take over and results are cached.
- The in-memory `JsonRepository` is for the prototype/demo; production traffic
  goes through `PgRepository` and SQL so it scales with the full Open Canada
  dataset.
```
