from django.test import TestCase
import pandas as pd

from .models import Exam, ExamResult, SpeechSubmissionSession, Student, Subject
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
