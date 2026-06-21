from ..models import ExamResult, ProcessedResult, Subject


def get_exam_export_payload(exam):
    subjects = list(Subject.objects.filter(examresult__exam=exam).distinct().order_by('name'))
    processed_results = list(
        ProcessedResult.objects.filter(exam=exam).select_related('student').order_by('position')
    )
    score_lookup = {
        (result.student_id, result.subject_id): result.score
        for result in ExamResult.objects.filter(exam=exam, subject__in=subjects)
    }
    return {
        'subjects': subjects,
        'processed_results': processed_results,
        'score_lookup': score_lookup,
    }
