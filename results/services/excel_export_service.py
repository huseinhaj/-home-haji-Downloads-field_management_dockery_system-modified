"""excel_export_service.py — Professional multi-sheet Excel for Tanzanian school results."""

from __future__ import annotations

import openpyxl
from django.http import HttpResponse
from openpyxl.styles import Alignment, Border, Font, GradientFill, PatternFill, Side
from openpyxl.utils import get_column_letter

from .export_data import get_exam_export_payload
from ..models import ExamResult


# ── Color palette ────────────────────────────────────────────────────────────
NAVY = "1B3A6B"
GOLD = "C9A84C"
WHITE = "FFFFFF"
LIGHT_GREY = "F2F4F7"
DARK_GREY = "444444"

# Grade fills (score → (fill hex, font hex))
def _score_fill(score) -> tuple[str | None, str | None]:
    if not isinstance(score, (int, float)):
        return None, None
    if score >= 75:
        return "C6F4D6", "145A32"  # green
    if score >= 65:
        return "D5F5E3", "1E8449"  # light green
    if score >= 50:
        return "FFF9C4", "7D6608"  # yellow
    if score >= 40:
        return "FDEBD0", "784212"  # orange
    return "FADBD8", "922B21"      # red


def _score_grade(score) -> str:
    if not isinstance(score, (int, float)):
        return '-'
    if score >= 75:
        return 'A'
    if score >= 65:
        return 'B'
    if score >= 50:
        return 'C'
    if score >= 40:
        return 'D'
    return 'F'


def _make_fill(hex_color: str) -> PatternFill:
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


def _make_border(color: str = "CCCCCC") -> Border:
    side = Side(style="thin", color=color)
    return Border(left=side, right=side, top=side, bottom=side)


def _navy_header_style(cell, *, bold: bool = True):
    cell.font = Font(color=WHITE, bold=bold, name='Calibri', size=10)
    cell.fill = _make_fill(NAVY)
    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    cell.border = _make_border(GOLD)


def _gold_header_style(cell):
    cell.font = Font(color=NAVY, bold=True, name='Calibri', size=9)
    cell.fill = _make_fill(GOLD)
    cell.alignment = Alignment(horizontal='center', vertical='center')
    cell.border = _make_border(NAVY)


def _set_auto_width(ws, min_width: int = 8, max_width: int = 35):
    for col in ws.columns:
        max_len = min_width
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value is not None:
                try:
                    cell_len = len(str(cell.value))
                    if cell_len > max_len:
                        max_len = cell_len
                except Exception:
                    pass
        ws.column_dimensions[col_letter].width = min(max_len + 3, max_width)


# ── Sheet 1: Matokeo Kamili (Full Results) ───────────────────────────────────
def _build_sheet_matokeo(wb: openpyxl.Workbook, exam, payload: dict):
    ws = wb.active
    ws.title = "Matokeo Kamili"

    subjects = payload['subjects']
    results = payload['processed_results']
    score_lookup = payload['score_lookup']

    # Title rows
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4 + len(subjects) + 4)
    title_cell = ws.cell(row=1, column=1)
    school_name = exam.school_name or 'SHULE'
    title_cell.value = f"{school_name.upper()} — MATOKEO YA {exam.get_exam_type_display().upper()} {exam.year}"
    title_cell.font = Font(bold=True, size=14, color=WHITE, name='Calibri')
    title_cell.fill = _make_fill(NAVY)
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 28

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=4 + len(subjects) + 4)
    sub_cell = ws.cell(row=2, column=1)
    sub_cell.value = f"Fomu {exam.form}   |   {exam.name}   |   Mwaka {exam.year}"
    sub_cell.font = Font(bold=False, size=10, color=GOLD, name='Calibri')
    sub_cell.fill = _make_fill(NAVY)
    sub_cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[2].height = 18

    # Header row
    header_row = 3
    headers = ["POS", "JINA", "JINSIA"] + [s.name.upper() for s in subjects] + ["JUMLA", "WASTANI", "DARASA", "POINTI"]
    for col_idx, title in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=title)
        _navy_header_style(cell)
    ws.row_dimensions[header_row].height = 22

    # Freeze panes
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    # Data rows
    subject_start_col = 4  # columns 1-3 = POS, JINA, JINSIA
    for row_idx, result in enumerate(results):
        data_row = header_row + 1 + row_idx
        student = result.student
        full_name = ' '.join(
            part for part in [student.first_name, student.middle_name or '', student.last_name] if part
        ).strip()

        # Base data
        ws.cell(row=data_row, column=1, value=result.position)
        ws.cell(row=data_row, column=2, value=full_name)
        ws.cell(row=data_row, column=3, value=student.gender)

        # Alternating fill
        row_fill = _make_fill(LIGHT_GREY) if row_idx % 2 == 0 else None

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=data_row, column=col_idx)
            cell.font = Font(name='Calibri', size=9)
            cell.border = _make_border()
            cell.alignment = Alignment(horizontal='center', vertical='center')
            if row_fill and col_idx not in (2,):
                cell.fill = row_fill
            if col_idx == 2:
                cell.alignment = Alignment(horizontal='left', vertical='center')

        # Subject scores (columns 4 … 3+len(subjects))
        for sub_col_offset, subject in enumerate(subjects):
            score = score_lookup.get((student.id, subject.id))
            col_idx = subject_start_col + sub_col_offset
            cell = ws.cell(row=data_row, column=col_idx)
            if score is not None:
                cell.value = score
                fill_hex, font_hex = _score_fill(score)
                if fill_hex:
                    cell.fill = _make_fill(fill_hex)
                if font_hex:
                    cell.font = Font(color=font_hex, bold=True, name='Calibri', size=9)
            else:
                cell.value = '-'

        # Totals columns
        total_col = subject_start_col + len(subjects)
        avg_col = total_col + 1
        div_col = avg_col + 1
        pts_col = div_col + 1

        total_cell = ws.cell(row=data_row, column=total_col, value=result.total_score)
        total_cell.font = Font(bold=True, name='Calibri', size=9, color=NAVY)

        avg_cell = ws.cell(row=data_row, column=avg_col, value=float(result.average_score))
        avg_cell.number_format = '0.00'
        avg_cell.font = Font(bold=True, name='Calibri', size=9)

        div_cell = ws.cell(row=data_row, column=div_col, value=result.division)
        if result.division == 'I':
            div_cell.fill = _make_fill("C6F4D6")
            div_cell.font = Font(bold=True, name='Calibri', size=9, color="145A32")
        elif result.division in ('II', 'III'):
            div_cell.fill = _make_fill("FFF9C4")
            div_cell.font = Font(bold=True, name='Calibri', size=9, color="7D6608")
        elif result.division in ('IV', '0'):
            div_cell.fill = _make_fill("FADBD8")
            div_cell.font = Font(bold=True, name='Calibri', size=9, color="922B21")

        ws.cell(row=data_row, column=pts_col, value=result.points)

    # Grade color legend row at bottom
    last_data_row = header_row + len(results) + 1
    legend_row = last_data_row + 2
    legend_labels = [
        ("A  (75-100)", "C6F4D6", "145A32"),
        ("B  (65-74)", "D5F5E3", "1E8449"),
        ("C  (50-64)", "FFF9C4", "7D6608"),
        ("D  (40-49)", "FDEBD0", "784212"),
        ("F  (<40)", "FADBD8", "922B21"),
    ]
    ws.cell(row=legend_row, column=1, value="UFUNGUO WA DARAJA:")
    ws.cell(row=legend_row, column=1).font = Font(bold=True, name='Calibri', size=8, color=NAVY)
    for i, (label, bg, fg) in enumerate(legend_labels):
        cell = ws.cell(row=legend_row, column=2 + i, value=label)
        cell.fill = _make_fill(bg)
        cell.font = Font(bold=True, name='Calibri', size=8, color=fg)
        cell.alignment = Alignment(horizontal='center')
        cell.border = _make_border()

    _set_auto_width(ws)
    # Make name column wider
    ws.column_dimensions['B'].width = 28


# ── Sheet 2: Muhtasari (Summary) ─────────────────────────────────────────────
def _build_sheet_muhtasari(wb: openpyxl.Workbook, exam, payload: dict):
    ws = wb.create_sheet(title="Muhtasari")

    subjects = payload['subjects']
    results = payload['processed_results']
    score_lookup = payload['score_lookup']

    def _write_section_header(row, title):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        cell = ws.cell(row=row, column=1, value=title)
        cell.font = Font(bold=True, size=10, color=WHITE, name='Calibri')
        cell.fill = _make_fill(NAVY)
        cell.alignment = Alignment(horizontal='left', vertical='center')
        cell.border = _make_border(GOLD)
        ws.row_dimensions[row].height = 18

    def _write_kv(row, key, val):
        k_cell = ws.cell(row=row, column=1, value=key)
        k_cell.font = Font(bold=True, name='Calibri', size=9, color=DARK_GREY)
        k_cell.fill = _make_fill(LIGHT_GREY)
        k_cell.border = _make_border()
        v_cell = ws.cell(row=row, column=2, value=val)
        v_cell.font = Font(name='Calibri', size=9)
        v_cell.border = _make_border()

    cur_row = 1

    # Exam details
    _write_section_header(cur_row, "MAELEZO YA MTIHANI")
    cur_row += 1
    _write_kv(cur_row, "Jina la Mtihani", exam.name)
    cur_row += 1
    _write_kv(cur_row, "Aina ya Mtihani", exam.get_exam_type_display())
    cur_row += 1
    _write_kv(cur_row, "Mwaka", exam.year)
    cur_row += 1
    _write_kv(cur_row, "Fomu", f"Fomu {exam.form}")
    cur_row += 1
    if exam.school_name:
        _write_kv(cur_row, "Shule", exam.school_name)
        cur_row += 1
    _write_kv(cur_row, "Jumla ya Wanafunzi", len(results))
    cur_row += 2

    # Division breakdown
    _write_section_header(cur_row, "MGAWANYO WA DARAJA")
    cur_row += 1
    div_headers = ["DARAJA", "IDADI", "ASILIMIA"]
    for col_idx, h in enumerate(div_headers, 1):
        cell = ws.cell(row=cur_row, column=col_idx, value=h)
        _gold_header_style(cell)
    cur_row += 1

    div_counts = {'I': 0, 'II': 0, 'III': 0, 'IV': 0, '0': 0}
    for r in results:
        div_counts[r.division] = div_counts.get(r.division, 0) + 1

    total_students = len(results) or 1
    for div in ['I', 'II', 'III', 'IV', '0']:
        count = div_counts.get(div, 0)
        pct = round(count / total_students * 100, 1)
        ws.cell(row=cur_row, column=1, value=f"Daraja {div}").border = _make_border()
        ws.cell(row=cur_row, column=2, value=count).border = _make_border()
        ws.cell(row=cur_row, column=3, value=f"{pct}%").border = _make_border()
        for col_idx in range(1, 4):
            ws.cell(row=cur_row, column=col_idx).font = Font(name='Calibri', size=9)
            ws.cell(row=cur_row, column=col_idx).alignment = Alignment(horizontal='center')
        cur_row += 1
    cur_row += 1

    # Per-subject statistics
    _write_section_header(cur_row, "TAKWIMU ZA MASOMO")
    cur_row += 1
    sub_headers = ["SOMO", "WASTANI", "JUU ZAIDI", "CHINI ZAIDI", "ASILIMIA KUFAULU"]
    for col_idx, h in enumerate(sub_headers, 1):
        cell = ws.cell(row=cur_row, column=col_idx, value=h)
        _gold_header_style(cell)
    cur_row += 1

    for subject in subjects:
        scores = [
            score_lookup[(r.student_id, subject.id)]
            for r in results
            if (r.student_id, subject.id) in score_lookup
        ]
        if not scores:
            continue
        avg = round(sum(scores) / len(scores), 1)
        highest = max(scores)
        lowest = min(scores)
        passing = sum(1 for s in scores if s >= 40)
        pass_pct = round(passing / len(scores) * 100, 1)

        ws.cell(row=cur_row, column=1, value=subject.name)
        ws.cell(row=cur_row, column=2, value=avg)
        ws.cell(row=cur_row, column=3, value=highest)
        ws.cell(row=cur_row, column=4, value=lowest)
        ws.cell(row=cur_row, column=5, value=f"{pass_pct}%")

        for col_idx in range(1, 6):
            cell = ws.cell(row=cur_row, column=col_idx)
            cell.font = Font(name='Calibri', size=9)
            cell.border = _make_border()
            cell.alignment = Alignment(horizontal='center')
        ws.cell(row=cur_row, column=1).alignment = Alignment(horizontal='left')
        cur_row += 1
    cur_row += 1

    # Top 5 students
    _write_section_header(cur_row, "WANAFUNZI BORA 5")
    cur_row += 1
    top_headers = ["NAFASI", "JINA", "JUMLA", "WASTANI", "DARAJA"]
    for col_idx, h in enumerate(top_headers, 1):
        cell = ws.cell(row=cur_row, column=col_idx, value=h)
        _gold_header_style(cell)
    cur_row += 1

    for result in results[:5]:
        student = result.student
        full_name = ' '.join(
            part for part in [student.first_name, student.middle_name or '', student.last_name] if part
        ).strip()
        ws.cell(row=cur_row, column=1, value=result.position)
        ws.cell(row=cur_row, column=2, value=full_name)
        ws.cell(row=cur_row, column=3, value=result.total_score)
        ws.cell(row=cur_row, column=4, value=float(result.average_score))
        ws.cell(row=cur_row, column=5, value=result.division)
        for col_idx in range(1, 6):
            cell = ws.cell(row=cur_row, column=col_idx)
            cell.font = Font(name='Calibri', size=9)
            cell.border = _make_border()
            cell.alignment = Alignment(horizontal='center')
        ws.cell(row=cur_row, column=2).alignment = Alignment(horizontal='left')
        cur_row += 1

    _set_auto_width(ws)
    ws.column_dimensions['B'].width = 28


# ── Sheet 3: Somo kwa Somo (Subject Analysis) ────────────────────────────────
def _build_sheet_somo_kwa_somo(wb: openpyxl.Workbook, exam, payload: dict):
    ws = wb.create_sheet(title="Somo kwa Somo")

    subjects = payload['subjects']
    results = payload['processed_results']
    score_lookup = payload['score_lookup']

    cur_row = 1

    # Title
    ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=5)
    title_cell = ws.cell(row=cur_row, column=1, value="UCHAMBUZI WA MASOMO")
    title_cell.font = Font(bold=True, size=12, color=WHITE, name='Calibri')
    title_cell.fill = _make_fill(NAVY)
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[cur_row].height = 22
    cur_row += 2

    for subject in subjects:
        # Subject header
        ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=4)
        subj_cell = ws.cell(row=cur_row, column=1, value=subject.name.upper())
        subj_cell.font = Font(bold=True, size=10, color=WHITE, name='Calibri')
        subj_cell.fill = _make_fill(NAVY)
        subj_cell.alignment = Alignment(horizontal='left', vertical='center')
        subj_cell.border = _make_border(GOLD)
        ws.row_dimensions[cur_row].height = 18
        cur_row += 1

        # Column headers
        col_headers = ["NAFASI", "JINA", "ALAMA", "DARAJA"]
        for col_idx, h in enumerate(col_headers, 1):
            cell = ws.cell(row=cur_row, column=col_idx, value=h)
            _gold_header_style(cell)
        cur_row += 1

        # Collect and sort by score
        subject_rows = []
        for result in results:
            score = score_lookup.get((result.student_id, subject.id))
            if score is None:
                continue
            student = result.student
            full_name = ' '.join(
                part for part in [student.first_name, student.middle_name or '', student.last_name] if part
            ).strip()
            subject_rows.append({'name': full_name, 'score': score})

        subject_rows.sort(key=lambda r: r['score'], reverse=True)

        for rank, row in enumerate(subject_rows, 1):
            grade = _score_grade(row['score'])
            fill_hex, font_hex = _score_fill(row['score'])

            ws.cell(row=cur_row, column=1, value=rank)
            ws.cell(row=cur_row, column=2, value=row['name'])
            score_cell = ws.cell(row=cur_row, column=3, value=row['score'])
            grade_cell = ws.cell(row=cur_row, column=4, value=grade)

            if fill_hex:
                score_cell.fill = _make_fill(fill_hex)
                grade_cell.fill = _make_fill(fill_hex)
            if font_hex:
                score_cell.font = Font(bold=True, name='Calibri', size=9, color=font_hex)
                grade_cell.font = Font(bold=True, name='Calibri', size=9, color=font_hex)

            for col_idx in range(1, 5):
                cell = ws.cell(row=cur_row, column=col_idx)
                cell.border = _make_border()
                cell.alignment = Alignment(horizontal='center')
                if col_idx != 3 and col_idx != 4:
                    if not cell.font or not cell.font.bold:
                        cell.font = Font(name='Calibri', size=9)
            ws.cell(row=cur_row, column=2).alignment = Alignment(horizontal='left')
            cur_row += 1

        cur_row += 1  # gap between subjects

    _set_auto_width(ws)
    ws.column_dimensions['B'].width = 28


# ── Public API ────────────────────────────────────────────────────────────────
def generate_professional_excel_response(exam) -> HttpResponse:
    """Generate a 3-sheet professional Excel for the given exam."""
    payload = get_exam_export_payload(exam)

    wb = openpyxl.Workbook()
    _build_sheet_matokeo(wb, exam, payload)
    _build_sheet_muhtasari(wb, exam, payload)
    _build_sheet_somo_kwa_somo(wb, exam, payload)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    safe_name = exam.name.replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename="{safe_name}_{exam.year}_matokeo.xlsx"'
    wb.save(response)
    return response


# Backward-compat alias used by old views
def generate_results_excel_response(exam) -> HttpResponse:
    """Legacy alias — now returns the professional multi-sheet Excel."""
    return generate_professional_excel_response(exam)
