import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
    from app.ask_service import answer_question
    from app.main import ask_paper, SearchRequest

spec = importlib.util.spec_from_file_location('evaluate_generation', Path(__file__).resolve().parents[2] / 'evaluation/evaluate_generation.py')
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class SharedPipelineTests(unittest.TestCase):
    def test_pipeline_uses_same_retrieved_chunks_for_answer_and_review(self):
        chunks = [{'chunk_index': 1, 'page_number': 2, 'content': 'Evidence', 'similarity': .9}]
        with patch('app.ask_service.create_embedding', return_value=[.1]) as embed, patch('app.ask_service.search_chunks', return_value=chunks) as search, patch('app.ask_service.generate_answer', return_value='Answer [Page 2]') as generate:
            result = answer_question(4, 'Question', include_context=True)
        embed.assert_called_once_with('Question')
        search.assert_called_once_with(paper_id=4, query_embedding=[.1], limit=5)
        generate.assert_called_once_with(question='Question', retrieved_chunks=chunks)
        self.assertIs(result['retrieved_chunks'], chunks)
        self.assertNotIn('content', result['sources'][0])

    def test_endpoint_delegates_to_shared_pipeline(self):
        with patch('app.main.answer_question', return_value={'answer': 'same'}) as ask:
            self.assertEqual(ask_paper(SearchRequest(paper_id=4, question='Question')), {'answer': 'same'})
            ask.assert_called_once_with(4, 'Question')


class EvaluationTests(unittest.TestCase):
    def test_citation_parser_supports_lists_and_keeps_unsupported_variants(self):
        answer = (
            'A [Page 2] B [Page 3; Page 4] C [Pages 2, 7, 8] '
            'D [Page 5 and Page 9] E [Pages 3–5]'
        )
        pages, unparsed = evaluation.extract_citations(answer)
        self.assertEqual(pages, [2, 3, 4, 7, 8, 5, 9])
        self.assertEqual(unparsed, ['[Pages 3–5]'])

    def test_reparse_updates_only_derived_citation_fields(self):
        data = {
            'total_questions': 1,
            'results': [{
                'id': 'q1',
                'status': 'completed',
                'answer': 'Supported by [Page 3; Page 4].',
                'cited_pages': [3],
                'unparsed_citations': ['[Page 3; Page 4]'],
                'review': {'answer_correctness': True, 'notes': 'Keep this'},
            }],
        }
        before = {key: value for key, value in data['results'][0].items()
                  if key not in ('cited_pages', 'unparsed_citations')}
        self.assertEqual(evaluation.reparse_saved_citations(data), 1)
        self.assertEqual(data['results'][0]['cited_pages'], [3, 4])
        self.assertEqual(data['results'][0]['unparsed_citations'], [])
        self.assertEqual(
            {key: value for key, value in data['results'][0].items()
             if key not in ('cited_pages', 'unparsed_citations')},
            before,
        )

    def test_collect_saves_evidence_and_unreviewed_grades(self):
        ask = Mock(return_value={'answer': 'A [Page 2]', 'sources': [{'page_number': 2}], 'retrieved_chunks': [{'content': 'A'}]})
        row = evaluation.collect_answer({'id': 'q1', 'paper_id': 4, 'question': 'Q'}, ask)
        ask.assert_called_once_with(4, 'Q', include_context=True)
        self.assertEqual(row['cited_pages'], [2])
        self.assertEqual(row['retrieved_chunks'], [{'content': 'A'}])
        self.assertTrue(all(row['review'][metric] is None for metric in evaluation.METRICS))

    def test_resume_preserves_manual_grades_and_retries_errors(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            questions = Path(directory) / 'questions.json'
            output = Path(directory) / 'results.json'
            questions.write_text(json.dumps([{'id': f'q{i}', 'paper_id': 4, 'question': f'Q{i}'} for i in range(2)]))
            response = {'answer': 'Answer', 'sources': [], 'retrieved_chunks': []}
            ask = Mock(side_effect=[response, RuntimeError('Temporary failure')])
            data = evaluation.evaluate(questions, output, ask)
            self.assertEqual([r['status'] for r in data['results']], ['completed', 'error'])
            data['results'][0]['review']['groundedness'] = True
            evaluation.save(output, data)
            resumed = Mock(return_value=response)
            result = evaluation.evaluate(questions, output, resumed, resume=True)
            resumed.assert_called_once_with(4, 'Q1', include_context=True)
            self.assertTrue(result['results'][0]['review']['groundedness'])
            with self.assertRaises(ValueError): evaluation.evaluate(questions, output, resumed)

    def test_unreviewed_questions_do_not_become_passes(self):
        data = {'total_questions': 15, 'results': [{'status': 'completed', 'review': dict.fromkeys(evaluation.METRICS)}]}
        with redirect_stdout(io.StringIO()) as output: evaluation.summarize(data)
        self.assertIn('Not reviewed', output.getvalue())
        self.assertIn('reviewed 0/15', output.getvalue())


if __name__ == '__main__':
    unittest.main()
