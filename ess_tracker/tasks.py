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


def _live_only_subtasks(prof) -> str:
    """CSV ya IDs za sub-task za chaguo za mwalimu ambazo ZIPO bado.

    IDs zilizofutwa (stale) hupuuzwa ili run isikwame. Tupu = jaza zote.
    """
    ids = prof.auto_subtask_ids()
    if not ids:
        return ''
    from .models import SubTask
    valid = set(SubTask.objects.filter(task__profile=prof)
                .values_list('id', flat=True))
    live = [i for i in ids if i in valid]
    return ','.join(str(i) for i in live)


def auto_fill_decision(prof, today, cal_win, day_start, day_end):
    """(ready, reason) kwa mwalimu mmoja. reason ni '' kama yuko tayari.

    Hukumu ile ile hutumika kwenye auto_fill_due NA amri ya usimamizi
    `ess_auto_fill` (ili maamuzi yasitofautiane). Sababu zinazoweza
    kutokea: 'disabled', 'no-window', 'closed', 'not-fill-day', 'already',
    'locked'.
    """
    from .compute import profile_fill_entries
    from .locks import is_locked
    from .models import EssFillRun

    if not prof.auto_fill_enabled:
        return False, 'disabled'
    open_d, close_d = cal_win or (prof.school_open, prof.school_close)
    if not (open_d and close_d):
        return False, 'no-window'
    if not (open_d <= today <= close_d):
        return False, 'closed'
    if not _fill_day(today.weekday(), profile_fill_entries(prof)):
        return False, 'not-fill-day'
    if EssFillRun.objects.filter(profile=prof, kind='fill') \
            .exclude(status='error') \
            .filter(started__gte=day_start, started__lt=day_end).exists():
        return False, 'already'
    if is_locked(prof.id):
        return False, 'locked'
    return True, ''


@shared_task(bind=True, time_limit=120, soft_time_limit=100)
def auto_fill_due(self):
    """Jaza kiotomatiki kwa kila mwalimu (dirisha na mzunguko kutoka mtaala).

    Dirisha la mwaka hutoka kalenda ya admin kama ipo, vinginevyo tarehe za
    wasifu. Siku za kujaza huzagwa kutoka vipindi vya mtaala vya somo
    (fallback entries_per_week). (queue='essfill')."""
    from .compute import calendar_window
    from .models import EssFillRun, TeacherProfile

    today = _today_eat()
    cal_win = calendar_window()
    day_start, day_end = _eat_day_bounds(today)
    triggered = []
    skipped = []
    qs = TeacherProfile.objects.filter(ess_ready=True).select_related('user')
    if not cal_win:
        qs = qs.exclude(school_open=None).exclude(school_close=None)
    for prof in qs:
        ready, why = auto_fill_decision(prof, today, cal_win, day_start, day_end)
        if not ready:
            skipped.append({'id': prof.id, 'why': why})
            continue
        run = EssFillRun.objects.create(
            profile=prof, only_subtasks=_live_only_subtasks(prof))
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
    from .compute import calendar_target_pct, calendar_window, profile_fill_entries
    from .models import EssFillRun, TeacherProfile
    from .push import push_configured, send_to_profile

    today = _today_eat()
    if not push_configured():
        return {'date': today.isoformat(), 'skipped': 'not-configured'}

    cal_win = calendar_window()
    target = calendar_target_pct(today)
    day_start, day_end = _eat_day_bounds(today)
    sent = 0
    skipped = 0
    profs = TeacherProfile.objects.filter(
        push_subscriptions__active=True).distinct().select_related('user')
    for prof in profs:
        if not _fill_day(today.weekday(), profile_fill_entries(prof)):
            skipped += 1
            continue
        open_d, close_d = cal_win or (prof.school_open, prof.school_close)
        if open_d and close_d and not (open_d <= today <= close_d):
            skipped += 1
            continue
        done_today = EssFillRun.objects.filter(
            profile=prof, kind='fill', status='done',
            finished__gte=day_start, finished__lt=day_end).exists()
        if done_today:
            skipped += 1
            continue
        body = 'Bonyeza "Jaza" kuingiza maendeleo yako ya leo.'
        if target is not None:
            body = (f'Lengo la mwezi huu ni {target:.0f}%. '
                    'Bonyeza "Jaza" kuingiza maendeleo yako ya leo.')
        res = send_to_profile(prof, title='Kumbuka: jaza e-Tendaji leo',
                              body=body, url='/ess/', tag='ess-remind')
        sent += res.get('sent', 0)
    return {'date': today.isoformat(), 'sent': sent, 'skipped': skipped}


@shared_task(time_limit=300, soft_time_limit=280)
def notify_calendar_targets():
    """Arifa kwa walimu walio NYUMA ya asilimia ya mwezi (kalenda ya admin).

    Hutumia asilimia lengwa ya mwezi husika na maendeleo ya sasa ya mwalimu.
    Hatumi mtu yeyote kama hakuna kalenda active au push haijapangwa.
    """
    from .compute import (active_calendar, calendar_target_pct,
                          profile_progress_pct)
    from .models import TeacherProfile
    from .push import push_configured, send_to_profile

    cal = active_calendar()
    if not cal:
        return {'skipped': 'no-calendar'}
    today = _today_eat()
    target = calendar_target_pct(today)
    if target is None:
        return {'skipped': 'no-target', 'year': cal.year}
    if not push_configured():
        return {'skipped': 'not-configured'}

    sent = 0
    checked = 0
    behind = 0
    profs = TeacherProfile.objects.filter(
        push_subscriptions__active=True).distinct().select_related('user')
    for prof in profs:
        cur = profile_progress_pct(prof)
        if cur is None:
            continue
        checked += 1
        if cur + 0.5 >= target:
            continue
        behind += 1
        body = (f'Kalenda {cal.year}: mwezi huu unatakiwa uwe {target:.0f}%, '
                f'wewe upo {cur:.0f}%. Ongeza maendeleo.')
        res = send_to_profile(prof, title='e-Tendaji: uko nyuma ya kalenda',
                              body=body, url='/ess/', tag='ess-calendar',
                              renotify=True)
        sent += res.get('sent', 0)
    return {'year': cal.year, 'result': today.isoformat(), 'target': target,
            'checked': checked, 'behind': behind, 'sent': sent}