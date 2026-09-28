"""Celery tasks for the results app.

Currently just the scoresheet-photo OCR pipeline: it calls an external
vision API (OpenRouter, falling back to Gemini) that can take anywhere
from a few seconds to 120s+ per page. Running that inline in the
request/response cycle risked hanging or 502-ing on a multi-page upload
(gunicorn/proxy worker timeouts are usually well under that). Doing it
as a background task means the HTTP request returns immediately with a
task_id, and the frontend polls scoresheet_extract_status for the result.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.core.cache import cache
from django.core.files.storage import default_storage

from .models import Exam, ExamResult, Student, Subject, SubjectSubmission
from .services.scoresheet_ocr_service import ScoreSheetOCRError, extract_scores_from_document

logger = logging.getLogger(__name__)

# Mirafu ya cache inayotumika kwa ripoti ya maendeleo. Inapaswa kuwa >= time_limit
# ya task chini (360s) ili hali ya "processing" isizikoseke kabla ya kukamilika.
_PROGRESS_CACHE_TIMEOUT = 600

# Hatua za backend (frontend inaongeza 'uploading' na 'done' kwenye zake).
OCR_STAGES = ('reading', 'matching')


def report_ocr_stage(progress_key, stage, done=None, total=None, namespace='scoresheet_ocr', **extra):
    """Tuma hatua ya OCR inayoendelea kwa frontend inayopoll.

    Njia zote mbili zinahitaji kihicho tofauti na ZINAKOSHAULIANA, si
    mbadala — kila njia inatumia kihicho chake tu:
      * Celery (progress_key is None) — self.update_state(meta=...) hifadhi
        meta kwenye backend na scoresheet_extract_status inaisoma kama
        AsyncResult.info.
      * Thread ya ndini (progress_key set, hakuna worker) — task haijafanyiwa
        dispatch, hivyo update_state haina backend halisi ya kuandikia;
        tunahifadhi kwenye cache kwa progress_key ile ile inayotumika na
        runner ya ndini.

    progress_key ni String tu (si callable) ili Celery iweze kuizisafisha
    bila hitilafu unaposafisha ujumbe kwa broker.

    namespace hutofautisha kihicho cha cache kwa kila aina ya scan. Bila
    argument hii, task ya orodha ingeandika chini ya 'scoresheet_ocr:...' na
    roster_scan_status isingeyipata (kila mtu akisoma kichicho hasa
    kilichotengenezwa na mtu mwingine ni mjeuri wa kugombana)."""
    payload = {'stage': stage}
    if done is not None:
        payload['pages_done'] = done
    if total is not None:
        payload['pages_total'] = total
    payload.update(extra)
    if progress_key:
        key = f'{namespace}:{progress_key}'
        entry = cache.get(key) or {}
        entry.update(payload)
        entry['status'] = 'processing'
        cache.set(key, entry, timeout=_PROGRESS_CACHE_TIMEOUT)
    return payload


def make_stage_reporter(task, progress_key, namespace='scoresheet_ocr'):
    """Jenga on_progress(stage, done, total, **extra) inayotuma hatua ya
    OCR kwa frontend.

    Mbili njia zinahitaji kihicho tofauti na ZINAKOSHAULIANA, si mbadala —
    kila njia inatumia kihicho chake tu:
      * Celery (progress_key is None) — task.update_state(meta=...) hifadhi
        meta kwenye backend na status endpoint inaisoma kama
        AsyncResult.info.
      * Thread ya ndini (progress_key set, hakuna worker) — task haijafanyiwa
        dispatch, hivyo update_state haina backend halisi ya kuandikia;
        tunahifadhi kwenye cache kwa progress_key ile ile inayotumika na
        runner ya ndini.

    namespace inapaswa kulingana na kichicho kinachoisoma status endpoint
    ya kila scan (scoresheet_ocr:... au roster_scan_ocr:...)."""

    def _stage(stage, done=None, total=None, **extra):
        meta = report_ocr_stage(progress_key, stage, done=done, total=total,
                                namespace=namespace, **extra)
        if progress_key:
            return
        try:
            task.update_state(state='PROGRESS', meta=meta)
        except Exception as exc:
            # A stage ping is a nicety, never a reason to fail the read.
            logger.debug("OCR stage report skipped: %s", exc)

    return _stage


def _row_number_warnings(extracted_rows):
    """Tahadhari za mistari ya karatasi iliyosomwa vibaya au kurukwa.

    AI inapokata mkondo (truncation), picha inakoleka, au mkono unaoficha
    namba ya mstari, mistari michache ya mwisho/mkatikati haipatikani —
    wanafunzi wake wanaishia "missing" na mwalimu haelewi kwanini. Hizi
    warnings zinamtambulisha hitilafu HIYO YA SCAN (si makosa yake) na
    kumwambia ni mistari gani ya "Na." ilipotea."""
    nums = [r.get('row') for r in extracted_rows
            if isinstance(r.get('row'), int) and r.get('row', 0) > 0]
    warnings = []
    if not nums:
        return warnings
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    if dupes:
        warnings.append(
            "Mistari hii imesomwa zaidi ya mara moja: "
            + ', '.join(map(str, dupes))
            + " — kagua karatasi, huenda mistari michanganyikiwa."
        )
    missing_nums = sorted(set(range(1, max(nums) + 1)) - set(nums))
    if missing_nums:
        preview = ', '.join(map(str, missing_nums[:15]))
        more = f' (+{len(missing_nums) - 15} zaidi)' if len(missing_nums) > 15 else ''
        warnings.append(
            "Mistari hii ya 'Na.' haikusomwa kabisa kwenye picha: "
            + preview + more
            + " — wanafunzi wake watakuwa hawajazwi; kagua karatasi au piga picha pya."
        )
    return warnings


@shared_task(bind=True, time_limit=360, soft_time_limit=340)
def process_scoresheet_photo_task(self, storage_path, roster_ids, progress_key=None):
    """storage_path: where scoresheet_photo_extract saved the upload
    (default_storage-relative) — this task owns deleting it once done.
    roster_ids: student PKs from the roster the teacher already had
    loaded client-side, used to fuzzy-match extracted names against.
    progress_key: optional task_id for the no-worker fallback path, used to
    publish which stage the read is on (see report_ocr_stage). None on the
    Celery path, which reports through self.update_state instead.

    Returns a dict — either {'error': ...} (OCR couldn't read the
    document) or {'matched': [...], 'unmatched': [...], 'missing': [...]}.
    'missing' lists roster students the OCR gave us NO signal for at all
    (not a score, not an X, not even an explicit blank row) — these are
    almost always a mark the AI failed to read, not a student who simply
    doesn't study the subject, and need a manual check against the photo."""
    from .services.speech_submission_service import match_rows_to_roster_by_position
    from .views import _parse_roster_line, _save_student

    # Hatua kwa frontend: 'reading' (kwa kurasa) kisha 'matching'.
    _stage = make_stage_reporter(self, progress_key)

    try:
        with default_storage.open(storage_path) as document:
            extracted_rows = extract_scores_from_document(
                document, on_progress=_stage,
            )
    except ScoreSheetOCRError as exc:
        return {'error': str(exc)}
    finally:
        try:
            default_storage.delete(storage_path)
        except Exception:
            logger.warning("process_scoresheet_photo_task: could not delete temp file %s", storage_path, exc_info=True)

    _stage('matching', rows=len(extracted_rows))

    # Preserve the order roster_ids arrived in — it mirrors the order the
    # frontend's marks table (and therefore download_scoresheet_names_pdf's
    # "Na." column) was in, which position-based matching depends on.
    # Student.objects.filter(id__in=...) does NOT preserve list order.
    students_by_id = {s.id: s for s in Student.objects.filter(id__in=roster_ids)}
    roster_students = [students_by_id[rid] for rid in roster_ids if rid in students_by_id]

    # ── Namba ya "Na." kwanza, jina kama kuhakiki ───────────────────
    # Karatasi ya scoresheet inachapishwa na mfumo mwenyewe
    # (download_scoresheet_names_pdf) kwa mpangilio rahisi, na
    # namba ya "Na." kwenye kila ukurasa ndiyo funguo inayotambulisha
    # mwanafunzi. AI inapaswa kusoma TU alama — si kujenga upya
    # utambulisho wa mwanafunzi kwa kusoma jina.
    #
    # Mwanzo ilikuwa jina kwanza (≥0.80), na namba ya mstari ilikuwa
    # ya kumuja tu. Ilishindwa kila jili AI ilipokosea jina MOJA:
    # mchapa, mwandiko uliofunikwa, au jina la mwanafunzi mwingine
    # lililofanana karibu — mwanafunzi huyo alipoteza alama yake,
    # au (mbaya zaidi) alichukua alama ya mwanafunzi mwingine
    # bila kuonekana. Sasa namba ya kuchapishwa inaongoza, na jina
    # limekuwa kuhakiki: pale rosti ya skrini imebadilika baada ya
    # kuchapisha, jina la kweli (≥0.80, kwa wazi bora) linaondoa
    # mstari huo kutoka nafasi yake.
    assignments, _unresolved = match_rows_to_roster_by_position(
        extracted_rows, roster_students,
    )

    blank_ids = {
        assignments[i][0].id for i, r in enumerate(extracted_rows)
        if r.get('blank') and i in assignments
    }

    matched = []
    unmatched = []
    for row_index, row in enumerate(extracted_rows):
        if row.get('blank'):
            continue
        assignment = assignments.get(row_index)
        if assignment:
            student, confidence = assignment
            matched.append({
                'id': student.id,
                'score': row['score'],
                'is_absent': row.get('is_absent', False),
                'raw_name': row['raw_name'],
                'confidence': round(confidence, 4),
                'is_new': False,
            })
            continue

        parsed = _parse_roster_line(row['raw_name'])
        if not parsed:
            unmatched.append({'raw_name': row['raw_name'], 'score': row['score'], 'is_absent': row.get('is_absent', False)})
            continue
        first, middle, last, gender = parsed
        saved = _save_student(first, middle, last, gender)
        matched.append({
            'id': saved['id'],
            'name': saved['name'],
            'score': row['score'],
            'is_absent': row.get('is_absent', False),
            'raw_name': row['raw_name'],
            'confidence': 0.0,
            'is_new': True,
        })

    # Anyone left over is either confirmed blank-on-the-sheet (fine, no
    # action needed) or never showed up in the OCR output at all (needs a
    # manual check — most likely a mark the AI missed).
    matched_ids = {m['id'] for m in matched if not m.get('is_new')}
    missing = [
        {'id': s.id, 'name': ' '.join(p for p in [s.first_name, s.middle_name or '', s.last_name] if p)}
        for s in roster_students
        if s.id not in matched_ids and s.id not in blank_ids
    ]

    return {
        'matched': matched, 'unmatched': unmatched, 'missing': missing,
        'warnings': _row_number_warnings(extracted_rows),
    }


@shared_task(bind=True, time_limit=360, soft_time_limit=340)
def process_roster_scan_task(self, storage_path, progress_key=None):
    """Academic roster scan: piga picha / pakia orodha ya wanafunzi, AI
    isome majina na jinsia, kisha Academic ahakiki (preview) kabla ya
    kuhifadhi kwenye FormStudent.

    storage_path: default_storage-relative path ya picha/PDF iliyopakiwa;
    task hii ndiyo inayoyamiliki kuifuta baada ya kumalika.
    progress_key: task_id ya njia ya thread (hakuna Celery worker), kwa
    kuripoti hatua — angalia report_ocr_stage. Celery path haina
    progress_key na inatumia update_state.

    Hapa ndipo academic scan ilikuwa IKIZUNGUAZWA ndani ya request
    (scan_roster) — kusoma kurasa 3-5 kwa AI kwa mfano ni dakika 60-300,
    ambayo proxy hufa kabla ya AI kukamilisha, na mtumiaji alipata
    "Failed to fetch" bila maelezo. Sasa hii ni kazi ya nyuma yenye
    polling, kama scoresheet OCR.

    Returns {'students': [...]} au {'error': '...'}. Hakuna chochote
    kinachohifadhiwa hapa — uhakiki na hifadhi ni kazi ya Academic."""
    from .services.roster_scan_service import extract_students_from_document

    # Kichicho 'roster_scan_ocr:...' kinalingana na roster_scan_status —
    # bila argument hii progress ya orodha ingeandikwa chini ya kichicho
    # cha scoresheet na paneli isingeyiweza kuionyesha.
    _stage = make_stage_reporter(self, progress_key, namespace='roster_scan_ocr')
    try:
        with default_storage.open(storage_path) as document:
            students = extract_students_from_document(document, on_progress=_stage)
    except ScoreSheetOCRError as exc:
        # RosterScanError inatoka kwenye ScoreSheetOCRError, hivyo kiumbe
        # kimoja kinatosha kwa makosa yote ya kusoma AI.
        return {'error': str(exc)}
    finally:
        try:
            default_storage.delete(storage_path)
        except Exception:
            logger.warning("process_roster_scan_task: could not delete temp file %s", storage_path, exc_info=True)

    _stage('matching', rows=len(students))
    return {'students': students}


def _ordered_roster(roster_ids):
    """Roster katika mpangilio unaotarajiwa wa kuchapisha.

    Namba ya "Na." kwenye scoresheet ni nafasi katika orodha hii, hivyo
    mpangilio lazima uwe wa tulivu — sio ulio arbitrary tuvao ya
    database. Tunapanga kwa jina la mwisho kwanza (nyumbani scoresheets
    huchapishwa kwa majibu), kisha jina la kwanza, kisha ID ili kama
    majina yanafanana mpangilio uwe na uhakika.
    """
    return list(
        Student.objects.filter(id__in=roster_ids).order_by('last_name', 'first_name', 'id')
    )


@shared_task(bind=True, time_limit=360, soft_time_limit=340)
def process_bulk_upload_task(self, storage_path, exam_id, subject_id, roster_ids, preview_only=False, progress_key=None):
    """Background task: OCR a scoresheet, match students, save results,
    and auto-approve the SubjectSubmission.  Used by the academic
    officer's bulk upload flow (one file per subject at a time).

    When *preview_only* is True the task returns the matched/unmatched
    rows but does NOT write them to the database — the frontend shows
    them in a review table so the teacher can correct scores before
    the final save.

    progress_key: kitanzi cha kazi (kawaida BulkUploadJob.pk) inachotumika
    kuandika hatua za maendeleo kwenye cache kwa paneli ya AI. Nzuri kwa
    njia ya thread (academic inaendesha task hii kwa thread, si Celery),
    kwa hivyo hapa tunatumia report_ocr_stage moja kwa moja badala ya
    task.update_state ambayo hafanyi kazi bila broker."""
    from django.utils import timezone
    from .services.speech_submission_service import match_rows_to_roster_by_position
    from .services.upload_processing_service import recompute_processed_results_for_exam

    _stage = make_stage_reporter(self, progress_key, namespace='bulk_upload_ocr')

    try:
        with default_storage.open(storage_path) as document:
            extracted_rows = extract_scores_from_document(document, on_progress=_stage)
    except ScoreSheetOCRError as exc:
        return {'error': str(exc)}
    finally:
        try:
            default_storage.delete(storage_path)
        except Exception:
            logger.warning("bulk_upload: could not delete temp file %s", storage_path, exc_info=True)

    # Match extracted names to roster students
    #
    # Mpangilio wa kwanza: kama scoresheet imeandikwa na mfumu huu
    # ("Na." = namba ya mwanafunzi kwa mpangilio wa kuchapisha), namba
    # hiyo ni kielelezo kinachotuaminia kuliko jina. Lakini kwenye
    # bulk upload tunazingatia majina pia — ili mtu asipate alama ya
    # mwanafunzi mwingine kwa sababu AI imesoma jina vibaya.
    roster_students = _ordered_roster(roster_ids)
    # Mtihani hutafutwa kwenye Exam moja kwa moja — SI kwenye ExamResult.
    # Kumbuka: kwanja hapa kiliangalie ExamResult ya kwanza, mtihani
    # mpya (ambapo bado hakuna alama zozote) ungependelea kuonekana
    # kuwa "haupatikana" kabisa hata kama upo kwenye database.
    exam_obj = Exam.objects.filter(id=exam_id).first()
    if not exam_obj:
        return {'error': 'Mtihani haupatikana.'}
    subject = Subject.objects.filter(id=subject_id).first()
    if not subject:
        return {'error': 'Somo halipatikani.'}

    # Tahadhari za mistari iliyokosewa kabisa (namba ya "Na." iliyosoma
    # mara kumi, au iliyokuwa haipo). Bila hizi mtu hana njia ya
    # kujua namba gani haikusomwa.
    row_warnings = _row_number_warnings(extracted_rows)

    _stage('matching', rows=len(extracted_rows))
    assignments, _unresolved = match_rows_to_roster_by_position(
        extracted_rows, roster_students,
    )

    matched = []
    unmatched = []
    for row_index, row in enumerate(extracted_rows):
        is_absent = row.get('is_absent', False)
        # Mstari ambao AI haukuweza kusoma alama yake (grada ya herufi,
        # au namba isiyo maana). Mzigo huu unaonyeshwa kwa mwalimu ili
        # asemewe mwenyewe — hatupangi alama ya mtu mwingine.
        if row.get('unreadable'):
            logger.warning("[BulkUpload] AI could not read the mark for '%s' (row %s, raw=%r) — left blank for the officer",
                row['raw_name'], row.get('row'), row.get('raw_mark'))
            unmatched.append({
                'raw_name': row['raw_name'], 'score': None, 'is_absent': False,
                'unreadable': True, 'raw_mark': row.get('raw_mark', ''),
            })
            continue
        # Mwanafunzi aliacha seli tupu — hakuna alama ya kuhifadhi, lakini
        # mstari unabaki ili vipimo vya "Na." vizingatie.
        if row.get('blank'):
            continue
        assignment = assignments.get(row_index)
        if assignment:
            student, confidence = assignment
            student_name = ' '.join(p for p in [student.first_name, student.middle_name or '', student.last_name] if p)
            logger.info("[BulkUpload] Matched '%s' -> '%s' (confidence=%.4f) score=%s absent=%s",
                row['raw_name'], student_name, confidence, row['score'], is_absent)
            matched.append({
                'student_id': student.id,
                'student_name': student_name,
                'score': row['score'],
                'is_absent': is_absent,
                'raw_name': row['raw_name'],
                'confidence': round(confidence, 4),
            })
            continue
        # Hatukuweza kusikia mwanafunzi wa mstari huu kwa uhakika. Tuna
        # mshauri mtu asichaguliwe: mwalimu atashughulika. Hatumii
        # jina lililosomewa kuunda mwanafunzi mpya hapa — kwenye
        # hali ya kuwaga, mfumo huingiza wanafunzi wasio waonekana
        # kama "wahisi" wana alama za watu wengine.
        logger.warning("[BulkUpload] No confident match for '%s' (row %s, score=%s) — left for the officer",
            row['raw_name'], row.get('row'), row['score'])
        unmatched.append({'raw_name': row['raw_name'], 'score': row['score'], 'is_absent': is_absent})
        continue

    # ── Preview mode: return data without saving ──────────────────────
    if preview_only:
        # Build roster list for the frontend dropdown
        roster_list = [{'id': s.id, 'name': ' '.join(p for p in [s.first_name, s.middle_name or '', s.last_name] if p)} for s in roster_students]
        # Roster students the OCR gave no row for at all — could be a
        # student who doesn't take this subject, or a mark it missed
        # entirely; there's no reliable way to tell the two apart here
        # (unlike the teacher's own photo upload, this file has no known
        # print order to anchor blank rows to), so surface them for the
        # academic officer to confirm rather than silently dropping them.
        matched_ids = {m['student_id'] for m in matched}
        missing = [s for s in roster_list if s['id'] not in matched_ids]
        return {
            'preview': True,
            'subject_id': subject.id,
            'subject_name': subject.name,
            'matched': matched,
            'unmatched': unmatched,
            'roster': roster_list,
            'missing': missing,
            # Tahadhari: mistari iliyosomwa mara kumi, au iliyokuwa
            # haipo. Bila hizi mwalimu hana njia ya kujua namba gani
            # haikusomwa na alama zimepelekwa wapi.
            'warnings': row_warnings,
        }

    # ── Save mode: write to DB ───────────────────────────────────────
    exam_results = []
    for m in matched:
        exam_results.append(ExamResult(
            exam=exam_obj, student_id=m['student_id'], subject=subject,
            score=m['score'] if not m.get('is_absent') else None,
            is_absent=m.get('is_absent', False),
        ))

    if exam_results:
        ExamResult.objects.bulk_create(
            exam_results,
            update_conflicts=True,
            unique_fields=['exam', 'student', 'subject'],
            update_fields=['score', 'is_absent'],
        )

    # Mark SubjectSubmission as SUBMITTED + APPROVED (academic uploaded it)
    SubjectSubmission.objects.update_or_create(
        exam=exam_obj, subject=subject,
        defaults={
            'status': SubjectSubmission.STATUS_APPROVED,
            'method': 'UPLOAD',
            'submitted_by': 'Academic Officer (Bulk Upload)',
            'submitted_at': timezone.now(),
            'approved_by': 'Academic Officer (Bulk Upload)',
            'approved_at': timezone.now(),
            'student_count': len(matched),
        },
    )

    # Recompute processed results
    recompute_processed_results_for_exam(exam_obj)

    return {
        'matched_count': len(matched),
        'unmatched_count': len(unmatched),
        'unmatched': unmatched,
    }
