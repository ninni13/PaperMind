-- Idempotent: preserves any overview already stored on papers.
ALTER TABLE papers ADD COLUMN IF NOT EXISTS overview JSONB;
-- The legacy paper_overviews table is intentionally left intact, but is no
-- longer created, read, or written by the application.
