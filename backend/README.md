# Research Paper API

From `backend/`, start with `venv/bin/uvicorn app.main:app --reload`.
Required `.env` settings: `DATABASE_URL` and `OPENAI_API_KEY`.
Optional `OVERVIEW_MODEL` defaults to `gpt-5-mini`.

## Overview backend

```
POST /papers/{id}/overview
  -> read papers.overview
  -> cached? return immediately (no embeddings, retrieval, or generation)
  -> get_overview_context(paper_id)
  -> one structured extraction request
  -> validate all five fields
  -> UPDATE papers SET overview = ...
  -> commit and return
```

- `GET /papers/{id}/overview` only reads PostgreSQL. It returns `not_generated`
  when `papers.overview` is SQL NULL, or `ready` with the validated cached JSON.
- `POST /papers/{id}/overview` generates on a cache miss, or returns the existing cache.
- Both retain the existing response envelope: `paper_id`, `status`, and `overview`.
  Optional legacy metadata fields are null, because this version stores only the five-field
  overview JSON on `papers`, not generation timestamps or model metadata.
- Errors: 404 missing paper, 409 another generation is running, 422 no readable context,
  502 model failure/refusal/incomplete/invalid output. Failures do not write an overview.
- There is no regeneration endpoint or automatic generation on GET.
- This change is backend-only. The existing frontend has not been changed in this step.

### Module responsibilities

- `overview_retrieval.py`: select context with opening chunks and semantic retrieval.
- `overview_service.py`: `generate_overview(chunks, model)` formats that context,
  calls structured extraction, and returns a validated `PaperOverview`.
- `overview.py`: shared `PaperOverview` and `OverviewResponse` schemas.
- `overview_repository.py`: cache lookup, generation coordination, and JSONB persistence.

The service accepts chunks rather than a paper ID; it does not retrieve or save data.

### Selected evidence

`get_overview_context()` combines the first 3 chunks with four semantic queries:
method, datasets/experimental setup, results/performance, and limitations/future work.
Each query retrieves 3 chunks using the existing `search_chunks` SQL and the same paper ID.
Query vectors use the existing batched embedding helper. Chunks are deduplicated by
`chunk_index` and sorted into document order: at most 15 under the default configuration.
No section recognition, full-document extraction, or agent is involved.

The generator receives only these chunks with page/chunk labels. It makes one
`responses.parse` request using a Pydantic schema with exactly:

```json
{
  "research_question": null,
  "method": null,
  "datasets": [],
  "key_results": [],
  "limitations": []
}
```

The prompt forbids outside knowledge and guessing. Missing evidence must produce null
or an empty list; it does not establish that the full paper lacks that information.
Results should retain metrics and evaluation qualifiers. Limitations/future work must
be explicitly supported. Schema validation checks structure, not factual accuracy.
Page references are model-produced prose, not verified clickable citations.

Input over 15 chunks or 24,000 characters is rejected rather than silently truncated.
The existing index uses 1,000-character chunks, so normal default retrieval fits this budget.
Generation has a 120-second request timeout and no automatic model retry. A failed or
incomplete response never becomes a cached partial overview.

Structured output reference: https://developers.openai.com/api/docs/guides/structured-outputs

### Storage and concurrency

Backend startup runs `migrations/002_papers_overview.sql` idempotently:

```sql
ALTER TABLE papers ADD COLUMN IF NOT EXISTS overview JSONB;
```

Existing non-null `papers.overview` values are preserved. Cached values must match the
five-field schema. The legacy `paper_overviews` table is not dropped or imported; the
application no longer creates, reads, or writes it. The historical 001 SQL file remains
for reference and is not executed on startup.

Generation runs in a FastAPI worker thread inside a database transaction. A transaction
advisory lock excludes duplicate generation across workers; a paper row lock coordinates
cache writes and deletion. Retrieval uses the existing repository connections. On failure,
the transaction rolls back and releases locks. On success, the update commits before the
response returns. GET remains read-only while generation is in progress and can return
`not_generated` until commit. This is synchronous work, not a durable background job.

## Verification

```sh
venv/bin/python -m unittest discover -s tests -v
```

Unit/API tests mock the database and OpenAI. They verify selected context only, one
structured request, schema validation, null/empty output, cache hits skipping retrieval
and generation, and failure paths avoiding cache writes.

For real PostgreSQL behavior with temporary tables and rolled-back writes:

```sh
venv/bin/python -m tests.check_overview_postgres
```

The integration check mocks retrieval and generation, and verifies idempotent migration,
JSONB round trips, retry after rollback, zero-retrieval cache hits, and advisory locking.
It does not change existing papers or spend OpenAI tokens.
