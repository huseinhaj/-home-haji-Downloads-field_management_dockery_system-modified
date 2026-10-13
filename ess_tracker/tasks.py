from celery import shared_task

# Siku za kujaza ESS: Jumatatu–Ijumaa (weekday 0=Jumatatu ... 4=Ijumaa).
FILL_WEEKDAYS = (0, 1, 2, 3, 4)

# Ugawanyaji wa siku za kujaza kwa wiki (Jumatatu–Ijumaa) kutoka idadi
# aliyochagua mwalimu (entries_per_week).
WEEKDAY_SPREAD = {
    1: (0,),
    2: (0, 3),          # Jumatatu, Alhamisi
    3: (0, 2, 4),       # Jumatatu, Jumatano, Ijumaa
    4: (0, 1, 3, 4),    # Jumatatu, Jumanne, Alhamisi, Ijumaa
    5: (0, 1, 2, 3, 4),  # Jumatatu–Ijumaa
}


def fill_weekdays(entries=3):
    """Siku za kujaza (weekday ints) kutoka idadi ya vipindi kwa wiki."""
    try:
        n = int(entries)
    except (TypeError, ValueError):
        n = 3
    n = max(1, min(5, n))
    return WEEKDAY_SPREAD[n]

# Saa za Tanzania (EAT). TIME_ZONE ya Django ni UTC; hesabu za siku za kujaza
# zinahitaji tarehe ya EAT ili usiku wa manane usisababishe kukosa/kuongeza siku.
EAT = None  # hupangwa kwa lazy kwenye _eat_tz()


def _eat_tz():
    global EAT
    if EAT is None:
        from zoneinfo import ZoneInfo
        EAT = ZoneInfo('Africa/Dar_es_Salaam')
    return EAT


def _today_eat():
    from django.utils import timezone
    return timezone.now().astimezone(_eat_tz()).date()


def _eat_day_bounds(day):
    """(mwanzoni, mwisho) wa siku ya EAT kama aware datetimes (kwa DB queries)."""
    from datetime import datetime, time, timedelta
    start = datetime.combine(day, time.min, tzinfo=_eat_tz())
    return start, start + timedelta(days=1)


def _fill_day(weekday, entries=None):
    """True kama leo ni siku ya kujaza kwa mwalimu mwenye `entries` kwa wiki.

    Siku huzagwa kutoka idadi aliyochagua mwalimu (mf. 3 = Jumatatu,
    Jumatano, Ijumaa). Bila `entries`, hutumia 3 kama kawaida.
    """
    return weekday in fill_weekdays(3 if entries is None else entries)


@shared_task(bind=True, time_limit=120, soft_time_limit=100)
def auto_fill_due(self):
    """Jaza kiotomatiki kwa kila mwalimu aliyejiwekea tarehe za shule,
    siku zinazohesabiwa kwa entries_per_week (queue='essfill')."""
    from .locks import is_locked
    from .models import EssFillRun, TeacherProfile

    today = _today_eat()
    day_start, day_end = _eat_day_bounds(today)
    triggered = []
    skipped = []
    for prof in TeacherProfile.objects.filter(ess_ready=True) \
            .select_related('user') \
            .exclude(school_open=None).exclude(school_close=None):
        if not prof.auto_fill_enabled:
            skipped.append({'id': prof.id, 'why': 'disabled'})
            continue
        if not (prof.school_open <= today <= prof.school_close):
            skipped.append({'id': prof.id, 'why': 'closed'})
            continue
        if not _fill_day(today.weekday(), prof.entries_per_week):
            skipped.append({'id': prof.id, 'why': 'not-fill-day'})
            continue
        if EssFillRun.objects.filter(profile=prof, kind='fill') \
                .exclude(status='error') \
                .filter(started__gte=day_start, started__lt=day_end).exists():
            skipped.append({'id': prof.id, 'why': 'already'})
            continue
        if is_locked(prof.id):
            skipped.append({'id': prof.id, 'why': 'locked'})
            continue
        run = EssFillRun.objects.create(
            profile=prof, only_subtasks=(prof.auto_subtasks or ''))
        from .tasks import run_ess_fill
        run_ess_fill.apply_async(args=[prof.id, run.id], queue='essfill')
        triggered.append(prof.id)
    return {'date': today.isoformat(), 'triggered': triggered,
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
    _notify_fill_result(profile_id, run_id)
    return res


def _notify_fill_result(profile_id, run_id):
    """Tuma arifa ya matokeo ya kujaza (kama notifications zimewashwa)."""
    from .models import EssFillRun
    from .push import push_configured, send_to_profile
    if not push_configured():
        return
    run = EssFillRun.objects.filter(pk=run_id).first()
    if run is None or run.status != 'done':
        return
    body = ('Imejaza: %d mpya, %d zilizopo tayari, %d hazikupatikana.'
            % (run.saved, run.skipped, run.not_found))
    send_to_profile(profile_id, title='e-Tendaji: kujaza kumekamilika',
                    body=body, url='/ess/', tag='ess-done', renotify=True)


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


@shared_task(bind=True, queue='essfill', time_limit=600, soft_time_limit=560,
             max_retries=3)
def run_ess_read(self, profile_id, run_id):
    """Soma asilimia halisi za ESS (queue='essfill')."""
    from .essfill import run_read
    from .locks import profile_lock
    with profile_lock(profile_id) as got:
        if not got:
            raise self.retry(countdown=_retry_countdown(self, 90))
        return run_read(profile_id, run_id)


@shared_task(time_limit=180, soft_time_limit=160)
def notify_fill_due():
    """Kumbusha walimu (wenye arifa) kujaza ESS siku za kujaza.

    Hutumwa tu Jumatatu–Ijumaa, kwa walimu ambao hawajajazwa leo
    (hawana run ya 'done' ya leo). Waliojibiwa tayari kiotomatiki
    hawasumbuliwi — wanapata arifa ya matokeo kwenye run_ess_fill.
    """
    from .models import EssFillRun, TeacherProfile
    from .push import push_configured, send_to_profile

    today = _today_eat()
    if not push_configured():
        return {'date': today.isoformat(), 'skipped': 'not-configured'}

    day_start, day_end = _eat_day_bounds(today)
    sent = 0
    skipped = 0
    profs = TeacherProfile.objects.filter(
        push_subscriptions__active=True).distinct().select_related('user')
    for prof in profs:
        if not _fill_day(today.weekday(), prof.entries_per_week):
            skipped += 1
            continue
        if prof.school_open and prof.school_close \
                and not (prof.school_open <= today <= prof.school_close):
            skipped += 1
            continue
        done_today = EssFillRun.objects.filter(
            profile=prof, kind='fill', status='done',
            finished__gte=day_start, finished__lt=day_end).exists()
        if done_today:
            skipped += 1
            continue
        res = send_to_profile(prof, title='Kumbuka: jaza e-Tendaji leo',
                              body='Bonyeza "Jaza" kuingiza maendeleo yako ya leo.',
                              url='/ess/', tag='ess-remind')
        sent += res.get('sent', 0)
    return {'date': today.isoformat(), 'sent': sent, 'skipped': skipped}