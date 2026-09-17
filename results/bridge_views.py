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
from .services.ai_grader import grade_sheet, match_student, AIGradeError
from .services.annotate_ai import annotate_ai_sheet
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

    # ScanJob ni model ya app 'results' — ResultsRouter inaipeleka DB ya
    # 'results'. Transaction LAZIMA ifunguliwe kwenye DB hiyo hiyo, la
    # sivyo select_for_update inatoka nje ya transaction (500).
    job_db = ScanJob.objects.db

    with transaction.atomic(using=job_db):
        # Shule ya bridge tu — kazi za shule hiyo
        job = (
            ScanJob.objects.using(job_db).select_for_update(skip_locked=True)
            .filter(status=ScanJob.Status.PENDING, school=bridge.school)
            .order_by('created_at')
            .first()
        )
        if not job:
            return JsonResponse({'ok': True, 'job': None})

        job.status = ScanJob.Status.CLAIMED
        job.bridge = bridge
        job.claimed_at = timezone.now()
        job.save(using=job_db, update_fields=['status', 'bridge', 'claimed_at'])

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
            'print_marked': job.print_marked,
            'marked_url': request.build_absolute_uri(
                f'/shule/sahishi/bridge/api/marked/{job.pk}/'
            ) if job.print_marked else None,
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

    # Hali mbili za usahihishaji:
    #   AI   — MarkingScheme ya picha imepakiwa → Gemini inasoma karatasi
    #          halisi (majina, matching, list, essay, calculations) na kuipa alama
    #   OMR  — hakuna scheme ya picha → bubbles + ScanAnswerKey (njia ya zamani)
    scheme = job.exam.marking_schemes.filter(subject=subject).first()
    scheme_pages = []
    if scheme:
        for page in scheme.pages.all().order_by('page_number'):
            try:
                with page.image.open('rb') as fh:
                    scheme_pages.append(fh.read())
            except Exception:
                logger.warning('Scheme page %s haikusomeka', page.pk)
    use_ai = bool(scheme_pages)

    roster = []
    if use_ai:
        roster = list(FormStudent.objects.filter(
            school=exam.school, form=exam.form, is_active=True,
        ))

    data_list = [f.read() for f in images]

    ai_grades = [None] * len(images)
    if use_ai:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {
                ex.submit(grade_sheet, data_list[i], scheme_pages): i
                for i in range(len(images))
            }
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    ai_grades[i] = fut.result()
                except Exception as exc:
                    logger.warning('[AIGrader] karatasi %s imeshindikana: %s', i, exc)

    key_obj = ScanAnswerKey.objects.filter(exam=exam, subject=subject).first()
    answer_key = key_obj.key if key_obj else {}

    batch = ScanSheetBatch.objects.create(
        exam=exam, subject=subject, image_count=len(images),
        note=f'Bridge: {bridge.name}' + (' (AI)' if use_ai else ''),
    )
    job.batch = batch

    graded = review = 0
    for i, f in enumerate(images):
        data = data_list[i]
        sheet = ScanSheet(exam=exam, subject=subject, batch=batch)
        sheet.image.save(f.name, ContentFile(data), save=False)

        if use_ai:
            grade = ai_grades[i]
            if grade is None:
                sheet.status = ScanSheet.Status.NEEDS_REVIEW
                sheet.needs_review_reason = 'AI imeshindikana kuisoma'
                review += 1
            else:
                fs = match_student(
                    exam.school,
                    grade.get('student_name') or '',
                    grade.get('reg_number') or '',
                    roster,
                )
                if fs:
                    sheet.student = fs
                else:
                    sheet.status = ScanSheet.Status.NEEDS_REVIEW
                    sheet.needs_review_reason = (
                        'Haijamatch rostini: ' + (grade.get('student_name') or '?')
                    )[:200]
                sheet.result = {'ai': grade}
                try:
                    sheet.score = float(grade.get('total') or 0)
                    sheet.total = float(grade.get('max_total') or 0)
                except (TypeError, ValueError):
                    pass
                if sheet.status != ScanSheet.Status.NEEDS_REVIEW:
                    sheet.status = ScanSheet.Status.GRADED
                    graded += 1
                else:
                    review += 1
                # Alama nyekundu za AI kwenye karatasi halisi
                try:
                    annotated = annotate_ai_sheet(data, grade)
                    if annotated:
                        sheet.annotated_image.save(
                            f'ai_{i}.png', ContentFile(annotated), save=False,
                        )
                except Exception:
                    logger.exception('AI annotation imeshindikana sheet idx=%s', i)
        else:
            res = process_sheet(data, answer_key)

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

        sheet.save(using=ScanSheet.objects.db)
        # Alama nyekundu za OMR (njia ya zamani)
        if not use_ai and sheet.score is not None and answer_key:
            _annotate_sheet(sheet, answer_key)

    job.status = ScanJob.Status.DONE
    job.completed_at = timezone.now()
    mode = 'AI' if use_ai else 'OMR'
    job.result_message = f'Karatasi {len(images)} ({mode}): {graded} graded, {review} review'
    job.save(using=ScanJob.objects.db,
             update_fields=['status', 'batch', 'completed_at', 'result_message'])
    logger.info('Bridge job #%s done: %s', job.pk, job.result_message)

    # Ripoti ya uchapishaji itasasishwa na bridge
    return JsonResponse({
        'ok': True,
        'graded': graded,
        'review': review,
        'total': len(images),
        'print_marked': job.print_marked,
        'marked_url': request.build_absolute_uri(
            f'/shule/sahishi/bridge/api/marked/{job.pk}/'
        ) if job.print_marked else None,
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
        print_marked=request.POST.get('print_marked') == 'on',
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
