"""
pdf_export_service.py — Professional academic report PDF
=======================================================

Produces a multi-page PDF that any head teacher can understand:

  Page 1   MUHTASARI (Summary)
           - Ministry header, school info
           - Division breakdown with percentages
           - Per-subject statistics (average, highest, lowest, pass rate)
           - Top 5 students

  Page 2+  MATOKEO KAMILI (Full Results)
           - Full results table (POS, JINA, JINSIA, subjects, JUMLA,
             WASTANI, DARAJA, POINTI)
           - Score color-coding (green→yellow→red)
           - Grade legend
           - Footer with page numbers

Excel export (3-sheet) is untouched — both PDF and Excel coexist.
"""

from collections import Counter
from datetime import datetime
from io import BytesIO

from django.http import HttpResponse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from .export_data import get_exam_export_payload


# ── Colour palette ───────────────────────────────────────────────────────────
NAVY    = colors.HexColor("#1F497D")
GOLD     = colors.HexColor("#D9A441")
WHITE    = colors.white
LIGHT_GREY = colors.HexColor("#F2F4F7")
BLACK    = colors.black
DARK_GREY  = colors.HexColor("#555555")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_location(exam):
    if exam.school and exam.school.district and exam.school.region:
        return f"{exam.school.district} DISTRICT — {exam.school.region} REGION".upper()
    if exam.school and exam.school.district:
        return f"{exam.school.district} DISTRICT".upper()
    return "LOCATION UNKNOWN"


def _get_school_name(exam):
    if exam.school_name:
        return exam.school_name.upper()
    if exam.school:
        return exam.school.name.upper()
    return "SCHOOL NAME UNKNOWN"


def _score_fill(score):
    """Return (background-hex, font-hex) for a score value."""
    if score is None or not isinstance(score, (int, float)):
        return None, None
    if score >= 75:  return "#C6F4D6", "#145A32"
    if score >= 65:  return "#D5F5E3", "#1E8449"
    if score >= 50:  return "#FFF9C4", "#7D6608"
    if score >= 40:  return "#FDEBD0", "#784212"
    return "#FADBD8", "#922B21"


def _make_style(*cmds):
    """Shortcut — wrap a list of TableStyle commands."""
    return TableStyle(list(cmds))

DIV_PALETTE = {
    'I':  ('#C6F4D6', '#145A32'),
    'II': ('#D5F5E3', '#1E8449'),
    'III':('#FFF9C4', '#7D6608'),
    'IV': ('#FDEBD0', '#784212'),
    '0':  ('#FADBD8', '#922B21'),
}


# ═════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═════════════════════════════════════════════════════════════════════════════

def generate_results_pdf_response(exam):
    """Return an HttpResponse containing the professional academic-report PDF."""
    payload = get_exam_export_payload(exam)
    subjects = payload['subjects']
    all_results = payload['processed_results']
    score_lookup = payload['score_lookup']

    buf = BytesIO()
    p = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    LM = 50          # left margin
    CW = W - 2 * LM  # content width

    total_students = len(all_results)

    # ── Summary stats pre-computed --------------------------------------
    if total_students:
        total_sum  = sum(r.total_score for r in all_results)
        avg_sum    = sum(float(r.average_score) for r in all_results)
        avg_total  = total_sum / total_students
        avg_avg    = avg_sum   / total_students
        div_counts = Counter(r.division for r in all_results)
    else:
        avg_total = avg_avg = 0
        div_counts = Counter()

    def _pct(n):
        return f"{(n / total_students * 100):.1f}%" if total_students else "0%"

    # Per-subject stats
    subj_stats = []
    for subj in subjects:
        scores = [score_lookup[(r.student_id, subj.id)]
                  for r in all_results if (r.student_id, subj.id) in score_lookup]
        if scores:
            passing = sum(1 for s in scores if s >= 40)
            subj_stats.append({
                'name': subj.name,
                'avg':  round(sum(scores) / len(scores), 1),
                'max':  max(scores),
                'min':  min(scores),
                'pass_pct': round(passing / len(scores) * 100, 1),
            })

    # ── Helper: draw the Ministry header block ───────────────────────────
    def _draw_header(y):
        p.setFillColor(NAVY)
        p.setFont("Helvetica-Bold", 14)
        p.drawCentredString(W / 2, y, "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY")

        p.setFont("Helvetica", 10)
        p.setFillColor(DARK_GREY)
        p.drawCentredString(W / 2, y - 18, _get_location(exam))

        p.setFont("Helvetica-Bold", 11)
        p.setFillColor(BLACK)
        p.drawCentredString(W / 2, y - 36, _get_school_name(exam))

        p.setStrokeColor(GOLD)
        p.setLineWidth(1.5)
        p.line(LM, y - 50, W - LM, y - 50)

        etype = exam.get_exam_type_display().upper()
        p.setFont("Helvetica-Bold", 11)
        p.setFillColor(NAVY)
        p.drawCentredString(W / 2, y - 68, f"{etype} EXAMINATION RESULTS")

        p.setFont("Helvetica", 10)
        p.setFillColor(DARK_GREY)
        p.drawCentredString(W / 2, y - 84, f"Academic Year: {exam.year}")

    # ── Helper: section heading line ─────────────────────────────────────
    def _section_heading(y, text):
        p.setFont("Helvetica-Bold", 12)
        p.setFillColor(NAVY)
        p.drawString(LM, y, text.upper())
        p.setStrokeColor(GOLD)
        p.setLineWidth(1)
        p.line(LM, y - 2, W - LM, y - 2)
        return y - 20

    # ── Helper: page footer ──────────────────────────────────────────────
    def _draw_footer(page, total_pages):
        p.setStrokeColor(NAVY)
        p.setLineWidth(0.5)
        p.line(LM, 32, W - LM, 32)
        p.setFont("Helvetica", 7)
        p.setFillColor(DARK_GREY)
        ts = datetime.now().strftime('%d/%m/%Y at %H:%M')
        p.drawCentredString(W / 2, 22,
            f"Page {page} of {total_pages} | Generated: {ts} | Academic Excellence Report")

    # ═════════════════════════════════════════════════════════════════════
    #  PAGE 1 — MUHTASARI (Summary)
    # ═════════════════════════════════════════════════════════════════════
    school_disp = _get_school_name(exam)
    etype_disp  = exam.get_exam_type_display().upper()

    # Header
    y = H - 50
    _draw_header(y)
    y -= 100

    # School title line
    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(NAVY)
    p.drawCentredString(W / 2, y, f"{school_disp} — {etype_disp} {exam.year} — FORM {exam.form}")
    y -= 20
    p.setFont("Helvetica", 9)
    p.setFillColor(DARK_GREY)
    p.drawCentredString(W / 2, y, exam.name)
    y -= 28

    # ── Division breakdown table ────────────────────────────────────────
    y = _section_heading(y, "MUHTASARI WA DARAJA (DIVISION SUMMARY)")
    y -= 6

    div_rows = [
        ["DARAJA", "IDADI", "ASILIMIA"],
        ["Daraja I",  str(div_counts.get('I', 0)),  _pct(div_counts.get('I', 0))],
        ["Daraja II", str(div_counts.get('II', 0)), _pct(div_counts.get('II', 0))],
        ["Daraja III",str(div_counts.get('III',0)), _pct(div_counts.get('III',0))],
        ["Daraja IV", str(div_counts.get('IV', 0)), _pct(div_counts.get('IV', 0))],
        ["Fail (0)",  str(div_counts.get('0', 0)),  _pct(div_counts.get('0', 0))],
        ["Jumla",     str(total_students),           "100%"],
    ]

    dt = Table(div_rows, colWidths=[140, 80, 80])
    dt.setStyle(_make_style(
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ))
    # Colour the division cells
    for i, d in enumerate(('I', 'II', 'III', 'IV', '0'), 1):
        bg, fg = DIV_PALETTE.get(d, ('FFFFFF', '000000'))
        dt.setStyle(_make_style(
            ('BACKGROUND', (0, i), (0, i), colors.HexColor(bg)),
            ('TEXTCOLOR',  (0, i), (0, i), colors.HexColor(fg)),
        ))

    dt.wrapOn(p, 300, 200)
    div_table_h = len(div_rows) * 22 + 8
    dt.drawOn(p, LM + 10, y - div_table_h)

    # ── Key stats (right side of division table) ─────────────────────────
    stats_x = LM + 310
    p.setFont("Helvetica", 10)
    p.setFillColor(BLACK)
    stats_info = [
        f"Jumla ya Wanafunzi:    {total_students}",
        f"Wastani wa Jumla:      {avg_total:.1f}",
        f"Wastani wa Mean:       {avg_avg:.1f}",
    ]
    for i, line in enumerate(stats_info):
        p.drawString(stats_x, y - 16 - i * 16, line)
    y -= div_table_h + 25

    # ── Subject Statistics ───────────────────────────────────────────────
    if subj_stats and y > 200:
        y = _section_heading(y, "TAKWIMU ZA MASOMO (SUBJECT STATISTICS)")
        y -= 8

        subj_header = ["SOMO", "WASTANI", "JUU", "CHINI", "KUFAULU"]
        subj_data = [subj_header]
        for ss in subj_stats:
            subj_data.append([
                ss['name'], str(ss['avg']), str(ss['max']),
                str(ss['min']), f"{ss['pass_pct']}%"
            ])

        st = Table(subj_data, colWidths=[110, 70, 50, 50, 70])
        st.setStyle(_make_style(
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ))
        st_h = len(subj_data) * 18 + 4
        st.wrapOn(p, 350, st_h)
        st.drawOn(p, LM + 10, y - st_h)
        y -= st_h + 20

    # ── Top 5 students ──────────────────────────────────────────────────
    if all_results and y > 140:
        y = _section_heading(y, "WANAFUNZI BORA 5 (TOP 5 PERFORMERS)")
        y -= 8

        top5 = all_results[:5]
        top_data = [["NAFASI", "JINA", "JUMLA", "WASTANI", "DARAJA"]]
        for r in top5:
            st = r.student
            nm = ' '.join(p for p in [st.first_name, st.middle_name or '', st.last_name] if p)
            if len(nm) > 22:
                nm = nm[:20] + ".."
            top_data.append([str(r.position), nm, str(r.total_score),
                             f"{r.average_score:.1f}", r.division])

        tt = Table(top_data, colWidths=[50, 180, 60, 70, 60])
        tt.setStyle(_make_style(
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ))
        tt_h = len(top_data) * 20 + 4
        tt.wrapOn(p, 420, tt_h)
        tt.drawOn(p, LM + 10, y - tt_h)

    # ── Grading key ──────────────────────────────────────────────────────
    y_footer = 50
    p.setStrokeColor(GOLD)
    p.setLineWidth(0.75)
    p.line(LM, y_footer + 25, W - LM, y_footer + 25)
    p.setFont("Helvetica-Bold", 8)
    p.setFillColor(NAVY)
    p.drawString(LM, y_footer + 12, "UFUNGUO WA DARAJA (GRADING KEY):")
    grad_data = [["A (75-100)", "B (65-74)", "C (50-64)", "D (40-49)", "F (<40)"]]
    grad_colors = ["#C6F4D6", "#D5F5E3", "#FFF9C4", "#FDEBD0", "#FADBD8"]
    gt = Table(grad_data, colWidths=[(CW - 20) / 5] * 5)
    gs_cmds = [
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]
    for i, bg in enumerate(grad_colors):
        gs_cmds.append(('BACKGROUND', (i, 0), (i, 0), colors.HexColor(bg)))
    gt.setStyle(_make_style(*gs_cmds))
    gt.wrapOn(p, CW, 18)
    gt.drawOn(p, LM + 10, y_footer - 5)

    p.showPage()

    # ═════════════════════════════════════════════════════════════════════
    #  PAGE 2+ — MATOKEO KAMILI (Full Results)
    # ═════════════════════════════════════════════════════════════════════
    col_pos   = 32
    col_name  = 140
    col_sex   = 28
    col_subj  = max(36, min(50, int((CW - (col_pos + col_name + col_sex + 170))
                                     / max(len(subjects), 1))))
    col_total = 42
    col_avg   = 42
    col_div   = 36
    col_pts   = 32
    col_widths = ([col_pos, col_name, col_sex] + [col_subj] * len(subjects)
                  + [col_total, col_avg, col_div, col_pts])
    headers = (["POS", "JINA", "JINSIA"]
               + [s.name.upper()[:10] for s in subjects]
               + ["JUMLA", "WASTANI", "DARAJA", "POINTI"])

    tbl_w = sum(col_widths)

    row_h  = 16
    head_h = 40
    avail  = H - 250
    rpp    = max(5, int((avail - head_h) / row_h))
    pages  = [all_results[i:i + rpp] for i in range(0, len(all_results), rpp)]

    for pn, group in enumerate(pages, 1):
        if pn > 1:
            p.showPage()

        y = H - 50
        _draw_header(y)
        y -= 100

        # Title
        p.setFont("Helvetica-Bold", 12)
        p.setFillColor(NAVY)
        p.drawCentredString(W / 2, y,
            f"{school_disp} — {etype_disp} {exam.year} — FORM {exam.form}")
        y -= 18
        p.setFont("Helvetica", 9)
        p.setFillColor(DARK_GREY)
        p.drawCentredString(W / 2, y, f"{exam.name}  |  MATOKEO KAMILI (PAGE {pn})")
        y -= 20

        # Build table
        data = [headers]
        for r in group:
            stu = r.student
            nm  = ' '.join(p for p in [stu.first_name, stu.middle_name or '', stu.last_name] if p)
            if len(nm) > 28:
                nm = nm[:26] + ".."
            row = [str(r.position), nm, stu.gender or 'M']
            for subj in subjects:
                sc = score_lookup.get((stu.id, subj.id))
                row.append(str(sc) if sc is not None else "-")
            row.extend([str(r.total_score), f"{r.average_score:.2f}",
                        r.division, str(r.points)])
            data.append(row)

        tbl = Table(data, colWidths=col_widths)

        style = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        for i in range(1, len(data)):
            if i % 2 == 0:
                style.append(('BACKGROUND', (0, i), (-1, i), LIGHT_GREY))

        # Score colours
        for i, r in enumerate(group, 1):
            for si, subj in enumerate(subjects):
                sc = score_lookup.get((r.student_id, subj.id))
                if sc is not None:
                    ci = 3 + si
                    bg, fg = _score_fill(sc)
                    if bg:
                        style.append(('BACKGROUND', (ci, i), (ci, i), colors.HexColor(bg)))
                    if fg:
                        style.append(('TEXTCOLOR', (ci, i), (ci, i), colors.HexColor(fg)))

        # Division colour
        dc = len(headers) - 2  # DARAJA column
        for i, r in enumerate(group, 1):
            if r.division in DIV_PALETTE:
                bg, fg = DIV_PALETTE[r.division]
                style.append(('BACKGROUND', (dc, i), (dc, i), colors.HexColor(bg)))
                style.append(('TEXTCOLOR', (dc, i), (dc, i), colors.HexColor(fg)))

        tbl.setStyle(_make_style(*style))

        tx = LM + (CW - tbl_w) / 2
        th = len(data) * 15 + 4
        tbl.wrapOn(p, tbl_w, th)
        tbl.drawOn(p, tx, y - th)

        # Grade legend at bottom
        ly = y - th - 18
        if ly > 50:
            leg_data = [["A (75-100)", "B (65-74)", "C (50-64)",
                         "D (40-49)", "F (<40)"]]
            leg_cols = [CW / 5] * 5
            lt = Table(leg_data, colWidths=leg_cols)
            ls_cmds = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ]
            for i, bg in enumerate(["#C6F4D6", "#D5F5E3", "#FFF9C4", "#FDEBD0", "#FADBD8"]):
                ls_cmds.append(('BACKGROUND', (i, 0), (i, 0), colors.HexColor(bg)))
            lt.setStyle(_make_style(*ls_cmds))
            lt.wrapOn(p, CW, 18)
            lt.drawOn(p, LM + 10, ly)

        _draw_footer(pn, len(pages))

    p.save()
    buf.seek(0)

    resp = HttpResponse(buf, content_type='application/pdf')
    safe_name = exam.name.replace(' ', '_')
    resp['Content-Disposition'] = f'attachment; filename="{safe_name}_Academic_Report.pdf"'
    return resp
