-- Publicus Grants Intelligence — full database schema.
-- Run as a migration in the Supabase SQL editor (or psql against DATABASE_URL).

-- Required for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Recipients: canonical company records after normalization
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recipients (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name_normalized   TEXT NOT NULL UNIQUE,
  names_raw         TEXT[],
  business_number   TEXT,
  province          CHAR(2),
  city              TEXT,
  created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recipients_name ON recipients USING gin(to_tsvector('english', name_normalized));
CREATE INDEX IF NOT EXISTS idx_recipients_province ON recipients(province);

-- ---------------------------------------------------------------------------
-- Grant programs: active programs from Business Benefits Finder
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grant_programs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source              TEXT DEFAULT 'bbf',
  name                TEXT NOT NULL,
  department          TEXT,
  program_type        TEXT,           -- 'Grant' | 'Loan' | 'Tax Credit' | 'Advisory'
  description         TEXT,
  min_amount          NUMERIC(15,2),
  max_amount          NUMERIC(15,2),
  eligible_provinces  TEXT[],         -- ['ON','QC'] or ['ALL']
  eligible_sectors    TEXT[],
  eligible_sizes      TEXT[],         -- ['1-10','11-50','51-200','200+']
  eligible_activities TEXT[],         -- ['R&D','Export','Hiring','Digital Transformation']
  deadline            DATE,
  is_open             BOOLEAN DEFAULT true,
  apply_url           TEXT,
  last_updated        DATE,
  created_at          TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Grant awards: historical disbursements from Open Canada + IRAP
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grant_awards (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source                  TEXT NOT NULL,          -- 'open_canada' | 'nrc_irap'
  ref_number              TEXT,
  amendment_number        INT DEFAULT 0,
  is_latest_amendment     BOOLEAN DEFAULT true,
  recipient_id            UUID REFERENCES recipients(id),
  recipient_name_raw      TEXT,
  department              TEXT,
  program_name_raw        TEXT,
  program_name_normalized TEXT,
  program_id              UUID REFERENCES grant_programs(id),
  agreement_type          TEXT,                   -- 'Grant' | 'Contribution' | 'Other'
  amount                  NUMERIC(15,2),
  province                CHAR(2),
  city                    TEXT,
  naics_code              TEXT,
  sector_normalized       TEXT,
  fiscal_year             TEXT,                   -- e.g. '2023-24'
  start_date              DATE,
  end_date                DATE,
  description             TEXT,
  created_at              TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_awards_recipient ON grant_awards(recipient_id);
CREATE INDEX IF NOT EXISTS idx_awards_sector ON grant_awards(sector_normalized);
CREATE INDEX IF NOT EXISTS idx_awards_province ON grant_awards(province);
CREATE INDEX IF NOT EXISTS idx_awards_fiscal_year ON grant_awards(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_awards_program ON grant_awards(program_name_normalized);
CREATE INDEX IF NOT EXISTS idx_awards_latest ON grant_awards(is_latest_amendment);

-- ---------------------------------------------------------------------------
-- Company profiles: session-based, no auth needed
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS company_profiles (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  TEXT UNIQUE NOT NULL,
  name        TEXT,
  sector      TEXT,
  province    CHAR(2),
  size_band   TEXT,           -- '1-10' | '11-50' | '51-200' | '200+'
  activities  TEXT[],
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Pipeline run logs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source           TEXT,
  run_at           TIMESTAMPTZ DEFAULT now(),
  records_raw      INT,
  records_clean    INT,
  records_skipped  INT,
  issues           JSONB
);
