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
from django.core.files.storage import default_storage

from .models import ExamResult, Student, Subject, SubjectSubmission
from .services.scoresheet_ocr_service import ScoreSheetOCRError, extract_scores_from_document

logger = logging.getLogger(__name__)


@shared_task(bind=True, time_limit=360, soft_time_limit=340)
def process_scoresheet_photo_task(self, storage_path, roster_ids):
    """storage_path: where scoresheet_photo_extract saved the upload
    (default_storage-relative) — this task owns deleting it once done.
    roster_ids: student PKs from the roster the teacher already had
    loaded client-side, used to fuzzy-match extracted names against.

    Returns a dict — either {'error': ...} (OCR couldn't read the
    document) or {'matched': [...], 'unmatched': [...]} in exactly the
    shape the view used to return synchronously."""
    from .services.speech_submission_service import match_rows_to_roster_exclusive
    from .views import _parse_roster_line, _save_student

    try:
        with default_storage.open(storage_path) as document:
            extracted_rows = extract_scores_from_document(document)
    except ScoreSheetOCRError as exc:
        return {'error': str(exc)}
    finally:
        try:
            default_storage.delete(storage_path)
        except Exception:
            logger.warning("process_scoresheet_photo_task: could not delete temp file %s", storage_path, exc_info=True)

    roster_students = list(Student.objects.filter(id__in=roster_ids))

    # Exclusive matching: each roster student can only be claimed by ONE
    # row, so two similarly-named students (same surname, or a name OCR
    # misread as another student's) can't both collapse onto the same
    # person — see match_rows_to_roster_exclusive's docstring.
    assignments, _unmatched_indices = match_rows_to_roster_exclusive(
        extracted_rows, roster_students, threshold=0.80,
    )

    matched = []
    unmatched = []
    for row_index, row in enumerate(extracted_rows):
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

    return {'matched': matched, 'unmatched': unmatched}


@shared_task(bind=True, time_limit=360, soft_time_limit=340)
def process_bulk_upload_task(self, storage_path, exam_id, subject_id, roster_ids, preview_only=False):
    """Background task: OCR a scoresheet, match students, save results,
    and auto-approve the SubjectSubmission.  Used by the academic
    officer's bulk upload flow (one file per subject at a time).

    When *preview_only* is True the task returns the matched/unmatched
    rows but does NOT write them to the database — the frontend shows
    them in a review table so the teacher can correct scores before
    the final save."""
    from django.utils import timezone
    from .services.speech_submission_service import match_rows_to_roster_exclusive
    from .services.upload_processing_service import recompute_processed_results_for_exam
    from .views import _parse_roster_line, _save_student

    try:
        with default_storage.open(storage_path) as document:
            extracted_rows = extract_scores_from_document(document)
    except ScoreSheetOCRError as exc:
        return {'error': str(exc)}
    finally:
        try:
            default_storage.delete(storage_path)
        except Exception:
            logger.warning("bulk_upload: could not delete temp file %s", storage_path, exc_info=True)

    # Match extracted names to roster students
    roster_students = list(Student.objects.filter(id__in=roster_ids))
    exam = ExamResult.objects.filter(exam_id=exam_id).select_related('exam').first()
    if not exam:
        return {'error': 'Mtihani haupatikana.'}
    exam_obj = exam.exam
    subject = Subject.objects.filter(id=subject_id).first()
    if not subject:
        return {'error': 'Somo halipatikani.'}

    # Exclusive matching: each roster student can only be claimed by ONE
    # row, so two similarly-named students (same surname, or a name OCR
    # misread as another student's) can't both collapse onto the same
    # person — see match_rows_to_roster_exclusive's docstring.
    assignments, _unmatched_indices = match_rows_to_roster_exclusive(
        extracted_rows, roster_students, threshold=0.80,
    )

    matched = []
    unmatched = []
    for row_index, row in enumerate(extracted_rows):
        is_absent = row.get('is_absent', False)
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
        parsed = _parse_roster_line(row['raw_name'])
        if not parsed:
            logger.warning("[BulkUpload] UNMATCHED '%s' score=%s absent=%s",
                row['raw_name'], row['score'], is_absent)
            unmatched.append({'raw_name': row['raw_name'], 'score': row['score'], 'is_absent': is_absent})
            continue
        first, middle, last, gender = parsed
        saved = _save_student(first, middle, last, gender)
        matched.append({
            'student_id': saved['id'],
            'student_name': saved['name'],
            'score': row['score'],
            'is_absent': is_absent,
            'raw_name': row['raw_name'],
            'confidence': 0.0,
        })

    # ── Preview mode: return data without saving ──────────────────────
    if preview_only:
        # Build roster list for the frontend dropdown
        roster_list = [{'id': s.id, 'name': ' '.join(p for p in [s.first_name, s.middle_name or '', s.last_name] if p)} for s in roster_students]
        return {
            'preview': True,
            'subject_id': subject.id,
            'subject_name': subject.name,
            'matched': matched,
            'unmatched': unmatched,
            'roster': roster_list,
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
