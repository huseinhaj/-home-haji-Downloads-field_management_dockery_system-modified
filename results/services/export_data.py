from ..models import ExamResult, FormStudent, ProcessedResult, Subject


def _registration_roster_order(exam):
    """{(first_name, last_name): index} for this exam's form/school/year's
    FormStudent roster, in the exact order shown on the roster/upload page
    (upload_form_students' `order_by('id')` — the school's own registration
    order, e.g. matching the physical class register). Same matching key
    _resolve_class_roster / _student_from_form_student (marks_entry.py) use
    to turn a FormStudent into its Student row, so a name found here is the
    same student the export's ProcessedResult rows point to.

    Returns {} when the exam has no school or no roster uploaded — callers
    then fall back to every student being "not in the roster" (see
    order_by_registration), which is still a sane, stable order."""
    if not exam.school:
        return {}
    form_students = FormStudent.objects.filter(
        school=exam.school, form=exam.form,
        is_active=True, academic_year=exam.year,
    ).order_by('id')
    return {
        (fs.first_name, fs.last_name): idx
        for idx, fs in enumerate(form_students)
    }


def order_by_registration(exam, processed_results):
    """Sort ProcessedResult rows (with `.student` already select_related)
    into the school's actual registration order for this exam — NOT exam
    rank. A student who isn't in the FormStudent roster (added after the
    roster was uploaded — e.g. via Marks Entry's "add student" or a
    scoresheet scan that created a new Student) sorts AFTER every
    registered student, oldest-added first (Student.id)."""
    roster_order = _registration_roster_order(exam)
    return sorted(
        processed_results,
        key=lambda r: (
            roster_order.get((r.student.first_name, r.student.last_name), len(roster_order)),
            r.student_id,
        ),
    )


def get_exam_export_payload(exam):
    """Build the data payload for PDF / Excel export.

    Returns:
        subjects           — every subject that has at least one ExamResult
        processed_results  — all students in the school's actual
                             registration order for this exam (see
                             order_by_registration) — NOT ranked by exam
                             position. Each result still carries its own
                             `.position` (rank) value for display; only
                             the row order changed. Callers that need an
                             actual performance ranking (e.g. "Top 5
                             Performers") must sort their own copy by
                             `.position` — don't assume list order.
        score_lookup       — {(student_id, subject_id): score or None}
        absent_lookup      — {(student_id, subject_id): True} for absent
        student_subjects   — {student_id: set(subject_ids)} — subjects
                             each student is *enrolled* in (has an
                             ExamResult entry, whether scored or absent)
    """
    subjects = list(Subject.objects.filter(examresult__exam=exam).distinct().order_by('name'))
    processed_results = order_by_registration(
        exam,
        ProcessedResult.objects.filter(exam=exam).select_related('student'),
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
