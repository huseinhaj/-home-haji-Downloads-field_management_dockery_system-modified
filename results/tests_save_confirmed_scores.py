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
