"""Tests za 'Jiunge' (school discovery + first-Academic registration).

Kuthibitisha kuwa shule za MSINGI pia zinaonekana na zinaweza kujiunga —
hana filter ya 'Secondary' pekee iliyokuwepo zamani.
"""
from django.test import Client, TestCase
from django.urls import reverse

from field_app.models import District, Region
from field_app.models import School as SourceSchool

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

    def test_join_as_primary_creates_school_with_primary_level(self):
        client = Client()
        resp = client.post(reverse('register_school_confirm'), {
            'school_id': self.primary.id,
            'full_name': 'Mwalimu Mkuu',
            'email': 'acad.primary@example.com',
            'password1': 'nenosiri1234',
            'password2': 'nenosiri1234',
        })
        # Account inaundwa na user anaingia moja kwa moja
        account = TeacherAccount.objects.filter(email='acad.primary@example.com').first()
        self.assertIsNotNone(account, f'Account haikoundwa: {getattr(resp, "status_code", "?")}')
        self.assertEqual(account.role, TeacherAccount.ROLE_ACADEMIC)

        # results.School imeundwa na level='primary'
        school = School.objects.get(source_school_id=self.primary.id)
        self.assertEqual(school.level, 'primary')
        self.assertTrue(school.is_primary)
        self.assertEqual(account.school_id, school.id)

    def test_join_as_secondary_still_works(self):
        client = Client()
        client.post(reverse('register_school_confirm'), {
            'school_id': self.secondary.id,
            'full_name': 'Mwalimu Sekondari',
            'email': 'acad.sec@example.com',
            'password1': 'nenosiri1234',
            'password2': 'nenosiri1234',
        })
        school = School.objects.get(source_school_id=self.secondary.id)
        self.assertFalse(school.is_primary)

    def test_second_joiner_told_to_contact_existing_academic(self):
        client = Client()
        client.post(reverse('register_school_confirm'), {
            'school_id': self.primary.id,
            'full_name': 'Mwalimu Wa Kwanza',
            'email': 'first@example.com',
            'password1': 'nenosiri1234',
            'password2': 'nenosiri1234',
        })
        # Mtu wa pili anajaribu kujiunga na shule ileile
        resp = client.post(reverse('register_school_confirm'), {
            'school_id': self.primary.id,
            'full_name': 'Mwalimu Wa Pili',
            'email': 'second@example.com',
            'password1': 'nenosiri1234',
            'password2': 'nenosiri1234',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'first@example.com'[:2])  # masked email inaonekana
        self.assertFalse(
            TeacherAccount.objects.filter(email='second@example.com').exists(),
            'Account ya pili haipaswi kuundwa',
        )
