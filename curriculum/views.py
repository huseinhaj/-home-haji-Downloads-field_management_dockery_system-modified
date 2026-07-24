"""
Curriculum app views — standalone Scheme of Work, Lesson Plan & Logbook.
Uses models from field_app but provides its own views, templates, and URLs.
"""
import json
import re
import threading
from io import BytesIO
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable

from .ai_utils import client, model_name
from .forms import SchemeOfWorkForm, LogbookForm

from field_app.models import (
    StudentTeacher, Subject, SchemeOfWork, LessonPlan,
    LogbookEntry, EducationLevel, ClassLevel, School,
    SchoolSubjectCapacity, StudentApplication, SchoolAssessment,
    AcademicYear, Textbook, BoardMember, BoardComment,
)
from field_app.views.utils import (
    _cached_active_year, _cached_subjects, _cached_today_logbook,
    _invalidate_today_logbook, get_or_create_student_profile,
    get_current_academic_year, invalidate_student_cache,
)


# =============================================================================
# LANDING PAGE (public, School Results login style)
# =============================================================================

def landing(request):
    """Public landing page — looks like School Results login interface.
    Centered card with TZ emblem, portal intro, and links to tools."""
    return render(request, 'curriculum/landing.html', {
        'is_public': not request.user.is_authenticated,
    })


# =============================================================================
# DASHBOARD (login required)
# =============================================================================

@login_required
def dashboard(request):
    """Standalone curriculum dashboard — overview of schemes, lesson plans & logbooks."""
    try:
        student = StudentTeacher.objects.select_related('selected_school').get(user=request.user)
    except StudentTeacher.DoesNotExist:
        messages.error(request, "Tafadhali jaza wasifu wako kwanza.")
        return redirect(reverse('curriculum:dashboard'))

    school = student.selected_school
    today = timezone.now().date()

    # Stats
    schemes_count = SchemeOfWork.objects.filter(student=student).count()
    lesson_plans_count = LessonPlan.objects.filter(student=student).count()
    logbook_today = LogbookEntry.objects.filter(student=student, date=today).first()
    logbook_count = LogbookEntry.objects.filter(student=student).count()
    this_month_logbooks = LogbookEntry.objects.filter(
        student=student, date__year=today.year, date__month=today.month
    ).count()

    # Recent items
    recent_schemes = SchemeOfWork.objects.filter(student=student).select_related('subject').order_by('-updated_at')[:3]
    recent_lessons = LessonPlan.objects.filter(student=student).select_related('subject').order_by('-created_at')[:3]
    recent_logbooks = LogbookEntry.objects.filter(student=student).select_related('subject_taught').order_by('-date')[:5]

    return render(request, 'curriculum/dashboard.html', {
        'student': student,
        'school': school,
        'schemes_count': schemes_count,
        'lesson_plans_count': lesson_plans_count,
        'logbook_today': logbook_today,
        'logbook_count': logbook_count,
        'this_month_logbooks': this_month_logbooks,
        'recent_schemes': recent_schemes,
        'recent_lessons': recent_lessons,
        'recent_logbooks': recent_logbooks,
        'today': today,
    })


# =============================================================================
# SCHEME OF WORK
# =============================================================================

def generate_scheme_view(request):
    """Display scheme of work generator form — public access."""
    form = SchemeOfWorkForm()
    education_levels = EducationLevel.objects.all().order_by('order')

    import json as _json
    classes_by_level = {}
    for cl in ClassLevel.objects.select_related('education_level').order_by('education_level', 'order'):
        classes_by_level.setdefault(cl.education_level_id, []).append({'id': cl.id, 'name': cl.name})

    primary_ids = list(
        EducationLevel.objects.filter(name__icontains='primary').values_list('id', flat=True)
    )
    subjects_by_level = {
        lvl.id: list(
            Subject.objects.filter(level='primary' if lvl.id in primary_ids else 'secondary')
            .order_by('name').values('id', 'name')
        )
        for lvl in education_levels
    }

    student = None
    school = None
    if request.user.is_authenticated:
        try:
            student = StudentTeacher.objects.select_related('selected_school').get(user=request.user)
            school = student.selected_school
            if not school:
                app = StudentApplication.objects.filter(
                    student=student, status='approved'
                ).select_related('school').first()
                if app:
                    school = app.school
        except StudentTeacher.DoesNotExist:
            pass

    return render(request, 'curriculum/generate_scheme.html', {
        'form': form,
        'education_levels': education_levels,
        'classes_by_level_json': _json.dumps(classes_by_level),
        'subjects_by_level_json': _json.dumps(subjects_by_level),
        'student': student,
        'school': school,
        'is_public': not request.user.is_authenticated,
    })


def ajax_generate_scheme(request):
    """AI generates a Scheme of Work."""
    if client is None:
        return JsonResponse({
            'success': False,
            'error': 'Huduma ya AI haitumiki. Ufunguo wa API (GROQ_API_KEY) haujawekwa. Wasiliana na msimamizi.'
        }, status=503)

    if request.method != 'POST':
        return JsonResponse({'success': False}, status=400)

    try:
        data = json.loads(request.body)

        education_level = data.get('education_level')
        class_name = data.get('class_name')
        subject = data.get('subject')
        term = data.get('term')
        year = data.get('year')
        syllabus = data.get('syllabus', 'New Syllabus')
        total_weeks = data.get('total_weeks', 12)
        periods_per_week = data.get('periods_per_week', 8)
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        teacher_name = data.get('teacher_name')
        school_name = data.get('school_name')
        reference_source = data.get('reference_source', '')
        breaks = data.get('breaks', [])

        breaks_text = ""
        if breaks:
            breaks_text = "\nBreaks (holidays/exams) to respect:\n"
            for b in breaks:
                breaks_text += f"- {b.get('name', 'Break')}: {b.get('start', '')} to {b.get('end', '')}\n"

        prompt = f"""
You are an AI assistant for Tanzanian teachers. Generate a complete Scheme of Work following EXACTLY the SEQUIP/TIE Tanzania revised format (2023).

Input details:
- Education Level: {education_level}
- Class/Form: {class_name}
- Subject: {subject}
- Term: {term} {year}
- Syllabus: {syllabus}
- Total Weeks: {total_weeks} weeks
- Periods per Week: {periods_per_week}
- Start Date: {start_date}
- End Date: {end_date}
- Teacher: {teacher_name}
- School: {school_name}
- Reference Source: {reference_source}
{breaks_text}
The output MUST be a JSON list of objects. Each object must have exactly these 12 keys:
"Main Competence", "Specific Competences", "Main Learning Activities", "Specific Learning Activities", "Month", "Week", "Number of Periods", "Teaching and Learning Methods", "Teaching and Learning Resources", "Assessment Tools", "References", "Remarks"

Requirements:
1. Distribute content across {total_weeks} weeks, respecting any breaks.
2. For each week, assign appropriate Month (e.g., MAY, JUNE, JULY, AUGUST, SEPTEMBER, OCTOBER).
3. "Week" column should be like "1st", "2nd", "3rd", etc.
4. "Number of Periods" should be {periods_per_week} for normal weeks.
5. "Specific Learning Activities" deconstruct Main Learning Activity into smaller measurable steps.
6. "References" must follow APA style version 7.
7. "Teaching and Learning Methods" should include CBC-aligned methods.
8. Return ONLY valid JSON, no extra text.
"""

        response = client.models.generate_content(model=model_name, contents=prompt)
        response_text = response.text

        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        json_data = json_match.group() if json_match else response_text

        try:
            scheme_data = json.loads(json_data)
        except Exception:
            scheme_data = []

        saved_id = None
        if request.user.is_authenticated:
            try:
                student = StudentTeacher.objects.get(user=request.user)
                school = student.selected_school
                if school and scheme_data:
                    level_map = {
                        'primary school': 'primary',
                        'ordinary level': 'ordinary',
                        'advanced level': 'advanced',
                    }
                    edu_level = level_map.get(education_level.lower(), 'ordinary')
                    subj_obj = Subject.objects.filter(name__iexact=subject).first()
                    if subj_obj:
                        start_dt = None
                        end_dt = None
                        if start_date:
                            try:
                                from datetime import date as _dt
                                start_dt = _dt.fromisoformat(start_date)
                            except Exception:
                                pass
                        if end_date:
                            try:
                                from datetime import date as _dt
                                end_dt = _dt.fromisoformat(end_date)
                            except Exception:
                                pass
                        scheme_obj, _ = SchemeOfWork.objects.update_or_create(
                            student=student,
                            subject=subj_obj,
                            term=term,
                            year=int(year),
                            defaults={
                                'school': school,
                                'education_level': edu_level,
                                'class_name': class_name,
                                'syllabus': syllabus,
                                'total_weeks': int(total_weeks),
                                'periods_per_week': int(periods_per_week),
                                'start_date': start_dt,
                                'end_date': end_dt,
                                'teacher_name': teacher_name,
                                'reference_source': reference_source,
                                'breaks': breaks,
                                'scheme_data': scheme_data,
                                'generated_by_ai': True,
                            }
                        )
                        saved_id = scheme_obj.id
            except Exception as save_err:
                print(f"[Curriculum] Scheme save error (non-fatal): {save_err}")

        return JsonResponse({'success': True, 'data': scheme_data, 'saved_id': saved_id})

    except Exception as e:
        import traceback
        traceback.print_exc()
        raw = str(e)
        if 'PERMISSION_DENIED' in raw or 'suspended' in raw.lower() or '403' in raw:
            msg = "Huduma ya AI imesimamishwa. Wasiliana na msimamizi."
        elif 'quota' in raw.lower() or '429' in raw or 'rate' in raw.lower():
            msg = f"Kikomo cha matumizi: {raw[:200]}"
        elif 'API_KEY' in raw or 'api_key' in raw.lower():
            msg = "Ufunguo wa API ya AI haujawekwa. Wasiliana na msimamizi."
        else:
            msg = f"Hitilafu: {raw[:200]}"
        return JsonResponse({'success': False, 'error': msg}, status=500)


def download_scheme_pdf(request):
    """Generate PDF ya Scheme of Work."""
    if request.method != 'POST':
        return HttpResponse("Invalid request", status=400)

    data = json.loads(request.body)
    scheme_data = data.get('scheme_data') or []
    subject = data.get('subject', '')
    class_name = data.get('class_name', '')
    term = data.get('term', '')
    year = data.get('year', '')
    syllabus = data.get('syllabus', '')
    teacher_name = data.get('teacher_name', '')
    school_name = data.get('school_name', '')
    total_weeks = data.get('total_weeks', '')

    NAVY = colors.HexColor('#0A2B5E')
    GOLD = colors.HexColor('#C8900A')
    STRIPE = colors.HexColor('#EBF0FB')
    BORDER = colors.HexColor('#9BAAC4')

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=18, leftMargin=18, topMargin=22, bottomMargin=22)
    elements = []

    cell_style = ParagraphStyle('SchCell', fontName='Helvetica', fontSize=7,
                                leading=10, wordWrap='LTR')
    hdr_style = ParagraphStyle('SchHdr', fontName='Helvetica-Bold', fontSize=7,
                               leading=10, textColor=colors.white, wordWrap='LTR', alignment=1)

    elements.append(Paragraph("SCHEME OF WORK",
        ParagraphStyle('ST', fontName='Helvetica-Bold', fontSize=14, alignment=1,
                       textColor=NAVY, spaceAfter=3)))
    elements.append(Paragraph(
        f"{subject}  |  {class_name}  |  Term {term} {year}  |  {syllabus}",
        ParagraphStyle('SS', fontSize=9, alignment=1, spaceAfter=2)))
    elements.append(Paragraph(
        f"Teacher: {teacher_name}    |    School: {school_name}    |    Total Weeks: {total_weeks}",
        ParagraphStyle('SI', fontSize=8, alignment=1, textColor=colors.grey, spaceAfter=10)))

    if scheme_data:
        headers = list(scheme_data[0].keys())
        WIDTH_MAP = {
            'Main Competence': 72, 'Specific Competences': 72,
            'Main Learning Activities': 68, 'Specific Learning Activities': 76,
            'Month': 38, 'Week': 34, 'Number of Periods': 32,
            'Teaching and Learning Methods': 64,
            'Teaching and Learning Resources': 64,
            'Assessment Tools': 54, 'References': 64, 'Remarks': 68,
        }
        TOTAL = 806
        col_widths = []
        for h in headers:
            w = WIDTH_MAP.get(h)
            if w is None:
                for k, v in WIDTH_MAP.items():
                    if k.lower() in h.lower() or h.lower() in k.lower():
                        w = v
                        break
            col_widths.append(w if w else TOTAL // len(headers))
        scale = TOTAL / sum(col_widths)
        col_widths = [w * scale for w in col_widths]

        table_data = [[Paragraph(h, hdr_style) for h in headers]]
        for row in scheme_data:
            table_data.append([Paragraph(str(row.get(h, '') or ''), cell_style) for h in headers])

        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        ts = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.35, BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, 0), 1.2, GOLD),
        ]
        for i in range(1, len(table_data)):
            bg = STRIPE if i % 2 == 0 else colors.white
            ts.append(('BACKGROUND', (0, i), (-1, i), bg))
        tbl.setStyle(TableStyle(ts))
        elements.append(tbl)

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Scheme_of_Work_{subject}_{class_name}.pdf"'
    return response


def download_scheme_word(request):
    """Export Scheme of Work as Word (.docx)."""
    if request.method != 'POST':
        return HttpResponse("Invalid request", status=400)

    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    data = json.loads(request.body)
    scheme_data = data.get('scheme_data', [])
    subject = data.get('subject', '')
    class_name = data.get('class_name', '')
    term = data.get('term', '')
    year = data.get('year', '')
    teacher_name = data.get('teacher_name', '')
    school_name = data.get('school_name', '')

    doc = Document()
    doc.core_properties.title = f"Scheme of Work — {subject}"

    title = doc.add_heading(f"{subject} — {class_name} — Term {term} {year}", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    info = doc.add_paragraph(f"Teacher: {teacher_name}    School: {school_name}")
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()

    if scheme_data:
        headers = list(scheme_data[0].keys())
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = 'Table Grid'

        WIDTH_CM = {
            'Main Competence': 2.6, 'Specific Competences': 2.6,
            'Main Learning Activities': 2.4, 'Specific Learning Activities': 2.8,
            'Month': 1.3, 'Week': 1.2, 'Number of Periods': 1.1,
            'Teaching and Learning Methods': 2.2,
            'Teaching and Learning Resources': 2.2,
            'Assessment Tools': 1.9, 'References': 2.2, 'Remarks': 2.5,
        }
        TOTAL_CM = 24.0
        col_cms = []
        for h in headers:
            w = WIDTH_CM.get(h)
            if w is None:
                for k, v in WIDTH_CM.items():
                    if k.lower() in h.lower() or h.lower() in k.lower():
                        w = v
                        break
            col_cms.append(w if w else TOTAL_CM / len(headers))
        scale_cm = TOTAL_CM / sum(col_cms)
        col_cms = [w * scale_cm for w in col_cms]

        section = doc.sections[0]
        section.page_width = Cm(29.7)
        section.page_height = Cm(21.0)
        section.left_margin = section.right_margin = Cm(1.2)
        section.top_margin = section.bottom_margin = Cm(1.2)

        hdr_cells = table.rows[0].cells
        for i, h in enumerate(headers):
            hdr_cells[i].text = h
            hdr_cells[i].width = Cm(col_cms[i])
            p = hdr_cells[i].paragraphs[0]
            if p.runs:
                p.runs[0].bold = True
                p.runs[0].font.size = Pt(8)
                p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            tc = hdr_cells[i]._tc
            tcPr = tc.get_or_add_tcPr()
            shd = OxmlElement('w:shd')
            shd.set(qn('w:val'), 'clear')
            shd.set(qn('w:color'), 'auto')
            shd.set(qn('w:fill'), '0A2B5E')
            tcPr.append(shd)

        for ri, row in enumerate(scheme_data):
            row_cells = table.add_row().cells
            fill_hex = 'EBF0FB' if ri % 2 == 0 else 'FFFFFF'
            for i, h in enumerate(headers):
                row_cells[i].width = Cm(col_cms[i])
                row_cells[i].text = str(row.get(h, '') or '')
                p = row_cells[i].paragraphs[0]
                if p.runs:
                    p.runs[0].font.size = Pt(8)
                tc = row_cells[i]._tc
                tcPr = tc.get_or_add_tcPr()
                shd = OxmlElement('w:shd')
                shd.set(qn('w:val'), 'clear')
                shd.set(qn('w:color'), 'auto')
                shd.set(qn('w:fill'), fill_hex)
                tcPr.append(shd)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    safe_name = f"Scheme_{subject}_{class_name}".replace(' ', '_')
    response = HttpResponse(buffer, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{safe_name}.docx"'
    return response


@login_required
def ajax_load_saved_scheme(request):
    """Load most recent saved SchemeOfWork from DB."""
    try:
        student = StudentTeacher.objects.get(user=request.user)
        scheme = (SchemeOfWork.objects
                  .filter(student=student)
                  .select_related('subject')
                  .order_by('-updated_at')
                  .first())
        if not scheme or not scheme.scheme_data:
            return JsonResponse({'success': False, 'error': 'Hakuna mpango uliohifadhiwa. Tengeneza kwanza.'}, status=404)
        return JsonResponse({
            'success': True,
            'data': scheme.scheme_data,
            'saved_id': scheme.id,
            'meta': {
                'subject': scheme.subject.name,
                'class_name': scheme.class_name,
                'term': scheme.term,
                'year': scheme.year,
                'teacher_name': scheme.teacher_name,
                'school_name': scheme.school.name if scheme.school else '',
                'total_weeks': scheme.total_weeks,
                'syllabus': scheme.syllabus,
                'updated_at': scheme.updated_at.strftime('%d %b %Y, %H:%M'),
            }
        })
    except StudentTeacher.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Wasifu wa mwanafunzi haupatikani.'}, status=404)


# =============================================================================
# LESSON PLAN
# =============================================================================

def lesson_plan_view(request):
    """Display lesson plan generator form — public access."""
    education_levels = EducationLevel.objects.all().order_by('order')

    import json as _json
    classes_by_level = {}
    for cl in ClassLevel.objects.select_related('education_level').order_by('education_level', 'order'):
        classes_by_level.setdefault(cl.education_level_id, []).append({'id': cl.id, 'name': cl.name})

    primary_ids = list(
        EducationLevel.objects.filter(name__icontains='primary').values_list('id', flat=True)
    )
    subjects_by_level = {
        lvl.id: list(
            Subject.objects.filter(level='primary' if lvl.id in primary_ids else 'secondary')
            .order_by('name').values('id', 'name')
        )
        for lvl in education_levels
    }

    student = None
    school = None
    if request.user.is_authenticated:
        try:
            student = StudentTeacher.objects.select_related('selected_school').get(user=request.user)
            school = student.selected_school
            if not school:
                app = StudentApplication.objects.filter(
                    student=student, status='approved'
                ).select_related('school').first()
                if app:
                    school = app.school
        except StudentTeacher.DoesNotExist:
            pass

    return render(request, 'curriculum/lesson_plan.html', {
        'education_levels': education_levels,
        'classes_by_level_json': _json.dumps(classes_by_level),
        'subjects_by_level_json': _json.dumps(subjects_by_level),
        'student': student,
        'school': school,
        'is_public': not request.user.is_authenticated,
    })


def ajax_generate_lessonplan(request):
    """Generate lesson plan using AI."""
    if client is None:
        return JsonResponse({'success': False, 'error': 'Huduma ya AI haitumiki.'}, status=503)

    if request.method != 'POST':
        return JsonResponse({'success': False}, status=400)

    try:
        data = json.loads(request.body)

        education_level = data.get('education_level', '')
        class_name = data.get('class_name', '')
        subject = data.get('subject', '')
        subject_id = data.get('subject_id', '')
        topic = data.get('topic', '')
        subtopic = data.get('subtopic', '')
        term = data.get('term', 'I')
        year = data.get('year', 2026)
        duration = data.get('duration', 40)
        total_students = data.get('total_students', '')
        present_students = data.get('present_students', '')
        teacher_name = data.get('teacher_name', '')

        prompt = f"""
You are an AI assistant for Tanzanian teachers. Generate a detailed LESSON PLAN following the SEQUIP/TIE Tanzania IDDR revised format (2023).

The IDDR model stages:
- I = Introduction: Engage learners, activate prior knowledge.
- D = Competence Development: Guide learners to build competence.
- D = Design: Deepen learning — apply knowledge in real-life contexts.
- R = Realisation: Assess and evaluate student achievement.

Input Details:
- Education Level: {education_level}
- Class/Form: {class_name}
- Subject: {subject}
- Topic: {topic}
- Subtopic: {subtopic}
- Term: {term}, Year: {year}
- Duration: {duration} minutes
- Total Students: {total_students}
- Present Students: {present_students}

Allocate time: Introduction ≈ 15% | Competence Development ≈ 40% | Design ≈ 30% | Realisation ≈ 15%

Output MUST be ONLY valid JSON:
{{
    "lesson_title": "...",
    "main_competence": "...",
    "specific_competence": "...",
    "previous_knowledge": "...",
    "learning_objectives": ["..."],
    "teaching_methods": ["..."],
    "teaching_resources": ["..."],
    "lesson_development": [
        {{"time": "X min", "stage": "Introduction (I)", "methods": "...", "teacher_activities": "...", "student_activities": "...", "assessment_criteria": "..."}},
        ...
    ],
    "remarks": {{"strength": "...", "weakness": "...", "way_forward": "..."}}
}}
"""

        response = client.models.generate_content(model=model_name, contents=prompt)
        response_text = response.text

        cleaned = re.sub(r'```json\s*', '', response_text)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()

        start_idx = cleaned.find('{')
        end_idx = cleaned.rfind('}')
        if start_idx != -1 and end_idx != -1:
            lesson_data = json.loads(cleaned[start_idx:end_idx + 1])
        else:
            lesson_data = {
                "main_competence": f"Demonstrate understanding of {topic}",
                "specific_competence": f"Explain key concepts of {topic}",
                "previous_knowledge": "Basic knowledge from previous lessons",
                "learning_objectives": [f"Define {topic}"],
                "teaching_methods": ["Group discussion", "Q&A", "Brainstorming"],
                "teaching_resources": ["Chalkboard", "Textbook", "Charts"],
                "lesson_development": [
                    {"time": f"{max(5, int(int(duration)*0.15))} min", "stage": "Introduction (I)", "methods": "Q&A, Brainstorming", "teacher_activities": f"Activate prior knowledge about {topic}", "student_activities": "Respond to questions", "assessment_criteria": "Participation"},
                    {"time": f"{max(10, int(int(duration)*0.40))} min", "stage": "Competence Development (D)", "methods": "Group discussion", "teacher_activities": "Guide discussions", "student_activities": "Explore content", "assessment_criteria": "Accuracy"},
                    {"time": f"{max(8, int(int(duration)*0.30))} min", "stage": "Design (D)", "methods": "Problem solving", "teacher_activities": "Organise application activities", "student_activities": "Apply knowledge", "assessment_criteria": "Correct application"},
                    {"time": f"{max(5, int(int(duration)*0.15))} min", "stage": "Realisation (R)", "methods": "Quiz", "teacher_activities": "Assess and provide feedback", "student_activities": "Complete assessment", "assessment_criteria": "Achievement of objectives"}
                ],
                "remarks": {"strength": "", "weakness": "", "way_forward": ""}
            }

        saved_id = None
        if request.user.is_authenticated:
            try:
                student = StudentTeacher.objects.get(user=request.user)
                school = student.selected_school
                if school:
                    level_map = {'primary school': 'primary', 'ordinary level': 'ordinary', 'advanced level': 'advanced'}
                    edu_level = level_map.get((education_level or '').lower(), 'ordinary')
                    subj_obj = None
                    if subject_id:
                        try:
                            subj_obj = Subject.objects.get(id=int(subject_id))
                        except (Subject.DoesNotExist, ValueError):
                            pass
                    if not subj_obj and subject:
                        subj_obj = Subject.objects.filter(name__iexact=subject).first()
                    if subj_obj:
                        lp_obj = LessonPlan.objects.create(
                            student=student, school=school, subject=subj_obj,
                            education_level=edu_level, class_name=class_name,
                            term=term, year=int(year), topic=topic, subtopic=subtopic or '',
                            date=timezone.now().date(), duration=int(duration) or 40,
                            total_students=int(total_students) if total_students else 0,
                            present_students=int(present_students) if present_students else 0,
                            teacher_name=teacher_name or student.full_name,
                            main_competence=lesson_data.get('main_competence', ''),
                            specific_competence=lesson_data.get('specific_competence', ''),
                            previous_knowledge=lesson_data.get('previous_knowledge', ''),
                            learning_objectives=lesson_data.get('learning_objectives', []),
                            teaching_methods=lesson_data.get('teaching_methods', []),
                            teaching_resources=lesson_data.get('teaching_resources', []),
                            lesson_development=lesson_data.get('lesson_development', []),
                            remarks=lesson_data.get('remarks', ''),
                            generated_by_ai=True,
                        )
                        saved_id = lp_obj.id
            except Exception as save_err:
                print(f"[Curriculum] LessonPlan save error: {save_err}")

        return JsonResponse({'success': True, 'data': lesson_data, 'saved_id': saved_id})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f"Hitilafu ya AI: {str(e)[:300]}"}, status=500)


def download_lesson_plan_pdf(request):
    """Export Lesson Plan as PDF."""
    if request.method != 'POST':
        return HttpResponse("Invalid request", status=400)

    data = json.loads(request.body)
    lesson = data.get('lesson_data', {})
    form = data.get('form_data', {})

    NAVY = colors.HexColor('#0A2B5E')
    GOLD = colors.HexColor('#C8900A')
    LIGHT = colors.HexColor('#EEF1F6')
    STRIPE = colors.HexColor('#F4F7FF')
    BORDER = colors.HexColor('#9BAAC4')

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    elements = []

    normal = ParagraphStyle('LP_N', fontName='Helvetica', fontSize=9, leading=13, wordWrap='LTR', spaceAfter=3)
    section_hdr = ParagraphStyle('LP_H', fontName='Helvetica-Bold', fontSize=10, textColor=NAVY, spaceBefore=10, spaceAfter=4)
    cell_s = ParagraphStyle('LP_C', fontName='Helvetica', fontSize=8, leading=11, wordWrap='LTR')
    hdr_s = ParagraphStyle('LP_CH', fontName='Helvetica-Bold', fontSize=8, leading=11, textColor=colors.white, wordWrap='LTR', alignment=1)
    label_s = ParagraphStyle('LP_L', fontName='Helvetica-Bold', fontSize=8, leading=11, textColor=NAVY)

    elements.append(Paragraph("LESSON PLAN",
        ParagraphStyle('LP_T', fontName='Helvetica-Bold', fontSize=16, alignment=1, textColor=NAVY, spaceAfter=2)))
    elements.append(Paragraph(
        f"{form.get('subject','')}  |  {form.get('class_name','')}  |  Term {form.get('term','')} {form.get('year','')}",
        ParagraphStyle('LP_S', fontSize=9, alignment=1, textColor=colors.grey, spaceAfter=10)))

    def P(txt, st=normal):
        return Paragraph(str(txt or ''), st)

    meta_rows = [
        [P('Teacher', label_s), P(form.get('teacher_name', '')),
         P('Subject', label_s), P(form.get('subject', ''))],
        [P('Class', label_s), P(form.get('class_name', '')),
         P('Term/Year', label_s), P(f"Term {form.get('term','')} {form.get('year','')}")],
        [P('Topic', label_s), P(form.get('topic', '')),
         P('Subtopic', label_s), P(form.get('subtopic', ''))],
        [P('Duration', label_s), P(f"{form.get('duration','')} minutes"),
         P('Date', label_s), P(str(timezone.now().date()))],
        [P('Students', label_s),
         P(f"{form.get('total_students','')} total / {form.get('present_students','')} present"),
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

    for label, key in [('Main Competence', 'main_competence'),
                       ('Specific Competence', 'specific_competence'),
                       ('Previous Knowledge', 'previous_knowledge')]:
        val = lesson.get(key, '')
        if val:
            elements.append(Paragraph(f"<b>{label}:</b>  {val}", normal))

    for label, key in [('Learning Objectives', 'learning_objectives'),
                       ('Teaching Methods', 'teaching_methods'),
                       ('Teaching Resources', 'teaching_resources')]:
        items = lesson.get(key, [])
        if items:
            elements.append(Paragraph(label, section_hdr))
            for item in items:
                elements.append(Paragraph(
                    f"<bullet>•</bullet> {item}",
                    ParagraphStyle('LP_B', fontName='Helvetica', fontSize=9, leading=13, leftIndent=14, wordWrap='LTR')))

    ld = lesson.get('lesson_development', [])
    if ld:
        elements.append(Paragraph("Lesson Development (IDDR Model)", section_hdr))
        ld_headers = ['Time', 'Stage (IDDR)', 'Methods', 'Teacher Activities', 'Student Activities', 'Assessment Criteria']
        ld_data = [[Paragraph(h, hdr_s) for h in ld_headers]]
        for i, stage in enumerate(ld):
            bg = colors.white if i % 2 == 0 else STRIPE
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
        ]
        for i in range(1, len(ld_data)):
            ld_ts.append(('BACKGROUND', (0, i), (-1, i), STRIPE if i % 2 == 0 else colors.white))
        ld_tbl.setStyle(TableStyle(ld_ts))
        elements.append(ld_tbl)

    remarks = lesson.get('remarks', '')
    if remarks:
        elements.append(Spacer(1, 8))
        elements.append(Paragraph("Remarks", section_hdr))
        if isinstance(remarks, dict):
            for label, key in [('1. Strength', 'strength'), ('2. Weakness', 'weakness'), ('3. Way Forward', 'way_forward')]:
                val = remarks.get(key, '') or '...............................................'
                elements.append(Paragraph(f"<b>{label}:</b>  {val}", normal))
        else:
            elements.append(Paragraph(str(remarks), normal))

    doc.build(elements)
    buffer.seek(0)
    safe_name = f"LessonPlan_{form.get('subject','')}_{form.get('topic','')}".replace(' ', '_')
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{safe_name}.pdf"'
    return response


def download_lesson_plan_word(request):
    """Export Lesson Plan as Word (.docx)."""
    if request.method != 'POST':
        return HttpResponse("Invalid request", status=400)

    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    data = json.loads(request.body)
    lesson = data.get('lesson_data', {})
    form = data.get('form_data', {})

    doc = Document()
    doc.add_heading('LESSON PLAN', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta_table = doc.add_table(rows=5, cols=4)
    meta_table.style = 'Table Grid'
    rows = meta_table.rows

    def _set(r, c, text, bold=False):
        cell = rows[r].cells[c]
        cell.text = text
        if bold and cell.paragraphs[0].runs:
            cell.paragraphs[0].runs[0].bold = True

    _set(0, 0, 'Teacher:', True)
    _set(0, 1, form.get('teacher_name', ''))
    _set(0, 2, 'Subject:', True)
    _set(0, 3, form.get('subject', ''))
    _set(1, 0, 'Class:', True)
    _set(1, 1, form.get('class_name', ''))
    _set(1, 2, 'Term/Year:', True)
    _set(1, 3, f"Term {form.get('term','')} {form.get('year','')}")
    _set(2, 0, 'Topic:', True)
    _set(2, 1, form.get('topic', ''))
    _set(2, 2, 'Subtopic:', True)
    _set(2, 3, form.get('subtopic', ''))
    _set(3, 0, 'Duration:', True)
    _set(3, 1, f"{form.get('duration','')} min")
    _set(3, 2, 'Date:', True)
    _set(3, 3, str(timezone.now().date()))
    _set(4, 0, 'Students:', True)
    _set(4, 1, f"{form.get('total_students','')} / {form.get('present_students','')}")

    doc.add_paragraph()

    for label, key in [('Main Competence', 'main_competence'),
                       ('Specific Competence', 'specific_competence'),
                       ('Previous Knowledge', 'previous_knowledge')]:
        val = lesson.get(key, '')
        if val:
            p = doc.add_paragraph()
            p.add_run(f"{label}: ").bold = True
            p.add_run(val)

    for label, key in [('Learning Objectives', 'learning_objectives'),
                       ('Teaching Methods', 'teaching_methods'),
                       ('Teaching Resources', 'teaching_resources')]:
        items = lesson.get(key, [])
        if items:
            doc.add_heading(label, level=2)
            for item in items:
                doc.add_paragraph(item, style='List Bullet')

    ld = lesson.get('lesson_development', [])
    if ld:
        doc.add_heading('Lesson Development (IDDR Model)', level=2)
        ld_table = doc.add_table(rows=1, cols=6)
        ld_table.style = 'Table Grid'
        hdr = ld_table.rows[0].cells
        for i, h in enumerate(['Time', 'Stage (IDDR)', 'Methods', 'Teacher Activities', 'Student Activities', 'Assessment Criteria']):
            hdr[i].text = h
            hdr[i].paragraphs[0].runs[0].bold = True
        for stage in ld:
            row = ld_table.add_row().cells
            row[0].text = stage.get('time', '')
            row[1].text = stage.get('stage', stage.get('phase', ''))
            row[2].text = stage.get('methods', '')
            row[3].text = stage.get('teacher_activities', '')
            row[4].text = stage.get('student_activities', '')
            row[5].text = stage.get('assessment_criteria', '')

    remarks = lesson.get('remarks', '')
    if remarks:
        doc.add_heading('Remarks', level=2)
        if isinstance(remarks, dict):
            for label, key in [('1. Strength', 'strength'), ('2. Weakness', 'weakness'), ('3. Way Forward', 'way_forward')]:
                p = doc.add_paragraph()
                p.add_run(f"{label}: ").bold = True
                p.add_run(remarks.get(key, '') or '...............................................')
        else:
            p = doc.add_paragraph()
            p.add_run('Remarks: ').bold = True
            p.add_run(str(remarks))

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    safe_name = f"LessonPlan_{form.get('subject','')}_{form.get('topic','')}".replace(' ', '_')
    response = HttpResponse(buffer, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{safe_name}.docx"'
    return response


@login_required
def ajax_load_saved_lessonplan(request):
    """Load most recent saved LessonPlan from DB."""
    try:
        student = StudentTeacher.objects.get(user=request.user)
        lp = (LessonPlan.objects
              .filter(student=student)
              .select_related('subject')
              .order_by('-created_at')
              .first())
        if not lp or not lp.lesson_development:
            return JsonResponse({'success': False, 'error': 'Hakuna mpango wa somo uliohifadhiwa.'}, status=404)
        lesson_data = {
            'lesson_title': f"{lp.subject.name} - {lp.topic}",
            'main_competence': lp.main_competence,
            'specific_competence': lp.specific_competence,
            'previous_knowledge': lp.previous_knowledge,
            'learning_objectives': lp.learning_objectives,
            'teaching_methods': lp.teaching_methods,
            'teaching_resources': lp.teaching_resources,
            'lesson_development': lp.lesson_development,
            'remarks': lp.remarks,
        }
        form_data = {
            'subject': lp.subject.name, 'class_name': lp.class_name,
            'term': lp.term, 'year': lp.year, 'topic': lp.topic,
            'subtopic': lp.subtopic, 'teacher_name': lp.teacher_name,
            'duration': lp.duration, 'total_students': lp.total_students,
            'present_students': lp.present_students,
        }
        return JsonResponse({'success': True, 'data': lesson_data, 'form_data': form_data, 'saved_id': lp.id})
    except StudentTeacher.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Wasifu haupatikani.'}, status=404)


# =============================================================================
# LOGBOOK
# =============================================================================

@login_required
def submit_logbook(request):
    """Submit daily logbook entry."""
    student = get_or_create_student_profile(request.user)
    today = timezone.now().date()

    if today.weekday() >= 5:
        messages.info(request, "Hakuna kazi ya uwanjani wikendi. Rudi tena Jumatatu.")
        return redirect(reverse('curriculum:dashboard'))

    if not student.selected_school:
        messages.error(request, "Lazima uchague shule kabla ya kujaza logbook.")
        return redirect(reverse('curriculum:dashboard'))

    school = student.selected_school
    logbook_entry = _cached_today_logbook(student, school, today)

    if request.method == 'POST':
        if logbook_entry is None:
            logbook_entry, _ = LogbookEntry.objects.get_or_create(
                student=student, date=today,
                defaults={'school': school, 'morning_check_in': timezone.now()}
            )
            _invalidate_today_logbook(student, today)

        form = LogbookForm(request.POST, instance=logbook_entry)

        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        is_location_verified = request.POST.get('is_location_verified', 'false') == 'true'

        days_swahili = {0: 'Jumatatu', 1: 'Jumanne', 2: 'Jumatano', 3: 'Alhamisi', 4: 'Ijumaa'}

        if not is_location_verified:
            messages.error(request, "Thibiti eneo lako kwanza kabla ya kuwasilisha logbook.")
            return render(request, 'curriculum/logbook.html', {
                'form': form, 'student': student, 'logbook_entry': logbook_entry,
                'today': today, 'today_name': days_swahili.get(today.weekday(), 'Leo'),
                'school': school, 'subjects': _cached_subjects(student),
                'location_error': True,
            })

        if not latitude or not longitude:
            messages.error(request, "Eneo halipatikani. Washa GPS na ujaribu tena.")
            return render(request, 'curriculum/logbook.html', {
                'form': form, 'student': student, 'logbook_entry': logbook_entry,
                'today': today, 'today_name': days_swahili.get(today.weekday(), 'Leo'),
                'school': school, 'subjects': _cached_subjects(student),
                'location_error': True,
            })

        try:
            lat = float(latitude)
            lng = float(longitude)
            logbook_entry.latitude = lat
            logbook_entry.longitude = lng
            logbook_entry.location_address = request.POST.get('location_address', '')

            if school and school.latitude and school.longitude:
                from geopy.distance import geodesic
                distance_m = geodesic((lat, lng), (school.latitude, school.longitude)).meters
                school_verified = distance_m <= 1000
            else:
                school_verified = (-11.8 <= lat <= -1.0) and (29.3 <= lng <= 40.5)

            logbook_entry.is_location_verified = school_verified
            logbook_entry.is_at_school = school_verified
        except (ValueError, TypeError) as e:
            messages.error(request, f"Hitilafu ya eneo: {e}")
            return render(request, 'curriculum/logbook.html', {
                'form': form, 'student': student, 'logbook_entry': logbook_entry,
                'today': today, 'today_name': days_swahili.get(today.weekday(), 'Leo'),
                'school': school, 'subjects': _cached_subjects(student),
            })

        if form.is_valid():
            entry = form.save(commit=False)
            try:
                entry.lessons_data = json.loads(request.POST.get('lessons_data', '[]'))
            except (ValueError, TypeError):
                entry.lessons_data = []

            entry.latitude = logbook_entry.latitude
            entry.longitude = logbook_entry.longitude
            entry.is_location_verified = logbook_entry.is_location_verified
            entry.is_at_school = logbook_entry.is_at_school
            entry.location_address = logbook_entry.location_address
            entry.save()
            _invalidate_today_logbook(student, today)

            if entry.is_location_verified:
                messages.success(request, "✅ Logbook imesajiliwa kikamilifu!")
            else:
                messages.warning(request, "⚠️ Logbook imesajiliwa. Eneo halikuthibitishwa.")

            return redirect(reverse('curriculum:logbook_history'))
        else:
            messages.error(request, "Tafadhali kagua makosa yaliyomo kwenye fomu.")
    else:
        form = LogbookForm(instance=logbook_entry)

    subjects = _cached_subjects(student)
    days_swahili = {0: 'Jumatatu', 1: 'Jumanne', 2: 'Jumatano', 3: 'Alhamisi', 4: 'Ijumaa'}

    return render(request, 'curriculum/logbook.html', {
        'form': form, 'student': student, 'logbook_entry': logbook_entry,
        'today': today, 'today_name': days_swahili.get(today.weekday(), 'Leo'),
        'school': school, 'subjects': subjects,
    })


@login_required
def logbook_history(request):
    """View logbook history."""
    student = get_or_create_student_profile(request.user)

    week_filter = request.GET.get('week')
    month_filter = request.GET.get('month')

    entries = LogbookEntry.objects.filter(student=student).select_related('subject_taught', 'school')

    if week_filter:
        try:
            year, week = map(int, week_filter.split('-W'))
            start_date = datetime.strptime(f'{year}-W{week}-1', "%Y-W%W-%w").date()
            entries = entries.filter(date__range=[start_date, start_date + timedelta(days=6)])
        except ValueError:
            messages.error(request, "Tarehe ya wiki si sahihi.")

    elif month_filter:
        try:
            year, month = map(int, month_filter.split('-'))
            entries = entries.filter(date__year=year, date__month=month)
        except ValueError:
            messages.error(request, "Tarehe ya mwezi si sahihi.")

    else:
        today = timezone.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        entries = entries.filter(date__range=[start_of_week, start_of_week + timedelta(days=4)])

    return render(request, 'curriculum/logbook_history.html', {
        'entries': entries.order_by('-date'), 'student': student,
    })


@login_required
def download_logbook_pdf(request, period_type=None):
    """Download logbook as PDF."""
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet

    student = get_or_create_student_profile(request.user)
    period_value = period_type or 'week'
    today = timezone.now().date()

    if period_value == 'today':
        entries = LogbookEntry.objects.filter(student=student, date=today)
        filename = f"logbook_{today}.pdf"
        title = f"Logbook — {today}"
    elif period_value == 'week':
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=4)
        entries = LogbookEntry.objects.filter(student=student, date__range=[start_of_week, end_of_week])
        filename = f"logbook_wiki_{start_of_week}.pdf"
        title = f"Logbook — Wiki {start_of_week} hadi {end_of_week}"
    elif period_value == 'month':
        start_of_month = today.replace(day=1)
        next_month = today.replace(day=28) + timedelta(days=4)
        end_of_month = next_month - timedelta(days=next_month.day)
        entries = LogbookEntry.objects.filter(student=student, date__range=[start_of_month, end_of_month])
        filename = f"logbook_mwezi_{today.year}_{today.month:02d}.pdf"
        title = f"Logbook — Mwezi {today.month}/{today.year}"
    else:
        entries = LogbookEntry.objects.filter(student=student)
        filename = f"logbook_zote_{today}.pdf"
        title = "Logbook Zote"

    entries = entries.order_by('date')

    NAVY = colors.HexColor('#0A2B5E')
    GOLD = colors.HexColor('#C8900A')
    LIGHT = colors.HexColor('#EEF1F6')
    WHITE = colors.white

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)

    styles = getSampleStyleSheet()
    s_title = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=14, textColor=NAVY, spaceAfter=4)
    s_sub = ParagraphStyle('sub', fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#4A5568'), spaceAfter=2)
    s_head = ParagraphStyle('head', fontName='Helvetica-Bold', fontSize=10, textColor=WHITE)
    s_label = ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=8, textColor=NAVY)
    s_body = ParagraphStyle('body', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#1A1A2E'), leading=11)
    s_small = ParagraphStyle('small', fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#4A5568'), leading=10)

    school_name = student.selected_school.name if student.selected_school else '—'
    district_name = (student.selected_school.district.name if student.selected_school and student.selected_school.district else '—')
    current_year = _cached_active_year()
    year_label = str(current_year) if current_year else '—'

    story = []
    story.append(Paragraph("WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA",
                           ParagraphStyle('gov', fontName='Helvetica-Bold', fontSize=11, textColor=NAVY, alignment=1)))
    story.append(Paragraph("Mfumo wa Ufuatiliaji wa Walimu Wanafunzi (IMS)",
                           ParagraphStyle('gov2', fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#4A5568'), alignment=1, spaceAfter=6)))
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=6))
    story.append(Paragraph(title, s_title))

    info_data = [
        [Paragraph('<b>Jina la Mwanafunzi:</b>', s_label), Paragraph(student.full_name, s_body),
         Paragraph('<b>Shule:</b>', s_label), Paragraph(school_name, s_body)],
        [Paragraph('<b>Wilaya:</b>', s_label), Paragraph(district_name, s_body),
         Paragraph('<b>Mwaka wa Masomo:</b>', s_label), Paragraph(year_label, s_body)],
        [Paragraph('<b>Tarehe ya Chapisha:</b>', s_label), Paragraph(str(today), s_body),
         Paragraph('<b>Idadi ya Siku:</b>', s_label), Paragraph(str(entries.count()), s_body)],
    ]
    info_tbl = Table(info_data, colWidths=[3.5 * cm, 5.5 * cm, 3.5 * cm, 5.5 * cm])
    info_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, NAVY),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CBD5E0')),
        ('PADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 10))

    day_names = {'Monday': 'Jumatatu', 'Tuesday': 'Jumanne', 'Wednesday': 'Jumatano',
                 'Thursday': 'Alhamisi', 'Friday': 'Ijumaa', 'Saturday': 'Jumamosi', 'Sunday': 'Jumapili'}

    for entry in entries:
        day_sw = day_names.get(entry.date.strftime('%A'), entry.date.strftime('%A'))
        gps_status = "✓ Imehakikiwa" if entry.is_location_verified else "✗ Haijahakikiwa"
        gps_color = colors.HexColor('#10B981') if entry.is_location_verified else colors.HexColor('#F59E0B')

        day_hdr = Table(
            [[Paragraph(f"{day_sw} — {entry.date}", s_head),
              Paragraph(f"GPS: {gps_status}", ParagraphStyle('gps', fontName='Helvetica-Bold', fontSize=8, textColor=gps_color))]],
            colWidths=[13 * cm, 5 * cm]
        )
        day_hdr.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), NAVY),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        story.append(day_hdr)

        lessons = entry.lessons_data if entry.lessons_data else []
        if not lessons:
            if entry.other_activities or entry.challenges_faced:
                extra_rows = []
                if entry.other_activities:
                    extra_rows.append([Paragraph('<b>Shughuli Nyingine</b>', s_label), Paragraph(entry.other_activities, s_body)])
                if entry.challenges_faced:
                    extra_rows.append([Paragraph('<b>Changamoto</b>', s_label), Paragraph(entry.challenges_faced, s_body)])
                if extra_rows:
                    extra_tbl = Table(extra_rows, colWidths=[4 * cm, 14 * cm])
                    extra_tbl.setStyle(TableStyle([
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
                        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CBD5E0')),
                        ('BACKGROUND', (0, 0), (0, -1), LIGHT),
                        ('PADDING', (0, 0), (-1, -1), 4),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ]))
                    story.append(extra_tbl)
            else:
                story.append(Paragraph("Hakuna data ya masomo.", s_small))
        else:
            for lesson in lessons:
                period_num = lesson.get('period', '?')
                subj = lesson.get('subject', '—')
                cls = lesson.get('class', '—')
                main_topic = lesson.get('main_topic', '—')
                activity = lesson.get('activity_type', '—')
                enrolled = lesson.get('enrolled', '—')
                present = lesson.get('present', '—')

                period_hdr = Table(
                    [[Paragraph(
                        f"Kipindi {period_num}  |  {subj}  |  Darasa: {cls}  |  Waliojumuishwa: {enrolled}  |  Waliopo: {present}  |  Aina: {activity}",
                        ParagraphStyle('ph', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE))]],
                    colWidths=[18 * cm]
                )
                period_hdr.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), GOLD),
                    ('PADDING', (0, 0), (-1, -1), 5),
                ]))
                story.append(period_hdr)

                lesson_rows = [
                    [Paragraph('<b>Mada Kuu</b>', s_label), Paragraph(main_topic, s_body),
                     Paragraph('<b>Mada Ndogo</b>', s_label), Paragraph(lesson.get('subtopic', '—'), s_body)],
                    [Paragraph('<b>Mbinu</b>', s_label), Paragraph(lesson.get('methods', '—'), s_body),
                     Paragraph('<b>Vifaa</b>', s_label), Paragraph(lesson.get('teaching_aids', '—'), s_body)],
                ]
                lesson_tbl = Table(lesson_rows, colWidths=[3.5 * cm, 5.5 * cm, 3.5 * cm, 5.5 * cm])
                lesson_tbl.setStyle(TableStyle([
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
                    ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CBD5E0')),
                    ('BACKGROUND', (0, 0), (0, -1), LIGHT),
                    ('BACKGROUND', (2, 0), (2, -1), LIGHT),
                    ('PADDING', (0, 0), (-1, -1), 4),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(lesson_tbl)

        if entry.supervisor_remarks:
            sr_tbl = Table(
                [[Paragraph('<b>Maoni ya Msimamizi</b>', s_label), Paragraph(entry.supervisor_remarks, s_body)]],
                colWidths=[4 * cm, 14 * cm]
            )
            sr_tbl.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
                ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CBD5E0')),
                ('BACKGROUND', (0, 0), (0, -1), LIGHT),
                ('PADDING', (0, 0), (-1, -1), 4),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(sr_tbl)

        story.append(Spacer(1, 10))

    if not entries:
        story.append(Spacer(1, 20))
        story.append(Paragraph("Hakuna rekodi za logbook kwa kipindi kilichochaguliwa.", s_sub))

    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceBefore=10, spaceAfter=4))
    story.append(Paragraph("© Wizara ya Elimu, Sayansi na Teknolojia — IMS v2.1.0",
                           ParagraphStyle('footer', fontName='Helvetica', fontSize=7, textColor=colors.HexColor('#4A5568'), alignment=1)))

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def logbook_download_options(request):
    """Page for choosing download options."""
    student = get_or_create_student_profile(request.user)
    total_entries = LogbookEntry.objects.filter(student=student).count()
    this_week_entries = LogbookEntry.objects.filter(
        student=student, date__gte=timezone.now().date() - timedelta(days=7)
    ).count()

    return render(request, 'curriculum/logbook_download.html', {
        'student': student, 'total_entries': total_entries, 'this_week_entries': this_week_entries,
    })


# =============================================================================
# API HELPERS
# =============================================================================

def get_topics_by_subject(request):
    """AJAX: Get topics (from textbooks) for a given subject and class level."""
    subject_id = request.GET.get('subject_id')
    class_level_id = request.GET.get('class_level_id')
    
    if not subject_id:
        return JsonResponse([], safe=False)
    
    subject = Subject.objects.filter(id=subject_id).first()
    if not subject:
        return JsonResponse([], safe=False)
    
    # Map subject level to textbook education_level
    if subject.level == 'primary':
        edu_level = 'primary'
    else:
        # For secondary, check class level to determine ordinary vs advanced
        if class_level_id:
            cl = ClassLevel.objects.filter(id=class_level_id).first()
            if cl:
                cl_name = cl.name.lower()
                if 'form 5' in cl_name or 'form 6' in cl_name or 'advanced' in cl_name:
                    edu_level = 'advanced'
                else:
                    edu_level = 'ordinary'
            else:
                edu_level = 'ordinary'
        else:
            edu_level = 'ordinary'
    
    textbooks = Textbook.objects.filter(
        subject=subject,
        education_level=edu_level,
        is_active=True
    ).order_by('title').values('id', 'title')
    
    topics = list(textbooks)
    
    # If no textbooks found, return empty list
    return JsonResponse(topics, safe=False)


def get_classes_by_level(request):
    """AJAX: Get classes for a given education level."""
    level_id = request.GET.get('level_id')
    if not level_id:
        return JsonResponse([], safe=False)
    classes = ClassLevel.objects.filter(education_level_id=level_id).order_by('order')
    return JsonResponse([{'id': c.id, 'name': c.name} for c in classes], safe=False)


def get_subjects_by_level(request):
    """AJAX: Get subjects for a given education level."""
    level_id = request.GET.get('level_id')
    if not level_id:
        return JsonResponse([], safe=False)
    level = EducationLevel.objects.filter(id=level_id).first()
    if not level:
        return JsonResponse([], safe=False)
    is_primary = 'primary' in level.name.lower()
    subjects = Subject.objects.filter(level='primary' if is_primary else 'secondary').order_by('name')
    return JsonResponse([{'id': s.id, 'name': s.name} for s in subjects], safe=False)


def get_textbooks_by_level(request):
    """AJAX: Get textbooks/references for a given education level."""
    level_id = request.GET.get('level_id')
    if not level_id:
        return JsonResponse([], safe=False)
    level = EducationLevel.objects.filter(id=level_id).first()
    if not level:
        return JsonResponse([], safe=False)
    level_name = level.name.lower()
    level_map = {'primary': 'primary', 'ordinary': 'ordinary', 'advanced': 'advanced'}
    mapped = 'primary'
    for k, v in level_map.items():
        if k in level_name:
            mapped = v
            break
    textbooks = Textbook.objects.filter(education_level=mapped, is_active=True).order_by('title')
    return JsonResponse([{'id': t.id, 'title': t.title, 'publisher': t.publisher} for t in textbooks], safe=False)
