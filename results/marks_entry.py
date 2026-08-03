"""
Marks Entry — mwalimu anapakia orodha ya wanafunzi, kujaza alama, kukagua
(matokeo yamepangwa kuanzia wa kwanza hadi wa mwisho), kisha kuwasilisha kwa
Mtaaluma (Academic Officer). Hii ni mbadala wa Speech Entry.

Flow:
  1. Chagua Mtihani + Somo
  2. Pakia orodha ya wanafunzi (CSV/Excel/PDF) → jaza alama za kila mwanafunzi
  3. Submit → mfumo unapanga kwa alama (1st → last) → Review
  4. "Submit kwa Mtaaluma" → SubjectSubmission inakuwa SUBMITTED
  5. "Pakua PDF" → download ya matokeo ya somo
"""
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Exam, ExamResult, Student, Subject, SubjectSubmission
from .permissions import teacher_required
from .services.upload_processing_service import recompute_processed_results_for_exam
from .utils import get_grade_for_form


def _parse_payload(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return {}
    return request.POST.dict()


@teacher_required
def marks_entry(request):
    """Entry page (fill marks) + review page (?review=1 shows sorted results)."""
    teacher = request.user
    teacher_subjects = teacher.subjects.all().order_by('name')
    if not teacher_subjects.exists():
        messages.warning(
            request,
            "Chagua masomo yako kwanza (Masomo Yangu) kabla ya kuingiza alama.",
        )
        return redirect('select_my_subjects')

    exams = Exam.objects.filter(school=teacher.school).order_by('-year', 'name')
    exam_id = request.GET.get('exam') or ''
    subject_id = request.GET.get('subject') or ''
    review_mode = request.GET.get('review') == '1'

    exam = subject = None
    review_rows = []
    submission = None
    pdf_url = None
    existing_marks = {}
    class_students = []

    if exam_id and subject_id:
        exam = Exam.objects.filter(id=exam_id, school=teacher.school).first()
        subject = teacher_subjects.filter(id=subject_id).first()
        if exam and subject:
            existing_marks = {
                r.student_id: r.score
                for r in ExamResult.objects.filter(exam=exam, subject=subject)
            }
            if review_mode:
                results = list(
                    ExamResult.objects.filter(exam=exam, subject=subject)
                    .select_related('student')
                    .order_by('-score', 'student__first_name')
                )
                review_rows = [
                    {
                        'position': i,
                        'student': r.student,
                        'score': r.score,
                        'grade': get_grade_for_form(r.score, exam.form),
                    }
                    for i, r in enumerate(results, 1)
                ]
                submission = SubjectSubmission.objects.filter(exam=exam, subject=subject).first()
                if not results:
                    messages.info(request, "Hakuna alama zilizohifadhiwa kwa somo hili bado.")
                    review_mode = False
                else:
                    pdf_url = reverse('subject_pdf', args=[exam.id, subject.id])
            else:
                # Wanafunzi wote waliosajiliwa kwenye mtihani huu (msingi wa orodha ya darasa)
                class_students = [
                    {
                        'id': s.id,
                        'name': ' '.join(p for p in [s.first_name, s.middle_name or '', s.last_name] if p),
                        'score': existing_marks.get(s.id),
                    }
                    for s in Student.objects.filter(examresult__exam=exam)
                    .distinct()
                    .order_by('first_name', 'last_name')
                ]

    # Wastani na kiwango cha kufaulu kwa ukaguzi
    avg_score = None
    pass_rate = None
    if review_rows:
        scores = [r['score'] for r in review_rows]
        avg_score = round(sum(scores) / len(scores), 1)
        pass_rate = round(sum(1 for s in scores if get_grade_for_form(s, exam.form) != 'F') / len(scores) * 100)

    return render(request, 'results/marks_entry.html', {
        'exams': exams,
        'teacher_subjects': teacher_subjects,
        'preselect_exam_id': exam_id,
        'preselect_subject_id': subject_id,
        'review_mode': review_mode,
        'exam': exam,
        'subject': subject,
        'review_rows': review_rows,
        'submission': submission,
        'pdf_url': pdf_url,
        'avg_score': avg_score,
        'pass_rate': pass_rate,
        'existing_marks_json': json.dumps(existing_marks),
        'class_students_json': json.dumps(class_students),
    })


@teacher_required
@require_POST
def marks_entry_save(request):
    """Save (or update) all scores for an exam+subject. Does NOT submit yet."""
    payload = _parse_payload(request)
    teacher = request.user
    exam = get_object_or_404(Exam, id=payload.get('exam_id'), school=teacher.school)
    subject = get_object_or_404(Subject, id=payload.get('subject_id'))
    if not teacher.subjects.filter(pk=subject.pk).exists():
        return JsonResponse({'error': 'Hujapangiwa somo hili.'}, status=403)

    entries = payload.get('entries') or []
    if not entries:
        return JsonResponse({'error': 'Hakuna alama zilizotumwa.'}, status=400)

    parsed = []
    for e in entries:
        try:
            sid = int(e.get('student_id'))
            score = int(e.get('score'))
        except (TypeError, ValueError):
            continue
        if score < 0 or score > 100:
            return JsonResponse({'error': f'Alama ya mwanafunzi #{sid} si sahihi (0-100).'}, status=400)
        parsed.append((sid, score))

    if not parsed:
        return JsonResponse({'error': 'Hakuna alama sahihi zilizotumwa.'}, status=400)

    student_ids = [sid for sid, _ in parsed]
    student_map = {s.id: s for s in Student.objects.filter(id__in=student_ids)}
    if len(student_map) != len(student_ids):
        return JsonResponse({'error': 'Baadhi ya wanafunzi hawapo kwenye mfumo. Pakia orodha tena.'}, status=400)

    ExamResult.objects.bulk_create(
        [ExamResult(exam=exam, student=student_map[sid], subject=subject, score=score)
         for sid, score in parsed],
        update_conflicts=True,
        unique_fields=['exam', 'student', 'subject'],
        update_fields=['score'],
    )

    return JsonResponse({
        'success': True,
        'saved_count': len(parsed),
        'review_url': reverse('marks_entry') + f'?exam={exam.id}&subject={subject.id}&review=1',
    })


@teacher_required
@require_POST
def marks_entry_submit(request):
    """Final submit — marks SubjectSubmission as SUBMITTED so the academic
    officer sees it (same logic as the old file-upload/speech flows)."""
    payload = _parse_payload(request)
    teacher = request.user
    exam = get_object_or_404(Exam, id=payload.get('exam_id'), school=teacher.school)
    subject = get_object_or_404(Subject, id=payload.get('subject_id'))
    if not teacher.subjects.filter(pk=subject.pk).exists():
        return JsonResponse({'error': 'Hujapangiwa somo hili.'}, status=403)

    has_results = ExamResult.objects.filter(exam=exam, subject=subject).exists()
    if not has_results:
        return JsonResponse({'error': 'Hakuna alama zilizohifadhiwa. Jaza alama kwanza.'}, status=400)

    student_count = ExamResult.objects.filter(exam=exam, subject=subject).count()
    SubjectSubmission.objects.update_or_create(
        exam=exam,
        subject=subject,
        defaults={
            'status': SubjectSubmission.STATUS_SUBMITTED,
            'method': 'MANUAL',
            'submitted_by': teacher.full_name or teacher.email,
            'submitted_by_user': teacher,
            'submitted_at': timezone.now(),
            'student_count': student_count,
        },
    )

    # Recompute overall processed results now that this subject is submitted
    try:
        recompute_processed_results_for_exam(exam)
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'overview_url': reverse('exam_overview', args=[exam.id]),
    })
