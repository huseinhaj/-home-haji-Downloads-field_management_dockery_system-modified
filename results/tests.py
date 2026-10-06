import json
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
import pandas as pd

from .models import ClassTimetableEntry, Exam, ExamResult, FormStudent, ProcessedResult, School, SchoolSubject, SpeechSubmissionSession, Student, Subject, TeacherAccount, TeachingAssignment, TimeSlot
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
		# Desimali hazikatwi: alama 10.6 ilikuwa ikifanyika 10 na
		# "7.5" ikifanyika 75 kwa kukata kila digit. Kukanusha
		# alama huu ndiyo uliotoroga wanafunzi wa baadaye kwenye
		# scoresheet (mstari uliotoweka -> mtu mwingine alipata alama).
		self.assertEqual(parse_score('78'), Decimal('78.00'))
		self.assertEqual(parse_score('10.6'), Decimal('10.60'))
		self.assertEqual(parse_score(44.8), Decimal('44.80'))
		self.assertEqual(parse_score('7.5'), Decimal('7.50'))
		self.assertIsNone(parse_score('not-a-number'))
		self.assertIsNone(parse_score(float('nan')))
		# Namba nje ya 0-100 haisomeki (kwa mtihani wa kawaida) —
		# hatuiruhusu ipotoshwe kuwa "106" iliyotokana na desimali.
		self.assertIsNone(parse_score('150'))
		self.assertIsNone(parse_score('-5'))
		self.assertIsNone(parse_score('10.678'))  # maeneo 3 ya decimal = kidole
		self.assertEqual(parse_score('85/100'), Decimal('85.00'))
		self.assertEqual(parse_score('10,6'), Decimal('10.60'))

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

	def test_extract_json_array_keeps_extra_fields_like_gender(self):
		"""Mijini ya AI kwa orodha ina 'gender'. Ikiwa tunajenga mistari
		mine tu (row/name/score), kila mwanafunzi wa kike katika orodha
		alihifadhiwa kama kiume — bila kosa lolote linaloonekana."""
		text = json.dumps([
			{"row": 1, "name": "Halima Ally Mohamed", "gender": "F"},
			{"row": 2, "student_name": "Juma Hamisi", "gender": "M"},
		])
		rows = _extract_json_array(text)
		self.assertEqual(rows[0]["name"], "Halima Ally Mohamed")
		self.assertEqual(rows[0]["gender"], "F")
		self.assertEqual(rows[1]["name"], "Juma Hamisi")
		self.assertEqual(rows[1]["gender"], "M")

	def test_extract_json_array_raises_on_no_array(self):
		with self.assertRaises(ScoreSheetOCRError):
			_extract_json_array('Sorry, I could not read the image.')

	def test_extract_json_array_raises_on_malformed_json(self):
		with self.assertRaises(ScoreSheetOCRError):
			_extract_json_array('[{"name": "Amina", "score": }]')

	# ── Majibu halisi ya vision models ──────────────────────────────────
	# Kila moja hapa ni muundo uliotokea kwenye matumizi halisi
	# (2026-09-27: mwalimu alipiga picha, AI akarudisha muundo
	# tofauti na ulioombwa, na ukurasa ukakoseka kabisa).

	def test_extract_json_array_reads_object_wrapped_array(self):
		"""AI nyingine inajibu {"rows": [...]} badala ya array moja.
		Muundo huu ulitosha kupoteza wanafunzi WOTE wa ukurasa."""
		text = '{"rows": [{"row": 1, "name": "Amina Juma", "score": 78}, {"row": 2, "name": "Peter Mushi", "score": 55}]}'
		rows = _extract_json_array(text)
		self.assertEqual([r['name'] for r in rows], ['Amina Juma', 'Peter Mushi'])
		self.assertEqual([r['score'] for r in rows], [78, 55])

	def test_extract_json_array_reads_alternative_key_names(self):
		"""'student_name'/'marks' ni majina sani ya AI — haya ya kawaida
		chini ya vision models, na hapo mwanzo parser yetu alikuwa
		akirusha 'AI haikurudisha muundo sahihi wa JSON'."""
		text = '[\n {"student_name": "Amina Juma", "marks": 78, "Na": 1},\n {"student_name": "Peter Mushi", "marks": 55, "Na": 2}\n]'
		rows = _extract_json_array(text)
		self.assertEqual([r['name'] for r in rows], ['Amina Juma', 'Peter Mushi'])
		self.assertEqual([r['score'] for r in rows], [78, 55])
		self.assertEqual([r['row'] for r in rows], [1, 2])

	def test_extract_json_array_salvages_truncated_response(self):
		"""Jibu lililokatika (max_tokens) halisombwi — mistari
		iliyokamilika inachukuliwa badala ya kupoteza ukurasa wote."""
		truncated = (
			'[{"row": 1, "name": "Amina Juma", "score": 78}, '
			'{"row": 2, "name": "Peter Mushi", "score": 55}, '
			'{"row": 3, "name": "Grace Kima'
		)
		rows = _extract_json_array(truncated)
		self.assertEqual([r['name'] for r in rows], ['Amina Juma', 'Peter Mushi'])

	def test_extract_json_array_tolerates_trailing_commas(self):
		text = '[\n {"name": "Amina Juma", "score": 78,},\n {"name": "Peter Mushi", "score": 55,},\n]'
		rows = _extract_json_array(text)
		self.assertEqual(len(rows), 2)
		self.assertEqual(rows[1]['name'], 'Peter Mushi')

	def test_extract_json_array_reads_numbered_plain_text_lines(self):
		"""AI ikirudi mistari ya maandishi badala ya JSON kabisa."""
		text = '1. Amina Juma 78\n2. Peter Mushi 55\n3. Grace Kimaro -'
		rows = _extract_json_array(text)
		self.assertEqual([r['name'] for r in rows], ['Amina Juma', 'Peter Mushi'])

	def test_extract_json_array_ignores_prose_line_with_number(self):
		"""'I counted 20 rows' si mwanafunzi — msimbo wa maneno
		mawili hapa unafanya sentensi kama hii isionekane kama
		mwanafunzi wa scoresheet."""
		with self.assertRaises(ScoreSheetOCRError):
			_extract_json_array('I counted 20 rows on the sheet.')

	def test_clean_rows_keeps_unreadable_marks_instead_of_dropping_the_row(self):
		"""Mstari ambao AI haukuweza kusoma alama yake HUBWEKI
		hasi, lakini bila alama — si kukatika.

		Mtumia wa mwanzo: mstari uliotoweka husogeza kila mwanafunzi
		baadaye nafasi, hivyo mwisho wa listi unapewa alama ya mwanafunzi
		wa juu yake. Zaidi ya hayo, alama ya desimali ("10.6") ilikuwa
		ikikatwa na mstari mzima ukatoweka — ndio iliyokuwa ikisababisha
		wanafunzi ~10 wa mwisho kupata alama za watu wengine.
		"""
		raw = [
			{"row": 1, "name": "Amina Juma", "score": 78},
			{"name": "", "score": 50},
			{"row": 3, "name": "No Score"},
			{"row": 4, "name": "Too High", "score": 150},
			{"row": 5, "name": "Too Low", "score": -5},
			{"row": 6, "name": "Not A Number", "score": "abc"},
			{"row": 7, "name": "Decimal Mark", "score": "10.6"},
		]
		rows = _clean_rows(raw)

		# Jina tupu bado hupungikwa (hakuna mwanafunzi wa kushughulikiwa)
		self.assertEqual([r["raw_name"] for r in rows], [
			"Amina Juma", "No Score", "Too High", "Too Low",
			"Not A Number", "Decimal Mark",
		])
		# Kila mstari unaotakiwa kuhifadhiwa, namba yake iko pale
		self.assertEqual([r["row"] for r in rows], [1, 3, 4, 5, 6, 7])

		by_name = {r["raw_name"]: r for r in rows}
		# Desimali inasomwa vizuri — si 106, si 10
		self.assertEqual(by_name["Decimal Mark"]["score"], Decimal('10.60'))
		self.assertFalse(by_name["Decimal Mark"]["blank"])

		# Alama zisizosomeka: mstari hubaki, alama ni None, na tunaijua
		# kuwa AI haikusoma ili mwalimu asemewe mwenyewe.
		for name in ("Too High", "Too Low", "Not A Number"):
			self.assertIsNone(by_name[name]["score"], name)
			self.assertTrue(by_name[name]["unreadable"], name)
			self.assertTrue(by_name[name]["blank"], name)

	def test_clean_rows_keeps_blank_rows_instead_of_dropping_them(self):
		"""A blank/dash score cell means 'student doesn't study this
		subject' — the row must be KEPT (blank=True, score=None) so a
		caller can tell it apart from a row the AI never reported at all
		(which usually means a mark was missed, not a non-taker)."""
		raw = [
			{"row": 1, "name": "Blank Cell", "score": "BLANK"},
			{"row": 2, "name": "Dash Cell", "score": "-"},
			{"row": 3, "name": "Null Cell", "score": None},
		]
		cleaned = _clean_rows(raw)
		self.assertEqual(len(cleaned), 3)
		self.assertTrue(all(r["blank"] and r["score"] is None and not r["is_absent"] for r in cleaned))

	def test_clean_rows_parses_row_number(self):
		raw = [{"row": "7", "name": "Amina Juma", "score": 78}]
		self.assertEqual(_clean_rows(raw)[0]["row"], 7)

	def test_row_number_warnings_flags_skipped_and_duplicated_rows(self):
		"""Mistari iliyorukwa (mf. ukurasa uliokatika / picha iliyokoleka)
		ilazimisha onyo kwa mwalimu — hitilafu ni YA SCAN, si ya orodha yake."""
		from .tasks import _row_number_warnings
		rows = [
			{'row': 1}, {'row': 2}, {'row': 3},
			{'row': 7}, {'row': 8},   # 4-6 zimerukwa (truncation)
		]
		warnings = _row_number_warnings(rows)
		self.assertEqual(len(warnings), 1)
		self.assertIn('4', warnings[0])
		self.assertIn('5', warnings[0])
		# Mistari ya dupes pia inaonyeshwa
		dupes = _row_number_warnings([
			{'row': 1}, {'row': 1}, {'row': 2},
		])
		self.assertEqual(len(dupes), 1)
		self.assertIn('mara moja', dupes[0])
		# Mistari kamili 1..N → hakuna onyo
		self.assertEqual(_row_number_warnings([{'row': i} for i in range(1, 8)]), [])


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
		over_cap = scoresheet_ocr_service.MAX_PDF_PAGES + 5
		pdf_file = SimpleUploadedFile('sheet.pdf', _build_pdf_bytes(num_pages=over_cap), content_type='application/pdf')
		images = _load_page_images(pdf_file)
		self.assertEqual(len(images), scoresheet_ocr_service.MAX_PDF_PAGES)


class ScoreSheetMultiPageExtractionTests(TestCase):
	"""extract_scores_from_document reads a multi-page document's pages
	CONCURRENTLY (one slow ~180s vision call per page, so a 3-5 page
	scoresheet must not wait on them one at a time) -- these prove that
	stays correct: page order is preserved regardless of which finishes
	first, and one page's failure doesn't discard the others' rows.

	_load_page_images is patched to return plain sentinel strings instead
	of real rendered pages -- _read_page_with_ai is mocked too, so nothing
	downstream ever needs an actual PIL image, and using distinct sentinels
	lets fake_read tell pages apart deterministically instead of relying on
	call order, which the ThreadPoolExecutor doesn't guarantee."""

	def setUp(self):
		from .services import scoresheet_ocr_service
		self._service = scoresheet_ocr_service
		patcher = patch.object(scoresheet_ocr_service, 'OPENROUTER_API_KEY', 'test-key')
		patcher.start()
		self.addCleanup(patcher.stop)

	def _upload(self):
		from django.core.files.uploadedfile import SimpleUploadedFile
		return SimpleUploadedFile('sheet.pdf', b'%PDF-fake', content_type='application/pdf')

	def test_page_order_preserved_regardless_of_completion_order(self):
		import time as _time

		# 'page1' is slower than 'page2' -- if results were assembled in
		# completion order instead of page order, page 2's row would land
		# before page 1's.
		def fake_read(img):
			if img == 'page1':
				_time.sleep(0.15)
				return '[{"row": 1, "name": "Page One Student", "score": 50}]'
			return '[{"row": 2, "name": "Page Two Student", "score": 60}]'

		with patch.object(self._service, '_load_page_images', return_value=['page1', 'page2']), \
				patch.object(self._service, '_read_page_with_ai', side_effect=fake_read):
			rows = self._service.extract_scores_from_document(self._upload())

		names = [r['raw_name'] for r in rows]
		self.assertEqual(names, ['Page One Student', 'Page Two Student'])

	def test_one_failed_page_does_not_discard_others(self):
		def fake_read(img):
			if img == 'page1':
				raise RuntimeError('vision API timed out')
			return '[{"row": 2, "name": "Survivor", "score": 70}]'

		with patch.object(self._service, '_load_page_images', return_value=['page1', 'page2']), \
				patch.object(self._service, '_read_page_with_ai', side_effect=fake_read):
			rows = self._service.extract_scores_from_document(self._upload())

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]['raw_name'], 'Survivor')

	def test_all_pages_failing_raises(self):
		with patch.object(self._service, '_load_page_images', return_value=['page1', 'page2']), \
				patch.object(self._service, '_read_page_with_ai', side_effect=RuntimeError('down')):
			with self.assertRaises(ScoreSheetOCRError):
				self._service.extract_scores_from_document(self._upload())


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

	def test_clean_numbered_sheet_aligns_by_position_not_name(self):
		"""The scoresheet PDF is generated from this exact roster, in this
		exact order, with a continuous 'Na.' column. When the OCR returns a
		clean 1..N run of row numbers matching the roster size, each row is
		aligned to the roster BY POSITION — a handwritten name the vision
		model re-typed imperfectly must not veto that, flag the student as
		'missing', or spawn a duplicate new student."""
		third = Student.objects.create(first_name='Grace', middle_name='', last_name='Kimaro', gender='F')
		roster = [
			{'id': self.student_one.id, 'name': 'Amina Juma'},
			{'id': self.student_two.id, 'name': 'Peter Mushi'},
			{'id': third.id, 'name': 'Grace Kimaro'},
		]
		# Row numbers present but shuffled; names garbled the way OCR of
		# handwriting is; row 2 left blank on the sheet.
		extracted = [
			{'raw_name': 'Amna Juuma', 'score': 78, 'row': 1, 'blank': False},
			{'raw_name': 'Grsce Kimuro', 'score': 41, 'row': 3, 'blank': False},
			{'raw_name': 'Ptr Mshi', 'score': None, 'row': 2, 'blank': True},
		]
		before = Student.objects.count()
		response = self._post(extracted, roster)
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(Student.objects.count(), before)  # no new students spawned
		self.assertEqual(data['unmatched'], [])
		self.assertEqual(data['missing'], [])  # row 2 is a real blank, not a miss
		matched_by_id = {row['id']: row['score'] for row in data['matched']}
		self.assertEqual(matched_by_id[self.student_one.id], 78)
		self.assertEqual(matched_by_id[third.id], 41)
		self.assertNotIn(self.student_two.id, matched_by_id)  # blank row carries no score

	def test_sheet_order_differs_from_roster_matches_by_name(self):
		"""Lalamiko 2026-09-23: karatasi safi 1..N lakini mpangilio wake si
		ule wa rosti ya skrini (mwanafunzi ameongezwa/kuondolewa baada ya
		kuprint) — alama zilisogea kwa wanafunzi wasio wao. Jina lililosomeka
		waziwazi lazima lishinde namba ya mstari (kama scan ya academic)."""
		third = Student.objects.create(first_name='Grace', middle_name='', last_name='Kimaro', gender='F')
		roster = [
			{'id': self.student_one.id, 'name': 'Amina Juma'},
			{'id': self.student_two.id, 'name': 'Peter Mushi'},
			{'id': third.id, 'name': 'Grace Kimaro'},
		]
		extracted = [
			{'raw_name': 'Grace Kimaro', 'score': 91, 'row': 1, 'blank': False},
			{'raw_name': 'Amina Juma', 'score': 64, 'row': 2, 'blank': False},
			{'raw_name': 'Peter Mushi', 'score': None, 'row': 3, 'blank': True},
		]
		data = self._post(extracted, roster).json()
		matched_by_id = {row['id']: row['score'] for row in data['matched']}
		self.assertEqual(matched_by_id, {third.id: 91, self.student_one.id: 64})
		self.assertEqual(data['missing'], [])

	def test_blank_rows_block_fuzzy_steal_of_unfilled_students(self):
		"""Lalamiko halisi: mwalimu hakuwajaza wanafunzi 3 (cells tupu kwenye
		karatasi) lakini baada ya scan walikuwa wamejaziwa — fuzzy fallback
		(KWENDA name-similarity) ilichukua alama za wenzao na kuwapa hao.

		Mstari ulio BLANK na namba ya mstari iliyosomwa ni thabiti kuliko
		jina la OCR: mwanafunzi aliye BLANK kwenye karatasi lazima asikubali
		kuchukuliwa na fuzzy matching — aishie 'missing' (mstari wa manjano)
		ili mwalimu ajaze mwenyewe."""
		third = Student.objects.create(first_name='Grace', middle_name='', last_name='Kimaro', gender='F')
		fourth = Student.objects.create(first_name='Baraka', middle_name='', last_name='Massawe', gender='M')
		fifth = Student.objects.create(first_name='Neema', middle_name='', last_name='Lyimo', gender='F')
		roster = [
			{'id': self.student_one.id, 'name': 'Amina Juma'},
			{'id': self.student_two.id, 'name': 'Peter Mushi'},
			{'id': third.id, 'name': 'Grace Kimaro'},
			{'id': fourth.id, 'name': 'Baraka Massawe'},
			{'id': fifth.id, 'name': 'Neema Lyimo'},
		]
		# Wanafunzi 3-4 wana cells tupu (BLANK, rows 3/4). AI imeruka mstari
		# wa 5 kabisa (rows=4 != roster=5) — hii inamwaga matching kwenye
		# fuzzy fallback, njia ile ile iliyovuruga scan ya mwalimu: bila
		# blank-protection, fuzzy inaweza kupaka alama za wenzazo kwenye
		# wanafunzi walio BLANK.
		extracted = [
			{'raw_name': 'Amna Juuma', 'score': 78, 'row': 1, 'blank': False},
			{'raw_name': 'Ptr Mshi', 'score': 55, 'row': 2, 'blank': False},
			{'raw_name': 'Grsce Kimuro', 'score': None, 'row': 3, 'blank': True},
			{'raw_name': 'Brka Msswe', 'score': None, 'row': 4, 'blank': True},
		]
		response = self._post(extracted, roster)
		self.assertEqual(response.status_code, 200)
		data = response.json()
		# Waliojazwa ni 2 tu — na ni alama zao wenyewe
		self.assertEqual(len(data['matched']), 2)
		matched_by_id = {row['id']: row['score'] for row in data['matched']}
		self.assertEqual(matched_by_id[self.student_one.id], 78)
		self.assertEqual(matched_by_id[self.student_two.id], 55)
		# Watatu wasiojazwa HAWAJAGUSIWA — hakuna alama iliyoingizwa kwao
		self.assertNotIn(third.id, matched_by_id)
		self.assertNotIn(fourth.id, matched_by_id)
		self.assertNotIn(fifth.id, matched_by_id)
		# Mwalimu aliyewaacha wazi (3, 4) hawaripotiwi missing — karatasi
		# ilithibitisha waziwazi cells zao tupu. Neema (5) ndiye missing —
		# AI haiwahi kumwona kabisa → mstari wa manjano kwa uhakiki.
		missing_ids = {m['id'] for m in data['missing']}
		self.assertEqual(missing_ids, {fifth.id})
		self.assertEqual(data['unmatched'], [])

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


class MarksEntryPreviewPdfTests(TestCase):
	"""The teacher's own review-before-save PDF — posted from the Marks
	Entry table's in-memory state after a photo/PDF scoresheet upload, so
	the teacher can check every row against the paper sheet before hitting
	'Hifadhi & Kagua'."""
	databases = {'default', 'results'}

	def setUp(self):
		self.exam = Exam.objects.create(name='Midterm 1', year=2026, form=1)
		self.subject = Subject.objects.create(name='Mathematics')
		self.teacher = TeacherAccount.objects.create(email='teacher@example.com', full_name='Teacher One', role=TeacherAccount.ROLE_TEACHER)
		self.teacher.subjects.set([self.subject])
		self.client = Client()
		self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')

	def test_renders_pdf_with_scores_absent_and_flagged_rows(self):
		payload = {
			'exam_id': self.exam.id,
			'subject_name': 'Mathematics',
			'rows': [
				{'name': 'Amina Juma', 'score': 78, 'is_absent': False, 'flagged': False},
				{'name': 'Peter Mushi', 'score': None, 'is_absent': True, 'flagged': False},
				{'name': 'Zawadi Rama', 'score': None, 'is_absent': False, 'flagged': True},
			],
		}
		response = self.client.post(
			reverse('marks_entry_preview_pdf'),
			data=json.dumps(payload), content_type='application/json',
		)
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
		self.assertIn('ZAWADI RAMA', text.upper())

	def test_exam_or_subject_name_with_angle_bracket_is_not_silently_dropped(self):
		"""ReportLab's Paragraph treats unescaped '<...>' as markup and
		swallows it silently (no error) -- an exam/subject name containing
		one must still render in full, not vanish from the header."""
		exam = Exam.objects.create(name='Mock <Series 1>', year=2026, form=1)
		response = self.client.post(
			reverse('marks_entry_preview_pdf'),
			data=json.dumps({'exam_id': exam.id, 'subject_name': 'Civics & Ethics', 'rows': []}),
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 200)

		import io
		import pdfplumber
		with pdfplumber.open(io.BytesIO(response.content)) as pdf:
			text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
		self.assertIn('Series 1', text)
		self.assertIn('Civics & Ethics', text)

	def test_missing_exam_returns_404(self):
		response = self.client.post(
			reverse('marks_entry_preview_pdf'),
			data=json.dumps({'exam_id': 999999, 'subject_name': 'Mathematics', 'rows': []}),
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 404)


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

	def test_merges_one_page_per_student_in_registration_order(self):
		"""Rows/pages follow registration order (Student.id — Amina was
		created first), not exam rank — see ResultsExportRegistrationOrderAndExcelStylesTests
		for a fixture that disambiguates registration order from both rank
		and alphabetical order."""
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
		self.assertLess(text.upper().index('AMINA JUMA'), text.upper().index('PETER MUSHI'))

	def test_slips_are_one_page_and_have_no_parent_signoff_block(self):
		"""Kila mwanafunzi ukurasa MMOJA tu (QR + sahihi ya mzazi vinaingia
		ukiurasa uleule), na block ya MAONI YA MZAZI/MLEZI na mistari yake
		ya dots imeondolewa — ilichukua nafasi bila maana kwenye slip."""
		client = Client()
		client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
		response = client.get(reverse('generate_bulk_student_results_pdf', args=[self.exam.id]))
		self.assertEqual(response.status_code, 200)
		import io
		import pdfplumber
		with pdfplumber.open(io.BytesIO(response.content)) as pdf:
			self.assertEqual(len(pdf.pages), 2)  # wanafunzi 2 = kurasa 2
			for page in pdf.pages:
				text = (page.extract_text() or '').upper()
				self.assertNotIn('MAONI YA MZAZI', text)
				self.assertNotIn('JINA LA MZAZI', text)

	def test_result_pdfs_are_attachments_not_new_windows(self):
		"""Content-Disposition lazima iwe 'attachment' — kivinjari kinapakua
		bila kufungua dirisha jipya tupu (target=_blank zimeondolewa kwenye
		templates; hii inalinda upande wa server pia)."""
		client = Client()
		client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
		resp_class = client.get(reverse('generate_results_pdf', args=[self.exam.id]) + '?style=necta')
		self.assertEqual(resp_class.status_code, 200)
		self.assertTrue(resp_class['Content-Disposition'].startswith('attachment'))
		resp_bulk = client.get(reverse('generate_bulk_student_results_pdf', args=[self.exam.id]))
		self.assertEqual(resp_bulk.status_code, 200)
		self.assertTrue(resp_bulk['Content-Disposition'].startswith('attachment'))

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

	def test_results_pdf_selected_students_only(self):
		"""?students= kwenye PDF ya matokeo → safu za waliochaguliwa tu, bila
		muhtasari wa darasa; CNO/nafasi ni za darasa zima."""
		client = Client()
		client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
		url = reverse('generate_results_pdf', args=[self.exam.id])
		for style in ('normal', 'necta'):
			response = client.get(f'{url}?style={style}&students={self.student_two.id}')
			self.assertEqual(response.status_code, 200, style)
			self.assertIn('Results_Waliochaguliwa_1', response['Content-Disposition'])
			import io
			import pdfplumber
			with pdfplumber.open(io.BytesIO(response.content)) as pdf:
				self.assertEqual(len(pdf.pages), 1, style)
				text = (pdf.pages[0].extract_text() or '').upper()
			self.assertIn('PETER MUSHI', text)
			self.assertNotIn('AMINA JUMA', text)
			self.assertNotIn('DIVISION PERFORMANCE SUMMARY', text)
			self.assertNotIn('EXAMINATION CENTRE OVERALL PERFORMANCE', text)
			self.assertIn('002', text)  # CNO ya darasa zima, si 001

	def test_results_pdf_selected_students_from_another_exam(self):
		other = Student.objects.create(first_name='Nje', middle_name='', last_name='Kabisa', gender='M')
		client = Client()
		client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
		url = reverse('generate_results_pdf', args=[self.exam.id])
		self.assertEqual(client.get(f'{url}?students={other.id}').status_code, 404)
		empty = client.get(f'{url}?students=')
		self.assertRedirects(empty, reverse('form_results', args=[self.exam.form]), fetch_redirect_response=False)


class ResultsExportRegistrationOrderAndExcelStylesTests(TestCase):
	"""The main results exports (PDF and Excel) list students in the
	school's actual registration order for this exam's form — the
	FormStudent roster, exactly as shown on the upload_form_students page
	(order_by('id')) — not ranked by exam position, not by Student.id, and
	not alphabetical. A student who was never on that roster (added later,
	e.g. via Marks Entry or a scoresheet scan that created a new Student on
	the fly) sorts after every registered student. "Top 5 Performers" is
	the one section that must still rank by actual score regardless of
	that row order. Each PDF ?style= (normal/rank/necta/royal/acsee) has a
	matching Excel export at the same ?style= on export_results_excel."""
	databases = {'default', 'results'}

	def setUp(self):
		self.school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
		self.exam = Exam.objects.create(name='Midterm 1', year=2026, form=2, school=self.school)
		self.subject = Subject.objects.create(name='Mathematics')

		# Student.id order is the OPPOSITE of the roster order on purpose —
		# Amina's Student row already existed (e.g. from a past exam) before
		# Zawadi's was created here, but the roster (FormStudent, this
		# exam's actual registration list) lists Zawadi first. A fix that
		# fell back to Student.id instead of the roster would get this
		# backwards, which is exactly the bug reported: students who are
		# high on the roster were showing up at the very bottom.
		self.amina = Student.objects.create(first_name='Amina', last_name='Ally', gender='F')
		self.zawadi = Student.objects.create(first_name='Zawadi', last_name='Zuberi', gender='F')
		FormStudent.objects.create(
			school=self.school, form=2, academic_year=2026, is_active=True,
			admission_no='S001', first_name='Zawadi', last_name='Zuberi', gender='F',
		)
		FormStudent.objects.create(
			school=self.school, form=2, academic_year=2026, is_active=True,
			admission_no='S002', first_name='Amina', last_name='Ally', gender='F',
		)
		# Lenatha Damian — never uploaded in the roster, added straight into
		# this exam (mirrors a teacher adding a student manually, or OCR
		# creating a new Student for an unmatched name). Best performer by
		# score, but must sort LAST in the main listing since he isn't in
		# the roster.
		self.lenatha = Student.objects.create(first_name='Lenatha', last_name='Damian', gender='M')

		# CSEE (Form 2) needs 7 subjects sat to get a real division/position
		# instead of INC (unranked) — these views always recompute on GET,
		# so a single-subject sitting would make every student here INC
		# and vanish from "Top Performers", which isn't what these tests
		# are about.
		extra_subjects = [
			Subject.objects.create(name=name)
			for name in ['English', 'Kiswahili', 'Biology', 'Chemistry', 'Physics', 'Civics']
		]
		for student, score in [(self.zawadi, 50), (self.amina, 70), (self.lenatha, 95)]:
			ExamResult.objects.create(exam=self.exam, student=student, subject=self.subject, score=score)
			for subject in extra_subjects:
				ExamResult.objects.create(exam=self.exam, student=student, subject=subject, score=score)
		ProcessedResult.objects.create(exam=self.exam, student=self.zawadi, total_score=50, average_score=50, points=5, position=3, division='III')
		ProcessedResult.objects.create(exam=self.exam, student=self.amina, total_score=70, average_score=70, points=3, position=2, division='II')
		ProcessedResult.objects.create(exam=self.exam, student=self.lenatha, total_score=95, average_score=95, points=1, position=1, division='I')

		self.academic = TeacherAccount.objects.create(email='academic@example.com', full_name='Academic One', role=TeacherAccount.ROLE_ACADEMIC, school=self.school)
		self.client = Client()
		self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')

	def test_pdf_lists_students_in_roster_order_with_unregistered_last(self):
		import io
		import pdfplumber
		response = self.client.get(reverse('generate_results_pdf', args=[self.exam.id]))
		self.assertEqual(response.status_code, 200)
		with pdfplumber.open(io.BytesIO(response.content)) as pdf:
			text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
		# Both names also appear earlier in the TOP 5 PERFORMERS section
		# (ranked by position) — use the LAST occurrence of each, which is
		# the main per-student results table, to check roster order:
		# Zawadi (1st on the roster) before Amina (2nd on the roster)
		# before Lenatha (not on the roster at all, despite being the top
		# performer).
		i_zuberi = text.rindex('Zuberi')
		i_ally = text.rindex('Ally')
		i_damian = text.rindex('Damian')
		self.assertLess(i_zuberi, i_ally)
		self.assertLess(i_ally, i_damian)

	def test_pdf_top4_still_ranked_by_actual_position(self):
		import io
		import pdfplumber
		response = self.client.get(reverse('generate_results_pdf', args=[self.exam.id]))
		with pdfplumber.open(io.BytesIO(response.content)) as pdf:
			text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
		top4_start = text.index('TOP 4 PERFORMERS')
		top4_section = text[top4_start:top4_start + 500]
		# Lenatha (position 1, the actual best performer) must lead the Top
		# 4 table even though he's listed LAST in the main roster-order
		# table (he isn't on the roster at all).
		self.assertLess(top4_section.index('Damian'), top4_section.index('Ally'))
		self.assertLess(top4_section.index('Ally'), top4_section.index('Zuberi'))

	def test_excel_lists_students_in_roster_order_with_unregistered_last(self):
		import io
		import openpyxl
		response = self.client.get(reverse('export_results_excel', args=[self.exam.id]))
		self.assertEqual(response.status_code, 200)
		wb = openpyxl.load_workbook(io.BytesIO(response.content))
		ws = wb.active
		names = [ws.cell(row=r, column=2).value for r in (4, 5, 6)]
		self.assertEqual(names, ['Zawadi Zuberi', 'Amina Ally', 'Lenatha Damian'])

	def test_excel_top5_still_ranked_by_actual_position(self):
		import io
		import openpyxl
		response = self.client.get(reverse('export_results_excel', args=[self.exam.id]))
		wb = openpyxl.load_workbook(io.BytesIO(response.content))
		ws = wb['Summary'] if 'Summary' in wb.sheetnames else wb['Muhtasari']
		header_row = next(
			r for r in range(1, ws.max_row + 1)
			if ws.cell(row=r, column=1).value in ('POS.', 'NAFASI')
		)
		first_name_in_top5 = ws.cell(row=header_row + 1, column=2).value
		self.assertEqual(first_name_in_top5, 'Lenatha Damian')

	def test_bulk_upload_job_status_endpoint(self):
		"""Upload ya scoresheet inatengeneza BulkUploadJob (OCR kwa nyuma);
		status endpoint inarudisha processing → preview bila Celery."""
		from .scan_models import BulkUploadJob
		job = BulkUploadJob.objects.create(
			exam=self.exam, subject=self.subject,
			status=BulkUploadJob.Status.PROCESSING,
		)
		resp = self.client.get(reverse('bulk_upload_status', args=[job.pk]))
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.json()['status'], 'processing')

		job.status = BulkUploadJob.Status.PREVIEW
		job.preview = {
			'preview': True, 'matched_count': 2, 'unmatched_count': 1,
			'unmatched': [{'raw_name': 'Haijulikani'}],
			'matched': [],
		}
		job.save()
		resp = self.client.get(reverse('bulk_upload_status', args=[job.pk]))
		self.assertEqual(resp.status_code, 200)
		data = resp.json()
		self.assertEqual(data['status'], 'preview')
		self.assertEqual(data['preview']['matched_count'], 2)

		# Job isiyyopo → 404 (siyo 500)
		resp = self.client.get(reverse('bulk_upload_status', args=[999999]))
		self.assertEqual(resp.status_code, 404)

	def test_form_results_excel_lists_students_in_roster_order(self):
		import io
		import openpyxl
		response = self.client.get(reverse('form_results_excel', args=[2]))
		self.assertEqual(response.status_code, 200)
		wb = openpyxl.load_workbook(io.BytesIO(response.content))
		ws = wb[wb.sheetnames[0]]
		names = [ws.cell(row=r, column=2).value for r in (4, 5, 6)]
		self.assertEqual(names, ['Zawadi Zuberi', 'Amina Ally', 'Lenatha Damian'])

	def test_excel_accepts_same_style_param_as_pdf(self):
		for style in ('normal', 'rank', 'necta', 'royal', 'acsee', 'junior', 'olevel'):
			response = self.client.get(reverse('export_results_excel', args=[self.exam.id]), {'style': style})
			self.assertEqual(response.status_code, 200, f'style={style}')
			self.assertEqual(
				response['Content-Type'],
				'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
			)

	def test_form_two_and_form_four_get_their_own_colours(self):
		"""Form 2 (junior/emerald) na Form 4 (olevel/ocean) zinapaswa kuwa
		na rangi zao mwenyewe — si kurudio tu la 'normal', na zisichukue
		rangi ya Form 5 (royal/purple) wala Form 6 (acsee/black-gold).

		Hii inahusu maombi ya mwalimu: kurasa tofauti za kila kiwango
		zioneke kuonyeshwa kwa utambulisho wa kawaida.
		"""
		from results.services.pdf_export_service import _THEMES
		from results.services.excel_export_service import _EXCEL_THEMES

		# Kila theme mpya ina kila ufunguo ule _THEMES['normal'] inaotumia,
		# hasa 'grid' — bila hiyo ukingo ungekuwa wa rangi ya royal.
		for key in ('header_bg', 'header_fg', 'band_bg', 'accent_bg', 'accent_fg', 'section_fg', 'page_bg', 'grid'):
			for theme in ('junior', 'olevel'):
				self.assertIn(key, _THEMES[theme], f'{theme}.{key}')

		# Rangi za kila theme lazima ziwe tofauti (Form 2 ≠ Form 4 ≠ 5 ≠ 6).
		sigs = {
			name: (
				str(_THEMES[name]['header_bg']),
				str(_THEMES[name]['page_bg']),
				_EXCEL_THEMES[name]['header_bg'],
			)
			for name in ('junior', 'olevel', 'royal', 'acsee')
		}
		self.assertEqual(len(set(sigs.values())), len(sigs), f'themes zinalingana: {sigs}')

		# Form 2/4 zinapaswa kukataza au kuacha rangi ya Form 5/6.
		for name, other, stolen in (
			('junior', 'royal', '#6B2FA0'),
			('junior', 'acsee', '#E5C96B'),
			('olevel', 'royal', '#6B2FA0'),
			('olevel', 'acsee', '#E5C96B'),
		):
			self.assertNotEqual(str(_THEMES[name]['header_bg']).upper(), stolen.upper(), f'{name} imechukua rangi ya {other}')

		# Zote mbili zina mandhari yao (page_bg) — hazipati 'None' kama normal.
		for name in ('junior', 'olevel'):
			self.assertIsNotNone(_THEMES[name]['page_bg'], name)

	# Na mtihani wa Form 2 unapaswa kupokea style=junior bila kurudi 'normal'
	def test_pdf_accepts_the_new_form_two_and_four_styles(self):
		for style in ('junior', 'olevel'):
			response = self.client.get(reverse('generate_results_pdf', args=[self.exam.id]), {'style': style})
			self.assertEqual(response.status_code, 200, f'style={style}')
			self.assertTrue(response['Content-Type'].startswith('application/pdf'), f'style={style}')

	# ── Divisheni zinaonekana kwa rangi (Form 2 na Form 4) ───────────
	def test_division_chips_have_colours_in_every_themed_style(self):
		"""Divisheni hazikiwezi kuwa hazionekani.

		Hitilafu hii ilikuwa: 'junior' na 'olevel' hawakuwa na
		rangi zao za divisheni, kwa hiyo zilirudi band_bg/header_fg
		— mpaka mpaka wa rangi ya kichwa. Div I "I" ilikuwa ya
		kijani kwenye kichwa cha kijani: hazikuwa na maana, ndiyo
		mwalimu alikuwa akisema "division hazionekani".

		Sasa kila style yenye rangi ina rangi zake za I, II, III,
		IV na 0.
		"""
		from results.services.pdf_export_service import _THEMES, DIV_BG_THEME, DIV_FG_THEME
		for style in ('junior', 'olevel', 'royal', 'acsee'):
			self.assertIn(style, DIV_BG_THEME, f'{style} haina rangi za divisheni')
			self.assertIn(style, DIV_FG_THEME, f'{style} haina rangi za nakala za divisheni')
			for division in ('I', 'II', 'III', 'IV', '0'):
				self.assertIn(division, DIV_BG_THEME[style], f'{style}: Div {division} haina rangi')
				self.assertIn(division, DIV_FG_THEME[style], f'{style}: Div {division} haina nakala')

		# Form 2 na Form 4 hazihitaji rangi zileile (zinatofautiana).
		self.assertNotEqual(
		 str(DIV_BG_THEME['junior']['I']),
		 str(DIV_BG_THEME['olevel']['I']),
		 'Form 2 na Form 4 zinatumia rangi ileile ya Division I',
		)

	def test_div_colour_chips_are_actually_readable(self):
		"""Nakala lazima ionyeshe juu ya mpaka wa rangi.

		Div I ya Form 2 ni nyeupe juu ya emerald iliyo ngumu. Kama
		mfumo ungekuwa na nakala ya njano kwenye njano, alama
		itaonekana kuwa haipo — hasa kwa wazee wa macho na kwa
		wanafunzi wa darasa.
		"""
		from results.services.pdf_export_service import DIV_BG_THEME, DIV_FG_THEME

		def luminance(c):
			def ch(v):
				v = max(0.0, min(1.0, v))
				return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
			return 0.2126 * ch(c.red) + 0.7152 * ch(c.green) + 0.0722 * ch(c.blue)

		for style in ('junior', 'olevel', 'royal', 'acsee'):
			for division in ('I', 'II', 'III', 'IV', '0'):
				bg = DIV_BG_THEME[style][division]
				fg = DIV_FG_THEME[style][division]
				l1, l2 = luminance(bg), luminance(fg)
				ratio = (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
				# WCAG AA kwa maandishi: 4.5:1
				self.assertGreaterEqual(
					ratio, 4.5,
					f'{style} Div {division}: contrast {ratio:.2f}:1 ni chini ya 4.5:1',
				)

	def test_div_colour_helper_is_used_in_every_division_cell(self):
		"""Seli zote za DIV zinapasita kupata rangi kutoka kichakato
		moja, ili Form 2/4 zisionekane za njia moja na zilizizo kwenye
		meza nyingine."""
		import inspect
		from results.services import pdf_export_service as svc
		src = inspect.getsource(svc)
		# Hakuna tena taratibu iliyokuwa ikirudi band_bg/header_fg moja kwa
		# moja kwenye sehemu ya meza kuu.
		self.assertIn('_div_colors(style_key, theme, r.division)', src)
		self.assertNotIn(
			"div_bg = theme['band_bg']",
			src,
			'kuna msimo uliobaki unaorudisha rangi ya kawaida badala ya rangi ya divisheni',
		)

	def test_excel_division_cells_use_theme_palette(self):
		"""Excel ndio inapaswa kuonyesha divisheni kwa rangi kama PDF."""
		from results.services.excel_export_service import _EXCEL_DIV_FILL
		for style in ('junior', 'olevel'):
			self.assertIn(style, _EXCEL_DIV_FILL)
			for division in ('I', 'II', 'III', 'IV', '0'):
				self.assertIn(division, _EXCEL_DIV_FILL[style], f'{style}: Div {division} haina rangi ya Excel')
				bg, fg = _EXCEL_DIV_FILL[style][division]
				self.assertNotEqual(bg, fg, f'{style} Div {division}: rangi na nakala ni zileile')


class SetClassTeacherAndConductTests(TestCase):
	"""The two new report-card sign-off screens: the Academic Officer
	assigns a class teacher (+ headmaster comment + term dates), and that
	class teacher then sets a conduct grade per student + one class-wide
	comment."""
	databases = {'default', 'results'}

	def setUp(self):
		self.school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
		self.exam = Exam.objects.create(name='Midterm 1', year=2026, form=2, school=self.school)
		self.subject = Subject.objects.create(name='Mathematics')
		self.student_one = Student.objects.create(first_name='Amina', last_name='Juma', gender='F')
		self.student_two = Student.objects.create(first_name='Peter', last_name='Mushi', gender='M')
		ExamResult.objects.create(exam=self.exam, student=self.student_one, subject=self.subject, score=78)
		ExamResult.objects.create(exam=self.exam, student=self.student_two, subject=self.subject, score=55)
		self.result_one = ProcessedResult.objects.create(exam=self.exam, student=self.student_one, total_score=78, average_score=78, points=2, position=1, division='I')
		self.result_two = ProcessedResult.objects.create(exam=self.exam, student=self.student_two, total_score=55, average_score=55, points=5, position=2, division='III')
		self.academic = TeacherAccount.objects.create(email='academic@example.com', full_name='Academic One', role=TeacherAccount.ROLE_ACADEMIC, school=self.school)
		self.class_teacher = TeacherAccount.objects.create(email='classteacher@example.com', full_name='Class Teacher One', role=TeacherAccount.ROLE_TEACHER, school=self.school)
		self.other_teacher = TeacherAccount.objects.create(email='other@example.com', full_name='Other Teacher', role=TeacherAccount.ROLE_TEACHER, school=self.school)

	def test_academic_can_assign_class_teacher_and_headmaster_comment(self):
		client = Client()
		client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
		response = client.post(reverse('set_class_teacher', args=[self.exam.id]), {
			'class_teacher_id': str(self.class_teacher.id),
			'headmaster_comment': 'Hongera kwa juhudi.',
			'term_closing_date': '2026-11-01',
			'term_opening_date': '2027-01-05',
		})
		self.assertEqual(response.status_code, 302)
		self.exam.refresh_from_db()
		self.assertEqual(self.exam.class_teacher_id, self.class_teacher.id)
		self.assertEqual(self.exam.headmaster_comment, 'Hongera kwa juhudi.')
		self.assertEqual(str(self.exam.term_closing_date), '2026-11-01')

	def test_non_academic_cannot_assign_class_teacher(self):
		client = Client()
		client.force_login(self.class_teacher, backend='results.backends.ResultsAuthBackend')
		response = client.get(reverse('set_class_teacher', args=[self.exam.id]))
		self.assertEqual(response.status_code, 403)

	def test_assigned_class_teacher_can_save_conduct_and_comment(self):
		self.exam.class_teacher = self.class_teacher
		self.exam.save(update_fields=['class_teacher'])

		client = Client()
		client.force_login(self.class_teacher, backend='results.backends.ResultsAuthBackend')
		get_response = client.get(reverse('set_conduct_and_comments', args=[self.exam.id]))
		self.assertEqual(get_response.status_code, 200)

		post_response = client.post(
			reverse('set_conduct_and_comments', args=[self.exam.id]),
			data=json.dumps({
				'conduct': [
					{'result_id': self.result_one.id, 'grades': {'uaminifu': 'A', 'michezo': 'B'}},
					{'result_id': self.result_two.id, 'grades': {'uaminifu': 'C', 'michezo': 'A'}},
				],
				'class_teacher_comment': 'Ufaulu ni mzuri, aendelee hivyo hivyo.',
			}),
			content_type='application/json',
		)
		self.assertEqual(post_response.status_code, 200)
		self.result_one.refresh_from_db()
		self.result_two.refresh_from_db()
		self.exam.refresh_from_db()
		self.assertEqual(self.result_one.conduct_grades, {'uaminifu': 'A', 'michezo': 'B'})
		# A weak-academic student can still score well on a specific
		# category — categories are independent, not one grade for all six.
		self.assertEqual(self.result_two.conduct_grades, {'uaminifu': 'C', 'michezo': 'A'})
		self.assertEqual(self.exam.class_teacher_comment, 'Ufaulu ni mzuri, aendelee hivyo hivyo.')

	def test_unrelated_teacher_cannot_set_conduct(self):
		self.exam.class_teacher = self.class_teacher
		self.exam.save(update_fields=['class_teacher'])

		client = Client()
		client.force_login(self.other_teacher, backend='results.backends.ResultsAuthBackend')
		response = client.get(reverse('set_conduct_and_comments', args=[self.exam.id]))
		self.assertEqual(response.status_code, 403)

	def test_academic_can_set_conduct_even_if_not_the_class_teacher(self):
		self.exam.class_teacher = self.class_teacher
		self.exam.save(update_fields=['class_teacher'])

		client = Client()
		client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
		response = client.get(reverse('set_conduct_and_comments', args=[self.exam.id]))
		self.assertEqual(response.status_code, 200)

	def test_unsaved_conduct_defaults_from_average_score(self):
		# result_one averages 78 (Division I) -> should default to 'A' on
		# every category; result_two averages 55 (Division III) -> 'C'.
		# This is only ever a starting point shown in the form — nothing is
		# written to the DB until the teacher actually saves.
		client = Client()
		client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
		response = client.get(reverse('set_conduct_and_comments', args=[self.exam.id]))
		self.assertEqual(response.status_code, 200)
		payload = json.loads(response.context['students_json'])
		by_id = {row['result_id']: row for row in payload}
		self.assertEqual(by_id[self.result_one.id]['grades']['uaminifu'], 'A')
		self.assertEqual(by_id[self.result_two.id]['grades']['michezo'], 'C')
		self.result_one.refresh_from_db()
		self.assertEqual(self.result_one.conduct_grades, {})


class BulkScoresheetPreviewPdfTests(TestCase):
    """Review-before-save PDF: the academic officer's bulk-upload review
    screen posts the CURRENT (possibly hand-corrected) table state here and
    gets back a PDF laid out like the paper scoresheet, so they can check
    every row landed on the right student before anything is saved."""
    databases = {'default', 'results'}

    def setUp(self):
        self.school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
        self.exam = Exam.objects.create(name='Midterm 1', year=2026, form=2, school=self.school)
        self.academic = TeacherAccount.objects.create(email='academic@example.com', full_name='Academic One', role=TeacherAccount.ROLE_ACADEMIC, school=self.school)
        self.teacher = TeacherAccount.objects.create(email='teacher@example.com', full_name='Teacher One', role=TeacherAccount.ROLE_TEACHER, school=self.school)
        self.client = Client()

    def test_renders_pdf_with_scores_absent_and_missing_rows(self):
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        payload = {
            'subject_name': 'Mathematics',
            'rows': [
                {'name': 'Amina Juma', 'score': 78, 'is_absent': False, 'status': 'matched'},
                {'name': 'Peter Mushi', 'score': None, 'is_absent': True, 'status': 'matched'},
                {'name': 'Zawadi Rama', 'score': None, 'is_absent': False, 'status': 'missing'},
            ],
        }
        response = self.client.post(
            reverse('bulk_scoresheet_preview_pdf', args=[self.exam.id]),
            data=json.dumps(payload), content_type='application/json',
        )
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
        self.assertIn('PETER MUSHI', text.upper())
        self.assertIn('ZAWADI RAMA', text.upper())

    def test_rejects_non_academic_teacher(self):
        self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')
        response = self.client.post(
            reverse('bulk_scoresheet_preview_pdf', args=[self.exam.id]),
            data=json.dumps({'subject_name': 'Mathematics', 'rows': []}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_bad_json_returns_400(self):
        self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')
        response = self.client.post(
            reverse('bulk_scoresheet_preview_pdf', args=[self.exam.id]),
            data='not json', content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)


class MergeDuplicateHistorySubjectsMigrationTests(TestCase):
	"""Data migration 0035: production had ended up with several
	differently-cased/typo'd 'Historia ya Tanzania na Maadili' Subject rows
	(created by an old path that bypassed normalize_subject_name), each
	with a blank `code` -- so on the results PDF both History and Historia
	fell back to the same 4-letter truncation ("HIST") and were
	indistinguishable. This exercises the actual migration function
	against real data, including a genuine FK conflict, to make sure the
	merge is safe to run against production."""
	databases = {'default', 'results'}

	def setUp(self):
		"""These tests exercise migration 0035 in isolation, but migration
		0043 seeds the full standard subject sets into the test DB before
		any test runs. Wipe whatever is pre-seeded so assertions about
		which Subject rows exist only see this test's own fixtures."""
		Subject.objects.all().delete()

	def _run_migration(self):
		import importlib
		module = importlib.import_module('results.migrations.0035_merge_duplicate_history_subjects')
		from django.apps import apps
		module.merge_and_backfill(apps, None)

	def test_merges_variants_repoints_fks_and_backfills_codes(self):
		history = Subject.objects.create(name='History')
		canonical = Subject.objects.create(name='Historia ya Tanzania na Maadili')
		variant_lower_t = Subject.objects.create(name='Historia ya tanzania na Maadili')
		variant_upper = Subject.objects.create(name='HISTORIA YA TANZANIA NA MAADILI')
		variant_typo = Subject.objects.create(name='Historian ya Tanzania na maadili')

		school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
		exam = Exam.objects.create(name='Midterm 1', year=2026, form=1, school=school)
		student_a = Student.objects.create(first_name='Amina', last_name='Juma', gender='F')
		student_b = Student.objects.create(first_name='Peter', last_name='Mushi', gender='M')

		# Straightforward re-point: only exists under a variant.
		ExamResult.objects.create(exam=exam, student=student_a, subject=variant_lower_t, score=60)
		# Genuine conflict: student_b already has a result under the
		# CANONICAL subject for this exam -- the variant's row must be
		# dropped, not crash the migration with a unique-constraint error.
		ExamResult.objects.create(exam=exam, student=student_b, subject=canonical, score=70)
		ExamResult.objects.create(exam=exam, student=student_b, subject=variant_upper, score=99)

		SchoolSubject.objects.create(school=school, subject=variant_typo)

		self._run_migration()

		# Only the canonical Historia row (and plain History) survive.
		remaining = set(Subject.objects.filter(name__icontains='hist').values_list('name', flat=True))
		self.assertEqual(remaining, {'History', 'Historia ya Tanzania na Maadili'})

		# Codes backfilled so the PDF/Excel can tell them apart.
		history.refresh_from_db()
		canonical.refresh_from_db()
		self.assertEqual(history.code, 'HIST')
		self.assertEqual(canonical.code, 'HIST/M')

		# Straightforward case re-pointed to canonical.
		result_a = ExamResult.objects.get(exam=exam, student=student_a)
		self.assertEqual(result_a.subject_id, canonical.id)
		self.assertEqual(result_a.score, 60)

		# Conflict case: canonical's pre-existing result (70) survives;
		# the variant's conflicting result (99) was dropped, not merged.
		self.assertEqual(ExamResult.objects.filter(exam=exam, student=student_b).count(), 1)
		result_b = ExamResult.objects.get(exam=exam, student=student_b)
		self.assertEqual(result_b.subject_id, canonical.id)
		self.assertEqual(result_b.score, 70)

		# M2M-free single-FK model with no conflict risk re-pointed too.
		self.assertTrue(SchoolSubject.objects.filter(school=school, subject=canonical).exists())

	def test_merges_m2m_subject_references(self):
		canonical = Subject.objects.create(name='Historia ya Tanzania na Maadili')
		variant = Subject.objects.create(name='HISTORIA YA TANZANIA NA MAADILI')
		other_subject = Subject.objects.create(name='Geography')

		school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
		student = FormStudent.objects.create(school=school, form=5, first_name='Amina', last_name='Juma', gender='F')
		student.subjects.set([variant, other_subject])

		teacher = TeacherAccount.objects.create(email='t1@example.com', full_name='Teacher One', role=TeacherAccount.ROLE_TEACHER)
		teacher.subjects.set([variant])

		self._run_migration()

		self.assertEqual(set(student.subjects.values_list('name', flat=True)), {'Historia ya Tanzania na Maadili', 'Geography'})
		self.assertEqual(set(teacher.subjects.values_list('name', flat=True)), {'Historia ya Tanzania na Maadili'})
		self.assertFalse(Subject.objects.filter(id=variant.id).exists())

	def test_no_duplicates_is_a_safe_no_op(self):
		Subject.objects.create(name='History')
		Subject.objects.create(name='Historia ya Tanzania na Maadili')
		self._run_migration()  # must not raise
		self.assertEqual(Subject.objects.filter(name__icontains='hist').count(), 2)

	def test_no_history_subjects_at_all_creates_nothing(self):
		"""A school that doesn't teach History/Historia must not end up
		with a spurious Subject row just because the migration ran."""
		Subject.objects.create(name='Geography')
		self._run_migration()
		self.assertFalse(Subject.objects.filter(name__icontains='hist').exists())

	def test_promotes_oldest_row_when_no_row_is_exactly_canonical(self):
		"""If the correctly-spelled canonical name doesn't exist at all
		(every row is a case/typo variant), the oldest variant is renamed
		to canonical rather than being discarded."""
		only_variant = Subject.objects.create(name='HISTORIA YA TANZANIA NA MAADILI')
		self._run_migration()
		only_variant.refresh_from_db()
		self.assertEqual(only_variant.name, 'Historia ya Tanzania na Maadili')
		self.assertEqual(only_variant.code, 'HIST/M')


class SubjectPdfPerformanceTests(TestCase):
	"""generate_subject_pdf_response used to run 3-4 queries PER
	FormStudent (fs.subjects.exists() x2 + Student.get_or_create, then a
	Student.objects.filter(id=...).first() per blank row) -- a 300-student
	form meant ~900 queries to render one subject's PDF. Locks in the
	bulk-resolved fix: query count must stay flat regardless of roster
	size, subject-restricted students must still be excluded correctly,
	and blank/scored/absent rows must still come out right."""
	databases = {'default', 'results'}

	def test_query_count_flat_and_rows_still_correct(self):
		from django.db import connections
		from django.test.utils import CaptureQueriesContext
		from .services.subject_pdf_service import generate_subject_pdf_response

		school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
		exam = Exam.objects.create(name='Midterm', year=2026, form=2, school=school)
		subject = Subject.objects.create(name='Mathematics')
		other_subject = Subject.objects.create(name='Physics')

		# 15 scored, 15 absent, 10 with no ExamResult at all (blank rows)
		# -- all three paths used to issue queries per row.
		for i in range(40):
			fs = FormStudent.objects.create(
				school=school, form=2, first_name=f'Student{i}', last_name='Test',
				gender='F' if i % 2 else 'M', admission_no=f'ADM{i}',
				academic_year=exam.year,
			)
			if i < 30:
				student, _ = Student.objects.get_or_create(
					first_name=f'Student{i}', last_name='Test', defaults={'gender': fs.gender},
				)
				if i < 15:
					ExamResult.objects.create(exam=exam, student=student, subject=subject, score=60 + (i % 30))
				else:
					ExamResult.objects.create(exam=exam, student=student, subject=subject, score=None, is_absent=True)

		# Explicitly does NOT take this subject -- must be excluded, not
		# just left unscored.
		excluded = FormStudent.objects.create(school=school, form=2, first_name='Excluded', last_name='Person', gender='M', admission_no='ADM-EXC')
		excluded.subjects.set([other_subject])

		with CaptureQueriesContext(connections['results']) as ctx:
			response = generate_subject_pdf_response(exam, subject)

		self.assertEqual(response.status_code, 200)
		self.assertLess(len(ctx.captured_queries), 15, 'query count must not scale with roster size')

		import io
		import pdfplumber
		with pdfplumber.open(io.BytesIO(response.content)) as pdf:
			text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
		text_upper = text.upper()
		self.assertIn('STUDENT0 TEST', text_upper)   # scored
		self.assertIn('STUDENT15 TEST', text_upper)  # absent
		self.assertIn('STUDENT30 TEST', text_upper)  # blank row (in roster, no ExamResult)
		self.assertNotIn('EXCLUDED PERSON', text_upper)


class UploadFormStudentsPageQueryCountTests(TestCase):
	"""The Upload Form Students page renders an assign-subjects checkbox
	grid: {% for s in students %}{% for subj in all_subjects %}{% if subj
	in s.subjects.all %}. Without prefetching, `s.subjects.all()` re-runs
	as a fresh query on EVERY (student, subject) pair -- for a form with
	S students and N subjects that's S*N queries, not S+N. Against a
	remote database this was slow enough to trip the gunicorn worker
	timeout and surface as a 500 / upstream error to the user."""
	databases = {'default', 'results'}

	def test_query_count_does_not_multiply_students_by_subjects(self):
		from django.db import connections
		from django.test.utils import CaptureQueriesContext
		from .models import SchoolSubject

		school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
		academic = TeacherAccount.objects.create(
			email='academic3@example.com', full_name='Academic Three',
			role=TeacherAccount.ROLE_ACADEMIC, school=school,
		)
		# 15 subjects offered at this school, 25 students on the form --
		# small enough to run fast in tests but large enough that an
		# S*N query pattern (375) would dwarf a flat S+N pattern (40).
		for i in range(15):
			subject = Subject.objects.create(name=f'Subject{i}')
			SchoolSubject.objects.create(school=school, subject=subject)
		for i in range(25):
			fs = FormStudent.objects.create(
				school=school, form=1, first_name=f'Student{i}', last_name='Test',
				gender='M', admission_no=f'ADM{i}', academic_year=2026,
			)
			# Every student has a couple of subjects assigned, so the
			# `{% if subj in s.subjects.all %}` branch actually evaluates
			# `True` sometimes too, not just the (cheap) False path.
			fs.subjects.set(Subject.objects.filter(name__in=['Subject0', 'Subject1']))

		client = Client()
		client.force_login(academic, backend='results.backends.ResultsAuthBackend')

		with CaptureQueriesContext(connections['results']) as ctx:
			response = client.get(reverse('upload_form_students'), {'form': '1'})

		self.assertEqual(response.status_code, 200)
		self.assertLess(
			len(ctx.captured_queries), 25,
			f'query count scaled with students*subjects: {len(ctx.captured_queries)} queries',
		)


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

	def test_generate_places_double_periods_on_consecutive_slots(self):
		# self.slot1/self.slot2 are back-to-back on Monday (setUp); this
		# Tuesday slot is not adjacent to either of them.
		tuesday_slot = TimeSlot.objects.create(school=self.school, day_of_week=1, order=0, start_time='08:00', end_time='08:40')
		TeachingAssignment.objects.create(
			school=self.school, form=1, stream='A', subject=self.math, teacher=self.teacher,
			periods_per_week=2, double_period=True,
		)
		entries, unplaced = generate_class_timetable(self.school)
		self.assertEqual(unplaced, [])
		slot_ids = {e['time_slot_id'] for e in entries}
		self.assertEqual(slot_ids, {self.slot1.id, self.slot2.id})
		self.assertNotIn(tuesday_slot.id, slot_ids)

	def test_double_period_goes_unplaced_without_a_consecutive_pair(self):
		# One slot per day across two separate days — no two slots are
		# ever adjacent, so a double session can never be seated.
		TimeSlot.objects.all().delete()
		TimeSlot.objects.create(school=self.school, day_of_week=0, order=0, start_time='08:00', end_time='08:40')
		TimeSlot.objects.create(school=self.school, day_of_week=1, order=0, start_time='08:00', end_time='08:40')
		TeachingAssignment.objects.create(
			school=self.school, form=1, stream='A', subject=self.math, teacher=self.teacher,
			periods_per_week=2, double_period=True,
		)
		entries, unplaced = generate_class_timetable(self.school)
		self.assertEqual(entries, [])
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


class HistoriaYaTanzaniaNaMaadiliTests(TestCase):
	"""History and Historia ya Tanzania na Maadili must stay distinct."""

	databases = {'default', 'results'}

	def test_normalize_keeps_the_two_history_subjects_apart(self):
		from .utils import normalize_subject_name
		for raw in ('History', 'HIST', 'hist'):
			self.assertEqual(normalize_subject_name(raw), 'History')
		for raw in ('HIST/M', 'hist-m', 'HISTM', 'Historia ya Tanzania na Maadili',
					'Maadili', 'History of Tanzania and Ethics', 'HTE'):
			self.assertEqual(normalize_subject_name(raw), 'Historia ya Tanzania na Maadili')

	def test_canon_subject_keeps_them_apart(self):
		from .combinations import canon_subject
		self.assertEqual(canon_subject('HIST'), 'History')
		self.assertEqual(canon_subject('HIST/M'), 'Historia ya Tanzania na Maadili')
		self.assertNotEqual(canon_subject('History'), canon_subject('Historia ya Tanzania na Maadili'))

	def test_safe_get_or_create_stamps_short_code(self):
		from .utils import safe_get_or_create_subject
		self.assertEqual(safe_get_or_create_subject('History').code, 'HIST')
		self.assertEqual(
			safe_get_or_create_subject('Historia ya Tanzania na Maadili').code, 'HIST/M')

	def test_code_is_backfilled_on_a_pre_existing_row(self):
		from .utils import safe_get_or_create_subject
		Subject.objects.create(name='Historia ya Tanzania na Maadili')  # no code
		subject = safe_get_or_create_subject('Historia ya Tanzania na Maadili')
		self.assertEqual(subject.code, 'HIST/M')

	def test_safe_get_or_create_normalises_raw_aliases(self):
		from .utils import safe_get_or_create_subject
		a = safe_get_or_create_subject('HIST/M')
		b = safe_get_or_create_subject('Maadili')
		self.assertEqual(a.pk, b.pk)
		self.assertEqual(a.name, 'Historia ya Tanzania na Maadili')

	def test_resolve_subject_columns_splits_two_history_columns(self):
		from .utils import resolve_subject_columns
		# pandas renames a duplicate "HIST" header to "HIST.1"
		resolved = resolve_subject_columns(['GEOG', 'HIST', 'HIST.1'])
		self.assertEqual(resolved, [
			('GEOG', 'Geography'),
			('HIST', 'History'),
			('HIST.1', 'Historia ya Tanzania na Maadili'),
		])

	def test_resolve_subject_columns_leaves_distinct_headers_alone(self):
		from .utils import resolve_subject_columns
		resolved = resolve_subject_columns(['History', 'HIST/M'])
		self.assertEqual(resolved, [
			('History', 'History'),
			('HIST/M', 'Historia ya Tanzania na Maadili'),
		])

	def test_upload_with_two_history_columns_creates_two_subjects(self):
		import io
		from django.core.files.uploadedfile import SimpleUploadedFile
		from .services.upload_processing_service import process_uploaded_results
		exam = Exam.objects.create(name='Mock', year=2026, form=4)
		csv = (
			"First Name,Last Name,Gender,HIST,HIST\n"
			"Asha,Juma,F,80,55\n"
		)
		process_uploaded_results(exam, SimpleUploadedFile(
			'r.csv', csv.encode('utf-8'), content_type='text/csv'))
		names = set(ExamResult.objects.filter(exam=exam).values_list('subject__name', flat=True))
		self.assertEqual(names, {'History', 'Historia ya Tanzania na Maadili'})

	def test_historia_ya_tanzania_never_enters_an_acsee_combination(self):
		from .combinations import detect_acsee_combination
		# Student's real combination is HGK; HIST/M is just an extra subject.
		code, subs = detect_acsee_combination(
			['History', 'Geography', 'Kiswahili', 'Historia ya Tanzania na Maadili'],
			lambda n: 1,
		)
		self.assertEqual(code, 'HGK')
		self.assertNotIn('Historia ya Tanzania na Maadili', subs)


class AcseeSubsidiarySubjectTests(TestCase):
	def test_general_studies_and_bam_are_subsidiary(self):
		from .utils import is_acsee_subsidiary_subject
		for name in (
			'General Studies', 'general studies', 'GS', 'G/Studies', 'G Studies',
			'Basic Applied Mathematics', 'basic applied maths', 'BAM',
			'Applied Mathematics', '  General   Studies  ',
		):
			self.assertTrue(is_acsee_subsidiary_subject(name), name)

	def test_principal_subjects_are_not_subsidiary(self):
		from .utils import is_acsee_subsidiary_subject
		for name in ('Physics', 'Advanced Mathematics', 'History', 'Economics', 'Mathematics', ''):
			self.assertFalse(is_acsee_subsidiary_subject(name), name)


class AcseeCombinationDetectionTests(TestCase):
	def test_canon_subject_normalises_aliases(self):
		from .combinations import canon_subject
		self.assertEqual(canon_subject('Maths'), 'Advanced Mathematics')
		self.assertEqual(canon_subject('  mathematics '), 'Advanced Mathematics')
		self.assertEqual(canon_subject('ENGLISH'), 'English Language')
		self.assertEqual(canon_subject('Literature in English'), 'Literature in English')
		self.assertEqual(canon_subject('Literature'), 'Literature in English')
		self.assertEqual(canon_subject('Phy'), 'Physics')
		self.assertEqual(canon_subject('BAM'), 'Basic Applied Mathematics')
		self.assertEqual(canon_subject('Nutmeg Studies'), 'Nutmeg Studies')

	def test_necta_printed_slip_abbreviations_resolve(self):
		"""Abbreviations NECTA itself prints on ACSEE result slips.

		Real slip S4828/0508 (ACSEE 2024) reads "GEOGR - 'C'" and
		"ADV/MATHS - 'C'" — with a slash. Unmapped, they canonicalised to
		'Geogr'/'Adv/maths', which appear in NO combination, so those
		candidates fell through to a naive best-3 and could be given the
		wrong division. NECTA counted CBG (Chem 4 + Bio 5 + Geog 3 = 12)
		and dropped the Divinity the candidate had scored better in.
		"""
		from .combinations import ACSEE_COMBINATIONS, canon_subject
		in_a_combination = {s for subs in ACSEE_COMBINATIONS.values() for s in subs}
		for raw in ('GEOGR', 'GEOG', 'ADV/MATHS', 'ADV MATHS', 'ADV/MATH'):
			self.assertIn(canon_subject(raw), in_a_combination, raw)
		self.assertEqual(canon_subject('GEOGR'), 'Geography')
		self.assertEqual(canon_subject('ADV/MATHS'), 'Advanced Mathematics')

	def test_slip_abbreviations_still_detect_the_right_combination(self):
		"""Slip S4828/0508 verbatim — NECTA printed AGGT 12, Div II."""
		from .combinations import canon_subject, detect_acsee_combination
		from .utils import get_grade_points
		sat = {'G/STUDIES': 'D', 'GEOGR': 'C', 'DIVINITY': 'B',
		       'CHEMISTRY': 'D', 'BIOLOGY': 'E', 'BAM': 'F'}
		by_canon = {}
		for name, grade in sat.items():
			pts = get_grade_points(grade, form=6)
			cname = canon_subject(name)
			if cname not in by_canon or pts < by_canon[cname][1]:
				by_canon[cname] = (name, pts)
		code, subs = detect_acsee_combination(by_canon.keys(), lambda n: by_canon[n][1])
		self.assertEqual(code, 'CBG')
		self.assertEqual(sum(by_canon[s][1] for s in subs), 12)

	def test_detects_unambiguous_combination(self):
		from .combinations import detect_acsee_combination
		code, subs = detect_acsee_combination(
			['Physics', 'Chemistry', 'Biology'], lambda n: 1)
		self.assertEqual(code, 'PCB')
		self.assertEqual(set(subs), {'Physics', 'Chemistry', 'Biology'})
		code, _ = detect_acsee_combination(
			['History', 'Geography', 'Kiswahili'], lambda n: 1)
		self.assertEqual(code, 'HGK')

	def test_no_match_returns_none(self):
		from .combinations import detect_acsee_combination
		self.assertIsNone(detect_acsee_combination(
			['Physics', 'History', 'Kiswahili'], lambda n: 1))

	def test_hgl_and_hgli_are_distinguished(self):
		from .combinations import detect_acsee_combination
		code, _ = detect_acsee_combination(
			['History', 'Geography', 'English Language'], lambda n: 1)
		self.assertEqual(code, 'HGL')
		code, subs = detect_acsee_combination(
			['History', 'Geography', 'Literature'], lambda n: 1)
		self.assertEqual(code, 'HGLi')
		self.assertIn('Literature in English', subs)

	def test_ambiguous_match_drops_the_best_extra_subject(self):
		from .combinations import detect_acsee_combination
		# Physics/Chemistry/Biology/Advanced Mathematics satisfies PCB, PCM
		# and CBM. Maths is the student's best subject (1 pt), the rest 5.
		# The conservative pick is the combination totalling the MOST
		# points — PCB — so the strong Maths is left uncounted.
		points = {'Advanced Mathematics': 1, 'Physics': 5, 'Chemistry': 5, 'Biology': 5}
		code, subs = detect_acsee_combination(
			['Physics', 'Chemistry', 'Biology', 'Mathematics'], lambda n: points[n])
		self.assertEqual(code, 'PCB')
		self.assertNotIn('Advanced Mathematics', subs)


class RecomputeAcseeDivisionTests(TestCase):
	"""ACSEE (Form 5-6) division: the student's COMBINATION subjects only,
	extras dropped. A combination short of 3 gets INC (1-2 sat) or ABS
	(0 sat) instead of a computed division."""

	databases = {'default', 'results'}

	def setUp(self):
		self.exam = Exam.objects.create(name='Mock ACSEE', year=2026, form=5)
		self._subjects = {}

	def _subject(self, name):
		if name not in self._subjects:
			self._subjects[name] = Subject.objects.create(name=name)
		return self._subjects[name]

	def _student(self, first, last):
		return Student.objects.create(first_name=first, middle_name='', last_name=last, gender='M')

	def _enter(self, student, **scores):
		for subject_name, score in scores.items():
			ExamResult.objects.create(
				exam=self.exam, student=student,
				subject=self._subject(subject_name.replace('_', ' ')), score=score,
			)

	def _processed(self, student):
		from .services.upload_processing_service import recompute_processed_results_for_exam
		recompute_processed_results_for_exam(self.exam)
		return ProcessedResult.objects.get(exam=self.exam, student=student)

	def test_general_studies_and_bam_excluded_from_division(self):
		# PCB combination: Physics D(4), Chemistry D(4), Biology E(5) -> 13
		# -> Div III. BAM C(3) is better than Biology but must NOT count.
		student = self._student('Asha', 'Kimaro')
		self._enter(student, Physics=52, Chemistry=55, Biology=45,
			Basic_Applied_Mathematics=65, General_Studies=42)
		result = self._processed(student)
		self.assertEqual(result.points, 13)
		self.assertEqual(result.division, 'III')
		self.assertTrue(result.counted_subjects.startswith('PCB:'), result.counted_subjects)
		self.assertNotIn('Basic Applied Mathematics', result.counted_subjects)
		self.assertNotIn('General Studies', result.counted_subjects)

	def test_extra_fourth_principal_subject_is_not_counted_even_if_better(self):
		# PCB student who also sat Advanced Mathematics and aced it.
		# Combination subjects: Physics C(3), Chemistry C(3), Biology E(5)
		# -> 11 -> Div II. A naive best-3 would take Maths A(1) instead of
		# Biology -> 7 -> Div I, which is wrong.
		student = self._student('Deo', 'Marwa')
		self._enter(student, Physics=62, Chemistry=62, Biology=42,
			Advanced_Mathematics=95, General_Studies=80)
		result = self._processed(student)
		self.assertEqual(result.points, 11)
		self.assertEqual(result.division, 'II')
		self.assertTrue(result.counted_subjects.startswith('PCB:'), result.counted_subjects)
		self.assertNotIn('Advanced Mathematics', result.counted_subjects)

	def test_arts_combination_is_detected(self):
		# HGL: English C(3), History D(4), Geography E(5) -> 12 -> Div II.
		student = self._student('Rehema', 'Kato')
		self._enter(student, History=55, Geography=45, English_Language=62)
		result = self._processed(student)
		self.assertEqual(result.points, 12)
		self.assertEqual(result.division, 'II')
		self.assertTrue(result.counted_subjects.startswith('HGL:'), result.counted_subjects)

	def test_three_subject_combination_with_subsidiaries_is_division_I(self):
		student = self._student('Frank', 'Noel')
		self._enter(student, Physics=85, Chemistry=78, Biology=70,
			General_Studies=55, Basic_Applied_Mathematics=60)
		result = self._processed(student)
		self.assertEqual(result.points, 5)          # A(1) + B(2) + B(2)
		self.assertEqual(result.division, 'I')
		self.assertTrue(result.counted_subjects.startswith('PCB:'), result.counted_subjects)
		self.assertNotIn('General Studies', result.counted_subjects)

	def test_ranking_tiebreak_uses_combination_total_not_general_studies(self):
		# Both are PCB with 3 points. A's combination marks total less than
		# B's, but A also has a huge General Studies mark. Ranking must go
		# by the combination total only -> B first.
		a = self._student('Aled', 'One')
		self._enter(a, Physics=80, Chemistry=80, Biology=80, General_Studies=99)
		b = self._student('Bex', 'Two')
		self._enter(b, Physics=83, Chemistry=83, Biology=83)
		from .services.upload_processing_service import recompute_processed_results_for_exam
		recompute_processed_results_for_exam(self.exam)
		a_r = ProcessedResult.objects.get(exam=self.exam, student=a)
		b_r = ProcessedResult.objects.get(exam=self.exam, student=b)
		self.assertEqual((a_r.points, b_r.points), (3, 3))
		self.assertLess(b_r.position, a_r.position)

	def test_student_absent_in_all_subjects_ranks_last(self):
		good = self._student('Good', 'Student')
		self._enter(good, Physics=90, Chemistry=90, Biology=90)
		absent = self._student('Absent', 'Student')
		ExamResult.objects.create(
			exam=self.exam, student=absent, subject=self._subject('Physics'),
			score=None, is_absent=True,
		)
		from .services.upload_processing_service import recompute_processed_results_for_exam
		recompute_processed_results_for_exam(self.exam)
		good_r = ProcessedResult.objects.get(exam=self.exam, student=good)
		absent_r = ProcessedResult.objects.get(exam=self.exam, student=absent)
		self.assertEqual(absent_r.division, 'ABS')
		self.assertIsNone(absent_r.position)
		self.assertIsNotNone(good_r.position)

	def test_single_principal_subject_gets_INC(self):
		# Only 1 of the 3 combination subjects sat -> INC, no division.
		student = self._student('Baraka', 'Mushi')
		self._enter(student, Physics=85)
		result = self._processed(student)
		self.assertEqual(result.division, 'INC')

	def test_single_principal_subject_F_still_gets_INC(self):
		# INC applies regardless of the score in the one subject sat.
		student = self._student('Neema', 'Paul')
		self._enter(student, Physics=20)
		result = self._processed(student)
		self.assertEqual(result.division, 'INC')

	def test_two_principal_subjects_get_INC(self):
		# 2 of 3 combination subjects sat -> INC, no division.
		student = self._student('Juma', 'Ally')
		self._enter(student, Physics=85, Chemistry=75)
		result = self._processed(student)
		self.assertEqual(result.division, 'INC')

	def test_inc_candidate_is_unranked_unlike_a_full_three_subject_candidate(self):
		full = self._student('Full', 'Combination')
		self._enter(full, Physics=85, Chemistry=85, Biology=85)  # 3 pts, Div I
		partial = self._student('One', 'Subject')
		self._enter(partial, History=85)  # only 1 of 3 -> INC
		from .services.upload_processing_service import recompute_processed_results_for_exam
		recompute_processed_results_for_exam(self.exam)
		full_r = ProcessedResult.objects.get(exam=self.exam, student=full)
		partial_r = ProcessedResult.objects.get(exam=self.exam, student=partial)
		self.assertEqual(full_r.division, 'I')
		self.assertEqual(partial_r.division, 'INC')
		self.assertIsNotNone(full_r.position)
		self.assertIsNone(partial_r.position)

	def test_three_full_principals_are_not_padded(self):
		student = self._student('Grace', 'Mena')
		self._enter(student, Physics=62, Chemistry=55, Geography=45)  # C,D,E = 3+4+5
		result = self._processed(student)
		self.assertEqual(result.points, 12)
		self.assertEqual(result.division, 'II')

	def test_only_subsidiary_subjects_gets_ABS(self):
		# General Studies / BAM are never combination subjects -> sitting
		# ONLY those counts as zero principal subjects sat -> ABS.
		student = self._student('Said', 'Omary')
		self._enter(student, General_Studies=65, Basic_Applied_Mathematics=70)
		result = self._processed(student)
		self.assertEqual(result.division, 'ABS')
		self.assertIsNone(result.position)


class RecomputeCseeMinimumSubjectRuleTests(TestCase):
	"""CSEE candidates who sat FEWER than 7 subjects get the INC marker
	(masomo hayajafika 7) — no division is computed from an incomplete
	sitting. Candidates who sat NOTHING get ABS with a NULL position."""

	databases = {'default', 'results'}

	def setUp(self):
		self.exam = Exam.objects.create(name='Terminal', year=2026, form=4)

	def _run(self, **scores):
		student = Student.objects.create(first_name='Test', middle_name='', last_name='Pupil', gender='F')
		for name, score in scores.items():
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=self.exam, student=student, subject=subject, score=score)
		from .services.upload_processing_service import recompute_processed_results_for_exam
		recompute_processed_results_for_exam(self.exam)
		return ProcessedResult.objects.get(exam=self.exam, student=student)

	def test_fewer_than_seven_subjects_get_INC(self):
		result = self._run(Physics=90, Chemistry=88, Biology=85)  # 3x A
		self.assertEqual(result.division, 'INC')

	def test_grade_tie_is_broken_by_score_not_by_subject_name(self):
		"""Two subjects sharing a grade must not be separated by NAME.

		The best-7 cut happens after the sort, so a tie between two
		grade-D subjects decided which one got thrown away. The rows
		arrive ordered by subject name, so "Zoology" was dropped before
		"History" — a candidate could lose a 44 to a 31 on alphabetical
		order alone. TOTAL, AVERAGE and the position tiebreaker all come
		from the kept rows, so that one mark also moved them down the
		ranking while their division stayed correct.
		"""
		from .services.upload_processing_service import recompute_processed_results_for_exam
		strong = dict(Agriculture=80, Biology=70, Chemistry=68, Divinity=50,
		              English=49, Geography=47)          # A,B,B,C,C,C
		weak = dict(History=31, Zoology=44)              # both grade D
		results = {}
		for first, marks in (('Asha', weak), ('Baraka', dict(History=44, Zoology=31))):
			student = Student.objects.create(first_name=first, last_name='Test', gender='F')
			for name, score in {**strong, **marks}.items():
				subject, _ = Subject.objects.get_or_create(name=name)
				ExamResult.objects.create(exam=self.exam, student=student, subject=subject, score=score)
			recompute_processed_results_for_exam(self.exam)
			results[first] = ProcessedResult.objects.get(exam=self.exam, student=student)

		asha, baraka = results['Asha'], results['Baraka']
		# Same multiset of marks -> identical everything. Only the subject
		# each 44 belongs to differs.
		self.assertEqual(asha.total_score, baraka.total_score)
		self.assertEqual(asha.average_score, baraka.average_score)
		self.assertEqual(asha.points, baraka.points)
		self.assertEqual(asha.division, baraka.division)
		# each keeps their own 44 rather than the 31
		self.assertIn('Zoology', asha.counted_subjects)
		self.assertIn('History', baraka.counted_subjects)

	def test_a_higher_mark_always_survives_the_cut(self):
		"""The kept mark must be the highest available, whatever its name."""
		from .services.upload_processing_service import recompute_processed_results_for_exam
		student = Student.objects.create(first_name='Keep', last_name='Best', gender='M')
		marks = dict(Aardvark=80, Buffalo=70, Camel=68, Donkey=50, Eagle=49,
		             Falcon=47, Gopher=44, Zebra=31)   # Gopher & Zebra both D
		for name, score in marks.items():
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=self.exam, student=student, subject=subject, score=score)
		recompute_processed_results_for_exam(self.exam)
		result = ProcessedResult.objects.get(exam=self.exam, student=student)
		self.assertIn('Gopher', result.counted_subjects)   # 44 kept
		self.assertNotIn('Zebra', result.counted_subjects)  # 31 dropped
		self.assertEqual(result.total_score, 408)
		self.assertEqual(result.points, 18)
		self.assertEqual(result.division, 'II')

	def test_fewer_than_seven_with_fails_also_get_INC(self):
		result = self._run(Physics=20, Chemistry=25)  # 2x F
		self.assertEqual(result.division, 'INC')

	def test_exactly_seven_subjects_get_a_real_division(self):
		subjects = ['Physics', 'Chemistry', 'Biology', 'Mathematics', 'English', 'Kiswahili', 'Civics']
		student = Student.objects.create(first_name='Full', last_name='House', gender='M')
		for name, score in zip(subjects, [90, 90, 90, 90, 90, 90, 90]):  # 7x A = 7 pts
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=self.exam, student=student, subject=subject, score=score)
		from .services.upload_processing_service import recompute_processed_results_for_exam
		recompute_processed_results_for_exam(self.exam)
		result = ProcessedResult.objects.get(exam=self.exam, student=student)
		self.assertEqual(result.division, 'I')

	def test_absent_in_all_subjects_gets_ABS_marker_and_no_position(self):
		student = Student.objects.create(first_name='Ghost', last_name='Candidate', gender='F')
		for name in ['Physics', 'Chemistry']:
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=self.exam, student=student, subject=subject, score=None, is_absent=True)
		from .services.upload_processing_service import recompute_processed_results_for_exam
		recompute_processed_results_for_exam(self.exam)
		result = ProcessedResult.objects.get(exam=self.exam, student=student)
		self.assertEqual(result.division, 'ABS')
		self.assertIsNone(result.position)

	def test_INC_is_unranked_like_ABS(self):
		# A 7-subject Division IV student is ranked; a 3-subject INC one
		# is not — INC gets no position, same as ABS.
		full = Student.objects.create(first_name='Full', last_name='Seven', gender='M')
		for name, score in zip(
			['Physics', 'Chemistry', 'Biology', 'Mathematics', 'English', 'Kiswahili', 'Civics'],
			[20, 20, 20, 20, 20, 20, 20],  # 7x F (<30) = 35 pts -> Div 0, still ranked
		):
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=self.exam, student=full, subject=subject, score=score)
		partial = Student.objects.create(first_name='Partial', last_name='Three', gender='F')
		for name, score in [('Physics', 90), ('Chemistry', 88), ('Biology', 85)]:
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=self.exam, student=partial, subject=subject, score=score)
		from .services.upload_processing_service import recompute_processed_results_for_exam
		recompute_processed_results_for_exam(self.exam)
		full_r = ProcessedResult.objects.get(exam=self.exam, student=full)
		partial_r = ProcessedResult.objects.get(exam=self.exam, student=partial)
		self.assertEqual(full_r.division, '0')
		self.assertEqual(partial_r.division, 'INC')
		self.assertIsNotNone(full_r.position)
		self.assertIsNone(partial_r.position)

	def test_fewer_subjects_straight_As_does_not_outrank_full_subject_straight_As(self):
		"""A 4-subject straight-A student is INC (fewer than 7 subjects) —
		INC ranks below every real division, so the 7-subject straight-A
		Division I student must come first. (Was previously the
		Division-IV cap; now the INC marker serves the same purpose.)"""
		partial = Student.objects.create(first_name='Partial', last_name='Subjects', gender='F')
		for name, score in [('Physics', 90), ('Chemistry', 88), ('Biology', 85), ('Mathematics', 92)]:
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=self.exam, student=partial, subject=subject, score=score)

		full = Student.objects.create(first_name='Full', last_name='Subjects', gender='M')
		for name, score in [
			('Physics', 90), ('Chemistry', 88), ('Biology', 85), ('Mathematics', 92),
			('English', 91), ('Kiswahili', 90), ('Civics', 93),
		]:
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=self.exam, student=full, subject=subject, score=score)

		from .services.upload_processing_service import recompute_processed_results_for_exam
		recompute_processed_results_for_exam(self.exam)
		partial_r = ProcessedResult.objects.get(exam=self.exam, student=partial)
		full_r = ProcessedResult.objects.get(exam=self.exam, student=full)

		self.assertEqual(partial_r.points, 4)
		self.assertEqual(partial_r.division, 'INC')
		self.assertEqual(full_r.points, 7)
		self.assertEqual(full_r.division, 'I')
		self.assertIsNotNone(full_r.position)
		self.assertIsNone(partial_r.position)

	def test_within_same_division_lower_points_still_ranks_first(self):
		better = Student.objects.create(first_name='Better', last_name='Points', gender='F')
		worse = Student.objects.create(first_name='Worse', last_name='Points', gender='M')
		subjects = ['Physics', 'Chemistry', 'Biology', 'Mathematics', 'English', 'Kiswahili', 'Civics']
		# Both Division I (points <= 17), but `better` scores higher overall.
		for name, score in zip(subjects, [90, 90, 90, 90, 90, 90, 90]):  # 7x A = 7 pts
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=self.exam, student=better, subject=subject, score=score)
		for name, score in zip(subjects, [70, 70, 70, 70, 70, 70, 70]):  # 7x B = 14 pts
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=self.exam, student=worse, subject=subject, score=score)

		from .services.upload_processing_service import recompute_processed_results_for_exam
		recompute_processed_results_for_exam(self.exam)
		better_r = ProcessedResult.objects.get(exam=self.exam, student=better)
		worse_r = ProcessedResult.objects.get(exam=self.exam, student=worse)

		self.assertEqual((better_r.division, worse_r.division), ('I', 'I'))
		self.assertLess(better_r.position, worse_r.position)


class RecomputeCseePositionRankingMigrationTests(TestCase):
	"""Data migration 0036 backfills the division-first ranking fix onto
	every existing CSEE exam's already-cached ProcessedResult rows."""
	databases = {'default', 'results'}

	def _run_migration(self):
		import importlib
		module = importlib.import_module('results.migrations.0036_recompute_csee_position_ranking')
		from django.apps import apps
		module.recompute_csee_exams(apps, None)

	def test_recomputes_stale_position_for_existing_csee_exam(self):
		exam = Exam.objects.create(name='Terminal', year=2026, form=4)
		partial = Student.objects.create(first_name='Partial', last_name='Subjects', gender='F')
		full = Student.objects.create(first_name='Full', last_name='Subjects', gender='M')
		for name, score in [('Physics', 90), ('Chemistry', 88), ('Biology', 85), ('Mathematics', 92)]:
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=exam, student=partial, subject=subject, score=score)
		for name, score in [
			('Physics', 90), ('Chemistry', 88), ('Biology', 85), ('Mathematics', 92),
			('English', 91), ('Kiswahili', 90), ('Civics', 93),
		]:
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=exam, student=full, subject=subject, score=score)

		# Simulate the OLD (buggy) cached ranking: partial (fewer subjects,
		# lower raw points) was stored as position 1.
		ProcessedResult.objects.create(exam=exam, student=partial, total_score=355, average_score=88.75, points=4, position=1, division='IV')
		ProcessedResult.objects.create(exam=exam, student=full, total_score=629, average_score=89.86, points=7, position=2, division='I')

		self._run_migration()

		partial_r = ProcessedResult.objects.get(exam=exam, student=partial)
		full_r = ProcessedResult.objects.get(exam=exam, student=full)
		self.assertIsNotNone(full_r.position)
		self.assertIsNone(partial_r.position)

	def test_non_csee_exams_are_left_alone(self):
		"""ACSEE (form 5-6) exams aren't touched by this backfill."""
		exam = Exam.objects.create(name='Mock ACSEE', year=2026, form=5)
		student = Student.objects.create(first_name='Asha', last_name='Kimaro', gender='F')
		for name, score in [('Physics', 85), ('Chemistry', 85), ('Biology', 85)]:
			subject, _ = Subject.objects.get_or_create(name=name)
			ExamResult.objects.create(exam=exam, student=student, subject=subject, score=score)
		self._run_migration()  # must not raise on an ACSEE exam
		self.assertFalse(ProcessedResult.objects.filter(exam=exam).exists())


def _build_docx_bytes(*, table_rows=None, paragraph_lines=None):
	from io import BytesIO
	from docx import Document

	doc = Document()
	if table_rows:
		table = doc.add_table(rows=0, cols=len(table_rows[0]))
		for row in table_rows:
			cells = table.add_row().cells
			for i, value in enumerate(row):
				cells[i].text = value
	if paragraph_lines:
		for line in paragraph_lines:
			doc.add_paragraph(line)
	buf = BytesIO()
	doc.save(buf)
	return buf.getvalue()


class DocxRosterUploadTests(TestCase):
	"""Roster upload also accepts a .docx (Word) class list -- a table
	first, falling back to one student per paragraph line, sharing the
	exact same row/line parsing as the PDF roster path."""

	databases = {'default', 'results'}

	def _docx_file(self, name='roster.docx', **kwargs):
		from django.core.files.uploadedfile import SimpleUploadedFile
		content = _build_docx_bytes(**kwargs)
		return SimpleUploadedFile(
			name, content,
			content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
		)

	def test_parses_students_from_a_docx_table(self):
		from .views import _parse_docx_roster
		docx_file = self._docx_file(table_rows=[
			['Jina la Mwanafunzi', 'Jinsia'],
			['Amina Juma', 'F'],
			['Peter Mushi', 'M'],
		])
		collected = []
		_parse_docx_roster(docx_file, on_student=lambda f, m, l, g, c='': collected.append((f, m, l, g)))
		names = {(row[0], row[2]) for row in collected}
		self.assertEqual(names, {('Amina', 'Juma'), ('Peter', 'Mushi')})

	def test_parses_students_from_docx_paragraph_lines_when_no_table(self):
		from .views import _parse_docx_roster
		docx_file = self._docx_file(paragraph_lines=[
			'Halima Ally Mohamed F',
			'John Peter Komba M',
		])
		collected = []
		_parse_docx_roster(docx_file, on_student=lambda f, m, l, g, c='': collected.append((f, m, l, g)))
		self.assertEqual(len(collected), 2)
		self.assertIn(('Halima', 'Ally', 'Mohamed', 'F'), collected)
		self.assertIn(('John', 'Peter', 'Komba', 'M'), collected)

	def test_collect_roster_rows_dispatches_docx_by_flag(self):
		from .views import _collect_roster_rows
		docx_file = self._docx_file(paragraph_lines=['Amina Juma F'])
		rows = _collect_roster_rows(docx_file, is_pdf=False, is_docx=True)
		self.assertEqual(rows, [('Amina', '', 'Juma', 'F', '')])

	def test_docx_table_with_candidate_number_score_and_signature_columns(self):
		"""The real-world 'C/NO. | NAME | SCORE | SIGNATURE' class-list
		layout: candidate number must be captured (not merged into the
		name), Score/Signature columns must never contaminate the name,
		blank padding rows and a repeated page-title row (duplicated
		across every column) must be skipped."""
		from .views import _parse_docx_roster
		docx_file = self._docx_file(table_rows=[
			['C/NO.', 'NAME', 'SCORE', 'SIGNATURE'],
			['S2475/0001', 'AGNES ANDREW MALEMA', '', ''],
			['', '', '', ''],  # blank padding row
			['REPEAT', 'REPEAT', 'REPEAT', 'REPEAT'],  # simulated repeated title row
			['S2475/0002', 'PETER MUSHI', '78', 'x'],
		])
		collected = []
		_parse_docx_roster(docx_file, on_student=lambda f, m, l, g, c='': collected.append((f, m, l, g, c)))
		self.assertEqual(collected, [
			('Agnes', 'Andrew', 'Malema', 'M', 'S2475/0001'),
			('Peter', '', 'Mushi', 'M', 'S2475/0002'),
		])

	def test_docx_table_candidate_number_flows_into_form_student_admission_no(self):
		"""End to end: Upload Form Students with a C/NO.-column docx must
		store the real candidate number as admission_no, not a random
		placeholder."""
		from .models import FormStudent
		from .views import _bulk_save_form_students, _collect_roster_rows

		school = School.objects.create(name='Malinyi Secondary', region='Njombe', district='Kilolo')
		docx_file = self._docx_file(table_rows=[
			['C/NO.', 'NAME', 'SCORE', 'SIGNATURE'],
			['S2475/0001', 'AGNES ANDREW MALEMA', '', ''],
		])
		rows = _collect_roster_rows(docx_file, is_pdf=False, is_docx=True, form_num=1)
		_bulk_save_form_students(school, 1, rows)

		fs = FormStudent.objects.get(school=school, form=1, first_name='Agnes')
		self.assertEqual(fs.admission_no, 'S2475/0001')

	def test_upload_roster_view_accepts_docx(self):
		teacher = TeacherAccount.objects.create(email='t2@example.com', full_name='Teacher Two', role=TeacherAccount.ROLE_TEACHER)
		client = Client()
		client.force_login(teacher, backend='results.backends.ResultsAuthBackend')
		docx_file = self._docx_file(paragraph_lines=['Amina Juma F', 'Peter Mushi M'])
		response = client.post(reverse('upload_roster'), {'file': docx_file})
		self.assertEqual(response.status_code, 200)
		data = response.json()
		names = {s['name'] for s in data.get('students', [])}
		self.assertEqual(names, {'Amina Juma', 'Peter Mushi'})

	def test_upload_form_students_view_accepts_docx(self):
		"""End-to-end HTTP test for the Academic Officer's 'Upload Form
		Students' page with a .docx file -- catches wiring bugs (like a
		missing is_pdf=False) that a direct call to the parsing helpers
		would not."""
		from .models import FormStudent

		school = School.objects.create(name='Malinyi Secondary', region='Njombe', district='Kilolo')
		academic = TeacherAccount.objects.create(
			email='academic2@example.com', full_name='Academic Two',
			role=TeacherAccount.ROLE_ACADEMIC, school=school,
		)
		client = Client()
		client.force_login(academic, backend='results.backends.ResultsAuthBackend')
		docx_file = self._docx_file(table_rows=[
			['C/NO.', 'NAME', 'SCORE', 'SIGNATURE'],
			['S2475/0001', 'AGNES ANDREW MALEMA', '', ''],
		])
		response = client.post(
			f"{reverse('upload_form_students')}?form=2",
			{'form': '2', 'student_file': docx_file},
		)
		self.assertEqual(response.status_code, 302)
		# The view swallows exceptions into a Django message and still
		# redirects (302) either way -- the real proof the upload worked
		# is that the student actually got saved, not the status code.
		fs = FormStudent.objects.get(school=school, form=2, first_name='Agnes')
		self.assertEqual(fs.last_name, 'Malema')
		self.assertEqual(fs.admission_no, 'S2475/0001')


class MarksEntryAddStudentTests(TestCase):
	"""A student added inline on the Marks Entry page must stick — the
	review page filters marks to the roster, so the new student has to be
	written into the teacher's StoredRoster or the row vanishes."""

	databases = {'default', 'results'}

	def setUp(self):
		from .models import FormStudent, StoredRoster
		self.StoredRoster = StoredRoster
		self.school = School.objects.create(name='Mfano Sekondari', region='Dodoma', district='Dodoma')
		self.exam = Exam.objects.create(name='Terminal', year=2026, form=4, school=self.school)
		self.subject = Subject.objects.create(name='History')
		self.teacher = TeacherAccount.objects.create(
			email='t@example.com', full_name='Mwalimu', role=TeacherAccount.ROLE_TEACHER,
			school=self.school)
		self.teacher.subjects.set([self.subject])
		FormStudent.objects.create(
			school=self.school, form=4, first_name='Asha', last_name='Kimaro', gender='F',
			academic_year=self.exam.year)
		self.client = Client()
		self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')

	def _add(self, first, last):
		return self.client.post(
			reverse('marks_entry_add_student'),
			data=json.dumps({
				'exam_id': self.exam.id, 'subject_id': self.subject.id,
				'first_name': first, 'last_name': last, 'gender': 'M',
			}),
			content_type='application/json',
		)

	def test_added_student_is_written_into_the_stored_roster(self):
		resp = self._add('Baraka', 'Mushi')
		self.assertEqual(resp.status_code, 200)
		new_id = resp.json()['id']

		stored = self.StoredRoster.objects.get(
			teacher=self.teacher, exam=self.exam, subject=self.subject)
		names = {s['name'] for s in stored.students}
		ids = {s['id'] for s in stored.students}
		self.assertIn(new_id, ids)                       # the new student
		self.assertIn('Asha Kimaro', names)              # seeded from FormStudent
		self.assertEqual(stored.student_count, len(stored.students))

	def test_added_student_survives_into_the_review_page(self):
		new_id = self._add('Baraka', 'Mushi').json()['id']

		save = self.client.post(
			reverse('marks_entry_save'),
			data=json.dumps({
				'exam_id': self.exam.id, 'subject_id': self.subject.id,
				'entries': [{'student_id': new_id, 'score': 72}],
			}),
			content_type='application/json',
		)
		self.assertEqual(save.status_code, 200)

		review = self.client.get(
			reverse('marks_entry') + f'?exam={self.exam.id}&subject={self.subject.id}&review=1')
		self.assertContains(review, 'Baraka')

	def test_adding_twice_does_not_duplicate_the_roster_row(self):
		first_id = self._add('Baraka', 'Mushi').json()['id']
		self._add('Baraka', 'Mushi')
		stored = self.StoredRoster.objects.get(
			teacher=self.teacher, exam=self.exam, subject=self.subject)
		self.assertEqual([s['id'] for s in stored.students].count(first_id), 1)


class CentreCountedSubjectsTests(TestCase):
	"""The class-results PDF 'Subjects Counted' / centre GPA divisor."""

	def _counted(self, form, *counted_subjects):
		from types import SimpleNamespace
		from .services.pdf_export_service import _centre_counted_subjects
		rows = [SimpleNamespace(counted_subjects=cs) for cs in counted_subjects]
		return _centre_counted_subjects(rows, form)

	def test_olevel_falls_back_to_seven_when_rows_have_no_counted_subjects(self):
		self.assertEqual(self._counted(4, '', None), 7)
		self.assertEqual(self._counted(4), 7)          # no results at all

	def test_alevel_falls_back_to_three(self):
		self.assertEqual(self._counted(5, ''), 3)

	def test_uses_the_widest_real_count_when_present(self):
		# one partial candidate (4 subjects), one full (7)
		self.assertEqual(self._counted(
			4,
			'Maths, Eng, Kisw, Bio',
			'Maths, Eng, Kisw, Bio, Chem, Phys, Geo',
		), 7)

	def test_alevel_combination_prefix_still_counts_three(self):
		self.assertEqual(self._counted(5, 'PCB: Physics, Chemistry, Biology'), 3)


class TeacherScanNoWorkerFallbackTests(TestCase):
	"""A teacher's scoresheet scan must still work when NO Celery worker is
	running (local docker starts web+redis+db without the celery container,
	or a production deploy is missing the separate `worker` service).
	Before, the task was queued into redis and never consumed — the frontend
	polled for 4 minutes and died with a generic 'failed to read photo'.

	It was then fixed by running the OCR INLINE in this request as a
	Celery-less fallback — but that blocked the request for as long as the
	vision-model call took (up to several minutes on a multi-page scan),
	which every reverse proxy in front of gunicorn kills long before it
	finishes: the browser saw that as a bare "Failed to fetch". The
	fallback now runs the OCR in a background thread and returns a task_id
	immediately, exactly like the real Celery path, so the request itself
	never blocks — see _run_scoresheet_ocr_background in marks_entry.py.

	These tests deliberately do NOT touch celery conf (no eager toggling) —
	only the worker-probe is patched, so they can't leak state into the
	eager-polling tests above."""

	databases = {'default', 'results'}

	def setUp(self):
		self.exam = Exam.objects.create(name='Terminal 1', year=2026, form=1)
		self.subject = Subject.objects.create(name='Biology')
		self.student = Student.objects.create(first_name='Amina', middle_name='', last_name='Juma', gender='F')
		self.teacher = TeacherAccount.objects.create(email='fallback@example.com', full_name='Teacher Two', role=TeacherAccount.ROLE_TEACHER)
		self.teacher.subjects.set([self.subject])
		self.client = Client()
		self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')

	def test_no_worker_runs_ocr_in_background_thread_not_inline(self):
		# Patch the task itself (the name the view looks up) — no real celery
		# machinery runs at all, so these tests can't leak state anywhere.
		# The patches must stay active until the background thread has
		# actually run process_scoresheet_photo_task (it looks the name up
		# from module globals at execution time, not when the thread was
		# spawned) — stopping them right after the POST races the thread
		# and can let it call the REAL task against fake bytes, leaking a
		# stray thread into later tests. So the poll loop below runs INSIDE
		# both `with` blocks, and they only exit once status != 'processing'.
		with patch('results.marks_entry.process_scoresheet_photo_task') as task, \
				patch('results.marks_entry._celery_worker_consuming', return_value=False):
			task.return_value = {'matched': [{'id': self.student.id, 'score': 64, 'is_absent': False, 'raw_name': 'Amina Juma', 'confidence': 1.0, 'is_new': False}], 'unmatched': [], 'missing': []}
			from django.core.files.uploadedfile import SimpleUploadedFile
			photo = SimpleUploadedFile('sheet.jpg', b'fake-bytes', content_type='image/jpeg')
			resp = self.client.post(reverse('scoresheet_photo_extract'), {
				'photo': photo,
				'exam_id': self.exam.id,
				'subject_id': self.subject.id,
				'roster': json.dumps([{'id': self.student.id, 'name': 'Amina Juma'}]),
			})
			# The request returns immediately with a task_id (202) — it
			# must NOT block waiting for the OCR result inline.
			self.assertEqual(resp.status_code, 202)
			task_id = resp.json().get('task_id')
			self.assertTrue(task_id and task_id.startswith('localocr-'))

			import time
			poll = data = None
			for _ in range(50):
				poll = self.client.get(reverse('scoresheet_extract_status', args=[task_id]))
				data = poll.json()
				if data.get('status') != 'processing':
					break
				time.sleep(0.05)
			else:
				self.fail('background OCR thread never finished')
		self.assertEqual(poll.status_code, 200)
		self.assertEqual(len(data.get('matched', [])), 1)
		self.assertEqual(data['matched'][0]['id'], self.student.id)
		self.assertEqual(data['matched'][0]['score'], 64)

	def test_worker_present_returns_task_id(self):
		task = patch('results.marks_entry.process_scoresheet_photo_task').start()
		task.apply_async.return_value.id = 'test-task-id'
		with patch('results.marks_entry._celery_worker_consuming', return_value=True):
			from django.core.files.uploadedfile import SimpleUploadedFile
			photo = SimpleUploadedFile('sheet.jpg', b'fake-bytes', content_type='image/jpeg')
			resp = self.client.post(reverse('scoresheet_photo_extract'), {
				'photo': photo,
				'exam_id': self.exam.id,
				'subject_id': self.subject.id,
				'roster': json.dumps([{'id': self.student.id, 'name': 'Amina Juma'}]),
			})
		patch.stopall()
		self.assertEqual(resp.status_code, 202)
		self.assertEqual(resp.json().get('task_id'), 'test-task-id')

	def test_status_unknown_task_returns_processing_not_error(self):
		resp = self.client.get(reverse('scoresheet_extract_status', args=['ghost-task-id']))
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.json().get('status'), 'processing')


class ResolveOrCreateStudentTests(TestCase):
	"""Middle-name-aware Student dedup. Isingiro bug: brothers sharing
	first+last names (Privatus Gordian Laurian #216 / Privatus Leonce
	Laurian #217) collapsed into one Student because get_or_create keyed
	on (first, last) only — adding #217 returned #216 and his marks were
	written onto the wrong kid."""

	databases = {'default', 'results'}

	def _resolve(self, first, middle, last, gender='M'):
		from .utils import resolve_or_create_student
		return resolve_or_create_student(first, middle, last, gender)

	def test_brother_with_different_middle_gets_his_own_row(self):
		gordian, created1 = self._resolve('Privatus', 'Gordian', 'Laurian')
		leonce, created2 = self._resolve('Privatus', 'Leonce', 'Laurian')
		self.assertTrue(created1)
		self.assertTrue(created2)
		self.assertNotEqual(gordian.id, leonce.id)
		self.assertEqual(gordian.middle_name, 'Gordian')
		self.assertEqual(leonce.middle_name, 'Leonce')

	def test_same_full_name_resolves_to_the_same_student(self):
		first, created1 = self._resolve('Privatus', 'Leonce', 'Laurian')
		again, created2 = self._resolve('Privatus', 'Leonce', 'Laurian')
		self.assertTrue(created1)
		self.assertFalse(created2)
		self.assertEqual(first.id, again.id)

	def test_name_only_row_backfills_middle_and_converges(self):
		# Old upload saved the kid without a middle name; adding the full
		# name later must reuse that row (and fill the middle), not fork.
		name_only, created1 = self._resolve('Privatus', '', 'Laurian')
		with_middle, created2 = self._resolve('Privatus', 'Gordian', 'Laurian')
		self.assertTrue(created1)
		self.assertFalse(created2)
		self.assertEqual(name_only.id, with_middle.id)
		self.assertEqual(with_middle.middle_name, 'Gordian')

	def test_blank_middle_request_converges_on_existing_full_name(self):
		full, _ = self._resolve('Privatus', 'Gordian', 'Laurian')
		blank, created = self._resolve('Privatus', '', 'Laurian')
		self.assertFalse(created)
		self.assertEqual(full.id, blank.id)


class AcademicAddStudentSiblingTests(TestCase):
	"""POST academic_add_student_marks (action=add_student) with a
	brother's full name must create the brother — not return the existing
	sibling (Isingiro: adding #217 returned #216) — and retries must not
	mint duplicate roster rows."""

	databases = {'default', 'results'}

	def setUp(self):
		self.school = School.objects.create(name='Isingiro Sekondari', region='Kagera', district='Kyerwa')
		self.exam = Exam.objects.create(name='Midterm 2026', year=2026, form=1, school=self.school)
		self.academic = TeacherAccount.objects.create(
			email='academic@example.com', full_name='Academic Officer',
			role=TeacherAccount.ROLE_ACADEMIC, school=self.school)
		self.client = Client()
		self.client.force_login(self.academic, backend='results.backends.ResultsAuthBackend')

	def _add(self, first, middle, last):
		return self.client.post(
			reverse('academic_add_student_marks'),
			data=json.dumps({
				'action': 'add_student', 'exam_id': self.exam.id,
				'first_name': first, 'middle_name': middle, 'last_name': last,
				'gender': 'M',
			}),
			content_type='application/json',
		)

	def test_adding_brother_returns_the_brother_not_the_sibling(self):
		r216 = self._add('Privatus', 'Gordian', 'Laurian').json()
		r217 = self._add('Privatus', 'Leonce', 'Laurian').json()
		self.assertNotEqual(r216['student']['id'], r217['student']['id'])
		self.assertIn('Leonce', r217['student']['name'])
		self.assertTrue(Student.objects.filter(
			first_name='Privatus', middle_name='Leonce', last_name='Laurian').exists())

	def test_re_adding_same_student_does_not_duplicate_roster_rows(self):
		first = self._add('Privatus', 'Leonce', 'Laurian').json()
		second = self._add('Privatus', 'Leonce', 'Laurian').json()
		self.assertEqual(first['student']['id'], second['student']['id'])
		self.assertEqual(FormStudent.objects.filter(
			school=self.school, form=1,
			first_name='Privatus', middle_name='Leonce', last_name='Laurian',
		).count(), 1)


class SpecialCaseMarkTests(TestCase):
    """Alama zilizoandikwa vibaye kwenye scoresheet.

    Namba kama "1O.6" (badala ya "10.6") hazisomeki vizuri, na AI
    ndiye anayedhamini. Kabla ya mabadiliko haya alama kama hizo
    zilipita kama zilivyokuwa kawaida — mwanafunzi alipata alama
    ya mtu mwingine bila mwalimu kupata nafasi ya kuona.

    Sasa: alama ya washa inaflag-iwika "special case", mwalimu
    anaona kwanza (juu ya meza), na hihifadhiwi mpaka azitibitisha.
    """

    # ── (1) AI mwenyewe akisema ana washa ───────────────────────────
    def test_ai_uncertain_flag_becomes_special_case(self):
        rows = _clean_rows([
            {'row': 1, 'name': 'Amina', 'score': 10.6, 'uncertain': True},
        ])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['is_special_case'])
        self.assertIn('uhakika', rows[0]['special_reason'])
        # Alama inabaki — mwalimu anaisahihisha, si mfumo.
        self.assertEqual(rows[0]['score'], Decimal('10.6'))

    def test_uncertain_as_string_is_honoured(self):
        # Gemini/OpenRouter wanaweza kurudi "true" kama maandishi.
        rows = _clean_rows([
            {'row': 1, 'name': 'Amina', 'score': 8, 'uncertain': 'true'},
        ])
        self.assertTrue(rows[0]['is_special_case'])

    def test_uncertain_false_is_not_special(self):
        rows = _clean_rows([
            {'row': 1, 'name': 'Amina', 'score': 8, 'uncertain': False},
        ])
        self.assertNotIn('is_special_case', rows[0])

    # ── (2) Herufi zinazodhibiwa na kukoseka ────────────────────────
    def test_letter_confusion_in_mark_is_flagged(self):
        # "1O.6" — O (herufi) badala ya 0. Alama iliyokosewa.
        rows = _clean_rows([{'row': 1, 'name': 'Zawadi', 'score': '1O.6'}])
        self.assertTrue(rows[0]['is_special_case'])
        self.assertIn('O', rows[0]['special_reason'])
        # Alama asilia inabaki ili mwalimu aipige mbali na alama yake.
        self.assertEqual(rows[0]['raw_mark'], '1O.6')

    def test_raw_mark_prefers_what_was_on_the_sheet(self):
        # AI alisoma "1O.6" kisha akaika kuwa 10.6 na kutuma
        # raw_score="1O.6". Mwalimu lazima aone "1O.6" ili apige
        # mbali na picha — "10.6" ni alama tayyo iliyosomewa na
        # haina thamani ya kulingana na karatasi.
        rows = _clean_rows([
            {'row': 1, 'name': 'Zawadi', 'score': 10.6,
             'uncertain': True, 'raw_score': '1O.6'},
        ])
        self.assertEqual(rows[0]['score'], Decimal('10.6'))
        self.assertEqual(rows[0]['raw_mark'], '1O.6')

    def test_s5_for_55_is_flagged(self):
        rows = _clean_rows([{'row': 1, 'name': 'Neema', 'score': 'S5'}])
        self.assertTrue(rows[0]['is_special_case'])
        self.assertIn('S', rows[0]['special_reason'])

    def test_raw_mark_shown_even_when_score_parsed(self):
        # Mufano halisi: alama inasomika kwa njia moja lakini mfumo
        # hakupata uhakika. Mwalimu lazima aone "1O.6" ili ajue
        # nini kilikuwa kwenye karatasi.
        rows = _clean_rows([
            {'row': 1, 'name': 'Peter', 'score': 10.6, 'raw_score': '1O.6'},
        ])
        self.assertTrue(rows[0]['is_special_case'])
        # raw_mark ni alama KWELI iliyokuwa kwenye karatasi ("1O.6"),
        # si alama AI iliyokosoa ("10.6") — mwalimu anahitaji kulingana
        # na picha.
        self.assertEqual(rows[0]['raw_mark'], '1O.6')
        self.assertEqual(rows[0]['score'], Decimal('10.6'))
        self.assertIn('1O.6', rows[0]['special_reason'])

    # ── (3) Alama safi hazipati alama ya sumaku ──────────────────
    def test_clean_marks_are_not_special(self):
        rows = _clean_rows([
            {'row': 1, 'name': 'A', 'score': 10.6},
            {'row': 2, 'name': 'B', 'score': 78},
            {'row': 3, 'name': 'C', 'score': 0},
            {'row': 4, 'name': 'D', 'score': 100},
            {'row': 5, 'name': 'E', 'score': 7.5},
        ])
        for r in rows:
            self.assertNotIn('is_special_case', r, f"{r['raw_name']} haipaswi kuwa special case")

    def test_absent_is_never_special(self):
        # X maana ya alikuwa absent — si alama ya mashaka.
        rows = _clean_rows([{'row': 1, 'name': 'Fatuma', 'score': 'X'}])
        self.assertTrue(rows[0]['is_absent'])
        self.assertNotIn('is_special_case', rows[0])

    def test_blank_is_not_special(self):
        rows = _clean_rows([{'row': 1, 'name': 'Hadija', 'score': 'BLANK'}])
        self.assertTrue(rows[0]['blank'])
        self.assertNotIn('is_special_case', rows[0])

    def test_unreadable_mark_is_not_double_flagged(self):
        # Alama inayosomika kabisa (grada ya herufi) inashikiliwa kama
        # 'unreadable' — hatuiweka alama yake. Hii inaonyesha mfumo
        # HAJAWEZA kusoma, tofauti na special case ambayo mfumo
        # unaweza kusoma lakini hana uhakika.
        rows = _clean_rows([{'row': 1, 'name': 'Zulekha', 'score': '???'}])
        self.assertTrue(rows[0].get('unreadable'))
        self.assertIsNone(rows[0]['score'])
        self.assertNotIn('is_special_case', rows[0])

    def test_zero_and_hundred_are_not_special(self):
        # Mwanafunzi aliyepata 0 au 100 kwa uakiki ni mwanafunzi wa
        # kawaida. Mf flag-iwake kama special case unamfanya mwalimu
        # aone kelele kwa kila darasa, na hapo ndipo alama za
        # kweli zinazohitaji ukaguzi zinapokosewa.
        rows = _clean_rows([
            {'row': 1, 'name': 'Zero', 'score': 0},
            {'row': 2, 'name': 'Full', 'score': 100},
        ])
        for r in rows:
            self.assertNotIn('is_special_case', r)

    def test_decimal_marks_survive_flagging(self):
        # Mwanzo wa bug: desimali zilikatwa. Alama ya special case
        # inapaswa kuwa DESIMALI kamili.
        rows = _clean_rows([
            {'row': 1, 'name': 'Asha', 'score': 9.75, 'uncertain': True},
        ])
        self.assertEqual(rows[0]['score'], Decimal('9.75'))
        self.assertTrue(rows[0]['is_special_case'])

    def test_special_case_does_not_shift_roster_positions(self):
        # Mstari wa special case bado ziko katika nafasi yake. Ikiwa
        # mungu hutoweka, wanafunzi wa baadaye wangesogeza nafasi.
        rows = _clean_rows([
            {'row': 1, 'name': 'A', 'score': 10.6, 'uncertain': True},
            {'row': 2, 'name': 'B', 'score': 78},
            {'row': 3, 'name': 'C', 'score': 65},
        ])
        self.assertEqual([r['raw_name'] for r in rows], ['A', 'B', 'C'])
        self.assertEqual([r['row'] for r in rows], [1, 2, 3])
