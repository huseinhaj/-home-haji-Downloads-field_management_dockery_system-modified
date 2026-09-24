from django.test import TestCase
from django.urls import reverse

from .models import Exam, School, SubjectSubmission, TeacherAccount
from .utils import safe_get_or_create_subject


class AddSubjectToExamUiTests(TestCase):
    databases = {'default', 'results'}

    def setUp(self):
        self.school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
        self.exam = Exam.objects.create(name='Midterm 1', year=2026, form=4, school=self.school)
        self.math = safe_get_or_create_subject('Mathematics')
        SubjectSubmission.objects.create(exam=self.exam, subject=self.math)
        self.academic = TeacherAccount.objects.create(
            email='academic@example.com', full_name='Academic One',
            role=TeacherAccount.ROLE_ACADEMIC, school=self.school,
        )
        self.teacher = TeacherAccount.objects.create(
            email='teacher@example.com', full_name='Teacher One',
            role=TeacherAccount.ROLE_TEACHER, school=self.school,
        )

    def test_overview_shows_add_subject_button_for_academic_only(self):
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        resp = self.client.get(reverse('exam_overview', args=[self.exam.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Mathematics')
        self.assertContains(resp, 'Add Subject')

        client2 = self.client.__class__()
        client2.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')
        resp2 = client2.get(reverse('exam_overview', args=[self.exam.id]))
        self.assertContains(resp2, 'Mathematics')
        self.assertNotContains(resp2, 'Add Subject')

    def test_post_creates_submission_and_shows_subject(self):
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        url = reverse('add_exam_subject', args=[self.exam.id])
        resp = self.client.post(url, {'subject_name': 'Computer Programming'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(SubjectSubmission.objects.filter(exam=self.exam, subject__name='Computer Programming').exists())
        resp2 = self.client.get(reverse('exam_overview', args=[self.exam.id]))
        self.assertContains(resp2, 'Computer Programming')

    def test_duplicate_is_idempotent(self):
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        url = reverse('add_exam_subject', args=[self.exam.id])
        resp = self.client.post(url, {'subject_name': 'Mathematics'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SubjectSubmission.objects.filter(exam=self.exam, subject=self.math).count(), 1)

    def test_overview_offers_remove_controls_in_modal(self):
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        resp = self.client.get(reverse('exam_overview', args=[self.exam.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Add/Remove Subject')
        self.assertContains(resp, reverse('remove_exam_subject', args=[self.exam.id, self.math.id]))

    def test_remove_subject_deletes_submission_and_marks(self):
        from .models import ExamResult, Student

        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        student = Student.objects.create(first_name='Juma', last_name='Baker')
        ExamResult.objects.create(exam=self.exam, student=student, subject=self.math, score=75)
        url = reverse('remove_exam_subject', args=[self.exam.id, self.math.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(SubjectSubmission.objects.filter(exam=self.exam, subject=self.math).exists())
        self.assertFalse(ExamResult.objects.filter(exam=self.exam, subject=self.math).exists())

    def test_remove_subject_requires_academic(self):
        from .models import ExamResult, Student

        student = Student.objects.create(first_name='Juma', last_name='Baker')
        ExamResult.objects.create(exam=self.exam, student=student, subject=self.math, score=75)
        self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')
        url = reverse('remove_exam_subject', args=[self.exam.id, self.math.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(SubjectSubmission.objects.filter(exam=self.exam, subject=self.math).exists())