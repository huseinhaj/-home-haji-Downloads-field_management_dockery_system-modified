"""Kosa la AI ya kusoma scoresheet linaelezwa kwa lugha rahisi."""
from unittest import mock

from django.test import SimpleTestCase
from PIL import Image

from results.services import scoresheet_ocr_service as ocr


class AIErrorMessageTests(SimpleTestCase):
    def _read(self, or_exc, gemini_exc):
        img = Image.new('RGB', (40, 20), 'white')
        with mock.patch.object(ocr, 'OPENROUTER_API_KEY', 'k'), \
                mock.patch.object(ocr, 'GOOGLE_API_KEY', 'k'), \
                mock.patch.object(ocr, '_call_openrouter_vision', side_effect=or_exc), \
                mock.patch.object(ocr, '_call_gemini_vision', side_effect=gemini_exc):
            with self.assertRaises(RuntimeError) as cm:
                ocr._read_page_with_ai(img)
        return str(cm.exception)

    def test_both_providers_explained(self):
        msg = self._read(
            RuntimeError('OpenRouter vision error 402: {"error":{"message":"Insufficient credits."}}'),
            RuntimeError('Gemini vision error 401: {"error":{"status":"UNAUTHENTICATED"}}'),
        )
        self.assertIn('OpenRouter: salio limeisha (402)', msg)
        self.assertIn('Gemini: ufunguo wa API kwenye server si sahihi (401)', msg)
        self.assertNotIn('{', msg)

    def test_truncation_marker_survives_for_retry(self):
        msg = self._read(RuntimeError('OR_TRUNCATED'), RuntimeError('Read timed out'))
        self.assertIn('OR_TRUNCATED', msg)
        self.assertIn('imechelewa kujibu', msg)
