"""Mfumo unaojielezea: menyu, njia ya kazi na maelekezo ya ukurasa."""
from django.test import Client, TestCase
from django.urls import reverse

from results.models import School, TeacherAccount
from results.page_help import NAV, PAGE_HELP, WORKFLOW, _routes


class PageHelpDataTests(TestCase):
    def test_every_nav_and_workflow_link_has_help(self):
        names = {n for *_, items in NAV for n, _, _ in items}
        names |= {n for steps in WORKFLOW.values() for n, _, _ in steps}
        self.assertEqual(names - set(PAGE_HELP), set())
        for name in names:
            self.assertEqual(PAGE_HELP[name]['kind'], 'page', name)
            reverse(name)  # arg-free: every menu link must resolve

    def test_every_help_entry_is_a_real_results_url(self):
        self.assertEqual({n for n, _ in _routes()}, set(PAGE_HELP))


class SelfExplainingPagesTests(TestCase):
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

    def test_academic_menu_workflow_and_page_help(self):
        self._login(TeacherAccount.ROLE_ACADEMIC)
        r = self.client.get(reverse('academic_dashboard'))
        self.assertEqual(r.status_code, 200)
        groups = self._groups(r)
        self.assertIn(reverse('upload_results'), groups['mitihani'])
        self.assertIn(reverse('manage_teachers'), groups['shule'])
        self.assertNotIn('ps', groups)
        self.assertNotIn(reverse('personal_upload'), groups['mitihani'])

        wf = r.context['WORKFLOW']
        self.assertEqual(wf['total'], len(WORKFLOW['academic']))
        self.assertEqual(wf['current'], wf['total'])  # dashibodi = hatua ya mwisho

        html = r.content.decode()
        self.assertIn('Uko hapa:', html)
        self.assertIn(PAGE_HELP['academic_dashboard']['sw']['title'], html)
        # Kila kiungo cha menyu kinaonyesha kinakupeleka wapi.
        self.assertIn(PAGE_HELP['manage_teachers']['sw']['what'], html)
        self.assertIn('aria-current="page"', html)

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
        self.assertEqual(r.context['WORKFLOW']['current'], 3)

    def test_printing_secretary_menu(self):
        self._login(TeacherAccount.ROLE_PRINTING_SECRETARY)
        r = self.client.get(reverse('printing_secretary_dashboard'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._groups(r)['ps'], [reverse('printing_secretary_dashboard')])
        self.assertIsNone(r.context['WORKFLOW'])

    def test_logged_out_login_page_has_no_menu_groups(self):
        r = self.client.get(reverse('results_login'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['NAV_GROUPS'], [])
