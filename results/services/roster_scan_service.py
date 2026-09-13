"""Roster Scan — Academic anapiga picha au kupakia picha/PDF ya orodha ya
wanafunzi (roster) iliyochapwa/kwandikwa kwa mkono, mfumo unatumia AI
(vision model) kusoma kila mstari na kuipa Academic uhakiki kwanza
(preview/confirm) kabla ya kuhifadhi kwenye FormStudent.

Chain ni ile ile ya scoresheet OCR: OpenRouter (google/gemini-2.5-flash,
vision) -> Gemini direct HTTP (FREE fallback). Tofauti ni PROMPT tu:
hii inasoma JINA + JINSIA, si alama.
"""
from __future__ import annotations

import logging
import re

from .scoresheet_ocr_service import (
    ScoreSheetOCRError,
    _clean_row_number,
    _extract_json_array,
    _load_page_images,
    _read_page_with_ai,
)

logger = logging.getLogger(__name__)

PROMPT = (
    "This is a PHOTO of a student roster / class list — a list of student "
    "names (each line or table row has a serial number, a full name, and "
    "usually a gender letter M/F). Read EVERY row carefully and extract "
    "the student's FULL NAME and GENDER.\n\n"
    "Return ONLY a JSON array — no explanations — in this exact format:\n"
    '[{"row": 1, "name": "Halima Ally Mohamed", "gender": "F"}, '
    '{"row": 2, "name": "Juma Hamisi Ramadhani", "gender": "M"}]\n\n'
    "CRITICAL RULES — follow exactly:\n"
    "1. NAME: Copy the student's full name EXACTLY as written — all parts "
    "(first + middle + last). Do NOT cut off or abbreviate names. Do NOT "
    "translate or correct spellings.\n"
    "2. GENDER: Copy the gender letter/word on the row (M, F, Male, Female, "
    "Kike, Kiume). If the row has no gender at all, use \"M\".\n"
    "3. IGNORE headers (S/N, NAME, SEX...), titles (e.g. 'FORM ONE "
    "ATTENDANCE LIST'), dates, signatures, admission numbers like "
    "'S2475/0001', and page footers — never report a header as a student.\n"
    "4. ROW NUMBER: if the list has a printed serial number, copy it into "
    "'row'. Otherwise omit 'row'.\n"
    "5. NEVER invent names — write ONLY what you see. Every printed row "
    "with a real student name must appear exactly once.\n"
    "6. If part of the photo is blurry, still do your best for the rows "
    "you can read — do not skip readable rows."
)


class RosterScanError(ScoreSheetOCRError):
    """Same failure family as scoresheet OCR (view layer treats them alike)."""


_FEMININE_PREFIXES = ('F', 'KIKE')  # F, Female, FE, Kike — Swahili-aware


def _clean_gender(raw) -> str:
    """'F'/'Female'/'kike' → 'F'; anything else → 'M' (same default the
    file-upload parsers use). Swahili 'kike/kiume' handled explicitly —
    normalize_gender alone would turn 'kike' into M."""
    s = str(raw or '').strip().upper()
    return 'F' if s.startswith(_FEMININE_PREFIXES) else 'M'


def _clean_name(name: str) -> str:
    """Collapse whitespace, strip leading serials ('1.' '12)') and stray
    punctuation the AI sometimes copies off the sheet."""
    s = re.sub(r'\s+', ' ', str(name or '')).strip()
    s = re.sub(r'^\d+[.)]\s*', '', s).strip()
    return s


def extract_students_from_document(uploaded_file) -> list[dict]:
    """Returns [{"first": str, "middle": str, "last": str, "gender": "M"|"F",
    "row": int|None}, ...] — one entry per student the AI read off the
    photo/PDF. Names are split first/middle/last the same way
    views._parse_roster_line does for uploaded text files, so scanned and
    uploaded rosters land in FormStudent identically (same dedup keys)."""
    from results.views import GENDER_TOKENS, normalize_gender  # local: avoid import cycle at module load

    pages = _load_page_images(uploaded_file)

    rows: list[dict] = []
    last_error: Exception | None = None
    any_page_succeeded = False

    for page_num, img in enumerate(pages, 1):
        try:
            text = _read_page_with_ai(img, prompt=PROMPT)
            any_page_succeeded = True
        except Exception as exc:
            last_error = exc
            logger.warning("[RosterScan] Page %d failed: %s", page_num, exc)
            continue

        raw_rows = _extract_json_array(text)
        logger.info("[RosterScan] Page %d extracted %d raw rows", page_num, len(raw_rows))

        for item in raw_rows:
            if not isinstance(item, dict):
                continue
            full = _clean_name(item.get('name'))
            if not full or len(full) < 3:
                continue
            # Skip anything that still looks like a header/title row
            low = full.lower()
            if any(h in low for h in ('jina la', 'first name', 'last name', 'gender',
                                      'jinsia', 'attendance', 'serial', 's/n')):
                continue

            parts = full.split()
            if len(parts) == 1:
                first, middle, last = parts[0], '', 'Unknown'
            elif len(parts) == 2:
                first, middle, last = parts[0], '', parts[1]
            else:
                first, middle, last = parts[0], ' '.join(parts[1:-1]), parts[-1]

            raw_gender = str(item.get('gender') or '').strip()
            if raw_gender.lower() not in GENDER_TOKENS or not raw_gender:
                # No gender read (or garbage) — default M, consistent with uploads
                gender = 'M'
            else:
                gender = normalize_gender(raw_gender)

            rows.append({
                'first': first,
                'middle': middle,
                'last': last or 'Unknown',
                'gender': gender,
                'row': _clean_row_number(item.get('row')),
            })

    if not any_page_succeeded:
        err_detail = str(last_error) if last_error else 'unknown error'
        raise RosterScanError(
            f"Imeshindwa kusoma picha — jaribu tena.\nSababu: {err_detail}"
        ) from last_error

    if not rows:
        raise RosterScanError(
            "Hakuna jina lililotambulika kwenye picha. Hakikisha orodha iko "
            "wazi, iko sawa (straight), na mwanga unatosha — kisha jaribu tena."
        )

    # Drop exact duplicates (AI occasionally re-reads the same row twice)
    seen: set[tuple] = set()
    unique_rows: list[dict] = []
    for r in rows:
        key = (r['first'].lower(), r['middle'].lower(), r['last'].lower())
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(r)

    logger.info("[RosterScan] FINAL: %d unique students", len(unique_rows))
    return unique_rows
