"""
Textbook: ongeza 'technical' (VETA) kwenye LEVEL_CHOICES + url/description/uploaded_by
— kwa ajili ya Maktaba ya Vitabu (links za TIE/TETEA + upload za walimu).
"""
from django.conf import settings
from django.db import migrations, models


def update_level_choices(apps, schema_editor):
    # Hakuna mabadiliko ya data — choices ni kwenye level ya Python pekee.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('field_app', '0034_technical_veta_schools_subjects'),
    ]

    operations = [
        migrations.AlterField(
            model_name='textbook',
            name='education_level',
            field=models.CharField(
                choices=[
                    ('primary', 'Primary School'),
                    ('ordinary', 'Ordinary Level'),
                    ('advanced', 'Advanced Level'),
                    ('technical', 'Technical / VETA'),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='textbook',
            name='url',
            field=models.URLField(blank=True, verbose_name='External link (PDF/reader)'),
        ),
        migrations.AddField(
            model_name='textbook',
            name='description',
            field=models.TextField(blank=True, verbose_name='Maelezo mafupi'),
        ),
        migrations.AddField(
            model_name='textbook',
            name='uploaded_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=models.SET_NULL,
                related_name='uploaded_textbooks',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(update_level_choices, migrations.RunPython.noop),
    ]
