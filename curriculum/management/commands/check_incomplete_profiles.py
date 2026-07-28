"""
Management command to identify TLM teachers with incomplete profiles.
These are teachers who registered before the auto-fill fields were added
to the registration form (class_name, stream, subject, total_boys, total_girls).

Usage:
    python manage.py check_incomplete_profiles           # List all incomplete
    python manage.py check_incomplete_profiles --fix      # Attempt auto-backfill from existing SchemeOfWork records
"""
from django.core.management.base import BaseCommand
from curriculum.models import TLMTeacher
from field_app.models import SchemeOfWork, Subject


class Command(BaseCommand):
    help = 'Identify TLM teachers whose profile is missing auto-fill fields'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to backfill missing data from existing SchemeOfWork records',
        )

    def handle(self, *args, **options):
        should_fix = options.get('fix', False)

        # Find teachers missing class_name, stream, subject, or student counts
        incomplete = TLMTeacher.objects.filter(
            class_name=''
        ) | TLMTeacher.objects.filter(
            subject__isnull=True
        )
        incomplete = incomplete.distinct().order_by('-created_at')

        total = incomplete.count()
        self.stdout.write(self.style.WARNING(f"\n🔍 Found {total} teachers with incomplete profiles"))
        self.stdout.write("-" * 80)

        for teacher in incomplete:
            missing = []
            if not teacher.class_name:
                missing.append('class_name')
            if not teacher.stream:
                missing.append('stream')
            if not teacher.subject:
                missing.append('subject')
            if teacher.total_boys == 0 and teacher.total_girls == 0:
                missing.append('total_boys/girls')

            school_name = teacher.school.name if teacher.school else 'N/A'
            self.stdout.write(
                f"  • {teacher.full_name:25s} | {teacher.phone_number:15s} | "
                f"{school_name:25s} | Missing: {', '.join(missing)}"
            )

            if should_fix:
                self._try_backfill(teacher)

        self.stdout.write(self.style.SUCCESS(f"\n✅ Done. {total} teachers checked."))

    def _try_backfill(self, teacher):
        """Try to fill missing data from existing SchemeOfWork records."""
        changed = False

        # Try to find subject from existing schemes
        if not teacher.subject:
            scheme = SchemeOfWork.objects.filter(
                teacher_name=teacher.full_name,
                school=teacher.school,
                subject__isnull=False
            ).select_related('subject').first()
            if scheme and scheme.subject:
                teacher.subject = scheme.subject
                changed = True
                self.stdout.write(self.style.SUCCESS(
                    f"    → Backfilled subject: {scheme.subject.name}"
                ))

        # Try to find class_name from existing schemes
        if not teacher.class_name:
            scheme = SchemeOfWork.objects.filter(
                teacher_name=teacher.full_name,
                school=teacher.school,
            ).exclude(class_name='').first()
            if scheme:
                teacher.class_name = scheme.class_name
                changed = True
                self.stdout.write(self.style.SUCCESS(
                    f"    → Backfilled class_name: {scheme.class_name}"
                ))

        if changed:
            teacher.save(update_fields=['subject', 'class_name'])
