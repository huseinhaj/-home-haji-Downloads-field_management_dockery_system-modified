"""
Management command: Sogeza topics za Form 5/6 zilizowekwa kwenye masomo ya
secondary (kutokana na majina yanayofanana) kwenda kwenye masomo ya advanced.

Idempotent — inaweza kuendeshwa mara nyingi bila madhara.

Usage:
    python manage.py fix_advanced_topic_placement
"""
from django.core.management.base import BaseCommand
from field_app.models import Subject
from curriculum.models import SubjectTopic, TopicSubtopic

A_LEVEL_CLASSES = ['Form 5', 'Form 6']


class Command(BaseCommand):
    help = "Move misplaced Form 5/6 topics from same-named secondary subjects to advanced subjects"

    def handle(self, *args, **options):
        moved_topics = 0
        moved_subtopics = 0

        advanced_subs = list(Subject.objects.filter(level='advanced'))
        for adv in advanced_subs:
            same_name_secondary = Subject.objects.filter(
                name__iexact=adv.name, level='secondary'
            ).first()
            if not same_name_secondary:
                continue

            misplaced = list(SubjectTopic.objects.filter(
                subject=same_name_secondary, class_name__in=A_LEVEL_CLASSES
            ))
            if not misplaced:
                continue

            new_topics = [
                SubjectTopic(subject=adv, class_name=t.class_name, name=t.name, order=t.order)
                for t in misplaced
            ]
            SubjectTopic.objects.bulk_create(new_topics, ignore_conflicts=True)

            new_by_key = {}
            for t in SubjectTopic.objects.filter(subject=adv, class_name__in=A_LEVEL_CLASSES):
                new_by_key[(t.class_name, t.name)] = t.id

            sub_objs = []
            for old in misplaced:
                new_id = new_by_key.get((old.class_name, old.name))
                if not new_id:
                    continue
                existing = set(
                    TopicSubtopic.objects.filter(topic_id=new_id).values_list('name', flat=True)
                )
                for sub in TopicSubtopic.objects.filter(topic=old):
                    if sub.name not in existing:
                        sub_objs.append(TopicSubtopic(
                            topic_id=new_id, name=sub.name, order=sub.order,
                        ))
                        moved_subtopics += 1
            TopicSubtopic.objects.bulk_create(sub_objs, ignore_conflicts=True)

            misplaced_ids = [t.id for t in misplaced]
            TopicSubtopic.objects.filter(topic_id__in=misplaced_ids).delete()
            SubjectTopic.objects.filter(id__in=misplaced_ids).delete()
            moved_topics += len(misplaced)
            self.stdout.write(f"  ✅ {adv.name}: {len(misplaced)} topics zimesogezwa")

        self.stdout.write(self.style.SUCCESS(
            f"Done! {moved_topics} topics, {moved_subtopics} subtopics zimesogezwa"
        ))
