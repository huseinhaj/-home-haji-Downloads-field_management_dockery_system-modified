"""
Management command: backup_db
Usage: python manage.py backup_db [--output /path/to/file.json]

Exports all critical IMS data as a JSON fixture that can be re-imported
with: python manage.py loaddata <file>
"""
import json
import os
from datetime import datetime
from django.core.management.base import BaseCommand
from django.core import serializers
from django.conf import settings


BACKUP_MODELS = [
    'field_app.StudentTeacher',
    'field_app.School',
    'field_app.District',
    'field_app.Region',
    'field_app.Subject',
    'field_app.StudentApplication',
    'field_app.LogbookEntry',
    'field_app.SchemeOfWork',
    'field_app.LessonPlan',
    'field_app.Assessor',
    'field_app.SchoolAssessment',
    'field_app.AcademicYear',
    'field_app.BoardMember',
    'field_app.BoardComment',
    'field_app.MonthlyReport',
]


class Command(BaseCommand):
    help = 'Export IMS data to a JSON backup file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output', '-o',
            type=str,
            default=None,
            help='Output file path (default: backups/ims_backup_YYYYMMDD_HHMMSS.json)',
        )

    def handle(self, *args, **options):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        output_path = options['output']
        if not output_path:
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            output_path = os.path.join(backup_dir, f'ims_backup_{timestamp}.json')

        self.stdout.write(self.style.NOTICE(f'Starting IMS backup → {output_path}'))

        all_objects = []
        stats = {}

        for model_label in BACKUP_MODELS:
            app_label, model_name = model_label.split('.')
            try:
                from django.apps import apps
                model = apps.get_model(app_label, model_name)
                qs = model.objects.all()
                count = qs.count()
                stats[model_label] = count
                if count > 0:
                    data = json.loads(serializers.serialize('json', qs))
                    all_objects.extend(data)
                    self.stdout.write(f'  ✓ {model_label}: {count} records')
                else:
                    self.stdout.write(f'  · {model_label}: 0 records (skipped)')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  ✗ {model_label}: {e}'))

        # Write backup file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(all_objects, f, ensure_ascii=False, indent=2, default=str)

        total = sum(stats.values())
        size_kb = os.path.getsize(output_path) // 1024

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Backup complete: {total} records, {size_kb} KB → {output_path}'
        ))
        self.stdout.write(
            f'Restore with: python manage.py loaddata {output_path}'
        )
        return output_path
