from collections import Counter
from datetime import datetime
from io import BytesIO

from django.http import HttpResponse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from .export_data import get_exam_export_payload


NAVY = colors.HexColor("#1F497D")       # Dark navy for headers
GOLD = colors.HexColor("#D9A441")       # Gold accent
WHITE = colors.white
LIGHT_GREY = colors.HexColor("#F2F4F7")
BLACK = colors.black
DARK_GREY = colors.HexColor("#444444")


def _get_location(exam):
    """Extract location from the exam's school, falling back to a placeholder."""
    if exam.school and exam.school.district and exam.school.region:
        return f"{exam.school.district} DISTRICT — {exam.school.region} REGION".upper()
    if exam.school and exam.school.district:
        return f"{exam.school.district} DISTRICT".upper()
    return "LOCATION UNKNOWN"


def _get_school_name(exam):
    """Extract school name from the exam."""
    if exam.school_name:
        return exam.school_name.upper()
    if exam.school:
        return exam.school.name.upper()
    return "SCHOOL NAME UNKNOWN"


def generate_results_pdf_response(exam):
    payload = get_exam_export_payload(exam)
    subjects = payload['subjects']
    all_results = payload['processed_results']
    scores_by_student_subject = payload['score_lookup']

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    left_margin = 55
    content_width = width - 2 * left_margin

    # ── Page dimensions helper ───────────────────────────────────────────
    def _write_header(p, y_start):
        """Draw the standard header block at the given y-position."""
        # Ministry line
        p.setFillColor(NAVY)
        p.setFont("Helvetica-Bold", 14)
        p.drawCentredString(width / 2, y_start, "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY")

        # Location
        p.setFont("Helvetica", 10)
        p.setFillColor(DARK_GREY)
        p.drawCentredString(width / 2, y_start - 18, _get_location(exam))

        # School name
        p.setFont("Helvetica-Bold", 11)
        p.setFillColor(BLACK)
        p.drawCentredString(width / 2, y_start - 36, _get_school_name(exam))

        # Gold separator line
        p.setStrokeColor(GOLD)
        p.setLineWidth(1.5)
        p.line(left_margin, y_start - 50, width - left_margin, y_start - 50)

        # Exam type + title
        exam_type_display = exam.get_exam_type_display().upper()
        p.setFont("Helvetica-Bold", 11)
        p.setFillColor(NAVY)
        p.drawCentredString(width / 2, y_start - 68, f"{exam_type_display} EXAMINATION RESULTS")

        # Academic year
        p.setFont("Helvetica", 10)
        p.setFillColor(DARK_GREY)
        p.drawCentredString(width / 2, y_start - 84, f"Academic Year: {exam.year}")

    def _write_section_header(p, y_start, text):
        """Write a bold section header."""
        p.setFont("Helvetica-Bold", 11)
        p.setFillColor(NAVY)
        p.drawString(left_margin, y_start, text.upper())
        p.setStrokeColor(GOLD)
        p.setLineWidth(0.75)
        p.line(left_margin, y_start - 2, width - left_margin, y_start - 2)
        return y_start - 18

    # ═══════════════════════════════════════════════════════════════════
    # PAGE 1 — SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    current_y = height - 55
    _write_header(p, current_y)
    current_y -= 110

    # ── Summary Statistics ───────────────────────────────────────────────
    current_y = _write_section_header(p, current_y, "EXAMINATION SUMMARY STATISTICS")
    current_y -= 8

    total_students = len(all_results)
    total_score_sum = sum(r.total_score for r in all_results)
    avg_score_sum = sum(float(r.average_score) for r in all_results)
    avg_total = (total_score_sum / total_students) if total_students else 0
    avg_avg = (avg_score_sum / total_students) if total_students else 0
    division_counts = Counter(r.division for r in all_results)

    def _pct(div):
        return f"{(division_counts.get(div, 0) / total_students * 100):.1f}%" if total_students else "0%"

    summary_rows = [
        ["METRIC", "VALUE", "PERCENTAGE"],
        ["Total Students", str(total_students), "100%"],
        ["Average Total Score", f"{avg_total:.1f}", "-"],
        ["Average Mean Score", f"{avg_avg:.1f}", "-"],
        ["Division I", str(division_counts.get('I', 0)), _pct('I')],
        ["Division II", str(division_counts.get('II', 0)), _pct('II')],
        ["Division III", str(division_counts.get('III', 0)), _pct('III')],
        ["Division IV", str(division_counts.get('IV', 0)), _pct('IV')],
        ["Failures (Div 0)", str(division_counts.get('0', 0)), _pct('0')],
    ]

    summary_table = Table(summary_rows, colWidths=[170, 80, 80])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    sum_width = 330
    sum_x = left_margin + (content_width - sum_width) / 2
    sum_h = len(summary_rows) * 20 + 4
    summary_table.wrapOn(p, sum_width, sum_h)
    summary_table.drawOn(p, sum_x, current_y - sum_h)
    current_y -= sum_h + 20

    # ── Top 10 / Bottom 10 ────────────────────────────────────────────────
    p.setFont("Helvetica-Bold", 10)
    p.setFillColor(NAVY)
    p.drawString(left_margin, current_y, "TOP 10 PERFORMERS")
    p.drawString(left_margin + content_width / 2 + 20, current_y, "BOTTOM 10 PERFORMERS")
    current_y -= 14

    top_10 = all_results[:10]
    top_data = [["Pos", "Student Name", "Total", "Div"]]
    for r in top_10:
        name = f"{r.student.first_name} {r.student.last_name}"
        if len(name) > 22:
            name = name[:20] + ".."
        top_data.append([str(r.position), name, str(r.total_score), r.division])

    bottom_10 = sorted(all_results, key=lambda r: r.position, reverse=True)[:10]
    bottom_data = [["Pos", "Student Name", "Total", "Div"]]
    for r in bottom_10:
        name = f"{r.student.first_name} {r.student.last_name}"
        if len(name) > 22:
            name = name[:20] + ".."
        bottom_data.append([str(r.position), name, str(r.total_score), r.division])

    half_w = (content_width - 30) / 2
    col_w_small = [28, half_w - 108, 40, 28]

    tbl_top = Table(top_data, colWidths=col_w_small)
    tbl_top.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
    ]))

    tbl_bottom = Table(bottom_data, colWidths=col_w_small)
    tbl_bottom.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
    ]))

    tbl_h = len(top_data) * 18 + 4
    tbl_top.wrapOn(p, half_w, tbl_h)
    tbl_top.drawOn(p, left_margin, current_y - tbl_h)
    tbl_bottom.wrapOn(p, half_w, tbl_h)
    tbl_bottom.drawOn(p, left_margin + half_w + 20, current_y - tbl_h)
    current_y -= tbl_h + 20

    # ── Academic Recommendations ──────────────────────────────────────────
    if current_y > 120:
        current_y = _write_section_header(p, current_y, "ACADEMIC RECOMMENDATIONS")
        current_y -= 10

        recommendations = [
            "Celebrate and recognize top performers to motivate other students.",
            "Provide intensive remedial classes for Division 0 students.",
            "Review and improve teaching methodologies for underperforming subjects.",
            "Implement peer tutoring programs for struggling students.",
            "Conduct regular progress assessments and monitoring.",
            "Organize parent-teacher conferences for academic improvement strategies.",
        ]

        p.setFont("Helvetica", 9)
        p.setFillColor(BLACK)
        for rec in recommendations:
            if current_y < 80:
                break
            p.drawString(left_margin + 10, current_y, f"\u2022  {rec}")
            current_y -= 16

    p.showPage()

    # ═══════════════════════════════════════════════════════════════════
    # PAGE 2+ — DETAILED RESULTS
    # ═══════════════════════════════════════════════════════════════════
    # Column widths for the detailed table
    col_name_w = 140
    col_small = 36
    subject_w = max(38, min(50, (content_width - (col_name_w + col_small + 3 * col_small + 170)) / max(len(subjects), 1)))

    col_widths = [col_small, col_name_w, col_small] + [subject_w] * len(subjects) + [50, 42, 36, 36]

    row_height = 18
    header_h = 42
    avail_h = height - 220
    rows_per_page = max(5, int((avail_h - header_h) / row_height))
    student_pages = [all_results[i:i + rows_per_page] for i in range(0, len(all_results), rows_per_page)]

    for page_num, students in enumerate(student_pages, 1):
        if page_num > 1:
            p.showPage()

        current_y = height - 55
        _write_header(p, current_y)
        current_y -= 100

        # Detailed results section header
        p.setFont("Helvetica-Bold", 11)
        p.setFillColor(NAVY)
        p.drawCentredString(width / 2, current_y, f"DETAILED EXAMINATION RESULTS - PAGE {page_num}")
        current_y -= 16

        # Table headers
        headers = ["POS", "STUDENT NAME", "SEX"] + [s.name[:8] for s in subjects] + ["TOTAL", "AVG", "DIV", "PTS"]
        data = [headers]

        for result in students:
            student = result.student
            student_name = f"{student.first_name} {student.last_name}"
            if len(student_name) > 25:
                student_name = student_name[:24] + "."

            row = [
                str(result.position),
                student_name,
                getattr(student, 'gender', 'N/A')[:1],
            ]

            for subj in subjects:
                score = scores_by_student_subject.get((student.id, subj.id))
                row.append(str(score) if score is not None else "-")

            row.extend([
                str(result.total_score),
                f"{result.average_score:.1f}",
                result.division,
                str(result.points),
            ])
            data.append(row)

        # Build the table
        tbl = Table(data, colWidths=col_widths)

        # Header style
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        # Alternating row backgrounds
        for i in range(1, len(data)):
            if i % 2 == 0:
                style_cmds.append(('BACKGROUND', (0, i), (-1, i), LIGHT_GREY))

        # Division column coloring (subtle)
        div_col = len(headers) - 2
        div_colors = {
            'I': ('#C6F4D6', '#145A32'),
            'II': ('#D5F5E3', '#1E8449'),
            'III': ('#FFF9C4', '#7D6608'),
            'IV': ('#FDEBD0', '#784212'),
            '0': ('#FADBD8', '#922B21'),
        }
        for i, result in enumerate(students, 1):
            d = result.division
            if d in div_colors:
                bg, fg = div_colors[d]
                style_cmds.append(('BACKGROUND', (div_col, i), (div_col, i), colors.HexColor(bg)))
                style_cmds.append(('TEXTCOLOR', (div_col, i), (div_col, i), colors.HexColor(fg)))

        tbl.setStyle(TableStyle(style_cmds))

        tbl_width = sum(col_widths)
        tbl_x = left_margin + (content_width - tbl_width) / 2
        tbl_h = len(data) * 17 + 4

        tbl.wrapOn(p, tbl_width, tbl_h)
        tbl.drawOn(p, tbl_x, current_y - tbl_h)

        # ── Footer ────────────────────────────────────────────────────────
        p.setStrokeColor(NAVY)
        p.setLineWidth(0.5)
        p.line(left_margin, 42, width - left_margin, 42)

        p.setFont("Helvetica", 7.5)
        p.setFillColor(DARK_GREY)
        p.drawCentredString(
            width / 2,
            32,
            f"Page {page_num} of {len(student_pages)} | Generated: {datetime.now().strftime('%d/%m/%Y at %H:%M')} | Academic Excellence Report",
        )

    p.save()
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{exam.name}_Professional_Results.pdf"'
    return response
