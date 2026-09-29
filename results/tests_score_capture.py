"""Capture Scores: karatasi zilizosahihishwa kwenye ADF → reg no + alama → Marks Entry."""
import io
import json
import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .bridge_models import SahishiBridge, ScanJob
from .models import Exam, FormStudent, School, Student, Subject, TeacherAccount
from .services.score_capture import build_capture_payload, norm_reg

ROSTER = [
    {'id': 1, 'name': 'Asha Kimaro'},
    {'id': 2, 'name': 'Baraka Mushi'},
    {'id': 3, 'name': 'Neema John'},
]
REG_MAP = {norm_reg('S0451/0001'): 1, norm_reg('S0451/0002'): 2, norm_reg('S0451/0003'): 3}


def _read(reg='', name='', score='50', **extra):
    return {'has_header': True, 'reg_number': reg, 'student_name': name,
            'score': score, 'max_score': None, 'unclear': False, **extra}


def _payload(*reads):
    return build_capture_payload(
        [{'page': i + 1, 'read': r} for i, r in enumerate(reads)], ROSTER, REG_MAP,
    )


class BuildCapturePayloadTests(SimpleTestCase):

    def test_reg_number_matches_even_with_different_separators(self):
        p = _payload(_read('s0451-0002', score='67.5'))
        m = p['matched'][0]
        self.assertEqual((m['id'], m['score'], m['confidence']), (2, 67.5, 1.0))
        self.assertFalse(m['is_special_case'])
        self.assertEqual([x['id'] for x in p['missing']], [1, 3])

    def test_reg_suffix_only_is_matched_but_low_confidence(self):
        m = _payload(_read('0003'))['matched'][0]
        self.assertEqual(m['id'], 3)
        self.assertLess(m['confidence'], 0.9)

    def test_name_fallback_is_flagged_special_case(self):
        m = _payload(_read('XX999', 'Asha Kimaro'))['matched'][0]
        self.assertEqual(m['id'], 1)
        self.assertTrue(m['is_special_case'])
        self.assertIn('jina', m['special_reason'])

    def test_unknown_paper_goes_to_unmatched_with_page(self):
        p = _payload(_read('Z1', 'Mtu Mwingine', '40'))
        self.assertEqual(p['matched'], [])
        self.assertEqual(p['unmatched'][0]['page'], 1)
        self.assertEqual(len(p['missing']), 3)

    def test_second_paper_for_same_student_is_not_used(self):
        p = _payload(_read('S0451/0001', score='40'), _read('S0451/0001', score='90'))
        self.assertEqual([m['score'] for m in p['matched']], [40])
        self.assertEqual(len(p['unmatched']), 1)
        self.assertTrue(any('mbili' in w for w in p['warnings']))

    def test_inner_pages_and_ai_failures_are_reported(self):
        p = build_capture_payload([
            {'page': 1, 'read': _read('S0451/0001')},
            {'page': 2, 'read': {'has_header': False}},
            {'page': 3, 'read': None},
        ], ROSTER, REG_MAP)
        self.assertEqual(len(p['matched']), 1)
        self.assertEqual(len(p['warnings']), 2)

    def test_unclear_or_out_of_fifty_marks_are_special_cases(self):
        p = _payload(
            _read('S0451/0001', score='38', max_score='50'),
            _read('S0451/0002', score='7?', unclear=True, unclear_reason='tarakimu ya pili'),
        )
        a, b = p['matched']
        self.assertTrue(a['is_special_case'])
        self.assertIn('50', a['special_reason'])
        self.assertTrue(b['is_special_case'])
        self.assertIn('tarakimu', b['special_reason'])

    def test_score_is_kept_as_written(self):
        m = _payload(_read('S0451/0001', score='45/100'))['matched'][0]
        self.assertEqual(m['score'], 45)
        self.assertEqual(m['raw_mark'], '45/100')


def _png():
    buf = io.BytesIO()
    Image.new('RGB', (20, 20), 'white').save(buf, format='PNG')
    return buf.getvalue()


class CaptureFlowTests(TestCase):
    """Mwalimu → ScanJob CAPTURE → bridge claim/upload → status inarudisha matched."""

    databases = {'default', 'results'}

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)

        self.school = School.objects.create(name='Mfano Sekondari', region='Dodoma', district='Dodoma')
        self.exam = Exam.objects.create(name='Terminal', year=2026, form=4, school=self.school)
        self.subject = Subject.objects.create(name='History')
        self.teacher = TeacherAccount.objects.create(
            email='t@example.com', full_name='Mwalimu', role=TeacherAccount.ROLE_TEACHER,
            school=self.school)
        self.teacher.subjects.set([self.subject])
        FormStudent.objects.create(
            school=self.school, form=4, first_name='Asha', last_name='Kimaro', gender='F',
            academic_year=2026, admission_no='S0451/0001')
        FormStudent.objects.create(
            school=self.school, form=4, first_name='Baraka', last_name='Mushi', gender='M',
            academic_year=2026, admission_no='S0451/0002')
        self.asha = Student.objects.create(first_name='Asha', last_name='Kimaro', gender='F')
        self.baraka = Student.objects.create(first_name='Baraka', last_name='Mushi', gender='M')
        self.bridge = SahishiBridge.objects.create(school=self.school, name='Ofisi')

        self.client = Client()
        self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')
        self.bridge_client = Client(HTTP_AUTHORIZATION=f'Bearer {self.bridge.token}')

    def _start(self, **extra):
        roster = [{'id': self.asha.id, 'name': 'Asha Kimaro'},
                  {'id': self.baraka.id, 'name': 'Baraka Mushi'}]
        data = {'exam_id': self.exam.id, 'subject_id': self.subject.id,
                'roster': json.dumps(roster), 'pages': 10, **extra}
        return self.client.post(reverse('bridge_capture_start'), data)

    def test_full_capture_flow(self):
        resp = self._start()
        self.assertEqual(resp.status_code, 200, resp.content)
        job_id = resp.json()['job_id']

        status = self.client.get(reverse('bridge_capture_status', args=[job_id])).json()
        self.assertEqual(status['status'], 'processing')

        claim = self.bridge_client.post(reverse('bridge_claim')).json()['job']
        self.assertEqual((claim['id'], claim['mode']), (job_id, 'CAPTURE'))

        reads = [
            {'has_header': True, 'reg_number': 'S0451/0002', 'student_name': 'Baraka',
             'score': '81', 'max_score': None, 'unclear': False},
            {'has_header': False},
        ]
        with mock.patch('results.services.score_capture.read_paper_header', side_effect=reads):
            up = self.bridge_client.post(
                reverse('bridge_upload', args=[job_id]),
                {'images': [SimpleUploadedFile('a.png', _png(), 'image/png'),
                            SimpleUploadedFile('b.png', _png(), 'image/png')]},
            )
        self.assertEqual(up.status_code, 200, up.content)

        done = self.client.get(reverse('bridge_capture_status', args=[job_id])).json()
        self.assertEqual(done['status'], 'done')
        self.assertEqual([(m['id'], m['score']) for m in done['matched']], [(self.baraka.id, 81)])
        self.assertEqual([m['id'] for m in done['missing']], [self.asha.id])

        page = self.client.get(reverse('bridge_capture_page', args=[job_id, 1]))
        self.assertEqual(page.status_code, 200)

    def test_school_without_bridge_gets_a_clear_error(self):
        self.bridge.delete()
        resp = self._start()
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Bridge', resp.json()['error'])

    def test_teacher_of_another_school_cannot_read_the_job(self):
        job_id = self._start().json()['job_id']
        other_school = School.objects.create(name='Nyingine', region='Dodoma', district='Dodoma')
        other = TeacherAccount.objects.create(
            email='o@example.com', full_name='Mwingine', role=TeacherAccount.ROLE_TEACHER,
            school=other_school)
        c = Client()
        c.force_login(other, backend='results.backends.ResultsAuthBackend')
        self.assertEqual(c.get(reverse('bridge_capture_status', args=[job_id])).status_code, 404)
        self.assertEqual(c.get(reverse('bridge_capture_page', args=[job_id, 1])).status_code, 404)

    def test_pending_job_can_be_cancelled_but_not_after_claim(self):
        job_id = self._start().json()['job_id']
        self.assertEqual(
            self.client.post(reverse('bridge_capture_cancel', args=[job_id])).status_code, 200)
        self.assertEqual(ScanJob.objects.get(pk=job_id).status, ScanJob.Status.CANCELLED)
        # Kazi iliyoghairiwa haichukuliwi na bridge
        self.assertIsNone(self.bridge_client.post(reverse('bridge_claim')).json()['job'])

        job2 = self._start().json()['job_id']
        self.bridge_client.post(reverse('bridge_claim'))
        self.assertEqual(
            self.client.post(reverse('bridge_capture_cancel', args=[job2])).status_code, 409)
