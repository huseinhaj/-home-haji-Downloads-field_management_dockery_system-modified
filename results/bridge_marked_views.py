"""
Endpoint ya Bridge kupakua karatasi zilizoalama nyekundu (ZIP ya PNG).

Bridge (PC ya shule) inapakua hii ZIP baada ya upload, kisha inachapisha
kila ukurasa kwa printer kupitia CUPS (`lp`) — mwalimu anatoa nakala
zenye alama nyekundu moja kwa moja kwenye output tray.
"""
import io
import logging
import zipfile

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .bridge_views import _bridge_from_request
from .models import FormStudent
from .scan_models import ScanSheet
from .services.scan_annotate import annotate_full_sheet

logger = logging.getLogger(__name__)


@require_GET
@csrf_exempt
def bridge_marked_zip(request, job_id):
    """ZIP yenye karatasi zote za job hii zilizoalama nyekundu."""
    from .bridge_models import ScanJob

    bridge = _bridge_from_request(request)
    if not bridge:
        return HttpResponse('Token si sahihi', status=403)

    job = get_object_or_404(
        ScanJob.objects.select_related('exam', 'subject'), pk=job_id,
    )
    if job.bridge_id and job.bridge_id != bridge.pk:
        return HttpResponse('Kazi si ya bridge hii', status=403)

    if not job.batch_id:
        return HttpResponse('Kazi haina karatasi bado', status=404)

    answer_key_obj = job.exam.scan_answer_keys.filter(
        subject=job.subject,
    ).first()
    answer_key = answer_key_obj.key if answer_key_obj else {}

    sheets = (
        ScanSheet.objects.filter(batch=job.batch)
        .select_related('student').order_by('student__first_name', 'page_number')
    )
    if not sheets:
        return HttpResponse('Hakuna karatasi', status=404)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for sheet in sheets:
            # Picha ya msingi
            try:
                with sheet.image.open('rb') as fh:
                    base_bytes = fh.read()
            except Exception:
                logger.warning('Sheet %s: picha haipatikani', sheet.pk)
                continue

            # Annotate (au tumia iliyopo)
            annotated = None
            if sheet.annotated_image:
                try:
                    with sheet.annotated_image.open('rb') as fh:
                        annotated = fh.read()
                except Exception:
                    annotated = None
            if annotated is None and answer_key:
                answers = (sheet.result or {}).get('answers', {})
                annotated = annotate_full_sheet(
                    base_bytes, answers, answer_key,
                    page_number=sheet.page_number or 1,
                    total_score=sheet.score,
                    total_questions=sheet.total,
                )

            final_bytes = annotated or base_bytes

            # Jina: mwanafunzi + ukurasa (mf. "Amina_Mtoto_p1.png")
            if sheet.student:
                name = ''.join(
                    ch for ch in sheet.student.full_name.replace(' ', '_')
                    if ch.isalnum() or ch == '_'
                )[:40]
            else:
                name = f'Unknown_{sheet.pk}'
            zf.writestr(f'{name}_p{sheet.page_number or 1}.png', final_bytes)

    resp = HttpResponse(buf.getvalue(), content_type='application/zip')
    resp['Content-Disposition'] = f'attachment; filename="marked_job_{job_id}.zip"'
    return resp
