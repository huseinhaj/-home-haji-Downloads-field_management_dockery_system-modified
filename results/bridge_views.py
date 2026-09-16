"""
Sahishi Bridge API.

Bridge (PC ya shule) inatumia token kwenye header: Authorization: Bearer sb_...
  GET  /shule/sahishi/bridge/api/ping/                  - kuthibitisha token + status
  POST /shule/sahishi/bridge/api/claim/                 - kupata kazi mpya (atomic)
  POST /shule/sahishi/bridge/api/upload/<job_id>/       - kutuma picha za scan

Mwalimu (kivinjari):
  POST /shule/sahishi/bridge/exam/<id>/subject/<id>/anza/   - kutengeneza ScanJob
  GET  /shule/sahishi/bridge/exam/<id>/subject/<id>/hali/   - JSON ya job status (polling)
"""
import logging

from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Exam, FormStudent, School, Subject
from .permissions import teacher_or_academic_required
from .scan_models import ScanAnswerKey, ScanSheet, ScanSheetBatch
from .scan_views import _annotate_sheet, _class_roster, _get_exam_or_404
from .services.scan_grader import process_sheet
from .services.upload_processing_service import recompute_processed_results_for_exam
from .bridge_models import SahishiBridge, ScanJob, generate_bridge_token

logger = logging.getLogger(__name__)


# ================= Bridge (token) endpoints =================

def _bridge_from_request(request):
    """Thibitisha token ya bridge kutoka header au query param."""
    auth = request.headers.get('Authorization', '')
    token = ''
    if auth.startswith('Bearer '):
        token = auth[7:].strip()
    if not token:
        token = request.GET.get('token', '').strip()
    if not token:
        return None
    return SahishiBridge.objects.filter(token=token, active=True).first()


@require_GET
@csrf_exempt
def bridge_ping(request):
    bridge = _bridge_from_request(request)
    if not bridge:
        return JsonResponse({'ok': False, 'error': 'Token si sahihi'}, status=403)
    bridge.last_seen = timezone.now()
    bridge.last_ip = request.META.get('REMOTE_ADDR')
    bridge.save(update_fields=['last_seen', 'last_ip'])
    return JsonResponse({
        'ok': True,
        'bridge': bridge.name,
        'scanner': bridge.scanner_name,
        'server_time': timezone.now().isoformat(),
    })


@require_POST
@csrf_exempt
def bridge_claim(request):
    """Bridge inauliza kazi mpya — inapata job moja PENDING (atomic select_for_update)."""
    bridge = _bridge_from_request(request)
    if not bridge:
        return JsonResponse({'ok': False, 'error': 'Token si sahihi'}, status=403)
    bridge.last_seen = timezone.now()
    bridge.last_ip = request.META.get('REMOTE_ADDR')
    bridge.save(update_fields=['last_seen', 'last_ip'])

    from django.db import transaction

    with transaction.atomic():
        # Shule ya bridge tu — kazi za shule hiyo
        job = (
            ScanJob.objects.select_for_update(skip_locked=True)
            .filter(status=ScanJob.Status.PENDING, school=bridge.school)
            .order_by('created_at')
            .first()
        )
        if not job:
            return JsonResponse({'ok': True, 'job': None})

        job.status = ScanJob.Status.CLAIMED
        job.bridge = bridge
        job.claimed_at = timezone.now()
        job.save(update_fields=['status', 'bridge', 'claimed_at'])

    return JsonResponse({
        'ok': True,
        'job': {
            'id': job.pk,
            'exam_id': job.exam_id,
            'subject_id': job.subject_id,
            'exam_name': job.exam.name,
            'subject_name': job.subject.name,
            'pages': job.pages,
            'duplex': job.duplex,
            'dpi': job.dpi,
            'upload_url': request.build_absolute_uri(
                f'/shule/sahishi/bridge/api/upload/{job.pk}/'
            ),
        },
    })


@require_POST
@csrf_exempt
def bridge_upload(request, job_id):
    """Bridge inatuma picha za scan. Fields: images (multiple), pages_done."""
    bridge = _bridge_from_request(request)
    if not bridge:
        return JsonResponse({'ok': False, 'error': 'Token si sahihi'}, status=403)

    job = get_object_or_404(
        ScanJob.objects.select_related('exam', 'subject'), pk=job_id,
    )
    if job.bridge_id and job.bridge_id != bridge.pk:
        return JsonResponse({'ok': False, 'error': 'Kazi si ya bridge hii'}, status=403)

    images = request.FILES.getlist('images')
    if not images:
        job.status = ScanJob.Status.FAILED
        job.result_message = 'Bridge ilituma picha 0'
        job.save(update_fields=['status', 'result_message'])
        return JsonResponse({'ok': False, 'error': 'Hakuna picha'}, status=400)

    exam, subject = job.exam, job.subject
    key_obj = ScanAnswerKey.objects.filter(exam=exam, subject=subject).first()
    answer_key = key_obj.key if key_obj else {}

    batch = ScanSheetBatch.objects.create(
        exam=exam, subject=subject, image_count=len(images),
        note=f'Bridge: {bridge.name}',
    )
    job.batch = batch

    graded = review = 0
    for f in images:
        data = f.read()
        res = process_sheet(data, answer_key)

        sheet = ScanSheet(exam=exam, subject=subject, batch=batch)
        sheet.image.save(f.name, ContentFile(data), save=False)

        qr = res.get('qr')
        if qr and qr['e'] == exam.pk and qr.get('sub') in (0, subject.pk):
            fs = FormStudent.objects.filter(pk=qr['s']).first()
            sheet.student = fs
            sheet.page_number = qr['p']
            if fs is None:
                sheet.status = ScanSheet.Status.NEEDS_REVIEW
                sheet.needs_review_reason = 'Mwanafunzi hayupo rostini'
        else:
            sheet.status = ScanSheet.Status.NEEDS_REVIEW
            sheet.needs_review_reason = res.get('review_reason') or 'QR haikusomeka'

        sheet.result = {'answers': res.get('answers', {})}
        if res.get('score') is not None:
            sheet.score = res['score']
            sheet.total = res.get('total') or len(answer_key)
            if sheet.status != ScanSheet.Status.NEEDS_REVIEW:
                sheet.status = ScanSheet.Status.GRADED
                graded += 1
        if sheet.status == ScanSheet.Status.NEEDS_REVIEW:
            review += 1
        sheet.save()
        # Alama nyekundu (✓/✗/○ + jumla) kwenye karatasi
        if sheet.score is not None and answer_key:
            _annotate_sheet(sheet, answer_key)

    job.status = ScanJob.Status.DONE
    job.completed_at = timezone.now()
    job.result_message = f'Karatasi {len(images)}: {graded} graded, {review} review'
    job.save(update_fields=['status', 'batch', 'completed_at', 'result_message'])
    logger.info('Bridge job #%s done: %s', job.pk, job.result_message)

    return JsonResponse({
        'ok': True,
        'graded': graded,
        'review': review,
        'total': len(images),
    })


@require_POST
@csrf_exempt
def bridge_fail(request, job_id):
    """Bridge inaripoti kushindwa (scanner haipo, karatasi zimekwama...)."""
    bridge = _bridge_from_request(request)
    if not bridge:
        return JsonResponse({'ok': False, 'error': 'Token si sahihi'}, status=403)
    job = get_object_or_404(ScanJob, pk=job_id)
    reason = (request.POST.get('reason') or 'Haijulikani')[:250]
    job.status = ScanJob.Status.FAILED
    job.result_message = reason
    job.completed_at = timezone.now()
    job.save(update_fields=['status', 'result_message', 'completed_at'])
    return JsonResponse({'ok': True})


# ================= Teacher (browser) endpoints =================

@require_POST
@teacher_or_academic_required
def bridge_start_job(request, exam_id, subject_id):
    """Mwalimu anabonyeza 'Anza Scan' → ScanJob mpya (PENDING)."""
    exam = _get_exam_or_404(exam_id, request.user)
    subject = get_object_or_404(Subject, pk=subject_id)
    school = getattr(request.user, 'school', None)

    pages = max(1, min(200, int(request.POST.get('pages', 40))))
    duplex = request.POST.get('duplex') == 'on'

    job = ScanJob.objects.create(
        school=school, exam=exam, subject=subject,
        pages=pages, duplex=duplex,
        note=request.POST.get('note', '')[:200],
    )
    return JsonResponse({'ok': True, 'job_id': job.pk})


@require_GET
@teacher_or_academic_required
def bridge_job_status(request, exam_id, subject_id, job_id):
    """Polling ya mwalimu: hali ya job + counts za karatasi."""
    exam = _get_exam_or_404(exam_id, request.user)
    job = get_object_or_404(ScanJob, pk=job_id, exam=exam)
    data = {
        'ok': True,
        'job_id': job.pk,
        'status': job.status,
        'status_display': job.get_status_display(),
        'result_message': job.result_message,
        'graded': 0, 'review': 0,
    }
    if job.batch_id:
        b = job.batch
        data['graded'] = b.sheets.filter(status=ScanSheet.Status.GRADED).count()
        data['review'] = b.sheets.filter(status=ScanSheet.Status.NEEDS_REVIEW).count()
    return JsonResponse(data)


@teacher_or_academic_required
def bridge_page(request, exam_id, subject_id):
    """Ukurasa wa 'Scan kwa Bridge' (live progress)."""
    exam = _get_exam_or_404(exam_id, request.user)
    subject = get_object_or_404(Subject, pk=subject_id)
    jobs = ScanJob.objects.filter(exam=exam, subject=subject)[:5]
    return render(request, 'results/scan_bridge.html', {
        'exam': exam, 'subject': subject, 'jobs': jobs,
    })


# ================= Admin/academic: token management =================

@require_POST
def bridge_rotate_token(request, bridge_id):
    """Zana za kubadilisha token (admin site au academic)."""
    from .permissions import academic_required
    from .bridge_models import SahishiBridge

    @academic_required
    def _view(request, bridge_id):
        bridge = get_object_or_404(SahishiBridge, pk=bridge_id)
        bridge.rotate_token()
        messages.success(request, f'Token mpya ya "{bridge.name}" imetolewa.')
        return redirect(request.META.get('HTTP_REFERER') or 'admin:index')

    return _view(request, bridge_id)
