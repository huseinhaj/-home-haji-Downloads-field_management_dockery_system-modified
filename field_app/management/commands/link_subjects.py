from django.core.management.base import BaseCommand
from field_app.models import School, Subject, SchoolSubjectCapacity

class Command(BaseCommand):
    help = "Link subjects to schools based on level (primary/secondary)"

    def handle(self, *args, **options):
        count_created = 0
        schools = School.objects.all()
        for school in schools:
            subjects = Subject.objects.filter(level=school.level.lower())
            for subject in subjects:
                obj, created = SchoolSubjectCapacity.objects.get_or_create(
                    school=school,
                    subject=subject,
                    defaults={
                        'max_students': 5,
                        'current_students': 0,
                    }
                )
                if created:
                    count_created += 1
                    self.stdout.write(f"Linked {subject.name} to {school.name}")

        self.stdout.write(self.style.SUCCESS(f"✅ Done. Total new links created: {count_created}"))

