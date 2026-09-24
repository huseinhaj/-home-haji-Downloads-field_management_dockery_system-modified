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