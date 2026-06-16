from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('field_app', '0022_add_subject_breakdown_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='finalassessment',
            name='finalized_at',
            field=models.DateTimeField(blank=True, null=True, help_text='Tarehe tathmini ilipokamilika'),
        ),
    ]
