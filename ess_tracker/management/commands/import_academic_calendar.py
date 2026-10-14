"""Ingiza kalenda ya mwaka (tarehe + asilimia za kila mwezi) kutoka CSV.

Matumizi:
    python manage.py import_academic_calendar 2026 \
        --csv kalenda.csv --open 2026-01-06 --close 2026-12-04 --activate

CSV (safu mbili: mwezi, asilimia):
    month,pct
    1,0
    7,20
    8,30
    ...
Mwezi unaweza kuwa namba (1-12) au jina (Januari/January).
"""
import csv

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from ...models import AcademicCalendar, MonthlyTarget

_MONTHS = {
    'januari': 1, 'january': 1, 'jan': 1,
    'februari': 2, 'february': 2, 'feb': 2,
    'machi': 3, 'march': 3, 'mar': 3,
    'aprili': 4, 'april': 4, 'apr': 4,
    'mei': 5, 'may': 5,
    'juni': 6, 'june': 6, 'jun': 6,
    'julai': 7, 'july': 7, 'jul': 7,
    'agosti': 8, 'august': 8, 'aug': 8,
    'septemba': 9, 'september': 9, 'sep': 9, 'sept': 9,
    'oktoba': 10, 'october': 10, 'oct': 10,
    'novemba': 11, 'november': 11, 'nov': 11,
    'desemba': 12, 'december': 12, 'dec': 12,
}


def _month(value):
    s = str(value or '').strip().lower()
    if not s:
        return None
    if s.isdigit():
        n = int(s)
        return n if 1 <= n <= 12 else None
    return _MONTHS.get(s)


class Command(BaseCommand):
    help = 'Ingiza/updates kalenda ya mwaka na asilimia za miezi kutoka CSV.'

    def add_arguments(self, parser):
        parser.add_argument('year', help='Mwaka, mf. 2026')
        parser.add_argument('--csv', dest='csv_path', default='',
                            help='Njia ya faili la CSV (month,pct).')
        parser.add_argument('--open', dest='open_date', default='',
                            help='Tarehe ya kufungua (YYYY-MM-DD).')
        parser.add_argument('--close', dest='close_date', default='',
                            help='Tarehe ya kufunga (YYYY-MM-DD).')
        parser.add_argument('--activate', action='store_true',
                            help='Weka kalenda hii kama active.')
        parser.add_argument('--noactivate', action='store_true',
                            help='Acha kalenda hii isiwe active.')

    def handle(self, *args, **opts):
        year = str(opts['year']).strip()
        if not year:
            raise CommandError('Mwaka unahitajika.')

        open_date = parse_date(opts['open_date']) if opts['open_date'] else None
        close_date = parse_date(opts['close_date']) if opts['close_date'] else None
        if opts['open_date'] and open_date is None:
            raise CommandError('Tarehe ya --open si sahihi.')
        if opts['close_date'] and close_date is None:
            raise CommandError('Tarehe ya --close si sahihi.')

        cal, _created = AcademicCalendar.objects.get_or_create(year=year)
        if open_date:
            cal.school_open = open_date
        if close_date:
            cal.school_close = close_date
        if opts['activate']:
            cal.is_active = True
        elif opts['noactivate']:
            cal.is_active = False
        cal.save()

        count = 0
        if opts['csv_path']:
            try:
                fh = open(opts['csv_path'], newline='', encoding='utf-8-sig')
            except OSError as exc:
                raise CommandError(f'Imeshindwa kufungua CSV: {exc}')
            with fh:
                for lineno, raw in enumerate(csv.reader(fh), start=1):
                    if not raw or not any(str(c).strip() for c in raw):
                        continue
                    mon = _month(raw[0])
                    if mon is None:
                        if lineno == 1:
                            continue  # header
                        self.stderr.write(f'Safu {lineno}: mwezi si sahihi: {raw[0]!r}')
                        continue
                    try:
                        pct = float(str(raw[1]).replace('%', '').strip())
                    except (IndexError, ValueError):
                        self.stderr.write(f'Safu {lineno}: asilimia si sahihi.')
                        continue
                    MonthlyTarget.objects.update_or_create(
                        calendar=cal, month=mon,
                        defaults={'expected_pct': pct})
                    count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Kalenda {cal.year}: malengo {count}, active={cal.is_active}, '
            f'kufungua={cal.school_open}, kufunga={cal.school_close}'))
