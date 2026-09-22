from django.db import transaction
from django.db.models import Prefetch
from django.db.models.functions import Lower

from ..combinations import canon_subject, detect_acsee_combination
from ..models import ExamResult, FormStudent, ProcessedResult, Student, Subject
from ..utils import (
    extract_subject_columns,
    get_division,
    get_grade_for_form,
    get_grade_points,
    is_absent_marker,
    is_acsee_subsidiary_subject,
    load_results_dataframe,
    normalize_gender,
    parse_score,
    resolve_subject_columns,
    safe_get_or_create_subject,
)


class UploadProcessingError(Exception):
    pass


@transaction.atomic
def process_uploaded_results(exam, uploaded_file):
    if not uploaded_file:
        raise UploadProcessingError("No file uploaded.")

    uploaded_file.seek(0)
    data_frame = load_results_dataframe(uploaded_file)

    subject_columns = extract_subject_columns(data_frame)
    if not subject_columns:
        raise UploadProcessingError("No subject columns found. Please check your file.")

    subjects_by_column = {}
    for column_name, subject_name in resolve_subject_columns(subject_columns):
        subject = safe_get_or_create_subject(subject_name)
        subjects_by_column[column_name] = subject

    # Parse every row first, then do the whole upload in a handful of bulk
    # queries instead of one-plus-one-per-subject round trips per student —
    # with a remote DB that made even a small file painfully slow to upload.
    parsed_students = []
    for _, row in data_frame.iterrows():
        first_name = str(row.get('First Name', '')).strip() or 'Unknown'
        middle_name = str(row.get('Middle Name', '')).strip() if 'Middle Name' in data_frame.columns else ''
        last_name = str(row.get('Last Name', '')).strip() or 'Unknown'

        if not (first_name or middle_name or last_name):
            continue

        gender = normalize_gender(row.get('Gender', ''))
        row_scores = {}      # {column_name: score}
        row_absent = {}      # {column_name: True} — student is absent for this subject
        for column_name, subject in subjects_by_column.items():
            raw_val = row.get(column_name)
            score = parse_score(raw_val)
            if score is not None:
                row_scores[column_name] = score
            elif is_absent_marker(raw_val):
                row_absent[column_name] = True

        parsed_students.append((first_name, middle_name, last_name, gender, row_scores, row_absent))

    if parsed_students:
        from django.db.models import Q

        name_pairs = {(fn, ln) for fn, _mn, ln, *_rest in parsed_students}
        name_filter = Q()
        for fn, ln in name_pairs:
            name_filter |= Q(first_name=fn, last_name=ln)

        student_map = {(s.first_name, s.last_name): s for s in Student.objects.filter(name_filter)}

        new_students = []
        seen = set()
        for fn, mn, ln, gender, _, _ in parsed_students:
            key = (fn, ln)
            if key not in student_map and key not in seen:
                seen.add(key)
                new_students.append(Student(first_name=fn, middle_name=mn, last_name=ln, gender=gender))
        if new_students:
            Student.objects.bulk_create(new_students)
            student_map = {(s.first_name, s.last_name): s for s in Student.objects.filter(name_filter)}

        exam_results = []
        for fn, mn, ln, gender, row_scores, row_absent in parsed_students:
            student = student_map.get((fn, ln))
            if not student:
                continue
            for column_name, score in row_scores.items():
                exam_results.append(
                    ExamResult(exam=exam, student=student, subject=subjects_by_column[column_name], score=score, is_absent=False)
                )
            for column_name in row_absent:
                exam_results.append(
                    ExamResult(exam=exam, student=student, subject=subjects_by_column[column_name], score=None, is_absent=True)
                )

        if exam_results:
            ExamResult.objects.bulk_create(
                exam_results,
                update_conflicts=True,
                unique_fields=['exam', 'student', 'subject'],
                update_fields=['score', 'is_absent'],
            )

    recompute_processed_results_for_exam(exam)


# Division is computed from a candidate's BEST subjects only — matching real
# NECTA practice (CSEE: best 7; ACSEE: 3 principal subjects) — not every
# subject the school happens to test. Without this, an exam covering many
# subjects (e.g. 18) would push nearly everyone into Division 0 by raw point
# accumulation, regardless of how well they actually performed.
_DIVISION_SUBJECT_COUNT = {1: 7, 2: 7, 3: 7, 4: 7, 5: 3, 6: 3}

# Both CSEE and ACSEE position ranking sort by DIVISION first, then raw
# points within it — see the "fewer-subjects"/INC note in
# recompute_processed_results_for_exam for why raw points alone can't be
# the primary key. INC/ABS are markers, not divisions: they always rank
# below every REAL division INCLUDING '0' — an INC candidate's points only
# ever sum a handful of subjects, so tying it with '0' would let raw
# points reintroduce the exact fewer-subjects advantage this ordering
# exists to prevent. ABS never gets a stored position anyway (see the
# bulk_create loop below); its order value here only has to avoid
# crashing a lookup.
_DIVISION_ORDER = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, '0': 5, 'INC': 6, 'ABS': 7}


def _sync_student_genders_from_roster(exam):
    """Roster (FormStudent) ndiyo mkuu kwa gender: kila mwanafunzi wa mtihani
    huu aliye kwenye roster anasawazishwa na gender ya rosti yake. Hii
    inatibu gender mchanganyiko (mf. 'Kike' ilikuwa inasomwa kama M kwenye
    zamani) hata kwenye records zilizohifadhiwa kabla fix ya parser —
    recompute yoyote inapofanyika, report cards na final results
    zinaonyesha gender sahihi kutoka kwenye roster ya shule."""
    if not exam.school:
        return
    roster = list(FormStudent.objects.filter(
        school=exam.school, form=exam.form,
        is_active=True, academic_year=exam.year,
    ).only('first_name', 'middle_name', 'last_name', 'gender'))
    if not roster:
        return

    # One query for the whole roster instead of one Student lookup per
    # roster row — over the remote DB's per-query latency that N+1 loop
    # alone made recompute take minutes for a single exam.
    candidates = Student.objects.annotate(
        fn_lower=Lower('first_name'),
        mn_lower=Lower('middle_name'),
        ln_lower=Lower('last_name'),
    ).filter(
        fn_lower__in=[fs.first_name.lower() for fs in roster],
        ln_lower__in=[fs.last_name.lower() for fs in roster],
    )
    by_key = {}
    for s in candidates:
        key = (s.fn_lower, s.mn_lower or '', s.ln_lower)
        by_key.setdefault(key, []).append(s)

    to_fix = []
    for fs in roster:
        # Match ile ile inayotumika na _resolve_class_roster (marks_entry)
        key = (fs.first_name.lower(), (fs.middle_name or '').lower(), fs.last_name.lower())
        for s in by_key.get(key, []):
            if s.gender != fs.gender:
                s.gender = fs.gender
                to_fix.append(s)
    if to_fix:
        Student.objects.bulk_update(to_fix, ['gender'])


def recompute_processed_results_for_exam(exam):
    """Recompute each student's total/average/points/division for this exam.

    Points and division follow the official NECTA method: convert each
    subject score to a grade (CSEE for Form 1-4, ACSEE for Form 5-6), take
    the student's BEST subjects (best_n = 7 for CSEE, 3 for ACSEE), sum
    those grades' point values, then map the total to a division. TOTAL/
    AVG are computed from those same counted subjects only — never every
    subject a student happened to sit — so a candidate who takes extra
    electives and does poorly in them isn't shown a misleadingly low
    aggregate; a student's TOTAL is always consistent with the points
    that actually set their division and rank.

    Incomplete sittings (CSEE / Form 1-4):
        - A candidate on the roster who sat NOTHING gets division ABS —
          aggregate displays '-', they are unranked (position NULL) and
          sort to the bottom of the class.
        - A candidate who sat SOME subjects but fewer than the 7 the CSEE
          division scale assumes gets the marker INC — masomo hayajafika 7
          — instead of a division; points still reflect what they sat and
          are used only for internal ordering. Like ABS, INC is unranked
          (position NULL) — no real division means no rank number.
        - Ranked candidates sort by DIVISION first, then points within it
          (both ascending — better division/fewer points first), then
          total score descending as the final tiebreaker, so "Top
          performers" always means genuine Division I/II students.

    ACSEE / Form 5-6 is different (verified against real 2025 result slips):
        - Division counts the student's COMBINATION subjects only (PCB,
          HGL, EGM, …). The combination is detected from the subjects the
          student sat (see results.combinations.detect_acsee_combination).
          Any extra subject — a 4th principal, General Studies, BAM — is
          dropped, even if the student scored better in it.
        - A candidate who sat all 3 combination subjects — or, when no
          registered combination fits, 3+ principal subjects (an unusual
          mix) — gets a real division computed from those subjects.
        - A candidate who sat only 1 or 2 principal subjects gets the
          marker INC ("masomo hayajafika 3") instead of a division —
          same meaning as CSEE's INC below, unranked (position NULL)
          for the same reason. One who sat NONE of the principal
          subjects (nothing, or only General Studies / BAM) gets ABS.
        - Position ranking tiebreaker is the total of the counted
          subjects only (not General Studies / a 4th subject).

    Ranking: students who sat nothing are placed last; both CSEE and
    ACSEE then sort by division first — INC/ABS always rank below every
    real division so a short combination/sitting can never outrank a
    genuine full one — then ascending points, then descending
    counted-subject total.
    """
    # Roster ndiyo mkuu kwa gender — sawazisha kabla ya kuhesabu matokeo
    _sync_student_genders_from_roster(exam)

    students = Student.objects.filter(examresult__exam=exam).distinct().prefetch_related(
        Prefetch(
            'examresult_set',
            queryset=ExamResult.objects.filter(exam=exam).select_related('subject').order_by('subject__name'),
        )
    )

    # ── Primary school (Darasa 1-7) ───────────────────────────────────
    # Msingi hauna division wala best-N: kila somo mwanafunzi anachokifanya
    # kinaingia kwenye jumla (kama PSLE — Wanafunzi wanapangwa kwa Jumla ya
    # alama, Wastani ndio inaonyeshwa). Division inabaki BLANK '' na
    # templates za msingi hazioniyesha.
    is_primary = bool(exam.school and exam.school.is_primary)
    best_n = 999 if is_primary else _DIVISION_SUBJECT_COUNT.get(exam.form, 7)
    student_data = []

    for student in students:
        all_results = list(student.examresult_set.all())
        if not all_results:
            continue

        # Only count subjects the student actually sat for (not absent)
        results = [r for r in all_results if not r.is_absent and r.score is not None]

        # Students with ALL subjects absent/blank still appear in results
        # — they must not be skipped so the PDF shows every registered
        # student. NECTA slip marker: division ABS, aggregate '-', and no
        # position (ranked last, unranked). Primary schools keep the
        # simple zeroed row (no division concept there).
        if not results:
            student_data.append({
                'student': student,
                'total': 0,
                'average': 0.0,
                'points': 0,
                'division': '' if is_primary else 'ABS',
                'counted_subjects': '',
                'subject_count': 0,
                'rank_total': 0,
            })
            continue

        count = len(results)  # ALL subjects sat — for the INC check and subject_count only

        combo_code = ''
        acsee_principal_count = None
        if exam.form in (5, 6):
            # ── ACSEE: division counts the student's COMBINATION only ──
            # Map every subject the student sat to its canonical A-Level
            # name, keeping the better result if a name repeats.
            by_canon = {}
            for r in results:
                cname = canon_subject(r.subject.name)
                if not cname:
                    continue
                pts = get_grade_points(get_grade_for_form(r.score, exam.form), form=exam.form)
                if cname not in by_canon or pts < by_canon[cname][1]:
                    by_canon[cname] = (r, pts)

            combo = detect_acsee_combination(by_canon.keys(), lambda n: by_canon[n][1])
            if combo:
                # Exactly the 3 combination subjects — any extra subject
                # (a 4th principal, General Studies, BAM) is dropped, even
                # if the student scored better in it.
                combo_code, combo_subjects = combo
                graded = sorted(
                    (by_canon[s] for s in combo_subjects if s in by_canon),
                    key=lambda pair: pair[1],
                )
            else:
                # No registered combination fits — either the sitting is
                # incomplete (1-2 principal subjects, INC below) or it's
                # an unusual mix of 3+ principals matching no registered
                # combination. General Studies / BAM never substitute
                # here — a candidate who sat ONLY those has zero
                # principal subjects and is ABS, not scored on them.
                principal = [
                    pair for cname, pair in by_canon.items()
                    if not is_acsee_subsidiary_subject(cname)
                ]
                graded = sorted(principal, key=lambda pair: pair[1])[:best_n]
            acsee_principal_count = len(graded)
        else:
            graded = sorted(
                ((r, get_grade_points(get_grade_for_form(r.score, exam.form, primary=is_primary), form=exam.form)) for r in results),
                key=lambda pair: pair[1],
            )

        # Use best N subjects (or all if fewer than N).
        best = graded[:best_n]
        points = sum(p for _, p in best)

        # TOTAL/AVG reflect only the COUNTED subjects — the same ones
        # that set points/division — never every subject the student
        # happened to sit. A student who takes extra electives and does
        # poorly in them must not have that drag down a figure meant to
        # describe their actual (best-subjects) performance: previously
        # TOTAL summed every subject sat, so a genuinely stronger
        # candidate with a couple of weak electives could show a LOWER
        # total than a weaker candidate who simply sat fewer subjects —
        # confusing on a report where position is sorted by points, not
        # this total. (Primary is unaffected: best_n there is 999, so
        # `best` already covers every subject sat.)
        total = sum(r.score for r, _ in best)
        counted_n = len(best)
        average = (total / counted_n) if counted_n else 0.0

        division = '' if is_primary else get_division(points, form=exam.form)
        counted_subjects = ', '.join(r.subject.name for r, _ in best)
        if combo_code:
            counted_subjects = f"{combo_code}: {counted_subjects}"

        # Tiebreaker for position ranking — the total of the counted
        # subjects only, same figure as TOTAL above.
        rank_total = total

        # ── NECTA incomplete-sitting marker (O-Level / CSEE) ──────────
        # A candidate who sat SOME subjects but fewer than the 7 the CSEE
        # division scale assumes gets the marker INC ("masomo hayajafika
        # 7") instead of a division — no real division can be computed
        # from an incomplete sitting, so none is printed.
        if exam.form in (1, 2, 3, 4) and not is_primary and count < best_n:
            division = 'INC'

        # ── ACSEE incomplete-combination marker ───────────────────────
        # NECTA classifies an A-Level candidate on a FULL set of 3
        # combination subjects. A candidate who sat 1 or 2 of them gets
        # INC ("masomo hayajafika 3") instead of a division; one who sat
        # NONE of them (nothing, or only General Studies / BAM) is ABS.
        # Both keep their raw (unpadded) points for internal ordering
        # only — a short combination must never outrank a genuine
        # full-combination candidate (see _DIVISION_ORDER below).
        if acsee_principal_count is not None and acsee_principal_count < best_n:
            division = 'ABS' if acsee_principal_count == 0 else 'INC'

        student_data.append(
            {
                'student': student,
                'total': total,
                'average': average,
                'points': points,
                'division': division,
                'counted_subjects': counted_subjects,
                'subject_count': count,
                'rank_total': rank_total,
            }
        )

    # NECTA ranking: students who sat nothing (Division 0, points forced
    # to 0) go last. CSEE and ACSEE both sort by division BEFORE points --
    # a short-sitting/short-combination student must not outrank a
    # full-sitting one just because their unpadded points happen to be
    # lower; division (now including the INC/ABS markers) already accounts
    # for that (see docstring above).
    # PRIMARY ranking: hakuna division — jumla ya alama ndio kipimo (juu
    # kwanza), Wastani ndio tiebreaker. Waliosajiliwa wasiokwepo huishia
    # mwisho kama sekondari.
    if is_primary:
        student_data.sort(
            key=lambda item: (item['subject_count'] == 0, -item['total'], -item['average'])
        )
    elif exam.form in (1, 2, 3, 4, 5, 6):
        # ABS candidates (subject_count == 0, or ACSEE zero-principal)
        # go last and are UNRANKED — their position stays None on the
        # stored row. INC rows rank below every real division but above
        # ABS.
        student_data.sort(
            key=lambda item: (
                item['subject_count'] == 0,
                _DIVISION_ORDER.get(item['division'], 5),
                item['points'],
                -item['rank_total'],
            )
        )
    else:
        student_data.sort(
            key=lambda item: (item['subject_count'] == 0, item['points'], -item['rank_total'])
        )

    # One bulk upsert instead of one update_or_create per student — the
    # remote DB's per-query latency made this the slowest part of an
    # upload for exams with more than a handful of students.
    #
    # Position: ABS (sat nothing) and INC (incomplete sitting/combination)
    # rows are UNRANKED — position stays NULL whatever their sort index
    # was; a candidate no real division was computed for cannot be given
    # a rank number among those who have one.
    processed_results = []
    position = 0
    for data in student_data:
        if data['division'] in ('ABS', 'INC'):
            stored_position = None
        else:
            position += 1
            stored_position = position
        processed_results.append(
            ProcessedResult(
                exam=exam,
                student=data['student'],
                total_score=data['total'],
                average_score=round(data['average'], 2),
                points=data['points'],
                division=data['division'],
                position=stored_position,
                counted_subjects=data['counted_subjects'],
            )
        )
    if processed_results:
        ProcessedResult.objects.bulk_create(
            processed_results,
            update_conflicts=True,
            unique_fields=['exam', 'student'],
            update_fields=['total_score', 'average_score', 'points', 'division', 'position', 'counted_subjects'],
        )

    # Stale cleanup: a student whose ExamResult rows were all removed
    # (roster correction, ghost-student fix, resubmission) after their
    # ProcessedResult was first computed would otherwise keep showing up
    # in results/rankings forever — bulk_create above only ever
    # creates/updates rows for students who currently qualify, it never
    # removes ones who no longer do.
    current_student_ids = [data['student'].id for data in student_data]
    ProcessedResult.objects.filter(exam=exam).exclude(student_id__in=current_student_ids).delete()


def recompute_processed_results_for_exam_with_model(exam, ProcessedResult):
    """Migration entry point — identical recompute but with the ProcessedResult
    model passed in (history-model-safe, see migration 0054 backfill)."""
    recompute_processed_results_for_exam(exam)
    # The normal recompute already upserted via the real model; nothing
    # extra to do here — the parameter exists so a historical-model caller
    # (migration) never crashes on model imports.