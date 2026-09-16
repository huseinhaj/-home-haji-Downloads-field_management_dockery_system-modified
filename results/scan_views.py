"""
Views za Sahishi (scan & auto-grade) — zimeunganishwa na models za results:
  - Rosti: FormStudent (school, form, is_active, academic_year=exam.year)
  - Matokeo: ExamResult (score 0-100) kupitia _student_from_form_student
  - Submission: SubjectSubmission (method='UPLOAD', submitted_by='Sahishi Scan')
"""
import json
import logging

from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ScanKeyForm, ScanUploadForm
from .marks_entry import _student_from_form_student
from .models import Exam, ExamResult, FormStudent, Subject, SubjectSubmission
from .scan_models import MarkingScheme, ScanAnswerKey, ScanSheet, ScanSheetBatch
from .permissions import teacher_or_academic_required
from .services.scan_annotate import annotate_full_sheet
from .services.scan_grader import process_sheet
from .services.scan_pdf import build_answer_sheets_pdf
from .services.upload_processing_service import recompute_processed_results_for_exam

logger = logging.getLogger(__name__)


def _get_exam_or_404(exam_id, user):
    """Fuatilia muundo wa views._get_exam_or_404: shule lazima iingiliane."""
    exam = Exam.objects.filter(id=exam_id).first()
    if exam is None:
        raise Http404("Mtihani haujapatikana.")
    user_school = getattr(user, 'school', None)
    if user_school and exam.school_id and exam.school_id != user_school.id:
        raise Http404("Mtihani hauko kwenye shule yako.")
    return exam


def _get_subject_or_404(subject_id):
    return get_object_or_404(Subject, id=subject_id)


def _get_or_create_key(exam, subject):
    key, _ = ScanAnswerKey.objects.get_or_create(exam=exam, subject=subject)
    return key


def _annotate_sheet(sheet, answer_key):
    """Chora alama nyekundu (✓/✗/○ + jumla) kwenye karatasi iliyosahihishwa."""
    try:
        if not sheet.image or not answer_key:
            return
        with sheet.image.open('rb') as fh:
            data = fh.read()
        answers = (sheet.result or {}).get('answers', {})
        annotated = annotate_full_sheet(
            data, answers, answer_key,
            page_number=sheet.page_number or 1,
            total_score=sheet.score,
            total_questions=sheet.total,
        )
        if annotated:
            name = f'annotated_{sheet.pk}.png'
            sheet.annotated_image.save(name, ContentFile(annotated), save=False)
    except Exception:
        logger.exception('Annotation imeshindikana sheet=%s', sheet.pk)


def _sheet_question_rows(sheet, answer_key):
    """Mistari ya kila swali kwa sheet: (namba, jibu la mwanafunzi, jibu sahihi, hali).
    hali: 'ok' | 'wrong' | 'blank' | 'unknown' (swali nje ya key)."""
    answers = (sheet.result or {}).get('answers', {})
    rows = []
    for qnum in sorted(answer_key, key=lambda x: int(x) if str(x).isdigit() else 0):
        given = answers.get(qnum)
        key_ans = str(answer_key[qnum]).upper()
        if given is None:
            state = 'blank'
        elif str(given).upper() == key_ans:
            state = 'ok'
        else:
            state = 'wrong'
        rows.append((qnum, given or '—', key_ans, state))
    return rows


def _build_student_results(exam, subject, answer_key):
    """Kundi la karatasi kwa mwanafunzi → matokeo ya mtihani mzima.
    Inarudi orodha ya dicts: student, sheets (na rows za maswali), score, total."""
    sheets = ScanSheet.objects.filter(
        exam=exam, subject=subject,
        status__in=[ScanSheet.Status.GRADED, ScanSheet.Status.IMPORTED],
        student__isnull=False,
    ).select_related('student', 'batch').order_by('student__first_name', 'page_number')

    by_student = {}
    for sheet in sheets:
        entry = by_student.setdefault(sheet.student_id, {
            'student': sheet.student,
            'sheets': [],
            'score': 0,
            'total': 0,
            'pages': 0,
        })
        entry['sheets'].append({
            'sheet': sheet,
            'rows': _sheet_question_rows(sheet, answer_key),
        })
        if sheet.score is not None:
            entry['score'] += sheet.score
            entry['total'] = max(entry['total'], sheet.total or 0)
            entry['pages'] += 1

    results = sorted(by_student.values(), key=lambda e: -(e['score']))
    # Position (nafasi) — wanafunzi wenye alama sawa wanapata nafasi sawa
    position = 0
    last_score = None
    for i, entry in enumerate(results, start=1):
        if entry['score'] != last_score:
            position = i
            last_score = entry['score']
        entry['position'] = position
    return results


def _class_roster(exam, subject):
    """Rosti ya wanafunzi wa darasa hili kwa somo hili (kama marks_entry)."""
    qs = FormStudent.objects.filter(
        form=exam.form, is_active=True, academic_year=exam.year,
    )
    if exam.school_id:
        qs = qs.filter(school=exam.school)
    qs = qs.order_by('id')
    # Somo filter: wanafunzi wenye somo zilizopewa tu ndio wanaonekana
    out = []
    for fs in qs:
        if fs.subjects.exists() and not fs.subjects.filter(pk=subject.pk).exists():
            continue
        out.append(fs)
    return out


# ---------------- Answer key ----------------

@teacher_or_academic_required
def scan_answer_key(request, exam_id, subject_id):
    exam = _get_exam_or_404(exam_id, request.user)
    subject = _get_subject_or_404(subject_id)
    key = _get_or_create_key(exam, subject)

    if request.method == 'POST':
        form = ScanKeyForm(request.POST)
        if form.is_valid():
            key.key = form.cleaned_data['key']
            key.save()
            messages.success(request, 'Answer key imehifadhiwa.')
            return redirect('scan_upload', exam_id=exam.pk, subject_id=subject.pk)
    else:
        form = ScanKeyForm(initial={'key': json.dumps(key.key, ensure_ascii=False)})

    return render(request, 'results/scan_answer_key.html', {
        'exam': exam, 'subject': subject, 'form': form,
        'n_questions': len(key.key),
    })


# ---------------- Print karatasi ----------------

@teacher_or_academic_required
def scan_print(request, exam_id, subject_id):
    exam = _get_exam_or_404(exam_id, request.user)
    subject = _get_subject_or_404(subject_id)
    pages = max(1, min(3, int(request.GET.get('pages', 1))))
    students = _class_roster(exam, subject)
    if not students:
        messages.warning(
            request,
            'Hakuna wanafunzi kwenye rosti ya Form %s (%s). Pakia rosti kwanza.'
            % (exam.form, exam.year),
        )
        return redirect('exam_overview', exam_id=exam.pk)

    pdf = build_answer_sheets_pdf(exam, subject, students, pages_per_student=pages)
    resp = HttpResponse(pdf, content_type='application/pdf')
    fname = f'sheets_{exam.pk}_{subject.pk}.pdf'
    resp['Content-Disposition'] = f'inline; filename="{fname}"'
    return resp


# ---------------- Upload / scan ----------------

@teacher_or_academic_required
def scan_upload(request, exam_id, subject_id):
    exam = _get_exam_or_404(exam_id, request.user)
    subject = _get_subject_or_404(subject_id)
    key = _get_or_create_key(exam, subject)

    if request.method == 'POST':
        form = ScanUploadForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist('images')
            if not files:
                messages.error(request, 'Chagua picha angalau moja.')
                return redirect('scan_upload', exam_id=exam.pk, subject_id=subject.pk)

            if not key.key:
                messages.error(request, 'Weka answer key kwanza kabla ya kusahihisha.')
                return redirect('scan_answer_key', exam_id=exam.pk, subject_id=subject.pk)

            batch = ScanSheetBatch.objects.create(
                exam=exam, subject=subject, image_count=len(files),
                note=form.cleaned_data.get('note', ''),
            )
            graded = review = 0
            for f in files:
                data = f.read()
                res = process_sheet(data, key.key)

                sheet = ScanSheet(exam=exam, subject=subject, batch=batch)
                sheet.image.save(f.name, ContentFile(data), save=False)

                qr = res.get('qr')
                if qr and qr['e'] == exam.pk and qr.get('sub') in (0, subject.pk):
                    fs = FormStudent.objects.filter(pk=qr['s']).first()
                    sheet.student = fs
                    sheet.page_number = qr['p']
                    if fs is None:
                        sheet.status = ScanSheet.Status.NEEDS_REVIEW
                        sheet.needs_review_reason = 'Mwanafunzi hayupo kwenye rosti'
                else:
                    sheet.status = ScanSheet.Status.NEEDS_REVIEW
                    sheet.needs_review_reason = res.get('review_reason') or 'QR haikusomeka'

                sheet.result = {'answers': res.get('answers', {})}
                if res.get('score') is not None:
                    sheet.score = res['score']
                    sheet.total = res.get('total') or len(key.key)
                    if sheet.status != ScanSheet.Status.NEEDS_REVIEW:
                        sheet.status = ScanSheet.Status.GRADED
                        graded += 1
                if sheet.status == ScanSheet.Status.NEEDS_REVIEW:
                    review += 1
                sheet.save()
                # Alama nyekundu (✓/✗/○ + jumla) — kwa zilizopata score
                if sheet.score is not None:
                    _annotate_sheet(sheet, key.key)

            messages.success(
                request,
                f'Karatasi {len(files)} zimepokelewa: {graded} zimesahihishwa, '
                f'{review} zinahitaji ukaguzi.',
            )
            return redirect('scan_review', exam_id=exam.pk, subject_id=subject.pk)
    else:
        form = ScanUploadForm()

    graded_count = ScanSheet.objects.filter(
        exam=exam, subject=subject, status=ScanSheet.Status.GRADED,
    ).count()
    review_count = ScanSheet.objects.filter(
        exam=exam, subject=subject, status=ScanSheet.Status.NEEDS_REVIEW,
    ).count()
    imported_count = ScanSheet.objects.filter(
        exam=exam, subject=subject, status=ScanSheet.Status.IMPORTED,
    ).count()
    scheme = MarkingScheme.objects.filter(exam=exam, subject=subject).first()

    return render(request, 'results/scan_upload.html', {
        'exam': exam, 'subject': subject, 'form': form,
        'has_key': bool(key.key), 'key_count': len(key.key),
        'graded_count': graded_count, 'review_count': review_count,
        'imported_count': imported_count,
        'roster_count': len(_class_roster(exam, subject)),
        'scheme': scheme,
    })


# ---------------- Review queue ----------------

@teacher_or_academic_required
def scan_review(request, exam_id, subject_id):
    exam = _get_exam_or_404(exam_id, request.user)
    subject = _get_subject_or_404(subject_id)

    sheets = ScanSheet.objects.filter(
        exam=exam, subject=subject,
    ).select_related('student', 'batch').order_by('status', 'id')

    roster = _class_roster(exam, subject)
    graded_count_total = sheets.filter(
        status=ScanSheet.Status.GRADED, student__isnull=False,
        score__isnull=False,
    ).count()
    scheme = MarkingScheme.objects.filter(exam=exam, subject=subject).first()

    return render(request, 'results/scan_review.html', {
        'exam': exam, 'subject': subject, 'sheets': sheets, 'roster': roster,
        'graded_count_total': graded_count_total,
        'scheme': scheme,
    })


@require_POST
@teacher_or_academic_required
def scan_sheet_confirm(request, sheet_id):
    sheet = get_object_or_404(
        ScanSheet.objects.select_related('exam', 'subject'), pk=sheet_id,
    )
    exam, subject = sheet.exam, sheet.subject

    student_id = request.POST.get('student')
    if student_id:
        fs = FormStudent.objects.filter(pk=student_id).first()
        if fs:
            sheet.student = fs
    score_raw = request.POST.get('score', '').strip()
    if score_raw.isdigit():
        sheet.score = int(score_raw)
    if not sheet.total:
        sheet.total = len(_get_or_create_key(exam, subject).key) or None
    sheet.status = ScanSheet.Status.GRADED
    sheet.needs_review_reason = ''
    sheet.save()
    messages.success(request, 'Karatasi imethibitishwa.')
    return redirect('scan_review', exam_id=exam.pk, subject_id=subject.pk)


@require_POST
@teacher_or_academic_required
def scan_sheet_delete(request, sheet_id):
    sheet = get_object_or_404(ScanSheet, pk=sheet_id)
    exam_id, subject_id = sheet.exam_id, sheet.subject_id
    sheet.image.delete(save=False)
    sheet.delete()
    messages.success(request, 'Karatasi imefutwa.')
    return redirect('scan_review', exam_id=exam_id, subject_id=subject_id)


def scan_sheet_image(request, sheet_id):
    sheet = get_object_or_404(ScanSheet, pk=sheet_id)
    return FileResponse(sheet.image.open('rb'))


@teacher_or_academic_required
def scan_sheet_annotated(request, sheet_id):
    """Picha ya karatasi yenye alama nyekundu (✓/✗/○ + jumla)."""
    sheet = get_object_or_404(ScanSheet, pk=sheet_id)
    if not sheet.annotated_image:
        _annotate_sheet(sheet, _get_or_create_key(sheet.exam, sheet.subject).key)
        sheet.refresh_from_db()
    if sheet.annotated_image:
        return FileResponse(sheet.annotated_image.open('rb'))
    return FileResponse(sheet.image.open('rb'))


@teacher_or_academic_required
def scan_review_pdf(request, exam_id, subject_id):
    """PDF ya karatasi ZOTE zilizoalama nyekundu — mwalimu anachapisha
    au kutuma kwa wanafunzi/parents kama 'marked script'."""
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    exam = _get_exam_or_404(exam_id, request.user)
    subject = get_object_or_404(Subject, pk=subject_id)
    sheets = ScanSheet.objects.filter(
        exam=exam, subject=subject,
        status__in=[ScanSheet.Status.GRADED, ScanSheet.Status.IMPORTED],
        student__isnull=False,
    ).select_related('student').order_by('student__first_name', 'page_number')

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    count = 0
    for sheet in sheets:
        img_source = sheet.annotated_image or sheet.image
        if not img_source:
            continue
        try:
            with img_source.open('rb') as fh:
                img_data = fh.read()
        except Exception:
            continue
        # Header ndogo
        c.setFont('Helvetica-Bold', 9)
        c.drawString(15 * 28.35, height - 20, f'{sheet.student.full_name} — {subject.name} (uk. {sheet.page_number})')
        c.setFont('Helvetica', 8)
        c.drawRightString(width - 15 * 28.35, height - 20,
                          f'{sheet.score if sheet.score is not None else "—"}/{sheet.total or ""}')
        try:
            c.drawImage(ImageReader(io.BytesIO(img_data)),
                        15 * 28.35, 30, width - 30 * 28.35, height - 60,
                        preserveAspectRatio=True, anchor='c')
        except Exception:
            continue
        c.showPage()
        count += 1
    c.save()

    resp = HttpResponse(buf.getvalue(), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="marked_{exam.pk}_{subject.pk}.pdf"'
    return resp


# ---------------- Matokeo (tick kwa kila swali + score) ----------------

@teacher_or_academic_required
def scan_results(request, exam_id, subject_id):
    """Matokeo ya usahihishaji: kila mwanafunzi — ✓✗○ kwa kila swali + jumla."""
    exam = _get_exam_or_404(exam_id, request.user)
    subject = get_object_or_404(Subject, pk=subject_id)
    key = _get_or_create_key(exam, subject)
    results = _build_student_results(exam, subject, key.key)

    context = {
        'exam': exam, 'subject': subject,
        'results': results,
        'key_count': len(key.key),
        'has_key': bool(key.key),
        'scheme': MarkingScheme.objects.filter(exam=exam, subject=subject).first(),
    }
    return render(request, 'results/scan_results.html', context)


# ---------------- Import kwenye matokeo ----------------

@require_POST
@teacher_or_academic_required
def scan_import(request, exam_id, subject_id):
    exam = _get_exam_or_404(exam_id, request.user)
    subject = _get_subject_or_404(subject_id)

    sheets = ScanSheet.objects.filter(
        exam=exam, subject=subject,
        status=ScanSheet.Status.GRADED,
        student__isnull=False,
        score__isnull=False,
        total__gt=0,
    ).select_related('student')

    if not sheets:
        messages.warning(request, 'Hakuna karatasi zilizosahihishwa za kuingiza.')
        return redirect('scan_review', exam_id=exam.pk, subject_id=subject.pk)

    # Alama 0-100: score/total * 100
    results = []
    for sheet in sheets:
        student = _student_from_form_student(sheet.student)
        percent = max(0, min(100, round(sheet.score / sheet.total * 100)))
        results.append(ExamResult(
            exam=exam, student=student, subject=subject,
            score=percent, is_absent=False,
        ))

    ExamResult.objects.bulk_create(
        results,
        update_conflicts=True,
        unique_fields=['exam', 'student', 'subject'],
        update_fields=['score', 'is_absent'],
    )

    sheets.update(status=ScanSheet.Status.IMPORTED, imported_to_results=True)

    student_count = ExamResult.objects.filter(
        exam=exam, subject=subject,
    ).values('student').distinct().count()

    SubjectSubmission.objects.update_or_create(
        exam=exam, subject=subject,
        defaults={
            'status': SubjectSubmission.STATUS_SUBMITTED,
            'method': 'UPLOAD',
            'submitted_by': 'Sahishi Scan',
            'submitted_at': timezone.now(),
            'student_count': student_count,
        },
    )

    try:
        recompute_processed_results_for_exam(exam)
    except Exception:
        logger.exception('recompute_processed_results_for_exam imeshindikana exam=%s', exam.pk)

    messages.success(
        request,
        f'Matokeo ya wanafunzi {len(results)} yameingizwa kwenye mtihani.',
    )
    return redirect('exam_overview', exam_id=exam.pk)
