"""INC/ABS division markers + nullable position.

- position becomes NULL for unranked candidates (ABS — sat nothing).
- division gains the NECTA markers INC (sat fewer than 7 subjects) and
  ABS (on the roster but sat nothing).

Schema-only on purpose: cached rows are backfilled by running the
`recompute_all_processed_results` management command (recomputing every
exam inside an atomic data migration deadlocked/dead-timeouted on the
remote Postgres proxy and rolled back wholesale on any single failure).
"""
from django.db import migrations, models


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
    ]
