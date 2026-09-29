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
            'mode': job.mode,
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

    if job.mode == ScanJob.Mode.CAPTURE:
        return _capture_upload(job, images)

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


def _capture_page_path(job_id, page):
    return f'sahishi_capture/job_{job_id}/page_{page:04d}.png'


def _capture_upload(job, images):
    """CAPTURE: karatasi zilizosahihishwa tayari → reg number + alama.

    Hakuna ExamResult inayoandikwa hapa — matokeo yanakaa kwenye
    job.capture_result, Marks Entry inayachukua na kujaza jedwali, na
    mwalimu anakagua kisha anabonyeza Hifadhi kama kawaida.
    """
    from concurrent.futures import ThreadPoolExecutor

    from django.core.files.storage import default_storage

    from .services.score_capture import (
        build_capture_payload, read_paper_header, reg_map_for_roster,
    )

    job.status = ScanJob.Status.UPLOADING
    job.save(using=ScanJob.objects.db, update_fields=['status'])

    data_list = [f.read() for f in images]

    # Picha zinahifadhiwa ili mwalimu aone karatasi halisi anapokagua
    # alama ya mashaka au karatasi isiyolingana na mwanafunzi yeyote.
    for i, data in enumerate(data_list, 1):
        try:
            default_storage.save(_capture_page_path(job.pk, i), ContentFile(data))
        except Exception:
            logger.exception('Capture job #%s: ukurasa %s haukuhifadhiwa', job.pk, i)

    def _read(i):
        try:
            return read_paper_header(data_list[i])
        except Exception as exc:
            logger.warning('[ScoreCapture] job #%s ukurasa %s: %s', job.pk, i + 1, exc)
            return None

    with ThreadPoolExecutor(max_workers=4) as ex:
        raw_reads = list(ex.map(_read, range(len(data_list))))

    roster = [r for r in (job.capture_roster or []) if isinstance(r, dict) and 'id' in r]
    reg_map = reg_map_for_roster(job.exam, [r['id'] for r in roster])
    payload = build_capture_payload(
        [{'page': i + 1, 'read': r} for i, r in enumerate(raw_reads)],
        roster, reg_map,
    )

    job.capture_result = payload
    job.status = ScanJob.Status.DONE
    job.completed_at = timezone.now()
    job.result_message = (
        f'Karatasi {len(images)}: {len(payload["matched"])} zimelingana, '
        f'{len(payload["unmatched"])} hazijalingana, {len(payload["missing"])} hazina karatasi'
    )[:255]
    job.save(using=ScanJob.objects.db, update_fields=[
        'capture_result', 'status', 'completed_at', 'result_message',
    ])
    logger.info('Capture job #%s done: %s', job.pk, job.result_message)
    return JsonResponse({
        'ok': True,
        'mode': job.mode,
        'total': len(images),
        'graded': len(payload['matched']),
        'review': len(payload['unmatched']),
        'print_marked': False,
        'marked_url': None,
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


# ================= Capture Scores (Marks Entry) =================

BRIDGE_ONLINE_SECONDS = 60  # bridge inauliza kila sekunde 4


def _bridge_online(school):
    cutoff = timezone.now() - timezone.timedelta(seconds=BRIDGE_ONLINE_SECONDS)
    return SahishiBridge.objects.filter(
        school=school, active=True, last_seen__gte=cutoff,
    ).exists()


def _teacher_capture_job(request, job_id):
    job = get_object_or_404(
        ScanJob.objects.select_related('exam', 'subject'),
        pk=job_id, mode=ScanJob.Mode.CAPTURE,
    )
    school = getattr(request.user, 'school', None)
    if school is None or job.school_id != school.pk:
        return None
    return job


@require_POST
@teacher_or_academic_required
def bridge_capture_start(request):
    """Marks Entry → "Capture Scores": ScanJob ya CAPTURE kwa bridge ya shule.

    Fields: exam_id, subject_id, roster (JSON [{id, name}]), pages, duplex.
    """
    import json

    from .marks_entry import _teacher_exam

    teacher = request.user
    school = getattr(teacher, 'school', None)
    if school is None:
        return JsonResponse({'error': 'Akaunti yako haina shule — bridge haiwezi kupatikana.'}, status=400)

    exam = _teacher_exam(teacher, request.POST.get('exam_id'))
    if exam is None:
        return JsonResponse({'error': 'Mtihani haupatikani.'}, status=404)
    subject = get_object_or_404(Subject, id=request.POST.get('subject_id'))
    if not teacher.subjects.filter(pk=subject.pk).exists():
        return JsonResponse({'error': 'Hujapangiwa somo hili.'}, status=403)

    try:
        roster = json.loads(request.POST.get('roster') or '[]')
    except json.JSONDecodeError:
        roster = []
    roster = [
        {'id': int(r['id']), 'name': str(r.get('name') or '')[:200]}
        for r in roster
        if isinstance(r, dict) and str(r.get('id', '')).isdigit()
    ]
    if not roster:
        return JsonResponse({'error': 'Orodha ya wanafunzi iko tupu — pakia orodha kwanza.'}, status=400)

    if not SahishiBridge.objects.filter(school=school, active=True).exists():
        return JsonResponse({
            'error': 'Shule yako haina Sahishi Bridge. Mwombe Mtaaluma/Admin aisajili '
                     '(Admin → Sahishi Bridges) na kuiwasha kwenye PC yenye printer.',
        }, status=400)

    try:
        pages = max(1, min(200, int(request.POST.get('pages') or 60)))
    except ValueError:
        pages = 60

    job = ScanJob.objects.create(
        school=school, exam=exam, subject=subject,
        mode=ScanJob.Mode.CAPTURE,
        pages=pages, duplex=request.POST.get('duplex') in ('on', '1', 'true'),
        dpi=200,  # reg number + alama tu — 200dpi inatosha na ni haraka
        capture_roster=roster,
        requested_by_id=teacher.pk,
        note='Capture score',
    )
    return JsonResponse({
        'ok': True,
        'job_id': job.pk,
        'bridge_online': _bridge_online(school),
    })


@require_GET
@teacher_or_academic_required
def bridge_capture_status(request, job_id):
    """Polling ya Marks Entry. Ikiisha inarudisha muundo ule ule wa
    scoresheet_extract_status (matched/unmatched/missing/warnings)."""
    job = _teacher_capture_job(request, job_id)
    if job is None:
        return JsonResponse({'error': 'Kazi haipatikani.'}, status=404)

    if job.status == ScanJob.Status.DONE:
        result = job.capture_result or {}
        return JsonResponse({
            'status': 'done',
            'job_id': job.pk,
            'message': job.result_message,
            'matched': result.get('matched', []),
            'unmatched': result.get('unmatched', []),
            'missing': result.get('missing', []),
            'warnings': result.get('warnings', []),
        })
    if job.status in (ScanJob.Status.FAILED, ScanJob.Status.CANCELLED):
        return JsonResponse({
            'status': 'failed',
            'error': job.result_message or job.get_status_display(),
        })
    return JsonResponse({
        'status': 'processing',
        'job_status': job.status,
        'status_display': job.get_status_display(),
        'bridge_online': _bridge_online(job.school),
    })


@require_POST
@teacher_or_academic_required
def bridge_capture_cancel(request, job_id):
    """Mwalimu anaghairi kazi ambayo bridge bado haijaichukua."""
    job = _teacher_capture_job(request, job_id)
    if job is None:
        return JsonResponse({'error': 'Kazi haipatikani.'}, status=404)
    updated = ScanJob.objects.filter(pk=job.pk, status=ScanJob.Status.PENDING).update(
        status=ScanJob.Status.CANCELLED, result_message='Imeghairiwa na mwalimu',
        completed_at=timezone.now(),
    )
    if not updated:
        return JsonResponse({'error': 'Bridge imeshaanza kuscan — subiri iishe.'}, status=409)
    return JsonResponse({'ok': True})


@require_GET
@teacher_or_academic_required
def bridge_capture_page(request, job_id, page):
    """Picha ya ukurasa mmoja wa capture — mwalimu anaikagua dhidi ya alama."""
    from django.core.files.storage import default_storage
    from django.http import FileResponse, Http404

    job = _teacher_capture_job(request, job_id)
    path = _capture_page_path(job_id, page)
    if job is None or not default_storage.exists(path):
        raise Http404('Ukurasa haupatikani.')
    return FileResponse(default_storage.open(path, 'rb'), content_type='image/png')
