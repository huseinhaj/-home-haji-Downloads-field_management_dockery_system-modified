import json
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
import pandas as pd

from .models import ClassTimetableEntry, Exam, ExamResult, ProcessedResult, School, SpeechSubmissionSession, Student, Subject, TeacherAccount, TeachingAssignment, TimeSlot
from .services.class_timetable_service import TimetableConflict, generate_class_timetable, save_class_timetable, set_single_cell
from .services.scoresheet_ocr_service import (
    ScoreSheetOCRError,
    _clean_rows,
    _extract_json_array,
    _is_pdf,
    _load_page_images,
)
from .services.speech_submission_service import (
    create_or_get_session,
    extract_name_and_score,
    fuzzy_match_student_name,
	get_session_status,
	submit_speech_entries_batch,
	SpeechMatchReviewRequired,
	SpeechSubmissionError,
	parse_spoken_score,
    submit_speech_entry,
)
from .utils import (
	extract_subject_columns,
	normalize_gender,
	normalize_subject_name,
	parse_score,
)


class ResultsUtilsTests(TestCase):
	def test_normalize_subject_name_maps_common_aliases(self):
		self.assertEqual(normalize_subject_name('phy'), 'Physics')
		self.assertEqual(normalize_subject_name(' mathematics '), 'Mathematics')

	def test_extract_subject_columns_excludes_student_identity_fields(self):
		df = pd.DataFrame(columns=['First Name', 'Last Name', 'Gender', 'Physics', 'Chemistry'])
		self.assertEqual(extract_subject_columns(df), ['Physics', 'Chemistry'])

	def test_parse_score_handles_invalid_and_numeric_values(self):
		self.assertEqual(parse_score('78'), 78)
		self.assertEqual(parse_score(44.8), 44)
		self.assertIsNone(parse_score('not-a-number'))
		self.assertIsNone(parse_score(float('nan')))

	def test_normalize_gender_defaults_to_male_for_unknown_input(self):
		self.assertEqual(normalize_gender('Female'), 'F')
		self.assertEqual(normalize_gender('male'), 'M')
		self.assertEqual(normalize_gender(''), 'M')


class SpeechSubmissionServiceTests(TestCase):
	databases = {'default', 'results'}

	def setUp(self):
		self.exam = Exam.objects.create(name='Midterm 1', year=2026, form=1)
		self.subject = Subject.objects.create(name='Mathematics')
		self.student_one = Student.objects.create(first_name='Amina', middle_name='', last_name='Juma', gender='F')
		self.student_two = Student.objects.create(first_name='Peter', middle_name='', last_name='Mushi', gender='M')

	def test_extract_name_and_score_from_transcript(self):
		name, score = extract_name_and_score('Amina Juma 78')
		self.assertEqual(name, 'amina juma')
		self.assertEqual(score, 78)

	def test_extract_name_and_score_handles_spaced_digits(self):
		name, score = extract_name_and_score('Amina Juma 8 0')
		self.assertEqual(name, 'amina juma')
		self.assertEqual(score, 80)

	def test_parse_spoken_score_handles_english_words(self):
		self.assertEqual(parse_spoken_score('Amina Juma eighty five'), 85)

	def test_parse_spoken_score_handles_english_filler_words(self):
		self.assertEqual(parse_spoken_score('Amina Juma score is eighty five'), 85)

	def test_parse_spoken_score_handles_swahili_words(self):
		self.assertEqual(parse_spoken_score('Amina Juma hamsini na tano'), 55)

	def test_parse_spoken_score_handles_swahili_phonetic_variants(self):
		self.assertEqual(parse_spoken_score('sistini'), 60)
		self.assertEqual(parse_spoken_score('Juma ali sistini'), 60)
		self.assertEqual(parse_spoken_score('Anasaiti, Nishinambili, Rasibari, Elateni, Yumaari, Tisinani.'), 90)
		self.assertEqual(parse_spoken_score('nishinambili'), 22)

	def test_extract_name_and_score_handles_non_trailing_spoken_score(self):
		name, score = extract_name_and_score('Juma ali sitini na mbili leo')
		self.assertEqual(score, 62)
		self.assertIn('juma', name)

	def test_fuzzy_match_student_name_returns_candidates(self):
		student, confidence, candidates = fuzzy_match_student_name('Amina Juma', Student.objects.all(), threshold=0.5)
		self.assertIsNotNone(student)
		self.assertEqual(student.id, self.student_one.id)
		self.assertGreaterEqual(confidence, 0.5)
		self.assertGreaterEqual(len(candidates), 2)

	def test_submit_speech_entry_finalizes_session_when_complete(self):
		session = create_or_get_session(exam=self.exam, subject=self.subject, teacher_name='Teacher One', expected_student_count=2)
		result_one = submit_speech_entry(
			session=session,
			transcript='Amina Juma 75',
			confirm_student_id=self.student_one.id,
		)
		self.assertEqual(result_one['score'], 75)
		result_two = submit_speech_entry(
			session=session,
			transcript='Peter Mushi 66',
			confirm_student_id=self.student_two.id,
		)
		session.refresh_from_db()
		self.assertEqual(result_two['score'], 66)
		self.assertEqual(session.status, SpeechSubmissionSession.STATUS_FINALIZED)

	def test_duplicate_submission_overwrites_existing_value(self):
		session = create_or_get_session(exam=self.exam, subject=self.subject, teacher_name='Teacher One', expected_student_count=2)
		submit_speech_entry(
			session=session,
			transcript='Amina Juma 75',
			confirm_student_id=self.student_one.id,
		)
		result = submit_speech_entry(
			session=session,
			transcript='Amina Juma 80',
			confirm_student_id=self.student_one.id,
		)
		self.assertEqual(result['score'], 80)

	def test_submit_speech_entries_batch_saves_multiple_students(self):
		session = create_or_get_session(
			exam=self.exam,
			subject=self.subject,
			teacher_name='Teacher One',
			expected_student_count=2,
			roster_student_ids=[self.student_one.id, self.student_two.id],
		)
		result = submit_speech_entries_batch(
			session=session,
			transcript='Amina Juma sabini na mbili. Peter Mushi themanini na moja.',
		)
		self.assertEqual(result['saved_count'], 2)
		self.assertEqual(result['skipped_count'], 0)

	def test_low_confidence_match_requires_review(self):
		session = create_or_get_session(exam=self.exam, subject=self.subject, teacher_name='Teacher One', expected_student_count=1)
		with self.assertRaises(SpeechMatchReviewRequired) as context:
			submit_speech_entry(
				session=session,
				transcript='completely different name 75',
			)
		self.assertGreaterEqual(len(context.exception.candidates), 1)

	def test_submit_speech_entry_recovers_noisy_name_from_transcript(self):
		session = create_or_get_session(exam=self.exam, subject=self.subject, teacher_name='Teacher One', expected_student_count=1)
		result = submit_speech_entry(
			session=session,
			transcript='ZZ Amina Jooma tisinani',
		)
		self.assertEqual(result['student']['id'], self.student_one.id)
		self.assertEqual(result['score'], 90)

	def test_get_session_status_includes_existing_subject_marks_in_debug_payload(self):
		session = create_or_get_session(
			exam=self.exam,
			subject=self.subject,
			teacher_name='Teacher One',
			expected_student_count=2,
			roster_student_ids=[self.student_one.id, self.student_two.id],
		)

		ExamResult.objects.create(exam=self.exam, student=self.student_two, subject=self.subject, score=64)
		submit_speech_entry(
			session=session,
			transcript='Amina Juma 88',
			confirm_student_id=self.student_one.id,
		)

		status = get_session_status(session, include_existing_marks=True)

		self.assertIn('existing_subject_marks', status)
		self.assertIn('saved_entries', status)
		self.assertEqual(len(status['existing_subject_marks']), 2)
		self.assertEqual(len(status['saved_entries']), 1)

		sources = {row['student_id']: row['source'] for row in status['existing_subject_marks']}
		self.assertEqual(sources[self.student_one.id], 'speech_session')
		self.assertEqual(sources[self.student_two.id], 'existing_result')


class ScoreSheetOCRParsingTests(TestCase):
	"""No network calls — only the response-parsing helpers, using canned
	AI-response text shapes (fenced, with surrounding prose, malformed)."""

	def test_extract_json_array_strips_markdown_fence(self):
		text = '```json\n[{"name": "Amina Juma", "score": 78}]\n```'
		self.assertEqual(_extract_json_array(text), [{"name": "Amina Juma", "score": 78}])

	def test_extract_json_array_ignores_surrounding_prose(self):
		text = 'Here are the results:\n[{"name": "Peter Mushi", "score": 55}]\nHope that helps!'
		self.assertEqual(_extract_json_array(text), [{"name": "Peter Mushi", "score": 55}])

	def test_extract_json_array_raises_on_no_array(self):
		with self.assertRaises(ScoreSheetOCRError):
			_extract_json_array('Sorry, I could not read the image.')

	def test_extract_json_array_raises_on_malformed_json(self):
		with self.assertRaises(ScoreSheetOCRError):
			_extract_json_array('[{"name": "Amina", "score": }]')

	def test_clean_rows_drops_out_of_range_and_missing_fields(self):
		raw = [
			{"name": "Amina Juma", "score": 78},
			{"name": "", "score": 50},
			{"name": "No Score"},
			{"name": "Too High", "score": 150},
			{"name": "Too Low", "score": -5},
			{"name": "Not A Number", "score": "abc"},
		]
		self.assertEqual(_clean_rows(raw), [{"raw_name": "Amina Juma", "score": 78}])


def _build_pdf_bytes(num_pages=1):
	from io import BytesIO
	from reportlab.pdfgen import canvas

	buf = BytesIO()
	c = canvas.Canvas(buf)
	for i in range(num_pages):
		c.drawString(100, 700, f"Scoresheet page {i + 1}")
		c.showPage()
	c.save()
	return buf.getvalue()


class ScoreSheetDocumentLoadingTests(TestCase):
	"""Real PDF rendering via pypdfium2 (no network/AI call) — proves a
	scanned PDF is turned into page images the same way a photo is."""

	def test_is_pdf_detects_pdf_by_magic_bytes(self):
		from django.core.files.uploadedfile import SimpleUploadedFile
		pdf_file = SimpleUploadedFile('sheet.pdf', _build_pdf_bytes(), content_type='application/octet-stream')
		self.assertTrue(_is_pdf(pdf_file))

	def test_is_pdf_false_for_image(self):
		from django.core.files.uploadedfile import SimpleUploadedFile
		jpeg_file = SimpleUploadedFile('sheet.jpg', b'\xff\xd8\xff\xe0fake', content_type='image/jpeg')
		self.assertFalse(_is_pdf(jpeg_file))

	def test_load_page_images_renders_one_image_per_pdf_page(self):
		from django.core.files.uploadedfile import SimpleUploadedFile
		pdf_file = SimpleUploadedFile('sheet.pdf', _build_pdf_bytes(num_pages=2), content_type='application/pdf')
		images = _load_page_images(pdf_file)
		self.assertEqual(len(images), 2)
		for img in images:
			self.assertEqual(img.mode, 'RGB')

	def test_load_page_images_caps_at_max_pages(self):
		from django.core.files.uploadedfile import SimpleUploadedFile
		from .services import scoresheet_ocr_service
		pdf_file = SimpleUploadedFile('sheet.pdf', _build_pdf_bytes(num_pages=8), content_type='application/pdf')
		images = _load_page_images(pdf_file)
		self.assertEqual(len(images), scoresheet_ocr_service.MAX_PDF_PAGES)


class ScoreSheetPhotoExtractViewTests(TestCase):
	"""scoresheet_photo_extract now only dispatches a Celery task and
	returns a task_id — these force the task to run synchronously
	(task_always_eager) so the tests don't need a real worker/broker, then
	poll scoresheet_extract_status once for the actual result."""
	databases = {'default', 'results'}

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from field_management.celery import app as celery_app
		cls._celery_app = celery_app
		cls._orig_conf = {
			'task_always_eager': celery_app.conf.task_always_eager,
			'task_eager_propagates': celery_app.conf.task_eager_propagates,
			'task_store_eager_result': celery_app.conf.task_store_eager_result,
		}
		celery_app.conf.task_always_eager = True
		celery_app.conf.task_eager_propagates = True
		celery_app.conf.task_store_eager_result = True

	@classmethod
	def tearDownClass(cls):
		cls._celery_app.conf.update(cls._orig_conf)
		super().tearDownClass()

	def setUp(self):
		self.exam = Exam.objects.create(name='Midterm 1', year=2026, form=1)
		self.subject = Subject.objects.create(name='Mathematics')
		self.student_one = Student.objects.create(first_name='Amina', middle_name='', last_name='Juma', gender='F')
		self.student_two = Student.objects.create(first_name='Peter', middle_name='', last_name='Mushi', gender='M')
		self.teacher = TeacherAccount.objects.create(email='teacher@example.com', full_name='Teacher One', role=TeacherAccount.ROLE_TEACHER)
		self.teacher.subjects.set([self.subject])
		self.client = Client()
		self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')

	def _post(self, extracted_rows, roster):
		with patch('results.tasks.extract_scores_from_document', return_value=extracted_rows):
			from django.core.files.uploadedfile import SimpleUploadedFile
			photo = SimpleUploadedFile('sheet.jpg', b'fake-bytes', content_type='image/jpeg')
			kickoff = self.client.post(reverse('scoresheet_photo_extract'), {
				'photo': photo,
				'exam_id': self.exam.id,
				'subject_id': self.subject.id,
				'roster': json.dumps(roster),
			})
			self.assertEqual(kickoff.status_code, 202)
			task_id = kickoff.json()['task_id']
			return self.client.get(reverse('scoresheet_extract_status', args=[task_id]))

	def test_extracted_rows_are_fuzzy_matched_against_posted_roster(self):
		roster = [
			{'id': self.student_one.id, 'name': 'Amina Juma'},
			{'id': self.student_two.id, 'name': 'Peter Mushi'},
		]
		extracted = [
			{'raw_name': 'Amina Juma', 'score': 78},
			{'raw_name': 'Peter Mushi', 'score': 55},
		]
		response = self._post(extracted, roster)
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(len(data['matched']), 2)
		self.assertEqual(data['unmatched'], [])
		matched_by_id = {row['id']: row['score'] for row in data['matched']}
		self.assertEqual(matched_by_id[self.student_one.id], 78)
		self.assertEqual(matched_by_id[self.student_two.id], 55)

	def test_name_not_on_roster_creates_a_new_student(self):
		"""The photo IS the roster — a name that doesn't match anyone
		already loaded (or an empty/no roster at all) should create a new
		Student and come back in `matched` with is_new=True, not get
		silently dropped as 'unmatched'."""
		roster = [{'id': self.student_one.id, 'name': 'Amina Juma'}]
		extracted = [{'raw_name': 'Completely Different Person', 'score': 60}]
		response = self._post(extracted, roster)
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(data['unmatched'], [])
		self.assertEqual(len(data['matched']), 1)
		entry = data['matched'][0]
		self.assertTrue(entry['is_new'])
		self.assertEqual(entry['score'], 60)
		new_student = Student.objects.get(id=entry['id'])
		self.assertEqual(new_student.first_name, 'Completely')
		self.assertEqual(new_student.last_name, 'Person')

	def test_empty_roster_still_creates_students_from_photo(self):
		"""No roster uploaded beforehand is the common case — the photo
		alone should be enough to populate the table."""
		extracted = [
			{'raw_name': 'Amina Juma', 'score': 78},
			{'raw_name': 'Peter Mushi', 'score': 55},
		]
		response = self._post(extracted, roster=[])
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(data['unmatched'], [])
		self.assertEqual(len(data['matched']), 2)
		self.assertTrue(all(row['is_new'] for row in data['matched']))

	def test_unparseable_name_is_reported_as_unmatched(self):
		roster = [{'id': self.student_one.id, 'name': 'Amina Juma'}]
		extracted = [{'raw_name': 'x', 'score': 60}]
		response = self._post(extracted, roster)
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(data['matched'], [])
		self.assertEqual(len(data['unmatched']), 1)
		self.assertEqual(data['unmatched'][0]['raw_name'], 'x')

	def test_ocr_error_returns_400(self):
		with patch('results.tasks.extract_scores_from_document', side_effect=ScoreSheetOCRError('Hakuna alama iliyotambulika.')):
			from django.core.files.uploadedfile import SimpleUploadedFile
			photo = SimpleUploadedFile('sheet.jpg', b'fake-bytes', content_type='image/jpeg')
			kickoff = self.client.post(reverse('scoresheet_photo_extract'), {
				'photo': photo,
				'exam_id': self.exam.id,
				'subject_id': self.subject.id,
				'roster': '[]',
			})
			self.assertEqual(kickoff.status_code, 202)
			task_id = kickoff.json()['task_id']
			response = self.client.get(reverse('scoresheet_extract_status', args=[task_id]))
		self.assertEqual(response.status_code, 400)
		self.assertIn('error', response.json())


class DownloadScoresheetNamesPdfTests(TestCase):
	databases = {'default', 'results'}

	def setUp(self):
		self.exam = Exam.objects.create(name='Midterm 1', year=2026, form=1)
		self.subject = Subject.objects.create(name='Mathematics')
		self.student_one = Student.objects.create(first_name='Amina', middle_name='', last_name='Juma', gender='F')
		self.student_two = Student.objects.create(first_name='Peter', middle_name='', last_name='Mushi', gender='M')
		# _resolve_class_roster's fallback tier picks up students via
		# existing ExamResult rows when there's no StoredRoster/FormStudent.
		ExamResult.objects.create(exam=self.exam, student=self.student_one, subject=self.subject, score=50)
		ExamResult.objects.create(exam=self.exam, student=self.student_two, subject=self.subject, score=60)
		self.teacher = TeacherAccount.objects.create(email='teacher@example.com', full_name='Teacher One', role=TeacherAccount.ROLE_TEACHER)
		self.teacher.subjects.set([self.subject])
		self.client = Client()
		self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')

	def test_returns_pdf_containing_registered_student_names(self):
		response = self.client.get(reverse('download_scoresheet_names_pdf'), {
			'exam_id': self.exam.id, 'subject_id': self.subject.id,
		})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response['Content-Type'], 'application/pdf')
		content = b''.join(response.streaming_content) if response.streaming else response.content
		self.assertTrue(content.startswith(b'%PDF'))

		import io
		import pdfplumber
		with pdfplumber.open(io.BytesIO(content)) as pdf:
			text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
		self.assertIn('Amina Juma', text)
		self.assertIn('Peter Mushi', text)

	def test_rejects_subject_teacher_is_not_assigned_to(self):
		other_subject = Subject.objects.create(name='Physics')
		response = self.client.get(reverse('download_scoresheet_names_pdf'), {
			'exam_id': self.exam.id, 'subject_id': other_subject.id,
		})
		self.assertEqual(response.status_code, 403)


class StudentResultPdfTests(TestCase):
	"""The downloadable version of the public /matokeo/<token>/ page — no
	login required, same share token a parent already uses to view online."""
	databases = {'default', 'results'}

	def setUp(self):
		self.exam = Exam.objects.create(name='Midterm 1', year=2026, form=2)
		self.subject = Subject.objects.create(name='Mathematics')
		self.student = Student.objects.create(first_name='Amina', middle_name='', last_name='Juma', gender='F')
		ExamResult.objects.create(exam=self.exam, student=self.student, subject=self.subject, score=78)
		self.result = ProcessedResult.objects.create(
			exam=self.exam, student=self.student,
			total_score=78, average_score=78, points=2, position=1, division='I',
		)

	def test_returns_pdf_with_student_name_and_division(self):
		response = self.client.get(reverse('student_result_pdf', args=[self.result.share_token]))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response['Content-Type'], 'application/pdf')
		content = response.content
		self.assertTrue(content.startswith(b'%PDF'))

		import io
		import pdfplumber
		with pdfplumber.open(io.BytesIO(content)) as pdf:
			text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
		self.assertIn('AMINA JUMA', text.upper())
		self.assertIn('78', text)

	def test_unknown_token_returns_404(self):
		import uuid
		response = self.client.get(reverse('student_result_pdf', args=[uuid.uuid4()]))
		self.assertEqual(response.status_code, 404)


class BulkStudentResultsPdfTests(TestCase):
	"""'Download all students' reports' — merges one result-slip page per
	student into a single PDF, restricted to the Academic Officer."""
	databases = {'default', 'results'}

	def setUp(self):
		self.school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
		self.exam = Exam.objects.create(name='Midterm 1', year=2026, form=2, school=self.school)
		self.subject = Subject.objects.create(name='Mathematics')
		self.student_one = Student.objects.create(first_name='Amina', middle_name='', last_name='Juma', gender='F')
		self.student_two = Student.objects.create(first_name='Peter', middle_name='', last_name='Mushi', gender='M')
		ExamResult.objects.create(exam=self.exam, student=self.student_one, subject=self.subject, score=78)
		ExamResult.objects.create(exam=self.exam, student=self.student_two, subject=self.subject, score=55)
		ProcessedResult.objects.create(exam=self.exam, student=self.student_one, total_score=78, average_score=78, points=2, position=1, division='I')
		ProcessedResult.objects.create(exam=self.exam, student=self.student_two, total_score=55, average_score=55, points=5, position=2, division='III')
		self.academic = TeacherAccount.objects.create(email='academic@example.com', full_name='Academic One', role=TeacherAccount.ROLE_ACADEMIC, school=self.school)
		self.teacher = TeacherAccount.objects.create(email='teacher@example.com', full_name='Teacher One', role=TeacherAccount.ROLE_TEACHER, school=self.school)

	def test_merges_one_page_per_student_in_position_order(self):
		client = Client()
		client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
		response = client.get(reverse('generate_bulk_student_results_pdf', args=[self.exam.id]))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response['Content-Type'], 'application/pdf')
		content = response.content
		self.assertTrue(content.startswith(b'%PDF'))

		import io
		import pdfplumber
		with pdfplumber.open(io.BytesIO(content)) as pdf:
			self.assertEqual(len(pdf.pages), 2)
			text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
		self.assertIn('AMINA JUMA', text.upper())
		self.assertIn('PETER MUSHI', text.upper())

	def test_rejects_non_academic_teacher(self):
		client = Client()
		client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')
		response = client.get(reverse('generate_bulk_student_results_pdf', args=[self.exam.id]))
		self.assertEqual(response.status_code, 403)

	def test_no_processed_results_returns_404(self):
		empty_exam = Exam.objects.create(name='Empty Exam', year=2026, form=1, school=self.school)
		client = Client()
		client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
		response = client.get(reverse('generate_bulk_student_results_pdf', args=[empty_exam.id]))
		self.assertEqual(response.status_code, 404)


class ClassTimetableServiceTests(TestCase):
	"""The one rule that must never break: a teacher can never be double
	booked at the same time slot across two different classes."""
	databases = {'default', 'results'}

	def setUp(self):
		self.school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
		self.teacher = TeacherAccount.objects.create(email='t1@example.com', full_name='Teacher One', role=TeacherAccount.ROLE_TEACHER, school=self.school)
		self.math = Subject.objects.create(name='Mathematics')
		self.slot1 = TimeSlot.objects.create(school=self.school, day_of_week=0, order=0, start_time='08:00', end_time='08:40')
		self.slot2 = TimeSlot.objects.create(school=self.school, day_of_week=0, order=1, start_time='08:40', end_time='09:20')

	def test_generate_never_double_books_a_teacher(self):
		# One teacher, two classes, each wanting 2 periods/week — but only
		# 2 slots exist in total, so at most 2 of the 4 needed lessons can
		# ever be placed without the teacher being in two places at once.
		TeachingAssignment.objects.create(school=self.school, form=1, stream='A', subject=self.math, teacher=self.teacher, periods_per_week=2)
		TeachingAssignment.objects.create(school=self.school, form=1, stream='B', subject=self.math, teacher=self.teacher, periods_per_week=2)

		entries, unplaced = generate_class_timetable(self.school)

		teacher_slot_pairs = [(e['teacher_id'], e['time_slot_id']) for e in entries]
		self.assertEqual(len(teacher_slot_pairs), len(set(teacher_slot_pairs)))
		self.assertEqual(len(entries), 2)
		self.assertEqual(sum(u['missing'] for u in unplaced), 2)

	def test_generate_raises_without_time_slots(self):
		TimeSlot.objects.all().delete()
		TeachingAssignment.objects.create(school=self.school, form=1, stream='A', subject=self.math, teacher=self.teacher, periods_per_week=1)
		with self.assertRaises(TimetableConflict):
			generate_class_timetable(self.school)

	def test_generate_raises_without_assignments(self):
		with self.assertRaises(TimetableConflict):
			generate_class_timetable(self.school)

	def test_save_class_timetable_only_replaces_touched_classes(self):
		untouched = ClassTimetableEntry.objects.create(
			school=self.school, form=9, stream='Z', time_slot=self.slot1, subject=self.math, teacher=self.teacher,
		)
		TeachingAssignment.objects.create(school=self.school, form=1, stream='A', subject=self.math, teacher=self.teacher, periods_per_week=1)
		entries, _ = generate_class_timetable(self.school, form_streams=[(1, 'A')])
		saved = save_class_timetable(self.school, entries, form_streams=[(1, 'A')])
		self.assertEqual(saved, 1)
		self.assertTrue(ClassTimetableEntry.objects.filter(school=self.school, form=1, stream='A').exists())
		self.assertTrue(ClassTimetableEntry.objects.filter(id=untouched.id).exists())

	def test_set_single_cell_rejects_double_booking(self):
		ClassTimetableEntry.objects.create(school=self.school, form=1, stream='A', time_slot=self.slot1, subject=self.math, teacher=self.teacher)
		with self.assertRaises(TimetableConflict):
			set_single_cell(self.school, form=1, stream='B', time_slot_id=self.slot1.id, subject_id=self.math.id, teacher_id=self.teacher.id)

	def test_set_single_cell_allows_same_class_update(self):
		entry = ClassTimetableEntry.objects.create(school=self.school, form=1, stream='A', time_slot=self.slot1, subject=self.math, teacher=self.teacher)
		other_subject = Subject.objects.create(name='English')
		set_single_cell(self.school, form=1, stream='A', time_slot_id=self.slot1.id, subject_id=other_subject.id, teacher_id=self.teacher.id)
		entry.refresh_from_db()
		self.assertEqual(entry.subject_id, other_subject.id)


class ClassTimetableViewTests(TestCase):
	databases = {'default', 'results'}

	def setUp(self):
		self.school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
		self.academic = TeacherAccount.objects.create(email='academic@example.com', full_name='Academic One', role=TeacherAccount.ROLE_ACADEMIC, school=self.school)
		self.teacher = TeacherAccount.objects.create(email='teacher@example.com', full_name='Teacher One', role=TeacherAccount.ROLE_TEACHER, school=self.school)
		self.subject = Subject.objects.create(name='Mathematics')
		self.client_academic = Client()
		self.client_academic.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
		self.client_teacher = Client()
		self.client_teacher.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')

	def test_non_academic_cannot_manage_time_slots(self):
		response = self.client_teacher.get(reverse('time_slot_setup'))
		self.assertEqual(response.status_code, 403)

	def test_academic_can_add_and_delete_time_slot(self):
		response = self.client_academic.post(reverse('time_slot_setup'), {
			'day_of_week': '0', 'order': '0', 'start_time': '08:00', 'end_time': '08:40', 'is_teaching_slot': 'on',
		})
		self.assertEqual(response.status_code, 302)
		slot = TimeSlot.objects.get(school=self.school)
		self.assertTrue(slot.is_teaching_slot)

		response = self.client_academic.post(reverse('time_slot_setup'), {'action': 'delete', 'slot_id': slot.id})
		self.assertEqual(response.status_code, 302)
		self.assertFalse(TimeSlot.objects.filter(id=slot.id).exists())

	def test_academic_can_add_teaching_assignment(self):
		response = self.client_academic.post(reverse('teaching_assignment_manage'), {
			'teacher_id': self.teacher.id, 'subject_id': self.subject.id, 'form': '1', 'stream': 'A', 'periods_per_week': '3',
		})
		self.assertEqual(response.status_code, 302)
		self.assertTrue(TeachingAssignment.objects.filter(school=self.school, teacher=self.teacher, subject=self.subject).exists())

	def test_generate_view_shows_preview_and_save_persists(self):
		TimeSlot.objects.create(school=self.school, day_of_week=0, order=0, start_time='08:00', end_time='08:40')
		TeachingAssignment.objects.create(school=self.school, form=1, stream='A', subject=self.subject, teacher=self.teacher, periods_per_week=1)

		response = self.client_academic.post(reverse('generate_class_timetable'), {'action': 'generate'})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.context['preview_rows']), 1)

		row = response.context['preview_rows'][0]
		save_response = self.client_academic.post(reverse('save_class_timetable'), {
			'form[]': [str(row['form'])],
			'stream[]': [row['stream']],
			'time_slot_id[]': [str(row['time_slot_id'])],
			'subject_id[]': [str(row['subject_id'])],
			'teacher_id[]': [str(row['teacher_id'])],
		})
		self.assertEqual(save_response.status_code, 302)
		self.assertTrue(ClassTimetableEntry.objects.filter(school=self.school, form=1, stream='A').exists())

	def test_class_timetable_view_renders_for_teacher_and_academic(self):
		slot = TimeSlot.objects.create(school=self.school, day_of_week=0, order=0, start_time='08:00', end_time='08:40')
		ClassTimetableEntry.objects.create(school=self.school, form=1, stream='A', time_slot=slot, subject=self.subject, teacher=self.teacher)
		TeachingAssignment.objects.create(school=self.school, form=1, stream='A', subject=self.subject, teacher=self.teacher, periods_per_week=1)

		for client in (self.client_academic, self.client_teacher):
			response = client.get(reverse('class_timetable_view'))
			self.assertEqual(response.status_code, 200)
			self.assertContains(response, 'Mathematics')

	def test_cell_edit_rejects_conflicting_teacher(self):
		slot = TimeSlot.objects.create(school=self.school, day_of_week=0, order=0, start_time='08:00', end_time='08:40')
		ClassTimetableEntry.objects.create(school=self.school, form=1, stream='A', time_slot=slot, subject=self.subject, teacher=self.teacher)

		response = self.client_academic.post(reverse('class_timetable_cell_edit'), {
			'form': '1', 'stream': 'B', 'time_slot_id': slot.id, 'subject_id': self.subject.id, 'teacher_id': self.teacher.id,
		})
		self.assertEqual(response.status_code, 409)

	def test_default_template_creates_slots_only_when_none_exist(self):
		response = self.client_academic.post(reverse('time_slot_setup'), {'action': 'default_template'})
		self.assertEqual(response.status_code, 302)
		count_after_first = TimeSlot.objects.filter(school=self.school).count()
		self.assertGreater(count_after_first, 0)

		# Second call must not duplicate — refuses instead of stacking a second template.
		response = self.client_academic.post(reverse('time_slot_setup'), {'action': 'default_template'})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(TimeSlot.objects.filter(school=self.school).count(), count_after_first)

	def test_auto_populate_bootstraps_from_teacher_form_assignment(self):
		from .models import TeacherFormAssignment
		TeacherFormAssignment.objects.create(teacher=self.teacher, form=2, subject=self.subject, school=self.school)

		response = self.client_academic.post(reverse('teaching_assignment_manage'), {'action': 'auto_populate'})
		self.assertEqual(response.status_code, 302)
		ta = TeachingAssignment.objects.get(school=self.school, form=2, subject=self.subject)
		self.assertEqual(ta.teacher_id, self.teacher.id)
		self.assertEqual(ta.stream, '')
		self.assertEqual(ta.periods_per_week, 5)

		# Re-running must not clobber a since-edited row.
		ta.periods_per_week = 3
		ta.save(update_fields=['periods_per_week'])
		self.client_academic.post(reverse('teaching_assignment_manage'), {'action': 'auto_populate'})
		ta.refresh_from_db()
		self.assertEqual(ta.periods_per_week, 3)
