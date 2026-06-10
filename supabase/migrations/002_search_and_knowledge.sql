-- =============================================================================
-- Publicus migration 002: Search, knowledge layer, and AI indexing
-- Run this in the Supabase SQL Editor AFTER schema.sql (or on an existing project).
-- Safe to re-run: uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS throughout.
-- =============================================================================

-- Vector similarity (Supabase supports pgvector on all plans)
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Extend grant_programs with richer catalogue + search fields
-- ---------------------------------------------------------------------------
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS short_description     TEXT;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS long_description      TEXT;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS status                TEXT;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS intake_start          DATE;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS intake_end            DATE;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS target_audience       TEXT;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS funding_instrument    TEXT;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS stacking_notes        TEXT;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS keywords              TEXT[];
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS summary_1liner        TEXT;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS eligibility_narrative TEXT;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS application_steps     TEXT[];
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS source_url            TEXT;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS last_verified_at      TIMESTAMPTZ;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS search_vector         tsvector;
ALTER TABLE grant_programs ADD COLUMN IF NOT EXISTS content_hash          TEXT;

CREATE INDEX IF NOT EXISTS idx_programs_fts ON grant_programs USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_programs_provinces ON grant_programs USING GIN (eligible_provinces);
CREATE INDEX IF NOT EXISTS idx_programs_sectors ON grant_programs USING GIN (eligible_sectors);
CREATE INDEX IF NOT EXISTS idx_programs_activities ON grant_programs USING GIN (eligible_activities);
CREATE INDEX IF NOT EXISTS idx_programs_open_deadline ON grant_programs (is_open, deadline);
CREATE INDEX IF NOT EXISTS idx_programs_amounts ON grant_programs (min_amount, max_amount);
CREATE INDEX IF NOT EXISTS idx_programs_keywords ON grant_programs USING GIN (keywords);

-- Full-text on award descriptions (competitor / project-type search)
ALTER TABLE grant_awards ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS idx_awards_fts ON grant_awards USING GIN (search_vector)
  WHERE is_latest_amendment = true;

-- ---------------------------------------------------------------------------
-- Raw BBF payloads (preserve every column from government export)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grant_program_sources (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  grant_program_id  UUID REFERENCES grant_programs(id) ON DELETE CASCADE,
  source            TEXT NOT NULL DEFAULT 'bbf',
  external_id       TEXT,
  raw_payload       JSONB NOT NULL,
  content_hash      TEXT,
  ingested_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_program_sources_program ON grant_program_sources(grant_program_id);
CREATE INDEX IF NOT EXISTS idx_program_sources_hash ON grant_program_sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_program_sources_payload ON grant_program_sources USING GIN (raw_payload);

-- ---------------------------------------------------------------------------
-- LLM-enriched metadata (narrative fields separate from core catalogue)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grant_program_metadata (
  grant_program_id       UUID PRIMARY KEY REFERENCES grant_programs(id) ON DELETE CASCADE,
  summary_1liner         TEXT,
  eligibility_narrative  TEXT,
  target_audience        TEXT,
  application_steps      TEXT[],
  typical_projects       TEXT[],
  stacking_notes         TEXT,
  keywords               TEXT[],
  enrichment_model       TEXT,
  enriched_at            TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Precomputed award analytics per program (powers insights + AI citations)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grant_program_stats (
  grant_program_id    UUID PRIMARY KEY REFERENCES grant_programs(id) ON DELETE CASCADE,
  total_disbursed     NUMERIC(15,2) DEFAULT 0,
  award_count         INT DEFAULT 0,
  recipient_count     INT DEFAULT 0,
  avg_award           NUMERIC(15,2),
  median_award        NUMERIC(15,2),
  p90_award           NUMERIC(15,2),
  largest_award       NUMERIC(15,2),
  provinces_active    TEXT[],
  sectors_active      TEXT[],
  naics_top_prefixes  TEXT[],
  yoy_growth_pct      NUMERIC(8,2),
  last_award_date     DATE,
  award_by_fiscal_year JSONB,
  top_recipient_names TEXT[],
  computed_at         TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_program_stats_disbursed ON grant_program_stats(total_disbursed DESC);
CREATE INDEX IF NOT EXISTS idx_program_stats_count ON grant_program_stats(award_count DESC);

-- ---------------------------------------------------------------------------
-- Chunked content for RAG (long descriptions, eligibility text)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grant_content_chunks (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  grant_program_id  UUID REFERENCES grant_programs(id) ON DELETE CASCADE,
  chunk_index       INT NOT NULL,
  chunk_type        TEXT NOT NULL DEFAULT 'description',
  content           TEXT NOT NULL,
  token_estimate    INT,
  created_at        TIMESTAMPTZ DEFAULT now(),
  UNIQUE (grant_program_id, chunk_type, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_chunks_program ON grant_content_chunks(grant_program_id);

-- ---------------------------------------------------------------------------
-- Vector embeddings (semantic / AI search)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grant_embeddings (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type  TEXT NOT NULL CHECK (entity_type IN ('program', 'program_chunk', 'award_sample')),
  entity_id    UUID NOT NULL,
  model        TEXT NOT NULL DEFAULT 'text-embedding-3-small',
  embedding    vector(1536) NOT NULL,
  content_text TEXT,
  metadata     JSONB DEFAULT '{}',
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_embeddings_entity ON grant_embeddings(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw ON grant_embeddings
  USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- Cached AI insight cards (audience-specific or general)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grant_insights (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  grant_program_id UUID REFERENCES grant_programs(id) ON DELETE CASCADE,
  insight_type     TEXT NOT NULL,
  audience         JSONB DEFAULT '{}',
  content          TEXT NOT NULL,
  evidence         JSONB DEFAULT '{}',
  model            TEXT,
  generated_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_insights_program ON grant_insights(grant_program_id);
CREATE INDEX IF NOT EXISTS idx_insights_type ON grant_insights(insight_type);

-- ---------------------------------------------------------------------------
-- Optional: log natural-language queries for tuning
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS search_queries (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  TEXT,
  query_text  TEXT NOT NULL,
  parsed_filters JSONB,
  result_count INT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Helper: rebuild program search_vector from text fields
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION refresh_program_search_vector(p_id UUID)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE grant_programs gp
  SET search_vector =
    setweight(to_tsvector('english', coalesce(gp.name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(gp.department, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(gp.summary_1liner, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(gp.short_description, '')), 'C') ||
    setweight(to_tsvector('english', coalesce(gp.description, '')), 'C') ||
    setweight(to_tsvector('english', coalesce(gp.eligibility_narrative, '')), 'C') ||
    setweight(to_tsvector('english', coalesce(array_to_string(gp.keywords, ' '), '')), 'B')
  WHERE gp.id = p_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- Hybrid search RPC (FTS + optional vector — call from API)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION search_grant_programs(
  search_query    TEXT DEFAULT NULL,
  query_embedding vector(1536) DEFAULT NULL,
  filter_sector   TEXT DEFAULT NULL,
  filter_province TEXT DEFAULT NULL,
  filter_open     BOOLEAN DEFAULT NULL,
  result_limit    INT DEFAULT 20,
  result_offset   INT DEFAULT 0
)
RETURNS TABLE (
  program_id   UUID,
  name         TEXT,
  department   TEXT,
  fts_rank     REAL,
  vector_dist  REAL,
  hybrid_score REAL
)
LANGUAGE sql STABLE
AS $$
  WITH base AS (
    SELECT
      gp.id,
      gp.name,
      gp.department,
      CASE WHEN search_query IS NOT NULL AND search_query <> ''
        THEN ts_rank_cd(gp.search_vector, websearch_to_tsquery('english', search_query))
        ELSE 0
      END AS fts_rank,
      CASE WHEN query_embedding IS NOT NULL
        THEN (SELECT MIN(e.embedding <=> query_embedding)
              FROM grant_embeddings e
              WHERE e.entity_type = 'program' AND e.entity_id = gp.id)
        ELSE NULL
      END AS vector_dist
    FROM grant_programs gp
    WHERE (filter_sector IS NULL OR filter_sector = ANY(gp.eligible_sectors))
      AND (filter_province IS NULL
           OR filter_province = ANY(gp.eligible_provinces)
           OR 'ALL' = ANY(gp.eligible_provinces))
      AND (filter_open IS NULL OR gp.is_open = filter_open)
      AND (
        search_query IS NULL OR search_query = ''
        OR gp.search_vector @@ websearch_to_tsquery('english', search_query)
        OR query_embedding IS NOT NULL
      )
  )
  SELECT
    b.id AS program_id,
    b.name,
    b.department,
    b.fts_rank::REAL,
    b.vector_dist::REAL,
    (
      COALESCE(b.fts_rank, 0) * 0.45
      + CASE WHEN b.vector_dist IS NOT NULL THEN (1.0 / (1.0 + b.vector_dist)) * 0.55 ELSE 0 END
    )::REAL AS hybrid_score
  FROM base b
  ORDER BY hybrid_score DESC, b.fts_rank DESC NULLS LAST
  LIMIT result_limit OFFSET result_offset;
$$;
