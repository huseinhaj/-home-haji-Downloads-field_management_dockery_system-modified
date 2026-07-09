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
    "history": "History",
    "geo": "Geography",
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


def extract_subject_columns(data_frame: pd.DataFrame) -> list[str]:
    return [column for column in data_frame.columns if column not in KNOWN_STUDENT_COLUMNS]


def parse_score(raw_score) -> Optional[int]:
    if pd.isna(raw_score):
        return None
    try:
        return int(float(raw_score))
    except (TypeError, ValueError):
        return None


def normalize_gender(raw_gender: str) -> str:
    normalized = str(raw_gender or "").strip().upper()
    if normalized.startswith("F"):
        return "F"
    return "M"


def get_grade(score):
    """NECTA CSEE (O-Level, Form 1-4) subject grade.

    IMPORTANT: These thresholds MUST stay in sync with the PDF and Excel
    display services (pdf_export_service._score_fill, excel_export_service
    _score_grade) — otherwise the points/division computed here will show
    different letter grades than what the report tables display.
    """
    if score >= 75:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def get_grade_alevel(score):
    """NECTA ACSEE (A-Level, Form 5-6) subject grade — wider 7-band scale."""
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


def get_grade_for_form(score, form):
    """Pick the right NECTA scale: ACSEE for Form 5/6, CSEE otherwise."""
    if form in (5, 6):
        return get_grade_alevel(score)
    return get_grade(score)


def is_passing_grade(grade):
    """Under both CSEE and ACSEE, F is the only failing grade."""
    return grade != "F"


GRADE_POINTS = {"A": 1, "B": 2, "C": 3, "D": 4, "F": 5}


def get_grade_points(grade):
    """NECTA CSEE point value for a subject grade (A=1 ... F=5), used to sum
    a student's total points across subjects for division classification."""
    return GRADE_POINTS.get(grade, 5)


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


def get_division(points):
    if points <= 17:
        return "I"
    if points <= 21:
        return "II"
    if points <= 25:
        return "III"
    if points <= 33:
        return "IV"
    return "0"

