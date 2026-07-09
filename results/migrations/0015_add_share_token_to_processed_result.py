"""Add share_token UUID field to ProcessedResult for public access links.

Uses SeparateDatabaseAndState + RunSQL so it works both on a fresh
database AND on Railway where a previous attempt left the column in place
but didn't commit the migration to Django's state tracker.
"""

import uuid

from django.db import migrations, models


def populate_existing_tokens(apps, schema_editor):
    """Give every existing ProcessedResult a unique UUID."""
    ProcessedResult = apps.get_model('results', 'ProcessedResult')
    ids = list(ProcessedResult.objects.values_list('id', flat=True))
    if not ids:
        return
    batch = []
    for pk in ids:
        batch.append(ProcessedResult(id=pk, share_token=uuid.uuid4()))
    ProcessedResult.objects.bulk_update(batch, fields=['share_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0014_subscriptionplan_schoolsubscription_and_more'),
    ]

    operations = [
        # Physically ensure the column exists (idempotent — IF NOT EXISTS)
        migrations.RunSQL(
            "ALTER TABLE results_processedresult "
            "ADD COLUMN IF NOT EXISTS share_token uuid;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Tell Django's state the field exists (safe to re-run)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='processedresult',
                    name='share_token',
                    field=models.UUIDField(
                        null=True,
                        editable=False,
                        help_text="Unique token for anonymous public access "
                                  "to this student's result.",
                    ),
                ),
            ],
            database_operations=[],
        ),
        # Generate a guaranteed-unique token for every row
        migrations.RunPython(populate_existing_tokens, migrations.RunPython.noop),
        # Make the column unique (only runs after duplicates are gone)
        migrations.AlterField(
            model_name='processedresult',
            name='share_token',
            field=models.UUIDField(
                default=uuid.uuid4, editable=False, unique=True,
                help_text="Unique token for anonymous public access to this student's result.",
            ),
        ),
    ]
