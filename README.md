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

## Quick start

The app downloads live federal grants data, cleans it, and serves it from
`data/processed/db_*.json` (or Postgres when `DATABASE_URL` is set).

```bash
# 1. Python deps
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# 2. Download + clean + load live data (first run downloads ~500MB Open Canada CSV)
python pipeline/run_all.py
#    -> writes data/processed/db_*.json

# Windows shortcut:
# .\scripts\run_pipeline.ps1

# 3. Start the API (uses Supabase when DATABASE_URL is set in .env.local)
.\scripts\run_api.ps1
#    -> http://localhost:8000/api/health  (backend should be "postgres")
#
# Or manually: cd api && python -m uvicorn main:app --reload --port 8000
# If port 8000 is busy, run_api.ps1 stops the stale process automatically.

# 4. Start the frontend (new terminal)
cd frontend && cp .env.local.example .env.local && npm install && npm run dev
#    -> http://localhost:3000
```

Re-download raw sources: `FORCE_INGEST=1 python pipeline/run_all.py`  
Reuse cached `data/raw/`: `SKIP_INGEST=1 python pipeline/run_all.py`

### Manual download (if your network blocks automated downloads)

Save these into `data/raw/` with any timestamped filename matching the patterns
below, then run `SKIP_INGEST=1 python pipeline/run_all.py`:

| Pattern | Source |
|---------|--------|
| `open_canada_grants_*.csv` | [Open Canada grants.csv](https://open.canada.ca/data/dataset/432527ab-7aac-45b5-81d6-7597107a7013/resource/1d15a62f-5656-49ad-8c88-f40ce689d831/download/grants.csv) (~500MB) |
| `bbf_programs_*.xlsx` | [Business Benefits Finder dataset](https://open.canada.ca/data/en/dataset/business-benefits-finder) — latest XLSX |
| `nrc_irap_202*_*.csv` | NRC IRAP fiscal-year CSVs from `ftp.maps.canada.ca` |

## Production setup (Supabase + LLM enrichment)

1. **Create a Supabase project** (free tier) and run
   [`supabase/schema.sql`](supabase/schema.sql) in the SQL editor.
2. **Configure env** — copy `.env.example` to `.env` and fill in:
   - `DATABASE_URL` — Supabase → Project Settings → Database → Connection string
     (the pooler/session string works with asyncpg)
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — for pipeline logging
   - `OPENAI_API_KEY` — enables real GPT-4o-mini enrichment (omit to use the
     deterministic heuristic fallbacks)
3. **Run the pipeline** — downloads from Open Canada, CKAN, and NRC-IRAP:
   ```bash
   python pipeline/run_all.py
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
| `/grants` | Browse all programs with filters + pagination |

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
data/raw/   downloaded source files (gitignored)
data/processed/  cleaned snapshots consumed by the API (gitignored)
scripts/    run_pipeline.ps1
```

## Notes & trade-offs

- **Live data only.** The pipeline downloads Open Canada grants, the Business
  Benefits Finder program catalogue (~1,500 programs), and NRC-IRAP CSVs.
- **Heuristic fallbacks** for both LLM steps keep the pipeline runnable without an
  OpenAI key; with a key, the GPT-4o-mini paths take over and results are cached.
- The in-memory `JsonRepository` serves the local JSON snapshot for development;
  production traffic goes through `PgRepository` and SQL.
