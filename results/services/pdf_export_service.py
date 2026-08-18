"""
pdf_export_service.py — Professional academic report PDF with Tanzania flag colours.

Page 1   MUHTASARI / SUMMARY
         - Tanzania-flag-branded header (green, yellow, black, blue)
         - Full school name ("KWADELO SECONDARY SCHOOL" not "KWADELO")
         - English for secondary schools, Kiswahili for primary schools
         - Division breakdown, subject stats, top 5

Page 2+  MATOKEO KAMILI / FULL RESULTS
         - Full results table with colour-coded scores
         - Grade legend, page footer
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
from .report_helpers import (
    TZ_BLUE,
    TZ_DARK_GREY,
    TZ_GOLD,
    TZ_GREEN,
    TZ_LIGHT_GREY,
    TZ_WHITE,
    get_full_school_name,
    get_report_label,
    get_report_language,
    get_section_title,
    get_school_type_for_exam,
)


# ── Colour palette (ReportLab native) ────────────────────────────────────────
# Tanzania flag: green (#1EB53A), yellow (#FCD116), black (#000000), blue (#00A3DD)
TZ_GREEN_CLR    = colors.HexColor(f"#{TZ_GREEN}")
TZ_YELLOW_CLR   = colors.HexColor("#FCD116")
TZ_BLUE_CLR     = colors.HexColor(f"#{TZ_BLUE}")
TZ_GOLD_CLR     = colors.HexColor(f"#{TZ_GOLD}")
TZ_BLACK_CLR    = colors.black
TZ_WHITE_CLR    = colors.white
TZ_LIGHT_GREY_CLR = colors.HexColor(f"#{TZ_LIGHT_GREY}")
TZ_DARK_GREY_CLR  = colors.HexColor(f"#{TZ_DARK_GREY}")

# Flag-bar colours for the header divider
FLAG_GREEN = colors.HexColor("#1EB53A")
FLAG_YELLOW = colors.HexColor("#FCD116")
FLAG_BLACK = colors.black
FLAG_BLUE  = colors.HexColor("#00A3DD")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_location(exam):
    if exam.school and exam.school.district and exam.school.region:
        return f"{exam.school.district} DISTRICT — {exam.school.region} REGION".upper()
    if exam.school and exam.school.district:
        return f"{exam.school.district} DISTRICT".upper()
    return "LOCATION UNKNOWN"


def _grade_thresholds(form):
    """Return (score-thresholds, grade-ranges) for the exam's NECTA scale.

    Form 2 (FTNA) and Form 5/6 (ACSEE) grade on different scales than
    Form 1/3/4 (CSEE):
        CSEE:  A 75+ | B 65+ | C 50+ | D 40+ | F <40
        FTNA:  A 75+ | B 65+ | C 45+ | D 30+ | F <30
        ACSEE: A 80+ | B 70+ | C 60+ | D 50+ | E 40+ | S 35+ | F <35
    """
    if form == 2:
        return [75, 65, 45, 30], [('A', '75-100'), ('B', '65-74'), ('C', '45-64'), ('D', '30-44'), ('F', '0-29')]
    if form in (5, 6):
        return [80, 70, 60, 50, 40, 35], [('A', '80-100'), ('B', '70-79'), ('C', '60-69'), ('D', '50-59'), ('E', '40-49'), ('S', '35-39'), ('F', '0-34')]
    return [75, 65, 50, 40], [('A', '75-100'), ('B', '65-74'), ('C', '50-64'), ('D', '40-49'), ('F', '0-39')]


# Grade colour per letter — shared by score cells and the grading-key legend.
# Must stay in sync with utils.get_grade_for_form / get_grade_points.
_FILL_BY_LETTER = {
    'A': ("#C6F4D6", "#145A32"),
    'B': ("#D5F5E3", "#1E8449"),
    'C': ("#FFF9C4", "#7D6608"),
    'D': ("#FDEBD0", "#784212"),
    'E': ("#F0B27A", "#9C640C"),
    'S': ("#F9E79F", "#B9770B"),
    'F': ("#FADBD8", "#922B21"),
}


def _score_fill(score, form=4):
    """Return (background-hex, font-hex) for a score value, using the
    exam's NECTA grade scale (FTNA for Form 2, ACSEE for Form 5/6,
    CSEE otherwise)."""
    if score is None or not isinstance(score, (int, float)):
        return None, None
    thresholds, grade_ranges = _grade_thresholds(form)
    for i, t in enumerate(thresholds):
        if score >= t:
            return _FILL_BY_LETTER.get(grade_ranges[i][0], (None, None))
    return _FILL_BY_LETTER.get(grade_ranges[-1][0], (None, None))


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
    school_type = get_school_type_for_exam(exam)
    lang = get_report_language(exam)
    school_disp = get_full_school_name(exam)
    etype_disp = exam.get_exam_type_display().upper()
    report_label = get_report_label(exam)

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

    # ── Helper: draw Tanzania flag-colour page border ────────────────
    def _draw_page_border():
        """Draw 4 thin coloured bands around the page perimeter — green top,
        yellow right, black bottom, blue left (Tanzania flag order)."""
        bw = 6   # border band thickness/width
        gm = 15  # gap from page edge
        # Top — Green
        p.setFillColor(TZ_GREEN_CLR)
        p.rect(gm, H - gm - bw, W - 2 * gm, bw, fill=1, stroke=0)
        # Right — Yellow
        p.setFillColor(TZ_YELLOW_CLR)
        p.rect(W - gm - bw, gm, bw, H - 2 * gm, fill=1, stroke=0)
        # Bottom — Black
        p.setFillColor(TZ_BLACK_CLR)
        p.rect(gm, gm, W - 2 * gm, bw, fill=1, stroke=0)
        # Left — Blue
        p.setFillColor(TZ_BLUE_CLR)
        p.rect(gm, gm, bw, H - 2 * gm, fill=1, stroke=0)

    # ── Helper: draw the flag-colour header block ──────────────────────
    def _draw_header(y, header_w=None):
        """
        Draw the header block. header_w can override the content width
        for landscape (wider) pages.
        """
        hdr_w = header_w if header_w else CW
        hdr_lm = (W - hdr_w) / 2  # left margin for this header

        # Green bar background
        p.setFillColor(TZ_GREEN_CLR)
        p.rect(hdr_lm, y - 100, hdr_w, 100, fill=1, stroke=0)

        # THE UNITED REPUBLIC OF TANZANIA (top line)
        p.setFillColor(TZ_WHITE_CLR)
        p.setFont("Helvetica-Bold", 11)
        country_line = "THE UNITED REPUBLIC OF TANZANIA" if lang == 'en' \
            else "JAMHURI YA MUUNGANO WA TANZANIA"
        p.drawCentredString(W / 2, y - 12, country_line)

        # Ministry name (second line)
        p.setFont("Helvetica-Bold", 13)
        p.drawCentredString(W / 2, y - 30,
            "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY" if lang == 'en'
            else "WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA")

        # School type subtitle
        p.setFont("Helvetica", 8)
        sub_lines = {
            'en': f"{'SECONDARY' if school_type == 'secondary' else 'PRIMARY'} SCHOOL — EXAMINATION SECTION",
            'sw': f"{'SEKONDARI' if school_type == 'secondary' else 'MSINGI'} — SEHEMU YA MITIHANI",
        }
        p.drawCentredString(W / 2, y - 46, sub_lines.get(lang, sub_lines['en']))

        # Tanzania flag-colour divider bar (green → yellow → black → blue)
        bar_y = y - 55
        bar_h = 5
        bar_parts = 4
        for i, clr in enumerate([FLAG_GREEN, FLAG_YELLOW, FLAG_BLACK, FLAG_BLUE]):
            p.setFillColor(clr)
            p.rect(hdr_lm + i * hdr_w / bar_parts, bar_y,
                   hdr_w / bar_parts, bar_h, fill=1, stroke=0)

        # School name (gold on green background)
        p.setFillColor(TZ_YELLOW_CLR)
        p.setFont("Helvetica-Bold", 14)
        p.drawCentredString(W / 2, y - 72, school_disp)

        # Location
        p.setFillColor(TZ_WHITE_CLR)
        p.setFont("Helvetica", 8)
        loc = _get_location(exam)
        p.drawCentredString(W / 2, y - 88, loc)

        # Gold line below header
        p.setStrokeColor(TZ_GOLD_CLR)
        p.setLineWidth(1.5)
        p.line(hdr_lm, y - 98, hdr_lm + hdr_w, y - 98)

    # ── Helper: section heading line ───────────────────────────────────
    def _section_heading(y, section_key):
        title = get_section_title(exam, section_key)
        p.setFont("Helvetica-Bold", 12 if lang == 'en' else 11)
        p.setFillColor(TZ_GREEN_CLR)
        p.drawString(LM, y, title.upper())
        p.setStrokeColor(TZ_GOLD_CLR)
        p.setLineWidth(1)
        p.line(LM, y - 2, W - LM, y - 2)
        return y - 20

    # ── Helper: page footer ─────────────────────────────────────────---
    def _draw_footer(page, total_pages):
        p.setStrokeColor(TZ_GREEN_CLR)
        p.setLineWidth(0.5)
        p.line(LM, 32, W - LM, 32)
        p.setFont("Helvetica", 7)
        p.setFillColor(TZ_DARK_GREY_CLR)
        ts = datetime.now().strftime('%d/%m/%Y at %H:%M')
        footer_text = {
            'en': f"Page {page} of {total_pages} | Generated: {ts} | Academic Excellence Report",
            'sw': f"Ukurasa {page} kati ya {total_pages} | Imeandaliwa: {ts} | Ripoti ya Taaluma",
        }
        p.drawCentredString(W / 2, 22, footer_text.get(lang, footer_text['en']))

    # ═══════════════════════════════════════════════════════════════════
    #  PAGE 1 — MUHTASARI / SUMMARY
    # ═══════════════════════════════════════════════════════════════════

    # Page border
    _draw_page_border()

    # Header
    y = H - 50
    _draw_header(y)
    y -= 110

    # School title line
    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(TZ_GREEN_CLR)
    title_text = f"{school_disp} — {etype_disp} {exam.year} — FORM {exam.form}" if lang == 'en' \
        else f"{school_disp} — {report_label}"
    p.drawCentredString(W / 2, y, title_text)
    y -= 20
    p.setFont("Helvetica", 9)
    p.setFillColor(TZ_DARK_GREY_CLR)
    p.drawCentredString(W / 2, y, exam.name)
    y -= 28

    # ── Division breakdown table ──────────────────────────────────────
    y = _section_heading(y, 'division_summary')
    y -= 6

    div_header = ["DARAJA", "IDADI", "ASILIMIA"] if lang == 'sw' \
        else ["DIVISION", "COUNT", "PERCENTAGE"]
    div_rows = [div_header]
    div_labels = {'I': 'Daraja I', 'II': 'Daraja II', 'III': 'Daraja III',
                  'IV': 'Daraja IV', '0': 'Fail (0)'}
    if lang == 'en':
        div_labels = {'I': 'Division I', 'II': 'Division II', 'III': 'Division III',
                      'IV': 'Division IV', '0': 'Fail (0)'}
    for d in ('I', 'II', 'III', 'IV', '0'):
        div_rows.append([div_labels[d], str(div_counts.get(d, 0)),
                         _pct(div_counts.get(d, 0))])
    div_rows.append(["Jumla" if lang == 'sw' else "Total",
                     str(total_students), "100%"])

    dt = Table(div_rows, colWidths=[140, 80, 80])
    dt.setStyle(_make_style(
        ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
        ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ('BOX', (0, 0), (-1, -1), 1.5, TZ_GREEN_CLR),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [TZ_WHITE_CLR, TZ_LIGHT_GREY_CLR]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ))
    for i, d in enumerate(('I', 'II', 'III', 'IV', '0'), 1):
        bg, fg = DIV_PALETTE.get(d, ('FFFFFF', '000000'))
        dt.setStyle(_make_style(
            ('BACKGROUND', (0, i), (0, i), colors.HexColor(bg)),
            ('TEXTCOLOR',  (0, i), (0, i), colors.HexColor(fg)),
        ))

    dt.wrapOn(p, 300, 200)
    div_table_h = len(div_rows) * 22 + 8
    dt.drawOn(p, LM + 10, y - div_table_h)

    # ── Key stats table (right side of division table) ─────────────────
    stats_width = 180
    stats_x = LM + 310
    if lang == 'sw':
        stats_title = "MUHTASARI WA MAENDELEO"
        stats_rows = [
            ["Jumla ya Wanafunzi", str(total_students)],
            ["Wastani wa Jumla", f"{avg_total:.1f}"],
            ["Wastani wa Mean", f"{avg_avg:.1f}"],
        ]
    else:
        stats_title = "PERFORMANCE SUMMARY"
        stats_rows = [
            ["Total Students", str(total_students)],
            ["Overall Average", f"{avg_total:.1f}"],
            ["Mean of Averages", f"{avg_avg:.1f}"],
        ]

    # Build stats table with branded styling
    stats_header = [[stats_title, ""]]
    stats_all = stats_header + stats_rows
    st_tbl = Table(stats_all, colWidths=[stats_width * 0.58, stats_width * 0.42])
    st_tbl.setStyle(_make_style(
        ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
        ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ('BOX', (0, 0), (-1, -1), 1.5, TZ_GREEN_CLR),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [TZ_WHITE_CLR, TZ_LIGHT_GREY_CLR]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ))
    st_h = len(stats_all) * 22 + 8
    st_tbl.wrapOn(p, stats_width, st_h)
    st_tbl.drawOn(p, stats_x, y - st_h)
    y -= max(div_table_h, st_h) + 25

    # ── Subject Statistics ─────────────────────────────────────────────
    if subj_stats and y > 200:
        y = _section_heading(y, 'subject_stats')
        y -= 8

        if lang == 'sw':
            subj_header = ["SOMO", "WASTANI", "JUU", "CHINI", "KUFAULU"]
        else:
            subj_header = ["SUBJECT", "AVERAGE", "HIGH", "LOW", "PASS %"]
        subj_data = [subj_header]
        for ss in subj_stats:
            subj_data.append([
                ss['name'], str(ss['avg']), str(ss['max']),
                str(ss['min']), f"{ss['pass_pct']}%"
            ])

        st = Table(subj_data, colWidths=[110, 70, 50, 50, 70])
        st.setStyle(_make_style(
            ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
            ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ('BOX', (0, 0), (-1, -1), 1.5, TZ_GREEN_CLR),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [TZ_WHITE_CLR, TZ_LIGHT_GREY_CLR]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ))
        st_h = len(subj_data) * 18 + 4
        st.wrapOn(p, 350, st_h)
        st.drawOn(p, LM + 10, y - st_h)
        y -= st_h + 20

    # ── Top 5 students ─────────────────────────────────────────────────
    if all_results and y > 140:
        y = _section_heading(y, 'top_students')
        y -= 8

        top5 = all_results[:5]
        if lang == 'sw':
            top_header = ["NAFASI", "JINA", "JUMLA", "WASTANI", "DARAJA"]
        else:
            top_header = ["POS.", "NAME", "TOTAL", "AVERAGE", "DIV."]
        top_data = [top_header]
        for r in top5:
            st = r.student
            nm = ' '.join(p for p in [st.first_name, st.middle_name or '', st.last_name] if p)
            if len(nm) > 22:
                nm = nm[:20] + ".."
            top_data.append([str(r.position), nm, str(r.total_score),
                             f"{r.average_score:.1f}", r.division])

        tt = Table(top_data, colWidths=[50, 180, 60, 70, 60])
        tt.setStyle(_make_style(
            ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
            ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ('BOX', (0, 0), (-1, -1), 1.5, TZ_GREEN_CLR),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [TZ_WHITE_CLR, TZ_LIGHT_GREY_CLR]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ))
        tt_h = len(top_data) * 20 + 4
        tt.wrapOn(p, 420, tt_h)
        tt.drawOn(p, LM + 10, y - tt_h)

    # ── Grading key ───────────────────────────────────────────────────
    y_footer = 50
    p.setStrokeColor(TZ_GOLD_CLR)
    p.setLineWidth(0.75)
    p.line(LM, y_footer + 25, W - LM, y_footer + 25)
    p.setFont("Helvetica-Bold", 8)
    p.setFillColor(TZ_GREEN_CLR)
    key_title = get_section_title(exam, 'grading_key')
    p.drawString(LM, y_footer + 12, f"{key_title}:")
    _, grade_ranges = _grade_thresholds(exam.form)
    grad_data = [[f"{g} ({rng})" for g, rng in grade_ranges]]
    grad_colors = [
        _FILL_BY_LETTER.get(g, ("#C6F4D6", "#145A32"))[0]
        for g, _ in grade_ranges
    ]
    gt = Table(grad_data, colWidths=[(CW - 20) / len(grade_ranges)] * len(grade_ranges))
    gs_cmds = [
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('BOX', (0, 0), (-1, -1), 1, TZ_GREEN_CLR),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
    ]
    for i, bg in enumerate(grad_colors):
        gs_cmds.append(('BACKGROUND', (i, 0), (i, 0), colors.HexColor(bg)))
    gt.setStyle(_make_style(*gs_cmds))
    gt.wrapOn(p, CW, 18)
    gt.drawOn(p, LM + 10, y_footer - 5)

    p.showPage()

    # ═══════════════════════════════════════════════════════════════════
    #  PAGE 2+ — MATOKEO KAMILI / FULL RESULTS (Landscape for many subjects)
    # ═══════════════════════════════════════════════════════════════════
    # If there are 10+ subjects, use landscape to avoid clipping
    USE_LANDSCAPE = len(subjects) >= 9
    if USE_LANDSCAPE:
        from reportlab.lib.pagesizes import landscape as _landscape
        W, H = _landscape(A4)  # 842 x 595
        # Recalculate content width for landscape
        LM = 40  # slightly narrower margins in landscape
        CW = W - 2 * LM

    # Compute column widths dynamically
    # Reserve space for fixed columns
    fixed_cols_width = 28 + 110 + 20 + 28 + 28 + 24 + 24  # POS + NAME + SEX + TOTAL + AVG + DIV + PTS
    avail_for_subjects = CW - fixed_cols_width
    col_subj = max(22, int(avail_for_subjects / max(len(subjects), 1)))
    # Cap subject columns so they don't get too wide
    col_subj = min(col_subj, 45)

    col_pos   = 28
    col_name  = 110
    col_sex   = 20
    col_total = 28
    col_avg   = 28
    col_div   = 24
    col_pts   = 24
    col_widths = ([col_pos, col_name, col_sex] + [col_subj] * len(subjects)
                  + [col_total, col_avg, col_div, col_pts])

    cols_sw  = ["POS", "JINA", "JINSIA"]
    cols_en  = ["POS", "NAME", "SEX"]
    lang_cols = cols_sw if lang == 'sw' else cols_en

    # Shorten subject names to 8 chars max for header
    headers = (lang_cols
               + [s.name.upper()[:8] for s in subjects]
               + (["JUMLA", "WASTANI", "DARAJA", "POINTI"] if lang == 'sw'
                  else ["TOTAL", "AVG", "DIV.", "PTS"]))

    tbl_w = sum(col_widths)

    row_h  = 14
    head_h = 32
    avail  = H - 260
    rpp    = max(8, int((avail - head_h) / row_h))
    pages  = [all_results[i:i + rpp] for i in range(0, len(all_results), rpp)]

    full_results_title = get_section_title(exam, 'full_results')

    for pn, group in enumerate(pages, 1):
        if pn > 1:
            p.showPage()

        # Switch to landscape pagesize after first page
        if USE_LANDSCAPE:
            p.setPageSize(_landscape(A4))

        # Page border on every page
        _draw_page_border()

        y = H - 40
        _draw_header(y, header_w=CW if USE_LANDSCAPE else None)
        y -= 110

        # Title
        p.setFont("Helvetica-Bold", 11)
        p.setFillColor(TZ_GREEN_CLR)
        disp = f"{school_disp} — {etype_disp} {exam.year} — FORM {exam.form}" if lang == 'en' \
            else f"{school_disp} — {report_label}"
        p.drawCentredString(W / 2, y, disp)
        y -= 16
        p.setFont("Helvetica", 8)
        p.setFillColor(TZ_DARK_GREY_CLR)
        p.drawCentredString(W / 2, y, f"{exam.name}  |  {full_results_title} (PAGE {pn})")
        y -= 18

        # Build table
        data = [headers]
        fontsize = 6.5 if len(subjects) >= 12 else 7.0 if len(subjects) >= 9 else 7.5
        for r in group:
            stu = r.student
            nm  = ' '.join(p for p in [stu.first_name, stu.middle_name or '', stu.last_name] if p)
            if len(nm) > 22:
                nm = nm[:20] + ".."
            row = [str(r.position), nm, stu.gender or 'M']
            for subj in subjects:
                sc = score_lookup.get((stu.id, subj.id))
                row.append(str(sc) if sc is not None else "-")
            row.extend([str(r.total_score), f"{r.average_score:.2f}",
                        r.division, str(r.points)])
            data.append(row)

        tbl = Table(data, colWidths=col_widths)

        style = [
            ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
            ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), fontsize),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
            ('BOX', (0, 0), (-1, -1), 1.5, TZ_GREEN_CLR),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        for i in range(1, len(data)):
            if i % 2 == 0:
                style.append(('BACKGROUND', (0, i), (-1, i), TZ_LIGHT_GREY_CLR))

        # Score colours
        for i, r in enumerate(group, 1):
            for si, subj in enumerate(subjects):
                sc = score_lookup.get((r.student_id, subj.id))
                if sc is not None:
                    ci = 3 + si
                    bg, fg = _score_fill(sc, exam.form)
                    if bg:
                        style.append(('BACKGROUND', (ci, i), (ci, i), colors.HexColor(bg)))
                    if fg:
                        style.append(('TEXTCOLOR', (ci, i), (ci, i), colors.HexColor(fg)))

        # Division colour
        dc = len(headers) - 2  # DARAJA/DIV column
        for i, r in enumerate(group, 1):
            if r.division in DIV_PALETTE:
                bg, fg = DIV_PALETTE[r.division]
                style.append(('BACKGROUND', (dc, i), (dc, i), colors.HexColor(bg)))
                style.append(('TEXTCOLOR', (dc, i), (dc, i), colors.HexColor(fg)))

        tbl.setStyle(_make_style(*style))

        tx = LM + (CW - tbl_w) / 2
        th = len(data) * row_h + 4
        tbl.wrapOn(p, tbl_w, th)
        tbl.drawOn(p, tx, y - th)

        # Grade legend at bottom
        ly = y - th - 14
        if ly > 40:
            _, grade_ranges = _grade_thresholds(exam.form)
            leg_data = [[f"{g} ({rng})" for g, rng in grade_ranges]]
            leg_w = min(CW - 20, 400)
            leg_cols = [leg_w / len(grade_ranges)] * len(grade_ranges)
            lt = Table(leg_data, colWidths=leg_cols)
            ls_cmds = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 6),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ('BOX', (0, 0), (-1, -1), 1, TZ_GREEN_CLR),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ]
            for i, (g, _) in enumerate(grade_ranges):
                bg = _FILL_BY_LETTER.get(g, ("#C6F4D6", "#145A32"))[0]
                ls_cmds.append(('BACKGROUND', (i, 0), (i, 0), colors.HexColor(bg)))
            lt.setStyle(_make_style(*ls_cmds))
            lt.wrapOn(p, leg_w, 14)
            lt.drawOn(p, LM + 10, ly)

        _draw_footer(pn, len(pages))

    p.save()
    buf.seek(0)

    resp = HttpResponse(buf, content_type='application/pdf')
    safe_name = exam.name.replace(' ', '_')
    resp['Content-Disposition'] = f'attachment; filename=\"{safe_name}_Academic_Report.pdf\"'
    return resp
