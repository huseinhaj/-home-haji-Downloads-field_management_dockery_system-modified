"""Majaribio ya paneli ya AI kwenye ukurasa wa Academic
"Pakia Scoresheets — Masomo Yote" (bulk_scoresheet_upload).

WAMEWEKWA KANDO ya results/tests.py kwa sababu ya mwingiliano:

Njia hii ya bulk inaendesha task nzima (process_bulk_upload_task) ndani
ya majaribio yenyewe — ikiwa ni DB writes, cache writes na mabadiliko ya
meta. Majaribio ya marks-entry (ScoreSheetPhotoExtractViewTests) yanatumia
Celery kwa njia ya `update_state` + `result_backend = django-db`, na
Django TestCase inafanya kila kitu ndani ya transaction moja: task ya
bulk inapoandika kwenye backend ile ile ya Celery, majaribio ya
marks-entry yanaishia kukiwa PROGRESS milele (jibu 'processing' cha
muda mrefu) badala ya 'done'. Majaribio hayo yalipita peke yake
(kwaniye hakuna task ya bulk iliyokuwa ikitandikisha nyuma yao), kwa
hiyo walikuwa flaky — sasa wako katika moduli yao ili iwe deterministic.

TestCase hapa inatumia transaction moja kwa kila majaribio, hivyo
haihitaji mpangilio wa ziada.
"""
import json

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from unittest.mock import MagicMock, patch

from .models import (
	Exam,
	ExamResult,
	FormStudent,
	School,
	Student,
	Subject,
	TeacherAccount,
)
from .scan_models import BulkUploadJob


class BulkUploadProgressPanelTests(TestCase):
	"""Paneli ya AI kwenye bulk upload inahitaji metadata halisi
	(stage/kurasa/mistari) ili frontend isielewe kinachoendelea."""

	databases = {'default', 'results'}

	def setUp(self):
		self.school = School.objects.create(name='Mfano Secondary', region='Dodoma', district='Dodoma')
		self.exam = Exam.objects.create(name='Midterm 1', year=2026, form=2, school=self.school)
		self.subject = Subject.objects.create(name='Mathematics')
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
		self.teacher = TeacherAccount.objects.create(
			email='teacher@example.com', full_name='Teacher One',
			role=TeacherAccount.ROLE_ACADEMIC, school=self.school,
		)
		self.teacher.subjects.set([self.subject])
		# Bulk upload inaendeshwa juu ya mtihani ambaye kuna ExamResult
		# (task inarudi 'Mtihani haupatikana.' kabla ya kuingia hatua ya
		# 'matching' kama hakuna).
		ExamResult.objects.create(
			exam=self.exam, student=self.amina, subject=self.subject, score=70,
		)
		self.client = Client()
		self.client.force_login(self.teacher, backend='results.backends.ResultsAuthBackend')


	def test_bulk_upload_status_reports_ocr_stage_to_panel(self):
		"""Paneli ya AI kwenye ukurasa wa academic (Pakia Scoresheets —
		Masomo Yote) inahitaji metadata: stage/kurasa/mistari. Bila
		hii paneli ingebaki 'Inasoma...' tu — hasa kwa sababu hii njia
		ya thread haikuandika meta kama Celery."""
		job = BulkUploadJob.objects.create(
			exam=self.exam, subject=self.subject,
			status=BulkUploadJob.Status.PROCESSING,
		)
		cache.set(f'bulk_upload_ocr:{job.pk}', {
			'status': 'processing', 'stage': 'reading',
			'pages_done': 2, 'pages_total': 6, 'rows': 0,
		}, timeout=60)
		data = self.client.get(reverse('bulk_upload_status', args=[job.pk])).json()
		self.assertEqual(data['status'], 'processing')
		self.assertEqual(data['stage'], 'reading')
		self.assertEqual(data['pages_done'], 2)
		self.assertEqual(data['pages_total'], 6)

		# Meta isiyo halali (stage ya kubuni, namba za tekstu) haipaswi
		# kuingia kwenye JSON — frontend haina hatua hiyo ya kuonyesha.
		cache.set(f'bulk_upload_ocr:{job.pk}', {
			'status': 'processing', 'stage': 'made-up', 'pages_done': 'mbili',
		}, timeout=60)
		data = self.client.get(reverse('bulk_upload_status', args=[job.pk])).json()
		self.assertNotIn('stage', data)
		self.assertNotIn('pages_done', data)

	def test_bulk_upload_task_writes_progress_under_its_own_cache_key(self):
		"""Task ya bulk upload inapaswa kuandika meta chini ya
		'bulk_upload_ocr:<job_id>' — si chini ya kichicho cha scoresheet
		(marks entry) wala kichicho cha orodha, ambavyo vimeshakiliwa na
		mzito mwingine kwenye cache."""
		from .tasks import process_bulk_upload_task

		def fake_extract(document, on_progress=None):
			if on_progress:
				on_progress('reading', 0, 2)
				on_progress('reading', 2, 2)
			return [
				{'raw_name': f'Mwanafunzi {i}', 'score': str(50 + i), 'is_absent': False}
				for i in range(5)
			]

		roster = [self.zawadi.id, self.amina.id]
		with patch('results.tasks.extract_scores_from_document', fake_extract), \
			 patch('results.tasks.default_storage.open', MagicMock()), \
			 patch('results.tasks.default_storage.delete', MagicMock()):
			process_bulk_upload_task.run(
				'bulk_upload/x.pdf', self.exam.id, self.subject.id, roster,
				progress_key='77',
			)

		entry = cache.get('bulk_upload_ocr:77')
		self.assertIsNotNone(entry, 'meta haikuandikwa kwenye kichicho cha bulk upload')
		self.assertEqual(entry['stage'], 'matching')
		self.assertEqual(entry['rows'], 5, 'mistari 5 iliyotoka kwenye picha lazima ielezwe')

		# Kichicho cha marks entry (scoresheet_ocr:<id>) kwa ID ile ile
		# 77 HAPASWI kugongwa na bulk upload — hiyo ndiyo regression
		# inayotokea kama namespace ikisahihishwa.
		self.assertIsNone(
			cache.get('scoresheet_ocr:77'),
			'bulk upload imeandika kwenye kichicho cha marks entry!',
		)

	def test_bulk_upload_accepts_a_fresh_exam_with_no_marks_yet(self):
		"""Mtihani MPYA — ambapo bado hakuna alama zozote — lazima
		ukubaliwe kupakia scoresheet.

		Hitilafu iliyokuwa ikijitokea: task ilitafuta mtihani kwenye
		`ExamResult` (mfano wa kwanza), hivyo mtihani mpya wenye zero
		alama ungependelea kurudi 'Mtihani haupatikana.' kama haukuo.
		Kilikuwa kinamutisha mwalimu kwamba amekosewa, wakati tatizo
		halikuwa kwake.
		"""
		from .tasks import process_bulk_upload_task

		fresh = Exam.objects.create(
			name='Mtihani Mpya', year=2026, form=2, school=self.school,
		)
		self.assertFalse(
			ExamResult.objects.filter(exam=fresh).exists(),
			'majaribio yanahitaji mtihani bila alama',
		)

		def fake_extract(document, on_progress=None):
			if on_progress:
				on_progress('reading', 1, 1)
			return [
				{'raw_name': 'Zawadi Zuberi', 'score': '10.6', 'is_absent': False, 'row': 1,
				 'blank': False, 'unreadable': False},
				{'raw_name': 'Amina Ally', 'score': '85.5', 'is_absent': False, 'row': 2,
				 'blank': False, 'unreadable': False},
			]

		roster = [self.zawadi.id, self.amina.id]
		with patch('results.tasks.extract_scores_from_document', fake_extract), \
				patch('results.tasks.default_storage.open', MagicMock()), \
				patch('results.tasks.default_storage.delete', MagicMock()):
			out = process_bulk_upload_task.run(
				'bulk_upload/mpya.pdf', fresh.id, self.subject.id, roster,
				preview_only=True, progress_key='91',
			)

		self.assertNotIn('error', out, f"mtihani mpya umekataliwa: {out.get('error')}")
		self.assertEqual(len(out['matched']), 2, out.get('matched'))
		# Desimali lazima zibaki kama desimali hadi kwenye preview —
		# hazipaswi kukatwa wala kuandikwa kama kamba tu.
		scores = sorted(str(m['score']) for m in out['matched'])
		self.assertEqual(scores, ['10.6', '85.5'], scores)

	def test_bulk_upload_never_creates_a_student_for_an_unknown_name(self):
		"""Jina lisilosomewa vizuri halitakiwi kuunda mwanafunzi
		mwingine kwa msimu — mstari unapaswa kuondwa na mwalimu
		akilazimishe mwenyewe.

		Tabia ya awali: jina lililosomewa vibaya lilikuwa likitengeneza
		mwanafunzi mpya kwa default storage, ambayo inaweza kumpa
		mwanafunzi wa mwisho alama ya mtu mwingine.
		"""
		from .tasks import process_bulk_upload_task

		before = Student.objects.count()

		def fake_extract(document, on_progress=None):
			return [
				{'raw_name': 'Zawadi Zuberi', 'score': '70', 'is_absent': False, 'row': 1,
				 'blank': False, 'unreadable': False},
				{'raw_name': 'Xxyzzy Nonexistent', 'score': '99', 'is_absent': False, 'row': 2,
				 'blank': False, 'unreadable': False},
			]

		roster = [self.zawadi.id, self.amina.id]
		with patch('results.tasks.extract_scores_from_document', fake_extract), \
				patch('results.tasks.default_storage.open', MagicMock()), \
				patch('results.tasks.default_storage.delete', MagicMock()):
			out = process_bulk_upload_task.run(
				'bulk_upload/umbeki.pdf', self.exam.id, self.subject.id, roster,
				preview_only=True, progress_key='92',
			)

		self.assertEqual(
			Student.objects.count(), before,
			'AI imeunda mwanafunzi mpya kwa jina ambalo halikuwa kwenye orodha!',
		)
		self.assertEqual(len(out['matched']), 1, 'mstari wa jina la kigeni haipaswi kulingishwa')
		self.assertTrue(out['unmatched'], 'mstari wa jina la kigeni unapaswa kuondwa kwa mwalimu')
		# Amina (iliyokuwa nafasi ya 2 kwenye orodha) HAJAPATA alama
		# ya mtu asiyejulikana.
		self.assertFalse(
			ExamResult.objects.filter(exam=self.exam, student=self.amina, subject=self.subject).exclude(pk=None).exists()
			and ExamResult.objects.filter(exam=self.exam, student=self.amina, subject=self.subject).count() > 1,
			'mtihani ulikuwa na alama moja tu kabla — hakuna alama nyingine zilizoongezwa',
		)
