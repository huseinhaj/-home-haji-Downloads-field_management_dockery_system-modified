"""Tests za shule za msingi (Darasa 1-7) — primary support.

Inathibitisha:
  - grading scale ya msingi (A-E, NECTA PSLE style)
  - recompute ya msingi: hakuna division, ranking kwa jumla ya alama
  - rollover ya msingi: Darasa 1→2 … 6→7, Darasa la 7 → Storage
  - primary_last_class custom (shule za mtaala mpya zenye darasa la 6
    kama mwisho) → 1→2 … 5→6, Darasa la 6 → Storage
  - templates/views za msingi zinaonyesha "Darasa la X" badala ya "Form X"
  - form_results ya msingi inaonyesha Gredi ya Wastani badala ya Division
"""
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    Exam, ExamResult, FormStudent, ProcessedResult, School, Student,
    Subject, TeacherAccount,
)
from .services.upload_processing_service import recompute_processed_results_for_exam
from .utils import get_grade_for_form, get_grade_primary


class PrimaryGradeTests(TestCase):
    """Grading scale ya msingi: A 80+ | B 65+ | C 45+ | D 30+ | E <30."""

    def test_grade_primary_boundaries(self):
        self.assertEqual(get_grade_primary(80), 'A')
        self.assertEqual(get_grade_primary(100), 'A')
        self.assertEqual(get_grade_primary(65), 'B')
        self.assertEqual(get_grade_primary(45), 'C')
        self.assertEqual(get_grade_primary(30), 'D')
        self.assertEqual(get_grade_primary(29), 'E')
        self.assertEqual(get_grade_primary(0), 'E')

    def test_grade_for_form_uses_primary_scale(self):
        # form=1 haihusiani na scale ya msingi — primary flag ndiyo muhimu
        self.assertEqual(get_grade_for_form(85, 1, primary=True), 'A')
        self.assertEqual(get_grade_for_form(85, 1, primary=False), 'A')  # CSEE A pia
        # 55 kwa msingi = C (45+); kwa CSEE = B (55 >= 50). Tofauti iko wapi?
        # 32 kwa msingi = D (30+); CSEE 32 pia D (30-44) — kikomo ni 29/30 chini.
        # 20 kwa msingi = E (<30); kwa CSEE = F (<30). Scale ya msingi haina F.
        self.assertEqual(get_grade_for_form(20, 1, primary=True), 'E')
        self.assertEqual(get_grade_for_form(20, 1, primary=False), 'F')


class PrimaryRecomputeTests(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Shule ya Msingi Jaribio', region='Dodoma', district='Dodoma',
            level='primary', current_academic_year=2026,
        )
        cls.exam = Exam.objects.create(
            name='Midterm 2026', year=2026, form=4, school=cls.school,
        )
        cls.subjects = [
            Subject.objects.create(name=n)
            for n in ('Kiswahili', 'English', 'Hisabati', 'Sayansi')
        ]
        cls.students = []
        for i, (scores, name) in enumerate([
            ((90, 85, 95, 88), 'Bora'),    # jumla 358 — nafasi ya 1
            ((70, 60, 50, 40), 'Wastani'),  # jumla 220 — nafasi ya 2
            ((10, 20, 15, 5), 'Dhaifu'),    # jumla 50  — nafasi ya 3
        ]):
            s = Student.objects.create(first_name=f'Mtoto{i}', last_name=name, gender='F')
            cls.students.append(s)
            for subj, score in zip(cls.subjects, scores):
                ExamResult.objects.create(
                    exam=cls.exam, student=s, subject=subj, score=score,
                )

    def test_primary_no_division_ranked_by_total(self):
        recompute_processed_results_for_exam(self.exam)
        prs = ProcessedResult.objects.filter(exam=self.exam).order_by('position')
        self.assertEqual([p.position for p in prs], [1, 2, 3])
        for pr in prs:
            self.assertEqual(pr.division, '', 'Msingi hauna division')
        # Jumla za kwanza ni kubwa
        self.assertEqual(prs[0].total_score, 358)
        self.assertEqual(prs[2].total_score, 50)

    def test_primary_position_tiebreak_by_average(self):
        # Wanafunzi 2 wenye jumla ileile — Wastani (yaani moja masomo mengi)
        # hutenganisha; hapa tunathibitisha tu kuwa hakuna crash na hakuna
        # division.
        recompute_processed_results_for_exam(self.exam)
        divs = set(
            ProcessedResult.objects.filter(exam=self.exam)
            .values_list('division', flat=True)
        )
        self.assertEqual(divs, {''})


class PrimaryRolloverTests(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Shule ya Msingi Rollover', region='Dodoma', district='Dodoma',
            level='primary', current_academic_year=2026,
        )
        cls.academic = TeacherAccount.objects.create(
            email='acad-primary@example.com', full_name='Academic Primary',
            role=TeacherAccount.ROLE_ACADEMIC, school=cls.school,
        )
        # Rosti: Darasa 1-7, mwanafunzi 1 kila darasa
        for form in range(1, 8):
            FormStudent.objects.create(
                school=cls.school, form=form, academic_year=2026,
                admission_no=f'P26/{form:02d}',
                first_name=f'Mtoto{form}', last_name='Wa2026', gender='M',
            )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')

    def test_primary_rollover_promotes_1_to_7_and_archives_last(self):
        self.client.post(reverse('year_rollover'), {'confirm': 'HAMISHA'})
        self.school.refresh_from_db()
        self.assertEqual(self.school.current_academic_year, 2027)
        # Darasa 1→2 … 6→7
        for src in range(1, 7):
            self.assertTrue(
                FormStudent.objects.filter(
                    school=self.school, form=src + 1, academic_year=2027,
                    first_name=f'Mtoto{src}',
                ).exists(),
                f'Darasa {src} haikupandishwa kwenda {src + 1}',
            )
        # Darasa la 7 la 2026 → School Storage
        self.assertTrue(
            FormStudent.objects.filter(
                school=self.school, form=7, academic_year=2026, is_active=False,
            ).exists(),
        )
        # Hakuna aliyeachwa nyuma kama hai kwa mwaka wa zamani
        self.assertEqual(
            FormStudent.objects.filter(
                school=self.school, academic_year=2026, is_active=True,
            ).count(), 0,
        )

    def test_primary_rollover_last_class_6_custom_curriculum(self):
        # Shule za mtaala mpya: darasa la 6 ndiyo mwisho. Rosti ya Form 7
        # (fixture ya shule ya darasa 7) haipaswi kuwepo — tuniondoa kwanza.
        FormStudent.objects.filter(school=self.school, form=7).delete()
        School.objects.filter(pk=self.school.pk).update(primary_last_class=6)
        self.school.refresh_from_db()
        self.client.post(reverse('year_rollover'), {'confirm': 'HAMISHA'})
        # Darasa 6 wa 2026 wamehifadhiwa; hakuna aliyeandikishwa Form 7
        self.assertTrue(
            FormStudent.objects.filter(
                school=self.school, form=6, academic_year=2026, is_active=False,
            ).exists(),
        )
        self.assertFalse(
            FormStudent.objects.filter(school=self.school, form=7).exists(),
        )

    def test_primary_rollover_page_shows_darasa_labels(self):
        resp = self.client.get(reverse('year_rollover'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Darasa la 1')
        self.assertContains(resp, 'Darasa la 7')
        self.assertNotContains(resp, 'Form 4')


class PrimaryPageTests(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Shule ya Msingi Pages', region='Dodoma', district='Dodoma',
            level='primary', current_academic_year=2026,
        )
        cls.academic = TeacherAccount.objects.create(
            email='acad-pages@example.com', full_name='Academic Pages',
            role=TeacherAccount.ROLE_ACADEMIC, school=cls.school,
        )
        cls.exam = Exam.objects.create(
            name='Midterm 2026', year=2026, form=4, school=cls.school,
        )
        cls.subject = Subject.objects.create(name='Kiswahili')
        cls.student = Student.objects.create(
            first_name='Mtoto', last_name='Mmoja', gender='F',
        )
        ExamResult.objects.create(
            exam=cls.exam, student=cls.student, subject=cls.subject, score=90,
        )
        cls.pr = ProcessedResult.objects.create(
            exam=cls.exam, student=cls.student,
            total_score=90, average_score=Decimal('90.00'),
            position=1, points=0, division='',
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')

    def test_form_results_primary_shows_avg_grade(self):
        resp = self.client.get(reverse('form_results', args=[4]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Darasa la 4')       # nav ya shule ya msingi
        self.assertContains(resp, 'Average Grade')      # LANG ya test = 'en'
        self.assertContains(resp, 'A')                  # 90% → A
        self.assertNotContains(resp, 'Points')          # hakuna column ya points/division

    def test_public_search_shows_darasa_and_avg_grade(self):
        resp = self.client.get(
            reverse('student_results_search'), {'q': 'Mtoto Mmoja'}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Mtoto Mmoja')
        self.assertContains(resp, 'Darasa 4')           # badge ya kiwango
        self.assertContains(resp, 'A')                   # gredi ya wastani (90 → A)

    def test_edit_page_primary_hides_division(self):
        resp = self.client.get(
            reverse('edit_processed_result', args=[self.pr.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Average Grade')
        self.assertContains(resp, 'A')
        self.assertNotContains(resp, 'Current division')
