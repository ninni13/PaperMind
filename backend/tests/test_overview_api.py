import os
import unittest
from unittest.mock import patch

# No credentials or model calls are needed by endpoint tests.
with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
    from app.main import app
from fastapi.testclient import TestClient
from app.overview import OverviewResponse
from app.overview_service import OverviewGenerationError
from app.overview_repository import OverviewBusy, PaperNotFound, PaperHasNoText


class OverviewAPITests(unittest.TestCase):
    def setUp(self):
        # Not entering the client context skips the real DB startup migration.
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_read_not_generated_has_stable_envelope(self):
        with patch('app.main.get_overview', return_value=OverviewResponse(paper_id=5, status='not_generated')):
            response = self.client.get('/papers/5/overview')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'not_generated')
        self.assertIsNone(response.json()['overview'])

    def test_post_returns_typed_response(self):
        saved = OverviewResponse(paper_id=5, status='ready', overview={
            'research_question': 'A question', 'method': None,
            'datasets': ['Example'], 'key_results': [], 'limitations': [],
        })
        with patch('app.main.create_overview', return_value=saved):
            response = self.client.post('/papers/5/overview')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['overview']['datasets'], ['Example'])

    def test_error_statuses(self):
        for error, status in [(PaperNotFound(), 404), (OverviewBusy(), 409),
                              (PaperHasNoText(), 422), (OverviewGenerationError(), 502)]:
            with self.subTest(status=status), patch('app.main.create_overview', side_effect=error), patch('app.main.logging'):
                response = self.client.post('/papers/5/overview')
                self.assertEqual(response.status_code, status)
                self.assertIsInstance(response.json()['detail'], str)

    def test_missing_paper_get(self):
        with patch('app.main.get_overview', side_effect=PaperNotFound()):
            self.assertEqual(self.client.get('/papers/999/overview').status_code, 404)


if __name__ == '__main__':
    unittest.main()
