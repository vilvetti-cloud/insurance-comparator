CREATE TABLE IF NOT EXISTS companies (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    slug TEXT UNIQUE,
    short_name TEXT,
    official_url TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    slug TEXT,
    product_type TEXT NOT NULL DEFAULT 'insurance',
    product_subtype TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(company_id, name)
);

CREATE TABLE IF NOT EXISTS comparison_fields (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    field_key TEXT NOT NULL,
    label TEXT,
    data_type TEXT NOT NULL DEFAULT 'text',
    value_schema JSONB,
    category TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(product_id, field_key)
);

CREATE TABLE IF NOT EXISTS sources (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title TEXT,
    source_type TEXT NOT NULL DEFAULT 'official_site',
    source_level SMALLINT NOT NULL DEFAULT 2 CHECK (source_level BETWEEN 1 AND 4),
    status TEXT NOT NULL DEFAULT 'active',
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_checked_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    http_status INTEGER,
    checksum TEXT,
    UNIQUE(company_id, url)
);

CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    title TEXT,
    document_url TEXT NOT NULL,
    document_date TEXT,
    document_version TEXT,
    checksum TEXT,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_checked_at TIMESTAMPTZ,
    UNIQUE(source_id, document_url)
);

CREATE TABLE IF NOT EXISTS conditions (
    id BIGSERIAL PRIMARY KEY,
    field_id BIGINT NOT NULL REFERENCES comparison_fields(id) ON DELETE CASCADE,
    source_id BIGINT REFERENCES sources(id) ON DELETE SET NULL,
    value TEXT,
    value_json JSONB,
    is_direct BOOLEAN,
    source_level SMALLINT CHECK (source_level BETWEEN 1 AND 4),
    confidence NUMERIC(5,4),
    status TEXT NOT NULL DEFAULT 'active',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    checked_at TIMESTAMPTZ,
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS evidence (
    id BIGSERIAL PRIMARY KEY,
    condition_id BIGINT REFERENCES conditions(id) ON DELETE CASCADE,
    source_id BIGINT REFERENCES sources(id) ON DELETE SET NULL,
    document_id BIGINT REFERENCES documents(id) ON DELETE SET NULL,
    page_number INTEGER,
    text_fragment TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    verified_by TEXT
);

CREATE TABLE IF NOT EXISTS condition_versions (
    id BIGSERIAL PRIMARY KEY,
    condition_id BIGINT NOT NULL REFERENCES conditions(id) ON DELETE CASCADE,
    value TEXT,
    value_json JSONB,
    is_direct BOOLEAN,
    source_id BIGINT REFERENCES sources(id) ON DELETE SET NULL,
    document_id BIGINT REFERENCES documents(id) ON DELETE SET NULL,
    page_number INTEGER,
    text_fragment TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS change_log (
    id BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id BIGINT,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    triggered_by TEXT,
    companies_total INTEGER NOT NULL DEFAULT 0,
    companies_success INTEGER NOT NULL DEFAULT 0,
    companies_failed INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS collection_items (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES collection_runs(id) ON DELETE CASCADE,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    source_count INTEGER NOT NULL DEFAULT 0,
    document_count INTEGER NOT NULL DEFAULT 0,
    fields_found INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS app_state (
    state_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE companies ADD COLUMN IF NOT EXISTS slug TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS short_name TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS official_url TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE companies ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE products ADD COLUMN IF NOT EXISTS slug TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS product_subtype TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE products ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE comparison_fields ADD COLUMN IF NOT EXISTS data_type TEXT NOT NULL DEFAULT 'text';
ALTER TABLE comparison_fields ADD COLUMN IF NOT EXISTS value_schema JSONB;
ALTER TABLE comparison_fields ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE comparison_fields ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;
ALTER TABLE comparison_fields ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE comparison_fields ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE sources ADD COLUMN IF NOT EXISTS source_level SMALLINT NOT NULL DEFAULT 2;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS http_status INTEGER;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS checksum TEXT;

ALTER TABLE conditions ADD COLUMN IF NOT EXISTS source_id BIGINT REFERENCES sources(id) ON DELETE SET NULL;
ALTER TABLE conditions ADD COLUMN IF NOT EXISTS value_json JSONB;
ALTER TABLE conditions ADD COLUMN IF NOT EXISTS is_direct BOOLEAN;
ALTER TABLE conditions ADD COLUMN IF NOT EXISTS source_level SMALLINT;
ALTER TABLE conditions ADD COLUMN IF NOT EXISTS confidence NUMERIC(5,4);
ALTER TABLE conditions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE conditions ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'unverified';
ALTER TABLE conditions ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ;
ALTER TABLE conditions ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ;

ALTER TABLE evidence ADD COLUMN IF NOT EXISTS document_id BIGINT REFERENCES documents(id) ON DELETE SET NULL;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS verified_by TEXT;

ALTER TABLE condition_versions ADD COLUMN IF NOT EXISTS value_json JSONB;
ALTER TABLE condition_versions ADD COLUMN IF NOT EXISTS is_direct BOOLEAN;

CREATE INDEX IF NOT EXISTS idx_products_company ON products(company_id);
CREATE INDEX IF NOT EXISTS idx_products_type_subtype ON products(product_type, product_subtype);
CREATE INDEX IF NOT EXISTS idx_fields_product ON comparison_fields(product_id);
CREATE INDEX IF NOT EXISTS idx_conditions_field ON conditions(field_id);
CREATE INDEX IF NOT EXISTS idx_conditions_source_level ON conditions(field_id, source_level);
CREATE INDEX IF NOT EXISTS idx_sources_company ON sources(company_id);
CREATE INDEX IF NOT EXISTS idx_sources_level ON sources(company_id, source_level);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_condition ON evidence(condition_id);
CREATE INDEX IF NOT EXISTS idx_condition_versions_condition ON condition_versions(condition_id);
CREATE INDEX IF NOT EXISTS idx_change_log_entity ON change_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_collection_items_run ON collection_items(run_id);
CREATE INDEX IF NOT EXISTS idx_collection_items_company ON collection_items(company_id);


-- Additive, repeatable CASCO document pipeline migration.
ALTER TABLE sources ADD COLUMN IF NOT EXISTS casco_analyzed_checksum TEXT;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS section TEXT;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS document_checksum TEXT;

CREATE TABLE IF NOT EXISTS casco_document_revisions (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    parsed JSONB,
    provider TEXT,
    error TEXT,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    analyzed_at TIMESTAMPTZ,
    UNIQUE(source_id, checksum)
);
CREATE TABLE IF NOT EXISTS casco_review_candidates (
    id BIGSERIAL PRIMARY KEY,
    revision_id BIGINT NOT NULL REFERENCES casco_document_revisions(id) ON DELETE CASCADE,
    field_id BIGINT NOT NULL REFERENCES comparison_fields(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    validation_status TEXT NOT NULL CHECK (validation_status IN ('PASS', 'FAIL')),
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_casco_review_field ON casco_review_candidates(field_id, created_at DESC);
