"""Afisa Wilaya: joint exams za Halmashauri (shule zote za wilaya pamoja)."""
import io
from decimal import Decimal

from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from openpyxl import load_workbook

from .district_models import JointExam, district_key, schools_in_district
from .models import (
    Exam, ExamResult, ProcessedResult, School, Student, Subject, SubjectSubmission,
    TeacherAccount,
)
from .services.joint_analysis import analyse_joint_exam

LOGIN_BACKEND = 'results.backends.ResultsAuthBackend'


class DistrictKeyTests(SimpleTestCase):

    def test_dc_suffix_and_case_are_ignored(self):
        self.assertEqual(district_key('Kyerwa'), 'kyerwa')
        self.assertEqual(district_key('KYERWA DC'), 'kyerwa')
        self.assertEqual(district_key(' Kyerwa District Council '), 'kyerwa')

    def test_town_council_is_a_different_council(self):
        self.assertNotEqual(district_key('Tarime Tc'), district_key('Tarime Dc'))


def _student(first, gender):
    return Student.objects.create(first_name=first, last_name='Test', gender=gender)


def _processed(exam, student, division, avg):
    return ProcessedResult.objects.create(
        exam=exam, student=student, total_score=Decimal(avg) * 7,
        average_score=Decimal(avg), points=7, division=division,
    )


class JointFlowTests(TestCase):
    databases = {'default', 'results'}

    def setUp(self):
        self.gov = School.objects.create(
            name='Businde Secondary School', region='Kagera', district='Kyerwa',
            ward='Businde', ownership='GOV', level='secondary')
        self.priv = School.objects.create(
            name='Bernard Secondary School', region='Kagera', district='Kyerwa Dc',
            ward='Kyerwa', ownership='PRIVATE', level='secondary')
        self.other = School.objects.create(
            name='Nje Secondary School', region='Kagera', district='Karagwe', level='secondary')
        self.maths = Subject.objects.create(name='Mathematics')
        self.kisw = Subject.objects.create(name='Kiswahili')

        self.officer = TeacherAccount.objects.create(
            email='deo@kyerwa.go.tz', full_name='Afisa', role=TeacherAccount.ROLE_DISTRICT,
            district='Kyerwa', region='Kagera')
        self.officer_client = Client()
        self.officer_client.force_login(self.officer, backend=LOGIN_BACKEND)

    def _create_joint(self):
        resp = self.officer_client.post(reverse('joint_exam_create'), {
            'name': 'FORM ONE MID TERM JOINT EXAMINATION', 'form': '1', 'year': '2026',
            'date': '2026-09-15', 'exam_type': 'DISTRICT_JOINT',
            'subjects': [self.maths.pk, self.kisw.pk],
            'schools': [self.gov.pk, self.priv.pk],
        })
        self.assertEqual(resp.status_code, 302, resp.content[:500])
        return JointExam.objects.get()

    def _fill_results(self, joint):
        """Businde: I, II, 0 (+1 ABS) · Bernard: I, I."""
        eg = Exam.objects.get(joint_exam=joint, school=self.gov)
        ep = Exam.objects.get(joint_exam=joint, school=self.priv)
        a, b, c, d = (_student('A', 'M'), _student('B', 'F'), _student('C', 'M'), _student('D', 'F'))
        _processed(eg, a, 'I', 80)
        _processed(eg, b, 'II', 66)
        _processed(eg, c, '0', 20)
        _processed(eg, d, 'ABS', 0)
        e, f = _student('E', 'F'), _student('F', 'M')
        _processed(ep, e, 'I', 90)
        _processed(ep, f, 'I', 76)
        for exam, student, score in [(eg, a, 80), (eg, b, 50), (eg, c, 10), (ep, e, 95), (ep, f, 70)]:
            ExamResult.objects.create(exam=exam, student=student, subject=self.maths, score=score)
        ExamResult.objects.create(exam=eg, student=d, subject=self.maths, is_absent=True)
        return eg, ep

    def test_create_attaches_an_exam_to_every_chosen_school(self):
        joint = self._create_joint()
        self.assertEqual(joint.school_exams.count(), 2)
        exam = joint.school_exams.get(school=self.gov)
        self.assertEqual((exam.form, exam.year, exam.exam_type), (1, 2026, 'DISTRICT_JOINT'))
        self.assertEqual(SubjectSubmission.objects.filter(exam=exam).count(), 2)
        # Shule ya wilaya nyingine haiguswi
        self.assertFalse(Exam.objects.filter(school=self.other).exists())

    def test_analysis_matches_council_formulas(self):
        joint = self._create_joint()
        self._fill_results(joint)
        data = analyse_joint_exam(joint)
        bernard, businde = data['schools']          # ranked by GPA
        self.assertEqual(bernard['school'], self.priv)
        self.assertEqual((bernard['rank'], bernard['gpa']), (1, 1.0))
        # Businde: I×1 + II×2 + 0×5 = 8 ÷ 3
        self.assertAlmostEqual(businde['gpa'], 8 / 3, places=4)
        self.assertEqual(businde['registered']['T'], 4)
        self.assertEqual(businde['sat']['T'], 3)
        self.assertEqual(businde['absent'], {'M': 0, 'F': 1, 'T': 1})
        self.assertEqual(businde['i_iv']['T'], 2)
        self.assertAlmostEqual(businde['iv_0_pct'], 33.33, places=2)
        self.assertEqual(data['totals']['sat']['T'], 5)

        maths = next(s for s in data['subjects'] if s['name'] == 'Mathematics')
        # A(80) C(50) F(10) A(95) B(70) → (1+3+5+1+2)/5
        self.assertAlmostEqual(maths['gpa'], 12 / 5, places=4)
        self.assertEqual(maths['pass']['T'], 4)
        self.assertEqual(maths['rows'][0]['school'], self.priv)

    def test_ownership_filter(self):
        joint = self._create_joint()
        self._fill_results(joint)
        data = analyse_joint_exam(joint, ownership='GOV')
        self.assertEqual([r['school'] for r in data['schools']], [self.gov])

    def test_excel_has_council_sheets(self):
        joint = self._create_joint()
        self._fill_results(joint)
        resp = self.officer_client.get(reverse('joint_exam_excel', args=[joint.pk]))
        self.assertEqual(resp.status_code, 200)
        wb = load_workbook(io.BytesIO(resp.content))
        self.assertEqual(wb.sheetnames[:3], ['DIVISION', 'GRADE', 'LIST OF SUBJECTS'])
        self.assertIn('MATHEMATICS', wb.sheetnames)
        ws = wb['DIVISION']
        self.assertEqual(ws['E9'].value, 'BERNARD SECONDARY SCHOOL')
        self.assertEqual(ws['D9'].value, 'BINAFSI')
        self.assertEqual(ws['AR9'].value, 1)          # NAFASI KIWILAYA
        self.assertEqual(ws['E10'].value, 'BUSINDE SECONDARY SCHOOL')
        self.assertEqual(ws['D10'].value, 'SERIKALI')

    def test_officer_pages_render(self):
        joint = self._create_joint()
        self._fill_results(joint)
        for url in [reverse('district_dashboard'), reverse('district_schools'),
                    reverse('joint_exam_create'), reverse('joint_exam_detail', args=[joint.pk])]:
            self.assertEqual(self.officer_client.get(url).status_code, 200, url)
        # Nyumbani kwa afisa ni dashibodi ya wilaya
        self.assertRedirects(self.officer_client.get(reverse('home')), reverse('district_dashboard'),
                             fetch_redirect_response=False)

    def test_officer_of_another_district_cannot_open_the_joint(self):
        joint = self._create_joint()
        other = TeacherAccount.objects.create(
            email='deo@karagwe.go.tz', role=TeacherAccount.ROLE_DISTRICT, district='Karagwe')
        c = Client()
        c.force_login(other, backend=LOGIN_BACKEND)
        self.assertEqual(c.get(reverse('joint_exam_detail', args=[joint.pk])).status_code, 404)
        self.assertEqual(c.get(reverse('joint_exam_excel', args=[joint.pk])).status_code, 404)

    def test_schools_see_district_results_only_after_publish(self):
        joint = self._create_joint()
        eg, ep = self._fill_results(joint)
        academic = TeacherAccount.objects.create(
            email='ac@bernard.sc.tz', role=TeacherAccount.ROLE_ACADEMIC, school=self.priv)
        c = Client()
        c.force_login(academic, backend=LOGIN_BACKEND)
        url = reverse('school_joint_results', args=[ep.pk])
        self.assertEqual(c.get(url).status_code, 302)

        self.officer_client.post(reverse('joint_exam_publish', args=[joint.pk]))
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Businde Secondary School')   # anaona shule nyingine pia

        outsider = TeacherAccount.objects.create(
            email='ac@nje.sc.tz', role=TeacherAccount.ROLE_ACADEMIC, school=self.other)
        c2 = Client()
        c2.force_login(outsider, backend=LOGIN_BACKEND)
        self.assertEqual(c2.get(url).status_code, 403)

    def test_teachers_cannot_use_officer_pages(self):
        academic = TeacherAccount.objects.create(
            email='ac2@bernard.sc.tz', role=TeacherAccount.ROLE_ACADEMIC, school=self.priv)
        c = Client()
        c.force_login(academic, backend=LOGIN_BACKEND)
        self.assertEqual(c.get(reverse('district_dashboard')).status_code, 403)

    def test_school_ward_and_ownership_can_be_edited(self):
        resp = self.officer_client.post(reverse('district_schools'), {
            f'ward_{self.gov.pk}': 'kibingo', f'ownership_{self.gov.pk}': 'PRIVATE',
            f'ward_{self.priv.pk}': 'Kyerwa', f'ownership_{self.priv.pk}': 'PRIVATE',
        })
        self.assertEqual(resp.status_code, 302)
        self.gov.refresh_from_db()
        self.assertEqual((self.gov.ward, self.gov.ownership), ('KIBINGO', 'PRIVATE'))


class SetupKyerwaCommandTests(TestCase):
    databases = {'default', 'results'}

    def test_creates_39_schools_once_and_the_officer(self):
        School.objects.create(name='Businde Secondary School', region='Kagera', district='Kyerwa')
        out = io.StringIO()
        call_command('setup_kyerwa_district', officer_email='deo@kyerwa.go.tz', stdout=out)
        schools = schools_in_district('Kyerwa', 'Kagera')
        self.assertEqual(schools.count(), 39)
        self.assertEqual(schools.filter(ownership='PRIVATE').count(), 7)
        self.assertEqual(schools.get(name='Businde Secondary School').ward, 'Businde')
        officer = TeacherAccount.objects.get(email='deo@kyerwa.go.tz')
        self.assertTrue(officer.is_district_officer)
        self.assertEqual(officer.district, 'Kyerwa')

        call_command('setup_kyerwa_district', stdout=io.StringIO())
        self.assertEqual(schools_in_district('Kyerwa', 'Kagera').count(), 39)

    def test_dry_run_changes_nothing(self):
        call_command('setup_kyerwa_district', dry_run=True, stdout=io.StringIO())
        self.assertEqual(School.objects.count(), 0)
