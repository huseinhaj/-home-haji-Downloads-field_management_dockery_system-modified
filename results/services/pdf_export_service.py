"""
pdf_export_service.py — Professional NECTA-style academic report PDF.

Layout:
  Page 1   SUMMARY — Division breakdown, subject stats, top 5, grading key
  Page 2+  FULL RESULTS — colour-coded scores table with GPA, points, division

Features:
  - School logo (top-left) + District council logo (top-right)
  - "THE UNITED REPUBLIC OF TANZANIA" header
  - Tanzania flag-colour border
  - Flexible for 3-11 subjects (auto column sizing)
  - Print-ready with signature area
"""

from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
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


# ── Colour palette ───────────────────────────────────────────────────────────
TZ_GREEN_CLR      = colors.HexColor(f"#{TZ_GREEN}")
TZ_YELLOW_CLR     = colors.HexColor("#FCD116")
TZ_BLUE_CLR       = colors.HexColor(f"#{TZ_BLUE}")
TZ_GOLD_CLR       = colors.HexColor(f"#{TZ_GOLD}")
TZ_BLACK_CLR      = colors.black
TZ_WHITE_CLR      = colors.white
TZ_LIGHT_GREY_CLR = colors.HexColor(f"#{TZ_LIGHT_GREY}")
TZ_DARK_GREY_CLR  = colors.HexColor(f"#{TZ_DARK_GREY}")

FLAG_GREEN  = colors.HexColor("#1EB53A")
FLAG_YELLOW = colors.HexColor("#FCD116")
FLAG_BLACK  = colors.black
FLAG_BLUE   = colors.HexColor("#00A3DD")


# ── NECTA grading thresholds ────────────────────────────────────────────────
def _grade_thresholds(form):
    if form == 2:
        return [75, 65, 45, 30], [('A', '75-100'), ('B', '65-74'), ('C', '45-64'), ('D', '30-44'), ('F', '0-29')]
    if form in (5, 6):
        return [80, 70, 60, 50, 40, 35], [('A', '80-100'), ('B', '70-79'), ('C', '60-69'), ('D', '50-59'), ('E', '40-49'), ('S', '35-39'), ('F', '0-34')]
    return [75, 65, 55, 45, 35, 25], [('A', '75-100'), ('B+', '65-74'), ('B', '55-64'), ('C+', '45-54'), ('C', '35-44'), ('D', '25-34'), ('F', '0-24')]


_FILL_BY_LETTER = {
    'A':  ("#C6F4D6", "#145A32"),
    'B+': ("#D5F5E3", "#1E8449"),
    'B':  ("#D5F5E3", "#1E8449"),
    'C+': ("#FFF9C4", "#7D6608"),
    'C':  ("#FFF9C4", "#7D6608"),
    'D':  ("#FDEBD0", "#784212"),
    'E':  ("#F0B27A", "#9C640C"),
    'S':  ("#F9E79F", "#B9770B"),
    'F':  ("#FADBD8", "#922B21"),
}

DIV_PALETTE = {
    'I':  ('#C6F4D6', '#145A32'),
    'II': ('#D5F5E3', '#1E8449'),
    'III':('#FFF9C4', '#7D6608'),
    'IV': ('#FDEBD0', '#784212'),
    '0':  ('#FADBD8', '#922B21'),
}


def _score_fill(score, form=4):
    if score is None or not isinstance(score, (int, float)):
        return None, None
    thresholds, grade_ranges = _grade_thresholds(form)
    for i, t in enumerate(thresholds):
        if score >= t:
            return _FILL_BY_LETTER.get(grade_ranges[i][0], (None, None))
    return _FILL_BY_LETTER.get(grade_ranges[-1][0], (None, None))


def _make_style(*cmds):
    return TableStyle(list(cmds))


# ── Logo loader ──────────────────────────────────────────────────────────────
def _load_logo(filename, max_w=60, max_h=60):
    """Try to load a logo from the static/results/logos/ directory.
    Returns an ImageReader or None if not found."""
    candidates = [
        Path(settings.STATICFILES_DIRS[0]) / 'results' / 'logos' / filename
        if hasattr(settings, 'STATICFILES_DIRS') and settings.STATICFILES_DIRS else None,
        Path(settings.BASE_DIR) / 'results' / 'static' / 'results' / 'logos' / filename,
    ]
    for path in candidates:
        if path and path.exists():
            try:
                img = ImageReader(str(path))
                return img
            except Exception:
                pass
    return None


def _get_location(exam):
    parts = []
    if exam.school and exam.school.district:
        parts.append(exam.school.district)
    if exam.school and exam.school.region:
        parts.append(exam.school.region)
    if parts:
        return ' — '.join(p.upper() for p in parts)
    return "LOCATION UNKNOWN"


# ═════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═════════════════════════════════════════════════════════════════════════════

def generate_results_pdf_response(exam):
    """Professional NECTA-style academic report PDF."""
    payload = get_exam_export_payload(exam)
    subjects = payload['subjects']
    all_results = payload['processed_results']
    score_lookup = payload['score_lookup']

    buf = BytesIO()
    p = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    LM = 45
    RM = 45
    CW = W - LM - RM

    total_students = len(all_results)
    school_type = get_school_type_for_exam(exam)
    lang = get_report_language(exam)
    school_disp = get_full_school_name(exam)
    etype_disp = exam.get_exam_type_display().upper()
    report_label = get_report_label(exam)

    # ── Load logos ────────────────────────────────────────────────────
    school_logo = _load_logo('school_logo.png', max_w=65, max_h=65)
    district_logo = _load_logo('district_logo.png', max_w=55, max_h=55)

    # ── Summary stats ─────────────────────────────────────────────────
    if total_students:
        total_sum  = sum(r.total_score for r in all_results)
        avg_sum    = sum(float(r.average_score) for r in all_results)
        avg_total  = total_sum / total_students
        avg_avg    = avg_sum / total_students
        div_counts = Counter(r.division for r in all_results)
        avg_points = sum(r.points for r in all_results) / total_students
        counted_sample = all_results[0].counted_subjects if all_results else ''
        n_counted = len([s for s in counted_sample.split(',') if s.strip()]) if counted_sample else len(subjects)
    else:
        avg_total = avg_avg = avg_points = 0
        div_counts = Counter()
        n_counted = len(subjects)

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

    # ── Helper: Tanzania flag-colour page border ─────────────────────
    def _draw_border():
        bw = 5
        gm = 12
        p.setFillColor(TZ_GREEN_CLR)
        p.rect(gm, H - gm - bw, W - 2 * gm, bw, fill=1, stroke=0)
        p.setFillColor(TZ_YELLOW_CLR)
        p.rect(W - gm - bw, gm, bw, H - 2 * gm, fill=1, stroke=0)
        p.setFillColor(TZ_BLACK_CLR)
        p.rect(gm, gm, W - 2 * gm, bw, fill=1, stroke=0)
        p.setFillColor(TZ_BLUE_CLR)
        p.rect(gm, gm, bw, H - 2 * gm, fill=1, stroke=0)

    # ── Helper: draw header ──────────────────────────────────────────
    def _draw_header(y_start, header_w=None):
        hdr_w = header_w or CW
        hdr_lm = (W - hdr_w) / 2

        # Green banner
        banner_h = 100
        p.setFillColor(TZ_GREEN_CLR)
        p.rect(hdr_lm, y_start - banner_h, hdr_w, banner_h, fill=1, stroke=0)

        # Logos
        if school_logo:
            p.drawImage(school_logo, hdr_lm + 5, y_start - 55, width=50, height=50,
                        preserveAspectRatio=True, mask='auto')
        if district_logo:
            p.drawImage(district_logo, hdr_lm + hdr_w - 55, y_start - 55, width=50, height=50,
                        preserveAspectRatio=True, mask='auto')

        # Text (centred between logos)
        text_cx = hdr_lm + hdr_w / 2
        p.setFillColor(TZ_WHITE_CLR)
        p.setFont("Helvetica-Bold", 11)
        country = "THE UNITED REPUBLIC OF TANZANIA" if lang == 'en' \
            else "JAMHURI YA MUUNGANO WA TANZANIA"
        p.drawCentredString(text_cx, y_start - 14, country)

        p.setFont("Helvetica-Bold", 9)
        ministry = "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY" if lang == 'en' \
            else "WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA"
        p.drawCentredString(text_cx, y_start - 28, ministry)

        p.setFont("Helvetica", 7)
        school_type_label = "SECONDARY SCHOOL" if school_type == 'secondary' else "PRIMARY SCHOOL"
        p.drawCentredString(text_cx, y_start - 40, f"{school_type_label} — EXAMINATION RESULTS")

        # Flag colour bar
        bar_y = y_start - 48
        bar_h = 4
        for i, clr in enumerate([FLAG_GREEN, FLAG_YELLOW, FLAG_BLACK, FLAG_BLUE]):
            p.setFillColor(clr)
            p.rect(hdr_lm + i * hdr_w / 4, bar_y, hdr_w / 4, bar_h, fill=1, stroke=0)

        # School name (gold)
        p.setFillColor(TZ_YELLOW_CLR)
        p.setFont("Helvetica-Bold", 13)
        p.drawCentredString(text_cx, y_start - 65, school_disp)

        # Location
        p.setFillColor(TZ_WHITE_CLR)
        p.setFont("Helvetica", 7)
        p.drawCentredString(text_cx, y_start - 78, _get_location(exam))

        # Gold line
        p.setStrokeColor(TZ_GOLD_CLR)
        p.setLineWidth(2)
        p.line(hdr_lm, y_start - banner_h - 1, hdr_lm + hdr_w, y_start - banner_h - 1)

        return y_start - banner_h - 6

    # ── Helper: section heading ──────────────────────────────────────
    def _section_heading(y, key):
        title = get_section_title(exam, key)
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(TZ_GREEN_CLR)
        p.drawString(LM, y, title.upper())
        p.setStrokeColor(TZ_GREEN_CLR)
        p.setLineWidth(1.5)
        p.line(LM, y - 2, W - RM, y - 2)
        p.setStrokeColor(TZ_GOLD_CLR)
        p.setLineWidth(0.5)
        p.line(LM, y - 4, W - RM, y - 4)
        return y - 16

    # ── Helper: page footer ──────────────────────────────────────────
    def _draw_footer(page, total_pages):
        p.setStrokeColor(TZ_GREEN_CLR)
        p.setLineWidth(0.5)
        p.line(LM, 34, W - RM, 34)
        p.setFont("Helvetica", 6.5)
        p.setFillColor(TZ_DARK_GREY_CLR)
        ts = datetime.now().strftime('%d/%m/%Y %H:%M')
        p.drawString(LM, 22, school_disp)
        p.drawCentredString(W / 2, 22, f"Page {page} of {total_pages}")
        p.drawRightString(W - RM, 22, f"Generated: {ts}")

    # ═══════════════════════════════════════════════════════════════════
    #  PAGE 1 — SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    _draw_border()

    y = H - 45
    y = _draw_header(y)
    y -= 4

    # Exam title
    p.setFont("Helvetica-Bold", 12)
    p.setFillColor(TZ_GREEN_CLR)
    title = f"{etype_disp} {exam.year} — FORM {exam.form}" if lang == 'en' \
        else f"{report_label}"
    p.drawCentredString(W / 2, y, title)
    y -= 14
    p.setFont("Helvetica", 8)
    p.setFillColor(TZ_DARK_GREY_CLR)
    p.drawCentredString(W / 2, y, exam.name)
    y -= 20

    # ── Division breakdown (left) + Stats (right) ────────────────────
    y = _section_heading(y, 'division_summary')
    y -= 2

    # Division table (left side, width 260)
    div_left = LM + 5
    div_w = 260
    if lang == 'sw':
        div_header = ["DARAJA", "IDADI", "ASILIMIA"]
    else:
        div_header = ["DIVISION", "COUNT", "PERCENTAGE"]
    div_rows = [div_header]
    div_labels = {'I': 'Division I', 'II': 'Division II', 'III': 'Division III',
                  'IV': 'Division IV', '0': 'Fail (0)'}
    if lang == 'sw':
        div_labels = {'I': 'Daraja I', 'II': 'Daraja II', 'III': 'Daraja III',
                      'IV': 'Daraja IV', '0': 'Fail (0)'}
    for d in ('I', 'II', 'III', 'IV', '0'):
        div_rows.append([div_labels[d], str(div_counts.get(d, 0)), _pct(div_counts.get(d, 0))])
    div_rows.append(["Total" if lang == 'en' else "Jumla", str(total_students), "100%"])

    dt = Table(div_rows, colWidths=[130, 65, 65])
    dt.setStyle(_make_style(
        ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
        ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ('BOX', (0, 0), (-1, -1), 1.2, TZ_GREEN_CLR),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [TZ_WHITE_CLR, TZ_LIGHT_GREY_CLR]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ))
    for i, d in enumerate(('I', 'II', 'III', 'IV', '0'), 1):
        bg, fg = DIV_PALETTE.get(d, ('FFFFFF', '000000'))
        dt.setStyle(_make_style(
            ('BACKGROUND', (0, i), (0, i), colors.HexColor(bg)),
            ('TEXTCOLOR',  (0, i), (0, i), colors.HexColor(fg)),
            ('FONTNAME', (0, i), (0, i), 'Helvetica-Bold'),
        ))

    dt.wrapOn(p, div_w, 200)
    dt_h = len(div_rows) * 20 + 6
    dt.drawOn(p, div_left, y - dt_h)

    # Stats table (right side)
    stats_x = div_left + div_w + 30
    stats_w = CW - div_w - 40
    if lang == 'sw':
        stats_title = "TAARIFA ZA MAENDELEO (NECTA)"
        stats_rows = [
            ["Wanafunzi", str(total_students)],
            ["Wastani Jumla", f"{avg_total:.1f}"],
            ["Wastani Mean", f"{avg_avg:.1f}"],
            ["Wastani Pointi (GPA)", f"{avg_points:.2f}"],
            ["Masomo Yaliyohesabiwa", str(n_counted)],
        ]
    else:
        stats_title = "PERFORMANCE SUMMARY (NECTA)"
        stats_rows = [
            ["Total Students", str(total_students)],
            ["Overall Average", f"{avg_total:.1f}"],
            ["Mean of Averages", f"{avg_avg:.1f}"],
            ["Average Points (GPA)", f"{avg_points:.2f}"],
            ["Subjects Counted", str(n_counted)],
        ]

    stats_all = [[stats_title, ""]] + stats_rows
    st_tbl = Table(stats_all, colWidths=[stats_w * 0.6, stats_w * 0.4])
    st_tbl.setStyle(_make_style(
        ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
        ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.5),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ('BOX', (0, 0), (-1, -1), 1.2, TZ_GREEN_CLR),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [TZ_WHITE_CLR, TZ_LIGHT_GREY_CLR]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ))
    st_h = len(stats_all) * 20 + 6
    st_tbl.wrapOn(p, stats_w, st_h)
    st_tbl.drawOn(p, stats_x, y - st_h)

    y -= max(dt_h, st_h) + 18

    # ── Subject Statistics ────────────────────────────────────────────
    if subj_stats and y > 180:
        y = _section_heading(y, 'subject_stats')
        y -= 2

        if lang == 'sw':
            sh = ["SOMO", "WASTANI", "JUU", "CHINI", "KUFAULU"]
        else:
            sh = ["SUBJECT", "AVERAGE", "HIGH", "LOW", "PASS %"]
        sd = [sh]
        for ss in subj_stats:
            sd.append([ss['name'], str(ss['avg']), str(ss['max']),
                       str(ss['min']), f"{ss['pass_pct']}%"])

        # Dynamic column width based on number of subjects
        tbl_w = min(CW - 20, 400)
        col_w = tbl_w / 5

        st = Table(sd, colWidths=[col_w * 1.6, col_w, col_w * 0.8, col_w * 0.8, col_w])
        st.setStyle(_make_style(
            ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
            ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ('BOX', (0, 0), (-1, -1), 1.2, TZ_GREEN_CLR),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [TZ_WHITE_CLR, TZ_LIGHT_GREY_CLR]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ))
        st_h = len(sd) * 18 + 4
        st.wrapOn(p, tbl_w, st_h)
        st.drawOn(p, LM + 5, y - st_h)
        y -= st_h + 16

    # ── Top 5 students ────────────────────────────────────────────────
    if all_results and y > 130:
        y = _section_heading(y, 'top_students')
        y -= 2

        top5 = all_results[:5]
        if lang == 'sw':
            th = ["NAFASI", "JINA", "JUMLA", "WASTANI", "POINTI", "DARAJA"]
        else:
            th = ["POS.", "NAME", "TOTAL", "AVG", "PTS", "DIV."]
        td = [th]
        for r in top5:
            st = r.student
            nm = ' '.join(p for p in [st.first_name, st.middle_name or '', st.last_name] if p)
            if len(nm) > 24:
                nm = nm[:22] + ".."
            counted = [s for s in (r.counted_subjects or '').split(',') if s.strip()]
            n_c = len(counted) if counted else len(subjects)
            gpa = r.points / n_c if n_c > 0 else 0
            td.append([str(r.position), nm, str(r.total_score),
                       f"{r.average_score:.1f}", str(r.points), r.division])

        tw = CW - 20
        tt = Table(td, colWidths=[tw * 0.08, tw * 0.37, tw * 0.13, tw * 0.13, tw * 0.12, tw * 0.13])
        tt.setStyle(_make_style(
            ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
            ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ('BOX', (0, 0), (-1, -1), 1.2, TZ_GREEN_CLR),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [TZ_WHITE_CLR, TZ_LIGHT_GREY_CLR]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            # Gold badge for position 1
            ('BACKGROUND', (0, 1), (0, 1), TZ_GOLD_CLR),
            ('TEXTCOLOR',  (0, 1), (0, 1), TZ_WHITE_CLR),
            ('FONTNAME',   (0, 1), (0, 1), 'Helvetica-Bold'),
        ))
        tt_h = len(td) * 20 + 4
        tt.wrapOn(p, tw, tt_h)
        tt.drawOn(p, LM + 5, y - tt_h)

    # ── Grading Key ───────────────────────────────────────────────────
    gk_y = 60
    p.setStrokeColor(TZ_GOLD_CLR)
    p.setLineWidth(0.5)
    p.line(LM, gk_y + 16, W - RM, gk_y + 16)
    p.setFont("Helvetica-Bold", 7)
    p.setFillColor(TZ_GREEN_CLR)
    key_title = get_section_title(exam, 'grading_key')
    p.drawString(LM, gk_y + 5, f"{key_title}:")

    _, grade_ranges = _grade_thresholds(exam.form)
    gk_data = [[f"{g} ({rng})" for g, rng in grade_ranges]]
    gk_w = CW - 20
    gk_cols = [gk_w / len(grade_ranges)] * len(grade_ranges)
    gt = Table(gk_data, colWidths=gk_cols)
    gt_cmds = [
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('BOX', (0, 0), (-1, -1), 0.8, TZ_GREEN_CLR),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
    ]
    for i, (g, _) in enumerate(grade_ranges):
        bg = _FILL_BY_LETTER.get(g, ("#C6F4D6", "#145A32"))[0]
        gt_cmds.append(('BACKGROUND', (i, 0), (i, 0), colors.HexColor(bg)))
    gt.setStyle(_make_style(*gt_cmds))
    gt.wrapOn(p, gk_w, 14)
    gt.drawOn(p, LM + 5, gk_y - 10)

    # Disclaimer
    p.setFont("Helvetica", 6)
    p.setFillColor(TZ_DARK_GREY_CLR)
    disc = "This is an official results report generated from the School Results Management System." if lang == 'en' \
        else "Hii ni ripoti rashi ya matokeo iliyotolewa kutoka Mfumo wa Usimamizi wa Matokeo wa Shule."
    p.drawCentredString(W / 2, 10, disc)

    _draw_footer(1, "2+")
    p.showPage()

    # ═══════════════════════════════════════════════════════════════════
    #  PAGE 2+ — FULL RESULTS (auto-landscape when ≥9 subjects)
    # ═══════════════════════════════════════════════════════════════════
    USE_LANDSCAPE = len(subjects) >= 9
    if USE_LANDSCAPE:
        W, H = landscape(A4)
        LM = 35
        RM = 35
        CW = W - LM - RM

    # ── Dynamic column widths — flexible for 3 to 11+ subjects ──────
    # Fixed columns: POS + NAME + SEX = ~140 pts
    fixed_w = 140
    avail_for_subj = CW - fixed_w - 140  # reserve 140 for TOTAL+AVG+PTS+GPA+DIV
    n_subj = max(len(subjects), 1)
    col_subj = max(24, min(int(avail_for_subj / n_subj), 48))

    # Recalculate actual available after subject columns
    subj_total_w = col_subj * n_subj
    right_avail = CW - fixed_w - subj_total_w
    # Distribute right columns proportionally
    col_total = max(28, int(right_avail * 0.22))
    col_avg   = max(28, int(right_avail * 0.20))
    col_pts   = max(26, int(right_avail * 0.18))
    col_gpa   = max(28, int(right_avail * 0.20))
    col_div   = max(28, right_avail - col_total - col_avg - col_pts - col_gpa)

    col_widths = ([30, 100, 18] + [col_subj] * n_subj
                  + [col_total, col_avg, col_pts, col_gpa, col_div])

    lang_cols = ["#", "JINA", "S"] if lang == 'sw' else ["#", "NAME", "S"]
    headers = (lang_cols
               + [s.name.upper()[:9] for s in subjects]
               + (["JUMLA", "WAST.", "PTS", "GPA", "DARAJA"] if lang == 'sw'
                  else ["TOTAL", "AVG", "PTS", "GPA", "DIV."]))

    tbl_w = sum(col_widths)
    row_h = 13
    head_h = 26
    avail_h = H - 220  # header + margins
    rpp = max(6, int((avail_h - head_h) / row_h))
    page_groups = [all_results[i:i + rpp] for i in range(0, len(all_results), rpp)]
    total_pages = len(page_groups)

    full_title = get_section_title(exam, 'full_results')

    for pn, group in enumerate(page_groups, 1):
        if pn > 1:
            p.showPage()

        if USE_LANDSCAPE:
            p.setPageSize(landscape(A4))

        _draw_border()
        y = H - 35
        y = _draw_header(y, header_w=CW if USE_LANDSCAPE else None)
        y -= 2

        # Title
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(TZ_GREEN_CLR)
        disp = f"{school_disp} — {etype_disp} {exam.year} — FORM {exam.form}" if lang == 'en' \
            else f"{school_disp} — {report_label}"
        p.drawCentredString(W / 2, y, disp)
        y -= 12
        p.setFont("Helvetica", 7)
        p.setFillColor(TZ_DARK_GREY_CLR)
        p.drawCentredString(W / 2, y, f"{exam.name}  |  {full_title}  —  PAGE {pn} / {total_pages}")
        y -= 14

        # ── Build data table ──────────────────────────────────────────
        data = [headers]
        fontsize = 5.8 if n_subj >= 11 else 6.2 if n_subj >= 9 else 6.8 if n_subj >= 7 else 7.5

        for r in group:
            stu = r.student
            nm = ' '.join(p for p in [stu.first_name, stu.middle_name or '', stu.last_name] if p)
            max_name = 18 if n_subj >= 10 else 20 if n_subj >= 8 else 22
            if len(nm) > max_name:
                nm = nm[:max_name - 2] + ".."

            row = [str(r.position), nm, stu.gender or 'M']
            for subj in subjects:
                sc = score_lookup.get((stu.id, subj.id))
                row.append(str(sc) if sc is not None else "-")

            counted = [s for s in (r.counted_subjects or '').split(',') if s.strip()]
            n_c = len(counted) if counted else n_subj
            gpa = r.points / n_c if n_c > 0 else 0
            row.extend([str(r.total_score), f"{r.average_score:.1f}",
                        str(r.points), f"{gpa:.2f}", r.division])
            data.append(row)

        tbl = Table(data, colWidths=col_widths)

        style = [
            ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
            ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), fontsize),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ('BOX', (0, 0), (-1, -1), 1.2, TZ_GREEN_CLR),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        # Alternating rows
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

        # Division colour (last column)
        dc = len(headers) - 1
        for i, r in enumerate(group, 1):
            if r.division in DIV_PALETTE:
                bg, fg = DIV_PALETTE[r.division]
                style.append(('BACKGROUND', (dc, i), (dc, i), colors.HexColor(bg)))
                style.append(('TEXTCOLOR', (dc, i), (dc, i), colors.HexColor(fg)))
                style.append(('FONTNAME', (dc, i), (dc, i), 'Helvetica-Bold'))

        tbl.setStyle(_make_style(*style))

        tx = LM + (CW - tbl_w) / 2
        th = len(data) * row_h + 4
        tbl.wrapOn(p, tbl_w, th)
        tbl.drawOn(p, tx, y - th)

        # ── Grade legend ──────────────────────────────────────────────
        ly = y - th - 10
        if ly > 55:
            _, grade_ranges = _grade_thresholds(exam.form)
            leg_data = [[f"{g} ({rng})" for g, rng in grade_ranges]]
            leg_w = min(CW - 20, 380)
            leg_cols = [leg_w / len(grade_ranges)] * len(grade_ranges)
            lt = Table(leg_data, colWidths=leg_cols)
            ls = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 6),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ('BOX', (0, 0), (-1, -1), 0.8, TZ_GREEN_CLR),
                ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ]
            for i, (g, _) in enumerate(grade_ranges):
                bg = _FILL_BY_LETTER.get(g, ("#C6F4D6", "#145A32"))[0]
                ls.append(('BACKGROUND', (i, 0), (i, 0), colors.HexColor(bg)))
            lt.setStyle(_make_style(*ls))
            lt.wrapOn(p, leg_w, 14)
            lt.drawOn(p, LM + 5, ly)

        # ── Signature area (last page only) ───────────────────────────
        if pn == total_pages:
            sig_y = ly - 28 if ly > 55 else ly - 8
            if sig_y > 75:
                sig_w = 150
                p.setStrokeColor(TZ_DARK_GREY_CLR)
                p.setLineWidth(0.5)
                p.setFont("Helvetica", 6.5)
                p.setFillColor(TZ_DARK_GREY_CLR)

                # Academic Officer
                p.line(LM + 5, sig_y, LM + 5 + sig_w, sig_y)
                p.drawString(LM + 5, sig_y - 10,
                             "Signature & Stamp — Academic Officer")

                # Head of School
                p.line(W - RM - 5 - sig_w, sig_y, W - RM - 5, sig_y)
                p.drawString(W - RM - 5 - sig_w, sig_y - 10,
                             "Signature & Stamp — Head of School")

                p.drawString(LM + 5, sig_y - 22,
                             "Date: ________________________")

        _draw_footer(pn, total_pages)

    p.save()
    buf.seek(0)

    resp = HttpResponse(buf, content_type='application/pdf')
    safe_name = exam.name.replace(' ', '_')
    resp['Content-Disposition'] = f'attachment; filename="{safe_name}_Academic_Report.pdf"'
    return resp
