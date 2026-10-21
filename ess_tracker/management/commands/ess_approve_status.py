"""Onyesha hali ya kuidhinisha (verify) kwa mkuu — diagnostics.

Inaonyesha kama kipindi cha auto-approve (`auto_approve_weeks`) inashikiliwaji
au la. Tumia kwenye production (Railway/docker) kuangalia hali halisi:

    python manage.py ess_approve_status
    python manage.py ess_approve_status --profile 3
    python manage.py ess_approve_status --profile 3 --runs 20

Safu za kila mkuu:
  - kipindi kilichowekwa + kwa siku ngapi
  - run ya mwisho ya kiotomatiki (ikiwa imeshindwa?)
  - tarehe inayofuata ya auto-approve
  - historia ya hivi karibuni ya approve (kiotomatiki au mkono)
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ess_tracker import tasks
from ess_tracker.models import EssFillRun, TeacherProfile


class Command(BaseCommand):
    help = ('Onyesha hali ya kuidhinisha (verify) kwa kila mkuu: kipindi, '
            'run ya mwisho ya kiotomatiki, tarehe inayofuata na historia ya '
            'hivi karibuni.')

    def add_arguments(self, parser):
        parser.add_argument('--profile', type=int,
                            help='ID ya TeacherProfile ya mkuu (moja).')
        parser.add_argument('--check-number', dest='check_number',
                            help='ESS check number ya mkuu.')
        parser.add_argument('--all', action='store_true',
                            help='Wakuu wote (wao wana approver_enabled).')
        parser.add_argument('--runs', type=int, default=10,
                            help='Idadi ya run za mwisho kuonyesha (default 10).')

    def handle(self, *args, **opts):
        profiles = self._profiles(opts)
        if not profiles:
            raise CommandError(
                'Hakuna wasifu. Tumia --profile, --check-number au --all.')
        now = timezone.now()
        for p in profiles:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'— {p.full_name or p.ess_username} (profile #{p.id}) —'))
            st = tasks.approve_status(p, now=now)
            self.stdout.write(
                f'  approver_enabled={p.approver_enabled} ess_ready={p.ess_ready}'
                f' | kipindi={st["interval_label"]} ({st["interval_days"]} siku,'
                f' auto_approve_weeks={st["weeks"]})')
            last = st['last_auto']
            if last is None:
                self.stdout.write('  auto-approve: HAJAENDESHWA bado '
                                  '(hujawahi kufanyika) — inafanyika mara '
                                  'moja kwanza.')
            else:
                self.stdout.write(
                    f'  auto-approve ya mwisho: {last.started:%d %b %Y %H:%M} '
                    f'status={last.status} verified={last.saved}')
            if st['last_failed'] is not None:
                self.stdout.write(self.style.WARNING(
                    f'  ! auto-approve iliyoshindwa: '
                    f'{st["last_failed"].started:%d %b %Y %H:%M} '
                    f'status={st["last_failed"].status}'))
            nxt = st['next_due']
            self.stdout.write(
                '  ijayo: %s | inafaa kwa sasa: %s'
                % (nxt.strftime('%d %b %Y') if nxt else '— (hakijawahi kuendeshwa)',
                   'NDIYO' if st['due'] else 'HAPANA'))
            runs = list(EssFillRun.objects.filter(
                profile=p, kind='approve').order_by('-started')[:opts['runs']])
            if not runs:
                self.stdout.write('  hakuna run ya approve bado.')
            for r in runs:
                self.stdout.write(
                    f'    #{r.id} {r.started:%d %b %Y %H:%M} '
                    f'source={r.source} status={r.status} verified={r.saved}')

    def _profiles(self, opts):
        qs = TeacherProfile.objects.select_related('user')
        if opts['profile']:
            return list(qs.filter(pk=opts['profile']))
        if opts['check_number']:
            return list(qs.filter(ess_username=str(opts['check_number'])))
        if opts['all']:
            return list(qs.filter(approver_enabled=True))
        return list(qs.filter(approver_enabled=True))
