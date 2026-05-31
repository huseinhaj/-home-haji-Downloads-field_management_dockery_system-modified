"""
Management command: import_schools_pdf
Inasasisha school_code kwenye database kutoka CSV ya shule za sekondari.

Matumizi:
    python manage.py import_schools_pdf               # import CSV (default)
    python manage.py import_schools_pdf --dry-run     # angalia bila kuhifadhi
    python manage.py import_schools_pdf --overwrite   # badilisha hata kama tayari ipo
    python manage.py import_schools_pdf --skip-if-done
"""

import re
import csv
import difflib
import os
from django.core.management.base import BaseCommand
from field_app.models import School


def _norm_name(name: str) -> str:
    name = name.upper().strip()
    for w in ['SECONDARY SCHOOL', 'SECONDARY', 'SEC SCHOOL', 'SEC.',
              ' SS', ' S/S', ' DAY', ' MIXED', ' GIRLS', ' BOYS', ' COMMUNITY']:
        name = name.replace(w, '')
    name = re.sub(r'[^A-Z0-9 ]', ' ', name)
    return re.sub(r'\s+', ' ', name).strip()


def _norm_district(name: str) -> str:
    name = name.upper().strip()
    for suf in [' DISTRICT COUNCIL', ' DISTRICT', ' MUNICIPAL COUNCIL',
                ' MUNICIPALITY', ' TOWN COUNCIL', ' CITY COUNCIL',
                ' DC', ' TC', ' MC', ' CC']:
        if name.endswith(suf):
            name = name[:-len(suf)].strip()
    return name


def _match(csv_name_norm: str, csv_district_norm: str, db_schools, threshold=0.85) -> School | None:
    pool = [s for s in db_schools
            if csv_district_norm in s['dist_norm'] or s['dist_norm'] in csv_district_norm]
    if not pool:
        pool = db_schools

    names_map = {s['name_norm']: s['obj'] for s in pool}

    if csv_name_norm in names_map:
        return names_map[csv_name_norm]

    hits = difflib.get_close_matches(csv_name_norm, names_map.keys(), n=1, cutoff=threshold)
    if hits:
        return names_map[hits[0]]
    return None


class Command(BaseCommand):
    help = 'Ingiza school_code kutoka CSV ya shule za sekondari'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--overwrite', action='store_true')
        parser.add_argument('--skip-if-done', action='store_true',
                            help='Acha kama shule >100 tayari zina school_code')
        # backward compat — bado inakubali --pdf lakini haitumiwi
        parser.add_argument('--pdf', default='')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        overwrite = options['overwrite']

        if options['skip_if_done']:
            done = School.objects.exclude(school_code='').count()
            if done > 100:
                self.stdout.write(f"Tayari shule {done} zina school_code — import inaachwa.")
                return

        csv_path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', 'data',
            'School_CG_Secondary_2022-2023.csv'
        )
        csv_path = os.path.normpath(csv_path)
        if not os.path.exists(csv_path):
            self.stderr.write(self.style.ERROR(f"CSV haikupatikana: {csv_path}"))
            return

        self.stdout.write(f"Inasoma: {csv_path}")

        csv_rows = []
        with open(csv_path, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                reg = row.get('Reg#', '').strip().upper()
                name = row.get('SCHOOL NAME', '').strip()
                council = _norm_district(row.get('COUNCIL', '').strip())
                if reg.startswith('S.') and name:
                    csv_rows.append({
                        'name': name,
                        'name_norm': _norm_name(name),
                        'council': council,
                        'code': reg,
                    })

        self.stdout.write(f"Rekodi kwenye CSV: {len(csv_rows)}")

        db_schools_qs = School.objects.select_related('district').all()
        db_schools = [{
            'obj': s,
            'name_norm': _norm_name(s.name),
            'dist_norm': _norm_district(s.district.name),
        } for s in db_schools_qs]

        self.stdout.write(f"Shule kwenye database: {len(db_schools)}")

        updated = skipped_no_match = skipped_exists = 0

        for r in csv_rows:
            school = _match(r['name_norm'], r['council'], db_schools)
            if not school:
                self.stdout.write(self.style.WARNING(f"  Haikupatikana: {r['name']} ({r['council']})"))
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
