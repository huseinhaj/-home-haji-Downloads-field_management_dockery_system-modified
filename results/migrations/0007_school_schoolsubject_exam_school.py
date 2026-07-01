from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0006_subjectsubmission_approval'),
    ]

    operations = [
        migrations.CreateModel(
            name='School',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('region', models.CharField(max_length=100)),
                ('district', models.CharField(max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='SchoolSubject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('form_levels', models.CharField(default='1,2,3,4', max_length=20)),
                ('school', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='school_subjects',
                    to='results.school',
                )),
                ('subject', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='results.subject',
                )),
            ],
            options={
                'unique_together': {('school', 'subject')},
            },
        ),
        migrations.AddField(
            model_name='exam',
            name='school',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='exams',
                to='results.school',
            ),
        ),
    ]
