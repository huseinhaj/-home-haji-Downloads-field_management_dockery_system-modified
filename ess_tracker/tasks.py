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


# Majina ya siku (Kiswahili) kwa weekday int (0=Jumatatu ... 6=Jumapili).
WEEKDAY_NAMES = ('Jumatatu', 'Jumanne', 'Jumatano', 'Alhamisi', 'Ijumaa',
                 'Jumamosi', 'Jumapili')


def fill_day_names(entries=3):
    """Majina ya siku za kujaza kutoka entries_per_week (mf. 'Jumatatu, Jumatano, Ijumaa')."""
    return [WEEKDAY_NAMES[d] for d in fill_weekdays(entries)]

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


def fill_lease_active(prof, now=None) -> bool:
    """True kama mfumo bado anaweza kujaza kwa profile hii.

    Mchakato wa moja kwa moja unadhibitiwa na kipindi (lease) cha mkuu:
    - Mkuu mwenyewe: kipindi chake.
    - Mwalimu: kipindi cha mkuu wa shule yake. Kama hakuna mkuu (approver)
      katika shule hiyo, hakuna kizuizi.

    Kipindi kikichisha = mfumo husimama (hakuna kujaza) hadi mkuu aweke
    muda upya.
    """
    from .models import TeacherProfile
    if getattr(prof, 'approver_enabled', False):
        return approve_lease_active(prof, now=now)
    if not prof.school_id:
        return True
    approvers = TeacherProfile.objects.filter(
        school_id=prof.school_id, approver_enabled=True)
    if not approvers.exists():
        return True
    for appr in approvers:
        if approve_lease_active(appr, now=now):
            return True
    return False


def auto_fill_decision(prof, today, cal_win, day_start, day_end):
    """(ready, reason) kwa mwalimu mmoja. reason ni '' kama yuko tayari.

    Hukumu ile ile hutumika kwenye auto_fill_due NA amri ya usimamizi
    `ess_auto_fill` (ili maamuzi yasitofautiane). Sababu zinazoweza
    kutokea: 'disabled', 'no-window', 'closed', 'not-fill-day', 'already',
    'locked', 'lease-expired'.
    """
    from .compute import entries_per_week
    from .locks import is_locked
    from .models import EssFillRun

    if not prof.auto_fill_enabled:
        return False, 'disabled'
    if not fill_lease_active(prof):
        return False, 'lease-expired'
    open_d, close_d = cal_win or (prof.school_open, prof.school_close)
    if not (open_d and close_d):
        return False, 'no-window'
    if not (open_d <= today <= close_d):
        return False, 'closed'
    # Siku za kujaza = entries_per_week (idadi aliyoiweka mwalimu). Vipindi vya
    # mtaala hutumika kwa ASILIMIA pekee, sio kwa ratiba ya siku.
    if not _fill_day(today.weekday(), entries_per_week(prof)):
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
    wasifu. Siku za kujaza huzagwa kutoka entries_per_week ya mwalimu; vipindi
    vya mtaala hutumika kwa ASILIMIA pekee (sio ratiba ya siku)."""
    from .compute import calendar_window
    from .models import EssFillRun, TeacherProfile
    from .runstate import reap_stale_runs

    reap_stale_runs()
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
            profile=prof, only_subtasks=_live_only_subtasks(prof),
            source='auto')
        from .tasks import run_ess_fill
        run_ess_fill.apply_async(args=[prof.id, run.id], queue='essfill')
        triggered.append(prof.id)
    return {'date': today.isoformat(), 'triggered': triggered,
            'skipped': skipped}


def run_auto_fill_inline(profiles=None, log=None):
    """Jaza kiotomatiki HUMU ndani ya process hii (bila broker/worker/beat).

    Hukumu ni zile zile za beat (`auto_fill_decision`). Hutumika na:
      - amri `ess_auto_fill --execute --inline`
      - kiendesha cha `ess_scheduler` (kilichopachikwa kwenye container ya web)
      - Cron Job ya Railway (bila beat/worker)

    `profiles` (si lazima): orodha ya TeacherProfile walio tayari; kama haipo,
    hupatikana kwa `auto_fill_decision`. `log` (si lazima): callable(msg).
    Hurudisha {'date', 'filled', 'failed'}.
    """
    from django.utils import timezone

    from .compute import calendar_window
    from .essfill import run_fill
    from .locks import profile_lock
    from .models import EssFillRun, TeacherProfile
    from .runstate import reap_stale_runs

    def _log(msg):
        if log:
            try:
                log(msg)
            except Exception:  # noqa: BLE001
                pass

    reap_stale_runs()
    today = _today_eat()
    cal_win = calendar_window()
    day_start, day_end = _eat_day_bounds(today)

    if profiles is None:
        qs = TeacherProfile.objects.filter(ess_ready=True).select_related('user')
        if not cal_win:
            qs = qs.exclude(school_open=None).exclude(school_close=None)
        profiles = []
        for prof in qs:
            ready, _why = auto_fill_decision(
                prof, today, cal_win, day_start, day_end)
            if ready:
                profiles.append(prof)

    filled, failed = [], []
    for prof in profiles:
        run = EssFillRun.objects.create(
            profile=prof, only_subtasks=_live_only_subtasks(prof), source='auto')
        with profile_lock(prof.id) as got:
            if not got:
                run.status = 'error'
                run.finished = timezone.now()
                run.log = 'Lock ilikuwa inashikiliwa; kurukwa.'
                run.save()
                _log(f'  #{prof.id} — lock, imerukwa')
                continue
            try:
                res = run_fill(prof.id, run.id)
                filled.append(prof.id)
                _log(f'  #{prof.id} — saved={res.get("saved")} '
                     f'skipped={res.get("skipped")} '
                     f'not_found={res.get("not_found")}')
            except Exception as exc:  # noqa: BLE001
                failed.append(prof.id)
                run.status = 'error'
                run.finished = timezone.now()
                run.log = (run.log + f'\n{exc}') if run.log else str(exc)
                run.save()
                _log(f'  #{prof.id} — HITILAFU: {exc}')
    return {'date': today.isoformat(), 'filled': filled, 'failed': failed}


def run_approve_inline(profiles=None, log=None, dry_run=False, only_due=False):
    """Idhinisha (verify) maendeleo SUBMITTED ya walimu — humu ndani ya process.

    Hupitia wakuu/kiongozi wote waliochaguliwa (`approver_enabled=True`).
    Hutumika na amri `ess_approve --all` na kiendesha `ess_approve_scheduler`.

    Kama `only_due=True`, huchukua wale tu ambao kipindi chao
    (`auto_lease_until`) bado kinaendelea na hawajawahi kuidhinishwa
    leo — hutumika na kiendesha cha kila siku.

    Hurudisha {'date', 'verified', 'processed', 'failed', 'profiles'}.
    """
    def _log(msg):
        if log:
            try:
                log(msg)
            except Exception:  # noqa: BLE001
                pass

    if profiles is None:
        from .models import TeacherProfile
        base = TeacherProfile.objects.filter(
            approver_enabled=True, ess_ready=True).select_related('user')
        profiles = [p for p in base if (not only_due) or approve_due_for(p)]

    profiles = list(profiles)
    verified = processed = failed = 0
    done = []
    conc = _approve_concurrency()

    if conc > 1 and len(profiles) > 1:
        _log(f'  [concurrency={conc}] wakuu {len(profiles)} — sambamba')
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=conc) as ex:
            futs = {ex.submit(_approve_one, p, dry_run, _log): p
                    for p in profiles}
            for fut in as_completed(futs):
                v, pr, f, ok = fut.result()
                verified += v
                processed += pr
                failed += f
                if ok:
                    done.append(futs[fut].id)
    else:
        for prof in profiles:
            v, pr, f, ok = _approve_one(prof, dry_run, _log)
            verified += v
            processed += pr
            failed += f
            if ok:
                done.append(prof.id)

    return {'date': _today_eat().isoformat(), 'verified': verified,
            'processed': processed, 'failed': failed, 'profiles': done}


def _approve_concurrency() -> int:
    """Idadi ya wakuu wanaoidhinishwa sambamba (env ESS_APPROVE_CONCURRENCY)."""
    import os
    try:
        n = int(os.environ.get('ESS_APPROVE_CONCURRENCY', '3'))
    except (TypeError, ValueError):
        n = 3
    return max(1, min(n, 8))


def _approve_one(prof, dry_run, _log):
    """Idhinisha mkuu mmoja (thread salama). Hurudi (verified, processed,
    failed, ok)."""
    from django.db import connection
    from django.utils import timezone

    from .essapprove import run_approve
    from .locks import profile_lock
    from .models import EssFillRun

    run = EssFillRun.objects.create(
        profile=prof, kind='approve', source='auto')
    try:
        with profile_lock(prof.id) as got:
            if not got:
                run.status = 'error'
                run.finished = timezone.now()
                run.log = 'Lock ilikuwa inashikiliwa; kurukwa.'
                run.save()
                _log(f'  #{prof.id} — lock, imerukwa')
                return (0, 0, 0, False)
            try:
                res = run_approve(prof.id, run.id, dry_run=dry_run)
                _log(f'  #{prof.id} — verified={res.get("verified", 0)} '
                     f'processed={res.get("processed", 0)} '
                     f'failed={res.get("failed", 0)}')
                return (res.get('verified', 0), res.get('processed', 0),
                        res.get('failed', 0), True)
            except Exception as exc:  # noqa: BLE001
                run.status = 'error'
                run.finished = timezone.now()
                run.log = (run.log + f'\n{exc}') if run.log else str(exc)
                run.save()
                _log(f'  #{prof.id} — HITILAFU: {exc}')
                return (0, 0, 1, False)
    finally:
        # Funga muunganisho wa DB wa thread hii (ThreadPoolExecutor).
        try:
            connection.close()
        except Exception:  # noqa: BLE001
            pass


def approve_interval_days(profile) -> int:
    """Muda wa kipindi (lease) kwa profile kwa siku (0 = hakuna mwisho)."""
    try:
        weeks = int(getattr(profile, 'auto_approve_weeks', 0))
    except (TypeError, ValueError):
        weeks = 0
    return max(0, weeks) * 7


def approve_interval_label(profile) -> str:
    """Jina la muda wa kipindi kwa Kiswahili (kwa kuionyesha kwa mkuu)."""
    days = approve_interval_days(profile)
    if days <= 0:
        return 'kila siku (hakuna mwisho)'
    if days == 7:
        return 'kwa wiki 1'
    if days == 14:
        return 'kwa wiki mbili'
    if days == 28:
        return 'kwa wiki 4'
    if days % 28 == 0:
        return 'kwa miezi %d' % (days // 28)
    if days % 7 == 0:
        return 'kwa wiki %d' % (days // 7)
    return 'kwa siku %d' % days


def approve_lease_until(profile):
    """Mwisho wa kipindi cha mchakato wa moja kwa moja (None = hakuna mwisho)."""
    return getattr(profile, 'auto_lease_until', None)


def approve_lease_expired(profile, now=None) -> bool:
    """True kama kipindi cha mchakato kimekwisha (mfumo husimama)."""
    from django.utils import timezone
    until = approve_lease_until(profile)
    if until is None:
        return False
    now = now or timezone.now()
    if timezone.is_naive(until):
        until = timezone.make_aware(until, timezone.get_default_timezone())
    return now >= until


def approve_lease_active(profile, now=None) -> bool:
    """True kama mfumo unaweza kuendelea kwa moja kwa moja kwa profile hii.

    Ndani ya kipindi: verify (na kujaza) hufanyika KILA SIKU. Kipindi
    kikichisha: mfumo husimama (hakuna kujaza, hakuna verify) hadi mtumiaji
    aweke muda upya.
    """
    if not getattr(profile, 'approver_enabled', False):
        return True
    if approve_interval_days(profile) <= 0:
        return True  # 'kila siku' = hakuna mwisho
    return not approve_lease_expired(profile, now=now)


def approve_lease_days_left(profile, now=None) -> int:
    """Siku zilizobaki kwenye kipindi (-1 = hakuna kipindi/imekwisha)."""
    from django.utils import timezone
    until = approve_lease_until(profile)
    if until is None:
        return -1
    now = now or timezone.now()
    if timezone.is_naive(until):
        until = timezone.make_aware(until, timezone.get_default_timezone())
    if now >= until:
        return 0
    return (until - now).days


def start_auto_lease(profile, weeks=None, now=None):
    """Anza kipindi (lease) mpya kwa profile (muda tayari uliwekwa)."""
    from datetime import timedelta
    from django.utils import timezone
    now = now or timezone.now()
    if weeks is None:
        weeks = int(getattr(profile, 'auto_approve_weeks', 0) or 0)
    weeks = max(0, weeks)
    profile.auto_lease_set_at = now
    profile.auto_lease_until = (now + timedelta(weeks=weeks)) if weeks else None
    return profile


def _approve_auto_runs(profile_id):
    """Query ya run zote za auto-approve (zisizo dry-run)."""
    from .models import EssFillRun
    return EssFillRun.objects.filter(
        profile_id=profile_id, kind='approve', source='auto'
    ).exclude(log__startswith='[DRY-RUN]')


def approve_last_run(profile_id):
    """Run ya mwisho ya auto-approve (hata ikiwa iko 'running' au imeshindwa).

    Inafanyika kama "kiwango" cha usiku wa sasa: kama ilikuwa ikifanyika
    leo, tusingie run ya pili.
    """
    return _approve_auto_runs(profile_id).order_by('-started').first()


def approve_last_auto(profile_id, include_failed=False):
    """Run ya mwisho ya auto-approve ILIYOFANYIKA (status='done').

    Dry-runs (jaribio tu, halijakubali Verify) HUPUZWA — vinginevyo jaribio
    la [DRY-RUN] lingeangusha ratiba nzima ya wiki/ziki bila kuona.

    Pia, run iliyoshindwa (`status='error'`) haisombui ratiba: kama
    auto-approve imeshindwa (mf. Playwright/timeout), mfumo hujaribu tena
    siku inayofuata badala ya kusubiri wiki nzima.
    """
    qs = _approve_auto_runs(profile_id)
    if include_failed:
        return qs.order_by('-started').first()
    return qs.filter(status='done').order_by('-started').first()


def approve_due_for(profile, now=None) -> bool:
    """True kama ni wakati wa kuidhinisha kiotomatiki kwa profile hii.

    Ndani ya kipindi (`auto_lease_until`): kuidhinisha hufanyika KILA SIKU.
    Kipindi kikikosea: mfumo husimama (False) hadi mtumiaji aweke upya.

    Pia huzuia run ya pili siku hiyo hiyo (catch-up + ratiba hazigongani).
    """
    from django.utils import timezone
    now = now or timezone.now()
    if not approve_lease_active(profile, now=now):
        return False
    today = now.astimezone(_eat_tz()).date()
    last_run = approve_last_run(profile.id)
    if (last_run is not None and last_run.started is not None
            and last_run.status != 'error'):
        last_day = last_run.started.astimezone(_eat_tz()).date()
        if last_day >= today:
            return False  # ilikwisha endeshwa (au inaendelea) leo
    return True


def approve_next_due(profile, now=None):
    """Tarehe inayofuata ya auto-approve (leo kama bado, kesho kama tayari)."""
    from datetime import timedelta
    from django.utils import timezone
    now = now or timezone.now()
    if not approve_lease_active(profile, now=now):
        return None
    today = now.astimezone(_eat_tz()).date()
    last_run = approve_last_run(profile.id)
    if (last_run is not None and last_run.started is not None
            and last_run.status != 'error'
            and last_run.started.astimezone(_eat_tz()).date() >= today):
        return today + timedelta(days=1)
    return today


def approve_status(profile, now=None) -> dict:
    """Muhtasari wa hali ya auto-approve ya mkuu (kwa UI na diagnostics).

    Zana: {'weeks', 'interval_days', 'interval_label', 'lease_until',
    'lease_set_at', 'lease_active', 'lease_expired', 'lease_days_left',
    'due', 'next_due', 'last_auto', 'last_failed'}.
    """
    from django.utils import timezone
    now = now or timezone.now()
    last = approve_last_auto(profile.id)
    last_run = approve_last_run(profile.id)
    failed = None
    if last_run is not None and last_run.status == 'error':
        failed = last_run
    until = approve_lease_until(profile)
    expired = approve_lease_expired(profile, now=now)
    return {
        'weeks': int(getattr(profile, 'auto_approve_weeks', 0) or 0),
        'interval_days': approve_interval_days(profile),
        'interval_label': approve_interval_label(profile),
        'lease_until': until,
        'lease_set_at': getattr(profile, 'auto_lease_set_at', None),
        'lease_active': approve_lease_active(profile, now=now),
        'lease_expired': expired,
        'lease_days_left': approve_lease_days_left(profile, now=now),
        'due': approve_due_for(profile, now=now),
        'next_due': approve_next_due(profile, now=now),
        'last_auto': last,
        'last_failed': failed,
    }


@shared_task(bind=True, time_limit=120, soft_time_limit=100)
def approve_due(self):
    """Weka foleni uhidhinishaji (verify) kwa wakuu waliochaguliwa (beat).

    Hulinganisha na `auto_fill_due`: hupanga `run_ess_approve` kwa kila mkuu
    mwenye `approver_enabled=True` ambaye kipindi chake (`auto_lease_until`)
    bado kinaendelea. Hutumika na `CELERY_BEAT_SCHEDULE` (docker-compose/VPS
    yenye beat); kwenye Railway huendeshwa na kiendesha kilichopachikwa
    `ess_approve_scheduler` badala yake.
    """
    from .models import EssFillRun, TeacherProfile
    from .runstate import reap_stale_runs

    reap_stale_runs()
    today = _today_eat()
    qs = TeacherProfile.objects.filter(
        approver_enabled=True, ess_ready=True).select_related('user')
    triggered, skipped = [], []
    for prof in qs:
        if not approve_due_for(prof):
            skipped.append(prof.id)
            continue
        run = EssFillRun.objects.create(
            profile=prof, kind='approve', source='auto')
        run_ess_approve.apply_async(args=[prof.id, run.id], queue='essfill')
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


# Kichwa/sentensi kwa aina ya run (kwa arifa kwa mwenye wasifu).
_VERB_BY_KIND = {
    'fill': 'Kujaza',
    'read': 'Kusoma asilimia',
    'sync': 'Kusawazisha majina',
    'push': 'Kutuma majina',
    'approve': 'Uhidhinishaji',
}


def notify_run_result(run_id):
    """Arifa ya matokeo ya run: kwa mwenye wasifu, na kwa admins kama error.

    Inaitwa na Celery (run_ess_fill / run_ess_approve) NA kwa thread
    fallback ya `launch_run` — hivyo hupata matokeo njia zote mbili.
    """
    from .models import EssFillRun
    run = EssFillRun.objects.filter(pk=run_id).select_related('profile').first()
    if run is None or run.status not in ('done', 'error'):
        return
    verb = _VERB_BY_KIND.get(run.kind, 'Kujaza')
    _notify_run_result(run, verb=verb)
    if run.status == 'error':
        _notify_admins(run, verb=verb.lower())


def _notify_fill_result(profile_id, run_id):
    """Tuma arifa ya matokeo ya kujaza (kama notifications zimewashwa)."""
    notify_run_result(run_id)


def _result_body(run, verb: str) -> str:
    """Sentensi fupi ya arifa: matokeo (au hatua iliyovunjika + kiungo)."""
    if run.status == 'done':
        return ('%s: imeongezwa %d, sawa %d, hazikupatikana %d.'
                % (verb, run.saved, run.skipped, run.not_found))
    step = run.error_step or 'sijulikana'
    art = run.artifacts or {}
    link = ' Angalia picha: %s' % art['screenshot'] if art.get('screenshot') else ''
    return '%s kumeshindwa kwenye hatua "%s".%s' % (verb, step, link)


def _notify_run_result(run, *, verb='Kujaza'):
    """Tuma matokeo ya run kwa mwenye wasifu (done au error)."""
    from .push import push_configured, send_to_profile
    if not push_configured():
        return {'sent': 0, 'skipped': 'not-configured'}
    if run.status == 'error':
        title = f'e-Tendaji: {verb.lower()} limevunjika'
    else:
        title = f'e-Tendaji: {verb.lower()} kumekamilika'
    return send_to_profile(run.profile_id, title=title,
                           body=_result_body(run, verb),
                           url=f'/ess/fill/{run.id}/',
                           tag='ess-error' if run.status == 'error' else 'ess-done',
                           renotify=True)


def _admin_ids() -> list[int]:
    """Idadi za wasifu za maombi/admin (env `ESS_ADMIN_PROFILE_IDS`)."""
    import re
    from django.conf import settings
    raw = getattr(settings, 'ESS_ADMIN_PROFILE_IDS', '') or ''
    out = []
    for part in re.split(r'[,\s;]+', str(raw)):
        if part.strip().isdigit():
            out.append(int(part))
    return out


def _error_line(run) -> str:
    """Mstari wa hitilafu kwenye log (ERROR [...] / HITILAFU), vinginevyo wa mwisho."""
    lines = [(ln or '').strip() for ln in (run.log or '').splitlines()]
    for ln in reversed(lines):
        if ln.startswith(('ERROR', 'HITILAFU')):
            return ln[:200]
    return lines[-1][:200] if lines else ''


def _notify_admins(run, verb='kujaza'):
    """Arifa kwa admins walioorodheshwa ESS_ADMIN_PROFILE_IDS pale run
    inaposhindwa (selectors/tables za ESS zimebadilika)."""
    from .push import push_configured, send_to_profile
    if not push_configured():
        return {'sent': 0, 'skipped': 'not-configured'}
    sent = 0
    art = run.artifacts or {}
    step = run.error_step or '?'
    body = f'ESS {verb} limevunjika (run #{run.id}, hatua "{step}"): {_error_line(run)}'
    if art.get('screenshot'):
        body += f' Picha: {art["screenshot"]}'
    for pid in _admin_ids():
        if pid == run.profile_id:
            continue
        res = send_to_profile(pid, title=f'e-Tendaji: {verb} limevunjika',
                              body=body[:400], url=f'/ess/fill/{run.id}/',
                              tag='ess-admin-error', renotify=True)
        sent += res.get('sent', 0)
    return {'sent': sent}


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


@shared_task(bind=True, queue='essfill', time_limit=900, soft_time_limit=860,
             max_retries=2)
def run_ess_approve(self, profile_id, run_id):
    """Idhinisha (verify) maendeleo SUBMITTED kwa mkuu mmoja (queue='essfill').

    Lock ya mkuu huzuia uhidhinishaji mbili za mtu mmoja ziende pamoja.
    """
    from .essapprove import run_approve
    from .locks import profile_lock
    with profile_lock(profile_id) as got:
        if not got:
            raise self.retry(countdown=_retry_countdown(self, 90))
        res = run_approve(profile_id, run_id)
    notify_run_result(run_id)
    return res


@shared_task(time_limit=180, soft_time_limit=160)
def notify_fill_due():
    """Kumbusha walimu (wenye arifa) kujaza ESS siku za kujaza.

    Hutumwa tu Jumatatu–Ijumaa, kwa walimu ambao hawajajazwa leo
    (hawana run ya 'done' ya leo). Waliojibiwa tayari kiotomatiki
    hawasumbuliwi — wanapata arifa ya matokeo kwenye run_ess_fill.
    """
    from .compute import calendar_target_pct, calendar_window, entries_per_week
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
        if not _fill_day(today.weekday(), entries_per_week(prof)):
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