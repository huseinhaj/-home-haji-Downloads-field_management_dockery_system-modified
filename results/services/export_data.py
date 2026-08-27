from ..models import ExamResult, ProcessedResult, Subject


def get_exam_export_payload(exam):
    """Build the data payload for PDF / Excel export.

    Returns:
        subjects           — every subject that has at least one ExamResult
        processed_results  — all students ranked by position
        score_lookup       — {(student_id, subject_id): score or None}
        absent_lookup      — {(student_id, subject_id): True} for absent
        student_subjects   — {student_id: set(subject_ids)} — subjects
                             each student is *enrolled* in (has an
                             ExamResult entry, whether scored or absent)
    """
    subjects = list(Subject.objects.filter(examresult__exam=exam).distinct().order_by('name'))
    processed_results = list(
        ProcessedResult.objects.filter(exam=exam).select_related('student').order_by('position')
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
