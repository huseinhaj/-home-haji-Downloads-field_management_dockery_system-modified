"""
Management command to seed the FULL syllabus topics and subtopics for levels
that had missing data:

  - PRIMARY: Hesabu, Kusoma, Kuandika, Sayansi, Maarifa ya Jamii, Stadi za Kazi,
             Elimu ya Dini, Uchoraji, Muziki, Michezo  (Standards 1-7)
  - SECONDARY extras: Bible Knowledge, Islamic Knowledge, French, Arabic (Form 1-4)
  - ADVANCED: A-Level subjects zote 16 (Form 5-6)
  - TECHNICAL / VETA: masomo ya ufundi 36 (Electrical Installation, Plumbing,
      Masonry, Carpentry, Welding, Motor Vehicle Mechanics, ICT n.k.)
      (Grade III, Grade II, Grade I, NTA 4/5/6)

Usage:
    python manage.py seed_full_syllabus              # Seed all
    python manage.py seed_full_syllabus --subject Hesabu
    python manage.py seed_full_syllabus --subject "Electrical Installation"
    python manage.py seed_full_syllabus --list       # List subjects

Data source: curriculum/management/data/full_syllabus_data.py
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from field_app.models import Subject
from curriculum.models import SubjectTopic, TopicSubtopic
from curriculum.management.data.full_syllabus_data import get_full_syllabus


class Command(BaseCommand):
    help = "Seed missing primary/secondary/advanced subjects with topics and subtopics"

    def add_arguments(self, parser):
        parser.add_argument('--subject', type=str, help='Subject name to seed (case-insensitive)')
        parser.add_argument('--list', action='store_true', help='List subjects that will be seeded')

    def handle(self, *args, **options):
        all_data = get_full_syllabus()

        if options['list']:
            self.stdout.write("\n📚 Subjects in full syllabus data:")
            self.stdout.write("=" * 60)
            for name, data in all_data.items():
                classes = len(data['topics_by_class'])
                topic_count = sum(len(t) for t in data['topics_by_class'].values())
                exists = Subject.objects.filter(name=name).exists()
                status = "⚠️ exists" if exists else "➕ new subject"
                self.stdout.write(
                    f"  • {name} [{data['level']}]: {classes} classes, {topic_count} topics [{status}]"
                )
            self.stdout.write(f"\nTotal: {len(all_data)} subjects")
            return

        subject_filter = options.get('subject')
        if subject_filter:
            matched = {}
            for name, data in all_data.items():
                if subject_filter.lower() in name.lower():
                    matched[name] = data
            if not matched:
                self.stdout.write(self.style.ERROR(
                    f"Subject '{subject_filter}' not found. Available: {', '.join(all_data.keys())}"
                ))
                return
            all_data = matched

        total_topics = 0
        total_subtopics = 0

        for subject_name, subject_data in all_data.items():
            with transaction.atomic():
                # Match by NAME AND LEVEL — kuna masomo yenye majina sawa (mf. Physics
                # iko secondary na advanced) kwa hiyo lazima tuchague ile sahihi.
                subj = Subject.objects.filter(
                    name__iexact=subject_name, level=subject_data['level']
                ).first()
                if not subj:
                    self.stdout.write(self.style.WARNING(
                        f"  ⚠️ Subject '{subject_name}' ({subject_data['level']}) haipo kwenye database — inarukwa."
                    ))
                    continue

                for class_name, topic_list in subject_data['topics_by_class'].items():
                    for topic_data in topic_list:
                        topic, t_created = SubjectTopic.objects.get_or_create(
                            subject=subj,
                            class_name=class_name,
                            name=topic_data['name'],
                            defaults={'order': topic_data.get('order', 0)}
                        )
                        if t_created:
                            for sub_order, subtopic_name in enumerate(topic_data.get('subtopics', []), 1):
                                TopicSubtopic.objects.get_or_create(
                                    topic=topic,
                                    name=subtopic_name,
                                    defaults={'order': sub_order}
                                )
                            total_topics += 1
                            total_subtopics += len(topic_data.get('subtopics', []))
                        else:
                            # Ensure subtopics exist for existing topics
                            existing_sub_names = set(
                                TopicSubtopic.objects.filter(topic=topic)
                                .values_list('name', flat=True)
                            )
                            for sub_order, subtopic_name in enumerate(topic_data.get('subtopics', []), 1):
                                if subtopic_name not in existing_sub_names:
                                    TopicSubtopic.objects.get_or_create(
                                        topic=topic,
                                        name=subtopic_name,
                                        defaults={'order': sub_order}
                                    )
                                    total_subtopics += 1
                self.stdout.write(f"  ✅ Seeded: {subject_name} [{subj.level}]")

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Done! {len(all_data)} subject(s) — {total_topics} new topics, {total_subtopics} subtopics"
        ))
