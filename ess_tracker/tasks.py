from celery import shared_task

FILL_WEEKDAYS = {
    2: (1, 4),      # Jumanne, Ijumaa
    3: (0, 2, 4),   # Jumatatu, Jumatano, Ijumaa
}


def _fill_day(weekday, entries):
    if not entries or entries < 1:
        return weekday == 0
    return weekday in FILL_WEEKDAYS.get(int(entries), (0, 2, 4))


@shared_task(bind=True, time_limit=120, soft_time_limit=100)
def auto_fill_due(self):
    """Jaza kiotomatiki kwa kila mwalimu aliyejiwekea tarehe za shule,
    siku zinazohesabiwa kwa entries_per_week (queue='default')."""
    from datetime import date

    from django.utils import timezone

    from .models import EssFillRun, TeacherProfile

    today = timezone.localdate()
    triggered = []
    skipped = []
    for prof in TeacherProfile.objects.filter(ess_ready=True) \
            .select_related('user') \
            .exclude(school_open=None).exclude(school_close=None):
        if not (prof.school_open <= today <= prof.school_close):
            skipped.append({'id': prof.id, 'why': 'closed'})
            continue
        if not _fill_day(today.weekday(), prof.entries_per_week):
            skipped.append({'id': prof.id, 'why': 'not-fill-day'})
            continue
        if EssFillRun.objects.filter(profile=prof, kind='fill') \
                .exclude(status='failed').filter(started__date=today).exists():
            skipped.append({'id': prof.id, 'why': 'already'})
            continue
        run = EssFillRun.objects.create(profile=prof)
        from .tasks import run_ess_fill
        run_ess_fill.apply_async(args=[prof.id, run.id], queue='default')
        triggered.append(prof.id)
    return {'date': date.today().isoformat(), 'triggered': triggered,
            'skipped': skipped}


@shared_task(bind=True, time_limit=600, soft_time_limit=560)
def run_ess_fill(self, profile_id, run_id):
    """Jaza ESS kwa profile moja (queue='default' — ndiyo worker inayosikiliza)."""
    from .essfill import run_fill
    return run_fill(profile_id, run_id)


@shared_task(bind=True, time_limit=600, soft_time_limit=560)
def run_ess_sync(self, profile_id, run_id):
    """Sawazisha majina ya task/sub-task na ESS (queue='default')."""
    from .essfill import run_sync
    return run_sync(profile_id, run_id)


@shared_task(bind=True, time_limit=600, soft_time_limit=560)
def run_ess_push(self, profile_id, run_id):
    """Tuma majina ya local kwenda ESS official (queue='default')."""
    from .essfill import run_push
    return run_push(profile_id, run_id)