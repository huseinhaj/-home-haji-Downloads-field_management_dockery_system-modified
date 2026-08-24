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
import logging
import uuid

from celery.result import AsyncResult
from django.contrib import messages
from django.core.files.storage import default_storage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Exam, ExamResult, FormStudent, Student, StoredRoster, Subject, SubjectSubmission
from .permissions import teacher_or_academic_required
from .services.upload_processing_service import recompute_processed_results_for_exam
from .tasks import process_scoresheet_photo_task
from .utils import get_grade_for_form, group_exams_by_type

logger = logging.getLogger(__name__)


def _student_from_form_student(fs):
    """Bridge a FormStudent row (the Academic Officer's official class
    list) to the Student model that ExamResult/marks-entry actually key
    off. Mirrors the exact (first_name, last_name) dedup that the
    file-upload roster path already uses (see _save_student in views.py)
    so a name the Academic uploaded and a name a teacher separately
    uploaded earlier converge on the same Student row instead of
    creating two.
    """
    student, _ = Student.objects.get_or_create(
        first_name=fs.first_name,
        last_name=fs.last_name or 'Unknown',
        defaults={'middle_name': fs.middle_name, 'gender': fs.gender},
    )
    if fs.middle_name and not student.middle_name:
        student.middle_name = fs.middle_name
        student.save(update_fields=['middle_name'])
    return student


def _resolve_class_roster(teacher, exam, subject, existing_marks):
    """Load students for this exam+subject, in priority order:
      1. This teacher's own uploaded/edited roster for this exact
         exam+subject (StoredRoster) — an explicit choice always wins.
      2. The Academic Officer's class list for this exam's form
         (FormStudent) — auto-populated, no upload needed, so a teacher
         can go straight to entering marks the moment the academic has
         uploaded the class.
      3. Whichever students already have results for this exam (legacy
         fallback for older exams).
    Shared by the Marks Entry page itself and the "download names as a
    blank scoresheet" PDF — both need the exact same roster."""
    stored = StoredRoster.objects.filter(
        teacher=teacher, exam=exam, subject=subject
    ).first()
    if stored and stored.students:
        return [
            {
                'id': s['id'],
                'name': s['name'],
                'score': existing_marks.get(s['id']),
            }
            for s in stored.students
        ]

    # Insertion order (id), not alphabetical — matches the order the
    # Academic uploaded the roster in.
    form_students = FormStudent.objects.filter(
        school=exam.school, form=exam.form
    ).order_by('id') if exam.school else FormStudent.objects.none()
    if form_students.exists():
        class_students = []
        for fs in form_students:
            student = _student_from_form_student(fs)
            class_students.append({
                'id': student.id,
                'name': ' '.join(p for p in [student.first_name, student.middle_name or '', student.last_name] if p),
                'score': existing_marks.get(student.id),
            })
        return class_students

    # Wanafunzi wote waliosajiliwa kwenye mtihani huu
    return [
        {
            'id': s.id,
            'name': ' '.join(p for p in [s.first_name, s.middle_name or '', s.last_name] if p),
            'score': existing_marks.get(s.id),
        }
        for s in Student.objects.filter(examresult__exam=exam)
        .distinct()
        .order_by('first_name', 'last_name')
    ]


def _parse_payload(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return {}
    return request.POST.dict()


@teacher_or_academic_required
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

    # Mitihani ya shule ya mwalimu. Kama mwalimu hana shule iliyowekwa
    # au shule yake haina mitihani bado, onyesha mitihani yote
    # (fallback) ili dropdown isiwe tupu.
    school_exams = Exam.objects.filter(school=teacher.school).order_by('-year', 'name')
    if teacher.school and school_exams.exists():
        exams = school_exams
    else:
        exams = Exam.objects.order_by('-year', 'name')
    # Dropdown inapangwa kwa aina ya mtihani: Terminal → Midterm → Test →
    # Quiz → Annual → Mock → Monthly → Other (si alphabetical).
    exam_groups = group_exams_by_type(exams, dict(Exam.EXAM_TYPE_CHOICES))
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
        # Inalingana na fallback ya dropdown: shule ikiwa na mitihani tumia yake,
        # vinginevyo mwalimu anaweza kuchagua mtihani wowote alioona kwenye orodha.
        if teacher.school and school_exams.exists():
            exam = Exam.objects.filter(id=exam_id, school=teacher.school).first()
        else:
            exam = Exam.objects.filter(id=exam_id).first()
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
                class_students = _resolve_class_roster(teacher, exam, subject, existing_marks)

    # Wastani na kiwango cha kufaulu kwa ukaguzi
    avg_score = None
    pass_rate = None
    if review_rows:
        scores = [r['score'] for r in review_rows]
        avg_score = round(sum(scores) / len(scores), 1)
        pass_rate = round(sum(1 for s in scores if get_grade_for_form(s, exam.form) != 'F') / len(scores) * 100)

    return render(request, 'results/marks_entry.html', {
        'exam_groups': exam_groups,
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


def _teacher_exam(teacher, exam_id):
    """Inalingana na dropdown ya marks entry: shule ikiwa na mitihani tumia yake,
    vinginevyo mwalimu anaweza kufanya kazi na mtihani wowote alioona kwenye orodha."""
    school_exams = Exam.objects.filter(school=teacher.school)
    if teacher.school and school_exams.exists():
        return Exam.objects.filter(id=exam_id, school=teacher.school).first()
    return Exam.objects.filter(id=exam_id).first()


@teacher_or_academic_required
@require_POST
def marks_entry_save(request):
    """Save (or update) all scores for an exam+subject. Does NOT submit yet."""
    payload = _parse_payload(request)
    teacher = request.user
    exam = _teacher_exam(teacher, payload.get('exam_id'))
    if exam is None:
        return JsonResponse({'error': 'Mtihani haupatikani.'}, status=404)
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


@teacher_or_academic_required
@require_POST
def marks_entry_submit(request):
    """Final submit — marks SubjectSubmission as SUBMITTED so the academic
    officer sees it (same logic as the old file-upload/speech flows).

    Ikiwa submission ilikuwa RETURNED na mtaaluma, submission ya zamani
    inatolewa kabisa na mpya inaingia na revision_number +1.
    """
    payload = _parse_payload(request)
    teacher = request.user
    exam = _teacher_exam(teacher, payload.get('exam_id'))
    if exam is None:
        return JsonResponse({'error': 'Mtihani haupatikani.'}, status=404)
    subject = get_object_or_404(Subject, id=payload.get('subject_id'))
    if not teacher.subjects.filter(pk=subject.pk).exists():
        return JsonResponse({'error': 'Hujapangiwa somo hili.'}, status=403)

    has_results = ExamResult.objects.filter(exam=exam, subject=subject).exists()
    if not has_results:
        return JsonResponse({'error': 'Hakuna alama zilizohifadhiwa. Jaza alama kwanza.'}, status=400)

    student_count = ExamResult.objects.filter(exam=exam, subject=subject).count()

    # ── Check if existing submission was RETURNED — if so, delete old + create new revision ──
    existing = SubjectSubmission.objects.filter(exam=exam, subject=subject).first()
    new_revision = 1
    if existing and existing.status == SubjectSubmission.STATUS_RETURNED:
        new_revision = existing.revision_number + 1
        existing.delete()

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
            'revision_number': new_revision,
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
        'revision': new_revision,
    })


@teacher_or_academic_required
@require_POST
def scoresheet_photo_extract(request):
    """Mwalimu anapakia picha AU PDF iliyochanganuliwa (scanned) ya
    scoresheet aliyoijaza kwa mkono. Usomaji wa AI (unaoweza kuchukua hadi
    dakika kadhaa kwa hati za kurasa nyingi) unafanyika nyuma-nyuma
    (Celery) badala ya ndani ya request hii — hii inarudisha task_id tu;
    frontend inauliza scoresheet_extract_status mpaka ikamilike. Haihifadhi
    alama chochote — mwalimu bado anabonyeza 'Hifadhi & Kagua'
    (marks_entry_save) kama kawaida."""
    teacher = request.user
    exam = _teacher_exam(teacher, request.POST.get('exam_id'))
    if exam is None:
        return JsonResponse({'error': 'Mtihani haupatikani.'}, status=404)
    subject = get_object_or_404(Subject, id=request.POST.get('subject_id'))
    if not teacher.subjects.filter(pk=subject.pk).exists():
        return JsonResponse({'error': 'Hujapangiwa somo hili.'}, status=403)

    document = request.FILES.get('photo')
    if not document:
        return JsonResponse({'error': 'Hakuna faili iliyotumwa.'}, status=400)

    try:
        roster = json.loads(request.POST.get('roster') or '[]')
    except json.JSONDecodeError:
        roster = []
    roster_ids = [r.get('id') for r in roster if isinstance(r, dict) and r.get('id')]

    storage_path = default_storage.save(
        f"scoresheet_tmp/{uuid.uuid4().hex}_{document.name}", document,
    )
    # Explicit queue='default': the deployed worker only consumes
    # --queues=default,emails (see Procfile/docker-compose.yml), not
    # Celery's own built-in default queue name ("celery"), which is where
    # a plain .delay() would land since this project sets no
    # CELERY_TASK_DEFAULT_QUEUE/CELERY_TASK_ROUTES. Without this the task
    # would sit in the broker forever and never run.
    task = process_scoresheet_photo_task.apply_async(
        args=[storage_path, roster_ids], queue='default',
    )
    return JsonResponse({'task_id': task.id}, status=202)


@teacher_or_academic_required
@require_GET
def scoresheet_extract_status(request, task_id):
    """Polled by the frontend every couple seconds after
    scoresheet_photo_extract kicks off the Celery task."""
    result = AsyncResult(task_id)

    if not result.ready():
        return JsonResponse({'status': 'processing'})

    if result.failed():
        logger.error("scoresheet_extract_status: task %s failed: %s", task_id, result.result)
        return JsonResponse({'error': 'Kuna hitilafu wakati wa kusoma picha. Jaribu tena.'}, status=500)

    payload = result.result or {}
    if payload.get('error'):
        return JsonResponse({'error': payload['error']}, status=400)

    return JsonResponse({'status': 'done', 'matched': payload.get('matched', []), 'unmatched': payload.get('unmatched', [])})


@teacher_or_academic_required
@require_GET
def download_scoresheet_names_pdf(request):
    """PDF ya majina yaliyokwisha-sajiliwa (na Mtaaluma/StoredRoster) kwa
    mtihani+somo fulani, yenye safu tupu ya 'Alama' — mwalimu anaipakua,
    anaichapisha, anajaza alama kwa mkono, kisha anapiga picha/scan na
    kuipakia kupitia 'Pakia Picha/PDF ya Scoresheet'. Hii inafunga mzunguko:
    Mtaaluma anasajili wanafunzi -> Mwalimu anapakua majina -> anajaza kwa
    mkono -> anapakia tena kama picha/PDF."""
    teacher = request.user
    exam = _teacher_exam(teacher, request.GET.get('exam_id') or request.GET.get('exam'))
    if exam is None:
        return HttpResponse('Mtihani haupatikani.', status=404)
    subject = get_object_or_404(Subject, id=request.GET.get('subject_id') or request.GET.get('subject'))
    if not teacher.subjects.filter(pk=subject.pk).exists():
        return HttpResponse('Hujapangiwa somo hili.', status=403)

    roster = _resolve_class_roster(teacher, exam, subject, existing_marks={})

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    import io

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm,
                             leftMargin=2 * cm, rightMargin=2 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('T', parent=styles['Title'], fontSize=15, spaceAfter=6,
                                  textColor=colors.HexColor('#1F7A3D'))
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=10, spaceAfter=4,
                                textColor=colors.HexColor('#333333'))
    hint_style = ParagraphStyle('Hint', parent=styles['Normal'], fontSize=9, spaceAfter=4,
                                 textColor=colors.HexColor('#555555'))

    GREEN = colors.HexColor('#1F7A3D')
    GREY = colors.HexColor('#F2F4F7')

    elements = []
    elements.append(Paragraph('SCORESHEET', title_style))
    label = f"{exam.name} — {subject.name} — Form {exam.form}"
    if exam.stream:
        label += f" {exam.stream}"
    label += f" ({exam.year})"
    elements.append(Paragraph(label, sub_style))
    elements.append(Paragraph(f"Mwalimu / Teacher: {teacher.full_name or teacher.email}", sub_style))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(
        '💡 Jaza alama kwa mkono kwenye safu ya "Alama", kisha piga picha au scan '
        'ukurasa huu, na uupakie kwenye "Pakia Picha/PDF ya Scoresheet" kwenye ukurasa wa Marks Entry.',
        hint_style,
    ))
    elements.append(Spacer(1, 6 * mm))

    hdr = ['Na.', 'Jina la Mwanafunzi', 'Alama']
    rows = [hdr]
    if roster:
        for i, s in enumerate(roster, 1):
            rows.append([str(i), s['name'], ''])
    else:
        rows.append(['', 'Hakuna wanafunzi waliosajiliwa bado.', ''])

    t = Table(rows, colWidths=[1.5 * cm, 11 * cm, 3 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), GREEN),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (-1, 1), (-1, -1), 'CENTER'),
        *[('BACKGROUND', (0, i), (-1, i), GREY) for i in range(2, len(rows), 2)],
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('BOX', (0, 0), (-1, -1), 1.2, GREEN),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph('Sahihi ya Mwalimu: ______________________', sub_style))

    doc.build(elements)
    response = HttpResponse(buf.getvalue(), content_type='application/pdf')
    safe_subject = subject.name.replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename="Scoresheet_{safe_subject}_{exam.id}.pdf"'
    return response
