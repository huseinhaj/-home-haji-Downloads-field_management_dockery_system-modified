"""
Andaa Halmashauri ya Wilaya ya Kyerwa kwa joint exams:
  - shule 39 (Serikali 32 + Binafsi 7) — kata + umiliki; zinazokosekana zinaundwa
  - (hiari) akaunti ya Afisa Wilaya

    python manage.py setup_kyerwa_district --dry-run
    python manage.py setup_kyerwa_district --officer-email deo@kyerwadc.go.tz --officer-name "Afisa Elimu Sekondari"

Afisa anaingia /shule/login/ kwa email hiyo mara ya kwanza na kuweka password yake.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from results.district_models import schools_in_district
from results.management.kyerwa_schools import DISTRICT, REGION, SCHOOLS
from results.models import School, TeacherAccount


def _norm(name):
    return ' '.join((name or '').lower().replace('secondary school', '').split())


class Command(BaseCommand):
    help = 'Weka shule 39 za Kyerwa (kata + umiliki) na akaunti ya Afisa Wilaya.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Onyesha tu, usibadilishe kitu')
        parser.add_argument('--officer-email', default='')
        parser.add_argument('--officer-name', default='')

    def handle(self, *args, dry_run=False, officer_email='', officer_name='', **kwargs):
        existing = {_norm(s.name): s for s in schools_in_district(DISTRICT, REGION)}
        created = updated = same = 0
        with transaction.atomic(using=School.objects.db):
            for name, ward, ownership in SCHOOLS:
                school = existing.get(_norm(name))
                if school is None:
                    created += 1
                    self.stdout.write(f'  + MPYA  {name} ({ward}, {ownership})')
                    if not dry_run:
                        School.objects.create(
                            name=name, region=REGION, district=DISTRICT,
                            ward=ward, ownership=ownership, level='secondary',
                        )
                    continue
                if school.ward == ward and school.ownership == ownership:
                    same += 1
                    continue
                updated += 1
                self.stdout.write(f'  ~ SASISHA {school.name}: kata={ward}, umiliki={ownership}')
                if not dry_run:
                    school.ward, school.ownership = ward, ownership
                    school.save(update_fields=['ward', 'ownership'])

            listed = {_norm(n) for n, _, _ in SCHOOLS}
            extra = [s.name for k, s in existing.items() if k not in listed]

            if officer_email:
                acct = TeacherAccount.objects.filter(email__iexact=officer_email).first()
                if acct and acct.role != TeacherAccount.ROLE_DISTRICT:
                    self.stderr.write(f'✗ {officer_email} tayari ni {acct.get_role_display()} — sijabadilisha.')
                elif acct:
                    self.stdout.write(f'  = Afisa {officer_email} tayari yupo')
                else:
                    self.stdout.write(f'  + Afisa Wilaya {officer_email}')
                    if not dry_run:
                        acct = TeacherAccount.objects.create_pending(
                            officer_email, full_name=officer_name,
                            role=TeacherAccount.ROLE_DISTRICT,
                        )
                        acct.district, acct.region = DISTRICT, REGION
                        acct.save(update_fields=['district', 'region'])

            if dry_run:
                transaction.set_rollback(True, using=School.objects.db)

        self.stdout.write(self.style.SUCCESS(
            f'{"[DRY RUN] " if dry_run else ""}Shule: {created} mpya, {updated} zimesasishwa, {same} tayari sawa.'
        ))
        if extra:
            self.stdout.write(
                'Shule za Kyerwa zilizopo kwenye mfumo lakini HAZIMO kwenye orodha ya Halmashauri '
                '(hazijaguswa — afisa anaweza kuzichagua au kuziacha kwenye joint):'
            )
            for n in sorted(extra):
                self.stdout.write(f'    - {n}')
