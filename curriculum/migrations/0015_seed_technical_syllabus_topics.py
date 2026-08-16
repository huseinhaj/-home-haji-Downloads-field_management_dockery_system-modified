"""
Data migration: Seed topics & subtopics za masomo ya ufundi (VETA/Technical) —
36 subjects (Electrical Installation, Plumbing, Masonry, Carpentry, Welding,
Motor Vehicle Mechanics, ICT, n.k.) kwa kila darasa la VETA (Grade III, Grade II,
Grade I, NTA 4/5/6).

Hii inaongeza data ya migration 0009 kwenye seed system ya kawaida
(curriculum/management/data/full_syllabus_data.py) — idempotent, inaweza kuendeshwa
mara nyingi bila madhara. Inafanya kazi pia kwenye mazingira ambayo 0009
haikuweza kufanikiwa (k.m. masomo yalikuwa hayajakuwepo wakati huo).
"""
from django.db import migrations

from curriculum.management.data.full_syllabus_data import TECHNICAL_CLASSES, TECHNICAL_SYLLABUS


def seed_technical_topics(apps, schema_editor):
    Subject = apps.get_model('field_app', 'Subject')
    SubjectTopic = apps.get_model('curriculum', 'SubjectTopic')
    TopicSubtopic = apps.get_model('curriculum', 'TopicSubtopic')
    db = schema_editor.connection.alias

    total_topics = 0
    total_subtopics = 0

    for subject_name, subject_data in TECHNICAL_SYLLABUS.items():
        # Match by CODE kwanza (T01, T02 ...) kisha kwa jina — kama 0009
        subj = Subject.objects.using(db).filter(code=subject_data.get('code')).first()
        if not subj:
            subj = Subject.objects.using(db).filter(name__iexact=subject_name).first()
        if not subj:
            print(f"[Technical Syllabus] ⚠️  '{subject_name}' haipo — imerukwa")
            continue

        existing_topic_keys = set(
            SubjectTopic.objects.using(db).filter(subject=subj)
            .values_list('class_name', 'name')
        )

        new_topics = []
        for class_name in TECHNICAL_CLASSES:
            for topic_data in subject_data['topics_by_class'][class_name]:
                if (class_name, topic_data['name']) in existing_topic_keys:
                    continue
                new_topics.append(SubjectTopic(
                    subject=subj,
                    class_name=class_name,
                    name=topic_data['name'],
                    order=topic_data.get('order', 0),
                ))
        SubjectTopic.objects.using(db).bulk_create(new_topics, ignore_conflicts=True)
        total_topics += len(new_topics)

        # Subtopics kwa topics zote za somo hili
        topic_ids = list(
            SubjectTopic.objects.using(db).filter(subject=subj).values_list('id', flat=True)
        )
        topic_id_by_name = {}
        if topic_ids:
            for t in SubjectTopic.objects.using(db).filter(id__in=topic_ids):
                topic_id_by_name[(t.class_name, t.name)] = t.id

        existing_sub_keys = set()
        if topic_ids:
            existing_sub_keys = set(
                TopicSubtopic.objects.using(db).filter(topic_id__in=topic_ids)
                .values_list('topic_id', 'name')
            )

        new_subtopics = []
        for class_name in TECHNICAL_CLASSES:
            for topic_data in subject_data['topics_by_class'][class_name]:
                tid = topic_id_by_name.get((class_name, topic_data['name']))
                if not tid:
                    continue
                for sub_order, subtopic_name in enumerate(topic_data.get('subtopics', []), 1):
                    if (tid, subtopic_name) in existing_sub_keys:
                        continue
                    new_subtopics.append(TopicSubtopic(
                        topic_id=tid, name=subtopic_name, order=sub_order,
                    ))
        TopicSubtopic.objects.using(db).bulk_create(new_subtopics, ignore_conflicts=True)
        total_subtopics += len(new_subtopics)

    print(f"[Technical Syllabus Seed] {len(TECHNICAL_SYLLABUS)} subjects | "
          f"{total_topics} topics | {total_subtopics} subtopics")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0014_fix_advanced_topic_placement'),
    ]

    operations = [
        migrations.RunPython(seed_technical_topics, noop),
    ]
