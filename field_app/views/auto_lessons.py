"""
MASOMO YA AUTOMATIC — views
===========================
Ukurasa wa "Masomo Yangu" (masomo yaliyozalishwa kiotomatiki kutoka scheme),
kuhariri (tarehe, attendance, maudhui), kupakua PDF/Word/zip, na
kuzalisha wiki zijazo kwa mikono.
"""
import json
import re
from datetime import timedelta
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from field_app.auto_lessons import (
    generate_lessons_for_student,
    monday_of,
    today_eat,
)

from ..models import LessonPlan, StudentTeacher
from .ai_utils import client, model_name

WEEK_DAY_NAMES = ['Jumatatu', 'Jumanne', 'Jumatano', 'Alhamisi', 'Ijumaa', 'Jumamosi', 'Jumapili']


def _get_student(request):
    try:
        return StudentTeacher.objects.get(user=request.user)
    except StudentTeacher.DoesNotExist:
        return None


def _own_lesson(request, lesson_id):
    student = _get_student(request)
    if not student:
        return None, None
    lesson = get_object_or_404(
        LessonPlan.objects.select_related('subject', 'scheme', 'school'),
        id=lesson_id, student=student,
    )
    return student, lesson


# ============================================================
# MASOMO YANGU — orodha ya masomo grouped kwa wiki
# ============================================================

@login_required
def my_lessons(request):
    student = _get_student(request)
    if not student:
        messages.error(request, 'Wasifu wa mwanafunzi haupatikani.')
        return redirect('dashboard')

    lessons = (LessonPlan.objects
               .filter(student=student)
               .select_related('subject', 'scheme')
               .order_by('date', 'period_index', 'id'))

    this_monday = monday_of(today_eat())
    next_monday = this_monday + timedelta(days=7)

    weeks = {}
    for lp in lessons:
        key = lp.week_start_date or monday_of(lp.date)
        weeks.setdefault(key, []).append(lp)

    week_cards = []
    for monday in sorted(weeks, reverse=True):
        items = weeks[monday]
        week_cards.append({
            'monday': monday,
            'label': f"Wiki ya {monday.strftime('%d %b %Y')}",
            'is_current': monday == this_monday,
            'is_past': monday < this_monday,
            'lessons': items,
        })

    upcoming = sum(
        1 for lp in lessons
        if (lp.week_start_date or monday_of(lp.date)) >= this_monday
    )
    needs_attention = [
        lp for lp in lessons
        if (lp.week_start_date or monday_of(lp.date)) >= this_monday
        and lp.date <= today_eat()
        and not lp.present_students
    ]

    ctx = {
        'week_cards': week_cards,
        'upcoming_count': upcoming,
        'needs_attention': needs_attention[:10],
        'needs_attention_count': len(needs_attention),
        'schemes_count': student.schemes.count(),
        'today': today_eat(),
    }
    return render(request, 'field_app/my_lessons.html', ctx)


@login_required
@require_POST
def ajax_generate_auto_lessons(request):
    """Kitufe cha 'Zalisha masomo ya wiki zijazo sasa' — kwa mwanafunzi huyu."""
    student = _get_student(request)
    if not student:
        return JsonResponse({'success': False, 'error': 'Wasifu wa mwanafunzi haupatikani.'}, status=404)
    try:
        summary = generate_lessons_for_student(student, weeks_ahead=2)
        return JsonResponse({
            'success': True,
            'created': summary['lessons_created'],
            'existing': summary['lessons_existing'],
            'message': (
                f"Masomo {summary['lessons_created']} mapya yamezalishwa"
                + (f" ({summary['lessons_existing']} yalikuwepo tayari)" if summary['lessons_existing'] else '')
                if summary['lessons_created'] or summary['lessons_existing']
                else 'Hakuna masomo mapya — hakikisha scheme yako ina tarehe ya kuanza na wiki za kufundisha bado zipo.'
            ),
        })
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f'Hitilafu: {exc}'}, status=500)


# ============================================================
# KUHARIRI SOMO
# ============================================================

def _clean_lines(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [ln.strip() for ln in str(value or '').split('\n') if ln.strip()]


def _int_or_none(value):
    try:
        return int(value) if str(value).strip() else None
    except (TypeError, ValueError):
        return None


@login_required
def lesson_edit(request, lesson_id):
    student, lesson = _own_lesson(request, lesson_id)
    if not lesson:
        messages.error(request, 'Somo halikupatikana au si lako.')
        return redirect('my_lessons')

    if request.method == 'POST':
        lesson.topic = request.POST.get('topic', lesson.topic)[:200]
        lesson.subtopic = (request.POST.get('subtopic') or '')[:200]
        try:
            lesson.date = request.POST.get('date') or lesson.date
        except Exception:
            pass
        try:
            lesson.duration = int(request.POST.get('duration') or lesson.duration)
        except (TypeError, ValueError):
            pass
        lesson.total_students = _int_or_none(request.POST.get('total_students'))
        lesson.present_students = _int_or_none(request.POST.get('present_students'))
        lesson.total_boys = _int_or_none(request.POST.get('total_boys'))
        lesson.total_girls = _int_or_none(request.POST.get('total_girls'))
        lesson.present_boys = _int_or_none(request.POST.get('present_boys'))
        lesson.present_girls = _int_or_none(request.POST.get('present_girls'))
        lesson.main_competence = request.POST.get('main_competence', '')
        lesson.specific_competence = request.POST.get('specific_competence', '')
        lesson.previous_knowledge = request.POST.get('previous_knowledge', '')
        lesson.learning_objectives = _clean_lines(request.POST.get('learning_objectives'))
        lesson.teaching_methods = _clean_lines(request.POST.get('teaching_methods'))
        lesson.teaching_resources = _clean_lines(request.POST.get('teaching_resources'))

        ld_raw = request.POST.get('lesson_development_json', '')
        try:
            ld = json.loads(ld_raw)
            if isinstance(ld, list):
                lesson.lesson_development = ld
        except (ValueError, TypeError):
            pass

        lesson.remarks = request.POST.get('remarks', '')
        lesson.status = 'edited'
        lesson.save()

        if request.POST.get('action') == 'save_download':
            return _lesson_pdf_response(lesson)
        messages.success(request, 'Somo limehifadhiwa.')
        return redirect('my_lessons')

    return render(request, 'field_app/lesson_edit.html', {'lesson': lesson})


@login_required
@require_POST
def lesson_delete(request, lesson_id):
    student, lesson = _own_lesson(request, lesson_id)
    if lesson:
        lesson.delete()
        messages.success(request, 'Somo limefutwa.')
    return redirect('my_lessons')


@login_required
@require_POST
def lesson_duplicate(request, lesson_id):
    """Nakala ya somo kwa siku nyingine — attendance/remarks zinaanza safi."""
    student, lesson = _own_lesson(request, lesson_id)
    if not lesson:
        messages.error(request, 'Somo halikupatikana.')
        return redirect('my_lessons')
    new = LessonPlan.objects.get(pk=lesson.pk)
    new.pk = None
    new.id = None
    new.auto_key = None
    new.scheme_week = lesson.scheme_week
    new.week_start_date = lesson.week_start_date
    new.period_index = None
    new.status = 'edited'
    new.source = 'manual'
    new.date = today_eat()
    new.total_students = None
    new.present_students = None
    new.total_boys = None
    new.total_girls = None
    new.present_boys = None
    new.present_girls = None
    new.remarks = ''
    new.save()
    messages.success(request, f'Nakala ya somo imeundwa — {new.date}. Hariri sasa.')
    return redirect('lesson_edit', lesson_id=new.id)


@login_required
def ajax_refine_lesson_ai(request, lesson_id):
    """AI iboreshe somo (inarudisha JSON — mwalimu anahifadhi mwenyewe)."""
    if client is None:
        return JsonResponse({'success': False,
                            'error': 'Huduma ya AI haitumiki. Ufunguo wa API haujawekwa.'}, status=503)
    student, lesson = _own_lesson(request, lesson_id)
    if not lesson:
        return JsonResponse({'success': False, 'error': 'Somo halikupatikana.'}, status=404)

    try:
        current = {
            'topic': lesson.topic,
            'subtopic': lesson.subtopic,
            'main_competence': lesson.main_competence,
            'specific_competence': lesson.specific_competence,
            'previous_knowledge': lesson.previous_knowledge,
            'learning_objectives': lesson.learning_objectives,
            'teaching_methods': lesson.teaching_methods,
            'teaching_resources': lesson.teaching_resources,
            'lesson_development': lesson.lesson_development,
        }
        scheme_row = {}
        if lesson.scheme and lesson.scheme.scheme_data:
            idx = (lesson.scheme_week or 1) - 1
            if 0 <= idx < len(lesson.scheme.scheme_data):
                scheme_row = lesson.scheme.scheme_data[idx]

        prompt = f"""You are an AI assistant for Tanzanian teachers. Improve this LESSON PLAN following the SEQUIP/TIE IDDR format (2023).
Keep the same language style as the input (Kiswahili content where present). Duration: {lesson.duration} minutes (I≈15%, D≈40%, D≈30%, R≈15%).

Scheme of work row for context:
{json.dumps(scheme_row, ensure_ascii=False, indent=1)}

Current lesson plan:
{json.dumps(current, ensure_ascii=False, indent=1)}

Return ONLY valid JSON with exactly these keys:
{{"topic": "...", "subtopic": "...", "main_competence": "...", "specific_competence": "...", "previous_knowledge": "...", "learning_objectives": ["..."], "teaching_methods": ["..."], "teaching_resources": ["..."], "lesson_development": [{{"time": "X min", "stage": "Introduction (I)", "methods": "...", "teacher_activities": "...", "student_activities": "...", "assessment_criteria": "..."}}], "remarks_hint": "short note on what you improved"}}
The lesson_development MUST have the 4 IDDR stages.
"""
        response = client.models.generate_content(model=model_name, contents=prompt)
        text = response.text
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text).strip()
        start, end = text.find('{'), text.rfind('}')
        if start == -1 or end <= start:
            raise ValueError('AI haikurudisha JSON')
        data = json.loads(text[start:end + 1])
        return JsonResponse({'success': True, 'data': data})
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f'Hitilafu ya AI: {str(exc)[:200]}'}, status=500)


# ============================================================
# EXPORT — PDF / WORD / ZIP kutoka DB
# ============================================================

def _lesson_pdf_bytes(lesson):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    NAVY = colors.HexColor('#0A2B5E')
    GOLD = colors.HexColor('#C8900A')
    LIGHT = colors.HexColor('#EEF1F6')
    STRIPE = colors.HexColor('#F4F7FF')
    BORDER = colors.HexColor('#9BAAC4')

    subject = lesson.subject.name if lesson.subject else ''
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    elements = []

    normal = ParagraphStyle('ALP_N', fontName='Helvetica', fontSize=9, leading=13,
                             wordWrap='LTR', spaceAfter=3)
    section_hdr = ParagraphStyle('ALP_H', fontName='Helvetica-Bold', fontSize=10,
                                  textColor=NAVY, spaceBefore=10, spaceAfter=4)
    cell_s = ParagraphStyle('ALP_C', fontName='Helvetica', fontSize=8, leading=11, wordWrap='LTR')
    hdr_s = ParagraphStyle('ALP_CH', fontName='Helvetica-Bold', fontSize=8, leading=11,
                            textColor=colors.white, wordWrap='LTR', alignment=1)
    label_s = ParagraphStyle('ALP_L', fontName='Helvetica-Bold', fontSize=8, leading=11,
                              textColor=NAVY)

    def P(txt, st=normal):
        return Paragraph(str(txt or ''), st)

    elements.append(Paragraph('LESSON PLAN',
        ParagraphStyle('ALP_T', fontName='Helvetica-Bold', fontSize=16, alignment=1,
                       textColor=NAVY, spaceAfter=2)))
    elements.append(Paragraph(
        f'{subject}  |  {lesson.class_name}  |  Term {lesson.term} {lesson.year}',
        ParagraphStyle('ALP_S', fontSize=9, alignment=1, textColor=colors.grey, spaceAfter=10)))

    meta_rows = [
        [P('Teacher', label_s), P(lesson.teacher_name), P('Subject', label_s), P(subject)],
        [P('Class', label_s), P(lesson.class_name),
         P('Term / Year', label_s), P(f'Term {lesson.term} {lesson.year}')],
        [P('Topic', label_s), P(lesson.topic), P('Subtopic', label_s), P(lesson.subtopic or '')],
        [P('Duration', label_s), P(f'{lesson.duration} minutes'),
         P('Date', label_s), P(str(lesson.date))],
        [P('Students', label_s),
         P(f'{lesson.total_students or "____"} total / {lesson.present_students or "____"} present'),
         P(''), P('')],
    ]
    meta_tbl = Table(meta_rows, colWidths=[72, 188, 72, 191])
    meta_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), LIGHT),
        ('BACKGROUND', (2, 0), (2, -1), LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, -1), (-1, -1), 1.2, GOLD),
    ]))
    elements.append(meta_tbl)
    elements.append(Spacer(1, 10))

    for label, key in [('Main Competence', lesson.main_competence),
                       ('Specific Competence', lesson.specific_competence),
                       ('Previous Knowledge', lesson.previous_knowledge)]:
        if key:
            elements.append(Paragraph(f'<b>{label}:</b>  {key}', normal))

    for label, items in [('Learning Objectives', lesson.learning_objectives),
                         ('Teaching Methods', lesson.teaching_methods),
                         ('Teaching Resources', lesson.teaching_resources)]:
        if items:
            elements.append(Paragraph(label, section_hdr))
            for item in items:
                elements.append(Paragraph(f'<bullet>•</bullet> {item}',
                    ParagraphStyle('ALP_B', fontName='Helvetica', fontSize=9,
                                   leading=13, leftIndent=14, wordWrap='LTR')))

    ld = lesson.lesson_development or []
    if ld:
        elements.append(Paragraph('Lesson Development (IDDR Model)', section_hdr))
        ld_headers = ['Time', 'Stage (IDDR)', 'Methods', 'Teacher Activities',
                      'Student Activities', 'Assessment Criteria']
        ld_data = [[Paragraph(h, hdr_s) for h in ld_headers]]
        for stage in ld:
            ld_data.append([
                Paragraph(str(stage.get('time', '') or ''), cell_s),
                Paragraph(str(stage.get('stage', stage.get('phase', '')) or ''), cell_s),
                Paragraph(str(stage.get('methods', '') or ''), cell_s),
                Paragraph(str(stage.get('teacher_activities', '') or ''), cell_s),
                Paragraph(str(stage.get('student_activities', '') or ''), cell_s),
                Paragraph(str(stage.get('assessment_criteria', '') or ''), cell_s),
            ])
        ld_tbl = Table(ld_data, colWidths=[38, 72, 72, 118, 118, 105], repeatRows=1)
        ld_ts = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('LINEBELOW', (0, 0), (-1, 0), 1.2, GOLD),
            ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(ld_data)):
            ld_ts.append(('BACKGROUND', (0, i), (-1, i),
                          STRIPE if i % 2 == 0 else colors.white))
        ld_tbl.setStyle(TableStyle(ld_ts))
        elements.append(ld_tbl)

    remarks = lesson.remarks
    if remarks:
        elements.append(Spacer(1, 8))
        elements.append(Paragraph('Remarks', section_hdr))
        if isinstance(remarks, dict):
            for label, key in [('1. Strength', 'strength'), ('2. Weakness', 'weakness'),
                               ('3. Way Forward', 'way_forward')]:
                val = remarks.get(key, '') or '...............................................'
                elements.append(Paragraph(f'<b>{label}:</b>  {val}', normal))
        else:
            elements.append(Paragraph(str(remarks), normal))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def _lesson_pdf_response(lesson):
    buffer = _lesson_pdf_bytes(lesson)
    safe = f'LessonPlan_{lesson.subject.name if lesson.subject else "Somo"}_{lesson.date}'.replace(' ', '_')
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{safe}.pdf"'
    return response


@login_required
def download_lesson_pdf_db(request, lesson_id):
    student, lesson = _own_lesson(request, lesson_id)
    if not lesson:
        return HttpResponse('Somo halikupatikana.', status=404)
    return _lesson_pdf_response(lesson)


@login_required
def download_lesson_word_db(request, lesson_id):
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    student, lesson = _own_lesson(request, lesson_id)
    if not lesson:
        return HttpResponse('Somo halikupatikana.', status=404)

    doc = Document()
    doc.add_heading('LESSON PLAN', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta_table = doc.add_table(rows=5, cols=4)
    meta_table.style = 'Table Grid'
    rows = meta_table.rows

    def _set(r, c, text, bold=False):
        cell = rows[r].cells[c]
        cell.text = str(text)
        if bold and cell.paragraphs[0].runs:
            cell.paragraphs[0].runs[0].bold = True

    subject = lesson.subject.name if lesson.subject else ''
    _set(0, 0, 'Teacher:', True); _set(0, 1, lesson.teacher_name)
    _set(0, 2, 'Subject:', True); _set(0, 3, subject)
    _set(1, 0, 'Class:', True); _set(1, 1, lesson.class_name)
    _set(1, 2, 'Term/Year:', True); _set(1, 3, f'Term {lesson.term} {lesson.year}')
    _set(2, 0, 'Topic:', True); _set(2, 1, lesson.topic)
    _set(2, 2, 'Subtopic:', True); _set(2, 3, lesson.subtopic or '')
    _set(3, 0, 'Duration:', True); _set(3, 1, f'{lesson.duration} min')
    _set(3, 2, 'Date:', True); _set(3, 3, str(lesson.date))
    _set(4, 0, 'Students:', True)
    _set(4, 1, f'{lesson.total_students or "____"} / {lesson.present_students or "____"}')

    doc.add_paragraph()
    for label, val in [('Main Competence', lesson.main_competence),
                       ('Specific Competence', lesson.specific_competence),
                       ('Previous Knowledge', lesson.previous_knowledge)]:
        if val:
            p = doc.add_paragraph()
            p.add_run(f'{label}: ').bold = True
            p.add_run(str(val))

    for label, items in [('Learning Objectives', lesson.learning_objectives),
                         ('Teaching Methods', lesson.teaching_methods),
                         ('Teaching Resources', lesson.teaching_resources)]:
        if items:
            doc.add_heading(label, level=2)
            for item in items:
                doc.add_paragraph(str(item), style='List Bullet')

    ld = lesson.lesson_development or []
    if ld:
        doc.add_heading('Lesson Development (IDDR Model)', level=2)
        ld_table = doc.add_table(rows=1, cols=6)
        ld_table.style = 'Table Grid'
        hdr = ld_table.rows[0].cells
        for i, h in enumerate(['Time', 'Stage (IDDR)', 'Methods', 'Teacher Activities',
                               'Student Activities', 'Assessment Criteria']):
            hdr[i].text = h
            if hdr[i].paragraphs[0].runs:
                hdr[i].paragraphs[0].runs[0].bold = True
        for stage in ld:
            row = ld_table.add_row().cells
            row[0].text = str(stage.get('time', ''))
            row[1].text = str(stage.get('stage', stage.get('phase', '')) or '')
            row[2].text = str(stage.get('methods', ''))
            row[3].text = str(stage.get('teacher_activities', ''))
            row[4].text = str(stage.get('student_activities', ''))
            row[5].text = str(stage.get('assessment_criteria', ''))

    if lesson.remarks:
        doc.add_heading('Remarks', level=2)
        doc.add_paragraph(str(lesson.remarks))

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    safe = f'LessonPlan_{subject}_{lesson.date}'.replace(' ', '_')
    response = HttpResponse(
        buffer,
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{safe}.docx"'
    return response


@login_required
def download_lessons_zip(request):
    """ZIP ya PDF za wiki hii + ijayo (au zote zijazo)."""
    import zipfile

    student = _get_student(request)
    if not student:
        return HttpResponse('Wasifu haupatikani.', status=404)

    this_monday = monday_of(today_eat())
    scope = request.GET.get('scope', 'upcoming')
    lessons = (LessonPlan.objects
               .filter(student=student)
               .select_related('subject')
               .order_by('date', 'period_index'))
    if scope == 'upcoming':
        lessons = [lp for lp in lessons
                   if (lp.week_start_date or monday_of(lp.date)) >= this_monday]
    else:
        lessons = list(lessons)

    if not lessons:
        return HttpResponse('Hakuna masomo ya kupakua. Zalisha kwanza.', status=404)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for lp in lessons:
            subject = lp.subject.name if lp.subject else 'Somo'
            fname = f'{lp.date}_{subject}_{lp.class_name}'.replace(' ', '_').replace('/', '-')
            pdf = _lesson_pdf_bytes(lp).getvalue()
            zf.writestr(f'{fname}.pdf', pdf)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="Masomo_{scope}_{today_eat()}.zip"'
    return response
