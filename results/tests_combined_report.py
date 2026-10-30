"""Tests za ripoti ya muhula — wastani wa mitihani miwili kwenye report card.

Data iliyohifadhiwa (ExamResult/ProcessedResult) HAIBADILISHWI; wastani
hupatikana tu kwenye payload ya PDF (combined_report_service.py).
"""
from datetime import date

from django.test import TestCase

from .models import Exam, ExamResult, ProcessedResult, School, Student, Subject
from .services.combined_report_service import (
    build_combined_payload,
    find_partner_exam,
)
from .services.pdf_export_service import generate_student_result_pdf_response


class CombinedReportTests(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Sekondari Muhula', region='Dodoma', district='Dodoma',
            level='secondary', current_academic_year=2026,
        )
        cls.sep = Exam.objects.create(
            name='Midterm Septemba', year=2026, form=4, school=cls.school,
            exam_type='MIDTERM', date=date(2026, 9, 15),
        )
        cls.dec = Exam.objects.create(
            name='Terminal Desemba', year=2026, form=4, school=cls.school,
            exam_type='TERMINAL', date=date(2026, 12, 5),
        )
        cls.march = Exam.objects.create(
            name='Midterm Machi', year=2026, form=4, school=cls.school,
            exam_type='MIDTERM', date=date(2026, 3, 10),
        )
        cls.june = Exam.objects.create(
            name='Terminal Juni', year=2026, form=4, school=cls.school,
            exam_type='TERMINAL', date=date(2026, 6, 20),
        )
        cls.unpaired = Exam.objects.create(
            name='Test Mei', year=2026, form=4, school=cls.school,
            exam_type='TEST', date=date(2026, 5, 10),
        )

        cls.student_a = Student.objects.create(
            first_name='Amina', middle_name='', last_name='Juma', gender='F',
        )
        cls.student_b = Student.objects.create(
            first_name='Baraka', middle_name='', last_name='Mushi', gender='M',
        )
        cls.subjects = [
            Subject.objects.create(name=name, level='secondary')
            for name in (
                'Mathematics', 'English Language', 'Kiswahili', 'Biology',
                'Chemistry', 'Physics', 'Geography',
            )
        ]

    def _seed(self, exam, scores_a, scores_b):
        for subject, score_a, score_b in zip(self.subjects, scores_a, scores_b):
            ExamResult.objects.create(
                exam=exam, student=self.student_a, subject=subject, score=score_a,
            )
            ExamResult.objects.create(
                exam=exam, student=self.student_b, subject=subject, score=score_b,
            )

    def test_find_partner_september_matches_december(self):
        self._seed(self.sep, [60] * 7, [40] * 7)
        self._seed(self.dec, [80] * 7, [60] * 7)
        self.assertEqual(find_partner_exam(self.sep), self.dec)
        self.assertEqual(find_partner_exam(self.dec), self.sep)

    def test_find_partner_march_matches_june(self):
        self._seed(self.march, [60] * 7, [40] * 7)
        self._seed(self.june, [80] * 7, [60] * 7)
        self.assertEqual(find_partner_exam(self.march), self.june)
        self.assertEqual(find_partner_exam(self.june), self.march)

    def test_no_partner_for_unpaired_month(self):
        self._seed(self.unpaired, [60] * 7, [40] * 7)
        self.assertIsNone(find_partner_exam(self.unpaired))
        self.assertIsNone(build_combined_payload(self.unpaired))

    def test_combined_scores_are_average_of_both_exams(self):
        self._seed(self.sep, [60] * 7, [40] * 7)
        self._seed(self.dec, [80] * 7, [60] * 7)

        payload = build_combined_payload(self.sep)
        self.assertIsNotNone(payload)
        maths = self.subjects[0]
        self.assertEqual(
            payload['scores_by_student'][self.student_a.id][maths.id], 70,
        )
        self.assertEqual(
            payload['scores_by_student'][self.student_b.id][maths.id], 50,
        )

        summary_a = payload['summary_by_student'][self.student_a.id]
        summary_b = payload['summary_by_student'][self.student_b.id]
        self.assertEqual(summary_a['total_score'], 490)
        self.assertEqual(summary_a['average_score'], 70)
        self.assertEqual(summary_a['points'], 14)
        self.assertEqual(summary_a['division'], 'I')
        self.assertEqual(summary_a['position'], 1)
        self.assertEqual(summary_b['total_score'], 350)
        self.assertEqual(summary_b['average_score'], 50)
        self.assertEqual(summary_b['points'], 21)
        self.assertEqual(summary_b['division'], 'II')
        self.assertEqual(summary_b['position'], 2)

    def test_subject_only_in_one_exam_uses_that_score(self):
        # Physics haipo kwenye mtihani wa Septemba — wastani unatumia
        # alama ya Desemba pekee, sio sifuri.
        for subject, score in zip(self.subjects[:6], [60] * 6):
            ExamResult.objects.create(
                exam=self.sep, student=self.student_a, subject=subject, score=score,
            )
        for subject, score in zip(self.subjects, [80] * 7):
            ExamResult.objects.create(
                exam=self.dec, student=self.student_a, subject=subject, score=score,
            )
        payload = build_combined_payload(self.sep)
        physics = self.subjects[6]
        self.assertEqual(
            payload['scores_by_student'][self.student_a.id][physics.id], 80,
        )

    def test_stored_processed_results_are_not_modified(self):
        self._seed(self.sep, [60] * 7, [40] * 7)
        self._seed(self.dec, [80] * 7, [60] * 7)
        stored = ProcessedResult.objects.create(
            exam=self.sep, student=self.student_a,
            total_score=420, average_score=60, points=17, division='II', position=1,
        )
        build_combined_payload(self.sep)
        stored.refresh_from_db()
        self.assertEqual(stored.total_score, 420)
        self.assertEqual(stored.average_score, 60)
        self.assertEqual(stored.division, 'II')

    def test_report_card_download_renders_combined_slip(self):
        self._seed(self.sep, [60] * 7, [40] * 7)
        self._seed(self.dec, [80] * 7, [60] * 7)
        result = ProcessedResult.objects.create(
            exam=self.sep, student=self.student_a,
            total_score=420, average_score=60, points=17, division='II', position=1,
        )
        resp = generate_student_result_pdf_response(result)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.getvalue().startswith(b'%PDF'))

    def test_combine_zero_disables_combination(self):
        self._seed(self.sep, [60] * 7, [40] * 7)
        self._seed(self.dec, [80] * 7, [60] * 7)
        result = ProcessedResult.objects.create(
            exam=self.sep, student=self.student_a,
            total_score=420, average_score=60, points=17, division='II', position=1,
        )

        class _Req:
            GET = {'combine': '0'}

        resp = generate_student_result_pdf_response(result, request=_Req)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.getvalue().startswith(b'%PDF'))
