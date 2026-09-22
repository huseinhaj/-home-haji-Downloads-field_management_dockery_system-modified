"""INC/ABS division markers + nullable position.

- position becomes NULL for unranked candidates (ABS — sat nothing).
- division gains the NECTA markers INC (sat fewer than 7 subjects) and
  ABS (on the roster but sat nothing).
- Cached rows that are really one of those two cases get backfilled by
  re-running the exam recompute (which now emits the markers itself).
"""
from django.db import migrations, models


def _noop_bwd(apps, schema_editor):
    pass


def _backfill(apps, schema_editor):
    """Recompute every secondary CSEE exam so cached rows pick up the new
    INC/ABS markers and the division-first ranking with NULL positions.
    ACSEE/primary recomputes are harmless no-ops for these fields."""
    ProcessedResult = apps.get_model('results', 'ProcessedResult')
    Exam = apps.get_model('results', 'Exam')

    exam_ids = list(
        ProcessedResult.objects.exclude(division='').values_list('exam_id', flat=True)
    )
    if not exam_ids:
        return

    # recompute needs the real model (relations, bulk upsert) — same
    # pattern migration 0036 uses for its backfill.
    from ..models import Exam as RealExam
    from ..services.upload_processing_service import recompute_processed_results_for_exam

    for exam_id in exam_ids:
        exam = RealExam.objects.filter(id=exam_id).first()
        if exam is None:
            continue
        try:
            recompute_processed_results_for_exam(exam)
        except Exception as exc:
            print(f"[0054] skipped exam #{exam_id}: {exc}")


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0053_add_result_verification_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='processedresult',
            name='position',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='processedresult',
            name='division',
            field=models.CharField(
                blank=True, max_length=3,
                choices=[
                    ('I', 'Division I'), ('II', 'Division II'),
                    ('III', 'Division III'), ('IV', 'Division IV'),
                    ('0', 'Fail'), ('INC', 'Incomplete (INC)'), ('ABS', 'Absent (ABS)'),
                ],
                help_text='CSEE/ACSEE division (sekondari). BLANK kwa shule za msingi — '
                          'msingi hauna division, unaonekana kwa jumla/wastani/nafasi. '
                          'INC = masomo < 7 (hayajatosha kuhesabu daraja); '
                          'ABS = hakufanya mtihani wowote.',
            ),
        ),
        migrations.RunPython(_backfill, _noop_bwd),
    ]
