"""Tests za NECTA Continuous Assessment Form (Form IV) automation.

Muhimu zaidi: makadirio yanayoheshimu utendaji (performance-aware) —
mwanafunzi aliye 80-100 HAWEEZI kutiwa 60 kwenye fomu ya C.A.
"""
import json

from django.test import TestCase
from django.urls import reverse

from .models import (
    ContinuousAssessmentSnapshot, Exam, ExamResult, FormStudent, School,
    SchoolSubject, Student, Subject, TeacherAccount,
)
from .services.necta_ca_service import (
    auto_map_exams, build_ca_preview, estimate_mark,
)


class EstimateMarkTests(TestCase):
    """estimate_mark — proportional scaling yenye clamp [min, max]."""

    databases = {'default', 'results'}

    def test_none_stays_none(self):
        self.assertIsNone(estimate_mark(None, 45, 100))

    def test_high_performer_is_never_lowballed(self):
        # Requirement: mwanafunzi wa 80-100 hawezi kutiwa 60.
        for base in (80, 85, 90, 95, 100):
            mark = estimate_mark(base, 45, 100)
            self.assertGreaterEqual(mark, 89, f'base={base} → {mark}')
        self.assertEqual(estimate_mark(100, 45, 100), 100)

    def test_proportional_mapping_endpoints(self):
        self.assertEqual(estimate_mark(0, 45, 100), 45)
        self.assertEqual(estimate_mark(50, 45, 100), 73)   # 72.5 → round-half-up
        self.assertEqual(estimate_mark(80, 45, 100), 89)
        self.assertEqual(estimate_mark(20, 45, 100), 56)

    def test_clamped_to_range(self):
        self.assertEqual(estimate_mark(120, 45, 100), 100)
        self.assertEqual(estimate_mark(-5, 45, 100), 45)


class AutoMapExamsTests(TestCase):
    databases = {'default', 'results'}

    def setUp(self):
        self.school = School.objects.create(name='S', region='R', district='D')
        self.exam = Exam.objects.create(
            school=self.school, name='Mock', year=2026, form=4, exam_type='MOCK',
        )

    def _exam(self, name, exam_type):
        return Exam.objects.create(
            school=self.school, name=name, year=2026, form=4, exam_type=exam_type,
        )

    def test_picks_by_type_without_reuse(self):
        t1 = self._exam('Test 1', 'TEST')
        t2 = self._exam('Test 2', 'TEST')
        mid = self._exam('Midterm', 'MIDTERM')
        term = self._exam('Terminal', 'TERMINAL')
        annual = self._exam('Annual', 'ANNUAL')

        mapping = auto_map_exams([self.exam, t1, t2, mid, term, annual])

        self.assertEqual(mapping['ft_test_one'], t1.id)
        self.assertEqual(mapping['ft_test_two'], t2.id)   # TEST ya pili
        self.assertEqual(mapping['ft_mid_term'], mid.id)
        self.assertEqual(mapping['ft_terminal'], term.id)
        self.assertEqual(mapping['st_annual'], annual.id)
        # PROJECT/PRACTICAL zinabaki wazi — kujaza mkononi.
        self.assertIsNone(mapping['project'])
        self.assertIsNone(mapping['practical'])

    def test_missing_type_leaves_column_blank(self):
        mapping = auto_map_exams([self.exam])
        self.assertIsNone(mapping['ft_test_one'])
        self.assertIsNone(mapping['st_annual'])


class BuildCAPreviewTests(TestCase):
    databases = {'default', 'results'}

    def setUp(self):
        self.school = School.objects.create(name='Sec S', region='R', district='D')
        self.subject = Subject.objects.create(name='HISTORY', level='secondary')
        SchoolSubject.objects.create(school=self.school, subject=self.subject)

        # Roster ya Form 4 + Student records zenye majina yanayolingana.
        self.fs1 = FormStudent.objects.create(
            school=self.school, form=4, admission_no='S001',
            first_name='Asha', middle_name='', last_name='Mkubwa', gender='F',
        )
        self.fs2 = FormStudent.objects.create(
            school=self.school, form=4, admission_no='S002',
            first_name='Juma', middle_name='Hassan', last_name='Mdogo', gender='M',
        )
        self.st1 = Student.objects.create(first_name='Asha', middle_name='', last_name='Mkubwa', gender='F')
        self.st2 = Student.objects.create(first_name='Juma', middle_name='Hassan', last_name='Mdogo', gender='M')

        self.exam = Exam.objects.create(
            school=self.school, name='Terminal', year=2026, form=4, exam_type='TERMINAL',
        )
        ExamResult.objects.create(exam=self.exam, student=self.st1, subject=self.subject, score=80)
        ExamResult.objects.create(exam=self.exam, student=self.st2, subject=self.subject, score=40)

    def test_estimates_track_real_performance(self):
        exam_map = {'ft_terminal': self.exam.id}
        preview = build_ca_preview(self.school, self.subject, exam_map, 45, 100, year=2026)

        rows = {r['name']: r['marks'] for r in preview['rows']}
        asha = rows['Asha Mkubwa']
        juma = rows['Juma Hassan Mdogo']

        # Asha (80 halisi) → 89; Juma (40 halisi) → 67. Performance inaheshimiwa.
        self.assertEqual(asha['ft_terminal'], 89)
        self.assertEqual(juma['ft_terminal'], 67)
        self.assertGreater(asha['ft_terminal'], juma['ft_terminal'])

    def test_blank_column_falls_back_to_combined_average(self):
        # Column zisizo-mapped zinavuta wastani wa columns zilizopo —
        # "combined results mpaka wakati huo".
        exam_map = {'ft_terminal': self.exam.id}
        preview = build_ca_preview(self.school, self.subject, exam_map, 45, 100, year=2026)

        rows = {r['name']: r['marks'] for r in preview['rows']}
        asha = rows['Asha Mkubwa']
        for key in ('ft_test_one', 'ft_mid_term', 'st_annual'):
            self.assertEqual(asha[key], 89, f'{key} inafuata combined average')

    def test_absent_result_excluded(self):
        # ExamResult ya pili (is_absent=True) kwa exam nyingine haipaswi
        # kuingia kwenye combined average wala kuzalisha 0.
        exam2 = Exam.objects.create(
            school=self.school, name='Test One', year=2026, form=4, exam_type='TEST',
        )
        ExamResult.objects.create(
            exam=exam2, student=self.st1, subject=self.subject,
            score=None, is_absent=True,
        )
        exam_map = {'ft_terminal': self.exam.id, 'ft_test_one': exam2.id}
        preview = build_ca_preview(self.school, self.subject, exam_map, 45, 100, year=2026)
        asha = next(r for r in preview['rows'] if r['name'] == 'Asha Mkubwa')
        # 80 ya Terminal bado inatumika, na column ya absent inarudi kwa
        # combined average (80) — si 0, si None.
        self.assertEqual(asha['marks']['ft_terminal'], 89)
        self.assertEqual(asha['marks']['ft_test_one'], 89)
        juma = next(r for r in preview['rows'] if 'Juma' in r['name'])
        self.assertEqual(juma['marks']['ft_terminal'], 67)

    def test_project_and_practical_stay_blank(self):
        exam_map = {'ft_terminal': self.exam.id}
        preview = build_ca_preview(self.school, self.subject, exam_map, 45, 100, year=2026)
        for row in preview['rows']:
            self.assertIsNone(row['marks']['project'])
            self.assertIsNone(row['marks']['practical'])

    def test_student_without_any_marks_stays_blank(self):
        # Mwanafunzi asiye na ExamResult yoyote → columns zote wazi.
        FormStudent.objects.create(
            school=self.school, form=4, admission_no='S003',
            first_name='Neema', middle_name='', last_name='Upya', gender='F',
        )
        exam_map = {'ft_terminal': self.exam.id}
        preview = build_ca_preview(self.school, self.subject, exam_map, 45, 100, year=2026)
        neema = next(r for r in preview['rows'] if 'Neema' in r['name'])
        self.assertTrue(all(v is None for v in neema['marks'].values()))
        self.assertEqual(preview['stats']['blank'], 1)


class NectaCaViewTests(TestCase):
    databases = {'default', 'results'}

    def setUp(self):
        self.school = School.objects.create(
            name='Sec S', region='R', district='D', current_academic_year=2026,
        )
        self.academic = TeacherAccount.objects.create(
            email='academic@example.com', full_name='Academic One',
            role=TeacherAccount.ROLE_ACADEMIC, school=self.school,
        )
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')

        self.subject = Subject.objects.create(name='HISTORY', level='secondary')
        SchoolSubject.objects.create(school=self.school, subject=self.subject)
        self.fs = FormStudent.objects.create(
            school=self.school, form=4, academic_year=2026, admission_no='S001',
            first_name='Asha', middle_name='', last_name='Mkubwa', gender='F',
        )
        self.student = Student.objects.create(first_name='Asha', middle_name='', last_name='Mkubwa', gender='F')
        self.exam = Exam.objects.create(
            school=self.school, name='Terminal', year=2026, form=4, exam_type='TERMINAL',
        )
        ExamResult.objects.create(exam=self.exam, student=self.student, subject=self.subject, score=80)

    def test_form_page_auto_selects_mapped_exams(self):
        resp = self.client.get(reverse('necta_ca_form'))
        self.assertEqual(resp.status_code, 200)
        # Auto-map inapaswa kuwa preselected kwenye dropdown ya TERMINAL.
        self.assertContains(
            resp,
            f'<option value="{self.exam.id}" selected>',
            html=False,
        )

    def test_preview_returns_estimated_marks(self):
        payload = {
            'subject_id': self.subject.id,
            'year': 2026,
            'mark_min': 45,
            'mark_max': 100,
            'exam_ft_terminal': self.exam.id,
        }
        resp = self.client.post(
            reverse('necta_ca_form'), data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['subject_name'], 'HISTORY')
        self.assertEqual(data['rows'][0]['marks']['ft_terminal'], 89)

    def test_download_creates_snapshot_and_excel(self):
        payload = {
            'subject_id': self.subject.id,
            'year': 2026,
            'center_no': 'S3063',
            'phone': '0712345678',
            'mark_min': 45,
            'mark_max': 100,
            'exam_ft_terminal': self.exam.id,
        }
        resp = self.client.post(
            reverse('necta_ca_download'), data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        snap = ContinuousAssessmentSnapshot.objects.get(school=self.school)
        self.assertEqual(snap.subject, self.subject)
        self.assertEqual(snap.params['center_no'], 'S3063')
        self.assertEqual(snap.payload['rows'][0]['marks']['ft_terminal'], 89)
        self.assertEqual(snap.created_by, self.academic)
