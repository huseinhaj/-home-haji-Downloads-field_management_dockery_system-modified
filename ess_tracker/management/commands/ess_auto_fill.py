from django.core.management.base import BaseCommand

from ess_tracker import tasks

REASON_SW = {
    'disabled': 'kujaza kiotomatiki kumezimwa (auto_fill_enabled=False)',
    'no-window': 'hakuna dirisha (kalenda/wasifu hauna tarehe za shule)',
    'closed': 'leo iko nje ya dirisha la shule',
    'not-fill-day': 'leo si siku ya kujaza (kwa entries_per_week aliyochagua)',
    'already': 'amejaza tayari leo',
    'locked': 'kuna kujaza kunaendelea (lock)',
}


class Command(BaseCommand):
    help = ('Onyesha walimu wanaotakiwa kujazwa kiotomatiki leo, au endesha '
            'kujaza hicho mara moja (--execute). Hutumia hesabu zile zile za '
            'beat (auto_fill_due).')

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true',
                            help='Endesha kujaza sasa (default: onyesho pekee).')
        parser.add_argument('--inline', action='store_true',
                            help='Kwa --execute: endesha kujaza HUMU ndani (bila '
                                 'worker/beat). Nzuri kwa Railway Cron Job.')
        parser.add_argument('--profile', type=int,
                            help='Profile ID moja pekee (kwa uchunguzi).')

    def handle(self, *args, **opts):
        from ess_tracker.compute import calendar_window
        from ess_tracker.models import TeacherProfile

        today = tasks._today_eat()
        cal_win = calendar_window()
        day_start, day_end = tasks._eat_day_bounds(today)

        qs = TeacherProfile.objects.filter(
            ess_ready=True).select_related('user')
        if not cal_win:
            qs = qs.exclude(school_open=None).exclude(school_close=None)
        if opts['profile']:
            qs = qs.filter(id=opts['profile'])

        if cal_win:
            self.stdout.write(f'Kalenda: {cal_win[0]} → {cal_win[1]}')
        else:
            self.stdout.write('Kalenda: (hakuna — hutumia tarehe za wasifu)')
        self.stdout.write(f'Leo (EAT): {today} ({today.strftime("%A")})')
        self.stdout.write('')

        ready = []
        for prof in qs:
            ready_ok, why = tasks.auto_fill_decision(
                prof, today, cal_win, day_start, day_end)
            name = prof.full_name or prof.user.get_username()
            if ready_ok:
                ready.append(prof)
                self.stdout.write(self.style.SUCCESS(
                    f'TAYARI  #{prof.id} {name}'))
            else:
                self.stdout.write(
                    f'RUKA    #{prof.id} {name} — {REASON_SW.get(why, why)}')

        self.stdout.write('')
        self.stdout.write(f'Walio tayari: {len(ready)}')

        if not opts['execute']:
            self.stdout.write(self.style.WARNING(
                'Hii ni onyesho pekee. Ongeza --execute kujaza kweli.'))
            return
        if not ready:
            return

        if opts['inline']:
            self._run_inline(ready)
            return

        res = tasks.auto_fill_due.apply().get()
        self.stdout.write(self.style.SUCCESS(
            f'Imeanzisha: {res.get("triggered")}'))

    def _run_inline(self, ready):  # noqa: D401
        """Endesha kujaza HUMU ndani (bila broker/worker) kwa kila mwalimu tayari.

        Hutumika na Railway Cron Job: service moja inaendesha amri hii kwa
        ratiba, bila kuhitaji beat/worker/worker_fill.
        """
        from django.utils import timezone

        from ess_tracker.essfill import run_fill
        from ess_tracker.locks import profile_lock
        from ess_tracker.models import EssFillRun
        from ess_tracker.runstate import reap_stale_runs

        reap_stale_runs()
        done = []
        for prof in ready:
            run = EssFillRun.objects.create(
                profile=prof, only_subtasks=tasks._live_only_subtasks(prof),
                source='auto')
            with profile_lock(prof.id) as got:
                if not got:
                    run.status = 'error'
                    run.finished = timezone.now()
                    run.log = 'Lock ilikuwa inashikiliwa; kurukwa.'
                    run.save()
                    self.stdout.write(f'  #{prof.id} — lock, imerukwa')
                    continue
                try:
                    res = run_fill(prof.id, run.id)
                    done.append(prof.id)
                    self.stdout.write(self.style.SUCCESS(
                        f'  #{prof.id} — saved={res.get("saved")} '
                        f'skipped={res.get("skipped")} '
                        f'not_found={res.get("not_found")}'))
                except Exception as exc:  # noqa: BLE001
                    run.status = 'error'
                    run.finished = timezone.now()
                    run.log = (run.log + f'\n{exc}') if run.log else str(exc)
                    run.save()
                    self.stderr.write(f'  #{prof.id} — HITILAFU: {exc}')
        self.stdout.write(self.style.SUCCESS(
            f'Imekamilika (inline): {len(done)}/{len(ready)}'))
