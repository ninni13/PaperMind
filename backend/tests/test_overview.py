import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError
from app.overview import PaperOverview
from app.overview_service import OverviewGenerationError, generate_overview
with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
    from app.overview_repository import (
        create_overview, get_overview, OverviewBusy, PaperNotFound, PaperHasNoText,
    )


def overview(**updates):
    data = dict(research_question=None, method=None, datasets=[], key_results=[], limitations=[])
    return PaperOverview(**(data | updates))


def chunk(index=0, content='Selected evidence'):
    return {'chunk_index': index, 'page_number': index + 1, 'content': content}


class ExtractionTests(unittest.TestCase):
    def test_one_call_contains_only_selected_evidence_in_order(self):
        with patch('app.overview_service.OpenAI') as client:
            parse = client.return_value.__enter__.return_value.responses.parse
            parse.return_value = SimpleNamespace(status='completed', output_parsed=overview(method='Method [Page 3]'))
            result = generate_overview([chunk(2, 'METHOD'), chunk(0, 'QUESTION')], 'test-model')
        self.assertEqual(result.method, 'Method [Page 3]')
        parse.assert_called_once()
        args = parse.call_args.kwargs
        self.assertEqual(args['model'], 'test-model')
        self.assertIs(args['text_format'], PaperOverview)
        self.assertIn('ONLY the supplied retrieved context', args['instructions'])
        self.assertIn('Do not use outside knowledge', args['instructions'])
        self.assertIn('null', args['instructions'])
        self.assertIn('[]', args['instructions'])
        self.assertEqual(args['input'], '<retrieved_context>\n[Page 1, Chunk 0]\nQUESTION\n\n[Page 3, Chunk 2]\nMETHOD\n</retrieved_context>')

    def test_empty_or_oversized_context_never_calls_model(self):
        for chunks in [[], [chunk(content=' ')], [chunk(i) for i in range(16)], [chunk(content='x' * 24001)]]:
            with self.subTest(size=len(chunks)), patch('app.overview_service.OpenAI') as client:
                with self.assertRaises(OverviewGenerationError): generate_overview(chunks, 'test-model')
                client.assert_not_called()

    def test_fifteen_chunks_are_accepted(self):
        with patch('app.overview_service.OpenAI') as client:
            parse = client.return_value.__enter__.return_value.responses.parse
            parse.return_value = SimpleNamespace(status='completed', output_parsed=overview())
            generate_overview([chunk(i) for i in range(15)], 'test-model')
            parse.assert_called_once()
            self.assertIn('[Page 15, Chunk 14]', parse.call_args.kwargs['input'])

    def test_refusal_incomplete_and_invalid_json_are_rejected(self):
        for status, parsed, error in [
            ('completed', None, OverviewGenerationError),
            ('incomplete', overview(), OverviewGenerationError),
            ('completed', {'method': 'Missing fields'}, ValidationError),
        ]:
            with self.subTest(status=status), patch('app.overview_service.OpenAI') as client:
                client.return_value.__enter__.return_value.responses.parse.return_value = SimpleNamespace(status=status, output_parsed=parsed)
                with self.assertRaises(error): generate_overview([chunk()], 'test-model')

    def test_schema_has_exactly_five_fields_and_preserves_unknowns(self):
        data = overview().model_dump()
        self.assertEqual(set(data), {'research_question', 'method', 'datasets', 'key_results', 'limitations'})
        self.assertIsNone(data['method'])
        self.assertEqual(data['limitations'], [])
        for updates in [{'datasets': 'NTU'}, {'unknown': 'value'}, {'method': ''}]:
            with self.subTest(updates=updates), self.assertRaises(ValidationError):
                PaperOverview.model_validate(data | updates)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.connection_patch = patch('app.overview_repository.get_connection')
        self.connection = self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        self.cur = self.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.retrieve_patch = patch('app.overview_repository.get_overview_context', return_value=[chunk()])
        self.retrieve = self.retrieve_patch.start()
        self.addCleanup(self.retrieve_patch.stop)
        self.generate_patch = patch('app.overview_repository.generate_overview', return_value=overview())
        self.generate = self.generate_patch.start()
        self.addCleanup(self.generate_patch.stop)
        self.cached = (overview(method='Cached method').model_dump(),)

    def test_get_hit_and_miss_never_retrieve_or_generate(self):
        self.cur.fetchone.side_effect = [(None,), self.cached]
        self.assertEqual(get_overview(1).status, 'not_generated')
        self.assertEqual(get_overview(1).overview.method, 'Cached method')
        self.retrieve.assert_not_called()
        self.generate.assert_not_called()

    def test_post_cache_hit_skips_retrieval_and_generation(self):
        self.cur.fetchone.side_effect = [(True,), self.cached]
        self.assertEqual(create_overview(1).overview.method, 'Cached method')
        self.retrieve.assert_not_called()
        self.generate.assert_not_called()
        self.assertFalse(any(call.args[0].startswith('UPDATE papers SET') for call in self.cur.execute.call_args_list))

    def test_concurrent_request_is_rejected_before_retrieval(self):
        self.cur.fetchone.return_value = (False,)
        with self.assertRaises(OverviewBusy): create_overview(1)
        self.retrieve.assert_not_called()
        self.generate.assert_not_called()

    def test_missing_and_empty_papers_do_not_generate(self):
        self.cur.fetchone.side_effect = [(True,), None]
        with self.assertRaises(PaperNotFound): create_overview(1)
        self.retrieve.assert_not_called()
        self.cur.fetchone.side_effect = [(True,), (None,)]
        self.retrieve.return_value = []
        with self.assertRaises(PaperHasNoText): create_overview(1)
        self.generate.assert_not_called()

    def test_failure_and_invalid_schema_never_update_cache(self):
        for result in [OverviewGenerationError(), {'method': 'Invalid'}]:
            self.cur.reset_mock()
            self.cur.fetchone.side_effect = [(True,), (None,)]
            self.generate.side_effect = result if isinstance(result, Exception) else None
            self.generate.return_value = result
            with self.assertRaises((OverviewGenerationError, ValidationError)): create_overview(1)
            self.assertFalse(any(call.args[0].startswith('UPDATE papers SET') for call in self.cur.execute.call_args_list))

    def test_miss_retrieves_once_and_updates_papers_jsonb(self):
        self.cur.fetchone.side_effect = [(True,), (None,)]
        self.assertEqual(create_overview(1).status, 'ready')
        self.retrieve.assert_called_once_with(1)
        self.generate.assert_called_once()
        self.assertEqual(self.generate.call_args.args[0], [chunk()])
        update = next(call for call in self.cur.execute.call_args_list if 'UPDATE papers SET' in call.args[0])
        self.assertEqual(update.args[1][0].obj, overview().model_dump())
        self.assertEqual(update.args[1][1], 1)
        self.assertFalse(any('paper_overviews' in call.args[0] for call in self.cur.execute.call_args_list))


if __name__ == '__main__':
    unittest.main()
