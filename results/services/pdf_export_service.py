from collections import Counter
from datetime import datetime
from io import BytesIO

from django.http import HttpResponse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from .export_data import get_exam_export_payload


def _get_score_color(score):
    if score >= 75:
        return colors.HexColor("#4CAF50")
    if score >= 65:
        return colors.HexColor("#8BC34A")
    if score >= 50:
        return colors.HexColor("#FFC107")
    if score >= 40:
        return colors.HexColor("#FF9800")
    return colors.HexColor("#F44336")


def generate_results_pdf_response(exam):
    payload = get_exam_export_payload(exam)
    subjects = payload['subjects']
    all_results = payload['processed_results']
    scores_by_student_subject = payload['score_lookup']

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    primary_color = colors.HexColor("#1565C0")
    secondary_color = colors.HexColor("#E3F2FD")
    accent_color = colors.HexColor("#FF6F00")
    success_color = colors.HexColor("#2E7D32")
    danger_color = colors.HexColor("#C62828")

    left_margin = 50
    content_width = width - 100

    def draw_decorative_border():
        p.setStrokeColor(primary_color)
        p.setLineWidth(3)
        p.rect(20, 20, width - 40, height - 40)

        p.setStrokeColor(secondary_color)
        p.setLineWidth(1)
        p.rect(25, 25, width - 50, height - 50)

        corner_size = 15
        p.setFillColor(accent_color)
        p.circle(35, height - 35, corner_size / 2, fill=1)
        p.circle(width - 35, height - 35, corner_size / 2, fill=1)
        p.circle(35, 35, corner_size / 2, fill=1)
        p.circle(width - 35, 35, corner_size / 2, fill=1)

    def draw_header():
        draw_decorative_border()
        p.setFillColor(primary_color)
        p.rect(left_margin, height - 150, content_width, 100, fill=1)

        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 16)
        p.drawCentredString(width / 2, height - 70, "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY")

        p.setFont("Helvetica-Bold", 14)
        p.drawCentredString(width / 2, height - 90, getattr(exam, 'location', 'LOCATION UNKNOWN').upper())

        p.setFont("Helvetica-Bold", 12)
        p.drawCentredString(width / 2, height - 110, getattr(exam, 'school_name', 'SCHOOL NAME UNKNOWN').upper())

        p.setFillColor(accent_color)
        p.rect(left_margin, height - 180, content_width, 25, fill=1)

        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 12)
        p.drawCentredString(width / 2, height - 172, f"{exam.name.upper()} EXAMINATION RESULTS")

        p.setFillColor(colors.black)
        p.setFont("Helvetica", 10)
        p.drawCentredString(width / 2, height - 195, f"Academic Year: {getattr(exam, 'year', 'YEAR UNKNOWN')}")

    draw_header()
    current_y = height - 220

    p.setFillColor(success_color)
    p.rect(left_margin, current_y - 25, content_width, 25, fill=1)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(left_margin + 10, current_y - 18, "Exam Summary Statistics")
    current_y -= 40

    total_students = len(all_results)
    total_score_sum = sum(r.total_score for r in all_results)
    avg_score_sum = sum(float(r.average_score) for r in all_results)
    avg_total = (total_score_sum / total_students) if total_students else 0
    avg_avg = (avg_score_sum / total_students) if total_students else 0
    division_counts = Counter(r.division for r in all_results)

    summary_data = [
        ["METRIC", "VALUE", "PERCENTAGE"],
        ["Total Students", str(total_students), "100%"],
        ["Average Total Score", f"{avg_total:.1f}", "-"],
        ["Average Mean Score", f"{avg_avg:.1f}", "-"],
        ["Division I", str(division_counts['I']), f"{(division_counts['I']/total_students*100):.1f}%" if total_students else "0%"],
        ["Division II", str(division_counts['II']), f"{(division_counts['II']/total_students*100):.1f}%" if total_students else "0%"],
        ["Division III", str(division_counts['III']), f"{(division_counts['III']/total_students*100):.1f}%" if total_students else "0%"],
        ["Division IV", str(division_counts['IV']), f"{(division_counts['IV']/total_students*100):.1f}%" if total_students else "0%"],
        ["Failures (Div 0)", str(division_counts['0']), f"{(division_counts['0']/total_students*100):.1f}%" if total_students else "0%"],
    ]

    summary_table = Table(summary_data, colWidths=[150, 80, 80])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, secondary_color]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    summary_table.wrapOn(p, content_width, height)
    table_height = len(summary_data) * 20
    summary_table.drawOn(p, left_margin + (content_width - 310) / 2, current_y - table_height)
    current_y -= table_height + 30

    p.setFillColor(success_color)
    p.rect(left_margin, current_y - 25, content_width / 2 - 10, 25, fill=1)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(left_margin + 10, current_y - 18, "TOP 10 PERFORMERS")

    p.setFillColor(danger_color)
    p.rect(left_margin + content_width / 2 + 10, current_y - 25, content_width / 2 - 10, 25, fill=1)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(left_margin + content_width / 2 + 20, current_y - 18, "BOTTOM 10 PERFORMERS")
    current_y -= 40

    top_10 = all_results[:10]
    top_data = [["Pos", "Student Name", "Total", "Div"]]
    for result in top_10:
        student_name = f"{result.student.first_name} {result.student.last_name}"
        if len(student_name) > 20:
            student_name = student_name[:20] + "..."
        top_data.append([str(result.position), student_name, str(result.total_score), result.division])

    top_table = Table(top_data, colWidths=[30, 120, 50, 30])
    top_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), success_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#E8F5E8")]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    bottom_10 = sorted(all_results, key=lambda r: r.position, reverse=True)[:10]
    bottom_data = [["Pos", "Student Name", "Total", "Div"]]
    for result in bottom_10:
        student_name = f"{result.student.first_name} {result.student.last_name}"
        if len(student_name) > 20:
            student_name = student_name[:20] + "..."
        bottom_data.append([str(result.position), student_name, str(result.total_score), result.division])

    bottom_table = Table(bottom_data, colWidths=[30, 120, 50, 30])
    bottom_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), danger_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#FFE8E8")]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    table_height = len(top_data) * 18
    top_table.wrapOn(p, content_width / 2, height)
    top_table.drawOn(p, left_margin, current_y - table_height)

    bottom_table.wrapOn(p, content_width / 2, height)
    bottom_table.drawOn(p, left_margin + content_width / 2 + 20, current_y - table_height)
    current_y -= table_height + 30

    p.setFillColor(accent_color)
    p.rect(left_margin, current_y - 25, content_width, 25, fill=1)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(left_margin + 10, current_y - 18, "ACADEMIC RECOMMENDATIONS")
    current_y -= 40

    recommendations = [
        "- Celebrate and recognize top performers to motivate other students",
        "- Provide intensive remedial classes for Division 0 students",
        "- Review and improve teaching methodologies for underperforming subjects",
        "- Implement peer tutoring programs for struggling students",
        "- Conduct regular progress assessments and monitoring",
        "- Organize parent-teacher conferences for academic improvement strategies",
    ]

    p.setFillColor(colors.black)
    p.setFont("Helvetica", 10)
    for recommendation in recommendations:
        if current_y < 100:
            break
        p.drawString(left_margin + 20, current_y, recommendation)
        current_y -= 20

    p.showPage()

    available_width = content_width - 40
    fixed_cols_width = 40 + 150 + 30
    summary_cols_width = 50 + 40 + 30 + 40
    subject_width = (available_width - fixed_cols_width - summary_cols_width) / len(subjects) if subjects else 40
    subject_width = max(35, min(50, subject_width))

    col_widths = [40, 150, 30] + [subject_width] * len(subjects) + [50, 40, 30, 40]

    row_height = 20
    header_height = 40
    available_height = height - 250
    rows_per_page = int((available_height - header_height) / row_height)
    student_pages = [all_results[i:i + rows_per_page] for i in range(0, len(all_results), rows_per_page)]

    for page_num, students in enumerate(student_pages, 1):
        if page_num > 1:
            p.showPage()

        draw_header()

        p.setFillColor(primary_color)
        p.rect(left_margin, height - 210, content_width, 25, fill=1)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 12)
        p.drawCentredString(width / 2, height - 202, f"DETAILED EXAMINATION RESULTS - PAGE {page_num}")

        current_y = height - 250

        header = ["POS", "STUDENT NAME", "SEX"] + [subj.name[:8] for subj in subjects] + ["TOTAL", "AVG", "DIV", "PTS"]
        data = [header]

        for result in students:
            student = result.student
            student_name = f"{student.first_name} {student.last_name}"
            if len(student_name) > 25:
                student_name = student_name[:25] + "..."

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

        table = Table(data, colWidths=col_widths)
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), primary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, secondary_color]),
        ])

        for row_index, result in enumerate(students, start=1):
            for subject_offset in range(len(subjects)):
                col_idx = 3 + subject_offset
                if col_idx < len(data[row_index]):
                    score_str = data[row_index][col_idx]
                    if score_str != "-":
                        try:
                            score = int(score_str)
                            color = _get_score_color(score)
                            style.add('BACKGROUND', (col_idx, row_index), (col_idx, row_index), color)
                            if score < 50:
                                style.add('TEXTCOLOR', (col_idx, row_index), (col_idx, row_index), colors.white)
                        except ValueError:
                            continue

            div_col = len(header) - 2
            div_colors = {
                'I': colors.HexColor("#4CAF50"),
                'II': colors.HexColor("#8BC34A"),
                'III': colors.HexColor("#FFC107"),
                'IV': colors.HexColor("#FF9800"),
                '0': colors.HexColor("#F44336"),
            }
            if result.division in div_colors:
                style.add('BACKGROUND', (div_col, row_index), (div_col, row_index), div_colors[result.division])
                if result.division in ['IV', '0']:
                    style.add('TEXTCOLOR', (div_col, row_index), (div_col, row_index), colors.white)

        table.setStyle(style)

        table_width = sum(col_widths)
        table_x = left_margin + (content_width - table_width) / 2

        table.wrapOn(p, content_width, available_height)
        table.drawOn(p, table_x, current_y - len(data) * row_height)

        p.setFillColor(primary_color)
        p.rect(left_margin, 30, content_width, 20, fill=1)
        p.setFillColor(colors.white)
        p.setFont("Helvetica", 8)
        p.drawCentredString(
            width / 2,
            37,
            f"Page {page_num} of {len(student_pages)} | Generated: {datetime.now().strftime('%d/%m/%Y at %H:%M')} | Academic Excellence Report",
        )

    p.save()
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{exam.name}_Professional_Results.pdf"'
    return response
