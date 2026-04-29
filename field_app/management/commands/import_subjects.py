import csv
from django.core.management.base import BaseCommand
from field_app.models import Subject

class Command(BaseCommand):
    help = 'Import subjects from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Path to the CSV file containing subjects'
        )

    def handle(self, *args, **kwargs):
        csv_file_path = kwargs['csv_file']

        try:
            with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                created_count = 0
                for row in reader:
                    name = row['name'].strip()
                    code = row['code'].strip().upper()
                    level = row['level'].strip().lower()

                    if level not in ['primary', 'secondary']:
                        self.stdout.write(self.style.WARNING(f"⚠️  Invalid level: {level}, skipping {name}"))
                        continue

                    subject, created = Subject.objects.get_or_create(
                        code=code,
                        defaults={'name': name, 'level': level}
                    )
                    if created:
                        created_count += 1
                        self.stdout.write(self.style.SUCCESS(f"✅ Created subject: {name} ({code})"))
                    else:
                        self.stdout.write(f"ℹ️  Skipped existing subject: {name} ({code})")

            self.stdout.write(self.style.SUCCESS(f"\n🎉 Import complete. {created_count} subjects created."))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"❌ File not found: {csv_file_path}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ An error occurred: {str(e)}"))

