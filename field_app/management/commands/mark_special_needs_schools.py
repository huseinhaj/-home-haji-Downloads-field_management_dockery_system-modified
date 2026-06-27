"""
Management command: mark_special_needs_schools

Weka alama shule zinazotoa elimu maalumu (special_needs_education=True)
na shule zote kama elimu jumuishi (is_inclusive=True).

Matumizi:
    python manage.py mark_special_needs_schools
    python manage.py mark_special_needs_schools --dry-run
"""
from django.core.management.base import BaseCommand
from field_app.models import School


# Maneno yanayoonyesha shule inatoa elimu maalumu
SPECIAL_NEEDS_KEYWORDS = [
    # Kiswahili
    'maalumu', 'viziwi', 'wasioona', 'viwete', 'wasiosikia',
    'albino', 'ulemavu', 'walemavu', 'nguvu maalum',
    # Kiingereza
    'special', 'deaf', 'blind', 'disability', 'disabled',
    'hearing', 'visual impair', 'inclusive unit', 'sped',
    'special need', 'special education',
]

# Shule mahususi Tanzania zinazojulikana kutoa elimu maalumu
# (jina, wilaya/mkoa - kwa utambulisho wa ziada)
KNOWN_SPECIAL_SCHOOLS = [
    # Dar es Salaam
    'Buguruni',
    'Furaha',
    # Dodoma
    'Kisasa',
    # Arusha
    'Ilboru Special',
    # Tabora
    'Buhangija',
    'Tabora Deaf',
    # Tanga / Lushoto
    'Irente',
    # Mwanza
    'Mitindo',
    # Morogoro
    'Mazimbu',
    # Pemba / Zanzibar
    'Fuoni Special',
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

        # Hatua 1: Shule zote → is_inclusive = True (mtaala mpya Tanzania)
        all_schools = School.objects.all()
        total = all_schools.count()
        self.stdout.write(f'Jumla ya shule: {total}')

        if not dry_run:
            updated = School.objects.filter(is_inclusive=False).update(is_inclusive=True)
            self.stdout.write(self.style.SUCCESS(
                f'✓ Shule {updated} zimewekwa is_inclusive=True (zilizobaki tayari zilikuwa True)'
            ))
        else:
            not_inclusive = School.objects.filter(is_inclusive=False).count()
            self.stdout.write(f'[DRY] Shule {not_inclusive} zingehitaji is_inclusive=True')

        # Hatua 2: Tafuta shule za elimu maalumu kwa maneno maalum
        from django.db.models import Q
        keyword_q = Q()
        for kw in SPECIAL_NEEDS_KEYWORDS:
            keyword_q |= Q(name__icontains=kw)

        name_q = Q()
        for name in KNOWN_SPECIAL_SCHOOLS:
            name_q |= Q(name__icontains=name)

        combined_q = keyword_q | name_q
        sn_schools = School.objects.filter(combined_q)
        sn_count = sn_schools.count()

        self.stdout.write(f'\nShule zinazofanana na vigezo vya elimu maalumu: {sn_count}')
        for s in sn_schools.select_related('district__region').order_by('district__region__name', 'name'):
            flag = '' if s.special_needs_education else '[MPYA]'
            self.stdout.write(
                f'  {flag} {s.name} | {s.level} | {s.district.name} | {s.district.region.name}'
            )

        if not dry_run and sn_count > 0:
            updated_sn = sn_schools.update(special_needs_education=True)
            self.stdout.write(self.style.SUCCESS(
                f'\n✓ Shule {updated_sn} zimewekwa special_needs_education=True'
            ))
        elif dry_run:
            self.stdout.write(f'\n[DRY] Shule {sn_count} zingehitaji special_needs_education=True')

        self.stdout.write(self.style.SUCCESS('\n=== Imekamilika ===\n'))
