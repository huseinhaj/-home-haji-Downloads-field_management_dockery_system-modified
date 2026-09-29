"""
Uchambuzi wa joint exam ya wilaya — takwimu zile zile za Excel za Halmashauri.

  DIVISION: waliosajiliwa / waliofanya / wasiofanya, Div I–IV & 0, I–III,
            I–IV, IV–0 (na %), PASS, GPA, nafasi kiwilaya.
  GRADE:    gredi ya wastani wa kila mwanafunzi A–F, PASS (A–D), %, GPA.
  MASOMO:   kwa kila somo, kila shule A–F, PASS, %, GPA + ranking ya masomo.

GPA (kama kwenye mafaili ya Halmashauri — ndogo ndiyo bora):
  Division: (I×1 + II×2 + III×3 + IV×4 + 0×5) ÷ waliopata division
  Gredi:    (A×1 + B×2 + C×3 + D×4 + F×5) ÷ waliofanya

Kila hesabu inagawanywa kwa jinsia: M (wavulana), F (wasichana), T (jumla).
"""
from __future__ import annotations

from collections import defaultdict

from ..utils import get_grade_for_exam

DIVISIONS = ['I', 'II', 'III', 'IV', '0']
DIV_POINTS = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, '0': 5}
GRADES = ['A', 'B', 'C', 'D', 'F']
GRADE_POINTS = {'A': 1, 'B': 2, 'C': 3, 'D': 4, 'F': 5}


def _mft():
    return {'M': 0, 'F': 0, 'T': 0}


def _add(bucket, gender, n=1):
    if gender in ('M', 'F'):
        bucket[gender] += n
    bucket['T'] += n


def _sum_mft(*buckets):
    out = _mft()
    for b in buckets:
        for k in out:
            out[k] += b[k]
    return out


def _pct(part, whole):
    return round(part * 100.0 / whole, 2) if whole else None


def _gpa(counts, points):
    total = sum(counts[k]['T'] for k in points)
    if not total:
        return None
    return round(sum(counts[k]['T'] * p for k, p in points.items()) / total, 4)


def _rank(rows, key='gpa', out='rank'):
    """Nafasi kwa GPA (ndogo = bora). Sawa = nafasi moja; bila GPA = hakuna nafasi."""
    ranked = sorted((r for r in rows if r[key] is not None), key=lambda r: r[key])
    prev, pos = None, 0
    for i, r in enumerate(ranked, 1):
        if r[key] != prev:
            pos, prev = i, r[key]
        r[out] = pos
    for r in rows:
        r.setdefault(out, None)


def _grade_block(counts):
    """{A..F: mft} → pass (A–D) mft, %, GPA."""
    sat = _sum_mft(*(counts[g] for g in GRADES))
    passed = _sum_mft(*(counts[g] for g in GRADES if g != 'F'))
    return {
        'grades': counts,
        'sat': sat,
        'pass': passed,
        'pass_pct': _pct(passed['T'], sat['T']),
        'gpa': _gpa(counts, GRADE_POINTS),
    }


def _division_block(reg, absent, divs, inc):
    sat = _sum_mft(*(divs[d] for d in DIVISIONS), inc)
    with_div = sum(divs[d]['T'] for d in DIVISIONS)
    i_iii = _sum_mft(divs['I'], divs['II'], divs['III'])
    i_iv = _sum_mft(i_iii, divs['IV'])
    iv_0 = _sum_mft(divs['IV'], divs['0'])
    return {
        'registered': reg,
        'sat': sat,
        'absent': absent,
        'divisions': divs,
        'inc': inc,
        'i_iii': i_iii, 'i_iii_pct': _pct(i_iii['T'], with_div),
        'i_iv': i_iv, 'i_iv_pct': _pct(i_iv['T'], with_div),
        'iv_0': iv_0, 'iv_0_pct': _pct(iv_0['T'], with_div),
        'pass': i_iv['T'],
        'gpa': _gpa(divs, DIV_POINTS),
    }


def analyse_joint_exam(joint, ownership=None):
    """Takwimu za shule zote za joint hii.

    ownership: None (zote) | 'GOV' | 'PRIVATE' — kuchuja shule.
    Inarudi dict: {'schools': [...], 'totals': {...}, 'subjects': [...]}
    """
    from ..models import ExamResult, ProcessedResult, SubjectSubmission

    exams = list(
        joint.school_exams.select_related('school').order_by('school__name')
    )
    if ownership:
        exams = [e for e in exams if e.school and e.school.ownership == ownership]
    exam_ids = [e.pk for e in exams]

    # ── Division + gredi ya wastani (ProcessedResult) ──
    per_exam = {e.pk: {
        'reg': _mft(), 'absent': _mft(), 'inc': _mft(),
        'divs': {d: _mft() for d in DIVISIONS},
        'grades': {g: _mft() for g in GRADES},
    } for e in exams}
    exam_by_id = {e.pk: e for e in exams}
    for exam_id, division, avg, gender in ProcessedResult.objects.filter(
        exam_id__in=exam_ids,
    ).values_list('exam_id', 'division', 'average_score', 'student__gender'):
        b = per_exam[exam_id]
        _add(b['reg'], gender)
        if division == 'ABS':
            _add(b['absent'], gender)
            continue
        if division in DIV_POINTS:
            _add(b['divs'][division], gender)
        else:
            _add(b['inc'], gender)
        grade = get_grade_for_exam(float(avg or 0), exam_by_id[exam_id])
        _add(b['grades'][grade if grade in GRADE_POINTS else 'F'], gender)

    # ── Maendeleo ya uingizaji wa alama (masomo yaliyowasilishwa) ──
    progress = defaultdict(lambda: [0, 0])
    for exam_id, status in SubjectSubmission.objects.filter(
        exam_id__in=exam_ids,
    ).values_list('exam_id', 'status'):
        progress[exam_id][1] += 1
        if status in (SubjectSubmission.STATUS_SUBMITTED, SubjectSubmission.STATUS_APPROVED):
            progress[exam_id][0] += 1

    schools = []
    for e in exams:
        b = per_exam[e.pk]
        row = {
            'exam': e,
            'school': e.school,
            'ward': (e.school.ward if e.school else '') or '',
            'ownership': e.school.get_ownership_display() if e.school and e.school.ownership else '',
            'subjects_done': progress[e.pk][0],
            'subjects_total': progress[e.pk][1],
            **_division_block(b['reg'], b['absent'], b['divs'], b['inc']),
        }
        g = _grade_block(b['grades'])
        row['grade'] = g
        row['grade_gpa'] = g['gpa']
        schools.append(row)
    _rank(schools)
    _rank(schools, key='grade_gpa', out='grade_rank')
    schools.sort(key=lambda r: (r['rank'] is None, r['rank'] or 0, r['school'].name if r['school'] else ''))

    def _total(key):
        return _sum_mft(*(r[key] for r in schools)) if schools else _mft()

    divs_total = {d: _sum_mft(*(r['divisions'][d] for r in schools)) if schools else _mft()
                  for d in DIVISIONS}
    totals = _division_block(_total('registered'), _total('absent'), divs_total, _total('inc'))
    totals['grade'] = _grade_block({
        g: _sum_mft(*(r['grade']['grades'][g] for r in schools)) if schools else _mft()
        for g in GRADES
    })

    # ── Masomo ──
    subj_counts = defaultdict(lambda: defaultdict(lambda: {g: _mft() for g in GRADES}))
    subj_absent = defaultdict(lambda: defaultdict(_mft))
    subject_objs = {s.pk: s for s in joint.subjects.all()}
    for exam_id, subject_id, subject_name, score, is_absent, gender in ExamResult.objects.filter(
        exam_id__in=exam_ids,
    ).values_list('exam_id', 'subject_id', 'subject__name', 'score', 'is_absent', 'student__gender'):
        if subject_id not in subject_objs:
            subject_objs[subject_id] = subject_name
        if is_absent or score is None:
            _add(subj_absent[subject_id][exam_id], gender)
            continue
        grade = get_grade_for_exam(float(score), exam_by_id[exam_id])
        _add(subj_counts[subject_id][exam_id][grade if grade in GRADE_POINTS else 'F'], gender)

    subjects = []
    for subject_id, subj in subject_objs.items():
        name = subj if isinstance(subj, str) else subj.name
        rows = []
        for e in exams:
            blk = _grade_block(subj_counts[subject_id][e.pk])
            rows.append({
                'school': e.school, 'ward': (e.school.ward if e.school else '') or '',
                'ownership': e.school.get_ownership_display() if e.school and e.school.ownership else '',
                'absent': subj_absent[subject_id][e.pk],
                **blk,
            })
        _rank(rows)
        rows.sort(key=lambda r: (r['rank'] is None, r['rank'] or 0, r['school'].name if r['school'] else ''))
        total = _grade_block({
            g: _sum_mft(*(r['grades'][g] for r in rows)) if rows else _mft() for g in GRADES
        })
        subjects.append({'subject_id': subject_id, 'name': name, 'rows': rows, **total})
    _rank(subjects)
    subjects.sort(key=lambda s: (s['rank'] is None, s['rank'] or 0, s['name']))

    return {'schools': schools, 'totals': totals, 'subjects': subjects}
