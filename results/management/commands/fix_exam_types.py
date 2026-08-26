"""
Management command to fix exam types that were set as 'OTHER'.

Usage:
    python manage.py fix_exam_types                    # List all 'OTHER' exams
    python manage.py fix_exam_types --preview          # Preview changes without saving
    python manage.py fix_exam_types --auto             # Auto-fix based on name patterns
    python manage.py fix_exam_types --set MOCK 5       # Set exam ID 5 to MOCK type
    python manage.py fix_exam_types --set PRE_NECTA 1,2,3  # Set multiple exams
"""

from django.core.management.base import BaseCommand
from results.models import Exam


# Keywords to match exam types based on name
EXAM_TYPE_KEYWORDS = {
    'PRE_NECTA': ['pre necta', 'pre-necta', 'prenecta'],
    'MOCK': ['mock'],
    'PRE_MOCK': ['pre mock', 'pre-mock', 'premock'],
    'INTERSCHOOL': ['interschool', 'inter-school'],
    'JOINT': ['joint'],
    'DISTRICT_JOINT': ['district joint', 'wilaya joint'],
    'REGION_JOINT': ['region joint', 'mkoa joint'],
    'ZONE_JOINT': ['zone joint', 'zone'],
    'TEST': ['test'],
    'MONTHLY': ['monthly', 'mwezi'],
    'QUIZ': ['quiz'],
    'MIDTERM': ['midterm', 'mid-term', 'kati'],
    'TERMINAL': ['terminal', 'mwisho', 'end of term'],
    'ANNUAL': ['annual', 'mwaka', 'csee', 'kcse'],
}


class Command(BaseCommand):
    help = 'Fix exam types that were incorrectly set as OTHER'

    def add_arguments(self, parser):
        parser.add_argument(
            '--preview', action='store_true',
            help='Preview changes without saving'
        )
        parser.add_argument(
            '--auto', action='store_true',
            help='Auto-fix based on exam name patterns'
        )
        parser.add_argument(
            '--set', nargs='+', metavar=('EXAM_TYPE', 'IDS'),
            help='Manually set exam type for specific IDs (e.g., --set MOCK 1,2,3)'
        )
        parser.add_argument(
            '--list', action='store_true',
            help='List all exams with OTHER type'
        )

    def handle(self, *args, **options):
        if options['set']:
            self.set_exam_type(options['set'])
        elif options['auto']:
            self.auto_fix(options['preview'])
        else:
            self.list_other_exams()

    def list_other_exams(self):
        """List all exams with OTHER type."""
        exams = Exam.objects.filter(exam_type='OTHER').order_by('-year', 'name')
        
        if not exams.exists():
            self.stdout.write(self.style.SUCCESS('✅ Hakuna exams zilizo na "OTHER" type!'))
            return
        
        self.stdout.write(self.style.WARNING(f'\n📊 Exams zilizo na "OTHER" type: {exams.count()}\n'))
        self.stdout.write(f'{"ID":<6} {"Name":<30} {"Year":<6} {"Form":<6} {"School":<30}')
        self.stdout.write('-' * 80)
        
        for exam in exams:
            school = exam.school_name or (exam.school.name if exam.school else 'N/A')
            self.stdout.write(
                f'{exam.id:<6} {exam.name:<30} {exam.year:<6} {exam.form:<6} {school:<30}'
            )
        
        self.stdout.write(self.style.WARNING(
            f'\n💡 Tumia command ifuatayo ku-fix:\n'
            f'   python manage.py fix_exam_types --auto          # Auto-fix based on name\n'
            f'   python manage.py fix_exam_types --set MOCK 1,2 # Manual fix'
        ))

    def auto_fix(self, preview=False):
        """Auto-fix based on exam name patterns."""
        exams = Exam.objects.filter(exam_type='OTHER')
        
        if not exams.exists():
            self.stdout.write(self.style.SUCCESS('✅ Hakuna exams zilizo na "OTHER" type!'))
            return
        
        changes = []
        
        for exam in exams:
            name_lower = exam.name.lower()
            new_type = None
            
            for exam_type, keywords in EXAM_TYPE_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in name_lower:
                        new_type = exam_type
                        break
                if new_type:
                    break
            
            if new_type:
                changes.append((exam, new_type))
        
        if not changes:
            self.stdout.write(self.style.WARNING(
                '\n⚠️  Hakuna exams zinazoweza ku-fix automatically.\n'
                'Tumia --set kwa kuzi-update manual.'
            ))
            return
        
        self.stdout.write(self.style.WARNING(f'\n📊 Idadi ya mabadiliko: {len(changes)}\n'))
        self.stdout.write(f'{"ID":<6} {"Name":<30} {"Old":<10} {"New":<15}')
        self.stdout.write('-' * 65)
        
        for exam, new_type in changes:
            self.stdout.write(
                f'{exam.id:<6} {exam.name:<30} {exam.exam_type:<10} {new_type:<15}'
            )
        
        if preview:
            self.stdout.write(self.style.WARNING('\n🔒 Preview mode - hakuna kilichobadilishwa'))
            return
        
        # Confirm
        confirm = input('\n✅ Ili ku-save mabadiliko, andika "yes": ')
        if confirm.lower() != 'yes':
            self.stdout.write(self.style.ERROR('❌ Operation cancelled'))
            return
        
        # Apply changes
        updated = 0
        for exam, new_type in changes:
            exam.exam_type = new_type
            exam.save()
            updated += 1
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Exams {updated} zimesha-update!'))

    def set_exam_type(self, args):
        """Manually set exam type for specific IDs."""
        if len(args) < 2:
            self.stdout.write(self.style.ERROR('❌ Tumia: --set EXAM_TYPE ID1,ID2,ID3'))
            return
        
        exam_type = args[0].upper()
        valid_types = [choice[0] for choice in Exam.EXAM_TYPE_CHOICES]
        
        if exam_type not in valid_types:
            self.stdout.write(self.style.ERROR(
                f'❌ Exam type "{exam_type}" si sahihi.\n'
                f'   Aina zinazokubalika: {", ".join(valid_types)}'
            ))
            return
        
        try:
            ids = [int(id_str) for id_str in args[1].split(',')]
        except ValueError:
            self.stdout.write(self.style.ERROR('❌ ID lazima ziwe number'))
            return
        
        exams = Exam.objects.filter(id__in=ids)
        
        if not exams.exists():
            self.stdout.write(self.style.ERROR(f'❌ Hakuna exams zilizopatikana kwa IDs: {ids}'))
            return
        
        self.stdout.write(self.style.WARNING(f'\n📊 Ku-update exams {exams.count()} kwenda "{exam_type}":\n'))
        
        for exam in exams:
            self.stdout.write(
                f'  ID {exam.id}: {exam.name} ({exam.exam_type} → {exam_type})'
            )
        
        confirm = input('\n✅ Ili ku-save, andika "yes": ')
        if confirm.lower() != 'yes':
            self.stdout.write(self.style.ERROR('❌ Operation cancelled'))
            return
        
        updated = exams.update(exam_type=exam_type)
        self.stdout.write(self.style.SUCCESS(f'\n✅ Exams {updated} zimesha-update!'))
