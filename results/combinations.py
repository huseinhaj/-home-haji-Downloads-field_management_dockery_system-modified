"""National A-Level (ACSEE) subject combinations.

NECTA classifies an A-Level candidate's division from the THREE subjects of
their registered combination ONLY. Any extra subject the school also tests
is ignored — even if the student scored better in it. (Contrast CSEE /
FTNA, where the best 7 / all subjects count.)

This system has no per-student "combination" field, so the combination is
detected from the subjects a student actually has marks in: the registered
combination whose three subjects the student all sat.

    - Exactly three principal subjects (with or without the compulsory
      subsidiaries General Studies / BAM)  →  unambiguous, that IS the
      combination.
    - Four or more principal subjects that satisfy several combinations
      →  the combination is chosen CONSERVATIVELY: the one whose three
      subjects carry the HIGHEST total points, i.e. the student's best
      "extra" subject is the one left out. This is the NECTA rule the
      user asked for ("extra subject haihesabiwi ... hata kama better").
    - No combination matches (unusual subject mix, or fewer than three
      principals)  →  caller falls back to best-three principal subjects.

The combination list below is compiled from the standard Tanzania mainland
A-Level combinations (and a few common Zanzibar ones). Add any combination
a school uses that is missing — the key is the printed code, the value its
three subjects (use the canonical names from ``_CANONICAL`` values).

Sources: schoolpvh.ac.tz A-level subject combinations; wazaelimu.com
"All combination for advanced level Tanzania (Form 5 & 6)";
mabumbe.com A'level Combinations in Tanzania.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional


# Canonical subject name for every spelling / abbreviation we expect on a
# scoresheet column. Anything not listed is title-cased and used as-is
# (so it simply will not match a combination and the caller falls back).
_CANONICAL = {
    # ── Advanced Mathematics (the A-Level principal — NOT "Basic Applied
    #    Mathematics", which is a subsidiary handled elsewhere) ──
    "mathematics": "Advanced Mathematics",
    "math": "Advanced Mathematics",
    "maths": "Advanced Mathematics",
    "advanced mathematics": "Advanced Mathematics",
    "advanced maths": "Advanced Mathematics",
    "advanced math": "Advanced Mathematics",
    "adv mathematics": "Advanced Mathematics",
    "adv maths": "Advanced Mathematics",
    "a-level mathematics": "Advanced Mathematics",
    "pure mathematics": "Advanced Mathematics",
    # ── English Language vs Literature in English ──
    # These are TWO distinct A-Level subjects. "L" in HGL / HKL / KLF is
    # English Language; "Li" in HGLi is Literature in English.
    "english": "English Language",
    "english language": "English Language",
    "eng language": "English Language",
    "literature": "Literature in English",
    "literature in english": "Literature in English",
    "lit in english": "Literature in English",
    "english literature": "Literature in English",
    "lit": "Literature in English",
    # ── the rest ──
    "kiswahili": "Kiswahili",
    "kisw": "Kiswahili",
    "swahili": "Kiswahili",
    "history": "History",
    "hist": "History",
    "geography": "Geography",
    "geo": "Geography",
    "physics": "Physics",
    "phy": "Physics",
    "chemistry": "Chemistry",
    "chem": "Chemistry",
    "biology": "Biology",
    "bio": "Biology",
    "economics": "Economics",
    "econ": "Economics",
    "commerce": "Commerce",
    "comm": "Commerce",
    "accountancy": "Accountancy",
    "accounting": "Accountancy",
    "accounts": "Accountancy",
    "book keeping": "Accountancy",
    "bookkeeping": "Accountancy",
    "agriculture": "Agriculture",
    "agric": "Agriculture",
    "nutrition": "Nutrition",
    "food and nutrition": "Nutrition",
    "food and human nutrition": "Nutrition",
    "home economics": "Nutrition",
    "computer science": "Computer Science",
    "computer studies": "Computer Science",
    "computer": "Computer Science",
    "ict": "Computer Science",
    "french": "French",
    "chinese": "Chinese",
    "arabic": "Arabic",
    "islamic knowledge": "Islamic Knowledge",
    "divinity": "Divinity",
    "bible knowledge": "Divinity",
    "fine art": "Fine Art",
    "fine arts": "Fine Art",
    "art": "Fine Art",
    "physical education": "Physical Education",
    "p.e": "Physical Education",
    "pe": "Physical Education",
    "music": "Music",
    # subsidiaries — canonicalised so they collapse consistently; they
    # never appear in a combination so they can never be "counted".
    "general studies": "General Studies",
    "general study": "General Studies",
    "g/studies": "General Studies",
    "g studies": "General Studies",
    "gs": "General Studies",
    "basic applied mathematics": "Basic Applied Mathematics",
    "basic applied maths": "Basic Applied Mathematics",
    "basic applied math": "Basic Applied Mathematics",
    "applied mathematics": "Basic Applied Mathematics",
    "applied maths": "Basic Applied Mathematics",
    "bam": "Basic Applied Mathematics",
}


ACSEE_COMBINATIONS = {
    # ── Science ──────────────────────────────────────────────────────
    "PCM": ("Physics", "Chemistry", "Advanced Mathematics"),
    "PCB": ("Physics", "Chemistry", "Biology"),
    "PGM": ("Physics", "Geography", "Advanced Mathematics"),
    "PMC": ("Physics", "Advanced Mathematics", "Computer Science"),
    "CBG": ("Chemistry", "Biology", "Geography"),
    "CBA": ("Chemistry", "Biology", "Agriculture"),
    "CBN": ("Chemistry", "Biology", "Nutrition"),
    "CBM": ("Chemistry", "Biology", "Advanced Mathematics"),
    # ── Business / social science ────────────────────────────────────
    "EGM": ("Economics", "Geography", "Advanced Mathematics"),
    "ECA": ("Economics", "Commerce", "Accountancy"),
    "PGE": ("Physical Education", "Geography", "Economics"),
    # ── Arts / humanities ───────────────────────────────────────────
    "HGL": ("History", "Geography", "English Language"),
    "HGLi": ("History", "Geography", "Literature in English"),
    "HGK": ("History", "Geography", "Kiswahili"),
    "HGE": ("History", "Geography", "Economics"),
    "HKL": ("History", "Kiswahili", "English Language"),
    "KLF": ("Kiswahili", "English Language", "French"),
    "KLG": ("Kiswahili", "English Language", "Geography"),
    "KEC": ("Kiswahili", "English Language", "Chinese"),
    "KFC": ("Kiswahili", "French", "Chinese"),
    "HLF": ("History", "English Language", "French"),
    "HKF": ("History", "Kiswahili", "French"),
    "HLA": ("History", "English Language", "Arabic"),
    "HKA": ("History", "Kiswahili", "Arabic"),
    "PBF": ("Physical Education", "Biology", "Fine Art"),
}


def canon_subject(name) -> str:
    """Canonical A-Level subject name for a raw scoresheet column."""
    key = " ".join(str(name or "").strip().lower().split())
    if not key:
        return ""
    if key in _CANONICAL:
        return _CANONICAL[key]
    return " ".join(word.capitalize() for word in key.split())


def detect_acsee_combination(
    subject_names: Iterable[str],
    points_of: Callable[[str], int],
) -> Optional[tuple]:
    """Identify a student's registered A-Level combination.

    Args:
        subject_names: raw names of every subject the student has a mark
            in (subsidiaries included — they are simply never part of a
            combination).
        points_of: canonical-subject-name -> the student's NECTA point
            value for that subject (A=1 … F=7). Only ever called for
            subjects the student actually sat.

    Returns:
        ``(code, (subject1, subject2, subject3))`` with canonical subject
        names, or ``None`` when no registered combination is fully
        covered by the student's subjects.
    """
    have = {canon_subject(n) for n in subject_names}
    have.discard("")

    matches = [
        (code, subjects)
        for code, subjects in ACSEE_COMBINATIONS.items()
        if set(subjects) <= have
    ]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    # Ambiguous: the student sat 4+ principal subjects covering several
    # combinations. Pick conservatively — the combination whose three
    # subjects total the MOST points, so the student's strongest "extra"
    # subject is the one left uncounted.
    return max(matches, key=lambda m: sum(points_of(s) for s in m[1]))
