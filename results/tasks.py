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

from .models import Student
from .services.scoresheet_ocr_service import ScoreSheetOCRError, extract_scores_from_document

logger = logging.getLogger(__name__)


@shared_task(bind=True, time_limit=280, soft_time_limit=260)
def process_scoresheet_photo_task(self, storage_path, roster_ids):
    """storage_path: where scoresheet_photo_extract saved the upload
    (default_storage-relative) — this task owns deleting it once done.
    roster_ids: student PKs from the roster the teacher already had
    loaded client-side, used to fuzzy-match extracted names against.

    Returns a dict — either {'error': ...} (OCR couldn't read the
    document) or {'matched': [...], 'unmatched': [...]} in exactly the
    shape the view used to return synchronously."""
    from .services.speech_submission_service import fuzzy_match_student_name
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

    # Same matching logic scoresheet_photo_extract used to run inline —
    # see marks_entry.py's docstring on _save_student for why an unmatched
    # name becomes a brand-new student rather than being dropped.
    matched = []
    unmatched = []
    for row in extracted_rows:
        student, confidence, _candidates = fuzzy_match_student_name(
            row['raw_name'], roster_students, threshold=0.80,
        )
        if student:
            matched.append({
                'id': student.id,
                'score': row['score'],
                'raw_name': row['raw_name'],
                'confidence': round(confidence, 4),
                'is_new': False,
            })
            continue

        parsed = _parse_roster_line(row['raw_name'])
        if not parsed:
            unmatched.append({'raw_name': row['raw_name'], 'score': row['score']})
            continue
        first, middle, last, gender = parsed
        saved = _save_student(first, middle, last, gender)
        matched.append({
            'id': saved['id'],
            'name': saved['name'],
            'score': row['score'],
            'raw_name': row['raw_name'],
            'confidence': 0.0,
            'is_new': True,
        })

    return {'matched': matched, 'unmatched': unmatched}
