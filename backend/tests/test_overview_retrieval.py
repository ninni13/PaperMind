import os
import unittest
from unittest.mock import call, patch

with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
    from app.overview_retrieval import OVERVIEW_QUERIES, get_overview_context
from app.repository import get_first_chunks


def chunk(index, page=1):
    return {'chunk_index': index, 'page_number': page, 'content': f'Text {index}'}


class OverviewRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.front_patch = patch('app.overview_retrieval.get_first_chunks')
        self.embedding_patch = patch('app.overview_retrieval.create_embeddings')
        self.search_patch = patch('app.overview_retrieval.search_chunks')
        self.front = self.front_patch.start()
        self.embed = self.embedding_patch.start()
        self.search = self.search_patch.start()
        for patcher in (self.front_patch, self.embedding_patch, self.search_patch):
            self.addCleanup(patcher.stop)
        self.front.return_value = [chunk(0), chunk(1), chunk(2, 2)]
        self.embed.return_value = [[0.1], [0.2], [0.3], [0.4]]

    def test_merges_all_queries_preserves_opening_and_deduplicates_by_chunk(self):
        self.search.side_effect = [
            [chunk(8, 4) | {'similarity': .9}, chunk(2, 2)],
            [chunk(5, 3), chunk(8, 4)],
            [chunk(7, 3)],
            [chunk(12, 8), chunk(5, 3)],
        ]
        result = get_overview_context(5)
        self.assertEqual([c['chunk_index'] for c in result], [0, 1, 2, 5, 7, 8, 12])
        self.assertEqual(result[-1]['page_number'], 8)
        self.assertTrue(all(set(c) == {'chunk_index', 'page_number', 'content'} for c in result))
        self.front.assert_called_once_with(5, limit=3)
        self.embed.assert_called_once_with(list(OVERVIEW_QUERIES))
        self.assertEqual(self.search.call_args_list, [call(5, [value], limit=3) for value in (.1, .2, .3, .4)])

    def test_empty_paper_does_not_spend_embedding_tokens(self):
        self.front.return_value = []
        self.assertEqual(get_overview_context(5), [])
        self.embed.assert_not_called()
        self.search.assert_not_called()

    def test_no_semantic_matches_still_returns_opening(self):
        self.search.return_value = []
        self.assertEqual(get_overview_context(5), [chunk(0), chunk(1), chunk(2, 2)])

    def test_custom_limits_and_invalid_limits(self):
        self.search.return_value = []
        get_overview_context(5, front_limit=2, query_limit=4)
        self.front.assert_called_once_with(5, limit=2)
        self.assertTrue(all(c.kwargs['limit'] == 4 for c in self.search.call_args_list))
        for front, semantic in [(0, 3), (3, 0), (-1, 3)]:
            with self.subTest(front=front, semantic=semantic), self.assertRaises(ValueError):
                get_overview_context(5, front_limit=front, query_limit=semantic)

    def test_missing_embedding_or_search_failure_does_not_return_partial_context(self):
        self.embed.return_value = [[0.1]]
        with self.assertRaises(ValueError):
            get_overview_context(5)
        self.search.assert_not_called()
        self.embed.return_value = [[0.1]] * 4
        self.search.side_effect = RuntimeError('Search failed')
        with self.assertRaises(RuntimeError):
            get_overview_context(5)


class FirstChunksTests(unittest.TestCase):
    def test_paper_filter_order_limit_and_page_metadata(self):
        with patch('app.repository.get_connection') as connection:
            cursor = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchall.return_value = [(0, 1, 'Abstract'), (1, 1, 'Introduction'), (2, 2, 'Contribution')]
            result = get_first_chunks(5)
            sql, params = cursor.execute.call_args.args
            self.assertIn('WHERE paper_id = %s', sql)
            self.assertIn('ORDER BY chunk_index ASC', sql)
            self.assertIn('LIMIT %s', sql)
            self.assertEqual(params, (5, 3))
            self.assertEqual(result[2], {'chunk_index': 2, 'page_number': 2, 'content': 'Contribution'})


if __name__ == '__main__':
    unittest.main()
