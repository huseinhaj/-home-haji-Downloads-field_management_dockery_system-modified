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
        url = reverse('joint_exam_excel', args=[joint.pk])

        resp = self.officer_client.get(url, {'kind': 'division'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('DIVISION PERFORMANCE ANALYSIS', resp['Content-Disposition'])
        wb = load_workbook(io.BytesIO(resp.content))
        self.assertEqual(wb.sheetnames, ['DIVISION', 'GRADE'])
        ws = wb['DIVISION']
        self.assertEqual(ws['A2'].value, 'HALMASHAURI YA WILAYA YA KYERWA')
        self.assertEqual((ws['E9'].value, ws['D9'].value), ('BERNARD SECONDARY SCHOOL', 'BINAFSI'))
        self.assertEqual((ws['O9'].value, ws['P9'].value), (1, 1))      # Div I: WAV 1, WAS 1
        self.assertEqual(ws['AR9'].value, '=IFERROR(RANK(AQ9,$AQ$9:$AQ$10,1),"")')
        self.assertEqual((ws['E10'].value, ws['D10'].value), ('BUSINDE SECONDARY SCHOOL', 'SERIKALI'))
        self.assertEqual(ws['A11'].value, 'TOTAL')
        self.assertEqual(ws['F11'].value, '=SUM(F9:F10)')

        gov = load_workbook(io.BytesIO(
            self.officer_client.get(url, {'kind': 'division', 'own': 'GOV'}).content))
        self.assertEqual(gov['DIVISION']['E9'].value, 'BUSINDE SECONDARY SCHOOL')
        self.assertEqual(gov['DIVISION']['A10'].value, 'TOTAL')

        wb = load_workbook(io.BytesIO(self.officer_client.get(url, {'kind': 'subjects'}).content))
        self.assertEqual(wb.sheetnames[0], 'LIST OF SUBJECTS')
        self.assertIn('MATHS', wb.sheetnames)
        self.assertIn('KISW', wb.sheetnames)
        self.assertEqual(wb['MATHS']['B6'].value, 'MATHEMATICS')
        self.assertTrue(str(wb['LIST OF SUBJECTS']['D9'].value).endswith('!$B$6'))

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


class JointRecomputeTests(TestCase):
    """recompute_all_processed_results must repair rows the grade-tie bug
    damaged, including rows of a DC Joint exam.

    The tiebreak bug's signature is "division and points unchanged,
    total/average/counted_subjects wrong" — a report that only watched
    division would score such a run as 0 changes, so the diff has to cover
    every stored field. DC Joint needs no special path: attach_school()
    gives each member school a plain Exam row, which the command
    recomputes like any other exam; --joint just scopes the queryset.
    """

    databases = {'default', 'results'}

    def setUp(self):
        self.school = School.objects.create(
            name='Bernard Secondary School', region='Kagera', district='Kyerwa',
            ward='Isingiro', ownership='PRIVATE', level='secondary')
        self.joint = JointExam.objects.create(
            name='FORM ONE JOINT', form=1, year=2026,
            district='Kyerwa', region='Kagera')
        self.subjects = []
        for name in ('Agriculture', 'Biology', 'Chemistry', 'Divinity', 'English',
                     'Geography', 'History', 'Zoology'):
            # Seeded subjects already exist in the test DB — reuse them.
            subject, _ = Subject.objects.get_or_create(name=name)
            self.subjects.append(subject)
        self.joint.subjects.set(self.subjects)
        self.exam = self.joint.attach_school(self.school)
        self.student = Student.objects.create(
            first_name='Asha', last_name='Test', gender='F')
        strong = dict(zip(
            ('Agriculture', 'Biology', 'Chemistry', 'Divinity', 'English', 'Geography'),
            (80, 70, 68, 50, 49, 47),
        ))
        # History & Zoology share grade D — the old name-ordered sort kept
        # Zoology and threw away History, costing the candidate 13 marks.
        marks = {**strong, 'History': 31, 'Zoology': 44}
        by_name = dict(zip(
            ('Agriculture', 'Biology', 'Chemistry', 'Divinity', 'English', 'Geography',
             'History', 'Zoology'), self.subjects))
        for name, score in marks.items():
            ExamResult.objects.create(
                exam=self.exam, student=self.student, subject=by_name[name], score=score)

    def _stale_row(self):
        """The row as the buggy code wrote it: 6 strong + Zoology = 395."""
        from .services.upload_processing_service import recompute_processed_results_for_exam
        recompute_processed_results_for_exam(self.exam)
        row = ProcessedResult.objects.get(exam=self.exam, student=self.student)
        row.total_score = 395
        row.average_score = 56.43  # 395/7 as the buggy sort wrote it
        row.counted_subjects = ', '.join(
            n for n in ('Agriculture', 'Biology', 'Chemistry', 'Divinity',
                        'English', 'Geography', 'History'))
        row.save(update_fields=['total_score', 'average_score', 'counted_subjects'])
        return row

    def test_command_repairs_a_grade_tie_row_of_a_joint_exam(self):
        stale = self._stale_row()
        self.assertEqual(stale.total_score, 395)

        out = io.StringIO()
        call_command('recompute_all_processed_results', '--exam', self.exam.pk,
                     '--in-process', stdout=out)
        report = out.getvalue()

        fixed = ProcessedResult.objects.get(exam=self.exam, student=self.student)
        self.assertEqual(fixed.total_score, 408)          # 31 -> 44 recovered
        self.assertEqual(float(fixed.average_score), 58.29)
        self.assertIn('Zoology', fixed.counted_subjects)   # 44 recovered
        self.assertNotIn('History', fixed.counted_subjects)  # 31 given up
        # points/division were never wrong and must not drift
        self.assertEqual(fixed.points, stale.points)
        self.assertEqual(fixed.division, stale.division)
        # the diff must NAME the fields it fixed, not just count a row
        self.assertIn('total_score', report)
        self.assertIn('average_score', report)
        self.assertIn('counted_subjects', report)

    def test_dry_run_reports_the_fix_but_saves_nothing(self):
        self._stale_row()
        out = io.StringIO()
        call_command('recompute_all_processed_results', '--exam', self.exam.pk,
                     '--in-process', '--dry-run', stdout=out)
        self.assertIn('DRY RUN', out.getvalue())
        self.assertEqual(
            ProcessedResult.objects.get(exam=self.exam, student=self.student).total_score,
            395,
        )

    def test_joint_filter_scopes_the_run_to_that_wilaya(self):
        self._stale_row()   # give this joint's exam a cached row to repair
        other = School.objects.create(
            name='Businde Secondary School', region='Kagera', district='Kyerwa',
            level='secondary')
        other_joint = JointExam.objects.create(
            name='FORM ONE JOINT (BWANI)', form=1, year=2026, district='Kyerwa')
        other_exam = other_joint.attach_school(other)
        other_student = Student.objects.create(first_name='Businde', last_name='T', gender='M')
        subject, _ = Subject.objects.get_or_create(name='Mathematics')
        ExamResult.objects.create(
            exam=other_exam, student=other_student, subject=subject, score=70)
        from .services.upload_processing_service import recompute_processed_results_for_exam
        recompute_processed_results_for_exam(other_exam)
        untouched = ProcessedResult.objects.get(exam=other_exam, student=other_student)
        untouched.total_score = 1
        untouched.save(update_fields=['total_score'])

        call_command('recompute_all_processed_results', '--joint', self.joint.pk,
                     '--in-process', stdout=io.StringIO())
        self.assertEqual(
            ProcessedResult.objects.get(exam=self.exam, student=self.student).total_score,
            408,
        )
        self.assertEqual(
            ProcessedResult.objects.get(exam=other_exam, student=other_student).total_score,
            1, 'mtihani wa joint nyingine haukubadilishwa',
        )


class AcademicJoinTests(TestCase):
    """Mtaaluma: "Join Kyerwa DC Joint Exams" → kata, umiliki, shule → alama kwenye Marks Entry."""

    databases = {'default', 'results'}

    def setUp(self):
        self.mine = School.objects.create(
            name='Kaisho Secondary School', region='Kagera', district='Kyerwa Dc', level='secondary')
        # Rekodi ya orodha ya Halmashauri (setup_kyerwa_district) — haina chochote
        self.placeholder = School.objects.create(
            name='Kaisho Secondary School', region='Kagera', district='Kyerwa',
            ward='Isingiro', ownership='PRIVATE', level='secondary')
        self.taken = School.objects.create(
            name='Businde Secondary School', region='Kagera', district='Kyerwa', level='secondary')
        TeacherAccount.objects.create(
            email='ac@businde.sc.tz', role=TeacherAccount.ROLE_ACADEMIC, school=self.taken)
        self.officer = TeacherAccount.objects.create(
            email='deo@kyerwa.go.tz', role=TeacherAccount.ROLE_DISTRICT,
            district='Kyerwa', region='Kagera')
        self.maths = Subject.objects.create(name='Mathematics')
        self.joint = JointExam.objects.create(
            name='FORM ONE MID TERM JOINT', form=1, year=2026, district='Kyerwa', region='Kagera')
        self.joint.subjects.set([self.maths])

        self.academic = TeacherAccount.objects.create(
            email='ac@kaisho.sc.tz', role=TeacherAccount.ROLE_ACADEMIC, school=self.mine)
        self.client = Client()
        self.client.force_login(self.academic, backend=LOGIN_BACKEND)

    def _join(self, school, ward='Isingiro', ownership='PRIVATE'):
        return self.client.post(reverse('district_joint_join'), {
            'ward': ward, 'ownership': ownership, 'school_id': school.pk,
        })

    def test_nav_link_and_join_page(self):
        home = self.client.get(reverse('academic_dashboard'))
        self.assertContains(home, 'Kyerwa DC Joint')
        # Bado hajajiunga → anapelekwa kwenye fomu
        self.assertRedirects(self.client.get(reverse('district_joint_home')),
                             reverse('district_joint_join'), fetch_redirect_response=False)
        page = self.client.get(reverse('district_joint_join'))
        self.assertContains(page, 'Businde Secondary School')

    def test_join_takes_over_the_empty_council_record(self):
        resp = self._join(self.placeholder)
        self.assertRedirects(resp, reverse('district_joint_home'), fetch_redirect_response=False)
        self.assertFalse(School.objects.filter(pk=self.placeholder.pk).exists())
        self.mine.refresh_from_db()
        self.assertEqual((self.mine.ward, self.mine.ownership, self.mine.joint_member),
                         ('ISINGIRO', 'PRIVATE', True))
        # Joint iliyopo imepewa shule hii, na somo liko tayari kwa Marks Entry
        exam = Exam.objects.get(joint_exam=self.joint, school=self.mine)
        self.assertTrue(SubjectSubmission.objects.filter(exam=exam, subject=self.maths).exists())
        self.assertEqual(self.client.get(reverse('district_joint_home')).status_code, 200)

    def test_cannot_take_a_school_that_is_already_in_use(self):
        resp = self._join(self.taken)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(School.objects.filter(pk=self.taken.pk).exists())
        self.mine.refresh_from_db()
        self.assertFalse(self.mine.joint_member)

    def test_joint_created_later_reaches_joined_schools(self):
        self._join(self.mine)
        officer = Client()
        officer.force_login(self.officer, backend=LOGIN_BACKEND)
        officer.post(reverse('joint_exam_create'), {
            'name': 'FORM TWO TERMINAL JOINT', 'form': '2', 'year': '2026',
            'subjects': [self.maths.pk],
        })
        later = JointExam.objects.get(name='FORM TWO TERMINAL JOINT')
        self.assertTrue(Exam.objects.filter(joint_exam=later, school=self.mine).exists())
        self.assertFalse(Exam.objects.filter(joint_exam=later, school=self.taken).exists())

    def test_academic_outside_the_district_sees_nothing(self):
        other = School.objects.create(name='Nje', region='Kagera', district='Karagwe')
        acct = TeacherAccount.objects.create(
            email='ac@nje.sc.tz', role=TeacherAccount.ROLE_ACADEMIC, school=other)
        c = Client()
        c.force_login(acct, backend=LOGIN_BACKEND)
        self.assertNotContains(c.get(reverse('academic_dashboard')), 'DC Joint')
        self.assertRedirects(c.get(reverse('district_joint_home')), reverse('home'),
                             fetch_redirect_response=False)
