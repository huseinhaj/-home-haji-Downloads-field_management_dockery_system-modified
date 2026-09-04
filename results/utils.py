from __future__ import annotations

from typing import Optional

import pandas as pd
from django.core.exceptions import ValidationError


KNOWN_STUDENT_COLUMNS = {
    "Registration Number",
    "First Name",
    "Middle Name",
    "Last Name",
    "Gender",
}

SUBJECT_NAME_MAP = {
    "phy": "Physics",
    "physics": "Physics",
    "chem": "Chemistry",
    "chemistry": "Chemistry",
    "bio": "Biology",
    "biology": "Biology",
    "math": "Mathematics",
    "mathematics": "Mathematics",
    "hist": "History",
    "history": "History",
    # "Historia ya Tanzania na Maadili" (new O-Level curriculum subject) is
    # a SEPARATE subject from plain History — keep the two apart so they do
    # not both collapse to "History" (and both abbreviate to "HIST").
    "historia ya tanzania na maadili": "Historia ya Tanzania na Maadili",
    "historia ya tanzania na maadili ya uraia": "Historia ya Tanzania na Maadili",
    "historia ya tanzania": "Historia ya Tanzania na Maadili",
    "history of tanzania and ethics": "Historia ya Tanzania na Maadili",
    "history of tanzania & ethics": "Historia ya Tanzania na Maadili",
    "maadili": "Historia ya Tanzania na Maadili",
    "maadili ya uraia": "Historia ya Tanzania na Maadili",
    "hist/m": "Historia ya Tanzania na Maadili",
    "hist / m": "Historia ya Tanzania na Maadili",
    "hist-m": "Historia ya Tanzania na Maadili",
    "hist m": "Historia ya Tanzania na Maadili",
    "histm": "Historia ya Tanzania na Maadili",
    "htm": "Historia ya Tanzania na Maadili",
    "hte": "Historia ya Tanzania na Maadili",
    "geo": "Geography",
    "geog": "Geography",
    "geography": "Geography",
    "cre": "CRE",
    "civics": "Civics",
    "kisw": "Kiswahili",
    "kiswahili": "Kiswahili",
    "english": "English",
    "computer": "Computer Studies",
    "agriculture": "Agriculture",
    "business": "Business Studies",
    "further math": "Further Mathematics",
}

# Short code shown in the compact results grid (the PDF truncates a bare
# name to 4 letters, which makes "History" and "Historia ya Tanzania na
# Maadili" both read as "HIST"). A subject with a code here renders by its
# code instead; add entries as new clashes appear.
SUBJECT_CODES = {
    "History": "HIST",
    "Historia ya Tanzania na Maadili": "HIST/M",
}

SUPPORTED_EXTENSIONS = (".xlsx", ".xls", ".csv")


def load_results_dataframe(uploaded_file) -> pd.DataFrame:
    file_name = uploaded_file.name.lower()
    if not file_name.endswith(SUPPORTED_EXTENSIONS):
        raise ValidationError("Unsupported file format. Please upload .xlsx, .xls, or .csv.")

    if file_name.endswith((".xlsx", ".xls")):
        data_frame = pd.read_excel(uploaded_file)
    else:
        data_frame = pd.read_csv(uploaded_file)

    data_frame.columns = [str(column).strip() for column in data_frame.columns]
    return data_frame


def normalize_subject_name(subject_name: str) -> str:
    return SUBJECT_NAME_MAP.get(subject_name.strip().lower(), subject_name.strip())


# When one upload carries the SAME subject twice (a school that teaches
# both History and Historia ya Tanzania na Maadili exports two columns,
# often both headed "HIST" — pandas then reads them as "HIST" / "HIST.1"),
# the second occurrence is renamed. Known pair first, then a plain "(2)".
_REPEATED_SUBJECT_SECOND_NAME = {
    "History": "Historia ya Tanzania na Maadili",
}

_DEDUP_SUFFIX = None  # compiled lazily to keep import time light


def _strip_pandas_dedup_suffix(column_name: str) -> str:
    """`"HIST.1"` / `"History.2"` (pandas' rename of duplicate headers) → base."""
    global _DEDUP_SUFFIX
    if _DEDUP_SUFFIX is None:
        import re
        _DEDUP_SUFFIX = re.compile(r"\.\d+$")
    return _DEDUP_SUFFIX.sub("", str(column_name)).strip()


def resolve_subject_columns(subject_columns):
    """Map raw scoresheet column headers to distinct subject names.

    Returns ``[(column_name, subject_name), ...]`` preserving input order.
    A subject that appears more than once in the same file is disambiguated
    so its columns never collapse onto one Subject row:
        - the 2nd "History" column  → "Historia ya Tanzania na Maadili"
        - any other repeat          → "<name> (2)", "(3)", …
    """
    resolved = []
    counts = {}
    for column_name in subject_columns:
        base = _strip_pandas_dedup_suffix(column_name)
        name = normalize_subject_name(base)
        counts[name] = counts.get(name, 0) + 1
        occurrence = counts[name]
        if occurrence >= 2:
            if occurrence == 2 and name in _REPEATED_SUBJECT_SECOND_NAME:
                name = _REPEATED_SUBJECT_SECOND_NAME[name]
            else:
                name = f"{name} ({occurrence})"
        resolved.append((column_name, name))
    return resolved


def extract_subject_columns(data_frame: pd.DataFrame) -> list[str]:
    return [column for column in data_frame.columns if column not in KNOWN_STUDENT_COLUMNS]


def parse_score(raw_score) -> Optional[int]:
    """Parse a score value from a scoresheet cell.

    Returns:
        int   — numeric score (0–100+)
        None  — empty / missing cell (student does NOT study this subject)

    Special handling:
        'X', 'ABS', 'absent', '-' → treated as empty (None)
        We do NOT return a score for absent — instead, the caller
        checks for 'X' separately via ``is_absent_marker``.
    """
    if pd.isna(raw_score):
        return None
    raw_str = str(raw_score).strip()
    if raw_str.upper() in ('X', 'ABS', 'ABSENT', '-'):
        return None  # caller should check is_absent_marker()
    try:
        return int(float(raw_str))
    except (TypeError, ValueError):
        return None


def is_absent_marker(raw_score) -> bool:
    """Check if a raw scoresheet value is an absent marker (X, ABS, etc.).

    Returns True when the teacher explicitly marked a student as absent
    for this subject — meaning the student studies the subject but did
    not sit for this particular exam.
    """
    if pd.isna(raw_score):
        return False
    return str(raw_score).strip().upper() in ('X', 'ABS', 'ABSENT')


def normalize_gender(raw_gender: str) -> str:
    normalized = str(raw_gender or "").strip().upper()
    if normalized.startswith("F"):
        return "F"
    return "M"


def safe_get_or_create_subject(name):
    """Get-or-create a Subject by name, tolerating pre-existing duplicates.

    If duplicate Subject rows share the same name, ``get_or_create``
    raises ``MultipleObjectsReturned``.  This helper catches that case,
    keeps the oldest record, deletes the extras, and returns the winner.

    The name is run through ``normalize_subject_name`` first, so callers
    that pass a raw alias ("HIST/M", "Maadili", "phy") land on the same
    canonical Subject. Also stamps the known short code (SUBJECT_CODES) on
    the row, filling it in on rows that pre-date the code."""
    from .models import Subject
    name = normalize_subject_name(str(name))
    try:
        subject, _ = Subject.objects.get_or_create(name=name)
    except Subject.MultipleObjectsReturned:
        subject = Subject.objects.filter(name=name).order_by('id').first()
        # Delete duplicates
        Subject.objects.filter(name=name).exclude(id=subject.id).delete()

    code = SUBJECT_CODES.get(name)
    if code and (subject.code or '') != code:
        subject.code = code
        subject.save(update_fields=['code'])
    return subject


def get_grade(score):
    """NECTA CSEE (O-Level, Form 1-4) subject grade — 5-band scale.

    Official NECTA CSEE grading (verified against real 2022/2024 CSEE
    result slips on onlinesys.necta.go.tz — subject grades there are only
    ever A/B/C/D/F, never B+/C+):
        A: 75-100  (1 point)
        B: 65-74   (2 points)
        C: 45-64   (3 points)
        D: 30-44   (4 points)
        F: 0-29    (5 points)

    IMPORTANT: These thresholds MUST stay in sync with the PDF and Excel
    display services (pdf_export_service._grading_thresholds/_grade_point,
    excel_export_service._grade_thresholds) — otherwise the points/division
    computed here will show different letter grades than what the report
    tables display.
    """
    if score is None:
        return "X"
    if score >= 75:
        return "A"
    if score >= 65:
        return "B"
    if score >= 45:
        return "C"
    if score >= 30:
        return "D"
    return "F"


def get_grade_alevel(score):
    """NECTA ACSEE (A-Level, Form 5-6) subject grade — wider 7-band scale."""
    if score is None:
        return "X"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 50:
        return "D"
    if score >= 40:
        return "E"
    if score >= 35:
        return "S"
    return "F"


def get_grade_ftna(score):
    """NECTA FTNA (Form Two National Assessment) subject grade.

    Official FTNA scale differs from CSEE: C starts at 45, D at 30, F below 30.
        A: 75-100  B: 65-74  C: 45-64  D: 30-44  F: 0-29
    """
    if score is None:
        return "X"
    if score >= 75:
        return "A"
    if score >= 65:
        return "B"
    if score >= 45:
        return "C"
    if score >= 30:
        return "D"
    return "F"


def get_grade_for_form(score, form):
    """Pick the right NECTA scale for the exam's form level:

    - Form 2 (FTNA):        A 75+ | B 65+ | C 45+ | D 30+ | F <30
    - Form 5/6 (ACSEE):     A 80+ | B 70+ | C 60+ | D 50+ | E 40+ | S 35+ | F <35
    - Form 1/3/4 (CSEE):    A 75+ | B 65+ | C 45+ | D 30+ | F <30
    """
    if score is None:
        return "X"
    if form == 2:
        return get_grade_ftna(score)
    if form in (5, 6):
        return get_grade_alevel(score)
    return get_grade(score)


def is_passing_grade(grade):
    """Under both CSEE and ACSEE, F is the only failing grade."""
    return grade != "F"


# ── ACSEE subsidiary subjects ────────────────────────────────────────────
# General Studies and Basic Applied Mathematics (BAM) are the compulsory
# SUBSIDIARY subjects at A-Level. NECTA never counts them toward the ACSEE
# division — that is built from the three PRINCIPAL subjects only. (They do
# count toward a student's TCU university-admission points, but that is a
# separate calculation this system does not do.)
#
# Verified against real ACSEE 2025 result slips (onlinesys.necta.go.tz):
# a candidate with BAM-C (3 pts) outscoring Biology-E (5 pts) still had
# Physics + Chemistry + Biology counted for the division (AGGT 13, Div III)
# — BAM and General Studies ignored.
_ACSEE_SUBSIDIARY_SUBJECTS = {
    "general studies", "generalstudies", "general study",
    "gs", "g/studies", "g studies", "g/study",
    "basic applied mathematics", "basic applied maths",
    "basic applied math", "applied mathematics", "applied maths",
    "bam",
}


def is_acsee_subsidiary_subject(subject_name) -> bool:
    """True for General Studies / Basic Applied Mathematics — the A-Level
    subsidiary subjects NECTA excludes from the ACSEE division points.

    Note: "Advanced Mathematics" (a real principal subject) is deliberately
    NOT matched — only the "applied"/"basic applied" forms are subsidiary.
    """
    key = " ".join(str(subject_name or "").strip().lower().split())
    return key in _ACSEE_SUBSIDIARY_SUBJECTS


GRADE_POINTS = {"A": 1, "B": 2, "C": 3, "D": 4, "F": 5}

# ACSEE (A-Level) has two extra bands (E, S) so F carries a higher point value
_ACSEE_POINTS = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "S": 6, "F": 7}


def get_grade_points(grade, form=None):
    """NECTA point value for a subject grade, used to sum a student's
    total points across subjects for division classification.

    CSEE (Form 1-4): A=1, B=2, C=3, D=4, F=5
    ACSEE (Form 5-6): A=1, B=2, C=3, D=4, E=5, S=6, F=7
    """
    if form in (5, 6):
        return _ACSEE_POINTS.get(grade, 7)
    return GRADE_POINTS.get(grade, 5)


# ── Exam dropdown grouping ────────────────────────────────────────────────
# Order ya aina za mitihani kwenye dropdown ya "Chagua Mtihani": mwalimu
# anatarajia kuona Terminal → Midterm → Test → Quiz → Annual → Mock →
# Monthly → (December/Competition) → Other, si mpangilio wa alphabet.
EXAM_TYPE_ORDER = [
    'PRE_NECTA', 'MOCK', 'PRE_MOCK', 'INTERSCHOOL',
    'JOINT', 'DISTRICT_JOINT', 'REGION_JOINT', 'ZONE_JOINT',
    'TERMINAL', 'MIDTERM', 'TEST', 'QUIZ', 'ANNUAL', 'MONTHLY',
    'OTHER',
]


def group_exams_by_type(exams, label_map):
    """Group an exam queryset by exam type, in the dropdown order teachers
    expect (Terminal first ... Other last). Returns
    [(code, label, [exam, ...]), ...] with only non-empty groups, each
    sorted newest year first then by name. Unknown types fall into 'OTHER'.
    """
    buckets = {code: [] for code in EXAM_TYPE_ORDER}
    for e in exams:
        code = e.exam_type if e.exam_type in buckets else 'OTHER'
        buckets[code].append(e)
    groups = []
    for code in EXAM_TYPE_ORDER:
        bucket = buckets[code]
        if not bucket:
            continue
        bucket.sort(key=lambda e: (-e.year, e.name))
        groups.append((code, label_map.get(code, code), bucket))
    return groups


def parse_name_score_sheet(uploaded_file) -> list[tuple[str, int]]:
    """Parse a simple 'Name, Score' CSV/Excel sheet for ad-hoc/personal uploads."""
    data_frame = load_results_dataframe(uploaded_file)
    col_lower = {str(c).strip().lower(): c for c in data_frame.columns}

    name_col = next(
        (col_lower[k] for k in ('name', 'jina', 'full name', 'jina kamili', 'student', 'jina la mwanafunzi') if k in col_lower),
        data_frame.columns[0],
    )
    score_col = next(
        (col_lower[k] for k in ('score', 'alama', 'marks', 'mark', 'result') if k in col_lower),
        None,
    )
    if score_col is None:
        numeric_cols = [c for c in data_frame.columns if pd.to_numeric(data_frame[c], errors='coerce').notna().any()]
        score_col = numeric_cols[-1] if numeric_cols else None
    if score_col is None:
        raise ValidationError("Hakuna safu ya alama iliyopatikana. Tumia jina kama 'Score' au 'Alama'.")

    rows: list[tuple[str, int]] = []
    for _, row in data_frame.iterrows():
        name = str(row.get(name_col, '')).strip()
        if not name or name in ('nan', 'None'):
            continue
        score = parse_score(row.get(score_col))
        if score is None:
            continue
        rows.append((name, score))
    return rows


def get_division(points, form=None):
    """NECTA division from accumulated grade points.

    CSEE (Form 1/3/4, 7 subjects, points range 7–35 since grades are only
    A-F, 1-5 points each — see get_grade()):
        I:   7–17
        II:  18–21
        III: 22–25
        IV:  26–33
        0:   34–35

    Verified empirically against 169+ real candidate records pulled from
    official NECTA CSEE result slips (onlinesys.necta.go.tz, 2022 and 2024
    exams) — every points total from 7 to 35 was cross-checked against its
    printed division, with a clean boundary at 33→IV / 34→0.

    ACSEE (Form 5/6, 3 subjects, points range 3–21):
        I:   3–9
        II:  10–12
        III: 13–17
        IV:  18–19
        0:   20–21

    Was previously CSEE-only regardless of form — an A-level student with
    3 subjects averaging D (12 points) fell under the CSEE "≤17 = Division
    I" band and was wrongly graded top division; a student who failed all
    3 (21 points) landed in "18-21 = Division II" instead of the fail
    division (0). The two scales scale with a completely different number
    of subjects (3 vs 7) and can't share one set of cutoffs.
    """
    if form in (5, 6):
        if points <= 9:
            return "I"
        if points <= 12:
            return "II"
        if points <= 17:
            return "III"
        if points <= 19:
            return "IV"
        return "0"
    if points <= 17:
        return "I"
    if points <= 21:
        return "II"
    if points <= 25:
        return "III"
    if points <= 33:
        return "IV"
    return "0"

