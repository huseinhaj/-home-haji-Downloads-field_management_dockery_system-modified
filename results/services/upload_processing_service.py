from django.db import transaction
from django.db.models import Prefetch

from ..models import ExamResult, ProcessedResult, Student, Subject
from ..utils import (
    extract_subject_columns,
    get_division,
    get_grade_for_form,
    get_grade_points,
    load_results_dataframe,
    normalize_gender,
    normalize_subject_name,
    parse_score,
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
    for column_name in subject_columns:
        normalized_name = normalize_subject_name(column_name)
        subject, _ = Subject.objects.get_or_create(name=normalized_name)
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
        row_scores = {}
        for column_name, subject in subjects_by_column.items():
            score = parse_score(row.get(column_name))
            if score is not None:
                row_scores[column_name] = score

        parsed_students.append((first_name, middle_name, last_name, gender, row_scores))

    if parsed_students:
        from django.db.models import Q

        name_pairs = {(fn, ln) for fn, _, ln, _, _ in parsed_students}
        name_filter = Q()
        for fn, ln in name_pairs:
            name_filter |= Q(first_name=fn, last_name=ln)

        student_map = {(s.first_name, s.last_name): s for s in Student.objects.filter(name_filter)}

        new_students = []
        seen = set()
        for fn, mn, ln, gender, _ in parsed_students:
            key = (fn, ln)
            if key not in student_map and key not in seen:
                seen.add(key)
                new_students.append(Student(first_name=fn, middle_name=mn, last_name=ln, gender=gender))
        if new_students:
            Student.objects.bulk_create(new_students)
            student_map = {(s.first_name, s.last_name): s for s in Student.objects.filter(name_filter)}

        exam_results = []
        for fn, mn, ln, gender, row_scores in parsed_students:
            student = student_map.get((fn, ln))
            if not student:
                continue
            for column_name, score in row_scores.items():
                exam_results.append(
                    ExamResult(exam=exam, student=student, subject=subjects_by_column[column_name], score=score)
                )

        if exam_results:
            ExamResult.objects.bulk_create(
                exam_results,
                update_conflicts=True,
                unique_fields=['exam', 'student', 'subject'],
                update_fields=['score'],
            )

    recompute_processed_results_for_exam(exam)


# Division is computed from a candidate's BEST subjects only — matching real
# NECTA practice (CSEE: best 7; ACSEE: 3 principal subjects) — not every
# subject the school happens to test. Without this, an exam covering many
# subjects (e.g. 18) would push nearly everyone into Division 0 by raw point
# accumulation, regardless of how well they actually performed.
_DIVISION_SUBJECT_COUNT = {1: 7, 2: 7, 3: 7, 4: 7, 5: 3, 6: 3}


def recompute_processed_results_for_exam(exam):
    """Recompute each student's total/average/points/division for this exam.

    Points and division follow the official NECTA method: convert each
    subject score to a grade (CSEE for Form 1-4, ACSEE for Form 5-6), take
    the student's BEST subjects (best_n = 7 for CSEE, 3 for ACSEE), sum
    those grades' point values, then map the total to a division.

    Fewer-subjects fairness:
        - Division and points are computed ONLY from the subjects a student
          actually has (minimum 1). A student with 4 CSEE subjects uses all
          4 for their points/division — they are NOT penalised for missing
          subjects they were never tested in.
        - Position ranking still uses the same NECTA sort (ascending points,
          then descending total-score as tiebreaker). This means a student
          with 4 A's (4 points) will rank above a student with 7 A's
          (7 points) — which matches real NECTA practice where the
          division is what matters, not a competitive position across
          different subject counts.
    """
    students = Student.objects.filter(examresult__exam=exam).distinct().prefetch_related(
        Prefetch('examresult_set', queryset=ExamResult.objects.filter(exam=exam).select_related('subject'))
    )

    best_n = _DIVISION_SUBJECT_COUNT.get(exam.form, 7)
    student_data = []

    for student in students:
        results = list(student.examresult_set.all())
        if not results:
            continue

        total = sum(result.score for result in results)
        count = len(results)
        average = (total / count) if count else 0.0

        # Grade every subject, then sort by points (ascending = better)
        graded = sorted(
            ((r, get_grade_points(get_grade_for_form(r.score, exam.form), form=exam.form)) for r in results),
            key=lambda pair: pair[1],
        )
        # Use best N subjects (or all if fewer than N) — no penalty for
        # having fewer subjects than the standard count.
        best = graded[:best_n]
        points = sum(p for _, p in best)
        division = get_division(points, form=exam.form)
        counted_subjects = ', '.join(r.subject.name for r, _ in best)

        student_data.append(
            {
                'student': student,
                'total': total,
                'average': average,
                'points': points,
                'division': division,
                'counted_subjects': counted_subjects,
                'subject_count': count,
            }
        )

    # NECTA ranking: sort by points ascending (lower points = better),
    # then by total score descending as tiebreaker
    student_data.sort(key=lambda item: (item['points'], -item['total']))

    # One bulk upsert instead of one update_or_create per student — the
    # remote DB's per-query latency made this the slowest part of an
    # upload for exams with more than a handful of students.
    processed_results = [
        ProcessedResult(
            exam=exam,
            student=data['student'],
            total_score=data['total'],
            average_score=round(data['average'], 2),
            points=data['points'],
            division=data['division'],
            position=position,
            counted_subjects=data['counted_subjects'],
        )
        for position, data in enumerate(student_data, start=1)
    ]
    if processed_results:
        ProcessedResult.objects.bulk_create(
            processed_results,
            update_conflicts=True,
            unique_fields=['exam', 'student'],
            update_fields=['total_score', 'average_score', 'points', 'division', 'position', 'counted_subjects'],
        )