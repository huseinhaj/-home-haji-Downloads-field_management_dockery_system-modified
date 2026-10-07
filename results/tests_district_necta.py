"""Ukurasa wa umma wa matokeo ya wilaya — mtiririko wa NECTA:

    /shule/wilaya/<joint>/matokeo/            herufi A–Z → shule zinazoanzia nayo
    /shule/wilaya/<joint>/matokeo/<exam>/     matokeo kamili ya shule hiyo

Bila login (kama NECTA) — ila kabla ya afisa kuyafungua ni afisa wa wilaya
na shule inayoshiriki pekee ndizo zinaona.
"""
from django.test import Client, TestCase
from django.urls import reverse

from .district_models import JointExam
from .models import (
    ExamResult, ProcessedResult, School, Student, Subject, TeacherAccount,
)
from .utils import get_grade_for_exam

LOGIN_BACKEND = 'results.backends.ResultsAuthBackend'


class NectaPortalTests(TestCase):
    databases = {'default', 'results'}

    def setUp(self):
        self.alpha = School.objects.create(
            name='Alpha Secondary School', region='Kagera', district='Kyerwa',
            ward='Alpha', ownership='GOV', level='secondary')
        self.beta = School.objects.create(
            name='Beta Secondary School', region='Kagera', district='Kyerwa',
            ward='Beta', ownership='GOV', level='secondary')
        self.maths = Subject.objects.create(name='Mathematics')

        self.joint = JointExam.objects.create(
            name='FORM ONE MID TERM JOINT', form=1, year=2026,
            district='Kyerwa', region='Kagera')
        self.joint.subjects.set([self.maths])
        self.exam_a = self.joint.attach_school(self.alpha)
        self.exam_b = self.joint.attach_school(self.beta)

        juma = Student.objects.create(first_name='Juma', last_name='Mwinyi', gender='M')
        asha = Student.objects.create(first_name='Asha', last_name='Khamis', gender='F')
        zawadi = Student.objects.create(first_name='Zawadi', last_name='Juma', gender='F')
        ProcessedResult.objects.create(
            exam=self.exam_a, student=juma, total_score=560, average_score=80,
            points=7, division='I', position=1)
        ProcessedResult.objects.create(
            exam=self.exam_a, student=asha, total_score=462, average_score=66,
            points=14, division='II', position=2)
        ProcessedResult.objects.create(
            exam=self.exam_b, student=zawadi, total_score=350, average_score=50,
            points=21, division='III', position=1)
        ExamResult.objects.create(exam=self.exam_a, student=juma, subject=self.maths, score=90)
        ExamResult.objects.create(exam=self.exam_a, student=asha, subject=self.maths, score=55)

        self.anon = Client()
        self.officer = TeacherAccount.objects.create(
            email='deo@kyerwa.go.tz', role=TeacherAccount.ROLE_DISTRICT,
            district='Kyerwa', region='Kagera')
        self.officer_client = Client()
        self.officer_client.force_login(self.officer, backend=LOGIN_BACKEND)

        self.outsider = TeacherAccount.objects.create(
            email='deo@karagwe.go.tz', role=TeacherAccount.ROLE_DISTRICT,
            district='Karagwe', region='Kagera')
        self.outsider_client = Client()
        self.outsider_client.force_login(self.outsider, backend=LOGIN_BACKEND)

        self.member = TeacherAccount.objects.create(
            email='ac@alpha.sc.tz', role=TeacherAccount.ROLE_ACADEMIC, school=self.alpha)
        self.member_client = Client()
        self.member_client.force_login(self.member, backend=LOGIN_BACKEND)

    def _index(self, client=None, **params):
        return (client or self.anon).get(
            reverse('district_necta_index', args=[self.joint.pk]), params)

    def _school(self, client=None, exam=None):
        exam = exam or self.exam_a
        return (client or self.anon).get(
            reverse('district_necta_school', args=[self.joint.pk, exam.pk]))

    # ── ruhusa ──────────────────────────────────────────────────────────
    def test_anonymous_cannot_open_an_unpublished_joint(self):
        self.assertEqual(self._index().status_code, 404)
        self.assertEqual(self._school().status_code, 404)

    def test_officer_of_the_district_can_preview_before_publish(self):
        self.assertEqual(self._index(self.officer_client).status_code, 200)
        self.assertEqual(self._school(self.officer_client).status_code, 200)

    def test_member_school_can_open_before_publish(self):
        self.assertEqual(self._index(self.member_client).status_code, 200)
        self.assertEqual(self._school(self.member_client).status_code, 200)

    def test_officer_of_another_district_sees_404(self):
        self.assertEqual(self._index(self.outsider_client).status_code, 404)
        self.assertEqual(self._school(self.outsider_client).status_code, 404)

    # ── ukurasa wa herufi ───────────────────────────────────────────────
    def test_public_portal_lists_the_published_joint(self):
        self.joint.published = True
        self.joint.save(update_fields=['published'])
        portal = self.anon.get(reverse('student_results_search'))
        self.assertContains(portal, reverse('district_necta_index', args=[self.joint.pk]))

    def test_letter_picker_groups_schools_by_first_letter(self):
        self.joint.published = True
        self.joint.save(update_fields=['published'])

        page_a = self._index(L='A')
        self.assertEqual(page_a.status_code, 200)
        self.assertContains(page_a, 'Alpha Secondary School')
        self.assertNotContains(page_a, 'Beta Secondary School')

        page_b = self._index(L='B')
        self.assertContains(page_b, 'Beta Secondary School')
        self.assertNotContains(page_b, 'Alpha Secondary School')

        # Herufi isiyo na shule → ujumbe, si hitilafu
        page_z = self._index(L='Z')
        self.assertEqual(page_z.status_code, 200)

    def test_index_renders_the_alphabet_and_uses_the_joint_district(self):
        self.joint.published = True
        self.joint.save(update_fields=['published'])
        page = self._index()
        self.assertContains(page, '?L=A')
        self.assertContains(page, '?L=B')
        # Herufi isiyo na shule bado inaonyeshwa — tu haiwezi kubonyekwa
        self.assertContains(page, '>Z</span>')
        # Mastimiti ya ukurasa wa umma hutoka kwa joint, si mtumiaji
        self.assertEqual(page.context['DISTRICT_NAME'], 'Kyerwa')
        self.assertContains(page, 'KYERWA')

    # ── ukurasa wa matokeo ya shule ─────────────────────────────────────
    def test_school_page_shows_the_full_necta_table(self):
        self.joint.published = True
        self.joint.save(update_fields=['published'])
        page = self._school()
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Alpha Secondary School')
        self.assertContains(page, 'MATHEMATICS')
        # Kila mwanafunzi: nafasi, jina, gredi ya somo, points na daraja
        self.assertContains(page, 'Juma Mwinyi')
        self.assertContains(page, get_grade_for_exam(90, self.exam_a))
        self.assertContains(page, get_grade_for_exam(55, self.exam_a))
        self.assertContains(page, 'Asha Khamis')
        self.assertContains(page, '>I<')
        self.assertContains(page, '>II<')

    def test_candidates_are_listed_in_position_order(self):
        self.joint.published = True
        self.joint.save(update_fields=['published'])
        content = self._school().content.decode()
        self.assertLess(content.index('Juma Mwinyi'), content.index('Asha Khamis'))

    def test_its_own_school_results_only(self):
        self.joint.published = True
        self.joint.save(update_fields=['published'])
        page = self._school(exam=self.exam_b)
        self.assertContains(page, 'Zawadi Juma')
        self.assertNotContains(page, 'Juma Mwinyi')

    def test_absent_candidate_shows_x_for_the_subject(self):
        absent = Student.objects.create(first_name='Neema', last_name='Said', gender='F')
        ProcessedResult.objects.create(
            exam=self.exam_a, student=absent, total_score=0, average_score=0,
            points=0, division='ABS', position=None)
        ExamResult.objects.create(
            exam=self.exam_a, student=absent, subject=self.maths, is_absent=True)
        self.joint.published = True
        self.joint.save(update_fields=['published'])
        content = self._school().content.decode()
        self.assertGreaterEqual(content.count('<td><b>X</b></td>'), 1)

    def test_an_exam_from_another_joint_is_not_reachable(self):
        other = JointExam.objects.create(
            name='ANOTHER JOINT', form=1, year=2025, district='Kyerwa')
        other.subjects.set([self.maths])
        foreign = other.attach_school(self.alpha)
        self.joint.published = True
        self.joint.save(update_fields=['published'])
        resp = self.anon.get(reverse(
            'district_necta_school', args=[self.joint.pk, foreign.pk]))
        self.assertEqual(resp.status_code, 404)
