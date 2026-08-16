"""
Data migration: Masomo ya A-Level yenye majina yanayofanana na ya secondary
(mf. Physics, Chemistry, Biology, Kiswahili, English Language, Geography,
History, Agriculture, Computer Science) — topics za Form 5/6 zilizowekwa kwenye
somo la secondary zinasogezwa kwenye somo la advanced.

Idempotent: kwenye mazingira mapya (0013 tayari imefanya kazi sahihi) hakuna
kitu cha kufanya. Inatumia BULK operations tu (bulk_create + queryset.delete)
ili kuepuka collector wa cascade delete unaoweza kukwama kwenye Postgres ya mbali.
"""
from django.db import migrations

A_LEVEL_CLASSES = ['Form 5', 'Form 6']


def fix_advanced_topics(apps, schema_editor):
    Subject = apps.get_model('field_app', 'Subject')
    SubjectTopic = apps.get_model('curriculum', 'SubjectTopic')
    TopicSubtopic = apps.get_model('curriculum', 'TopicSubtopic')
    db = schema_editor.connection.alias

    moved_topics = 0
    moved_subtopics = 0

    advanced_subs = list(Subject.objects.using(db).filter(level='advanced'))
    for adv in advanced_subs:
        same_name_secondary = Subject.objects.using(db).filter(
            name__iexact=adv.name, level='secondary'
        ).first()
        if not same_name_secondary:
            continue

        misplaced = list(SubjectTopic.objects.using(db).filter(
            subject=same_name_secondary, class_name__in=A_LEVEL_CLASSES
        ))
        if not misplaced:
            continue

        # 1) Tengeneza topics kwenye somo la advanced (bulk, ignore conflicts)
        new_topics = [
            SubjectTopic(subject=adv, class_name=t.class_name, name=t.name, order=t.order)
            for t in misplaced
        ]
        SubjectTopic.objects.using(db).bulk_create(new_topics, ignore_conflicts=True)

        # 2) Ramani: (class, name) -> id ya topic kwenye advanced
        new_by_key = {}
        for t in SubjectTopic.objects.using(db).filter(
            subject=adv, class_name__in=A_LEVEL_CLASSES
        ):
            new_by_key[(t.class_name, t.name)] = t.id

        # 3) Nakili subtopics (bulk, ignore conflicts)
        sub_objs = []
        for old in misplaced:
            new_id = new_by_key.get((old.class_name, old.name))
            if not new_id:
                continue
            existing = set(
                TopicSubtopic.objects.using(db).filter(topic_id=new_id)
                .values_list('name', flat=True)
            )
            for sub in TopicSubtopic.objects.using(db).filter(topic=old):
                if sub.name not in existing:
                    sub_objs.append(TopicSubtopic(
                        topic_id=new_id, name=sub.name, order=sub.order,
                    ))
                    moved_subtopics += 1
        TopicSubtopic.objects.using(db).bulk_create(sub_objs, ignore_conflicts=True)

        # 4) Futa subtopics za topics zilizokosea, kisha topics zenyewe
        misplaced_ids = [t.id for t in misplaced]
        TopicSubtopic.objects.using(db).filter(topic_id__in=misplaced_ids).delete()
        SubjectTopic.objects.using(db).filter(id__in=misplaced_ids).delete()
        moved_topics += len(misplaced)

    print(f"[Fix Advanced Placement] {moved_topics} topics | {moved_subtopics} subtopics zimesogezwa", flush=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0013_full_syllabus_topics'),
    ]

    operations = [
        migrations.RunPython(fix_advanced_topics, noop),
    ]
