"""
Views za Marking Scheme za Sahishi.

Mtiririko:
  1. Mwalimu anachagua somo → anachapisha karatasi za SCHEME (tupu)
  2. Anajaza majibu kwenye bubbles kwa pen
  3. Anascan/upload scheme (PDF au picha) → mfumo unasoma kwa OMR
  4. CHOICE: inakuwa ScanAnswerKey moja kwa moja
     CALC: inabaki kama marejeleo (picha) kwa review ya mwalimu
"""
import logging

from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Exam, Subject
from .permissions import teacher_or_academic_required
from .scan_models import MarkingScheme, MarkingSchemePage
from .scan_views import _get_exam_or_404
from .services.scan_scheme import (
    build_scheme_sheet_pdf,
    parse_scheme_pages,
    pdf_to_images,
    sync_answer_key,
)

logger = logging.getLogger(__name__)


@teacher_or_academic_required
def scheme_print(request, exam_id, subject_id):
    """Chapisha karatasi za scheme tupu (maswali 90 = kurasa 3)."""
    exam = _get_exam_or_404(exam_id, request.user)
    subject = get_object_or_404(Subject, pk=subject_id)
    pages = max(1, min(3, int(request.GET.get('pages', 3))))
    pdf = build_scheme_sheet_pdf(exam, subject, pages=pages)
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="scheme_{exam.pk}_{subject.pk}.pdf"'
    return resp


@teacher_or_academic_required
def scheme_upload(request, exam_id, subject_id):
    """Pakia scheme (PDF au picha) → OMR → MarkingScheme + ScanAnswerKey."""
    exam = _get_exam_or_404(exam_id, request.user)
    subject = get_object_or_404(Subject, pk=subject_id)

    if request.method == 'POST':
        files = request.FILES.getlist('files')
        if not files:
            messages.error(request, 'Chagua faili angalau moja (PDF au picha).')
            return redirect('scan_scheme_upload', exam_id=exam.pk, subject_id=subject.pk)

        # Kusanya picha: PDF zinageuzwa picha; picha zinapitishwa moja kwa moja
        images = []
        for f in files:
            data = f.read()
            if f.name.lower().endswith('.pdf'):
                images.extend(pdf_to_images(data))
            else:
                images.append(data)

        if not images:
            messages.error(request, 'Hakuna picha zilizopatikana.')
            return redirect('scan_scheme_upload', exam_id=exam.pk, subject_id=subject.pk)

        result = parse_scheme_pages(
            images, expected_exam_id=exam.pk, expected_subject_id=subject.pk,
        )

        teacher_name = getattr(request.user, 'full_name', '') or \
            getattr(request.user, 'email', '') or ''

        scheme, created = MarkingScheme.objects.update_or_create(
            exam=exam, subject=subject,
            defaults={
                'kind': result['kind'],
                'parsed_key': result['parsed_key'],
                'parsed_count': len(result['parsed_key']),
                'uploaded_by': teacher_name,
            },
        )
        # Futa kurasa za zamani, weka mpya
        scheme.pages.all().delete()
        for p in result['pages']:
            page = MarkingSchemePage(scheme=scheme, page_number=p['page_number'])
            page.image.save(
                f'scheme_{exam.pk}_{subject.pk}_p{p["page_number"]}.png',
                ContentFile(p['image']), save=False,
            )
            page.parsed = p['parsed']
            page.save()

        # CHOICE → andika ScanAnswerKey moja kwa moja
        key_count = sync_answer_key(scheme)

        for w in result['warnings']:
            messages.warning(request, w)

        if result['kind'] == 'CHOICE':
            messages.success(
                request,
                f'Scheme imesomwa: maswali {len(result["parsed_key"])}. '
                f'Answer key imewekwa moja kwa moja ({key_count} maswali).',
            )
        else:
            messages.success(
                request,
                'Scheme imehifadhiwa kama marejeleo (masomo ya calculation). '
                'Ukurasa wa review utaiona wakati wa kusahihisha.',
            )
        return redirect('scan_upload', exam_id=exam.pk, subject_id=subject.pk)

    return render(request, 'results/scan_scheme.html', {
        'exam': exam, 'subject': subject,
        'scheme': MarkingScheme.objects.filter(exam=exam, subject=subject).first(),
    })
