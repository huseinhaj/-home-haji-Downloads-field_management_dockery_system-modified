"""Menyu ya results: kila kiungo cha menyu (PC + simu) kinafunguka kwa role husika."""
import re

from django.test import Client, TestCase
from django.urls import reverse

from results.models import School, TeacherAccount

_HREF = re.compile(r'href="(/shule/[^"?#]*)"')


class NavLinksTests(TestCase):
    databases = {'default', 'results'}

    def setUp(self):
        self.school = School.objects.create(name='Mfano Secondary', region='Kagera', district='Kyerwa')
        self.client = Client()

    def _login(self, role):
        user = TeacherAccount.objects.create(
            email=f'{role.lower()}@example.com', full_name='Mtumiaji', role=role, school=self.school)
        self.client.force_login(user, backend='results.backends.ResultsAuthBackend')

    def _menu_links(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        start, end = html.index('<header class="app-header">'), html.index('<main')
        links = set(_HREF.findall(html[start:end])) - {reverse('results_logout')}
        self.assertTrue(links)
        return links

    def _assert_all_open(self, links):
        for url in sorted(links):
            r = self.client.get(url)
            self.assertIn(r.status_code, (200, 302), url)

    def test_academic_menu_links_open(self):
        self._login(TeacherAccount.ROLE_ACADEMIC)
        links = self._menu_links(reverse('academic_dashboard'))
        self.assertIn(reverse('upload_results'), links)
        self.assertIn(reverse('student_results_search'), links)
        self.assertIn(reverse('user_guide'), links)
        self._assert_all_open(links)

    def test_academic_bottom_navigation_order(self):
        self._login(TeacherAccount.ROLE_ACADEMIC)
        html = self.client.get(reverse('academic_dashboard')).content.decode()
        start = html.index('<nav class="bottom-nav"')
        end = html.index('</nav>', start)
        bottom = html[start:end]
        expected_urls = [
            reverse('home'),
            reverse('upload_results'),
            reverse('marks_entry'),
            reverse('student_results_search'),
            reverse('results_logout'),
            '#',
        ]
        positions = [bottom.index(url) for url in expected_urls]
        self.assertEqual(positions, sorted(positions))

    def test_teacher_menu_links_open(self):
        self._login(TeacherAccount.ROLE_TEACHER)
        links = self._menu_links(reverse('teacher_dashboard'))
        self.assertIn(reverse('marks_entry'), links)
        self.assertNotIn(reverse('upload_results'), links)
        self._assert_all_open(links)

    def test_printing_secretary_menu_links_open(self):
        self._login(TeacherAccount.ROLE_PRINTING_SECRETARY)
        links = self._menu_links(reverse('printing_secretary_dashboard'))
        self.assertIn(reverse('printing_secretary_dashboard'), links)
        self._assert_all_open(links)
