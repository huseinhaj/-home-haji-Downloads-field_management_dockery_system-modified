"""Tests za QR Result Verification — slips zenye QR, public verify page."""
import io
import re

from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    Exam, ExamResult, ProcessedResult, ResultVerificationToken,
    School, Student, Subject, TeacherAccount,
)
from .services.pdf_export_service import _build_student_result_pdf_bytes


class ResultVerificationTests(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Sekondari QR', region='Dodoma', district='Dodoma',
            level='secondary', current_academic_year=2026,
        )
        cls.teacher = TeacherAccount.objects.create(
            email='qr@sekondari.ac.tz', full_name='Mwalimu QR',
            role='TEACHER', school=cls.school,
        )
        cls.exam = Exam.objects.create(
            name='Terminal 2026', year=2026, form=4, school=cls.school,
            exam_type='TERMINAL',
        )
        cls.student = Student.objects.create(
            first_name='Amina', middle_name='', last_name='Juma', gender='F',
        )
        cls.maths = Subject.objects.create(name='Mathematics', level='secondary')
        cls.biology = Subject.objects.create(name='Biology', level='secondary')
        ExamResult.objects.create(exam=cls.exam, student=cls.student, subject=cls.maths, score=80)
        ExamResult.objects.create(exam=cls.exam, student=cls.student, subject=cls.biology, score=65)
        cls.result = ProcessedResult.objects.create(
            exam=cls.exam, student=cls.student,
            total_score=145, average_score=72.5,
            points=3, division='II', position=1,
        )

    def test_slip_pdf_contains_qr_and_creates_token(self):
        """Slip PDF ina QR (image XObject) + token inaundwa wastaharabu."""
        buf = _build_student_result_pdf_bytes(self.result)
        pdf_bytes = buf.getvalue()
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
        token = ResultVerificationToken.active_for(self.result)
        self.assertIsNotNone(token)
        self.assertGreaterEqual(len(token.token), 40)
        # PDF ina image XObject (QR PNG)
        self.assertIn(b'/Subtype /Image', pdf_bytes)

    def test_verify_page_shows_real_results(self):
        """Scan ya QR → ukurasa wa public unaonyesha matokeo halisi."""
        vt = ResultVerificationToken.objects.create(result=self.result)
        resp = self.client.get(reverse('result_verify', args=[vt.token]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('AMINA JUMA', content)   # template ina-UPPERCASE
        self.assertIn('Mathematics', content)
        self.assertIn('80', content)
        self.assertIn('72.50', content)
        # Scan tracking inafanya kazi
        vt.refresh_from_db()
        self.assertEqual(vt.scan_count, 1)

    def test_invalid_token_shows_not_found(self):
        resp = self.client.get(reverse('result_verify', args=['bogus-token-123456789012345678901234567890']))
        self.assertEqual(resp.status_code, 404)
        self.assertIn('haithibitishwi', resp.content.decode())

    def test_revoked_token_shows_replaced_notice(self):
        """Token iliyobadilishwa (regenerate) → 'slip imebadilishwa'."""
        vt = ResultVerificationToken.objects.create(result=self.result, revoked=True)
        resp = self.client.get(reverse('result_verify', args=[vt.token]))
        self.assertEqual(resp.status_code, 410)
        self.assertIn('imebadilishwa', resp.content.decode())

    def test_regenerate_revokes_old_and_creates_new(self):
        self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')
        old = ResultVerificationToken.objects.create(result=self.result)
        resp = self.client.post(reverse('result_verify_regenerate', args=[self.result.id]))
        self.assertIn(resp.status_code, (200, 302))
        old.refresh_from_db()
        self.assertTrue(old.revoked)
        new = ResultVerificationToken.active_for(self.result)
        self.assertIsNotNone(new)
        # Token mpya tofauti (ya zamani imekuwa revoked)
        self.assertNotEqual(new.token, old.token)
        self.assertFalse(new.revoked)

    def test_regenerate_requires_login_and_own_school(self):
        other_teacher = TeacherAccount.objects.create(
            email='other@x.tz', full_name='Other', role='TEACHER',
        )
        ResultVerificationToken.objects.create(result=self.result)
        c = Client()
        # Bila login → 302/403
        resp = c.post(reverse('result_verify_regenerate', args=[self.result.id]))
        self.assertIn(resp.status_code, (302, 403))
        # Mwalimu wa shule nyingine → 404
        c.force_login(other_teacher, backend='results.backends.ResultsAuthBackend')
        resp = c.post(reverse('result_verify_regenerate', args=[self.result.id]))
        self.assertEqual(resp.status_code, 404)
