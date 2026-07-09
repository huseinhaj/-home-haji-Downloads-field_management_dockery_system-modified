"""Add share_token UUID field to ProcessedResult for public access links."""

import uuid

from django.db import migrations, models


def populate_existing_tokens(apps, schema_editor):
    ProcessedResult = apps.get_model('results', 'ProcessedResult')
    for obj in ProcessedResult.objects.all():
        if not obj.share_token:
            obj.share_token = uuid.uuid4()
            obj.save(update_fields=['share_token'])


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
                help_text="Unique token for anonymous public access to this student's result.",
                null=True,  # Temporarily nullable for existing rows
            ),
        ),
        migrations.RunPython(populate_existing_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='processedresult',
            name='share_token',
            field=models.UUIDField(
                default=uuid.uuid4, editable=False, unique=True,
                help_text="Unique token for anonymous public access to this student's result.",
            ),
        ),
    ]
