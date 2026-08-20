from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0020_add_form_student_and_teacher_assignment'),
    ]

    operations = [
        migrations.AddField(
            model_name='school',
            name='school_logo_b64',
            field=models.TextField(blank=True, default='',
                help_text='School logo stored as base64 — persists on Railway'),
        ),
        migrations.AddField(
            model_name='school',
            name='district_logo_b64',
            field=models.TextField(blank=True, default='',
                help_text='District logo stored as base64 — persists on Railway'),
        ),
    ]
