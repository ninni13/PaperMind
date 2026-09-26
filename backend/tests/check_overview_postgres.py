"""Run explicitly: venv/bin/python -m tests.check_overview_postgres.
Uses session-local temporary tables. Rolls back all test writes. No LLM calls.
"""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / '.env')
from app.database import get_connection
from app.overview import PaperOverview
from app.overview_service import OverviewGenerationError
from app.overview_repository import create_overview, get_overview, OverviewBusy


def main():
    conn = get_connection()
    try:
        conn.execute('CREATE TEMP TABLE papers (id BIGINT PRIMARY KEY)')
        conn.execute('CREATE TEMP TABLE chunks (paper_id BIGINT, chunk_index INTEGER, page_number INTEGER, content TEXT)')
        sql = (Path(__file__).resolve().parent.parent / 'migrations/002_papers_overview.sql').read_text()
        conn.execute(sql)
        conn.execute(sql)  # Idempotent migration
        # Above 32-bit range verifies compatibility with papers.id BIGINT.
        paper_id = 5000000123
        conn.execute('INSERT INTO papers VALUES (%s)', (paper_id,))
        conn.execute('INSERT INTO chunks VALUES (%s, 0, 1, %s), (%s, 1, 3, %s)',
                     (paper_id, 'Introduction', paper_id, 'Final limitations'))

        @contextmanager
        def test_connection():
            with conn.transaction():
                yield conn

        result = PaperOverview(research_question='Test question', method=None,
                               datasets=['Test dataset'], key_results=['Test result [Page 3]'], limitations=[])
        with patch('app.overview_repository.get_connection', test_connection), patch(
            'app.overview_repository.get_overview_context',
            return_value=[{'chunk_index': 0, 'page_number': 1, 'content': 'Introduction'},
                          {'chunk_index': 1, 'page_number': 3, 'content': 'Final limitations'}],
        ) as retrieve:
            assert get_overview(paper_id).status == 'not_generated'
            with patch('app.overview_repository.generate_overview', side_effect=OverviewGenerationError()):
                try:
                    create_overview(paper_id)
                except OverviewGenerationError:
                    pass
                else:
                    raise AssertionError('Expected failed generation')
            assert get_overview(paper_id).status == 'not_generated'
            retrieve.reset_mock()
            with patch('app.overview_repository.generate_overview', return_value=result) as generate:
                saved = create_overview(paper_id)
                assert saved.overview == result
                assert get_overview(paper_id).overview == result
                assert create_overview(paper_id).overview == result
                assert generate.call_count == 1
                assert retrieve.call_count == 1
                assert conn.execute('SELECT overview FROM papers WHERE id = %s', (paper_id,)).fetchone()[0] == result.model_dump()
            conn.execute('DELETE FROM papers WHERE id = %s', (paper_id,))
            assert conn.execute('SELECT COUNT(*) FROM papers').fetchone()[0] == 0
        # A second connection must see the transaction-scoped advisory lock.
        with get_connection() as other:
            with patch('app.overview_repository.get_connection', return_value=other):
                try:
                    create_overview(paper_id)
                except OverviewBusy:
                    pass
                else:
                    raise AssertionError('Concurrent generation was not excluded')
        print('PASS: BIGINT IDs, rollback/retry, JSONB round trip, zero-retrieval cache hits, paper deletion, cross-connection exclusion')
    finally:
        conn.rollback()
        conn.close()


if __name__ == '__main__':
    main()
