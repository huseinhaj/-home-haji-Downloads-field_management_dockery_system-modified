"""Kiendesha kuidhinisha (verify) kiotomatiki ESS kila siku — HUMU ndani.

Kama `ess_scheduler` lakini kwa uhidhinishaji: huwasha wakuu wote
waliochaguliwa (`approver_enabled=True`) na kuidhinisha maendeleo SUBMITTED
ya walimu.

Mifano:
    python manage.py ess_approve_scheduler --once            # mara moja sasa
    python manage.py ess_approve_scheduler --hour 22 --minute 0
    python manage.py ess_approve_scheduler --once --dry-run
"""
import time as _time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ess_tracker import tasks


class Command(BaseCommand):
    help = ('Kuidhinisha (verify) maendeleo SUBMITTED ya ESS kila siku kwa '
            'wakuu waliochaguliwa — HUMU ndani (bila celery worker).')

    def add_arguments(self, parser):
        parser.add_argument('--hour', type=int, default=22,
                            help='Saa ya EAT (default 22 — saa 10 jioni, baada '
                                 'ya saa za kazi).')
        parser.add_argument('--minute', type=int, default=0,
                            help='Dakika (default 0).')
        parser.add_argument('--once', action='store_true',
                            help='Endesha mara moja sasa kisha toka.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Onyesha tu; usibofye Verify.')
        parser.add_argument('--catch-up', action='store_true',
                            help='Kwenye kuanza: endesha kama saa ya leo imepita.')

    def handle(self, *args, **opts):
        self.hour = opts['hour']
        self.minute = opts['minute']
        self.dry_run = opts['dry_run']
        self.stdout.write(self.style.SUCCESS(
            f'[ess-approve-scheduler] imeanza — kila siku {self.hour:02d}:'
            f'{self.minute:02d} EAT'))

        if opts['once']:
            self._run_once()
            return

        if opts['catch_up']:
            try:
                if self._should_catch_up():
                    self.stdout.write('[ess-approve-scheduler] catch-up...')
                    self._run_once()
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f'[ess-approve-scheduler] catch-up error: {exc}')

        while True:
            secs = self._seconds_until_next()
            self.stdout.write(
                f'[ess-approve-scheduler] ijayo baada ya {secs / 3600:.2f} h '
                f'({self.hour:02d}:{self.minute:02d} EAT)')
            self._sleep(secs)
            try:
                self._run_once()
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f'[ess-approve-scheduler] error: {exc}')

    def _now_eat(self):
        return timezone.now().astimezone(tasks._eat_tz())

    def _seconds_until_next(self):
        now = self._now_eat()
        target = now.replace(hour=self.hour, minute=self.minute,
                             second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return (target - now).total_seconds()

    def _sleep(self, secs):
        end = _time.monotonic() + max(0.0, secs)
        while True:
            remaining = end - _time.monotonic()
            if remaining <= 0:
                break
            _time.sleep(min(remaining, 300))

    def _should_catch_up(self):
        from ess_tracker.models import TeacherProfile

        now = self._now_eat()
        target = now.replace(hour=self.hour, minute=self.minute,
                             second=0, microsecond=0)
        if now < target:
            return False
        # Kuna mkuu yeyote ambaye kipindi chake bado kinaendelea?
        qs = TeacherProfile.objects.filter(
            approver_enabled=True, ess_ready=True)
        return any(tasks.approve_due_for(p) for p in qs)

    def _run_once(self):
        self.stdout.write(
            f'[ess-approve-scheduler] kuidhinisha sasa ({self._now_eat()})...')
        res = tasks.run_approve_inline(
            log=lambda m: self.stdout.write(str(m)), dry_run=self.dry_run,
            only_due=True)
        self.stdout.write(self.style.SUCCESS(
            f'[ess-approve-scheduler] imekamilika: verified={res.get("verified")} '
            f'processed={res.get("processed")} failed={res.get("failed")}'))
