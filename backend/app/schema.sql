-- Idempotent schema. Applied on API/worker startup.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS trials (
    nct_id              TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    official_title      TEXT,
    summary             TEXT,
    status              TEXT,
    phase               TEXT,           -- e.g. "PHASE2", "PHASE1/PHASE2", "NA"
    study_type          TEXT,
    sponsor             TEXT,
    sponsor_class       TEXT,
    conditions          TEXT[] NOT NULL DEFAULT '{}',
    mesh_terms          TEXT[] NOT NULL DEFAULT '{}',
    mesh_ancestors      TEXT[] NOT NULL DEFAULT '{}',
    keywords            TEXT[] NOT NULL DEFAULT '{}',
    interventions       JSONB NOT NULL DEFAULT '[]',
    sex                 TEXT,           -- ALL | FEMALE | MALE
    min_age_years       REAL,
    max_age_years       REAL,
    healthy_volunteers  BOOLEAN,
    eligibility_text    TEXT,
    enrollment          INTEGER,
    start_date          DATE,
    last_update         DATE,
    central_contact     JSONB,
    source_query        TEXT,
    raw                 JSONB,
    criteria_hash       TEXT,
    search_tsv          TSVECTOR,
    embedding           vector(384),
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS trials_tsv_idx ON trials USING GIN (search_tsv);
CREATE INDEX IF NOT EXISTS trials_mesh_idx ON trials USING GIN (mesh_terms);
CREATE INDEX IF NOT EXISTS trials_status_idx ON trials (status);
CREATE INDEX IF NOT EXISTS trials_embedding_idx ON trials USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS sites (
    id          BIGSERIAL PRIMARY KEY,
    nct_id      TEXT NOT NULL REFERENCES trials(nct_id) ON DELETE CASCADE,
    facility    TEXT,
    city        TEXT,
    state       TEXT,
    zip         TEXT,
    country     TEXT,
    status      TEXT,
    lat         DOUBLE PRECISION,
    lon         DOUBLE PRECISION,
    contact     JSONB
);
CREATE INDEX IF NOT EXISTS sites_nct_idx ON sites (nct_id);
CREATE INDEX IF NOT EXISTS sites_geo_idx ON sites (lat, lon);

-- Structured eligibility produced by a parser. One row per (trial, parser).
CREATE TABLE IF NOT EXISTS parsed_eligibility (
    nct_id        TEXT NOT NULL REFERENCES trials(nct_id) ON DELETE CASCADE,
    parser        TEXT NOT NULL,          -- "rules" | "llm"
    model         TEXT,
    criteria_hash TEXT NOT NULL,
    parsed        JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (nct_id, parser)
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id            BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'running',
    trials_seen   INTEGER DEFAULT 0,
    trials_upserted INTEGER DEFAULT 0,
    detail        JSONB
);

-- Every LLM call, for quota accounting and auditability.
CREATE TABLE IF NOT EXISTS llm_calls (
    id          BIGSERIAL PRIMARY KEY,
    purpose     TEXT NOT NULL,
    model       TEXT,
    ok          BOOLEAN NOT NULL,
    latency_ms  INTEGER,
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS explanations (
    cache_key   TEXT PRIMARY KEY,
    nct_id      TEXT NOT NULL,
    body        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS geocode_cache (
    query       TEXT PRIMARY KEY,
    results     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Evaluation reports (parsing accuracy, ranking, fairness) shown on /insights.
CREATE TABLE IF NOT EXISTS eval_reports (
    kind        TEXT PRIMARY KEY,
    report      JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Gold-standard annotations for the parsing evaluation. Seeded with AI-drafted labels;
-- a person reviews each line in /annotate and marks it verified.
CREATE TABLE IF NOT EXISTS gold_annotations (
    id          INTEGER PRIMARY KEY,
    nct_id      TEXT,
    kind        TEXT NOT NULL,
    text        TEXT NOT NULL,
    labels      JSONB NOT NULL DEFAULT '[]',
    draft       JSONB NOT NULL DEFAULT '[]',     -- labels as originally drafted, for audit
    status      TEXT NOT NULL DEFAULT 'draft',   -- draft | verified | skipped
    source      TEXT NOT NULL DEFAULT 'stratified',  -- stratified | random
    annotator   TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
