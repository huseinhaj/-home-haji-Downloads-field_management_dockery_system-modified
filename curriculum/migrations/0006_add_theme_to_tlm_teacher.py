"""Add theme field to TLMTeacher model."""
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add theme field with 5 choices for PDF color themes."""

    dependencies = [
        ('curriculum', '0005_subjecttopic_topicsubtopic'),
    ]

    operations = [
        migrations.AddField(
            model_name='tlmteacher',
            name='theme',
            field=models.CharField(
                choices=[
                    ('classic', 'TIE Classic — Navy & Gold'),
                    ('tanzania', 'Tanzania — Green & Yellow'),
                    ('ocean', 'Ocean Blue — Blue & Teal'),
                    ('royal', 'Royal Purple — Purple & Pink'),
                    ('executive', 'Executive — Charcoal & Silver'),
                ],
                default='classic',
                help_text='Chagua rangi za PDF zako (Scheme & Lesson Plan)',
                max_length=20,
                verbose_name='Rangi / Theme',
            ),
        ),
    ]
