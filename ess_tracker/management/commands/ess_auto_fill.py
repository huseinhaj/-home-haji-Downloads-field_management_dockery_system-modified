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
        res = tasks.auto_fill_due.apply().get()
        self.stdout.write(self.style.SUCCESS(
            f'Imeanzisha: {res.get("triggered")}'))
