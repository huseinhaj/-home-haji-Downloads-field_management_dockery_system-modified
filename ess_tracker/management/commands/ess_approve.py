"""Idhinisha (verify) maendeleo SUBMITTED ya walimu kwenye ESS.

Mifano:
    python manage.py ess_approve --profile 3            # mkuu mmoja
    python manage.py ess_approve --all                  # wakuu wote waliochaguliwa
    python manage.py ess_approve --all --dry-run        # onyesha tu (bila Verify)
    python manage.py ess_approve --check-number 9812389 # kwa check number
"""
from django.core.management.base import BaseCommand, CommandError

from ess_tracker import essapprove
from ess_tracker.models import EssFillRun, TeacherProfile


class Command(BaseCommand):
    help = ('Idhinisha (verify) maendeleo ya walimu yaliyowasilishwa (SUBMITTED) '
            'kwenye e-Utendaji kwa akaunti za wakuu/kiongozi.')

    def add_arguments(self, parser):
        parser.add_argument('--profile', type=int,
                            help='ID ya TeacherProfile ya mkuu (mkuu mmoja).')
        parser.add_argument('--check-number', dest='check_number',
                            help='ESS check number ya mkuu.')
        parser.add_argument('--all', action='store_true',
                            help='Wakuu wote wenye approver_enabled.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Onyesha tu; usibofye Verify.')

    def handle(self, *args, **opts):
        profiles = self._profiles(opts)
        if not profiles:
            raise CommandError(
                'Hakuna wasifu. Tumia --profile, --check-number au --all '
                '(na uhakikishe approver_enabled imewashwa).')
        dry = opts['dry_run']
        totals = {'verified': 0, 'processed': 0, 'failed': 0, 'profiles': 0}
        for p in profiles:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'— {p.full_name or p.ess_username} (profile #{p.id}) —'))
            if not p.ess_ready:
                self.stdout.write(self.style.WARNING(
                    '  hana ESS username/password — nairuka.'))
                continue
            run = EssFillRun.objects.create(
                profile=p, kind='approve', source='manual')
            res = essapprove.run_approve(p.id, run.id, dry_run=dry)
            totals['profiles'] += 1
            totals['verified'] += res.get('verified', 0)
            totals['processed'] += res.get('processed', 0)
            totals['failed'] += res.get('failed', 0)
            style = (self.style.SUCCESS if res.get('status') == 'done'
                     else self.style.ERROR)
            self.stdout.write(style(
                f'  {res.get("status")}: verified={res.get("verified", 0)} '
                f'processed={res.get("processed", 0)} '
                f'failed={res.get("failed", 0)}'
                + (f' msg={res.get("msg")}' if res.get('msg') else '')))
        self.stdout.write(self.style.SUCCESS(
            f'JUMLA: wakuu={totals["profiles"]} verified={totals["verified"]} '
            f'processed={totals["processed"]} failed={totals["failed"]}'
            + (' [DRY-RUN]' if dry else '')))

    def _profiles(self, opts):
        qs = TeacherProfile.objects.select_related('user')
        if opts['profile']:
            return list(qs.filter(pk=opts['profile']))
        if opts['check_number']:
            return list(qs.filter(ess_username=str(opts['check_number'])))
        if opts['all']:
            return list(qs.filter(approver_enabled=True))
        return []
