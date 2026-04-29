from django.core.management.base import BaseCommand
from field_app.models import Region, District, School
import csv
import os

class Command(BaseCommand):
    help = 'Import schools from CSV, creating regions and districts if missing'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')
        parser.add_argument('school_type', type=str, choices=['primary', 'secondary'], help='Type of school')

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']
        school_type = kwargs['school_type'].capitalize()  # Primary or Secondary

        if not os.path.exists(csv_file):
            self.stdout.write(self.style.ERROR(f"❌ File not found: {csv_file}"))
            return

        schools_to_create = []
        created_schools_keys = set()
        skipped = 0
        created = 0

        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for i, row in enumerate(reader, start=1):
                region_name = row.get('REGION', '').strip().title()
                district_name = row.get('COUNCIL', '').strip().title()
                school_name = row.get('SCHOOL NAME', '').strip().title()

                if not (region_name and district_name and school_name):
                    self.stdout.write(self.style.WARNING(f"⚠️ Skipping incomplete row: {row}"))
                    skipped += 1
                    continue

                # Create or get Region
                region, created_region = Region.objects.get_or_create(name__iexact=region_name, defaults={'name': region_name})

                # Create or get District (Council) linked to region
                district, created_district = District.objects.get_or_create(
                    name__iexact=district_name,
                    region=region,
                    defaults={'name': district_name, 'region': region}
                )

                school_key = (school_name.lower(), district.id, school_type)

                if school_key in created_schools_keys:
                    continue  # already added in this session

                if School.objects.filter(name__iexact=school_name, district=district, level=school_type).exists():
                    skipped += 1
                    continue

                created_schools_keys.add(school_key)

                school = School(
                    name=school_name,
                    district=district,
                    level=school_type
                )
                schools_to_create.append(school)
                created += 1

                if i % 100 == 0:
                    self.stdout.write(f"⏳ Processed {i} rows...")

        if schools_to_create:
            School.objects.bulk_create(schools_to_create)

        self.stdout.write(self.style.SUCCESS(f"\n✅ Done. {created} schools imported. {skipped} rows skipped."))

