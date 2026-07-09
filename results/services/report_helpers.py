"""
report_helpers.py — Shared helpers for PDF and Excel report generation.

Centralises Tanzania-brand colour palette, school-level detection (primary
vs. secondary), full school-name formatting, and language selection so that
PDF and Excel reports stay consistent with one another.
"""

from __future__ import annotations

# ── Tanzania Flag Colours ────────────────────────────────────────────────────
#   Green  #1EB53A  —  Uso wa nchi / Agriculture
#   Yellow #FCD116  —  Madini / Minerals
#   Black  #000000  —  Wananchi / Citizens
#   Blue   #00A3DD  —  Bahari / Indian Ocean
#   Gold   #D9A441  —  Accent (legacy, kept for secondary elements)

TZ_GREEN  = "FF1EB53A"
TZ_YELLOW = "FFFCD116"
TZ_BLACK  = "FF000000"
TZ_BLUE   = "FF00A3DD"
TZ_GOLD   = "FFD9A441"
TZ_WHITE  = "FFFFFFFF"
TZ_LIGHT_GREY = "FFF2F4F7"
TZ_DARK_GREY  = "FF555555"

# For reportlab (PDF) — HexColor objects
def get_school_type_for_exam(exam):
    """Determine whether this exam is for a Primary or Secondary school.

    Returns 'secondary' by default (most schools using this system are
    secondary).  Checks, in order:
    1. The exam.school_name text for keywords
    2. The linked field_app.models.School (via results.School.source_school_id)
    3. The exam.form number (≥5 suggests advanced secondary, not primary)
    """
    # 1. Check school_name text
    name = (exam.school_name or '').lower()
    if any(kw in name for kw in ('primary', 'msingi', 'standard')):
        return 'primary'
    if any(kw in name for kw in ('secondary', 'sekondari', 'high school', 'form')):
        return 'secondary'

    # 2. Try to look up field_app School via source_school_id
    if exam.school_id and exam.school and exam.school.source_school_id:
        try:
            from field_app.models import School as FieldSchool
            field_school = FieldSchool.objects.get(pk=exam.school.source_school_id)
            return (field_school.level or 'secondary').lower()
        except Exception:
            pass

    # 3. Heuristic: Form 1-6 are secondary; there is no "Form" in primary
    if exam.form and exam.form >= 1:
        return 'secondary'

    return 'secondary'


def get_full_school_name(exam):
    """Return the full school name including 'Secondary School' or
    'Primary School' if not already present.

    Examples:
        'KWADELO SECONDARY SCHOOL'
        'KWADELO PRIMARY SCHOOL'
        'KWADELO' (no change if type unknown)
    """
    raw = exam.school_name or ''
    if exam.school and not raw:
        raw = exam.school.name

    raw = raw.strip()
    if not raw:
        return 'SCHOOL NAME UNKNOWN'

    upper = raw.upper()
    # Already has a suffix?
    if any(upper.endswith(suffix) for suffix in
           ('SECONDARY SCHOOL', 'PRIMARY SCHOOL', 'SCHOOL', 'ACADEMY',
            'SEMINARY', 'INSTITUTE', 'COLLEGE')):
        return upper

    school_type = get_school_type_for_exam(exam)
    if school_type == 'primary':
        return f'{upper} PRIMARY SCHOOL'
    return f'{upper} SECONDARY SCHOOL'


def get_report_language(exam):
    """Return 'en' for secondary schools, 'sw' for primary schools."""
    school_type = get_school_type_for_exam(exam)
    return 'en' if school_type == 'secondary' else 'sw'


def get_report_label(exam):
    """Return the exam-type label in the appropriate language.

    Secondary → English (e.g. 'TERMINAL EXAMINATION RESULTS')
    Primary   → Swahili (e.g. 'MATOKEO YA MTIHANI WA MWISHO WA MUHULA')
    """
    lang = get_report_language(exam)
    etype = exam.get_exam_type_display().upper()
    school_type = get_school_type_for_exam(exam)

    if lang == 'sw':
        type_map = {
            'TEST': 'MTIHANI WA MAJARIBIO',
            'COMPETITION': 'MTIHANI WA MASHINDANO',
            'TERMINAL': 'MTIHANI WA MWISHO WA MUHULA',
            'MIDTERM': 'MTIHANI WA KATI YA MUHULA',
            'DECEMBER': 'MTIHANI WA DESEMBA',
            'ANNUAL': 'MTIHANI WA MWAKA',
            'OTHER': 'MTIHANI',
        }
        exam_label = type_map.get(etype, etype)
        return f'MATOKEO YA {exam_label} {exam.year}'
    else:
        if school_type != 'primary':
            return f'{etype} EXAMINATION RESULTS'
        else:
            type_map = {
                'TEST': 'TEST',
                'COMPETITION': 'COMPETITION',
                'TERMINAL': 'END OF TERM',
                'MIDTERM': 'MIDTERM',
                'DECEMBER': 'DECEMBER',
                'ANNUAL': 'ANNUAL',
                'OTHER': '',
            }
            label = type_map.get(etype, etype)
            return f'{label} EXAMINATION RESULTS'


def get_section_title(exam, section_key: str) -> str:
    """Return localised section heading."""
    lang = get_report_language(exam)
    titles = {
        'division_summary': {
            'en': 'DIVISION SUMMARY',
            'sw': 'MUHTASARI WA DARAJA',
        },
        'subject_stats': {
            'en': 'SUBJECT STATISTICS',
            'sw': 'TAKWIMU ZA MASOMO',
        },
        'top_students': {
            'en': 'TOP 5 PERFORMERS',
            'sw': 'WANAFUNZI BORA 5',
        },
        'full_results': {
            'en': 'FULL RESULTS',
            'sw': 'MATOKEO KAMILI',
        },
        'grading_key': {
            'en': 'GRADING KEY',
            'sw': 'UFUNGUO WA DARAJA',
        },
    }
    return titles.get(section_key, {}).get(lang, section_key)
