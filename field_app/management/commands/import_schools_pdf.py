"""
Management command: import_schools_pdf
Inasasisha school_code na head_phone kwa kila shule kwenye database
kutoka kwa data iliyotolewa kwenye PDF ya "NAMBA ZA SIMU WAKUU WA SHULE TZ.pdf".

Matumizi:
    python manage.py import_schools_pdf                  # soma JSON iliyopo kwenye data/
    python manage.py import_schools_pdf --dry-run        # angalia bila kuhifadhi
    python manage.py import_schools_pdf --overwrite      # badilisha hata kama tayari ipo
    python manage.py import_schools_pdf --pdf /path.pdf  # soma PDF moja kwa moja
"""

import re
import json
import difflib
import os
from django.core.management.base import BaseCommand
from field_app.models import School


def _normalise(name: str) -> str:
    name = name.upper().strip()
    for word in ['SECONDARY SCHOOL', 'SECONDARY', 'SEC SCHOOL', 'SEC.', ' SS', ' S/S']:
        name = name.replace(word, '')
    name = re.sub(r'[^A-Z0-9 ]', ' ', name)
    return re.sub(r'\s+', ' ', name).strip()


def _match_school(pdf_name: str, pdf_district: str, db_schools) -> School | None:
    norm_pdf = _normalise(pdf_name)
    district_schools = [
        s for s in db_schools
        if _normalise(s.district.name) in pdf_district.upper()
        or pdf_district.upper() in _normalise(s.district.name)
    ]
    pool = district_schools if district_schools else db_schools
    names_map = {_normalise(s.name): s for s in pool}

    if norm_pdf in names_map:
        return names_map[norm_pdf]

    matches = difflib.get_close_matches(norm_pdf, names_map.keys(), n=1, cutoff=0.75)
    if matches:
        return names_map[matches[0]]
    return None


def _extract_from_pdf(pdf_path: str) -> list:
    import pdfplumber
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if not row or len(row) < 9:
                        continue
                    row = [str(c).strip() if c else '' for c in row]
                    if any(h in row[0].upper() for h in ['COUNCIL', 'REGION', 'WARD']):
                        continue
                    council = row[0]
                    school_name = row[2]
                    reg_number = row[4]
                    phone = row[9] if len(row) > 9 else (row[8] if len(row) > 8 else '')
                    if not school_name or not reg_number:
                        continue
                    if not reg_number.upper().startswith('S.'):
                        continue
                    phone = re.sub(r'[^0-9+]', '', phone)
                    if phone.startswith('255') and len(phone) == 12:
                        phone = '0' + phone[3:]
                    elif phone.startswith('+255') and len(phone) == 13:
                        phone = '0' + phone[4:]
                    rows.append({
                        'council': council,
                        'name': school_name,
                        'code': reg_number.upper().strip(),
                        'phone': phone,
                    })
    return rows


class Command(BaseCommand):
    help = 'Ingiza school_code na head_phone kutoka data ya wakuu wa shule'

    def add_arguments(self, parser):
        parser.add_argument('--pdf', default='', help='Path ya PDF (optional)')
        parser.add_argument('--dry-run', action='store_true', help='Angalia bila kuhifadhi')
        parser.add_argument('--overwrite', action='store_true', help='Badilisha hata kama tayari ipo')
        parser.add_argument('--skip-if-done', action='store_true', help='Acha kama shule nyingi tayari zina school_code')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        overwrite = options['overwrite']
        pdf_path = options['pdf']
        skip_if_done = options['skip_if_done']

        if skip_if_done:
            done_count = School.objects.exclude(school_code='').count()
            if done_count > 100:
                self.stdout.write(f"Tayari shule {done_count} zina school_code — import inaachwa.")
                return

        # Amua chanzo cha data
        if pdf_path and os.path.exists(pdf_path):
            self.stdout.write(f"Inasoma PDF: {pdf_path}")
            rows = _extract_from_pdf(pdf_path)
        else:
            json_path = os.path.join(
                os.path.dirname(__file__), '..', '..', '..', 'data', 'schools_import.json'
            )
            json_path = os.path.normpath(json_path)
            if not os.path.exists(json_path):
                self.stderr.write(self.style.ERROR(f"Faili haikupatikana: {json_path}"))
                return
            self.stdout.write(f"Inasoma JSON: {json_path}")
            with open(json_path) as f:
                rows = json.load(f)

        self.stdout.write(f"Rekodi kwenye faili: {len(rows)}")

        db_schools = list(School.objects.select_related('district', 'district__region').all())
        self.stdout.write(f"Shule kwenye database: {len(db_schools)}")

        updated = skipped_no_match = skipped_exists = 0

        for r in rows:
            school = _match_school(r['name'], r['council'], db_schools)
            if not school:
                self.stdout.write(self.style.WARNING(f"  Haikupatikana: {r['name']} ({r['council']})"))
                skipped_no_match += 1
                continue

            changed = False

            if overwrite or not school.school_code:
                if school.school_code != r['code']:
                    school.school_code = r['code']
                    changed = True
            else:
                skipped_exists += 1

            if overwrite or not school.head_phone:
                if r['phone'] and school.head_phone != r['phone']:
                    school.head_phone = r['phone']
                    changed = True

            if changed:
                if not dry_run:
                    school.save(update_fields=['school_code', 'head_phone'])
                updated += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {'[DRY] ' if dry_run else ''}{school.name} → {school.school_code} / {school.head_phone}"
                    )
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Zilizosasishwa: {updated}"))
        self.stdout.write(self.style.WARNING(f"Hazikupatikana: {skipped_no_match}"))
        self.stdout.write(f"Zilizopita (tayari zina data): {skipped_exists}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — hakuna kilichohifadhiwa"))
