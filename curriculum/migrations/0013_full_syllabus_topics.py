"""
Data migration: Topics na subtopics za masomo yaliyokuwa hayana data —
PRIMARY (10 subjects, Standards 1-7), SECONDARY extras (4 subjects, Form 1-4)
na ADVANCED/A-Level (16 subjects, Form 5-6).

Data inategemea curriculum/management/data/full_syllabus_data.py.
Inatekelezwa kiotomatiki wakati wa 'manage.py migrate'.
"""
from django.db import migrations
from curriculum.management.data.full_syllabus_data import get_full_syllabus


def seed_full_topics(apps, schema_editor):
    Subject = apps.get_model('field_app', 'Subject')
    SubjectTopic = apps.get_model('curriculum', 'SubjectTopic')
    TopicSubtopic = apps.get_model('curriculum', 'TopicSubtopic')
    db = schema_editor.connection.alias

    all_data = get_full_syllabus()

    total_topics = 0
    total_subtopics = 0

    for subject_name, subject_data in all_data.items():
        # Match by NAME AND LEVEL — kuna masomo yenye majina sawa (mf. Physics
        # iko secondary na advanced) kwa hiyo lazima tuchague ile sahihi.
        subj = Subject.objects.using(db).filter(
            name__iexact=subject_name, level=subject_data['level']
        ).first()
        if not subj:
            print(f"[Full Syllabus] ⚠️  '{subject_name}' ({subject_data['level']}) haipo — imerukwa")
            continue

        existing_topic_keys = set(
            SubjectTopic.objects.using(db).filter(subject=subj)
            .values_list('class_name', 'name')
        )

        new_topics = []
        for class_name, topic_list in subject_data['topics_by_class'].items():
            for topic_data in topic_list:
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

        # Subtopics for all topics of this subject
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
        for class_name, topic_list in subject_data['topics_by_class'].items():
            for topic_data in topic_list:
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

    print(f"[Full Syllabus] {len(all_data)} subjects | "
          f"{total_topics} topics | {total_subtopics} subtopics")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0012_pastpaper_markingscheme'),
    ]

    operations = [
        migrations.RunPython(seed_full_topics, noop),
    ]
