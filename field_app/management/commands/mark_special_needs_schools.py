"""
Management command: mark_special_needs_schools

1. Weka is_inclusive=True kwa shule ZOTE (mtaala mpya Tanzania 2021–2026)
2. Weka special_needs_education=True kwa shule zinazotoa elimu maalumu
3. Ongeza shule mpya kutoka CSV kama hazipatikani kwenye DB

Matumizi:
    python manage.py mark_special_needs_schools
    python manage.py mark_special_needs_schools --dry-run
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from field_app.models import School, District


SPECIAL_NEEDS_KEYWORDS = [
    # Kiswahili
    'viziwi', 'wasioona', 'walemavu', 'viwete', 'wasiosikia',
    'maalum',   # inashika "maalumu" NA "maalum"
    'albino', 'ulemavu',
    # Kiingereza
    'blind', 'deaf', 'disabled', 'disability',
    'special need', 'special education', 'sped',
    'hearing impair', 'visual impair',
]

# Shule zinazojulikana — zinatambulishwa kwa JINA + WILAYA (epuka false positives)
KNOWN_SPECIAL_SCHOOLS_BY_DISTRICT = [
    # (jina_icontains, district_name_icontains)
    ('Irente',    'Lushoto'),    # Irente School for the Blind Girls — Tanga
    ('Mitindo',   'Misungwi'),   # Mitindo Primary (Deaf) — Mwanza
    ('Buhangija', 'Shinyanga'),  # Buhangija Special Needs Centre — Shinyanga
    ('Buigiri',   'Chamwino'),   # Buigiri Special Needs — Dodoma
]

# Shule za CSV ambazo HAZIPO kwenye database — zinaongezwa mara moja
# (jina, district_name_icontains, level, ownership)
CSV_NEW_SCHOOLS = [
    ('Step by Step Learning Center',              'Arusha Cc',    'Primary',   'private'),
    ('Al Muntazir Special Education Needs School','Ilala',        'Primary',   'private'),
    ('Crown Secondary School',                    'Kinondoni',    'Secondary', 'private'),
    ('Kids Manual Skills Development Center',     'Ilala',        'Primary',   'private'),
    ('Josephian Schools Mbezi Beach',             'Kinondoni',    'Primary',   'private'),
    ('Faraja Home Special Needs School',          'Moshi Mc',     'Primary',   'private'),
    ('Visualization Pedagogy Global Learning',    'Tabora Mc',    'Primary',   'private'),
]


class Command(BaseCommand):
    help = 'Weka alama shule za elimu maalumu na ongeza shule mpya za CSV'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Onyesha tu bila kubadilisha database'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verb = 'DRY-RUN' if dry_run else 'KUTEKELEZA'
        self.stdout.write(f'\n=== {verb}: Shule za Elimu Maalumu ===\n')

        # ── Hatua 1: Shule zote → is_inclusive = True ──────────────────────
        total = School.objects.count()
        self.stdout.write(f'Jumla ya shule: {total}')
        if not dry_run:
            n = School.objects.filter(is_inclusive=False).update(is_inclusive=True)
            self.stdout.write(self.style.SUCCESS(f'✓ is_inclusive=True kwa shule {n} (zilizobaki tayari True)'))
        else:
            self.stdout.write(f'[DRY] {School.objects.filter(is_inclusive=False).count()} zingehitaji is_inclusive=True')

        # ── Hatua 2: Keyword + district-aware matching ──────────────────────
        kw_q = Q()
        for kw in SPECIAL_NEEDS_KEYWORDS:
            kw_q |= Q(name__icontains=kw)

        dist_q = Q()
        for sname, dname in KNOWN_SPECIAL_SCHOOLS_BY_DISTRICT:
            dist_q |= Q(name__icontains=sname, district__name__icontains=dname)

        sn_qs = School.objects.filter(kw_q | dist_q).select_related('district__region')
        sn_count = sn_qs.count()

        self.stdout.write(f'\nShule zilizopatikana (keyword/known): {sn_count}')
        for s in sn_qs.order_by('district__region__name', 'name'):
            tag = '     ' if s.special_needs_education else '[MPYA]'
            self.stdout.write(f'  {tag} {s.name} | {s.level} | {s.district.name} | {s.district.region.name}')

        if not dry_run and sn_count > 0:
            updated = sn_qs.update(special_needs_education=True)
            self.stdout.write(self.style.SUCCESS(f'\n✓ special_needs_education=True kwa shule {updated}'))
        elif dry_run:
            self.stdout.write(f'\n[DRY] {sn_count} zingehitaji special_needs_education=True')

        # ── Hatua 3: Ongeza shule mpya kutoka CSV ──────────────────────────
        self.stdout.write('\nKuongeza shule mpya kutoka CSV:')
        added = 0
        for school_name, district_kw, level, ownership in CSV_NEW_SCHOOLS:
            # Angalia kama ipo tayari
            exists = School.objects.filter(name__iexact=school_name).exists()
            if exists:
                self.stdout.write(f'  [TAYARI IPO] {school_name}')
                # Weka alama ya special needs kama haijawekwa
                if not dry_run:
                    School.objects.filter(name__iexact=school_name).update(
                        special_needs_education=True, is_inclusive=True
                    )
                continue

            # Tafuta wilaya
            district = District.objects.filter(name__icontains=district_kw).first()
            if not district:
                self.stdout.write(self.style.WARNING(f'  [WILAYA HAIPO] {school_name} — {district_kw}'))
                continue

            if not dry_run:
                school = School.objects.create(
                    name=school_name,
                    district=district,
                    level=level,
                    ownership=ownership,
                    capacity=10,
                    special_needs_education=True,
                    is_inclusive=True,
                )
                self.stdout.write(self.style.SUCCESS(
                    f'  [IMEONGEZWA] {school.name} | {level} | {district.name} | {district.region.name}'
                ))
                added += 1
            else:
                self.stdout.write(
                    f'  [DRY-ONGEZA] {school_name} | {level} | {district.name} | {district.region.name}'
                )

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f'\n✓ Shule mpya {added} zimeongezwa'))

        self.stdout.write(self.style.SUCCESS('\n=== Imekamilika ===\n'))
