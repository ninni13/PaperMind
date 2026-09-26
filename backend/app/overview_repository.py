"""Persistent overview cache and cross-process generation exclusion."""
from pathlib import Path

from psycopg.types.json import Jsonb

from app.database import get_connection
from app.overview import PaperOverview, OverviewResponse
from app.overview_service import generate_overview, overview_model
from app.overview_retrieval import get_overview_context


class PaperNotFound(Exception):
    pass


class OverviewBusy(Exception):
    pass


class PaperHasNoText(Exception):
    pass


def initialize_overview_storage():
    migration = Path(__file__).resolve().parent.parent / "migrations" / "002_papers_overview.sql"
    with get_connection() as conn:
        # Serialize schema initialization across multiple server workers.
        conn.execute("SELECT pg_advisory_xact_lock(17012026, 0)")
        conn.execute(migration.read_text())


def _read(cur, paper_id: int, *, lock: bool = False) -> OverviewResponse:
    cur.execute(
        "SELECT overview FROM papers WHERE id = %s" + (" FOR UPDATE" if lock else ""),
        (paper_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise PaperNotFound()
    if row[0] is None:
        return OverviewResponse(paper_id=paper_id, status="not_generated")
    return OverviewResponse(paper_id=paper_id, status="ready", overview=row[0])


def get_overview(paper_id: int) -> OverviewResponse:
    with get_connection() as conn:
        with conn.cursor() as cur:
            return _read(cur, paper_id)


def create_overview(paper_id: int) -> OverviewResponse:
    # Transaction-owned locking releases automatically on error or process exit.
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"papermind:overview:{paper_id}",),
            )
            if not cur.fetchone()[0]:
                raise OverviewBusy()
            # Lock the paper against concurrent deletion or cache replacement.
            cached = _read(cur, paper_id, lock=True)
            if cached.status == "ready":
                return cached

            # Only a cache miss can trigger embeddings/retrieval or generation.
            chunks = get_overview_context(paper_id)
            if not any(chunk["content"].strip() for chunk in chunks):
                raise PaperHasNoText()
            overview = PaperOverview.model_validate(generate_overview(chunks, overview_model()))
            cur.execute(
                "UPDATE papers SET overview = %s WHERE id = %s",
                (Jsonb(overview.model_dump(mode="json")), paper_id),
            )
            return OverviewResponse(paper_id=paper_id, status="ready", overview=overview)
