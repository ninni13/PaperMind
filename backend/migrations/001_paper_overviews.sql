CREATE TABLE IF NOT EXISTS paper_overviews (
    paper_id BIGINT PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
    overview JSONB NOT NULL CHECK (jsonb_typeof(overview) = 'object'),
    model TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    context_chunks INTEGER NOT NULL CHECK (context_chunks > 0),
    context_pages INTEGER NOT NULL CHECK (context_pages > 0),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Match papers.id, including early development installs.
ALTER TABLE paper_overviews ALTER COLUMN paper_id TYPE BIGINT;
