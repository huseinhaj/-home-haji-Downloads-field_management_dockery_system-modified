import logging
import time as _time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = ('Kiendesha masomo ya automatic (auto-lessons) — kila siku EAT '
            'huangalia kama masomo ya wiki hii na ijayo yamezalishwa kwa '
            'wanafunzi wote wenye schemes; kama hapana, inazalisha. '
            'Idempotent (auto_key inazuia rudufu). HUMU ndani ya container '
            'ya web — mfano wa ess_scheduler.')

    def add_arguments(self, parser):
        parser.add_argument('--hour', type=int, default=5,
                            help='Saa ya EAT ya kuendesha kila siku (default 5).')
        parser.add_argument('--minute', type=int, default=0,
                            help='Dakika (default 0).')
        parser.add_argument('--weeks', type=int, default=2,
                            help='Wiki ngani mbele kuzalisha (default 2: hii + ijayo).')
        parser.add_argument('--once', action='store_true',
                            help='Endesha mara moja sasa kisha toka.')
        parser.add_argument('--catch-up', action='store_true',
                            help='Kwenye kuanza: kama saa ya leo imepita na hakuna '
                                 'run ya leo, endesha mara moja.')

    def handle(self, *args, **opts):
        self.hour = opts['hour']
        self.minute = opts['minute']
        self.weeks = opts['weeks']
        self.stdout.write(self.style.SUCCESS(
            f'[auto-lessons] imeanza — kila siku {self.hour:02d}:{self.minute:02d} EAT '
            f'(wiki mbele: {self.weeks})'))

        if opts['once']:
            self._run()
            return

        if opts['catch_up']:
            try:
                if self._should_catch_up():
                    self.stdout.write('[auto-lessons] catch-up: leo haijaendeshwa — inaendesha.')
                    self._run()
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f'[auto-lessons] catch-up error: {exc}')

        while True:
            secs = self._seconds_until_next()
            self.stdout.write(
                f'[auto-lessons] ijayo baada ya {secs / 3600:.2f} h')
            _time.sleep(secs)
            self._run()

    def _seconds_until_next(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo('Africa/Dar_es_Salaam'))
        target = now.replace(hour=self.hour, minute=self.minute,
                             second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return (target - now).total_seconds() + 5

    def _should_catch_up(self):
        from field_app.models import AutoLessonRun
        from field_app.auto_lessons import today_eat
        return not AutoLessonRun.objects.filter(ran_on=today_eat()).exists()

    def _run(self):
        from field_app.auto_lessons import generate_for_all_students, today_eat
        from field_app.models import AutoLessonRun

        close_old_connections()
        try:
            summary = generate_for_all_students(weeks_ahead=self.weeks)
        except Exception as exc:  # noqa: BLE001
            logger.exception('[auto-lessons] run failed')
            self.stderr.write(f'[auto-lessons] run failed: {exc}')
            AutoLessonRun.objects.create(
                ran_on=today_eat(), status='failed', detail=f'{exc}',
                lessons_created=0, students_processed=0)
            return

        detail = '; '.join(summary['errors'][:20]) if summary['errors'] else ''
        AutoLessonRun.objects.create(
            ran_on=today_eat(),
            status='ok' if not summary['errors'] else 'partial',
            detail=detail[:2000],
            lessons_created=summary['lessons_created'],
            students_processed=summary['students'],
        )
        self.stdout.write(self.style.SUCCESS(
            f'[auto-lessons] wanafunzi: {summary["students"]} | masomo mapya: '
            f'{summary["lessons_created"]} | makosa: {len(summary["errors"])}'))
