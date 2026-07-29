"""Add preferred_language field to TLMTeacher model."""
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add preferred_language field for English/Kiswahili toggle."""

    dependencies = [
        ('curriculum', '0006_add_theme_to_tlm_teacher'),
    ]

    operations = [
        migrations.AddField(
            model_name='tlmteacher',
            name='preferred_language',
            field=models.CharField(
                choices=[
                    ('auto', 'Auto (Otomatiki — kulingana na somo)'),
                    ('english', 'English'),
                    ('kiswahili', 'Kiswahili'),
                ],
                default='auto',
                help_text='Chagua lugha ya Scheme na Lesson Plan zako',
                max_length=10,
                verbose_name='Lugha / Language',
            ),
        ),
    ]
