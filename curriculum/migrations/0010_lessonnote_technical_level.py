# Generated migration — LessonNote education_level now includes 'technical' (VETA).
# Choices-only change; no schema alteration required.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0009_technical_syllabus_topics'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lessonnote',
            name='education_level',
            field=models.CharField(
                choices=[
                    ('primary', 'Primary School'),
                    ('ordinary', 'Ordinary Level'),
                    ('advanced', 'Advanced Level'),
                    ('technical', 'Technical / VETA'),
                ],
                default='ordinary', max_length=20, verbose_name='Ngazi ya Elimu',
            ),
        ),
    ]
