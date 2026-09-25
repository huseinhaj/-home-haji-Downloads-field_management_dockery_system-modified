"""Masomo kwa aina ya shule (primary vs secondary) + Academic
'Ongeza Mwanafunzi & Jaza Alama' flow.

Inathibitisha:
  - subjects_for_school: msingi anaona masomo ya msingi/both/blank tu;
    sekondari ya sekondari/both/blank tu; school=None inaona yote.
  - Subject list za page zote (Masomo Yangu, Wanafunzi wa Kidato,
    Ratiba, Speech Entry, Assign Teacher) zinafuata aina ya shule.
  - academic_add_student_marks: chagua exam type → ongeza mwanafunzi
    (jina kamili + jinsia) → orodha yote ya masomo ya mtihani → alama
    zinahifadhiwa → mwanafunzi anaonekana kwenye matokeo ya exam type
    na level (Form/Darasa).
"""
import re

from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    Exam, ExamResult, FormStudent, ProcessedResult, School, Student,
    Subject, SubjectSubmission, TeacherAccount,
)
from .utils import subjects_for_school


class SubjectsForSchoolTests(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.primary_school = School.objects.create(
            name='Shule ya Msingi', region='Dodoma', district='Dodoma',
            level='primary', current_academic_year=2026,
        )
        cls.secondary_school = School.objects.create(
            name='Sekondari', region='Dodoma', district='Dodoma',
            level='secondary', current_academic_year=2026,
        )
        cls.hisabati = Subject.objects.create(name='Hisabati', code='P03', level='primary')
        cls.maths = Subject.objects.create(name='Mathematics', code='S01', level='secondary')
        cls.kiswahili = Subject.objects.create(name='Kiswahili', code='S06', level='secondary')
        cls.pe = Subject.objects.create(name='Physical Education', code='B01', level='both')
        cls.legacy = Subject.objects.create(name='Fine Art', level='')

    def test_primary_school_sees_primary_only(self):
        names = set(subjects_for_school(self.primary_school).values_list('name', flat=True))
        self.assertIn('Hisabati', names)
        self.assertIn('Physical Education', names)   # both
        self.assertIn('Fine Art', names)             # legacy blank
        self.assertNotIn('Mathematics', names)       # sekondari — haionekani
        self.assertNotIn('Kiswahili', names)

    def test_secondary_school_sees_secondary_only(self):
        names = set(subjects_for_school(self.secondary_school).values_list('name', flat=True))
        self.assertIn('Mathematics', names)
        self.assertIn('Kiswahili', names)
        self.assertIn('Physical Education', names)   # both
        self.assertIn('Fine Art', names)             # legacy blank
        self.assertNotIn('Hisabati', names)          # msingi — haionekani

    def test_no_school_sees_everything(self):
        # App startup ina-seed masomo mengi ya ziada — hapa tunathibitisha
        # kila mada yetu iko, si usawa kamili wa seti.
        names = set(subjects_for_school(None).values_list('name', flat=True))
        for expected in ('Hisabati', 'Mathematics', 'Kiswahili', 'Physical Education', 'Fine Art'):
            self.assertIn(expected, names)


class SubjectListPagesRespectSchoolTypeTests(TestCase):
    """Page list zote za masomo zinafuata aina ya shule."""
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Msingi A', region='Dodoma', district='Dodoma',
            level='primary', current_academic_year=2026,
        )
        cls.academic = TeacherAccount.objects.create(
            email='academic@msingi.ac.tz', full_name='Mtaaluma', role='ACADEMIC', school=cls.school,
        )
        cls.academic.set_password('Pass1234!')
        cls.academic.save()
        Subject.objects.create(name='Hisabati', code='P03', level='primary')
        Subject.objects.create(name='Physics', code='S03', level='secondary')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')

    def _assert_subjects_on_page(self, url_name, must_have, must_not_have):
        resp = self.client.get(reverse(url_name))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        for name in must_have:
            self.assertIn(name, content)
        for name in must_not_have:
            self.assertNotIn(name, content)

    def test_select_my_subjects(self):
        self._assert_subjects_on_page(
            'select_my_subjects', must_have=['Hisabati'], must_not_have=['Physics'],
        )

    def test_manage_teachers(self):
        self._assert_subjects_on_page(
            'manage_teachers', must_have=['Hisabati'], must_not_have=['Physics'],
        )

    def test_upload_form_students(self):
        # ?form= inahitajika — modal ya assign-subjects inarudiwa kwa kila
        # mwanafunzi wa form ile, bila form hakuna orodha ya masomo.
        # NB: template ina neno 'Physics' kwenye maandishi ya msaada tu —
        # tunakagua <option>, si maandishi yote.
        resp = self.client.get(reverse('upload_form_students') + '?form=3')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('>Hisabati</option>', content)
        self.assertNotIn('>Physics</option>', content)

    def test_assign_teacher_form(self):
        self._assert_subjects_on_page(
            'assign_teacher_form', must_have=['Hisabati'], must_not_have=['Physics'],
        )

    def test_class_timetable_assignments(self):
        self._assert_subjects_on_page(
            'teaching_assignment_manage', must_have=['Hisabati'], must_not_have=['Physics'],
        )

    def test_speech_entry(self):
        self._assert_subjects_on_page(
            'speech_entry_page', must_have=['Hisabati'], must_not_have=['Physics'],
        )


class AcademicAddStudentMarksTests(TestCase):
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Msingi B', region='Dodoma', district='Dodoma',
            level='primary', current_academic_year=2026,
        )
        cls.academic = TeacherAccount.objects.create(
            email='acad@msingi.ac.tz', full_name='Mtaaluma B', role='ACADEMIC', school=cls.school,
        )
        cls.academic.set_password('Pass1234!')
        cls.academic.save()
        cls.exam = Exam.objects.create(
            name='Midterm 2026', year=2026, form=3, school=cls.school,
            exam_type='MIDTERM',
        )
        cls.sub1 = Subject.objects.create(name='Kiswahili')
        cls.sub2 = Subject.objects.create(name='Hesabu')
        cls.sub3 = Subject.objects.create(name='Sayansi')
        for s in (cls.sub1, cls.sub2, cls.sub3):
            SubjectSubmission.objects.create(exam=cls.exam, subject=s)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        self.add_url = reverse('academic_add_student_marks')

    def test_page_requires_academic(self):
        teacher = TeacherAccount.objects.create(
            email='mwalimu@x.tz', full_name='Mwalimu', role='TEACHER', school=self.school,
        )
        c = Client()
        c.force_login(teacher, backend='results.backends.ResultsAuthBackend')
        resp = c.get(self.add_url)
        self.assertEqual(resp.status_code, 403)

    def test_page_shows_exam_and_class(self):
        # Subject list inaonekana baada ya ku-add mwanafunzi (AJAX) — hapa
        # tunathibitisha page inachagua exam na inaonyesha level label sahihi.
        resp = self.client.get(self.add_url + f'?exam={self.exam.id}')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('Midterm 2026', content)
        self.assertIn('Darasa la', content)  # primary class label

    def test_grade_chip_receives_selected_exam_form(self):
        resp = self.client.get(self.add_url + f'?exam={self.exam.id}')
        content = resp.content.decode()
        self.assertIn("const EXAM_FORM = Number('3');", content)
        self.assertIn("const IS_ADVANCED = [5, 6].includes(EXAM_FORM);", content)

    def test_grade_chip_switches_for_advanced_forms(self):
        secondary_school = School.objects.create(
            name='Sekondari Advanced', region='Dodoma', district='Dodoma',
            level='secondary', current_academic_year=2026,
        )
        academic = TeacherAccount.objects.create(
            email='advanced@secondary.ac.tz', full_name='Mtaaluma Advanced',
            role='ACADEMIC', school=secondary_school,
        )
        client = Client()
        client.force_login(academic, backend='results.backends.ResultsAuthBackend')
        for form in (5, 6):
            exam = Exam.objects.create(
                name=f'Advanced Mock {form}', year=2026, form=form, school=secondary_school,
            )
            content = client.get(self.add_url + f'?exam={exam.id}').content.decode()
            self.assertIn(f"const EXAM_FORM = Number('{form}');", content)

    def test_page_renders_non_empty_csrf_token_for_ajax(self):
        """Regression: base.html haina hidden CSRF input, so the page's
        fetch() calls found no token and every 'Add Student' POST died
        with a 403 before reaching the view. The page must render its own
        non-empty csrfmiddlewaretoken (same pattern as marks_entry)."""
        resp = self.client.get(self.add_url + f'?exam={self.exam.id}')
        content = resp.content.decode()
        match = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"', content,
        )
        self.assertIsNotNone(match, 'Page must render a csrfmiddlewaretoken input for its AJAX calls.')
        self.assertTrue(match.group(1).strip(), 'CSRF token value must not be empty.')

    def test_add_student_returns_subjects(self):
        resp = self.client.post(
            self.add_url,
            data={
                'action': 'add_student', 'exam_id': self.exam.id,
                'first_name': 'Amina', 'middle_name': 'Juma', 'last_name': 'Hassan',
                'gender': 'F',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['created'])
        self.assertEqual(data['student']['name'], 'Amina Juma Hassan')
        subject_names = {s['name'] for s in data['subjects']}
        self.assertEqual(subject_names, {'Kiswahili', 'Hesabu', 'Sayansi'})

        # Roster row created (FormStudent) — ameingia kwenye Darasa la 3
        fs = FormStudent.objects.get(school=self.school, form=3, first_name='Amina')
        self.assertEqual(fs.gender, 'F')
        self.assertTrue(fs.is_active)

    def test_add_student_dedups_existing(self):
        Student.objects.create(first_name='Baraka', last_name='Mkwawa', gender='M')
        resp = self.client.post(
            self.add_url,
            data={
                'action': 'add_student', 'exam_id': self.exam.id,
                'first_name': 'Baraka', 'last_name': 'Mkwawa', 'gender': 'M',
            },
            content_type='application/json',
        )
        data = resp.json()
        self.assertFalse(data['created'])
        self.assertEqual(Student.objects.filter(first_name='Baraka', last_name='Mkwawa').count(), 1)

    def test_save_marks_creates_results_and_recomputes(self):
        # 1. Add student
        resp = self.client.post(
            self.add_url,
            data={
                'action': 'add_student', 'exam_id': self.exam.id,
                'first_name': 'Zawadi', 'last_name': 'Mbwana', 'gender': 'F',
            },
            content_type='application/json',
        )
        student_id = resp.json()['student']['id']

        # 2. Save marks across ALL exam subjects
        resp = self.client.post(
            self.add_url,
            data={
                'action': 'save_marks', 'exam_id': self.exam.id, 'student_id': student_id,
                'entries': [
                    {'subject_id': self.sub1.id, 'score': 82},
                    {'subject_id': self.sub2.id, 'score': 66},
                    {'subject_id': self.sub3.id, 'score': 'X'},  # absent
                ],
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        results = {r.subject_id: r for r in ExamResult.objects.filter(exam=self.exam)}
        self.assertEqual(results[self.sub1.id].score, 82)
        self.assertEqual(results[self.sub2.id].score, 66)
        self.assertTrue(results[self.sub3.id].is_absent)

        # 3. Mwanafunzi anaonekana kwenye matokeo ya exam (ProcessedResult)
        pr = ProcessedResult.objects.get(exam=self.exam, student_id=student_id)
        self.assertEqual(pr.position, 1)

    def test_save_marks_validates_range(self):
        resp = self.client.post(
            self.add_url,
            data={
                'action': 'add_student', 'exam_id': self.exam.id,
                'first_name': 'Doto', 'last_name': 'Pole', 'gender': 'M',
            },
            content_type='application/json',
        )
        student_id = resp.json()['student']['id']
        resp = self.client.post(
            self.add_url,
            data={
                'action': 'save_marks', 'exam_id': self.exam.id, 'student_id': student_id,
                'entries': [{'subject_id': self.sub1.id, 'score': 150}],
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_wrong_school_exam_rejected(self):
        other_school = School.objects.create(
            name='Sekondari Nyengine', region='Dodoma', district='Dodoma',
            level='secondary', current_academic_year=2026,
        )
        other_exam = Exam.objects.create(
            name='Mock 2026', year=2026, form=2, school=other_school,
        )
        resp = self.client.post(
            self.add_url,
            data={
                'action': 'add_student', 'exam_id': other_exam.id,
                'first_name': 'Jina', 'last_name': 'Mwingine', 'gender': 'M',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_marks_entry_roster_picks_up_new_student(self):
        """Mwanafunzi aliyeeongezwa anaonekana pia kwenye Marks Entry ya
        mwalimu (rosti ya FormStudent inamlisha)."""
        resp = self.client.post(
            self.add_url,
            data={
                'action': 'add_student', 'exam_id': self.exam.id,
                'first_name': 'Neema', 'last_name': 'Kabuje', 'gender': 'F',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        # Rosti ya darasa (FormStudent) ina mwanafunzi huyu — ndiyo
        # inayomlisha marks entry na PDFs za scoresheet.
        self.assertTrue(
            FormStudent.objects.filter(
                school=self.school, form=3, is_active=True,
                first_name='Neema', last_name='Kabuje',
            ).exists()
        )

    # ── Dropdown ya wanafunzi / masomo / kuondoa (2026-09-23) ──────────────

    def _post(self, **payload):
        return self.client.post(self.add_url, data={'exam_id': self.exam.id, **payload},
                                content_type='application/json')

    def test_page_lists_roster_and_marked_students_once(self):
        FormStudent.objects.create(school=self.school, form=3, academic_year=2026,
                                   admission_no='A1', first_name='Asha', middle_name='Ali',
                                   last_name='Musa', gender='F')
        # Ana alama kwenye mtihani + yupo kwenye rosti (herufi tofauti) → mara moja tu
        st = Student.objects.create(first_name='ASHA', middle_name='ALI', last_name='MUSA', gender='F')
        ExamResult.objects.create(exam=self.exam, student=st, subject=self.sub1, score=70)
        FormStudent.objects.create(school=self.school, form=4, academic_year=2026,
                                   admission_no='B1', first_name='Juma', last_name='Darasa4', gender='M')
        resp = self.client.get(self.add_url + f'?exam={self.exam.id}')
        students = resp.context['exam_students']
        self.assertEqual([e['key'] for e in students], [f's{st.id}'])
        self.assertTrue(students[0]['has_marks'])

    def test_select_student_returns_existing_marks(self):
        fs = FormStudent.objects.create(school=self.school, form=3, academic_year=2026,
                                        admission_no='A2', first_name='Bahati', middle_name='K',
                                        last_name='Juma', gender='M')
        data = self._post(action='select_student', key=f'f{fs.id}').json()
        sid = data['student']['id']
        self.assertEqual(data['marks'], {})
        ExamResult.objects.create(exam=self.exam, student_id=sid, subject=self.sub2, score=55)
        data = self._post(action='select_student', key=f's{sid}').json()
        self.assertEqual(data['marks'], {str(self.sub2.id): 55})
        self.assertEqual(len(data['subjects']), 3)

    def test_add_student_with_same_three_names_reuses_roster_row(self):
        FormStudent.objects.create(school=self.school, form=3, academic_year=2026,
                                   admission_no='A3', first_name='Pili', middle_name='Hamisi',
                                   last_name='Said', gender='F')
        for _ in range(2):
            resp = self._post(action='add_student', first_name='PILI', middle_name='hamisi',
                              last_name='Said', gender='F')
            self.assertEqual(resp.status_code, 200)
        self.assertEqual(FormStudent.objects.filter(school=self.school, first_name__iexact='pili').count(), 1)
        self.assertEqual(Student.objects.filter(first_name__iexact='pili').count(), 1)

    def test_add_student_in_other_form_is_rejected(self):
        """Isingiro 2026-09-23: wanafunzi wa Form 5 waliingia matokeo ya Form 6."""
        FormStudent.objects.create(school=self.school, form=2, academic_year=2026,
                                   admission_no='A4', first_name='Derick', middle_name='Ngalinda',
                                   last_name='Dismas', gender='M')
        resp = self._post(action='add_student', first_name='Derick', middle_name='Ngalinda',
                          last_name='Dismas', gender='M')
        self.assertEqual(resp.status_code, 409)
        self.assertFalse(FormStudent.objects.filter(school=self.school, form=3,
                                                    first_name='Derick').exists())

    def test_add_subject_to_existing_exam(self):
        data = self._post(action='add_subject', subject_name='Computer Studies').json()
        self.assertTrue(data['created'])
        self.assertTrue(SubjectSubmission.objects.filter(
            exam=self.exam, subject_id=data['subject']['id']).exists())
        data = self._post(action='add_subject', subject_id=self.sub1.id).json()
        self.assertFalse(data['created'])

    def test_remove_student_from_exam_results(self):
        keep = Student.objects.create(first_name='Kaa', last_name='Mimi', gender='M')
        gone = Student.objects.create(first_name='Toka', last_name='Wewe', gender='M')
        FormStudent.objects.create(school=self.school, form=3, academic_year=2026,
                                   admission_no='A5', first_name='Toka', last_name='Wewe', gender='M')
        ExamResult.objects.create(exam=self.exam, student=keep, subject=self.sub1, score=40)
        ExamResult.objects.create(exam=self.exam, student=gone, subject=self.sub1, score=90)
        resp = self._post(action='remove_student', student_id=gone.id, remove_from_roster=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ExamResult.objects.filter(exam=self.exam, student_id=gone.id).exists())
        self.assertFalse(ProcessedResult.objects.filter(exam=self.exam, student_id=gone.id).exists())
        self.assertFalse(Student.objects.filter(id=gone.id).exists())  # yatima
        self.assertFalse(FormStudent.objects.get(admission_no='A5').is_active)
        self.assertEqual(ProcessedResult.objects.get(exam=self.exam, student=keep).position, 1)


    def test_roster_delete_with_remove_results_clears_pdf_rows(self):
        other_exam = Exam.objects.create(name='Annual 2026', year=2026, form=3,
                                         school=self.school, exam_type='ANNUAL')
        fs = FormStudent.objects.create(school=self.school, form=3, academic_year=2026,
                                        admission_no='R1', first_name='Futa', middle_name='Kabisa',
                                        last_name='Sasa', gender='M')
        gone = Student.objects.create(first_name='FUTA', middle_name='KABISA', last_name='SASA', gender='M')
        keep = Student.objects.create(first_name='Baki', last_name='Hapa', gender='F')
        for ex in (self.exam, other_exam):
            ExamResult.objects.create(exam=ex, student=gone, subject=self.sub1, score=95)
            ExamResult.objects.create(exam=ex, student=keep, subject=self.sub1, score=50)
        url = reverse('delete_form_student', args=[fs.id])
        self.client.post(url, {'remove_results': '1'})
        self.assertFalse(FormStudent.objects.filter(id=fs.id).exists())
        self.assertFalse(ExamResult.objects.filter(student_id=gone.id).exists())
        self.assertFalse(Student.objects.filter(id=gone.id).exists())
        for ex in (self.exam, other_exam):
            self.assertEqual(ProcessedResult.objects.get(exam=ex, student=keep).position, 1)

    def test_roster_delete_without_flag_keeps_marks(self):
        fs = FormStudent.objects.create(school=self.school, form=3, academic_year=2026,
                                        admission_no='R2', first_name='Orodha', last_name='Tu', gender='M')
        st = Student.objects.create(first_name='Orodha', last_name='Tu', gender='M')
        ExamResult.objects.create(exam=self.exam, student=st, subject=self.sub1, score=60)
        self.client.post(reverse('delete_form_student', args=[fs.id]))
        self.assertFalse(FormStudent.objects.filter(id=fs.id).exists())
        self.assertTrue(ExamResult.objects.filter(student=st).exists())



class MarksEntryRosterPerfTests(TestCase):
    """Performance ya Continue (marks_entry): rosti kubwa bila queries N+1.

    Kulikuwa na lalamiko ya walimu kuwa Continue inachelea — chanzo:
    get_or_create (2 queries) kwa kila mwanafunzi + 2 subject queries kwa
    kila mwanafunzi kwenye rosti yote kila wakati page inapofunguliwa.
    """
    databases = {'default', 'results'}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='Sekondari Perf', region='Dodoma', district='Dodoma',
            level='secondary', current_academic_year=2026,
        )
        cls.teacher = TeacherAccount.objects.create(
            email='perf@sekondari.ac.tz', full_name='Mwalimu Perf',
            role='TEACHER', school=cls.school,
        )
        cls.exam = Exam.objects.create(
            name='Terminal 2026', year=2026, form=4, school=cls.school,
            exam_type='TERMINAL',
        )
        cls.subject = Subject.objects.create(name='Biology', level='secondary')
        # Mwalimu lazima awe na somo ("Masomo Yangu") — vinginevyo marks
        # entry inamrudisha select_my_subjects (302).
        cls.teacher.subjects.add(cls.subject)
        # Rosti ya wanafunzi 120 (roster halisi ya darasa)
        FormStudent.objects.bulk_create([
            FormStudent(
                school=cls.school, form=4, academic_year=2026,
                admission_no=f'S{i:04d}',
                first_name=f'Mwanafunzi{i}', last_name=f'Mwisho{i}',
                gender='M' if i % 2 else 'F',
            ) for i in range(120)
        ])
        # Baadhi wana somo zilizopangiwa (option subjects)
        for fs in FormStudent.objects.all()[:40]:
            fs.subjects.add(cls.subject)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')

    def test_marks_entry_bounded_queries(self):
        """Continue kwenye rosti ya wanafunzi 120 lazima itumie idadi
        ndogo, isiyobadilika queries — si 2 queries kwa kila mwanafunzi."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        url = reverse('marks_entry') + f'?exam={self.exam.id}&subject={self.subject.id}'
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # Query >= roster + lookup + M2M + idx — lakini lazima iwe chini ya
        # 100, siyo ~1000+ kama zamani (2 * 120 + 2 * 120 = 480+).
        self.assertLess(
            len(ctx), 100,
            f'Marks entry inatumia queries {len(ctx)} — N+1 imerudi?',
        )
        # Roster yote 40 walio na somo hili + 80 wasio na lolote
        data = resp.context['class_students_json']
        self.assertIn('Mwanafunzi1', data)

    def test_marks_entry_resolves_students_correctly(self):
        """Rosti inaonyesha wanafunzi wote (na somo au bila) — na Student
        records zinaundwa mara moja tu (get_or_create dedup haijavurugwa)."""
        url = reverse('marks_entry') + f'?exam={self.exam.id}&subject={self.subject.id}'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        students = Student.objects.filter(
            first_name__startswith='Mwanafunzi',
        )
        self.assertEqual(students.count(), 120)   # hakuna duplicates
        # Pili — hakuna Student mpya (get_or_create bado inalinda)
        self.client.get(url)
        self.assertEqual(Student.objects.filter(
            first_name__startswith='Mwanafunzi',
        ).count(), 120)
