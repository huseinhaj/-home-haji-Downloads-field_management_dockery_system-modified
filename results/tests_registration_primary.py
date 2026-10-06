"""Tests za 'Jiunge' (school discovery).

Kuthibitisha kuwa shule za MSINGI pia zinaonekana kwenye orodha, na kuwa
kuchagua shule SI kuniunga na shule hiyo — ukurasa unaonyesha tu ujumbe
"Hujaungwa na shule hii" pamoja na namba ya Support ya Admin. (Watumiaji
waliripoti kuunganishwa na shule tofauti, kwa hivyo kusajili hapa
imefungwa.)
"""
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.html import escape

from field_app.models import District, Region
from field_app.models import School as SourceSchool

from .context_processors import SUPPORT_PHONE
from .models import School, TeacherAccount


class JoinSchoolPrimaryTests(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.region = Region.objects.create(name='Dodoma')
        cls.district = District.objects.create(name='Dodoma MJini', region=cls.region)
        cls.primary = SourceSchool.objects.create(
            name='Shule ya Msingi Chang\'ombe', district=cls.district, level='Primary',
        )
        cls.secondary = SourceSchool.objects.create(
            name='Sekondari ya Chang\'ombe', district=cls.district, level='Secondary',
        )

    def sw_client(self):
        """Mteja wa lugha ya Kiswahili — ujumbe wa 'Hujaungwa' unaonekana."""
        client = Client()
        session = client.session
        session['ui_lang'] = 'sw'
        session.save()
        return client

    def test_ajax_schools_returns_primary_and_secondary(self):
        client = Client()
        resp = client.get(reverse('ajax_schools'), {'district_id': self.district.id})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        ids = [s['id'] for s in data['schools']]
        self.assertIn(self.primary.id, ids, 'Shule ya msingi haionekani kwenye orodha!')
        self.assertIn(self.secondary.id, ids)
        levels = {s['id']: s['level'] for s in data['schools']}
        self.assertEqual(levels[self.primary.id], 'Primary')

    def test_join_primary_shows_not_joined_and_support_phone(self):
        """Kuchagua shule kunasema 'Hujaungwa na shule hii' + namba ya Admin."""
        client = self.sw_client()
        resp = client.post(reverse('register_school_confirm'), {'school_id': self.primary.id})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Hujaungwa na shule hii')
        self.assertContains(resp, SUPPORT_PHONE)
        self.assertContains(resp, escape(School.objects.get(source_school_id=self.primary.id).name))
        # Hakuna akaunti inayoundwa na hakuna mtumiaji kuunganishwa
        self.assertFalse(TeacherAccount.objects.exists())

    def test_join_primary_still_mirrors_school_with_primary_level(self):
        """Shule inaendelea kunakiliwa kwenye results.School (kwa admin)."""
        client = Client()
        client.post(reverse('register_school_confirm'), {'school_id': self.primary.id})
        school = School.objects.get(source_school_id=self.primary.id)
        self.assertEqual(school.level, 'primary')
        self.assertTrue(school.is_primary)

    def test_join_secondary_mirrors_secondary_level(self):
        client = Client()
        client.post(reverse('register_school_confirm'), {'school_id': self.secondary.id})
        school = School.objects.get(source_school_id=self.secondary.id)
        self.assertFalse(school.is_primary)
        self.assertFalse(TeacherAccount.objects.exists())

    def test_full_registration_details_do_not_create_account(self):
        """Hata akiwasilisha jina/email/password, hakuna akaunti inayoundwa.

        Ndiyo hitilafu iliyoripotiwa: watumiaji walikuwa wakiunganishwa na
        shule tofauti — sasa kusajili hapa hauruhusiwi kabisa.
        """
        client = self.sw_client()
        resp = client.post(reverse('register_school_confirm'), {
            'school_id': self.secondary.id,
            'full_name': 'Mwalimu Mkuu',
            'email': 'mwalimu@example.com',
            'password1': 'nenosiri1234',
            'password2': 'nenosiri1234',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Hujaungwa na shule hii')
        self.assertFalse(
            TeacherAccount.objects.filter(email='mwalimu@example.com').exists(),
            'Akaunti haipaswi kuundwa kwenye ukurasa wa kujiunga',
        )

    def test_second_joiner_also_told_to_contact_admin(self):
        """Hakuna 'akaunti tayari ipo' — kila mtu anaambiwa wasiliane na Admin."""
        client = self.sw_client()
        client.post(reverse('register_school_confirm'), {
            'school_id': self.primary.id,
            'full_name': 'Mwalimu Wa Kwanza',
            'email': 'first@example.com',
            'password1': 'nenosiri1234',
            'password2': 'nenosiri1234',
        })
        resp = client.post(reverse('register_school_confirm'), {'school_id': self.primary.id})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Hujaungwa na shule hii')
        self.assertContains(resp, SUPPORT_PHONE)
        self.assertFalse(TeacherAccount.objects.exists())

    def test_get_without_school_redirects_to_start(self):
        client = Client()
        resp = client.get(reverse('register_school_confirm'))
        self.assertRedirects(resp, reverse('register_school_start'))
        resp = client.post(reverse('register_school_confirm'), {})
        self.assertRedirects(resp, reverse('register_school_start'))
