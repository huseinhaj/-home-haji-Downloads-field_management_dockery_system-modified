"""Deduplicate Subject records before adding unique constraint."""
from django.db import migrations


def deduplicate_subjects(apps, schema_editor):
    Subject = apps.get_model('results', 'Subject')
    ExamResult = apps.get_model('results', 'ExamResult')
    SubjectSubmission = apps.get_model('results', 'SubjectSubmission')

    # Find duplicate name groups
    from django.db.models import Count
    dupes = (
        Subject.objects.values('name')
        .annotate(cnt=Count('id'))
        .filter(cnt__gt=1)
    )

    for row in dupes:
        name = row['name']
        subjects = list(Subject.objects.filter(name=name).order_by('id'))
        keep = subjects[0]  # keep the oldest record
        remove = subjects[1:]

        for old in remove:
            # Re-point ExamResult and SubjectSubmission FKs to the kept record
            ExamResult.objects.filter(subject=old).update(subject=keep)
            SubjectSubmission.objects.filter(subject=old).update(subject=keep)
            old.delete()


def reverse_dedup(apps, schema_editor):
    pass  # no-op


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0030_translate_timetable_labels_to_english'),
    ]

    operations = [
        migrations.RunPython(deduplicate_subjects, reverse_dedup),
        migrations.AlterField(
            model_name='subject',
            name='name',
            field=models.CharField(max_length=100, unique=True),
        ),
    ]
