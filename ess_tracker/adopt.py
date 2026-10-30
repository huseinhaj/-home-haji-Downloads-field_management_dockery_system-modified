"""Onboarding ya ESS-native: mwalimu hapezi kitu KIMOJA tu — password ya ESS.

Mwalimu anapaswa kutoa jina la mtumiaji na password ya e-Tendaji tu. Kisha
mfumo hujipanga mwenyewe:

  1. task/sub-task na tarehe zake — kutoka ESS (`run_sync`).
  2. mode/target/vila_per_week kwa kila sub-task — kwa maandishi ya ESS.
  3. dirisha la shule (`school_open`/`school_close`) — kutoka tarehe za ESS.
  4. auto-fill, mara kwa wiki, na kipindi (mwezi 1) — ma defaults.

Mwalimu hahitaji kufungua app tena; kazi yake ya kawaida inaendelea ndani
ya ESS official, mfumo ukifanya kila kitu nyuma ya Pazia.

Kanuni: hakuna kitu kinachofutwa. Thamani zilizopo zinabaki (mwalimu au
msimamizi huwa ameweka), zilizo hazipo zinaongezwa.
"""
from datetime import date

from .compute import periods_per_week, subtask_window, weeks_between

# Maandishi ya ESS -> kitu mfumo kinachotambua. Zinatumika kwa njia
# rahisi (maneno kamili) ili 'kufundishia' isisambue na 'kufundisha'.
KEY_PATTERNS = (
    ('maazimio', ('azimio',)),
    ('nukuu', ('nukuu',)),
    ('maandalio', ('maandalio',)),
    ('zana', ('zana',)),
    ('mitihani', ('mitihani',)),
    ('majaribio', ('majaribio', 'jaribio')),
    ('kufundisha', ('kufundisha', 'vipindi')),
)

# Mipangilio inayotokana na ESS peke yake (mwalimu hawasemi chochote).
DEFAULT_ENTRIES_PER_WEEK = 3
DEFAULT_LEASE_WEEKS = 4  # mwezi 1


def classify_key(desc: str) -> str | None:
    """Ufunguo wa sub-task kutoka maandishi ya ESS (mf. 'nukuu', 'kufundisha').

    Rudi None kama maandishi hayatambuiwi.
    """
    text = (desc or '').lower()
    for key, words in KEY_PATTERNS:
        for word in words:
            if word in text:
                return key
    return None


def classify_subtask(st) -> dict:
    """Mabadiliko ya sub-task moja kwa maandishi ya ESS.

    Rudi dict ya ufields ('mode', 'target', 'vila_per_week', 'week_count')
    au tupu kama sub-task haijatambuiwa au mwalimu ameitengeneza mwenyewe.

    'nukuu' haibadilishwi: idadi ya nukuu inaendelea kwa ratiba (kama ilivyo
    kabla), na mfumo hupata lengo kutoka jina la ESS pale inapofanya.
    """
    task = st.task
    desc = st.description or ''
    key = classify_key(desc)
    if not key or key == 'nukuu':
        return {}
    if key == 'maazimio':
        return {'mode': 'annual', 'target': 1,
                'vila_per_week': 0, 'week_count': 0}
    if key in ('maandalio', 'zana', 'kufundisha'):
        vila = periods_per_week(task.somo, task.kidato) or 0
        start, end = subtask_window(st)
        weeks = int(round(weeks_between(start, end) or 0))
        return {'mode': 'periods', 'target': int(round(vila * weeks)),
                'vila_per_week': int(round(vila)), 'week_count': weeks}
    if st.events.exists():
        return {}
    return {'mode': 'manual', 'target': 0,
            'vila_per_week': 0, 'week_count': 0}


def _tuned(st) -> bool:
    """True kama mwalimu/masimamizi ameweka sub-task hii mwenyewe."""
    try:
        if st.week_count:
            return True
        if float(st.target or 0) > 0:
            return True
        if float(st.vila_per_week or 0) > 0:
            return True
    except (TypeError, ValueError):
        return True
    return False


def classify_subtasks(profile, *, force: bool = False) -> int:
    """Panga mode/target kwa sub-tasks zote za profile. Rudi idadi iliyobadilika.

    Mtu wa kwanza (walimu wa ESS-native) ndiye asiyokuwa amepanga chochote
    mwenyewe; wengine (waliopanga app) hawabadilishwi.
    """
    if not force and not getattr(profile, 'ess_native', False):
        return 0
    changed = 0
    for task in profile.tasks.all():
        for st in task.subtasks.all():
            if _tuned(st):
                continue
            fields = classify_subtask(st)
            if not fields:
                continue
            upd = {}
            for key, val in fields.items():
                if getattr(st, key) != val:
                    upd[key] = val
            if not upd:
                continue
            for key, val in upd.items():
                setattr(st, key, val)
            st.save(update_fields=list(upd.keys()))
            changed += 1
    return changed


def _ess_window(profile) -> tuple[date | None, date | None]:
    """(kufunguliwa, kufungwa) kutoka tarehe za task/sub-task za ESS."""
    starts, ends = [], []
    for task in profile.tasks.all():
        if task.start:
            starts.append(task.start)
        if task.end:
            ends.append(task.end)
        for st in task.subtasks.all():
            if st.start:
                starts.append(st.start)
            if st.end:
                ends.append(st.end)
    if not starts and not ends:
        return None, None
    return (min(starts) if starts else None, max(ends) if ends else None)


def provision_profile(profile, *, emit=None, force: bool = False) -> dict:
    """Panga profile ya mwalimu kutoka ESS peke yake.

    Hudhibiti: mode/target ya sub-tasks, dirisha la shule, mara kwa wiki.
    Haishughuliki kipindi (lease) — hilo ni kazi ya mkuu wa shule.

    Rudi muhtasari: {'classified': int, 'window': (open, close)|None,
    'entries_per_week': int, 'notes': [str]}
    """
    notes = []

    def _say(msg):
        notes.append(msg)
        if emit:
            emit(msg)

    classified = classify_subtasks(profile, force=force)
    if classified:
        _say(f'Sub-tasks zilizopangwa kiotomatiki: {classified}.')

    open_d, close_d = _ess_window(profile)
    if open_d and close_d:
        changed = False
        if not profile.school_open:
            profile.school_open = open_d
            changed = True
        if not profile.school_close:
            profile.school_close = close_d
            changed = True
        if changed:
            profile.save(update_fields=['school_open', 'school_close'])
            _say(f'Dirisha la shule: {open_d} — {close_d} (kutoka ESS).')
    else:
        _say('ESS haikuwa na tarehe za kuangalia dirisha la shule.')

    if not profile.entries_per_week:
        profile.entries_per_week = DEFAULT_ENTRIES_PER_WEEK
        profile.save(update_fields=['entries_per_week'])
        _say(f'Jazo limewekwa: mara {DEFAULT_ENTRIES_PER_WEEK} kwa wiki.')

    return {'classified': classified,
            'window': (profile.school_open, profile.school_close),
            'entries_per_week': profile.entries_per_week,
            'notes': notes}
