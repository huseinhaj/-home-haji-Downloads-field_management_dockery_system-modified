from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0005_exam_school_name_subjectsubmission'),
    ]

    operations = [
        migrations.AddField(
            model_name='subjectsubmission',
            name='approved_by',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='subjectsubmission',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='subjectsubmission',
            name='approval_notes',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='subjectsubmission',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('SUBMITTED', 'Submitted'),
                    ('APPROVED', 'Approved'),
                ],
                default='PENDING',
                max_length=20,
            ),
        ),
    ]
