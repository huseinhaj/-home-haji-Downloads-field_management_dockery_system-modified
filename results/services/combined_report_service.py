"""Ripoti ya muhula — kuunganisha mitihani miwili kwa wastani.

Shule hufanya mtihani wa kati ya muhula na mtihani wa mwisho wa muhula.
Report card ya mwanafunzi inapaswa kuonyesha wastani wa mitihani hiyo
miwili, sio mtihani mmoja pekee:

    * Muhula wa kwanza  : Machi (3)  + Juni (6)
    * Muhula wa pili    : Septemba (9) + Novemba/Desemba (11/12)

Mchanganyiko huu ni wa REPORT TU — hakuna ExamResult/ProcessedResult
inayohifadhiwa upya. Data ya awali inabaki kama ilivyo; tunaunda payload
ya muda (in-memory) yenye alama zilizowekwa wastani, kisha PDF builder ya
kawaida inachora report card kwa payload hiyo.
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count

from ..combinations import canon_subject, detect_acsee_combination
from ..models import Exam, ExamResult
from ..utils import (
    get_division,
    get_grade_for_form,
    get_grade_points,
    is_acsee_subsidiary_subject,
)

# Mwezi wa mtihani -> miezi ya mwenza wake ndani ya muhula mmoja.
# Desemba hupendelewa kuliko Novemba kwa muhula wa pili.
TERM_PAIRS = {
    3: (6,),
    6: (3,),
    9: (12, 11),
    11: (9,),
    12: (9,),
}

# Aina ya mtihani inayotarajiwa kwa mwezi husika — hutumika kuchagua
# mwenza sahihi pale kuna mitihani zaidi ya mmoja kwenye mwezi mmoja.
_MONTH_TYPE_PREFERENCE = {
    3: ['MIDTERM', 'MONTHLY', 'TEST'],
    6: ['TERMINAL', 'ANNUAL', 'TEST'],
    9: ['MIDTERM', 'MONTHLY', 'TEST'],
    11: ['TERMINAL', 'ANNUAL', 'TEST'],
    12: ['TERMINAL', 'ANNUAL', 'TEST'],
}

_DIVISION_SUBJECT_COUNT = {1: 7, 2: 7, 3: 7, 4: 7, 5: 3, 6: 3}
_DIVISION_ORDER = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, '0': 5, 'INC': 6, 'ABS': 7}


def _exam_month(exam):
    return exam.date.month if exam.date else None


def find_partner_exam(exam):
    """Mweza wa mtihani huu ndani ya muhula (au None).

    Huchagua Exam ya shule hiyo hiyo, mwaka huo, form/stream hiyo hiyo,
    yenye tarehe kwenye mwezi wa mwenza na yenye matokeo. Aina ya mtihani
    inayotarajiwa kwa mwezi huo hupendelewa (mf. TERMINAL kwa Desemba),
    kisha tarehe ya karibuni zaidi.
    """
    month = _exam_month(exam)
    if month not in TERM_PAIRS or not exam.school_id:
        return None

    target_months = TERM_PAIRS[month]
    prefs = _MONTH_TYPE_PREFERENCE.get(target_months[0], [])

    candidates = list(
        Exam.objects.filter(
            school_id=exam.school_id,
            year=exam.year,
            form=exam.form,
            stream=exam.stream,
            date__month__in=target_months,
        )
        .exclude(pk=exam.pk)
        .exclude(date__isnull=True)
        .annotate(_n_results=Count('examresult'))
        .filter(_n_results__gt=0)
    )
    if not candidates:
        return None

    def _pref(exam_type):
        try:
            return prefs.index(exam_type)
        except ValueError:
            return len(prefs)

    def _month_pref(c):
        try:
            return target_months.index(c.date.month)
        except ValueError:
            return len(target_months)

    candidates.sort(
        key=lambda c: (
            _month_pref(c),
            _pref(c.exam_type),
            -c.date.toordinal(),
            -c.id,
        )
    )
    return candidates[0]


def _subject_key(subject):
    """Ufunguo wa kuunganisha somo kati ya mitihani miwili."""
    cname = canon_subject(subject.name)
    return cname or ' '.join((subject.name or '').strip().lower().split())


def _best_first(item):
    """(subject, score, points) — bora kwanza (points chini, alama juu)."""
    return (item[2], -item[1])


def build_combined_payload(exam, partner=None):
    """Rudisha payload ya wastani wa mitihani miwili, au None.

    Payload:
        partner             — Exam ya mwenza
        scores_by_student   — {student_id: {subject_id: combined_score}}
        subjects_by_student — {student_id: [Subject, ...]}
        summary_by_student  — {student_id: {total_score, average_score,
                              points, division, position, subject_count}}
        subject_ranks       — {subject_id: {student_id: rank}}
        total_students      — idadi ya wanafunzi
    """
    if partner is None:
        partner = find_partner_exam(exam)
    if partner is None:
        return None

    rows = list(
        ExamResult.objects.filter(exam__in=[exam, partner])
        .select_related('student', 'subject')
    )
    if not rows:
        return None

    students = {}
    subject_by_key = {}
    # per_exam[exam_id][student_id][subject_key] = ExamResult
    per_exam = defaultdict(lambda: defaultdict(dict))
    for er in rows:
        students[er.student_id] = er.student
        key = _subject_key(er.subject)
        if not key:
            continue
        # Prefer the downloaded exam's own Subject row for display.
        if key not in subject_by_key or er.exam_id == exam.id:
            subject_by_key[key] = er.subject
        per_exam[er.exam_id][er.student_id][key] = er

    scores_by_student = {}
    subjects_by_student = {}
    summary_by_student = {}

    for student_id, student in students.items():
        student_scores = {}
        student_subjects = {}
        for key, subject in subject_by_key.items():
            collected = []
            for exam_id in (exam.id, partner.id):
                er = per_exam.get(exam_id, {}).get(student_id, {}).get(key)
                if er is None:
                    continue
                if er.is_absent or er.score is None:
                    continue
                collected.append(float(er.score))
            if not collected:
                continue
            combined = round(sum(collected) / len(collected), 2)
            student_scores[subject.id] = combined
            student_subjects[subject.id] = subject

        subjects = sorted(student_subjects.values(), key=lambda s: s.name)
        scores_by_student[student_id] = student_scores
        subjects_by_student[student_id] = subjects
        summary_by_student[student_id] = _compute_summary(
            exam, subjects, student_scores,
        )

    _rank_students(exam, summary_by_student)

    subject_ranks = {}
    scored_by_subject = defaultdict(list)
    for student_id, scores in scores_by_student.items():
        for subject_id, score in scores.items():
            scored_by_subject[subject_id].append((score, student_id))
    for subject_id, pairs in scored_by_subject.items():
        pairs.sort(key=lambda p: -p[0])
        subject_ranks[subject_id] = {
            student_id: idx + 1 for idx, (_score, student_id) in enumerate(pairs)
        }

    return {
        'partner': partner,
        'scores_by_student': scores_by_student,
        'subjects_by_student': subjects_by_student,
        'summary_by_student': summary_by_student,
        'subject_ranks': subject_ranks,
        'total_students': len(summary_by_student),
    }


def _compute_summary(exam, subjects, scores):
    """Hesabu jumla/wastani/points/division kwa alama zilizowekwa wastani."""
    is_primary = bool(exam.school and exam.school.is_primary)
    form = exam.form
    sat = [s for s in subjects if s.id in scores]
    subject_count = len(sat)

    if not sat:
        return {
            'total_score': 0,
            'average_score': 0.0,
            'points': 0,
            'division': '' if is_primary else 'ABS',
            'position': None,
            'subject_count': 0,
        }

    best_n = 999 if is_primary else _DIVISION_SUBJECT_COUNT.get(form, 7)
    combo_code = ''
    acsee_principal_count = None

    if form in (5, 6):
        by_canon = {}
        for subj in sat:
            cname = canon_subject(subj.name)
            if not cname:
                continue
            score = scores[subj.id]
            pts = get_grade_points(
                get_grade_for_form(score, form), form=form,
            )
            if cname not in by_canon or pts < by_canon[cname][2]:
                by_canon[cname] = (subj, score, pts)

        combo = detect_acsee_combination(
            by_canon.keys(), lambda n: by_canon[n][2],
        )
        if combo:
            combo_code, combo_subjects = combo
            graded = sorted(
                (by_canon[s] for s in combo_subjects if s in by_canon),
                key=_best_first,
            )
        else:
            principal = [
                pair for cname, pair in by_canon.items()
                if not is_acsee_subsidiary_subject(cname)
            ]
            graded = sorted(principal, key=_best_first)[:best_n]
        acsee_principal_count = len(graded)
    else:
        graded = sorted(
            (
                (
                    subj,
                    scores[subj.id],
                    get_grade_points(
                        get_grade_for_form(
                            scores[subj.id], form, primary=is_primary,
                        ),
                        form=form,
                    ),
                )
                for subj in sat
            ),
            key=_best_first,
        )

    best = graded[:best_n]
    points = sum(item[2] for item in best)
    total = sum(item[1] for item in best)
    counted_n = len(best)
    average = (total / counted_n) if counted_n else 0.0

    division = '' if is_primary else get_division(points, form=form)

    if form in (1, 2, 3, 4) and not is_primary and subject_count < best_n:
        division = 'INC'
    if acsee_principal_count is not None and acsee_principal_count < best_n:
        division = 'ABS' if acsee_principal_count == 0 else 'INC'

    counted_subjects = ', '.join(item[0].name for item in best)
    if combo_code:
        counted_subjects = f"{combo_code}: {counted_subjects}"

    return {
        'total_score': total,
        'average_score': round(average, 2),
        'points': points,
        'division': division,
        'position': None,
        'subject_count': subject_count,
        'counted_subjects': counted_subjects,
    }


def _rank_students(exam, summary_by_student):
    """Panga nafasi kwa kanuni ile ile ya recompute_processed_results."""
    is_primary = bool(exam.school and exam.school.is_primary)
    form = exam.form

    items = [
        (student_id, summary)
        for student_id, summary in summary_by_student.items()
    ]

    if is_primary:
        items.sort(
            key=lambda pair: (
                pair[1]['subject_count'] == 0,
                -pair[1]['total_score'],
                -pair[1]['average_score'],
            )
        )
    elif form in (1, 2, 3, 4, 5, 6):
        items.sort(
            key=lambda pair: (
                pair[1]['subject_count'] == 0,
                _DIVISION_ORDER.get(pair[1]['division'], 5),
                pair[1]['points'],
                -pair[1]['total_score'],
            )
        )
    else:
        items.sort(
            key=lambda pair: (
                pair[1]['subject_count'] == 0,
                pair[1]['points'],
                -pair[1]['total_score'],
            )
        )

    position = 0
    for _student_id, summary in items:
        if summary['division'] in ('ABS', 'INC'):
            summary['position'] = None
        else:
            position += 1
            summary['position'] = position
