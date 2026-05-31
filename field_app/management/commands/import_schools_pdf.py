"""
Management command: import_schools_pdf
Inasasisha school_code kwenye database kutoka data ya NECTA (shule 6,230).

Matumizi:
    python manage.py import_schools_pdf               # import (default)
    python manage.py import_schools_pdf --dry-run     # angalia bila kuhifadhi
    python manage.py import_schools_pdf --overwrite   # badilisha hata kama tayari ipo
"""

import re
import csv
import difflib
import os
from django.core.management.base import BaseCommand
from field_app.models import School


def _norm(name: str) -> str:
    name = name.upper().strip()
    for w in ['SECONDARY SCHOOL', 'SECONDARY', 'SEC SCHOOL', 'SEC.',
              ' SS', ' S/S', ' DAY', ' MIXED', ' GIRLS', ' BOYS',
              ' COMMUNITY', " CENTRE", " CENTER"]:
        name = name.replace(w, '')
    name = re.sub(r"'", '', name)
    name = re.sub(r'[^A-Z0-9 ]', ' ', name)
    return re.sub(r'\s+', ' ', name).strip()


def _match(necta_norm: str, db_schools, threshold=0.85) -> School | None:
    # Toa kipaumbele kwa sekondari
    sec = [s for s in db_schools if s['obj'].level == 'Secondary'] or db_schools
    names_map = {s['norm']: s['obj'] for s in sec}

    if necta_norm in names_map:
        return names_map[necta_norm]

    hits = difflib.get_close_matches(necta_norm, names_map.keys(), n=1, cutoff=threshold)
    if hits:
        return names_map[hits[0]]
    return None


class Command(BaseCommand):
    help = 'Ingiza school_code kutoka data ya NECTA (necta_schools_2025.csv)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--overwrite', action='store_true')
        # backward compat
        parser.add_argument('--pdf', default='')
        parser.add_argument('--skip-if-done', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        overwrite = options['overwrite']

        if options.get('skip_if_done'):
            done = School.objects.exclude(school_code='').count()
            if done > 100:
                self.stdout.write(f"Tayari shule {done} zina school_code — import inaachwa.")
                return

        csv_path = os.path.normpath(os.path.join(
            os.path.dirname(__file__), '..', '..', '..', 'data', 'necta_schools_2025.csv'
        ))
        if not os.path.exists(csv_path):
            self.stderr.write(self.style.ERROR(f"Faili haikupatikana: {csv_path}"))
            return

        self.stdout.write(f"Inasoma: {csv_path}")

        necta_rows = []
        with open(csv_path, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                code = row['code'].strip()
                name = row['name'].strip()
                if code and name:
                    necta_rows.append({'code': code, 'name': name, 'norm': _norm(name)})

        self.stdout.write(f"Rekodi kwenye NECTA: {len(necta_rows)}")

        db_schools = [{
            'obj': s,
            'norm': _norm(s.name),
        } for s in School.objects.all()]

        self.stdout.write(f"Shule kwenye database: {len(db_schools)}")

        updated = skipped_no_match = skipped_exists = 0

        for r in necta_rows:
            school = _match(r['norm'], db_schools)
            if not school:
                skipped_no_match += 1
                continue

            if overwrite or not school.school_code:
                if school.school_code != r['code']:
                    school.school_code = r['code']
                    if not dry_run:
                        school.save(update_fields=['school_code'])
                    updated += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  {'[DRY] ' if dry_run else ''}{school.name} → {school.school_code}"
                        )
                    )
            else:
                skipped_exists += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Zilizosasishwa: {updated}"))
        self.stdout.write(self.style.WARNING(f"Hazikupatikana: {skipped_no_match}"))
        self.stdout.write(f"Zilizopita (tayari zina data): {skipped_exists}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — hakuna kilichohifadhiwa"))
