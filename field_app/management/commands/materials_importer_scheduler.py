import logging
import time as _time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = ('Kiendesha Maktaba — kila siku EAT huangalia vyanzo vyote '
            '(Wazaelimu, Lusa Elimu, n.k.) na kuchota notes/mitihani mpya, '
            'kuipakua na kuiainisha (AI). HUMU ndani ya container ya web '
            '(mfano wa ess_scheduler / auto_lessons_scheduler).')

    def add_arguments(self, parser):
        parser.add_argument('--hour', type=int, default=3,
                            help='Saa ya EAT ya kuendesha kila siku (default 3).')
        parser.add_argument('--minute', type=int, default=15,
                            help='Dakika (default 15).')
        parser.add_argument('--max-new', type=int, default=20,
                            help='Materials mpya kwa kila chanzo kila run (default 20).')
        parser.add_argument('--once', action='store_true',
                            help='Endesha mara moja sasa kisha toka.')
        parser.add_argument('--catch-up', action='store_true',
                            help='Kwenye kuanza: kama leo haijaendeshwa, endesha mara moja.')

    def handle(self, *args, **opts):
        self.hour = opts['hour']
        self.minute = opts['minute']
        self.max_new = opts['max_new']
        self.stdout.write(self.style.SUCCESS(
            f'[maktaba] imeanza — kila siku {self.hour:02d}:{self.minute:02d} EAT'))

        if opts['once']:
            self._run()
            return

        if opts['catch_up']:
            try:
                if self._should_catch_up():
                    self.stdout.write('[maktaba] catch-up: leo haijaendeshwa — inaendesha.')
                    self._run()
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f'[maktaba] catch-up error: {exc}')

        while True:
            secs = self._seconds_until_next()
            self.stdout.write(f'[maktaba] ijayo baada ya {secs / 3600:.2f} h')
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
        from field_app.auto_lessons import today_eat
        from field_app.models import MaterialImportRun
        return not MaterialImportRun.objects.filter(ran_on=today_eat()).exists()

    def _run(self):
        from field_app.materials_importer import import_all_sources
        from field_app.auto_lessons import today_eat
        from field_app.models import MaterialImportRun

        close_old_connections()
        try:
            summary = import_all_sources(max_new_per_source=self.max_new)
        except Exception as exc:  # noqa: BLE001
            logger.exception('[maktaba] run failed')
            self.stderr.write(f'[maktaba] run failed: {exc}')
            MaterialImportRun.objects.create(
                ran_on=today_eat(), status='failed', detail=f'{exc}',
                materials_downloaded=0)
            return

        created = sum(r['created'] for r in summary['runs'])
        found = sum(r['found'] for r in summary['runs'])
        detail_lines = [f"{r['source']}: mpya {r['created']}/{r['found']} "
                        f"(skipped {r['skipped']}, makosa {r['errors']})"
                        for r in summary['runs']]
        detail = '; '.join(detail_lines + summary['errors'])[:2000]
        MaterialImportRun.objects.create(
            ran_on=today_eat(),
            status='ok' if not summary['errors'] else 'partial',
            materials_found=found,
            materials_downloaded=created,
            detail=detail,
        )
        self.stdout.write(self.style.SUCCESS(
            f'[maktaba] mpya: {created} | zilizopatikana: {found} | '
            f'makosa: {len(summary["errors"])}'))
