import openpyxl
from django.http import HttpResponse
from openpyxl.styles import Alignment, Font, PatternFill

from .export_data import get_exam_export_payload


def _get_excel_score_fill(score):
    if score >= 75:
        return PatternFill(start_color="a9d18e", end_color="a9d18e", fill_type="solid")
    if score >= 50:
        return None
    if score >= 40:
        return PatternFill(start_color="ffff00", end_color="ffff00", fill_type="solid")
    return PatternFill(start_color="ff0000", end_color="ff0000", fill_type="solid")


def generate_results_excel_response(exam):
    payload = get_exam_export_payload(exam)
    subjects = payload['subjects']
    results = payload['processed_results']
    score_lookup = payload['score_lookup']

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = f"{exam.name} Results"

    header = ["POS", "NAME", "SEX"] + [subj.name for subj in subjects] + ["TOTAL", "AVG", "DIV", "POINTS"]
    green_fill = PatternFill(start_color="c6f7c3", end_color="c6f7c3", fill_type="solid")
    header_font = Font(color="000000", bold=True)

    for col_num, title in enumerate(header, 1):
        cell = worksheet.cell(row=1, column=col_num, value=title)
        cell.fill = green_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    row_num = 2
    for result in results:
        student = result.student
        row = [result.position, f"{student.first_name} {student.middle_name or ''} {student.last_name}".strip(), student.gender]
        for subj in subjects:
            row.append(score_lookup.get((student.id, subj.id), "-"))
        row.extend([result.total_score, result.average_score, result.division, result.points])

        for col_num, value in enumerate(row, 1):
            cell = worksheet.cell(row=row_num, column=col_num, value=value)
            cell.alignment = Alignment(horizontal="center")

            if 4 <= col_num < 4 + len(subjects) and isinstance(value, (int, float)):
                fill = _get_excel_score_fill(value)
                if fill:
                    cell.fill = fill

            if col_num == len(header) - 2:
                if value == 'I':
                    cell.fill = PatternFill(start_color="a9d18e", end_color="a9d18e", fill_type="solid")
                elif value == '0':
                    cell.fill = PatternFill(start_color="ff0000", end_color="ff0000", fill_type="solid")
        row_num += 1

    for col in worksheet.columns:
        max_len = max(len(str(cell.value)) for cell in col if cell.value)
        worksheet.column_dimensions[col[0].column_letter].width = max_len + 2

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{exam.name}_results.xlsx"'
    workbook.save(response)
    return response
