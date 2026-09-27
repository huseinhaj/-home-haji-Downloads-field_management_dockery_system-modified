"""Tests za Roster Scan — piga picha ya orodha → AI inasoma → uhakiki →
hifadhi (badala ya ku-upload faili).

Hakuna API call halisi: extract_students_from_document inafanyiwa mock,
kwa hivyo tests zinajaribu view logic (auth, validation, preview JSON,
save + dedup) bila kutegemea OpenRouter/Gemini.
"""
import json
from unittest import mock

from django.http import JsonResponse
from django.test import Client, TestCase
from django.urls import reverse

from .models import FormStudent, School, TeacherAccount


class RosterScanTestBase(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Shule ya Scan', region='Dodoma', district='Dodoma',
            current_academic_year=2026, level='secondary',
        )
        cls.academic = TeacherAccount.objects.create(
            email='scan@example.com', full_name='Academic Scan',
            role=TeacherAccount.ROLE_ACADEMIC, school=cls.school,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')


class ScanRosterViewTests(RosterScanTestBase):

    def test_scan_requires_form(self):
        resp = self.client.post(reverse('scan_roster'), {})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.json())

    def test_scan_rejects_invalid_form_number(self):
        resp = self.client.post(reverse('scan_roster'), {'form': '9'})
        self.assertEqual(resp.status_code, 400)

    def test_scan_without_file_returns_400(self):
        resp = self.client.post(reverse('scan_roster'), {'form': '1'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Hakuna picha', resp.json()['error'])

    def test_scan_kicks_off_task_and_returns_202(self):
        """Scan hausubiri AI — anarudisha task_id mara moja (frontend anala
        kwa polling). Hapa tunathibitisha kuanza kazi, kwamba hakuna
        kilichohifadhiwa na kwamba frontend inajua task_id."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_file = SimpleUploadedFile('roster.jpg', b'fake-image-bytes', content_type='image/jpeg')
        with mock.patch('results.views.process_roster_scan_task.apply_async') as apply_async:
            apply_async.return_value = mock.Mock(id='celery-task-1')
            resp = self.client.post(reverse('scan_roster'), {'form': '1', 'scan_file': fake_file})
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()['task_id'], 'celery-task-1')
        apply_async.assert_called_once()
        # Preview bado haipo — inatoka baada ya poll
        self.assertNotIn('students', resp.json())
        self.assertEqual(FormStudent.objects.filter(school=self.school).count(), 0)

    def test_scan_falls_back_to_thread_when_no_celery_worker(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_file = SimpleUploadedFile('roster.jpg', b'fake-image-bytes', content_type='image/jpeg')
        # Celery conf hauruhusu assignment moja kwa moja
        # (task_always_eager hubaki True), kwa hivyo tunaficha app nzima.
        fake_app = mock.Mock()
        fake_app.conf.task_always_eager = False
        with mock.patch('field_management.celery.app', fake_app), \
             mock.patch('results.marks_entry._celery_worker_consuming', return_value=False), \
             mock.patch('results.views._run_roster_scan_background',
                        return_value=JsonResponse({'task_id': 'local-1'}, status=202)) as runner:
            resp = self.client.post(reverse('scan_roster'), {'form': '1', 'scan_file': fake_file})
        self.assertEqual(resp.status_code, 202)
        runner.assert_called_once()

    def test_scan_requires_login(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.logout()
        fake_file = SimpleUploadedFile('roster.jpg', b'fake-image-bytes', content_type='image/jpeg')
        resp = self.client.post(reverse('scan_roster'), {'form': '1', 'scan_file': fake_file})
        self.assertIn(resp.status_code, (302, 401, 403))


class RosterScanStatusTests(RosterScanTestBase):
    """roster_scan_status ndio mzito wa paneli ya maendeleo: ndiyo
    inayoripoti kurasa zilizosomwa na mistari ili paneli ionyeshe
    progress halisi, si 'subiri kidogo'."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        self.cache = cache

    def _local_id(self):
        from results.views import _ROSTER_TASK_PREFIX
        return f'{_ROSTER_TASK_PREFIX}{self.id()}'

    def test_status_reports_stage_and_pages(self):
        task_id = self._local_id()
        self.cache.set(f'roster_scan_ocr:{task_id}', {
            'status': 'processing', 'stage': 'reading',
            'pages_done': 2, 'pages_total': 5, 'rows': 3,
        }, timeout=60)
        resp = self.client.get(reverse('roster_scan_status', args=[task_id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'processing')
        self.assertEqual(data['stage'], 'reading')
        self.assertEqual(data['pages_done'], 2)
        self.assertEqual(data['pages_total'], 5)
        self.assertEqual(data['rows'], 3)

    def test_status_drops_unknown_stage_and_garbage(self):
        """stage isiyo ya OCR_STAGES haipaswi kuingia kwenye JSON —
        frontend haina hatua nyingine za kuonyesha."""
        task_id = self._local_id()
        self.cache.set(f'roster_scan_ocr:{task_id}', {
            'status': 'processing', 'stage': 'not-a-real-stage',
            'pages_done': 'two', 'rows': -1,
        }, timeout=60)
        data = self.client.get(reverse('roster_scan_status', args=[task_id])).json()
        self.assertNotIn('stage', data)
        self.assertNotIn('pages_done', data)
        self.assertNotIn('rows', data)

    def test_status_returns_preview_without_saving(self):
        task_id = self._local_id()
        students = [{'first': 'Halima', 'middle': 'Ally', 'last': 'Mohamed', 'gender': 'F', 'row': 1}]
        self.cache.set(f'roster_scan_ocr:{task_id}', {
            'status': 'done', 'result': {'students': students},
        }, timeout=60)
        resp = self.client.get(reverse('roster_scan_status', args=[task_id]))
        data = resp.json()
        self.assertEqual(data['status'], 'preview')
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['students'][0]['first'], 'Halima')
        # Muhakiki wa Academic ndio unaohifadhi — endpoint hii hairuhusu
        self.assertEqual(FormStudent.objects.filter(school=self.school).count(), 0)

    def test_status_surfaces_task_error(self):
        task_id = self._local_id()
        self.cache.set(f'roster_scan_ocr:{task_id}', {
            'status': 'failed', 'error': 'Gemini imekataa',
        }, timeout=60)
        resp = self.client.get(reverse('roster_scan_status', args=[task_id]))
        self.assertEqual(resp.status_code, 500)
        self.assertIn('Gemini imekataa', resp.json()['error'])

    def test_status_treats_expired_cache_as_still_processing(self):
        """Cache inaweza kufutwa kabisa poll hajalikuwa — tunarudi
        'processing' badala ya 404 ili frontend ionyeshe bado inasubiri
        (mpaka MAX_WAIT_MS) kuliko kuonyesha kosa la kubwa."""
        data = self.client.get(reverse('roster_scan_status', args=[self._local_id()])).json()
        self.assertEqual(data['status'], 'processing')

    def test_status_reads_celery_meta(self):
        pending = mock.Mock()
        pending.ready.return_value = False
        pending.info = {'stage': 'matching', 'pages_done': 3, 'pages_total': 3, 'rows': 9}
        with mock.patch('results.views.AsyncResult', return_value=pending):
            data = self.client.get(reverse('roster_scan_status', args=['celery-id'])).json()
        self.assertEqual(data['status'], 'processing')
        self.assertEqual(data['stage'], 'matching')
        self.assertEqual(data['rows'], 9)

    def test_status_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('roster_scan_status', args=[self._local_id()]))
        self.assertIn(resp.status_code, (302, 401, 403))

    def test_background_runner_writes_done_to_matching_cache_key(self):
        """Regression: task na runner lazima tumie kichicho KILELE
        ('roster_scan_ocr:...'). Zikiwa tofauti, progress inaandikwa
        chini ya kichicho cha scoresheet na paneli ya orodha inabaki
        'processing' milele."""
        from results import views as results_views

        students = [{'first': 'Juma', 'middle': 'H', 'last': 'R', 'gender': 'M', 'row': 1}]
        captured = {}

        def fake_extract(document, on_progress=None):
            captured['called'] = True
            return students

        def _run_now(thread_self, *a, **kw):
            # .start() inapata lengo kwenye constructor, si kama argument
            thread_self._target(*thread_self._args, **thread_self._kwargs)

        with mock.patch('results.services.roster_scan_service.extract_students_from_document', fake_extract), \
             mock.patch('results.tasks.default_storage.open', mock.MagicMock()), \
             mock.patch('threading.Thread.start', _run_now):
            resp = results_views._run_roster_scan_background('roster_scan/x.jpg')

        self.assertEqual(resp.status_code, 202)
        task_id = json.loads(resp.content)['task_id']
        entry = self.cache.get(f'roster_scan_ocr:{task_id}')
        self.assertIsNotNone(entry, 'runner hakuandika chini ya kichicho cha roster')
        self.assertEqual(entry['status'], 'done')
        self.assertEqual(entry['result']['students'], students)
        self.assertTrue(captured.get('called'))

    def test_task_reports_progress_under_roster_namespace(self):
        """process_roster_scan_task inapeleka meta chini ya kichicho
        cha orodha — hapo ndipo status endpoint inayoisoma."""
        from django.core.cache import cache
        from results.tasks import process_roster_scan_task

        seen = {}

        def fake_extract(document, on_progress=None):
            on_progress('reading', 0, 2)
            on_progress('reading', 1, 2)
            on_progress('matching', 2, 2, rows=1)
            return [{'first': 'A', 'middle': '', 'last': 'B', 'gender': 'M', 'row': 1}]

        with mock.patch('results.services.roster_scan_service.extract_students_from_document', fake_extract), \
             mock.patch('results.tasks.default_storage.open', mock.MagicMock()):
            out = process_roster_scan_task.run('roster_scan/x.jpg', progress_key='k1')

        self.assertNotIn('error', out)
        entry = cache.get('roster_scan_ocr:k1')
        self.assertIsNotNone(entry, 'meta haikuandikwa kwenye kichicho cha roster')
        self.assertEqual(entry['stage'], 'matching')
        self.assertEqual(entry['pages_done'], 2)
        self.assertEqual(entry['rows'], 1)
        self.assertIsNone(cache.get('scoresheet_ocr:k1'),
                          'meta ya orodha imeandikwa chini ya kichicho cha scoresheet!')
        seen.clear()



class SaveScannedRosterTests(RosterScanTestBase):

    def _post(self, students, form=1):
        payload = {'form': form, 'students': students}
        return self.client.post(
            reverse('save_scanned_roster'),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_save_creates_students(self):
        resp = self._post([
            {'first': 'Halima', 'middle': 'Ally', 'last': 'Mohamed', 'gender': 'F'},
            {'first': 'Juma', 'middle': '', 'last': 'Ramadhani', 'gender': 'M'},
        ])
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['saved'], 2)
        self.assertEqual(data['created'], 2)
        self.assertEqual(
            FormStudent.objects.filter(school=self.school, form=1, is_active=True).count(), 2,
        )
        fs = FormStudent.objects.get(school=self.school, first_name='Halima')
        self.assertEqual((fs.middle_name, fs.last_name, fs.gender), ('Ally', 'Mohamed', 'F'))

    def test_save_dedups_against_existing_roster(self):
        FormStudent.objects.create(
            school=self.school, form=1, academic_year=2026,
            admission_no='S001', first_name='Halima', middle_name='Ally',
            last_name='Mohamed', gender='F',
        )
        resp = self._post([
            {'first': 'Halima', 'middle': 'Ally', 'last': 'Mohamed', 'gender': 'F'},
            {'first': 'Mpya', 'middle': '', 'last': 'Kabisa', 'gender': 'M'},
        ])
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['saved'], 2)
        self.assertEqual(data['created'], 1)
        self.assertEqual(data['existing'], 1)
        # Hakuna duplicate
        self.assertEqual(
            FormStudent.objects.filter(
                school=self.school, first_name='Halima', last_name='Mohamed',
            ).count(), 1,
        )

    def test_save_rejects_empty_and_invalid(self):
        resp = self._post([])
        self.assertEqual(resp.status_code, 400)
        resp = self._post([{'first': '', 'last': 'Hakuna'}])
        self.assertEqual(resp.status_code, 400)
        resp = self._post([{'first': 'Sahihi', 'last': 'Mtu'}], form=99)
        self.assertEqual(resp.status_code, 400)

    def test_save_skips_rows_without_first_name(self):
        resp = self._post([
            {'first': '', 'middle': '', 'last': 'Tupu', 'gender': 'M'},
            {'first': 'Halima', 'middle': '', 'last': 'Mohamed', 'gender': 'F'},
        ])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['saved'], 1)


class RosterScanServiceUnitTests(TestCase):
    """Unit tests za cleaning helpers za service (bila network)."""

    def test_clean_gender(self):
        from .services.roster_scan_service import _clean_gender
        self.assertEqual(_clean_gender('F'), 'F')
        self.assertEqual(_clean_gender('female'), 'F')
        self.assertEqual(_clean_gender('Kike'), 'F')
        self.assertEqual(_clean_gender('M'), 'M')
        self.assertEqual(_clean_gender('kiume'), 'M')
        self.assertEqual(_clean_gender(''), 'M')
        self.assertEqual(_clean_gender(None), 'M')
        self.assertEqual(_clean_gender('garbage'), 'M')

    def test_clean_name(self):
        from .services.roster_scan_service import _clean_name
        self.assertEqual(_clean_name('  Halima   Ally  Mohamed '), 'Halima Ally Mohamed')
        self.assertEqual(_clean_name('12. Juma Hamisi'), 'Juma Hamisi')
        self.assertEqual(_clean_name('3) Aisha J'), 'Aisha J')
        self.assertEqual(_clean_name(''), '')

    def test_extract_dedupes_and_splits_names(self):
        from .services.roster_scan_service import extract_students_from_document
        fake_pages = [object()]  # _load_page_images is mocked; images unused
        ai_text = json.dumps([
            {'row': 1, 'name': 'Halima Ally Mohamed', 'gender': 'F'},
            {'row': 2, 'name': 'Juma Hamisi', 'gender': 'M'},
            {'row': 3, 'name': 'Halima Ally Mohamed', 'gender': 'F'},  # duplicate
            {'row': 4, 'name': 'S/N', 'gender': 'M'},  # header junk — filtered
        ])
        with mock.patch('results.services.roster_scan_service._load_page_images', return_value=fake_pages), \
             mock.patch('results.services.roster_scan_service._read_page_with_ai', return_value=ai_text):
            rows = extract_students_from_document(uploaded_file=None)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['first'], 'Halima')
        self.assertEqual(rows[0]['middle'], 'Ally')
        self.assertEqual(rows[0]['last'], 'Mohamed')
        self.assertEqual(rows[0]['gender'], 'F')
        self.assertEqual(rows[1]['first'], 'Juma')
        self.assertEqual(rows[1]['middle'], '')
        self.assertEqual(rows[1]['last'], 'Hamisi')
