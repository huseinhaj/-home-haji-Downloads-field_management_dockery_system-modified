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


class OcrProgressReportingTests(SimpleTestCase):
    """Paneli ya AI juu ya Marks Entry inaonyesha kama inasoma, hivyo
    frontend inapata stage/kurasa/mistari kutoka backend. Majaribio haya
    inalinda makubaliano hayo: sifa moja ikibadilika, paneli inakaa
    "inasoma..." bila maendeleo yoyote bila kuonekana mabadiliko."""

    def test_stage_fields_only_passes_known_stage_and_nonneg_ints(self):
        from results.marks_entry import _stage_fields
        # Celery's AsyncResult.info is not always a dict — a task that
        # never published meta yet can hand back None, a str, or bytes.
        self.assertEqual(_stage_fields(None), {})
        self.assertEqual(_stage_fields('PROGRESS'), {})
        self.assertEqual(_stage_fields({'stage': 'not-a-real-stage'}), {})
        self.assertEqual(
            _stage_fields({
                'stage': 'reading', 'pages_done': 2, 'pages_total': 5,
                'rows': 0, 'junk': 'x', 'pages_done2': None,
            }),
            {'stage': 'reading', 'pages_done': 2, 'pages_total': 5, 'rows': 0},
        )
        # A negative page count would render a nonsense progress bar.
        self.assertEqual(_stage_fields({'stage': 'reading', 'pages_done': -1}), {'stage': 'reading'})

    def test_report_stage_writes_to_cache_and_returns_meta(self):
        from django.core.cache import cache
        from results.tasks import report_ocr_stage
        cache.delete('scoresheet_ocr:testkey1')
        self.addCleanup(cache.delete, 'scoresheet_ocr:testkey1')

        meta = report_ocr_stage('testkey1', 'reading', done=1, total=3)
        self.assertEqual(meta, {'stage': 'reading', 'pages_done': 1, 'pages_total': 3})
        entry = cache.get('scoresheet_ocr:testkey1')
        self.assertEqual(entry['status'], 'processing')
        self.assertEqual(entry['stage'], 'reading')
        self.assertEqual((entry['pages_done'], entry['pages_total']), (1, 3))

        # A later stage must not wipe the page counters already published.
        report_ocr_stage('testkey1', 'matching', rows=17)
        entry = cache.get('scoresheet_ocr:testkey1')
        self.assertEqual(entry['stage'], 'matching')
        self.assertEqual(entry['rows'], 17)
        self.assertEqual(entry['status'], 'processing')

    def test_report_stage_without_key_still_returns_meta_for_celery(self):
        from results.tasks import report_ocr_stage
        # Celery path has no progress_key — meta goes out via
        # self.update_state, and the cache must not be touched.
        self.assertEqual(
            report_ocr_stage(None, 'matching', rows=4),
            {'stage': 'matching', 'rows': 4},
        )

    def test_a_failed_page_still_advances_the_progress_counter(self):
        # Ukurasa mmoja unaofeli lazima pia uhesabiwe: mwenyesi wa paneli
        # akisubiri 3/3 ambayo haizishambuliwa hana sababu ya kusubiri.
        progress = []

        def fake_read(img):
            if img == 'page2':
                raise RuntimeError('vision API timed out')
            return '[{"row": 1, "name": "Survivor", "score": 70}]'

        with mock.patch.object(ocr, 'OPENROUTER_API_KEY', 'k'), \
                mock.patch.object(ocr, 'GOOGLE_API_KEY', 'k'), \
                mock.patch.object(ocr, '_load_page_images', return_value=['page1', 'page2', 'page3']), \
                mock.patch.object(ocr, '_read_page_with_ai', side_effect=fake_read):
            rows = ocr.extract_scores_from_document(
                object(), on_progress=lambda s, d, t: progress.append((s, d, t))
            )
        # Partial results still come back — a dead page is not fatal, and
        # the two surviving pages both contribute.
        self.assertEqual(len(rows), 2)
        self.assertEqual(progress[0], ('reading', 0, 3))
        self.assertEqual(sorted(d for _, d, _ in progress), [0, 1, 2, 3])
        self.assertEqual({t for _, _, t in progress}, {3})
        self.assertEqual({s for s, _, _ in progress}, {'reading'})
