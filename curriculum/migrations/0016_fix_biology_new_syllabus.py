"""
Data migration: Rekebisha Biology Form 1 na Form 2 — topics za MTAALA MPYA (2023).

Walimu walilalamika kwamba Biology Form 1 ilikuwa na topics za mtaala wa zamani.
Mtaala mpya (2023 CBC) unatumika kwa Form 1 na Form 2; Form 3 na Form 4
zinabaki kwenye mtaala wa zamani.

Chanzo: TIE "Biology for Secondary Schools" (2023/2025) — Form One na Form Two.
Data hii inaendana na curriculum/management/commands/seed_tie_syllabus.py
(FORM_1_SYLLABUS / FORM_2_SYLLABUS) ili kukaa single source of truth.
Idempotent: inaweza kuendeshwa mara nyingi bila madhara.
"""
from django.db import migrations

from curriculum.management.commands.seed_tie_syllabus import FORM_1_SYLLABUS, FORM_2_SYLLABUS


def fix_biology_new_syllabus(apps, schema_editor):
    Subject = apps.get_model('field_app', 'Subject')
    SubjectTopic = apps.get_model('curriculum', 'SubjectTopic')
    TopicSubtopic = apps.get_model('curriculum', 'TopicSubtopic')
    db = schema_editor.connection.alias

    biology = Subject.objects.using(db).filter(name__iexact='Biology', level='secondary').first()
    if not biology:
        biology = Subject.objects.using(db).filter(name__iexact='Biology').first()
    if not biology:
        print("[Biology New Syllabus] ⚠️  Somo 'Biology' halipatikani kwenye database — imerukwa")
        return

    new_data = {
        'Form 1': FORM_1_SYLLABUS['Biology']['topics'],
        'Form 2': FORM_2_SYLLABUS['Biology']['topics'],
    }

    total_created = 0
    total_subs = 0
    for class_name, topic_list in new_data.items():
        # Ondoa topics zote za zamani za darasa hili (subtopics zinafutika kwa CASCADE)
        old_ids = list(
            SubjectTopic.objects.using(db).filter(
                subject=biology, class_name__iexact=class_name
            ).values_list('id', flat=True)
        )
        deleted = SubjectTopic.objects.using(db).filter(id__in=old_ids).delete()
        print(f"[Biology New Syllabus] {class_name}: topics za zamani zimefutwa "
              f"({deleted[0]} records)")

        # Unda topics mpya za mtaala mpya
        for topic_data in topic_list:
            topic = SubjectTopic.objects.using(db).create(
                subject=biology,
                class_name=class_name,
                name=topic_data['name'],
                order=topic_data.get('order', 0),
            )
            total_created += 1
            for i, subtopic_name in enumerate(topic_data.get('subtopics', []), 1):
                TopicSubtopic.objects.using(db).create(
                    topic=topic, name=subtopic_name, order=i,
                )
                total_subs += 1

    print(f"[Biology New Syllabus] Imeisha: {total_created} topics mpya, "
          f"{total_subs} subtopics (Form 1 & 2 = mtaala mpya 2023)")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0015_seed_technical_syllabus_topics'),
    ]

    operations = [
        migrations.RunPython(fix_biology_new_syllabus, noop),
    ]
