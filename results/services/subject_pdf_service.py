"""subject_pdf_service.py — Generate an advanced per-subject PDF for one exam subject.

Uses NECTA-aligned grading (CSEE for Form 1-4, ACSEE for Form 5-6) and adds
a grade-distribution breakdown, gender comparison (when available), and
rule-based recommendations for the teacher — on top of the ranked results
table.
"""

from __future__ import annotations

from django.http import HttpResponse

from ..models import ExamResult
from ..utils import get_grade, get_grade_for_form, is_passing_grade
from .results_analytics import GRADE_ORDER, compute_subject_stats, generate_recommendations

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
        HRFlowable,
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _grade_color(grade: str):
    """Return a reportlab color for the grade."""
    palette = {
        'A':  colors.HexColor('#1a7a3b'),
        'B':  colors.HexColor('#2d7d46'),
        'C':  colors.HexColor('#8a6f00'),
        'D':  colors.HexColor('#b35c00'),
        'E':  colors.HexColor('#b35c00'),
        'S':  colors.HexColor('#946200'),
        'F':  colors.HexColor('#b30000'),
    }
    return palette.get(grade, colors.black)


NAVY = colors.HexColor('#1F7A3D')
GOLD = colors.HexColor('#D9A441')
LIGHT_GOLD = colors.HexColor('#FBEFD3')
WHITE = colors.white
LIGHT_GREY = colors.HexColor('#F0F2F5')
DARK_GREY = colors.HexColor('#444444')

GRADE_KEYS_OLEVEL = [('A', '75-100'), ('B', '65-74'), ('C', '45-64'), ('D', '30-44'), ('F', '0-29')]
GRADE_KEYS_FTNA = [('A', '75-100'), ('B', '65-74'), ('C', '45-64'), ('D', '30-44'), ('F', '0-29')]
GRADE_KEYS_ALEVEL = [('A', '80-100'), ('B', '70-79'), ('C', '60-69'), ('D', '50-59'), ('E', '40-49'), ('S', '35-39'), ('F', '0-34')]


def get_grade_keys_for_form(form):
    """Return the correct NECTA grade key for an exam's form level.

    - Form 2 (FTNA) uses its own scale (C 45+, D 30+, F <30)
    - Form 5/6 (ACSEE) uses the 7-band scale
    - Form 1/3/4 (CSEE) uses the standard O-Level scale
    """
    if form == 2:
        return GRADE_KEYS_FTNA
    if form in (5, 6):
        return GRADE_KEYS_ALEVEL
    return GRADE_KEYS_OLEVEL

_LABELS = {
    'sw': {
        'name': 'JINA LA MWANAFUNZI', 'score': 'ALAMA', 'grade': 'DARAJA',
        'total_students': 'JUMLA YA WANAFUNZI', 'passed': 'WALIOFAULU', 'pass_rate': 'ASILIMIA KUFAULU',
        'class_avg': 'WASTANI WA DARASA', 'distribution': 'MGAWANYO WA MADARAJA',
        'gender_comparison': 'ULINGANISHO WA JINSIA', 'gender': 'JINSIA', 'count': 'IDADI',
        'girls': 'WASICHANA', 'boys': 'WAVULANA', 'average': 'WASTANI',
        'recommendations': 'MAPENDEKEZO KWA MWALIMU', 'teacher': 'Mwalimu', 'subject': 'Somo',
    },
    'en': {
        'name': 'STUDENT NAME', 'score': 'SCORE', 'grade': 'GRADE',
        'total_students': 'TOTAL STUDENTS', 'passed': 'PASSED', 'pass_rate': 'PASS RATE',
        'class_avg': 'CLASS AVERAGE', 'distribution': 'GRADE DISTRIBUTION',
        'gender_comparison': 'GENDER COMPARISON', 'gender': 'GENDER', 'count': 'COUNT',
        'girls': 'GIRLS', 'boys': 'BOYS', 'average': 'AVERAGE',
        'recommendations': 'RECOMMENDATIONS FOR TEACHER', 'teacher': 'Teacher', 'subject': 'Subject',
    },
}


def generate_subject_pdf_response(exam, subject, teacher_name: str = '', lang: str = 'sw') -> HttpResponse:
    """Generate an A4 PDF for ONE subject: position, name, score, grade,
    grade distribution, gender comparison, and teacher recommendations.

    Includes ALL registered students:
    - Students with marks → show score + grade
    - Students with X (absent) → show X
    - Students with blank (no marks entered) → show blank
    """
    from results.models import FormStudent, Student

    # ── Step 1: All ExamResult entries (scored + absent) ──
    all_results = list(
        ExamResult.objects.filter(exam=exam, subject=subject)
        .select_related('student')
    )
    result_by_student = {r.student_id: r for r in all_results}

    # ── Step 2: Students from roster who have NO ExamResult (blank) ──
    roster_student_ids = set()
    if exam.school:
        form_students = FormStudent.objects.filter(
            school=exam.school, form=exam.form
        ).select_related()
        for fs in form_students:
            # Subject filter: if FormStudent has subjects assigned,
            # only include if this subject is in their list
            if fs.subjects.exists() and not fs.subjects.filter(pk=subject.pk).exists():
                continue
            # Bridge to Student model (same logic as _student_from_form_student)
            stu, _ = Student.objects.get_or_create(
                first_name=fs.first_name,
                last_name=fs.last_name or 'Unknown',
                defaults={'middle_name': fs.middle_name, 'gender': fs.gender},
            )
            roster_student_ids.add(stu.id)
    # Fallback: if no FormStudent roster, use students who have ExamResults
    if not roster_student_ids:
        roster_student_ids = {r.student_id for r in all_results}

    # ── Step 3: Build rows for ALL students ──
    scored_rows = []
    absent_rows = []
    blank_rows = []

    for stu_id in roster_student_ids:
        result = result_by_student.get(stu_id)
        if result is None:
            # Student in roster but no ExamResult at all → blank
            stu = Student.objects.filter(id=stu_id).first()
            if stu:
                full_name = ' '.join(p for p in [stu.first_name, stu.middle_name, stu.last_name] if p)
                blank_rows.append({
                    'name': full_name,
                    'score': None,
                    'grade': '',
                    'gender': stu.gender,
                })
        elif result.is_absent:
            # Student marked absent → X
            full_name = ' '.join(p for p in [result.student.first_name, result.student.middle_name, result.student.last_name] if p)
            absent_rows.append({
                'name': full_name,
                'score': None,
                'grade': 'X',
                'gender': result.student.gender,
            })
        else:
            # Student with marks → score + grade
            full_name = ' '.join(p for p in [result.student.first_name, result.student.middle_name, result.student.last_name] if p)
            scored_rows.append({
                'name': full_name,
                'score': result.score or 0,
                'grade': get_grade_for_form(result.score or 0, exam.form),
                'gender': result.student.gender,
            })

    # Sort scored by score descending, then name
    scored_rows.sort(key=lambda r: (-r['score'], r['name']))
    absent_rows.sort(key=lambda r: r['name'])
    blank_rows.sort(key=lambda r: r['name'])

    # Combine: scored first (ranked), then absent (X), then blank
    rows_data = []
    for pos, row in enumerate(scored_rows, 1):
        row['position'] = pos
        rows_data.append(row)
    for row in absent_rows:
        row['position'] = ''
        rows_data.append(row)
    for row in blank_rows:
        row['position'] = ''
        rows_data.append(row)

    labels = _LABELS.get(lang, _LABELS['sw'])
    safe_subject = subject.name.replace(' ', '_').replace('/', '-')
    meta_parts = [p for p in [exam.school_name, str(exam), f"{labels['teacher']}: {teacher_name}" if teacher_name else ''] if p]

    return _render_results_pdf(
        heading=subject.name.upper(),
        meta_parts=meta_parts,
        rows_data=rows_data,
        filename_stub=f"{safe_subject}_{exam.id}_results",
        subject_name=subject.name,
        grade_keys=get_grade_keys_for_form(exam.form),
        lang=lang,
    )


def generate_personal_pdf_response(upload, lang: str = 'sw') -> HttpResponse:
    """Generate the same-style advanced PDF for a teacher's private (non-official) upload."""
    results = list(upload.results.order_by('-score', 'student_name'))
    rows_data = []
    for pos, result in enumerate(results, 1):
        rows_data.append({
            'position': pos,
            'name': result.student_name,
            'score': result.score,
            'grade': get_grade(result.score),  # personal uploads have no exam.form; default to O-Level
            'gender': None,
        })

    labels = _LABELS.get(lang, _LABELS['sw'])
    teacher_label = upload.teacher.full_name or upload.teacher.email
    meta_parts = [f"{labels['subject']}: {upload.subject.name}", f"{labels['teacher']}: {teacher_label}", upload.created_at.strftime('%d %b %Y')]
    safe_title = upload.title.replace(' ', '_').replace('/', '-') or 'matokeo'

    return _render_results_pdf(
        heading=upload.title.upper(),
        meta_parts=meta_parts,
        rows_data=rows_data,
        filename_stub=f"binafsi_{safe_title}_{upload.id}",
        subject_name=upload.subject.name,
        grade_keys=GRADE_KEYS_OLEVEL,
        lang=lang,
    )


def _render_results_pdf(
    *,
    heading: str,
    meta_parts: list[str],
    rows_data: list[dict],
    filename_stub: str,
    subject_name: str,
    grade_keys: list[tuple[str, str]],
    lang: str = 'sw',
) -> HttpResponse:
    """Shared A4 PDF renderer: table + distribution + gender + recommendations."""

    labels = _LABELS.get(lang, _LABELS['sw'])
    stats = compute_subject_stats(rows_data)
    recommendations = generate_recommendations(stats, subject_name=subject_name, lang=lang)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename_stub}.pdf"'

    if not REPORTLAB_AVAILABLE:
        response.write(b"reportlab is not installed. Cannot generate PDF.")
        return response

    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'SubjectTitle', parent=styles['Heading1'], textColor=WHITE, fontSize=16,
        fontName='Helvetica-Bold', spaceAfter=0, spaceBefore=0, leading=20,
    )
    section_style = ParagraphStyle(
        'Section', parent=styles['Heading2'], textColor=NAVY, fontSize=11,
        fontName='Helvetica-Bold', spaceAfter=6, spaceBefore=0,
    )
    label_style = ParagraphStyle(
        'Label', parent=styles['Normal'], textColor=DARK_GREY, fontSize=9, fontName='Helvetica',
    )
    rec_style = ParagraphStyle(
        'Recommendation', parent=styles['Normal'], textColor=colors.HexColor('#1f2937'),
        fontSize=9.5, fontName='Helvetica', leading=13, spaceAfter=6,
    )

    story = []

    # --- Header banner ---
    header_table = Table([[Paragraph(heading, title_style), '']], colWidths=['100%'])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('TOPPADDING', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('BOX', (0, 0), (-1, -1), 1.5, GOLD),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph('   |   '.join(meta_parts), label_style))
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width='100%', thickness=1, color=GOLD))
    story.append(Spacer(1, 0.4 * cm))

    # --- Results table ---
    col_widths = [1.5 * cm, 9.5 * cm, 2.5 * cm, 2.5 * cm]
    table_data = [['POS', labels['name'], labels['score'], labels['grade']]]
    for row in rows_data:
        score_str = str(row['score']) if row['score'] is not None else '—'
        pos_str = str(row['position']) if row['position'] != '' else '—'
        table_data.append([pos_str, row['name'], score_str, row['grade']])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    grade_styles = []
    for i, row in enumerate(rows_data, 1):
        g_color = _grade_color(row['grade'])
        grade_styles.append(('TEXTCOLOR', (3, i), (3, i), g_color))
        grade_styles.append(('FONTNAME', (3, i), (3, i), 'Helvetica-Bold'))
        if i % 2 == 0:
            grade_styles.append(('BACKGROUND', (0, i), (-1, i), LIGHT_GREY))
        if not is_passing_grade(row['grade']):
            grade_styles.append(('TEXTCOLOR', (2, i), (2, i), colors.HexColor('#b30000')))

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, GOLD),
        ('LINEBELOW', (0, 1), (-1, -1), 0.25, colors.HexColor('#cccccc')),
        ('BOX', (0, 0), (-1, -1), 1, NAVY),
    ] + grade_styles))
    story.append(table)
    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 0.3 * cm))

    # --- Footer stats ---
    footer_data = [
        [labels['total_students'], labels['passed'], labels['pass_rate'], labels['class_avg']],
        [str(stats['total']), str(stats['pass_count']), f"{stats['pass_rate']}%", f"{stats['class_avg']}"],
    ]
    footer_table = Table(footer_data, colWidths=['25%', '25%', '25%', '25%'])
    footer_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT_GOLD),
        ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('BACKGROUND', (0, 1), (-1, 1), WHITE),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 11),
        ('TEXTCOLOR', (0, 1), (-1, 1), NAVY),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, NAVY),
        ('LINEBELOW', (0, 0), (-1, 0), 1, GOLD),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
    ]))
    story.append(footer_table)
    story.append(Spacer(1, 0.5 * cm))

    # --- Grade distribution ---
    total = stats['total'] or 1
    story.append(Paragraph(labels['distribution'], section_style))
    dist_header = [g for g, _ in grade_keys]
    dist_counts = [str(stats['grade_counts'].get(g, 0)) for g, _ in grade_keys]
    dist_pcts = [f"{round(stats['grade_counts'].get(g, 0) / total * 100)}%" for g, _ in grade_keys]
    dist_table = Table([dist_header, dist_counts, dist_pcts], colWidths=[str(round(100 / len(grade_keys), 2)) + '%'] * len(grade_keys))
    dist_style = [
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#eeeeee')),
        ('BACKGROUND', (0, 1), (-1, 2), LIGHT_GREY),
    ]
    for i, (g, _) in enumerate(grade_keys):
        dist_style.append(('BACKGROUND', (i, 0), (i, 0), _grade_color(g)))
        dist_style.append(('TEXTCOLOR', (i, 0), (i, 0), WHITE))
    dist_table.setStyle(TableStyle(dist_style))
    story.append(dist_table)
    story.append(Spacer(1, 0.5 * cm))

    # --- Gender comparison (only when the data has genders) ---
    gender_stats = stats.get('gender_stats') or {}
    if gender_stats:
        story.append(Paragraph(labels['gender_comparison'], section_style))
        g_rows = [[labels['gender'], labels['count'], labels['pass_rate'], labels['average']]]
        for g, label in (('F', labels['girls']), ('M', labels['boys'])):
            gs = gender_stats.get(g)
            if gs:
                g_rows.append([label, str(gs['count']), f"{gs['pass_rate']}%", str(gs['avg'])])
        gender_table = Table(g_rows, colWidths=['25%', '25%', '25%', '25%'])
        gender_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#eeeeee')),
        ]))
        story.append(gender_table)
        story.append(Spacer(1, 0.5 * cm))

    # --- Recommendations ---
    story.append(Paragraph(labels['recommendations'], section_style))
    rec_rows = [[Paragraph(f"&bull;&nbsp;&nbsp;{text}", rec_style)] for text in recommendations]
    rec_table = Table(rec_rows, colWidths=['100%'])
    rec_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GOLD),
        ('BOX', (0, 0), (-1, -1), 1, GOLD),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(rec_table)
    story.append(Spacer(1, 0.4 * cm))

    # --- Grade key ---
    key_header = [g for g, _ in grade_keys]
    key_ranges = [f"{g} ({rng})" for g, rng in grade_keys]
    grade_key_table = Table([key_ranges], colWidths=[str(round(100 / len(grade_keys), 2)) + '%'] * len(grade_keys))
    key_style = [
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#eeeeee')),
    ]
    for i, (g, _) in enumerate(grade_keys):
        key_style.append(('TEXTCOLOR', (i, 0), (i, 0), _grade_color(g)))
    grade_key_table.setStyle(TableStyle(key_style))
    story.append(grade_key_table)

    doc.build(story)
    return response
