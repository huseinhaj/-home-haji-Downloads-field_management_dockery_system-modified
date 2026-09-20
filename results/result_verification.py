"""
result_verification.py — Public QR verification ya slip za matokeo.

Kila ProcessedResult (slip) ina ResultVerificationToken. Slip PDF inaonyesha
QR iliyo na URL: /results/verify/<token>/ — mzazi/mwalimu anascan bila
account, anapata ukurasa wenye matokeo halisi kutoka DB. Inaondoa slips za
kughushi: slip ya kweli ina QR inayolingana na DB; ya ghushi haipo.
"""
import logging

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .models import ProcessedResult, ResultVerificationToken
from .permissions import teacher_or_academic_required
from .services.pdf_export_service import (
    _build_student_result_pdf_bytes,
    _student_name,
)

logger = logging.getLogger(__name__)


def _get_or_create_token(result, user=None):
    """Token iliyo hai ya result hii — iundwe wastaharabu isipokuwa."""
    token = ResultVerificationToken.active_for(result)
    if token is None:
        token = ResultVerificationToken.objects.create(result=result, created_by=user)
    return token


def verify_url_for(token: ResultVerificationToken, request) -> str:
    """URL kamili ya QR — inatumia host ya request (au detanya env)."""
    import os
    base = os.getenv('PUBLIC_BASE_URL')
    if base:
        return f"{base.rstrip('/')}{reverse('result_verify', args=[token.token])}"
    return request.build_absolute_uri(reverse('result_verify', args=[token.token]))


@teacher_or_academic_required
@require_POST
def regenerate_result_token(request, result_id):
    """Regenerate (revoke old + new token) — slip zamani zinakufa."""
    result = get_object_or_404(
        ProcessedResult.objects.select_related('exam', 'student'),
        id=result_id,
        exam__school=request.user.school,
    )
    old = ResultVerificationToken.objects.filter(result=result).first()
    if old:
        old.revoked = True
        old.save(update_fields=['revoked'])
    ResultVerificationToken.objects.create(result=result, created_by=request.user)
    messages.success(request, "QR mpya imetengenezwa — slips za zamani hazithibitishwi tena.")
    return result.slip_redirect(request) if hasattr(result, 'slip_redirect') else _slip_redirect(request, result)


def _slip_redirect(request, result):
    from django.shortcuts import redirect
    return redirect(request.META.get('HTTP_REFERER') or reverse('exam_overview', args=[result.exam_id]))


def result_verify(request, token):
    """Ukurasa wa public verification — HAKUNA login.

    Onyesha matokeo kamili kwenye template, na muundo unaofanana na slip.
    Invalid/revoked token → page ya 'matokeo hayapatikani / yamebadilishwa'.
    """
    vt = (ResultVerificationToken.objects
          .select_related('result__exam__school', 'result__student')
          .filter(token=token)
          .first())
    if vt is None:
        return render(request, 'results/result_verify.html', {'invalid': True}, status=404)

    # Scan tracking (idempotent-ish: every hit counts, cheap)
    vt.scan_count += 1
    vt.last_scanned_at = timezone.now()
    vt.save(update_fields=['scan_count', 'last_scanned_at'])

    result = vt.result
    exam = result.exam
    student = result.student

    if vt.revoked:
        # Token ilibadilishwa — slip hii ya zamani rasmi imefutwa
        return render(request, 'results/result_verify.html', {
            'revoked': True,
            'student_name': _student_name(result),
            'exam': exam,
        }, status=410)

    from .models import ExamResult, Subject
    from .utils import get_grade_for_form

    scores = {
        er.subject_id: er.score
        for er in ExamResult.objects.filter(exam=exam, student=student).select_related('subject')
    }
    subjects = list(Subject.objects.filter(
        examresult__exam=exam, examresult__student=student,
    ).distinct().order_by('name'))
    total_students = ProcessedResult.objects.filter(exam=exam).count()

    is_primary = bool(exam.school and exam.school.is_primary)
    rows = []
    for subj in subjects:
        score = scores.get(subj.id)
        if score is None:
            continue
        grade = get_grade_for_form(score, exam.form, primary=is_primary)
        rows.append({'subject': subj.name, 'score': score, 'grade': grade})

    from .models import ProcessedResult as PR
    division = dict(PR.DIVISION_CHOICES).get(result.division, result.division)

    context = {
        'valid': True,
        'student_name': _student_name(result),
        'exam': exam,
        'student': student,
        'rows': rows,
        'total': result.total_score,
        'average': result.average_score,
        'points': result.points,
        'division': division,
        'position': result.position,
        'total_students': total_students,
        'scanned_at': vt.last_scanned_at,
    }
    return render(request, 'results/result_verify.html', context)
