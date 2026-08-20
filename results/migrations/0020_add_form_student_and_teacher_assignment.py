from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0019_add_logos_to_school'),
    ]

    operations = [
        migrations.CreateModel(
            name='FormStudent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('form', models.PositiveIntegerField()),
                ('admission_no', models.CharField(blank=True, max_length=50)),
                ('first_name', models.CharField(max_length=100)),
                ('middle_name', models.CharField(blank=True, max_length=100)),
                ('last_name', models.CharField(max_length=100)),
                ('gender', models.CharField(choices=[('F', 'Female'), ('M', 'Male')], max_length=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='form_students', to='results.school')),
            ],
            options={
                'ordering': ['form', 'last_name', 'first_name'],
                'unique_together': {('school', 'form', 'admission_no')},
            },
        ),
        migrations.CreateModel(
            name='TeacherFormAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('form', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='teacher_assignments', to='results.school')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='results.subject')),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='form_assignments', to='results.teacheraccount')),
            ],
            options={
                'ordering': ['form', 'subject__name'],
                'unique_together': {('teacher', 'form', 'subject')},
            },
        ),
    ]
