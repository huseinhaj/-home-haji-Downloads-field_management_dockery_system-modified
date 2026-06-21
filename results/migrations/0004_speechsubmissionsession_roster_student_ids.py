from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0003_speechsubmissionsession_speechsubmissionentry_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='speechsubmissionsession',
            name='roster_student_ids',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
