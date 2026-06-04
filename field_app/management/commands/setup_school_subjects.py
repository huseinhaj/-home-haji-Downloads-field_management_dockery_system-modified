from django.core.management.base import BaseCommand
from field_app.models import School, Subject, SchoolSubjectCapacity


class Command(BaseCommand):
    help = 'Link all schools with subjects of their level (max_students=5)'

    def handle(self, *args, **options):
        primary_subjects = list(Subject.objects.filter(level='primary'))
        secondary_subjects = list(Subject.objects.filter(level='secondary'))

        if not primary_subjects or not secondary_subjects:
            self.stdout.write(self.style.ERROR('Subjects not loaded. Run import_subjects first.'))
            return

        existing = set(
            SchoolSubjectCapacity.objects.values_list('school_id', 'subject_id')
        )
        self.stdout.write(f'Existing records: {len(existing)}')

        to_create = []
        for school in School.objects.only('id', 'level'):
            subjects = primary_subjects if school.level == 'Primary' else secondary_subjects
            for subject in subjects:
                if (school.id, subject.id) not in existing:
                    to_create.append(SchoolSubjectCapacity(
                        school=school,
                        subject=subject,
                        max_students=5,
                        current_students=0,
                    ))

        if not to_create:
            self.stdout.write(self.style.SUCCESS('All school-subject links already exist.'))
            return

        self.stdout.write(f'Creating {len(to_create)} records...')
        SchoolSubjectCapacity.objects.bulk_create(to_create, batch_size=1000, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f'Done. Created {len(to_create)} school-subject links.'))
