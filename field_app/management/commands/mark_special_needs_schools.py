"""
Management command: mark_special_needs_schools

Weka alama shule zinazotoa elimu maalumu (special_needs_education=True)
na shule zote kama elimu jumuishi (is_inclusive=True).

Matumizi:
    python manage.py mark_special_needs_schools
    python manage.py mark_special_needs_schools --dry-run
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from field_app.models import School


# Maneno yanayoonyesha WAZI kwamba shule inatoa elimu maalumu
# (lazima yawe kwenye jina la shule yenyewe)
SPECIAL_NEEDS_KEYWORDS = [
    # Kiswahili
    'viziwi', 'wasioona', 'walemavu', 'viwete', 'wasiosikia',
    'maalumu', 'albino', 'ulemavu',
    # Kiingereza
    'blind', 'deaf', 'disabled', 'disability',
    'special need', 'special education', 'sped',
    'hearing impair', 'visual impair',
]

# Shule mahususi zinazojulikana Tanzania — zinatambulishwa kwa JINA + WILAYA
# ili kuepuka false positives (e.g. "Furaha" ni jina la kawaida)
KNOWN_SPECIAL_SCHOOLS_BY_DISTRICT = [
    # (jina_icontains, district_name_icontains)
    ('Irente',   'Lushoto'),    # Irente School for the Blind Girls — Tanga
    ('Mitindo',  'Misungwi'),   # Mitindo Primary (Deaf) — Mwanza
    ('Buhangija','Shinyanga'),  # Buhangija Special Needs Centre — Shinyanga
]


class Command(BaseCommand):
    help = 'Weka alama shule zinazotoa elimu maalumu na elimu jumuishi Tanzania'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Onyesha tu bila kubadilisha database'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verb = 'DRY-RUN' if dry_run else 'KUTEKELEZA'
        self.stdout.write(f'\n=== {verb}: Kuweka alama shule za elimu maalumu ===\n')

        # Hatua 1: Shule zote → is_inclusive = True (mtaala mpya Tanzania 2021–2026)
        total = School.objects.count()
        self.stdout.write(f'Jumla ya shule: {total}')

        if not dry_run:
            updated = School.objects.filter(is_inclusive=False).update(is_inclusive=True)
            self.stdout.write(self.style.SUCCESS(
                f'✓ Shule {updated} zimewekwa is_inclusive=True'
            ))
        else:
            self.stdout.write(f'[DRY] Shule {School.objects.filter(is_inclusive=False).count()} zingehitaji is_inclusive=True')

        # Hatua 2: Keyword matching — maneno dhahiri kwenye jina la shule
        keyword_q = Q()
        for kw in SPECIAL_NEEDS_KEYWORDS:
            keyword_q |= Q(name__icontains=kw)

        # Hatua 3: District-aware matching — shule zinazojulikana bila keyword
        district_q = Q()
        for school_name, district_name in KNOWN_SPECIAL_SCHOOLS_BY_DISTRICT:
            district_q |= Q(
                name__icontains=school_name,
                district__name__icontains=district_name
            )

        sn_schools = School.objects.filter(keyword_q | district_q).select_related('district__region')
        sn_count = sn_schools.count()

        self.stdout.write(f'\nShule za elimu maalumu zilizopatikana: {sn_count}')
        for s in sn_schools.order_by('district__region__name', 'name'):
            tag = '' if s.special_needs_education else '[MPYA]'
            self.stdout.write(
                f'  {tag} {s.name} | {s.level} | {s.district.name} | {s.district.region.name}'
            )

        if not dry_run and sn_count > 0:
            updated_sn = sn_schools.update(special_needs_education=True)
            self.stdout.write(self.style.SUCCESS(
                f'\n✓ Shule {updated_sn} zimewekwa special_needs_education=True'
            ))
        elif dry_run:
            self.stdout.write(f'\n[DRY] Shule {sn_count} zingehitaji special_needs_education=True')

        self.stdout.write(self.style.SUCCESS('\n=== Imekamilika ===\n'))
