"""
Capture Score — karatasi ZILIZOSAHIHISHWA tayari na mwalimu → scoresheet.

Mwalimu anasahihisha mitihani kwa mkono, anaweka karatasi kwenye ADF ya
printer, kisha anabonyeza "Capture Scores" kwenye Marks Entry. Bridge
inascan, na hapa kwa kila ukurasa AI inasoma TU:
  - reg number (admission no) ya mwanafunzi
  - jina (kama msaada wa matching)
  - alama ya jumla ambayo mwalimu ameiandika juu ya karatasi
Hakuna kusahihisha — alama ni ile mwalimu aliyoandika.

Kisha mfumo unalinganisha reg number ya karatasi na reg number za
wanafunzi (FormStudent.admission_no) walio kwenye orodha ya Marks Entry,
na kurudisha payload ya muundo ule ule wa scoresheet_extract_status:
  {"matched": [...], "unmatched": [...], "missing": [...], "warnings": [...]}
ili frontend ijaze jedwali kwa njia ile ile. Mwalimu bado anakagua na
kubonyeza "Hifadhi" — hakuna kinachohifadhiwa moja kwa moja.
"""
from __future__ import annotations

import difflib
import logging
import re

from .ai_grader import (
    AIGradeError,
    GOOGLE_API_KEY,
    OPENROUTER_API_KEY,
    _call_gemini_multi,
    _call_openrouter_multi,
    _extract_json_object,
    _jpeg_bytes,
    _norm_name,
)

logger = logging.getLogger(__name__)

PROMPT = """You will receive ONE scanned page of a student's exam paper that a
teacher has ALREADY MARKED by hand. Do NOT grade anything.

Read ONLY the student details and the teacher's final score:
- reg_number: the student's registration / admission / exam number written on
  the paper (e.g. "S0451/0023", "2451", "F4-017"). Copy it exactly.
- student_name: the student's name as written.
- score: the TOTAL mark the teacher wrote for the paper (often in red ink,
  circled, in a marks box, or written like "45/100" or "45%"). Copy the number
  EXACTLY as written, keep decimals ("10.5"). Do NOT add up the question marks
  yourself and do NOT correct the teacher's total.
- max_score: the number after "/" if the teacher wrote one (e.g. 50 in
  "38/50"), otherwise null.

If the teacher crossed out a total and wrote a new one, use the new one and set
unclear=true. If any digit of the reg number or score is hard to read, give
your best reading and set unclear=true with a short reason.
If this page has no student details and no total (an inner/continuation page),
set has_header=false.

Return ONLY a JSON object — no markdown, no explanations — exactly:
{"has_header": true, "reg_number": "S0451/0023", "student_name": "Amina Juma",
 "score": "45", "max_score": null, "unclear": false, "unclear_reason": ""}
"""


def read_paper_header(image_bytes: bytes) -> dict:
    """Soma reg number + jina + alama ya jumla kutoka ukurasa mmoja.

    Chain ile ile ya ai_grader: OpenRouter (Gemini) → Gemini direct.
    Inatoa AIGradeError kama zote zimeshindikana.
    """
    images = [_jpeg_bytes(image_bytes)]
    errors = []
    if OPENROUTER_API_KEY:
        try:
            return _extract_json_object(_call_openrouter_multi(images, PROMPT))
        except Exception as exc:
            errors.append(f"openrouter: {exc}")
            logger.warning("[ScoreCapture] OpenRouter failed: %s", exc)
    if GOOGLE_API_KEY:
        try:
            return _extract_json_object(_call_gemini_multi(images, PROMPT))
        except Exception as exc:
            errors.append(f"gemini: {exc}")
            logger.warning("[ScoreCapture] Gemini failed: %s", exc)
    raise AIGradeError("; ".join(errors) or "Hakuna AI provider imewekwa")


# ---------------- Matching ----------------

def norm_reg(reg) -> str:
    """"S0451/0023", "s0451-0023 ", "S 0451 0023" → "S04510023"."""
    return re.sub(r"[^A-Z0-9]", "", str(reg or "").upper())


def reg_map_for_roster(exam, roster_ids) -> dict:
    """{norm_reg: Student id} kwa wanafunzi wa orodha ya Marks Entry.

    Reg number zinakaa kwenye FormStudent (orodha ya Mtaaluma) lakini
    ExamResult/Marks Entry zinatumia Student — daraja ni lile lile la
    marks_entry._student_from_form_student (jina la kwanza + la mwisho).
    """
    from ..marks_entry import _student_from_form_student
    from ..models import FormStudent, Student

    if not exam.school_id:
        return {}
    form_students = [
        fs for fs in FormStudent.objects.filter(
            school=exam.school, form=exam.form,
            is_active=True, academic_year=exam.year,
        ).exclude(admission_no__isnull=True).exclude(admission_no='')
    ]
    if not form_students:
        return {}

    by_name = {}
    for s in Student.objects.filter(
        first_name__in={fs.first_name for fs in form_students},
        last_name__in={fs.last_name or 'Unknown' for fs in form_students},
    ):
        by_name.setdefault((s.first_name, s.last_name), []).append(s)

    wanted = set(roster_ids)
    cache = {}
    out = {}
    for fs in form_students:
        key = (fs.first_name, fs.last_name or 'Unknown')
        if key not in by_name:
            # Hayupo kama Student bado → hawezi kuwa kwenye orodha ya
            # Marks Entry; usitengeneze Student mpya kwa ajili ya lookup tu.
            continue
        student = _student_from_form_student(fs, _cache=cache, _candidates=by_name)
        if student.id in wanted:
            out[norm_reg(fs.admission_no)] = student.id
    return out


def _match_by_reg(reg: str, reg_map: dict):
    """(student_id, confidence) au (None, 0).

    1. Sawa kabisa (baada ya kusafisha) → 1.0
    2. AI ilisoma sehemu ya mwisho tu (mf. "0023" ya "S0451/0023") na
       reg MOJA tu inaishia hivyo → 0.85 (mwalimu aone mstari wa njano)
    """
    if not reg:
        return None, 0.0
    if reg in reg_map:
        return reg_map[reg], 1.0
    if len(reg) >= 3:
        hits = {sid for r, sid in reg_map.items() if r.endswith(reg) or reg.endswith(r)}
        if len(hits) == 1:
            return hits.pop(), 0.85
    return None, 0.0


def _match_by_name(name: str, roster: list):
    nname = _norm_name(name)
    if not nname:
        return None, 0.0
    best, best_score = None, 0.0
    for s in roster:
        full = _norm_name(s.get('name'))
        if not full:
            continue
        if full == nname:
            return s['id'], 0.95
        toks = [t for t in nname.split() if len(t) > 1]
        if toks and all(t in full.split() for t in toks):
            ratio = 0.9
        else:
            ratio = difflib.SequenceMatcher(None, nname, full).ratio()
        if ratio > best_score:
            best, best_score = s['id'], ratio
    return (best, round(best_score, 4)) if best_score >= 0.82 else (None, 0.0)


def _score_value(raw):
    """Alama kama namba ya JSON (int ikiwa haina desimali), au None."""
    from ..utils import parse_mark

    val = parse_mark(raw, max_value=None)
    if val is None:
        return None
    return int(val) if val == val.to_integral_value() else float(val)


def build_capture_payload(reads: list, roster: list, reg_map: dict) -> dict:
    """Unganisha usomaji wa kila ukurasa na orodha ya wanafunzi.

    reads: [{"page": 1, "sheet_id": 12 | None, "read": {...} | None, "error": ""}]
    roster: [{"id": <Student id>, "name": "..."}]  (orodha ya Marks Entry)
    reg_map: {norm_reg: Student id}  (reg_map_for_roster)
    """
    names = {s['id']: s.get('name', '') for s in roster}
    matched, unmatched, warnings = [], [], []
    seen = {}          # student_id → page ya karatasi ya kwanza
    skipped_pages = []
    failed_pages = []

    for item in reads:
        page = item.get('page')
        read = item.get('read')
        if read is None:
            failed_pages.append(page)
            continue
        if read.get('has_header') is False:
            skipped_pages.append(page)
            continue

        raw_reg = str(read.get('reg_number') or '').strip()
        raw_name = str(read.get('student_name') or '').strip()
        raw_score = str(read.get('score') if read.get('score') is not None else '').strip()
        label = ' — '.join(p for p in [raw_reg, raw_name] if p) or f'Ukurasa #{page}'
        score = _score_value(raw_score)

        sid, conf = _match_by_reg(norm_reg(raw_reg), reg_map)
        how = 'reg'
        if sid is None:
            sid, conf = _match_by_name(raw_name, roster)
            how = 'name'
        if sid is None or sid not in names:
            unmatched.append({
                'raw_name': label, 'score': raw_score, 'is_absent': False,
                'sheet_id': item.get('sheet_id'), 'page': page,
            })
            continue

        if sid in seen:
            warnings.append(
                f'Karatasi mbili za {names[sid]} (ukurasa #{seen[sid]} na #{page}) — '
                f'ya pili haijatumika, kagua.'
            )
            unmatched.append({
                'raw_name': f'{label} (karatasi ya pili ya {names[sid]})',
                'score': raw_score, 'is_absent': False,
                'sheet_id': item.get('sheet_id'), 'page': page,
            })
            continue
        seen[sid] = page

        reasons = []
        if read.get('unclear'):
            reasons.append(str(read.get('unclear_reason') or 'AI haikuwa na uhakika'))
        if score is None:
            reasons.append('Alama haisomeki kwenye karatasi')
        elif score > 100:
            reasons.append('Alama zaidi ya 100 — thibitisha')
        max_score = _score_value(read.get('max_score'))
        if max_score not in (None, 100):
            reasons.append(f'Alama imeandikwa kati ya {max_score}, si 100')
        if how == 'name':
            reasons.append('Reg number haikulingana — imelinganishwa kwa jina')

        matched.append({
            'id': sid,
            'score': score if score is not None else '',
            'is_absent': False,
            'raw_name': label,
            'confidence': conf,
            'is_new': False,
            'is_special_case': bool(reasons),
            'special_reason': '; '.join(reasons)[:200],
            'raw_mark': raw_score,
            'sheet_id': item.get('sheet_id'),
            'page': page,
        })

    if skipped_pages:
        warnings.append(
            f'Kurasa {len(skipped_pages)} hazikuwa na reg number wala alama '
            f'(huenda ni kurasa za ndani) — zimerukwa: #'
            + ', #'.join(map(str, skipped_pages[:15]))
        )
    if failed_pages:
        warnings.append(
            f'AI imeshindwa kusoma kurasa {len(failed_pages)}: #'
            + ', #'.join(map(str, failed_pages[:15])) + ' — jaza alama zao mwenyewe.'
        )

    missing = [
        {'id': s['id'], 'name': s.get('name', '')}
        for s in roster if s['id'] not in seen
    ]
    return {'matched': matched, 'unmatched': unmatched, 'missing': missing, 'warnings': warnings}
