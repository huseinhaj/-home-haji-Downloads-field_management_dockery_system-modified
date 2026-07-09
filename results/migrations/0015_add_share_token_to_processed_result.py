"""Add share_token UUID field to ProcessedResult for public access links."""

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
        migrations.AddField(
            model_name='processedresult',
            name='share_token',
            field=models.UUIDField(
                default=uuid.uuid4, editable=False,
                help_text="Unique token for anonymous public access "
                          "to this student's result.",
            ),
        ),
        # Populate existing rows with unique UUIDs (overwrites the
        # single eval-time default so every row gets a distinct value)
        migrations.RunPython(populate_existing_tokens, migrations.RunPython.noop),
    ]
