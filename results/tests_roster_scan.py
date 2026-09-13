"""Tests za Roster Scan — piga picha ya orodha → AI inasoma → uhakiki →
hifadhi (badala ya ku-upload faili).

Hakuna API call halisi: extract_students_from_document inafanyiwa mock,
kwa hivyo tests zinajaribu view logic (auth, validation, preview JSON,
save + dedup) bila kutegemea OpenRouter/Gemini.
"""
import json
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from .models import FormStudent, School, TeacherAccount


class RosterScanTestBase(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Shule ya Scan', region='Dodoma', district='Dodoma',
            current_academic_year=2026, level='secondary',
        )
        cls.academic = TeacherAccount.objects.create(
            email='scan@example.com', full_name='Academic Scan',
            role=TeacherAccount.ROLE_ACADEMIC, school=cls.school,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')


class ScanRosterViewTests(RosterScanTestBase):

    def test_scan_requires_form(self):
        resp = self.client.post(reverse('scan_roster'), {})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.json())

    def test_scan_rejects_invalid_form_number(self):
        resp = self.client.post(reverse('scan_roster'), {'form': '9'})
        self.assertEqual(resp.status_code, 400)

    def test_scan_without_file_returns_400(self):
        resp = self.client.post(reverse('scan_roster'), {'form': '1'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Hakuna picha', resp.json()['error'])

    def test_scan_preview_returns_students_not_saved(self):
        fake_students = [
            {'first': 'Halima', 'middle': 'Ally', 'last': 'Mohamed', 'gender': 'F', 'row': 1},
            {'first': 'Juma', 'middle': 'Hamisi', 'last': 'Ramadhani', 'gender': 'M', 'row': 2},
        ]
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_file = SimpleUploadedFile('roster.jpg', b'fake-image-bytes', content_type='image/jpeg')
        with mock.patch('results.services.roster_scan_service.extract_students_from_document',
                        return_value=fake_students):
            resp = self.client.post(reverse('scan_roster'), {'form': '1', 'scan_file': fake_file})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'preview')
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['students'][0]['first'], 'Halima')
        # Hakuna kilichohifadhiwa kwenye preview
        self.assertEqual(FormStudent.objects.filter(school=self.school).count(), 0)


class SaveScannedRosterTests(RosterScanTestBase):

    def _post(self, students, form=1):
        payload = {'form': form, 'students': students}
        return self.client.post(
            reverse('save_scanned_roster'),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_save_creates_students(self):
        resp = self._post([
            {'first': 'Halima', 'middle': 'Ally', 'last': 'Mohamed', 'gender': 'F'},
            {'first': 'Juma', 'middle': '', 'last': 'Ramadhani', 'gender': 'M'},
        ])
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['saved'], 2)
        self.assertEqual(data['created'], 2)
        self.assertEqual(
            FormStudent.objects.filter(school=self.school, form=1, is_active=True).count(), 2,
        )
        fs = FormStudent.objects.get(school=self.school, first_name='Halima')
        self.assertEqual((fs.middle_name, fs.last_name, fs.gender), ('Ally', 'Mohamed', 'F'))

    def test_save_dedups_against_existing_roster(self):
        FormStudent.objects.create(
            school=self.school, form=1, academic_year=2026,
            admission_no='S001', first_name='Halima', middle_name='Ally',
            last_name='Mohamed', gender='F',
        )
        resp = self._post([
            {'first': 'Halima', 'middle': 'Ally', 'last': 'Mohamed', 'gender': 'F'},
            {'first': 'Mpya', 'middle': '', 'last': 'Kabisa', 'gender': 'M'},
        ])
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['saved'], 2)
        self.assertEqual(data['created'], 1)
        self.assertEqual(data['existing'], 1)
        # Hakuna duplicate
        self.assertEqual(
            FormStudent.objects.filter(
                school=self.school, first_name='Halima', last_name='Mohamed',
            ).count(), 1,
        )

    def test_save_rejects_empty_and_invalid(self):
        resp = self._post([])
        self.assertEqual(resp.status_code, 400)
        resp = self._post([{'first': '', 'last': 'Hakuna'}])
        self.assertEqual(resp.status_code, 400)
        resp = self._post([{'first': 'Sahihi', 'last': 'Mtu'}], form=99)
        self.assertEqual(resp.status_code, 400)

    def test_save_skips_rows_without_first_name(self):
        resp = self._post([
            {'first': '', 'middle': '', 'last': 'Tupu', 'gender': 'M'},
            {'first': 'Halima', 'middle': '', 'last': 'Mohamed', 'gender': 'F'},
        ])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['saved'], 1)


class RosterScanServiceUnitTests(TestCase):
    """Unit tests za cleaning helpers za service (bila network)."""

    def test_clean_gender(self):
        from .services.roster_scan_service import _clean_gender
        self.assertEqual(_clean_gender('F'), 'F')
        self.assertEqual(_clean_gender('female'), 'F')
        self.assertEqual(_clean_gender('Kike'), 'F')
        self.assertEqual(_clean_gender('M'), 'M')
        self.assertEqual(_clean_gender('kiume'), 'M')
        self.assertEqual(_clean_gender(''), 'M')
        self.assertEqual(_clean_gender(None), 'M')
        self.assertEqual(_clean_gender('garbage'), 'M')

    def test_clean_name(self):
        from .services.roster_scan_service import _clean_name
        self.assertEqual(_clean_name('  Halima   Ally  Mohamed '), 'Halima Ally Mohamed')
        self.assertEqual(_clean_name('12. Juma Hamisi'), 'Juma Hamisi')
        self.assertEqual(_clean_name('3) Aisha J'), 'Aisha J')
        self.assertEqual(_clean_name(''), '')

    def test_extract_dedupes_and_splits_names(self):
        from .services.roster_scan_service import extract_students_from_document
        fake_pages = [object()]  # _load_page_images is mocked; images unused
        ai_text = json.dumps([
            {'row': 1, 'name': 'Halima Ally Mohamed', 'gender': 'F'},
            {'row': 2, 'name': 'Juma Hamisi', 'gender': 'M'},
            {'row': 3, 'name': 'Halima Ally Mohamed', 'gender': 'F'},  # duplicate
            {'row': 4, 'name': 'S/N', 'gender': 'M'},  # header junk — filtered
        ])
        with mock.patch('results.services.roster_scan_service._load_page_images', return_value=fake_pages), \
             mock.patch('results.services.roster_scan_service._read_page_with_ai', return_value=ai_text):
            rows = extract_students_from_document(uploaded_file=None)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['first'], 'Halima')
        self.assertEqual(rows[0]['middle'], 'Ally')
        self.assertEqual(rows[0]['last'], 'Mohamed')
        self.assertEqual(rows[0]['gender'], 'F')
        self.assertEqual(rows[1]['first'], 'Juma')
        self.assertEqual(rows[1]['middle'], '')
        self.assertEqual(rows[1]['last'], 'Hamisi')
