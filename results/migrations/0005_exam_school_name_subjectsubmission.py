from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0004_speechsubmissionsession_roster_student_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='exam',
            name='school_name',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.CreateModel(
            name='SubjectSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending'), ('SUBMITTED', 'Submitted')],
                    default='PENDING',
                    max_length=20,
                )),
                ('method', models.CharField(
                    blank=True,
                    choices=[('SPEECH', 'Speech Entry'), ('UPLOAD', 'File Upload')],
                    max_length=20,
                )),
                ('submitted_by', models.CharField(blank=True, max_length=100)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('student_count', models.PositiveIntegerField(default=0)),
                ('exam', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='subject_submissions',
                    to='results.exam',
                )),
                ('subject', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='submissions',
                    to='results.subject',
                )),
            ],
            options={
                'ordering': ['subject__name'],
                'unique_together': {('exam', 'subject')},
            },
        ),
    ]
