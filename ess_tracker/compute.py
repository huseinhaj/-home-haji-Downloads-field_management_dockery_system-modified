"""Hesabu za e-Utendaji (zimehamishwa kutoka ess_utendaji.py v2).

Mantiki ni sawa na CLI: kutengeneza maandishi ya sub task, target, actual,
na asilimia. Kwenye app, actual = actual_base + jumla ya WeekEntry.
"""
import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from .models import SubTask, Task

# ── Namba -> maneno ya Kiswahili ─────────────────────────────────────
_SW_ONES = ['', 'moja', 'mbili', 'tatu', 'nne', 'tano', 'sita', 'saba', 'nane', 'tisa']
_SW_TENS = ['', 'kumi', 'ishirini', 'thelathini', 'arobaini', 'hamsini', 'sitini',
            'sabini', 'themanini', 'tisini']
_MONTHS_SW = ['Januari', 'Februari', 'Machi', 'Aprili', 'Mei', 'Juni', 'Julai',
              'Agosti', 'Septemba', 'Oktoba', 'Novemba', 'Desemba']


def _sw_below_100(n: int) -> str:
    if n < 10:
        return _SW_ONES[n]
    if n == 10:
        return 'kumi'
    if n < 20:
        return 'kumi na ' + _SW_ONES[n - 10]
    tens, ones = divmod(n, 10)
    return _SW_TENS[tens] + (' na ' + _SW_ONES[ones] if ones else '')


def swahili_number(value) -> str:
    """Namba (0..999999) -> maneno ya Kiswahili.

    mf. 936 -> 'mia tisa thelathini na sita'; 4 -> 'nne'; 600 -> 'mia sita'.
    """
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    if n < 0:
        return 'hasi ' + swahili_number(-n)
    if n == 0:
        return 'sifuri'
    parts = []
    if n >= 1000:
        th, n = divmod(n, 1000)
        parts.append('elfu ' + swahili_number(th))
    if n >= 100:
        hu, n = divmod(n, 100)
        parts.append('mia ' + _SW_ONES[hu])
    if n:
        parts.append(_sw_below_100(n))
    return ' '.join(parts)


def count_phrase(value) -> str:
    """'mia tisa thelathini na sita(936)' — tupu kama hakuna idadi."""
    if value in (None, '', 0, '0'):
        return ''
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    if n <= 0:
        return ''
    return f'{swahili_number(n)}({n})'


# ── Templates za sub-tasks (kwa mfano wa ESS halisi) ─────────────────
# (key, template, mode): {somo}{kidato_p} hujazwa; {*_p} = idadi kwa
# maneno+tarakimu (mf. 'mia tisa thelathini na sita(936)') au tupu.
SUBTASK_SPECS = [
    ('maazimio',
     'Kuandaa azimio la kazi la somo la {somo}{kidato_p}',
     'annual'),
    ('nukuu',
     'Kuandaa nukuu {nukuu_p} za somo la {somo}{kidato_p} kwa kila mada husika',
     'manual'),
    ('maandalio',
     'Kuandaa maandalio {maandalio_p}',
     'periods'),
    ('zana',
     'Kuandaa zana {zana_p} za kufundishia na kujifunzia somo la {somo}{kidato_p}',
     'periods'),
    ('kufundisha',
     'Kufundisha vipindi {vipindi_p} na kutoa zoezi kwa kila kipindi',
     'periods'),
    ('mitihani',
     'Kutoa, kuashisha na kufanya tathmini ya matokeo ya mitihani {mitihani_p}',
     'manual'),
    ('majaribio',
     'Kutoa, kuashisha na kufanya tathmini ya matokeo ya majaribio {majaribio_p}',
     'manual'),
]

DEFAULTS = {'maazimio': 1, 'majaribio': 6, 'mitihani': 4}

# ── Vipindi kwa wiki (Mtaala Mpya wa Elimu ya Sekondari, 2023) ───────
# Chanzo: TIE, "Mtaala wa Elimu ya Sekondari Kidato cha I - IV" (2023),
# Jedwali Na. 5 (Masomo ya Msingi na Lazima) na Jedwali Na. 6 (Masomo
# Chaguzi). Mwaka wa masomo = siku 194 = wiki 39 (mihula miwili); kila
# muhula wiki 2 hutumika kwa upimaji wa ndani; kipindi = dakika 40.
WEEKS_PER_YEAR = 39
SCHOOL_DAYS_PER_YEAR = 194
ASSESSMENT_WEEKS_PER_YEAR = 4          # wiki 2 kwa kila muhula
TEACHING_WEEKS_PER_YEAR = WEEKS_PER_YEAR - ASSESSMENT_WEEKS_PER_YEAR
PERIOD_MINUTES = 40

# jina la somo -> (vipindi Kidato I–II, vipindi Kidato III–IV)
SUBJECT_PERIODS_WEEK = {
    # Jedwali Na. 5 — Masomo ya Msingi na Lazima
    'mathematics': (5, 5), 'hisabati': (5, 5),
    'kiswahili': (4, 4),
    'english language': (5, 5), 'english': (5, 5), 'kiingereza': (5, 5),
    'business studies': (3, 3), 'elimu ya biashara': (3, 3), 'biashara': (3, 3),
    'geography': (2, 3), 'jiografia': (2, 3),
    'historia ya tanzania na maadili': (3, 3),
    # Jedwali Na. 6 — Masomo Chaguzi
    'physics': (3, 4), 'fizikia': (3, 4),
    'chemistry': (3, 4), 'kemia': (3, 4),
    'biology': (3, 4), 'baiolojia': (3, 4),
    'agriculture': (5, 5), 'kilimo': (5, 5),
    'computer science': (4, 4), 'computer studies': (4, 4),
    'sayansi ya kompyuta': (4, 4),
    'food and human nutrition': (5, 5), 'chakula na lishe': (5, 5),
    'sport studies': (4, 4), 'michezo': (4, 4),
    'textile and garment construction': (5, 5), 'ushoni': (5, 5),
    'fine art': (4, 4), 'sanaa': (4, 4),
    'theatre arts': (4, 4), 'sanaa bunifu': (4, 4),
    'additional mathematics': (0, 3), 'hisabati ya ziada': (0, 3),
    'literature in english': (0, 2),
    'fasihi ya kiswahili': (0, 2),
    'french': (3, 3), 'kifaransa': (3, 3),
    'arabic': (3, 3), 'kiarabu': (3, 3),
    'chinese': (3, 3), 'kichina': (3, 3),
    'music': (4, 4), 'muziki': (4, 4),
    'history': (3, 4), 'historia': (3, 4),
    'book-keeping': (3, 4), 'book keeping': (3, 4), 'uhasibu': (3, 4),
    'bible knowledge': (3, 3), 'elimu ya dini ya kikristo': (3, 3),
    'dini ya kiislamu': (3, 3), 'elimu ya dini ya kiislamu': (3, 3),
}

_UPPER_FORM_HINTS = ('3', '4', 'iii', 'iv', 'tatu', 'nne', 'three', 'four')


def _is_upper_form(kidato) -> bool:
    """Kidato cha III/IV (kidato cha tatu/nne, III, IV, 3, 4)."""
    k = str(kidato or '').strip().lower()
    return any(h in k for h in _UPPER_FORM_HINTS)


def periods_per_week(somo, kidato=None):
    """Vipindi kwa wiki kwa somo (Mtaala Mpya 2023).

    Hurejesha Kidato III–IV kama kidato ni cha juu, vinginevyo I–II.
    None kama somo haijulikani kwenye jedwali.
    """
    row = SUBJECT_PERIODS_WEEK.get(str(somo or '').strip().lower())
    if row is None:
        return None
    lo, up = row
    v = up if _is_upper_form(kidato) else lo
    return v or None


def periods_per_year(somo, kidato=None, weeks=TEACHING_WEEKS_PER_YEAR):
    """Vipindi kwa mwaka = vipindi/wiki x wiki za kufundisha (mf. 35)."""
    pww = periods_per_week(somo, kidato)
    return pww * weeks if pww else None


def _to_number(val):
    if val is None:
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return val
    s = str(val).strip().replace('%', '').replace(',', '')
    if not s:
        return None
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


_DATE_FORMATS = ['%b %d, %Y', '%B %d, %Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y',
                 '%d-%b-%Y', '%d %b %Y', '%d %B %Y', '%b %d %Y', '%Y/%m/%d',
                 '%d.%m.%Y', '%Y.%m.%d']


def parse_date(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    try:
        from dateutil import parser
        return parser.parse(s, dayfirst=False).date()
    except Exception:
        return None


def weeks_between(a, b) -> float | None:
    if a is None or b is None:
        return None
    return (b - a).days / 7.0


def _window(task: Task) -> tuple[date | None, date | None]:
    """Dirisha la mwaka: tarehe ya shule ikiwekwa (Wasifu), vinginevyo za Task."""
    profile = getattr(task, 'profile', None)
    if profile is not None and profile.school_open and profile.school_close:
        return profile.school_open, profile.school_close
    return task.start, task.end


def elapsed_weeks(task: Task, leo: date | None = None) -> float:
    leo = leo or date.today()
    start, end = _window(task)
    weeks = weeks_between(start, leo)
    total = weeks_between(start, end)
    if weeks is None:
        return 0.0
    if weeks < 0:
        return 0.0
    if total is not None and weeks > total:
        return total
    return weeks


def total_weeks(task: Task) -> float | None:
    start, end = _window(task)
    return weeks_between(start, end)


def topics_fraction(task: Task) -> float | None:
    """Sehemu ya mada zilizofundishwa (0..1) au None kama hazijawekwa."""
    total = getattr(task, 'topics_total', 0) or 0
    taught = getattr(task, 'topics_taught', 0) or 0
    if total > 0:
        return max(0.0, min(1.0, taught / total))
    return None


def holiday_days(profile, start, end) -> int:
    """Jumla ya siku za likizo zilizochaguliwa ndani ya kipindi [start, end]."""
    if not (start and end):
        return 0
    total = 0
    for h in profile.holidays.all():
        s = max(h.start_date, start)
        e = min(h.end_date, end)
        if e >= s:
            total += (e - s).days + 1
    return total


def school_days(profile) -> int | None:
    """Siku za shule = 194 za mtaala huku zikitolewa likizo zilizochaguliwa.

    Likizo hupimwa ndani ya dirisha la mwaka wa shule (kufungua..kufunga).
    """
    if not (profile.school_open and profile.school_close):
        return None
    return max(0, SCHOOL_DAYS_PER_YEAR
               - holiday_days(profile, profile.school_open, profile.school_close))


# ── Target / Actual / Asilimia ───────────────────────────────────────
def target_for(st: SubTask) -> Decimal:
    if st.mode == 'periods':
        return _dec(st.vila_per_week) * _dec(st.week_count or 0)
    return _dec(st.target)


def actual_for(st: SubTask) -> Decimal:
    total = _dec(st.actual_base)
    for entry in st.entries.all():
        total += _dec(entry.amount)
    return total


def expected_for(st: SubTask) -> Decimal | None:
    """Kinachotarajiwa kwenda kwa sasa (periods mode): vila x wiki zilizopita."""
    if st.mode == 'periods':
        task = st.task
        rel = elapsed_weeks(task)
        if rel > 0:
            return (_dec(st.vila_per_week) * _dec(round(rel, 2))).quantize(Decimal('0.01'))
    return None


def pct_for(st: SubTask) -> tuple[float | None, str]:
    """Rudi (asilimia, chanzo). Chanzo: 'annual' | 'computed' | 'none'."""
    target = target_for(st)
    actual = actual_for(st)
    if st.mode == 'annual':
        return 100.0, 'annual'
    if target > 0 and actual >= target:
        return 100.0, 'computed'
    if target > 0:
        return round(float(actual) / float(target) * 100.0 + 1e-9, 2), 'computed'
    frac = topics_fraction(st.task)
    if frac is not None:
        return round(frac * 100.0, 2), 'topics'
    return None, 'none'


def planned_fraction(task: Task, leo: date | None = None) -> float:
    """Sehemu ya muda iliyopita (0..1) kati ya kuanza na kuisha kwa Task."""
    tw = total_weeks(task)
    if not tw or tw <= 0:
        return 0.0
    return max(0.0, min(1.0, elapsed_weeks(task, leo) / tw))


def entries_per_week(profile) -> int:
    """Mara ngapi kwa wiki mfumo unatarajia kiingilio (2 au 3)."""
    try:
        return max(1, int(getattr(profile, 'entries_per_week', 3) or 3))
    except (TypeError, ValueError):
        return 3


def schedule_units(task: Task) -> tuple[float, int] | None:
    """(wiki zote, viingilio kwa wiki) vya mwaka wa Task, au None."""
    tw = total_weeks(task)
    if not tw or tw <= 0:
        return None
    return tw, entries_per_week(task.profile)


def increment_pct(task: Task) -> float | None:
    """Asilimia inayoongezwa kwa KILA kiingilio = 100 / (wiki x viingilio/wiki)."""
    su = schedule_units(task)
    if su is None:
        return None
    tw, epw = su
    total = tw * epw
    return round(100.0 / total, 4) if total > 0 else None


def entry_fraction(st: SubTask, leo: date | None = None) -> float:
    """Sehemu ya ratiba ya viingilio (0..1).

    Kila kiingilio huongeza 100/(wiki x entries_per_week) asilimia. Hapa
    hulinganisha viingilio halisi vya sub task (WeekEntry) na vile
    vinavyotarajiwa kufikia sasa (wiki zilizopita x entries_per_week).
    """
    su = schedule_units(st.task)
    if su is None:
        return 0.0
    tw, epw = su
    total = tw * epw
    if total <= 0:
        return 0.0
    expected_now = elapsed_weeks(st.task, leo) * epw
    made = st.entries.count()
    return max(0.0, min(1.0, max(made, expected_now) / total))


def pct_auto_for(st: SubTask) -> tuple[float | None, str]:
    """Asilimia ya 'Jaza' bila mwalimu kuandika kitu.

    - Sub-task ya mwaka (maazimio): 100%.
    - Nyingine: ratiba ya viingilio (entries_per_week) au actual kama
      aliandika zaidi ya ratiba. Chanzo: 'annual' | 'schedule' | 'topics'.
    """
    if st.mode == 'annual':
        return 100.0, 'annual'
    target = target_for(st)
    actual = actual_for(st)
    frac = entry_fraction(st)
    if target > 0:
        planned = target * _dec(round(frac, 6))
        eff = actual if actual > planned else planned
        return min(100.0, round(float(eff) / float(target) * 100.0, 2)), 'schedule'
    topics = topics_fraction(st.task)
    if topics is not None:
        return round(topics * 100.0, 2), 'topics'
    return round(frac * 100.0, 2), 'schedule'


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal('0')


_NOTE_LEADS = {
    1: 'Nimeandaa azimio la kazi',
    2: 'Nimeandaa nukuu',
    3: 'Nimeandaa maandalio',
    4: 'Nimeandaa zana',
    5: 'Nimefundisha vipindi',
    6: 'Nimetoa na kusahihisha mitihani',
    7: 'Nimetoa na kusahihisha majaribio',
}


def implementation_note_with(st: SubTask, actual) -> str:
    """Sentensi ya kile kilichofanyika kwa idadi maalum (actual)."""
    lead = _NOTE_LEADS.get(st.position, 'Nimetekeleza')
    target = target_for(st)
    if target and target > 0:
        return (f'{lead} {float(actual):g} kati ya '
                f'{float(target):g} kikamilifu')
    return f'{lead} kikamilifu'


def implementation_note(st: SubTask) -> str:
    """Sentensi ya kile kilichofanyika (description ya entry ya ESS).

    Mf. 'Nimefundisha vipindi 292 kati ya 432 kikamilifu'.
    """
    return implementation_note_with(st, actual_for(st))


# Namba za Kiswahili (kwa kusoma description za ESS zilizopita).
_SW_NUM = {
    'moja': 1, 'mmoja': 1, 'mmoja': 1, 'mawili': 2, 'miwili': 2, 'mbili': 2,
    'matatu': 3, 'tatu': 3, 'manne': 4, 'nne': 4, 'matano': 5, 'tano': 5,
    'sita': 6, 'saba': 7, 'nane': 8, 'tisa': 9, 'kumi': 10,
}
# Neno la funguo kwa kila nafasi ya sub-task.
_POS_KEYWORDS = {
    1: ('azimio',), 2: ('nukuu',), 3: ('maandalio',), 4: ('zana',),
    5: ('vipindi',), 6: ('tathmini',),
    7: ('majaribio', 'jaribio', 'mitihani', 'mtihani'),
}


def parse_count(desc: str, position: int | None) -> int | None:
    """Toa idadi iliyotajwa kwenye description ya ESS (kwa nafasi ya sub-task).

    Mf. 'Majaribio mawili na mitihani miwili ...' -> 2 (nafasi 7).
    """
    if not desc:
        return None
    text = desc.lower()
    keywords = _POS_KEYWORDS.get(position, ())
    if not keywords:
        return None
    for kw in keywords:
        for m in re.finditer(r'\b' + re.escape(kw) + r'\b', text):
            tail = text[m.end():m.end() + 24].strip()
            digit = re.match(r'(\d+)', tail)
            if digit:
                return int(digit.group(1))
            word = re.match(r'([a-z\u00c0-\u024f]+)', tail)
            if word and word.group(1) in _SW_NUM:
                return _SW_NUM[word.group(1)]
    return None


def entry_from_values(st: SubTask, target, base_pct,
                      prev_actual=None) -> tuple[str, float]:
    """(description, asilimia) kutoka target/base_pct (BILA DB).

    Hutumika ndani ya context ya Playwright (async) ambapo ORM haiwezi
    kuitwa. actual = idadi kubwa kati ya entries za nyuma (prev_actual) na
    ile ya ratiba (target x base_pct), isiyozidi target. asilimia = actual/target.
    """
    try:
        target = float(target or 0)
    except (TypeError, ValueError):
        target = 0.0
    base_pct = float(base_pct or 0.0)
    if target > 0:
        planned = round(target * base_pct / 100.0)
        actual = max(planned, int(prev_actual or 0))
        actual = int(min(actual, int(target)))
        pct = round(100.0 * actual / target, 2)
        return implementation_note_with(st, actual), pct
    return implementation_note_with(st, int(prev_actual or 0)), round(base_pct, 2)


def entry_for_ess(st: SubTask, prev_actual=None) -> tuple[str, float]:
    """(description, asilimia) ya entry mpya ya ESS (inagusa DB)."""
    base_pct, _src = pct_auto_for(st)
    return entry_from_values(st, target_for(st), base_pct, prev_actual)


def built_wanted(profile) -> list[tuple[SubTask, str, str, float, float]]:
    """[(sub-task, jina, description, asilimia, target)] za KILA sub-task.

    Hukokotolewa KABLA ya Playwright ili ndani ya context ya async tusiguse
    ORM. description inaweza kubadilishwa baada ya kusoma entries za nyuma.
    """
    out = []
    for task in profile.tasks.all():
        for st in task.subtasks.all():
            pct, _src = pct_auto_for(st)
            if pct is not None:
                out.append((st, st.description, implementation_note(st), pct,
                            float(target_for(st))))
    return out


# ── Kutengeneza sub-tasks kwa kiingilio rahisi (kama CSV) ────────────
def autogen_subtasks(somo: str, kidato: str, *,
                     maazimio: int = 1, majaribio: int = 6, mitihani: int = 4,
                     nukuu=None, maandalio=None, vipindi=None,
                     zana=None) -> list[dict]:
    """Tengeneza sub-tasks 7 za kawaida (kwa mfano wa ESS halisi).

    Idadi inayoonekana kwenye maandishi hujazwa kwa maneno+tarakimu, mf.
    'Kufundisha vipindi mia tisa thelathini na sita(936) ...'. Idadi
    isiyotolewa huacha nafasi tupu (maandishi ya jumla) na target
    huhesabiwa baadaye kando ya vila_per_week/wiki.
    """
    fmt = {
        'somo': somo,
        'kidato_p': f' kidato cha {kidato}' if kidato else '',
        'nukuu_p': count_phrase(nukuu),
        'maandalio_p': count_phrase(maandalio),
        'zana_p': count_phrase(zana),
        'vipindi_p': count_phrase(vipindi),
        'mitihani_p': count_phrase(mitihani),
        'majaribio_p': count_phrase(majaribio),
    }
    out = []
    for i, (key, tpl, mode) in enumerate(SUBTASK_SPECS, start=1):
        text = re.sub(r'\s+', ' ', tpl.format(**fmt)).strip()
        out.append({'position': i, 'key': key, 'text': text, 'mode': mode})
    return out


# ── Kusoma CSV aina ya masomo_sample_v2.csv ─────────────────────────
NUMERIC_COLS = ['maazimio', 'nukuu', 'maandalio', 'zana', 'vipindi', 'majaribio',
                'mitihani', 'maazimio_actual', 'nukuu_actual', 'maandalio_actual',
                'zana_actual', 'vipindi_actual', 'tathmini_actual', 'majaribio_actual',
                'vipindi_kwa_wiki', 'wiki', *[f'asilimia_{i}' for i in range(1, 8)]]


def _norm_key(k: str) -> str:
    return re.sub(r'\s+', '_', (k or '').strip().lower())


def parse_csv_text(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    cleaned = []
    for raw in reader:
        row = {_norm_key(k): (v.strip() if isinstance(v, str) else v)
               for k, v in raw.items() if k is not None}
        if not row.get('somo'):
            continue
        for col in NUMERIC_COLS:
            if col in row:
                row[col] = _to_number(row[col])
        cleaned.append(row)
    return cleaned


def create_task_from_row(profile, row: dict):
    """Tengeneza Task + SubT asks kutoka safu moja ya CSV (kama build_plan v2)."""
    somo = str(row.get('somo') or '').strip()
    kidato = str(row.get('kidato') or '').strip()
    anza = parse_date(row.get('tarehe_anza'))
    mwisho = parse_date(row.get('tarehe_mwisho'))
    if not anza or not mwisho:
        return None
    leo = parse_date(row.get('tarehe_leo')) or date.today()

    total_weeks = _to_number(row.get('wiki'))
    if total_weeks is None:
        total_weeks = weeks_between(anza, mwisho)
    rel = weeks_between(anza, leo)
    if total_weeks is not None and rel is not None:
        rel = min(rel, total_weeks)
    if rel is not None and rel < 0:
        rel = 0.0

    pww = _to_number(row.get('vipindi_kwa_wiki'))
    period_target = int(round(pww * total_weeks)) if (pww and total_weeks) else None
    period_actual = int(round(pww * rel)) if (pww and rel is not None) else None

    nums = dict(DEFAULTS)
    for col in ('maazimio', 'nukuu', 'maandalio', 'zana', 'vipindi', 'majaribio',
                'mitihani'):
        if row.get(col) is not None:
            nums[col] = row[col]
    for col in ('nukuu', 'maandalio', 'vipindi'):
        if row.get(col) is None and period_target is not None:
            nums[col] = period_target

    name = str(row.get('task') or '').strip()
    if not name:
        tail = _sw_month_year(mwisho) or str(mwisho)
        name = (f'kutekeleza majukumu ya ufundishaji na ujifunzaji wa somo la '
                f'{somo} mpaka ifikapo {tail}')

    task = Task.objects.create(
        profile=profile, name=name, somo=somo, kidato=kidato,
        start=anza, end=mwisho)

    specs = autogen_subtasks(somo, kidato,
                             maazimio=nums.get('maazimio'),
                             majaribio=nums.get('majaribio') or 0,
                             mitihani=nums.get('mitihani'),
                             nukuu=nums.get('nukuu'),
                             maandalio=nums.get('maandalio'),
                             vipindi=nums.get('vipindi'),
                             zana=nums.get('zana'))
    for item in specs:
        mode = _mode_for(item['position'], row)
        target = nums.get(_SPEC_TARGET_COL[item['position'] - 1])
        actual_col = _SPEC_ACTUAL_COL[item['position'] - 1]
        actual = row.get(actual_col)
        if actual is None and item['position'] in (3, 5) and period_actual is not None:
            actual = period_actual
        vila = _to_number(row.get('vipindi_kwa_wiki')) or 0
        wc = int(round(total_weeks)) if total_weeks else 0
        SubTask.objects.create(
            task=task, position=item['position'], description=item['text'],
            mode=mode, target=_to_number(target) or 0,
            vila_per_week=vila, week_count=wc,
            actual_base=actual or 0)
    return task


_SPEC_TARGET_COL = ['maazimio', 'nukuu', 'maandalio', 'zana', 'vipindi',
                    'mitihani', 'majaribio']
_SPEC_ACTUAL_COL = ['maazimio_actual', 'nukuu_actual', 'maandalio_actual',
                    'zana_actual', 'vipindi_actual', 'tathmini_actual',
                    'majaribio_actual']
_DEFAULT_MODES = {1: 'annual', 2: 'manual', 3: 'periods', 4: 'periods',
                  5: 'periods', 6: 'manual', 7: 'manual'}


def _mode_for(idx: int, row: dict) -> str:
    raw = row.get(f'mode_{idx}')
    if raw is not None and str(raw).strip():
        m = str(raw).strip().lower()
        if m in ('100', 'mwaka', 'annual'):
            return 'annual'
        if m in ('periods', 'wiki', 'vipindi'):
            return 'periods'
        if m in ('manual', 'actual', 'target'):
            return 'manual'
    return _DEFAULT_MODES[idx]


def _sw_month_year(d) -> str:
    if d is None:
        return ''
    return f'{_MONTHS_SW[d.month - 1]} {d.year}'