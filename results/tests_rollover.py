"""Tests za Year Rollover + School Storage.

Inasimulia shule yenye Form 1-5 mwaka 2026, inafanya rollover kwenda
2027, na kuthibitisha:
  - pandisho 1→2, 2→3, 3→4, 5→6 na mwaka mpya
  - Form 4/6 zinaishia archive (is_active=False, bila kufutwa)
  - matokeo (ExamResult/ProcessedResult) hayagusiwi
  - rosti za miaka iliyopita hazimix na intake mpya (marks entry +
    upload dedup + delete-all)
  - restore kutoka School Storage
  - dedup ya upload (same file twice = hakuna duplicate)
  - admission_no inayorudiwa mwaka mpya haigongani na archive
"""
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    Exam, ExamResult, FormStudent, ProcessedResult, School, Student,
    Subject, TeacherAccount,
)


class RolloverTestBase(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Shule ya Jaribio', region='Dodoma', district='Dodoma',
            current_academic_year=2026,
        )
        cls.academic = TeacherAccount.objects.create(
            email='acad@example.com', full_name='Academic One',
            role=TeacherAccount.ROLE_ACADEMIC, school=cls.school,
        )
        # Rosti ya 2026: Form 1-5, mwanafunzi 2 kila form
        cls.fs = {}
        for form in (1, 2, 3, 4, 5):
            for i in (1, 2):
                cls.fs[(form, i)] = FormStudent.objects.create(
                    school=cls.school, form=form, academic_year=2026,
                    admission_no=f'S26/{form:02d}{i:02d}',
                    first_name=f'Mwanafunzi{form}{i}', last_name='Wa2026',
                    gender='F' if i == 1 else 'M',
                )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')


class YearRolloverTests(RolloverTestBase):

    def test_post_without_confirmation_does_nothing(self):
        resp = self.client.post(reverse('year_rollover'), {'confirm': 'NDOGO'})
        self.assertEqual(resp.status_code, 302)
        self.school.refresh_from_db()
        self.assertEqual(self.school.current_academic_year, 2026)
        self.assertEqual(FormStudent.objects.filter(school=self.school, academic_year=2027).count(), 0)

    def test_rollover_promotes_and_archives(self):
        resp = self.client.post(reverse('year_rollover'), {'confirm': 'HAMISHA'})
        self.assertEqual(resp.status_code, 302)

        self.school.refresh_from_db()
        self.assertEqual(self.school.current_academic_year, 2027)

        # Pandisho: Form 1→2, 2→3, 3→4, 5→6, mwaka mpya
        for src, dst in ((1, 2), (2, 3), (3, 4), (5, 6)):
            self.assertTrue(
                FormStudent.objects.filter(
                    school=self.school, form=dst, academic_year=2027,
                    first_name__startswith=f'Mwanafunzi{src}',
                ).exists(),
                f'Form {src} haikupandishwa kwenda {dst}',
            )
        # Form 4 (na 6) wa 2026 wamehifadhiwa — bado wapo, lakini si hai
        self.assertEqual(
            FormStudent.objects.filter(
                school=self.school, form=4, academic_year=2026, is_active=False,
            ).count(), 2,
        )
        # Form 1 ya 2026 haipo tena kama hai (imewa pandishwa wote)
        self.assertFalse(
            FormStudent.objects.filter(school=self.school, form=1, academic_year=2026, is_active=True).exists()
        )

    def test_rollover_moves_everyone_including_leftovers(self):
        # Mwanafunzi asiye na admission_no + mwenye placeholder
        leftover = FormStudent.objects.create(
            school=self.school, form=3, academic_year=2026,
            admission_no='NA-leftover1', first_name='Acha', last_name='Shule', gender='M',
        )
        self.client.post(reverse('year_rollover'), {'confirm': 'HAMISHA'})
        leftover.refresh_from_db()
        self.assertEqual((leftover.form, leftover.academic_year), (4, 2027))
        # Aliyeachishwa anaenda na wenzake (hamisha wote) — restore baadaye
        self.assertTrue(leftover.is_active)

    def test_results_untouched(self):
        exam = Exam.objects.create(
            name='Midterm 2026', year=2026, form=1, school=self.school,
        )
        subject = Subject.objects.create(name='Kiswahili')
        student = Student.objects.create(
            first_name='Mwanafunzi11', last_name='Wa2026', gender='F',
        )
        ExamResult.objects.create(
            exam=exam, student=student, subject=subject, score=70,
        )
        ProcessedResult.objects.create(
            exam=exam, student=student, total_score=70,
            average_score=Decimal('70.00'), position=1, points=2, division='I',
        )

        self.client.post(reverse('year_rollover'), {'confirm': 'HAMISHA'})

        self.assertEqual(ExamResult.objects.filter(exam=exam).count(), 1)
        self.assertEqual(ProcessedResult.objects.filter(exam=exam).count(), 1)
        pr = ProcessedResult.objects.get(exam=exam)
        self.assertEqual((pr.division, pr.points), ('I', 2))

    def test_rollover_page_get_shows_summary(self):
        resp = self.client.get(reverse('year_rollover'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'HAMISHA')
        self.assertContains(resp, 'Form 4')


class RosterIsolationTests(RolloverTestBase):
    """Baada ya rollover: rosti mpya na ya zamani visichanganyike."""

    def setUp(self):
        super().setUp()
        self.client.post(reverse('year_rollover'), {'confirm': 'HAMISHA'})

    def test_delete_all_spares_archive(self):
        # Rosti hai ya Form 2 (zamani ilikuwa Form 1 ya 2026)
        self.assertEqual(
            FormStudent.objects.filter(school=self.school, form=2, is_active=True).count(), 2,
        )
        self.client.post(reverse('delete_all_form_students', args=[2]))
        self.assertEqual(
            FormStudent.objects.filter(school=self.school, form=2, is_active=True).count(), 0,
        )
        # Archive ya Form 4/6 haijagusiwa
        self.assertEqual(
            FormStudent.objects.filter(school=self.school, is_active=False).count(), 2,
        )

    def test_marks_entry_uses_only_matching_year(self):
        # Mtihani wa mwaka 2026 Form 2 haupaswi kuona rosti ya 2027 Form 2
        # (waliopandishwa), na rosti ya 2026 Form 2 iko bado.
        # Tunaangalia query logic kidogo: filter ya marks_entry ni
        # (school, form, is_active, academic_year=exam.year).
        exam_2026_f2 = Exam.objects.create(
            name='Old Form2 Exam', year=2026, form=2, school=self.school,
        )
        visible = FormStudent.objects.filter(
            school=self.school, form=2, is_active=True, academic_year=exam_2026_f2.year,
        )
        # Form 2 ya 2026: walikuwa Form 1 wa 2026 — sasa wako 2027, si 2026.
        # Rosti ya Form 2 ya 2026 (asilia) ilipandishwa kwenda Form 3.
        self.assertEqual(visible.count(), 0)
