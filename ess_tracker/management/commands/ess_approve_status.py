"""Onyesha hali ya kuidhinisha (verify) kwa mkuu — diagnostics.

Inaonyesha kama kipindi cha mchakato (lease: `auto_lease_until`) kimesimama
au bado kinaendelea. Tumia kwenye production (Railway/docker) kuangalia hali
halisi:

    python manage.py ess_approve_status
    python manage.py ess_approve_status --profile 3
    python manage.py ess_approve_status --profile 3 --runs 20

Safu za kila mkuu:
  - muda uliowekwa (wiki) + mwisho wa kipindi
  - run ya mwisho ya kiotomatiki (ikiwa imeshindwa?)
  - kama mfumo bado unaweza kujaza/kuidhinisha kwa kiotomatiki
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
        self._automation_state(now)
        for p in profiles:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'— {p.full_name or p.ess_username} (profile #{p.id}) —'))
            st = tasks.approve_status(p, now=now)
            self.stdout.write(
                f'  approver_enabled={p.approver_enabled} ess_ready={p.ess_ready}'
                f' | muda={st["interval_label"]} ({st["interval_days"]} siku,'
                f' auto_approve_weeks={st["weeks"]})')
            until = st['lease_until']
            if until is None:
                lease_txt = ('hakuna mwisho (kila siku)' if st['weeks'] == 0
                             else 'hauekwisha kuanzishwa')
            else:
                lease_txt = (f'hadi {until:%d %b %Y} '
                             f'({st["lease_days_left"]} siku zimebaki)')
            self.stdout.write(
                f'  kipindi: {lease_txt} | mfumo bado unaweza: '
                f'{"NDIYO" if st["lease_active"] else "HAPANA (kimekwisha!)"}')
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
                % (nxt.strftime('%d %b %Y') if nxt else '— (mfumo umesimama)',
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

    def _automation_state(self, now):
        """Hali ya 'alarm' ya kila siku: kujaza za walimu + kaguzi wa 22:00."""
        import os

        self.stdout.write(self.style.MIGRATE_HEADING('— UJASIRI WA KILA SIKU —'))
        last_fill = EssFillRun.objects.filter(
            kind='fill', source='auto').order_by('-started').first()
        if last_fill is None:
            self.stdout.write('  kujaza kiotomatiki: HAJAENDEKA bado.')
        else:
            self.stdout.write(
                f'  kujaza kiotomatiki ya mwisho: {last_fill.started:%d %b %Y %H:%M} '
                f'(status={last_fill.status})')
        day = now.astimezone(tasks._eat_tz()).date()
        start, end = tasks._eat_day_bounds(day)
        today_fill = EssFillRun.objects.filter(
            kind='fill', source='auto',
            started__gte=start, started__lt=end).count()
        today_appr = EssFillRun.objects.filter(
            kind='approve', source='auto',
            started__gte=start, started__lt=end).count()
        self.stdout.write(
            f'  leo ({day:%d %b %Y}): kujaza={today_fill} run, '
            f'auto-approve={today_appr} run')
        embed_sched = os.environ.get('ESS_EMBED_SCHEDULER', '(automatiki)')
        embed_appr = os.environ.get('ESS_EMBED_APPROVER', '(automatiki)')
        self.stdout.write(
            f'  ESS_EMBED_SCHEDULER={embed_sched} (alarm: kujaza 06:30 EAT) | '
            f'ESS_EMBED_APPROVER={embed_appr} (alarm: verify 22:00 EAT) | '
            f'beat: ess-auto-fill-daily 06:30 + ess-approve-daily 22:00')
        self.stdout.write('  Kumbuka: ndani ya kipindi (lease) mfumo hujaza na '
                         'huidhinisha KILA SIKU; kipindi kikichisha mfumo '
                         'husimama hadi mtumiaji aweke muda upya.')
