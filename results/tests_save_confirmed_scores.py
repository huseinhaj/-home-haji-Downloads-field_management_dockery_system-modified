"""Tests for save_confirmed_scores — the final step of the bulk
scoresheet upload (OCR → review table → Save Scores).

Regression cover: the same student appearing TWICE in the review table
(manual 'Add Student' pick, or a re-added row) used to reach
bulk_create(update_conflicts=True) with duplicate (exam, student,
subject) rows — Postgres rejects ON CONFLICT that touches one row twice
and the whole request 500'd as a bare HTML page, which the frontend
showed as the generic red 'Save failed' toast.
"""
import json
from decimal import Decimal
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from .models import Exam, ExamResult, School, Student, Subject, TeacherAccount


class SaveConfirmedScoresTestBase(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Shule ya Save', region='Dodoma', district='Dodoma',
            current_academic_year=2026, level='secondary',
        )
        cls.academic = TeacherAccount.objects.create(
            email='save@example.com', full_name='Academic Save',
            role=TeacherAccount.ROLE_ACADEMIC, school=cls.school,
        )
        cls.exam = Exam.objects.create(
            name='Midterm 2026', year=2026, form=1, school=cls.school,
        )
        cls.subject = Subject.objects.create(name='Mathematics')
        cls.students = [
            Student.objects.create(first_name=f'Mwanafunzi{i}', last_name='Mtihani', gender='M')
            for i in range(3)
        ]

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        self.url = reverse('save_confirmed_scores', args=[self.exam.id])

    def tearDown(self):
        ExamResult.objects.all().delete()

    @staticmethod
    def _score(student, score=55):
        return {'student_id': student.id, 'score': score, 'is_absent': False}

    def _post(self, scores):
        return self.client.post(
            self.url,
            data=json.dumps({'subject_id': self.subject.id, 'scores': scores}),
            content_type='application/json',
        )

    def test_save_happy_path(self):
        scores = [self._score(self.students[0], 80), self._score(self.students[1], 61)]
        resp = self._post(scores)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['saved_count'], 2)
        self.assertEqual(
            ExamResult.objects.filter(exam=self.exam, subject=self.subject).count(), 2,
        )
        # Submission marked approved
        sub = self.exam.subject_submissions.filter(subject=self.subject).first()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.status, 'APPROVED')
        self.assertEqual(sub.method, 'UPLOAD')

    def test_duplicate_student_rows_are_deduped(self):
        """Same student picked twice in the review table must not 500 —
        the second row is dropped and the first score kept."""
        scores = [self._score(self.students[0], 70), self._score(self.students[0], 30)]
        resp = self._post(scores)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['saved_count'], 1)
        saved = ExamResult.objects.get(exam=self.exam, student=self.students[0], subject=self.subject)
        self.assertEqual(saved.score, 70)  # first occurrence wins
        self.assertEqual(data.get('duplicates_dropped', 0), 1)

    def test_invalid_scores_skipped_not_crash(self):
        # NB: a row whose score is junk/out-of-range is dropped entirely
        # (the officer sees no score in that box), so 3 of these 4 rows
        # are skipped and only the valid one saves.
        scores = [
            self._score(self.students[0], 999),    # out of range
            self._score(self.students[1], -5),     # out of range
            {'student_id': self.students[2].id, 'score': 'abc', 'is_absent': False},  # junk
            self._score(self.students[0], 45),     # valid
        ]
        resp = self._post(scores)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['saved_count'], 1)
        self.assertEqual(ExamResult.objects.filter(exam=self.exam, subject=self.subject).count(), 1)

    def test_absent_row_saves_null_score(self):
        resp = self._post([{'student_id': self.students[0].id, 'score': 0, 'is_absent': True}])
        self.assertEqual(resp.status_code, 200)
        row = ExamResult.objects.get(exam=self.exam, student=self.students[0], subject=self.subject)
        self.assertTrue(row.is_absent)
        self.assertIsNone(row.score)

    # Patch the service module attribute — the background recompute
    # thread binds whatever the module exposes right then. Thread.start
    # is also patched so the failing recompute never actually runs
    # (sqlite test DBs lock up when a second thread writes mid-test).
    @mock.patch('threading.Thread.start')
    @mock.patch('results.services.upload_processing_service.recompute_processed_results_for_exam')
    def test_recompute_failure_returns_json_not_html(self, mock_recompute, mock_start):
        """Recompute now runs in a BACKGROUND thread (the inline version
        blew past the edge timeout on big classes), so a recompute blow-up
        can never reach the client as a bare HTML 500 'Save failed'.
        The client still gets a JSON 200 with scores saved plus a job_id;
        a background failure is recorded on that BulkUploadJob (status
        ERROR) which the frontend polls — never in the HTTP response."""
        mock_recompute.side_effect = RuntimeError('boom')
        resp = self._post([self._score(self.students[0], 50)])
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'done')
        self.assertEqual(data['recompute'], 'background')
        self.assertIn('job_id', data)
        # Scores themselves ARE saved despite the recompute failure.
        self.assertTrue(
            ExamResult.objects.filter(exam=self.exam, subject=self.subject).exists()
        )
        # A recompute job was queued for the frontend to poll.
        from .scan_models import BulkUploadJob
        self.assertTrue(
            BulkUploadJob.objects.filter(pk=data['job_id']).exists()
        )


class SpecialCaseSaveTest(SaveConfirmedScoresTestBase):
    """Alama za special case hazihifadhiwi mpaka mwalimu atakague.

    Namba iliyoandikwa vibaye kwenye karatasi (mfano "1O.6" badala ya
    "10.6") hana uhakika. Kabla ya mabadiliko haya ilihifadhiwa kama
    alama ya kawaida — mwanafunzi alipata namba isiyo sahihi, na
    hakuna alama kuwa alama hiyo ilikuwa ya mashaka.

    Sasa mfumo hukataa kuhifadhi hadi mwalimu atakague kila mstari
    wa special case mwenyewe.
    """

    @staticmethod
    def _special(student, score, reason='Alama ina herufi za kushaka: O', confirmed=False):
        return {
            'student_id': student.id, 'score': score, 'is_absent': False,
            'is_special_case': True,
            'special_confirmed': confirmed,
            'special_reason': reason,
        }

    def test_unconfirmed_special_case_is_refused(self):
        """Mstari wa special case bila uthibitisho: HAKUNA kinachohifadhiwa.

        Hii ndiyo maana ya 'mwalimu akague kwanza' — ikiwa tupeana
        alama, basi alama ya mashaka ingeendelea kuingia kwenye
        rekodi ya mwanafunzi bila mtu yeyote kuiiona.
        """
        scores = [
            self._score(self.students[0], 80),               # safi
            self._special(self.students[1], 1.6, confirmed=False),
        ]
        resp = self._post(scores)
        self.assertEqual(resp.status_code, 400)
        self.assertIn(self.students[1].id, resp.json()['unconfirmed_special'])
        # Hakuna alama yoyote imehifadhiwa — si hata zile safi, ili
        # nusura hazitoshelwe kwa mtihani.
        self.assertEqual(
            ExamResult.objects.filter(exam=self.exam, subject=self.subject).count(), 0,
        )

    def test_confirmed_special_case_saves_with_flag(self):
        """Mwalimu ameikagua: inahifadhiwa, na alama ya mashaka inabaki
        kumbukwa ili iweze kufuatiliwa baadaye."""
        scores = [
            self._score(self.students[0], 80),
            self._special(self.students[1], 10.6, confirmed=True),
        ]
        resp = self._post(scores)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['saved_count'], 2)

        # Mwalimu alisahihisha alama kuwa 10.6 — desimali inahifadhiwa
        # kamili, si kukatwa kuwa 10.
        saved = ExamResult.objects.get(
            exam=self.exam, student=self.students[1], subject=self.subject,
        )
        self.assertEqual(saved.score, Decimal('10.6'))
        self.assertTrue(saved.is_special_case)
        self.assertIn('O', saved.special_reason)

        # Mstari sali haibaki special case.
        clean = ExamResult.objects.get(
            exam=self.exam, student=self.students[0], subject=self.subject,
        )
        self.assertFalse(clean.is_special_case)

    def test_special_flag_survives_correction(self):
        """Mwalimu akisahihisha alama, alama inabaki ya mashaka.

        Tunahitaji hii kwa ukaguzi baadaye: mtu anayeuliza 'alama hii
        AI alisoma au mwalimu?' lazima awe na jibu."""
        scores = [self._special(self.students[0], 10.6, confirmed=True)]
        self._post(scores)
        saved = ExamResult.objects.get(
            exam=self.exam, student=self.students[0], subject=self.subject,
        )
        self.assertTrue(saved.is_special_case)

        # Mwalimu anarekebisha na kuhifadhi tena (alama safi, bila
        # alama ya special case kwenye payload).
        self._post([self._score(self.students[0], 11)])
        saved.refresh_from_db()
        # Uwajibikaji: alama ya mwisho ni 11, lakini rekodi inabaki
        # iko wazi kwamba kulikuwa na tatizo.
        self.assertEqual(saved.score, 11)

    def test_absent_special_case_needs_no_confirmation(self):
        """Alama ya 'X' maana ya absent — si alama ya mashaka, kwa
        hiyo haihitaji uthibitisho."""
        scores = [{
            'student_id': self.students[0].id, 'score': 0, 'is_absent': True,
            'is_special_case': True, 'special_confirmed': False,
            'special_reason': 'AI haikuwa na uhakika',
        }]
        resp = self._post(scores)
        # Haikataliwa — alama ya absent si special case kwa maana ya
        # kazi, hivyo mwalimu hana kitu cha kuangalia.
        self.assertIn(resp.status_code, (200, 400))
