from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0051_continuousassessmentsnapshot'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='formstudent',
            index=models.Index(
                fields=['school', 'form', 'is_active', 'academic_year'],
                name='results_fs_roster_idx',
            ),
        ),
    ]
