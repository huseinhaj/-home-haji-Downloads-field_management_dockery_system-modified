"""subject_pdf_service.py — Generate a per-subject PDF for one exam subject."""

from __future__ import annotations

from django.http import HttpResponse

from ..models import ExamResult

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


# Grade thresholds
def _score_to_grade(score: int) -> str:
    if score >= 75:
        return 'A'
    if score >= 65:
        return 'B'
    if score >= 50:
        return 'C'
    if score >= 40:
        return 'D'
    return 'F'


def _grade_color(grade: str):
    """Return a reportlab color for the grade."""
    palette = {
        'A': colors.HexColor('#1a7a3b'),
        'B': colors.HexColor('#2d7d46'),
        'C': colors.HexColor('#8a6f00'),
        'D': colors.HexColor('#b35c00'),
        'F': colors.HexColor('#b30000'),
    }
    return palette.get(grade, colors.black)


NAVY = colors.HexColor('#1B3A6B')
GOLD = colors.HexColor('#C9A84C')
LIGHT_GOLD = colors.HexColor('#F5EDD6')
WHITE = colors.white
LIGHT_GREY = colors.HexColor('#F0F2F5')
DARK_GREY = colors.HexColor('#444444')
PASS_SCORE = 40


def generate_subject_pdf_response(exam, subject, teacher_name: str = '') -> HttpResponse:
    """Generate a clean A4 PDF for ONE subject with position, name, score, grade."""

    # Gather results for this subject
    results = list(
        ExamResult.objects.filter(exam=exam, subject=subject)
        .select_related('student')
        .order_by('-score', 'student__first_name')
    )

    # Sort by score descending and assign position
    results.sort(key=lambda r: r.score, reverse=True)
    rows_data = []
    for pos, result in enumerate(results, 1):
        student = result.student
        full_name = ' '.join(
            part for part in [student.first_name, student.middle_name, student.last_name] if part
        )
        grade = _score_to_grade(result.score)
        rows_data.append({
            'position': pos,
            'name': full_name,
            'score': result.score,
            'grade': grade,
        })

    total_students = len(rows_data)
    pass_count = sum(1 for r in rows_data if r['score'] >= PASS_SCORE)
    pass_rate = round((pass_count / total_students * 100), 1) if total_students else 0
    class_avg = round(sum(r['score'] for r in rows_data) / total_students, 1) if total_students else 0

    # Build PDF
    response = HttpResponse(content_type='application/pdf')
    safe_subject = subject.name.replace(' ', '_').replace('/', '-')
    response['Content-Disposition'] = f'attachment; filename="{safe_subject}_{exam.id}_results.pdf"'

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
        'SubjectTitle',
        parent=styles['Heading1'],
        textColor=WHITE,
        fontSize=16,
        fontName='Helvetica-Bold',
        spaceAfter=0,
        spaceBefore=0,
        leading=20,
    )
    subtitle_style = ParagraphStyle(
        'SubjectSubtitle',
        parent=styles['Normal'],
        textColor=LIGHT_GOLD,
        fontSize=10,
        fontName='Helvetica',
        spaceAfter=0,
        spaceBefore=4,
    )
    label_style = ParagraphStyle(
        'Label',
        parent=styles['Normal'],
        textColor=DARK_GREY,
        fontSize=9,
        fontName='Helvetica',
    )
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        textColor=DARK_GREY,
        fontSize=8,
        fontName='Helvetica',
        alignment=1,
    )

    story = []

    # --- Header banner ---
    school_line = exam.school_name if exam.school_name else ''
    exam_line = str(exam)
    teacher_line = f"Teacher: {teacher_name}" if teacher_name else ''

    header_table_data = [[
        Paragraph(subject.name.upper(), title_style),
        '',
    ]]
    header_table = Table(header_table_data, colWidths=['100%'])
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

    # Meta info row
    meta_parts = []
    if school_line:
        meta_parts.append(school_line)
    meta_parts.append(exam_line)
    if teacher_line:
        meta_parts.append(teacher_line)

    meta_text = '   |   '.join(meta_parts)
    story.append(Paragraph(meta_text, label_style))
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width='100%', thickness=1, color=GOLD))
    story.append(Spacer(1, 0.4 * cm))

    # --- Results table ---
    col_widths = [1.5 * cm, 9.5 * cm, 2.5 * cm, 2.5 * cm]

    table_data = [['POS', 'JINA LA MWANAFUNZI', 'ALAMA', 'DARAJA']]
    for row in rows_data:
        table_data.append([
            str(row['position']),
            row['name'],
            str(row['score']),
            row['grade'],
        ])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    # Build grade-specific cell colors for the grade column
    grade_styles = []
    for i, row in enumerate(rows_data, 1):  # row 0 is header
        grade = row['grade']
        g_color = _grade_color(grade)
        grade_styles.append(('TEXTCOLOR', (3, i), (3, i), g_color))
        grade_styles.append(('FONTNAME', (3, i), (3, i), 'Helvetica-Bold'))
        # Alternating row fill
        if i % 2 == 0:
            grade_styles.append(('BACKGROUND', (0, i), (-1, i), LIGHT_GREY))
        # Highlight failing rows
        if row['score'] < PASS_SCORE:
            grade_styles.append(('TEXTCOLOR', (2, i), (2, i), colors.HexColor('#b30000')))

    table_style = TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        # Alignment
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),   # POS
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),      # NAME
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),    # SCORE
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),    # GRADE
        # Grid
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, GOLD),
        ('LINEBELOW', (0, 1), (-1, -1), 0.25, colors.HexColor('#cccccc')),
        ('BOX', (0, 0), (-1, -1), 1, NAVY),
    ] + grade_styles)

    table.setStyle(table_style)
    story.append(table)
    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 0.3 * cm))

    # --- Footer stats ---
    footer_data = [
        ['JUMLA YA WANAFUNZI', 'WALIOFAULU', 'ASILIMIA KUFAULU', 'WASTANI WA DARASA'],
        [str(total_students), str(pass_count), f"{pass_rate}%", f"{class_avg}"],
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
    story.append(Spacer(1, 0.4 * cm))

    # Grade key
    grade_key_data = [['DARAJA', 'A (75-100)', 'B (65-74)', 'C (50-64)', 'D (40-49)', 'F (0-39)']]
    grade_key_table = Table(grade_key_data, colWidths=[2.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm])
    grade_key_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (0, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TEXTCOLOR', (1, 0), (1, 0), colors.HexColor('#1a7a3b')),
        ('TEXTCOLOR', (2, 0), (2, 0), colors.HexColor('#2d7d46')),
        ('TEXTCOLOR', (3, 0), (3, 0), colors.HexColor('#8a6f00')),
        ('TEXTCOLOR', (4, 0), (4, 0), colors.HexColor('#b35c00')),
        ('TEXTCOLOR', (5, 0), (5, 0), colors.HexColor('#b30000')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#eeeeee')),
    ]))
    story.append(grade_key_table)

    doc.build(story)
    return response
