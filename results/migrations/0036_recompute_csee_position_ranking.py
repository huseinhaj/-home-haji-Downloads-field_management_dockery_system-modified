"""Recompute ProcessedResult for every existing CSEE (Form 1-4) exam.

Why: recompute_processed_results_for_exam() used to rank students by raw
points alone, so a student with fewer subjects (all A's) could rank ABOVE
a student with all 7 subjects (also all A's) purely for sitting fewer
exams -- e.g. 4 points beats 7 points -- even though NECTA's own
minimum-subject rule already caps that 4-subject student at Division IV.
The fix sorts by division first. Every CSEE exam computed under the old
code has stale `position` values cached in ProcessedResult, so this
backfills them with the corrected ranking -- it's a pure re-derivation
from ExamResult (the source of truth), not a data change of its own.
"""
from django.db import migrations


def recompute_csee_exams(apps, schema_editor):
    from ..services.upload_processing_service import recompute_processed_results_for_exam

    Exam = apps.get_model('results', 'Exam')
    exam_ids = list(Exam.objects.filter(form__in=[1, 2, 3, 4]).values_list('id', flat=True))
    # recompute_processed_results_for_exam expects the real model (it
    # calls .examresult_set, .select_related, etc.) -- apps.get_model's
    # historical model is fine for the lookup above, but re-fetch with the
    # real Exam class for the actual recompute call.
    from ..models import Exam as RealExam

    for exam_id in exam_ids:
        exam = RealExam.objects.filter(id=exam_id).first()
        if exam is None:
            continue
        try:
            recompute_processed_results_for_exam(exam)
        except Exception as exc:
            print(f"[0036] skipped exam #{exam_id}: {exc}")


def reverse_noop(apps, schema_editor):
    pass  # re-derived cache, not meaningfully reversible


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0035_merge_duplicate_history_subjects'),
    ]

    operations = [
        migrations.RunPython(recompute_csee_exams, reverse_noop),
    ]
