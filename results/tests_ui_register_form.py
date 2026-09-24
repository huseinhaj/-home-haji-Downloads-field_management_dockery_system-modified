from django.test import TestCase
from django.urls import reverse

from .models import FormStudent, School, TeacherAccount


class RegisterFormStudentUiTests(TestCase):
    databases = {'default', 'results'}

    def setUp(self):
        self.school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
        self.academic = TeacherAccount.objects.create(
            email='academic@example.com', full_name='Academic One',
            role=TeacherAccount.ROLE_ACADEMIC, school=self.school,
        )
        self.teacher = TeacherAccount.objects.create(
            email='teacher@example.com', full_name='Teacher One',
            role=TeacherAccount.ROLE_TEACHER, school=self.school,
        )

    def test_get_shows_register_form(self):
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        resp = self.client.get(reverse('register_form_student', args=[1]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Register Student')

    def test_dashboard_has_register_form_button(self):
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        resp = self.client.get(reverse('academic_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Register Form I')
        self.assertContains(resp, reverse('register_form_student', args=[1]))

    def test_teacher_cannot_register(self):
        self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')
        resp = self.client.get(reverse('register_form_student', args=[1]))
        self.assertEqual(resp.status_code, 403)

    def test_post_creates_student_and_redirects_to_roster(self):
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        url = reverse('register_form_student', args=[1])
        resp = self.client.post(url, {
            'first_name': 'Juma', 'middle_name': 'Salim', 'last_name': 'Kipande', 'gender': 'M',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'form=1', resp.url)
        self.assertTrue(FormStudent.objects.filter(
            school=self.school, form=1, first_name='Juma', last_name='Kipande',
        ).exists())

    def test_invalid_form_number_redirects(self):
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        resp = self.client.get(reverse('register_form_student', args=[99]))
        self.assertEqual(resp.status_code, 302)

    def test_duplicate_same_name_no_second_row(self):
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        url = reverse('register_form_student', args=[1])
        self.client.post(url, {
            'first_name': 'Juma', 'middle_name': 'Salim', 'last_name': 'Kipande', 'gender': 'M',
        })
        resp = self.client.post(url, {
            'first_name': 'juma', 'middle_name': 'salim', 'last_name': 'kipande', 'gender': 'F',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(FormStudent.objects.filter(
            school=self.school, form=1, first_name__iexact='Juma', last_name__iexact='Kipande',
        ).count(), 1)