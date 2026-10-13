from celery import shared_task

# Siku za kujaza ESS: Jumatatu–Ijumaa (weekday 0=Jumatatu ... 4=Ijumaa).
FILL_WEEKDAYS = (0, 1, 2, 3, 4)


def _fill_day(weekday, entries=None):
    """True kama leo ni siku ya kujaza (Jumatatu–Ijumaa).

    `entries` (entries_per_week) haitumiki tena kwa ratiba ya siku — siku
    zote za kazi hujazwa. Bado zinatumika kwenye hesabu ya asilimia
    (compute.py) kama ilivyo.
    """
    return weekday in FILL_WEEKDAYS


@shared_task(bind=True, time_limit=120, soft_time_limit=100)
def auto_fill_due(self):
    """Jaza kiotomatiki kwa kila mwalimu aliyejiwekea tarehe za shule,
    siku zinazohesabiwa kwa entries_per_week (queue='essfill')."""
    from datetime import date

    from django.utils import timezone

    from .locks import is_locked
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
        if is_locked(prof.id):
            skipped.append({'id': prof.id, 'why': 'locked'})
            continue
        run = EssFillRun.objects.create(profile=prof)
        from .tasks import run_ess_fill
        run_ess_fill.apply_async(args=[prof.id, run.id], queue='essfill')
        triggered.append(prof.id)
    return {'date': date.today().isoformat(), 'triggered': triggered,
            'skipped': skipped}


def _retry_countdown(task, base):
    """Backoff: base, base x2, base x4 ... hadi dakika 15."""
    return min(base * (2 ** task.request.retries), 900)


def _retry_safe(task, run_id, res) -> bool:
    """Retry tu kama run ilishindwa KABLA ya kuwasilisha kitu (saved == 0).

    Hii inaepusha kuwasilisha entry mara mbili kwenye ESS wakati wa retry.
    """
    if not res or res.get('status') != 'error':
        return False
    if task.request.retries >= task.max_retries:
        return False
    from .models import EssFillRun
    saved = EssFillRun.objects.filter(pk=run_id) \
        .values_list('saved', flat=True).first() or 0
    return not saved


@shared_task(bind=True, queue='essfill', time_limit=600, soft_time_limit=560,
             max_retries=3)
def run_ess_fill(self, profile_id, run_id):
    """Jaza ESS kwa profile moja (queue='essfill').

    Lock ya mwalimu huzuia run mbili za mtu mmoja ziende pamoja. Kama
    mwingine anaendelea, tunasubiri (retry) badala ya kugongana kwenye ESS.
    """
    from .essfill import run_fill
    from .locks import profile_lock
    with profile_lock(profile_id) as got:
        if not got:
            raise self.retry(countdown=_retry_countdown(self, 90))
        res = run_fill(profile_id, run_id)
    if _retry_safe(self, run_id, res):
        raise self.retry(countdown=_retry_countdown(self, 120))
    return res


@shared_task(bind=True, queue='essfill', time_limit=600, soft_time_limit=560,
             max_retries=3)
def run_ess_sync(self, profile_id, run_id):
    """Sawazisha majina ya task/sub-task na ESS (queue='essfill')."""
    from .essfill import run_sync
    from .locks import profile_lock
    with profile_lock(profile_id) as got:
        if not got:
            raise self.retry(countdown=_retry_countdown(self, 90))
        return run_sync(profile_id, run_id)


@shared_task(bind=True, queue='essfill', time_limit=600, soft_time_limit=560,
             max_retries=3)
def run_ess_push(self, profile_id, run_id):
    """Tuma majina ya local kwenda ESS official (queue='essfill')."""
    from .essfill import run_push
    from .locks import profile_lock
    with profile_lock(profile_id) as got:
        if not got:
            raise self.retry(countdown=_retry_countdown(self, 90))
        return run_push(profile_id, run_id)