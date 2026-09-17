from ..models import ExamResult, ProcessedResult, Subject


def get_exam_export_payload(exam):
    """Build the data payload for PDF / Excel export.

    Returns:
        subjects           — every subject that has at least one ExamResult
        processed_results  — all students in the same order they were
                             registered into the system (Student.id, i.e.
                             the order their roster row was first created —
                             see FormStudent.Meta and upload_form_students'
                             `order_by('id')`, which this mirrors) — NOT
                             ranked by exam position. Each result still
                             carries its own `.position` (rank) value for
                             display; only the row order changed. Callers
                             that need an actual performance ranking (e.g.
                             "Top 5 Performers") must sort their own copy
                             by `.position` — don't assume list order.
        score_lookup       — {(student_id, subject_id): score or None}
        absent_lookup      — {(student_id, subject_id): True} for absent
        student_subjects   — {student_id: set(subject_ids)} — subjects
                             each student is *enrolled* in (has an
                             ExamResult entry, whether scored or absent)
    """
    subjects = list(Subject.objects.filter(examresult__exam=exam).distinct().order_by('name'))
    processed_results = list(
        ProcessedResult.objects.filter(exam=exam).select_related('student')
        .order_by('student_id')
    )

    all_exam_results = ExamResult.objects.filter(exam=exam, subject__in=subjects)

    score_lookup = {}
    absent_lookup = set()
    student_subjects = {}   # student_id → set of subject_ids they study

    for result in all_exam_results:
        student_subjects.setdefault(result.student_id, set()).add(result.subject_id)
        if result.is_absent:
            absent_lookup.add((result.student_id, result.subject_id))
        else:
            score_lookup[(result.student_id, result.subject_id)] = result.score

    return {
        'subjects': subjects,
        'processed_results': processed_results,
        'score_lookup': score_lookup,
        'absent_lookup': absent_lookup,
        'student_subjects': student_subjects,
    }
