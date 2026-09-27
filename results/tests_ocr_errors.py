"""Kosa la AI ya kusoma scoresheet linaelezwa kwa lugha rahisi."""
import os
from unittest import mock

from django.test import SimpleTestCase
from PIL import Image

from results.services import scoresheet_ocr_service as ocr


class AIErrorMessageTests(SimpleTestCase):
    def setUp(self):
        # A 402 in the first test puts OpenRouter into its out-of-credits
        # cooldown, which would make the next test skip the provider
        # entirely — clear the memory so each test sees a fresh chain.
        ocr._reset_provider_health()
        self.addCleanup(ocr._reset_provider_health)

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
        self.assertIn('Gemini: ufunguo wa Gemini si sahihi (401 UNAUTHENTICATED)', msg)
        self.assertNotIn('{', msg)

    def test_permission_denied_is_not_reported_as_a_bad_key(self):
        """403 = API haijasajiliwa / ufunguo wa Android pekee. Kuiita 'ufunguo
        si sahihi' ilipelekea mpangilio akafuate ufunguo mpwa mara kwa mara
        wakati suluhisho lake ni kuwasha API kwenye Google Cloud Console."""
        msg = self._read(
            RuntimeError('OpenRouter vision error 402: insufficient'),
            RuntimeError('Gemini vision error 403: {"error":{"status":"PERMISSION_DENIED"}}'),
        )
        self.assertIn('403 PERMISSION_DENIED', msg)
        self.assertIn('Generative Language API → ENABLE', msg)
        self.assertNotIn('ufunguo wa Gemini si sahihi', msg)

    def test_unknown_error_still_shows_googles_own_words(self):
        """Kosa lisichojulikana hatakuwa 'hitilafu isiyotambulika: <code>'
        tu — mpangilio anapaswa kuona namba halisi ya mtoa huduma."""
        msg = self._read(
            RuntimeError('weird'),
            RuntimeError('Gemini vision error 500: {"error":{"status":"UNAVAILABLE"}}'),
        )
        self.assertIn('500 UNAVAILABLE', msg)
        self.assertNotIn('is same 401', msg)

    def test_truncation_marker_survives_for_retry(self):
        msg = self._read(RuntimeError('OR_TRUNCATED'), RuntimeError('Read timed out'))
        self.assertIn('OR_TRUNCATED', msg)
        self.assertIn('imechelewa kujibu', msg)


class KeyReadingTests(SimpleTestCase):
    """Ufunguo ulioambishwa na viwilio/alama za semi hufaanya Google 401 —
    mfumo humuita 'ufunguo si sahihi' wakati kwa kweli ni sahihi."""

    def test_surrounding_junk_is_stripped(self):
        for raw in ['  KEY  ', '"KEY"', "'KEY'", ' "KEY" \n', '\tKEY\r\n']:
            with mock.patch.dict(os.environ, {'GOOGLE_API_KEY': raw}):
                self.assertEqual(ocr._read_key('GOOGLE_API_KEY'), 'KEY')

    def test_plain_key_untouched(self):
        with mock.patch.dict(os.environ, {'GOOGLE_API_KEY': 'AQ.Ab8RN6J'}):
            self.assertEqual(ocr._read_key('GOOGLE_API_KEY'), 'AQ.Ab8RN6J')

    def test_unset_key_is_empty_not_none(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ocr._read_key('GOOGLE_API_KEY'), '')

    def test_fingerprint_flags_paste_junk_without_leaking_the_key(self):
        with mock.patch.dict(os.environ, {'GOOGLE_API_KEY': ' "AQ.Ab8RN6J"'}):
            fp = ocr._key_fingerprint('GOOGLE_API_KEY')
        self.assertTrue(fp['had_paste_junk'])
        self.assertEqual(fp['len'], 10)
        self.assertEqual(fp['prefix'], 'AQ.Ab8')
        self.assertNotIn('RN6J', str(fp))

    def test_fingerprint_reports_a_missing_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(ocr._key_fingerprint('GOOGLE_API_KEY')['missing'])


class ProviderOrderTests(SimpleTestCase):
    """Gemini (bure) kwanza, OpenRouter (ya malipo) cha pili — ili mfumo
    usikae unanilipa kila kwanza wanapotaka kusoma wanafunzi kwa AI."""

    def setUp(self):
        ocr._reset_provider_health()
        self.addCleanup(ocr._reset_provider_health)
        self.img = Image.new('RGB', (40, 20), 'white')

    def test_default_order_prefers_free_gemini(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('OCR_PROVIDER_ORDER', None)
            self.assertEqual(ocr._provider_order(), ['gemini', 'openrouter'])

    def test_env_can_restore_paid_first(self):
        with mock.patch.dict(os.environ, {'OCR_PROVIDER_ORDER': 'openrouter,gemini'}):
            self.assertEqual(ocr._provider_order(), ['openrouter', 'gemini'])

    def test_gemini_success_never_calls_openrouter(self):
        with mock.patch.object(ocr, 'OPENROUTER_API_KEY', 'k'), \
                mock.patch.object(ocr, 'GOOGLE_API_KEY', 'k'), \
                mock.patch.object(ocr, '_call_gemini_vision', return_value='[]') as gem, \
                mock.patch.object(ocr, '_call_openrouter_vision') as orr:
            self.assertEqual(ocr._read_page_with_ai(self.img), '[]')
        self.assertEqual(gem.call_count, 1)
        self.assertEqual(orr.call_count, 0)

    def test_openrouter_skipped_after_out_of_credits(self):
        # Both down: Gemini is tried, then OpenRouter answers 402. Page 2 of
        # the same upload must not pay for another doomed call.
        with mock.patch.object(ocr, 'OPENROUTER_API_KEY', 'k'), \
                mock.patch.object(ocr, 'GOOGLE_API_KEY', 'k'), \
                mock.patch.object(ocr, '_call_openrouter_vision',
                                  side_effect=RuntimeError('OpenRouter vision error 402: Insufficient credits')) as orr, \
                mock.patch.object(ocr, '_call_gemini_vision', side_effect=RuntimeError('Gemini down')):
            with self.assertRaises(RuntimeError):
                ocr._read_page_with_ai(self.img)
            self.assertEqual(orr.call_count, 1)
            self.assertFalse(ocr._openrouter_usable())
            with self.assertRaises(RuntimeError):
                ocr._read_page_with_ai(self.img)
            self.assertEqual(orr.call_count, 1)

    def test_openrouter_used_again_after_cooldown(self):
        with mock.patch.object(ocr, 'OPENROUTER_API_KEY', 'k'), \
                mock.patch.object(ocr, 'GOOGLE_API_KEY', 'k'), \
                mock.patch.object(ocr, '_call_openrouter_vision', return_value='[]') as orr, \
                mock.patch.object(ocr, '_call_gemini_vision', side_effect=RuntimeError('Gemini down')):
            ocr._disable_openrouter(seconds=0)
            self.assertEqual(orr.call_count, 0)
            ocr._read_page_with_ai(self.img)
        self.assertEqual(orr.call_count, 1)
