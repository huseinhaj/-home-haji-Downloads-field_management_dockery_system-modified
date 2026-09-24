"""Menyu ya results: kila kiungo kinafunguka, na kila role inaona viungo vyake tu."""
from django.test import Client, TestCase
from django.urls import reverse

from results.models import School, TeacherAccount
from results.nav import NAV


class NavLinksTests(TestCase):
    databases = {'default', 'results'}

    def setUp(self):
        self.school = School.objects.create(name='Mfano Secondary', region='Kagera', district='Kyerwa')
        self.client = Client()
        session = self.client.session
        session['ui_lang'] = 'sw'
        session.save()

    def _login(self, role):
        user = TeacherAccount.objects.create(
            email=f'{role.lower()}@example.com', full_name='Mtumiaji', role=role, school=self.school)
        self.client.force_login(user, backend='results.backends.ResultsAuthBackend')
        return user

    def _groups(self, response):
        return {g['key']: [i['url'] for i in g['items']] for g in response.context['NAV_GROUPS']}

    def _assert_all_links_open(self, groups):
        for urls in groups.values():
            for url in urls:
                r = self.client.get(url)
                self.assertIn(r.status_code, (200, 302), url)

    def test_every_nav_link_resolves(self):
        for *_, items in NAV:
            for name, *_ in items:
                reverse(name)

    def test_academic_menu(self):
        self._login(TeacherAccount.ROLE_ACADEMIC)
        r = self.client.get(reverse('academic_dashboard'))
        self.assertEqual(r.status_code, 200)
        groups = self._groups(r)
        self.assertIn(reverse('upload_results'), groups['mitihani'])
        self.assertIn(reverse('manage_teachers'), groups['shule'])
        self.assertNotIn('ps', groups)
        self.assertNotIn(reverse('personal_upload'), groups['mitihani'])
        html = r.content.decode()
        self.assertIn('aria-current="page"', html)
        # Maelekezo yameondolewa.
        self.assertNotIn('Uko hapa:', html)
        self.assertNotIn('srs-workflow', html)
        self.assertNotIn('help.js', html)
        self._assert_all_links_open(groups)

    def test_teacher_sees_only_teacher_links(self):
        self._login(TeacherAccount.ROLE_TEACHER)
        r = self.client.get(reverse('teacher_dashboard'))
        self.assertEqual(r.status_code, 200)
        groups = self._groups(r)
        all_urls = [u for urls in groups.values() for u in urls]
        self.assertIn(reverse('marks_entry'), all_urls)
        self.assertIn(reverse('personal_upload'), all_urls)
        for academic_only in ('upload_results', 'manage_teachers', 'school_setup', 'academic_dashboard'):
            self.assertNotIn(reverse(academic_only), all_urls)
        self._assert_all_links_open(groups)

    def test_printing_secretary_menu(self):
        self._login(TeacherAccount.ROLE_PRINTING_SECRETARY)
        r = self.client.get(reverse('printing_secretary_dashboard'))
        self.assertEqual(r.status_code, 200)
        groups = self._groups(r)
        self.assertEqual(groups['ps'], [reverse('printing_secretary_dashboard')])
        self._assert_all_links_open(groups)

    def test_logged_out_login_page_has_no_menu_groups(self):
        r = self.client.get(reverse('results_login'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['NAV_GROUPS'], [])
