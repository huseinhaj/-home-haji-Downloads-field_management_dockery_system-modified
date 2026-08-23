import json
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
import pandas as pd

from .models import Exam, ExamResult, SpeechSubmissionSession, Student, Subject, TeacherAccount
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
	databases = {'default', 'results'}

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
		with patch('results.marks_entry.extract_scores_from_document', return_value=extracted_rows):
			from django.core.files.uploadedfile import SimpleUploadedFile
			photo = SimpleUploadedFile('sheet.jpg', b'fake-bytes', content_type='image/jpeg')
			return self.client.post(reverse('scoresheet_photo_extract'), {
				'photo': photo,
				'exam_id': self.exam.id,
				'subject_id': self.subject.id,
				'roster': json.dumps(roster),
			})

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
		with patch('results.marks_entry.extract_scores_from_document', side_effect=ScoreSheetOCRError('Hakuna alama iliyotambulika.')):
			from django.core.files.uploadedfile import SimpleUploadedFile
			photo = SimpleUploadedFile('sheet.jpg', b'fake-bytes', content_type='image/jpeg')
			response = self.client.post(reverse('scoresheet_photo_extract'), {
				'photo': photo,
				'exam_id': self.exam.id,
				'subject_id': self.subject.id,
				'roster': '[]',
			})
		self.assertEqual(response.status_code, 400)
		self.assertIn('error', response.json())
