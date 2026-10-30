import time as _time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ess_tracker import tasks


class Command(BaseCommand):
    help = ('Kiendesha kujaza kiotomatiki ESS kila siku 06:30 EAT — HUMU ndani '
            '(bila celery beat/worker). Hupachikwa kwenye container ya web '
            '(Railway) kwa background, ili service moja ijaze kiotomatiki.')

    def add_arguments(self, parser):
        parser.add_argument('--hour', type=int, default=6,
                            help='Saa ya EAT (default 6).')
        parser.add_argument('--minute', type=int, default=30,
                            help='Dakika (default 30).')
        parser.add_argument('--sync-hour', type=int, default=5,
                            help='Saa ya EAT ya kusawazisha majina (default 5).')
        parser.add_argument('--sync-minute', type=int, default=45,
                            help='Dakika ya kusawazisha majina (default 45).')
        parser.add_argument('--once', action='store_true',
                            help='Endesha mara moja sasa kisha toka.')
        parser.add_argument('--catch-up', action='store_true',
                            help='Kwenye kuanza: kama saa ya leo imepita na '
                                 'hakuna auto-run leo, endesha mara moja.')

    def handle(self, *args, **opts):
        self.hour = opts['hour']
        self.minute = opts['minute']
        self.sync_hour = opts['sync_hour']
        self.sync_minute = opts['sync_minute']
        self.stdout.write(self.style.SUCCESS(
            f'[ess-scheduler] imeanza — kila siku {self.hour:02d}:'
            f'{self.minute:02d} EAT (jazo), {self.sync_hour:02d}:'
            f'{self.sync_minute:02d} EAT (majina)'))

        if opts['once']:
            self._run_once()
            return

        if opts['catch_up']:
            try:
                if self._should_catch_up():
                    self.stdout.write(
                        '[ess-scheduler] catch-up: leo haijajazwa — inaendesha.')
                    self._run_once()
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f'[ess-scheduler] catch-up error: {exc}')

        while True:
            kind, secs = self._seconds_until_next()
            self.stdout.write(
                f'[ess-scheduler] {kind} ijayo baada ya {secs / 3600:.2f} h')
            self._sleep(secs)
            try:
                if kind == 'sync':
                    self._run_sync_once()
                else:
                    self._run_once()
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f'[ess-scheduler] error: {exc}')

    def _now_eat(self):
        return timezone.now().astimezone(tasks._eat_tz())

    def _actions(self):
        """(kind, wakati) ya hatua zote za leo na kesho."""
        now = self._now_eat()
        out = []
        for kind, hour, minute in (
                ('sync', self.sync_hour, self.sync_minute),
                ('fill', self.hour, self.minute)):
            target = now.replace(hour=hour, minute=minute, second=0,
                                 microsecond=0)
            out.append((kind, target))
            out.append((kind, target + timedelta(days=1)))
        return out

    def _seconds_until_next(self):
        now = self._now_eat()
        best = None
        for kind, target in self._actions():
            secs = (target - now).total_seconds()
            if secs <= 0:
                continue
            if best is None or secs < best[1]:
                best = (kind, secs)
        if best is None:
            return 'fill', 60.0
        return best[0], best[1]

    def _sleep(self, secs):
        # Lala kwa vipande ili signals/restarts zijibiwe haraka.
        end = _time.monotonic() + max(0.0, secs)
        while True:
            remaining = end - _time.monotonic()
            if remaining <= 0:
                break
            _time.sleep(min(remaining, 300))

    def _should_catch_up(self):
        from ess_tracker.models import EssFillRun

        now = self._now_eat()
        target = now.replace(hour=self.hour, minute=self.minute,
                             second=0, microsecond=0)
        if now < target:
            return False
        day_start, day_end = tasks._eat_day_bounds(now.date())
        return not EssFillRun.objects.filter(
            kind='fill', source='auto',
            started__gte=day_start, started__lt=day_end).exists()

    def _run_once(self):
        self.stdout.write(
            f'[ess-scheduler] kujaza kiotomatiki sasa ({self._now_eat()})...')
        res = tasks.run_auto_fill_inline(
            log=lambda m: self.stdout.write(str(m)))
        self.stdout.write(self.style.SUCCESS(
            f'[ess-scheduler] imekamilika: filled={res.get("filled")} '
            f'failed={res.get("failed")}'))

    def _run_sync_once(self):
        """Sawazisha majina ya ESS kwa walimu wasiofungua app."""
        self.stdout.write(
            f'[ess-scheduler] kusawazisha majina ya ESS ({self._now_eat()})...')
        res = tasks.run_auto_sync_inline(
            log=lambda m: self.stdout.write(str(m)))
        self.stdout.write(self.style.SUCCESS(
            f'[ess-scheduler] majina: synced={len(res.get("synced") or [])} '
            f'failed={len(res.get("failed") or [])}'))
