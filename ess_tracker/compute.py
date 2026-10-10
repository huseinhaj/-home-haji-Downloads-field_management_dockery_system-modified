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
_MAAZIMIO_WORDS = {1: 'moja', 2: 'mawili', 3: 'matatu', 4: 'manne', 5: 'matano'}
_MITIHANI_WORDS = {1: 'mmoja', 2: 'miwili', 3: 'mitatu', 4: 'minne', 5: 'mitano',
                   6: 'sita', 7: 'saba', 8: 'nane'}
_MONTHS_SW = ['Januari', 'Februari', 'Machi', 'Aprili', 'Mei', 'Juni', 'Julai',
              'Agosti', 'Septemba', 'Oktoba', 'Novemba', 'Desemba']

# ── Templates za sub-tasks (sawa na CLI) ─────────────────────────────
SUBTASK_SPECS = [
    ('maazimio',
     'kuandaa maazimio {maazimio_neno} ya kufundishia somo la {somo} kidato cha {kidato}',
     'annual'),
    ('nukuu',
     'kuandaa nukuu {nukuu} za somo la {somo} kidato cha {kidato}',
     'annual'),
    ('maandalio',
     'kuandaa maandalio {maandalio} ya somo la {somo}',
     'periods'),
    ('zana',
     'kuandaa zana {zana} za kufundishia na kujifunzia somo la {somo} kidato cha {kidato}',
     'manual'),
    ('kufundisha',
     'kufundisha vipindi {vipindi} vya somo la {somo} kidato cha {kidato}',
     'periods'),
    ('tathmini',
     'kufanya tathmini ya maendeleo ya wanafunzi katika somo la {somo} '
     'kila baada ya tathmini ya mtihani mmoja',
     'annual'),
    ('majaribio',
     'kutoa na kusahihisha majaribio ({majaribio_pad}) ya mitihani '
     '{mitihani_neno} ya somo la {somo} kidato cha {kidato}',
     'manual'),
]

DEFAULTS = {'maazimio': 2, 'majaribio': 5, 'mitihani': 4}


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


def elapsed_weeks(task: Task, leo: date | None = None) -> float:
    leo = leo or date.today()
    weeks = weeks_between(task.start, leo)
    total = weeks_between(task.start, task.end)
    if weeks is None:
        return 0.0
    if weeks < 0:
        return 0.0
    if total is not None and weeks > total:
        return total
    return weeks


def total_weeks(task: Task) -> float | None:
    return weeks_between(task.start, task.end)


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
    return None, 'none'


def planned_fraction(task: Task, leo: date | None = None) -> float:
    """Sehemu ya muda iliyopita (0..1) kati ya kuanza na kuisha kwa Task."""
    tw = total_weeks(task)
    if not tw or tw <= 0:
        return 0.0
    return max(0.0, min(1.0, elapsed_weeks(task, leo) / tw))


def pct_auto_for(st: SubTask) -> tuple[float | None, str]:
    """Asilimia ya 'Jaza' bila mwalimu kuandika kitu.

    - Sub-task za mwaka (maazimio/nukuu/tathmini): 100%.
    - Nyingine: maendeleo ya ratiba (muda uliopita) au actual kama aliandika
      zaidi ya ratiba. Chanzo: 'annual' | 'auto'.
    """
    if st.mode == 'annual':
        return 100.0, 'annual'
    target = target_for(st)
    actual = actual_for(st)
    frac = planned_fraction(st.task)
    if target > 0:
        planned = target * _dec(round(frac, 6))
        eff = actual if actual > planned else planned
        return min(100.0, round(float(eff) / float(target) * 100.0, 2)), 'auto'
    return round(frac * 100.0, 2), 'auto'


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal('0')


def built_wanted(profile) -> list[tuple[str, float]]:
    """[(description, asilimia)] za KILA sub-task (maendeleo ya ratiba).

    Hutumika na 'Jaza': mwalimu haandiki kitu, asilimia inahesabiwa kiotomatiki.
    """
    out = []
    for task in profile.tasks.all():
        for st in task.subtasks.all():
            pct, _src = pct_auto_for(st)
            if pct is not None:
                out.append((st.description, pct))
    return out


# ── Kutengeneza sub-tasks kwa kiingilio rahisi (kama CSV) ────────────
def autogen_subtasks(somo: str, kidato: str, *,
                     maazimio: int = 2, majaribio: int = 5, mitihani: int = 4,
                     nukuu=None, maandalio=None, vipindi=None,
                     zana=None) -> list[dict]:
    """Tengeneza stakabadhi 7 za kawaida. Nambari zisizotolewa huhesabiwa
    baadaye kando ya vila_per_week/wiki."""

    def word(d, n):
        return d.get(int(n) if isinstance(n, (int, float)) else -1, str(n))

    maazimio_neno = word(_MAAZIMIO_WORDS, maazimio)
    mitihani_neno = word(_MITIHANI_WORDS, mitihani)
    try:
        majaribio_pad = f'{int(majaribio):02d}'
    except (TypeError, ValueError):
        majaribio_pad = str(majaribio)

    fmt = {
        'somo': somo, 'kidato': kidato or '',
        'maazimio': maazimio, 'nukuu': nukuu or '', 'maandalio': maandalio or '',
        'zana': zana or '', 'vipindi': vipindi or '',
        'majaribio': majaribio, 'mitihani': mitihani,
        'maazimio_neno': maazimio_neno, 'mitihani_neno': mitihani_neno,
        'majaribio_pad': majaribio_pad,
    }
    return [
        {'position': i, 'key': key, 'text': tpl.format(**fmt), 'mode': mode}
        for i, (key, tpl, mode) in enumerate(SUBTASK_SPECS, start=1)
    ]


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
_DEFAULT_MODES = {1: 'annual', 2: 'annual', 3: 'periods', 4: 'manual',
                  5: 'periods', 6: 'annual', 7: 'manual'}


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