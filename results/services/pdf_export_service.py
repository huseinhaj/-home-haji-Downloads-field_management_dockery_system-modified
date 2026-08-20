"""
Professional NECTA Academic Results PDF — Pure ReportLab.
Matches the official NECTA CSEE/FTNA/ACSEE results format.
"""
import io
import os
import base64
from collections import Counter, defaultdict
from datetime import datetime

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, NextPageTemplate,
    Table, TableStyle, Paragraph, Spacer, PageBreak,
    KeepTogether, Flowable,
)

from .export_data import get_exam_export_payload
from .report_helpers import (
    get_full_school_name, get_report_label, get_report_language,
    get_section_title, get_school_type_for_exam,
)

# ── Colours ──────────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#1B3A5C")
GREEN  = colors.HexColor("#1A7B3A")
GOLD   = colors.HexColor("#C4961A")
CREAM  = colors.HexColor("#FAF7F0")
SLATE  = colors.HexColor("#5A6B7A")
LGRAY  = colors.HexColor("#E8EBF0")
WHITE  = colors.white
BLACK  = colors.black
DARK_LINE = colors.HexColor("#CCCCCC")

TZ_GREEN  = colors.HexColor("#1EB53A")
TZ_YELLOW = colors.HexColor("#FCD116")
TZ_BLACK  = colors.black
TZ_BLUE   = colors.HexColor("#00A3DD")

GRADE_BG = {
    'A':  colors.HexColor("#D4EFDF"), 'B+': colors.HexColor("#D5F5E3"),
    'B':  colors.HexColor("#D5F5E3"), 'C+': colors.HexColor("#FEF9E7"),
    'C':  colors.HexColor("#FEF9E7"), 'D':  colors.HexColor("#FDEBD0"),
    'E':  colors.HexColor("#F5CBA7"), 'S':  colors.HexColor("#F9E79F"),
    'F':  colors.HexColor("#FADBD8"),
}
GRADE_FG = {
    'A':  colors.HexColor("#1A6B3A"), 'B+': colors.HexColor("#1E8449"),
    'B':  colors.HexColor("#2D7D46"), 'C+': colors.HexColor("#B7950B"),
    'C':  colors.HexColor("#9A7D0A"), 'D':  colors.HexColor("#BA4A00"),
    'E':  colors.HexColor("#AF601A"), 'S':  colors.HexColor("#B9770B"),
    'F':  colors.HexColor("#922B21"),
}
DIV_BG = {
    'I':   colors.HexColor("#D4EFDF"), 'II':  colors.HexColor("#D5F5E3"),
    'III': colors.HexColor("#FEF9E7"), 'IV':  colors.HexColor("#FDEBD0"),
    '0':   colors.HexColor("#FADBD8"),
}
DIV_FG = {
    'I':   colors.HexColor("#1A6B3A"), 'II':  colors.HexColor("#1E8449"),
    'III': colors.HexColor("#B7950B"), 'IV':  colors.HexColor("#BA4A00"),
    '0':   colors.HexColor("#922B21"),
}


# ── Styles ───────────────────────────────────────────────────────────────────
def _styles():
    ss = getSampleStyleSheet()
    s = {}
    # Header styles
    for name, fn, sz, al, clr, sb, sa in [
        ('title_lg', 'Helvetica-Bold', 14, TA_CENTER, NAVY, 2, 1),
        ('title_md', 'Helvetica-Bold', 11, TA_CENTER, NAVY, 2, 1),
        ('subtitle', 'Helvetica', 8, TA_CENTER, SLATE, 0, 4),
        ('section', 'Helvetica-Bold', 10, TA_LEFT, GREEN, 8, 4),
        ('th', 'Helvetica-Bold', 8, TA_CENTER, colors.white, 0, 0),
        ('th_sm', 'Helvetica-Bold', 7, TA_CENTER, colors.white, 0, 0),
        ('td', 'Helvetica', 8, TA_CENTER, BLACK, 0, 0),
        ('td_sm', 'Helvetica', 7, TA_CENTER, BLACK, 0, 0),
        ('td_name', 'Helvetica', 8, TA_LEFT, BLACK, 0, 0),
        ('td_bold', 'Helvetica-Bold', 8, TA_CENTER, BLACK, 0, 0),
        ('td_bold_sm', 'Helvetica-Bold', 7, TA_CENTER, BLACK, 0, 0),
        ('sig', 'Helvetica', 8, TA_CENTER, SLATE, 0, 0),
        ('footer', 'Helvetica', 6.5, TA_CENTER, SLATE, 0, 0),
    ]:
        s[name] = ParagraphStyle(name, parent=ss['Normal'], fontName=fn,
                                 fontSize=sz, alignment=al, textColor=clr,
                                 spaceBefore=sb, spaceAfter=sa, leading=sz + 3)
    return s


# ── Grading ──────────────────────────────────────────────────────────────────
def _grading_thresholds(form):
    if form == 2:
        return [75, 65, 45, 30], [('A','75-100'),('B','65-74'),('C','45-64'),('D','30-44'),('F','0-29')]
    if form in (5, 6):
        return [80, 70, 60, 50, 40, 35], [('A','80-100'),('B','70-79'),('C','60-69'),('D','50-59'),('E','40-49'),('S','35-39'),('F','0-34')]
    return [75, 65, 55, 45, 35, 25], [('A','75-100'),('B+','65-74'),('B','55-64'),('C+','45-54'),('C','35-44'),('D','25-34'),('F','0-24')]


def _grade_for_score(score, form=4):
    if score is None or not isinstance(score, (int, float)):
        return None
    th, gr = _grading_thresholds(form)
    for i, t in enumerate(th):
        if score >= t:
            return gr[i][0]
    return gr[-1][0]


# ── Helpers ──────────────────────────────────────────────────────────────────
def _load_logo_b64(field):
    if not field:
        return ''
    try:
        field.open('rb')
        data = field.read()
        ext = os.path.splitext(str(field.name))[1].lower()
        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg', '.gif': 'image/gif'}
        mime = mime_map.get(ext, 'image/png')
        b64 = base64.b64encode(data).decode('ascii')
        return f'data:{mime};base64,{b64}'
    except Exception:
        return ''


def _student_name(r):
    return ' '.join(p for p in [r.student.first_name, r.student.middle_name or '', r.student.last_name] if p)


def _location_str(exam):
    parts = []
    if exam.school and exam.school.district:
        parts.append(exam.school.district.upper())
    if exam.school and exam.school.region:
        parts.append(exam.school.region.upper())
    return ' — '.join(parts) if parts else 'TANZANIA'


def _p(text, style):
    return Paragraph(str(text), style)


def _safe_b64_img(data_uri, x, y, w, h, canvas):
    if not data_uri or not data_uri.startswith('data:'):
        return
    try:
        import base64 as _b64
        b64_part = data_uri.split(',', 1)[1]
        img_data = _b64.b64decode(b64_part)
        img_buf = io.BytesIO(img_data)
        from reportlab.lib.utils import ImageReader
        canvas.drawImage(ImageReader(img_buf), x, y, width=w, height=h,
                         preserveAspectRatio=True, mask='auto')
    except Exception:
        pass


def _std_table_style(n_rows):
    """Standard table style for data tables."""
    s = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    for i in range(1, n_rows):
        if i % 2 == 0:
            s.append(('BACKGROUND', (0, i), (-1, i), CREAM))
    return s


# ── Header Flowable ──────────────────────────────────────────────────────────
class NECTAHeader(Flowable):
    def __init__(self, exam, school_disp, slogo_uri, dlogo_uri, stype, lang):
        Flowable.__init__(self)
        self.exam = exam
        self.school_disp = school_disp
        self.slogo_uri = slogo_uri
        self.dlogo_uri = dlogo_uri
        self.stype = stype
        self.lang = lang
        self.width = A4[0] - 3.6 * cm
        self.height = 3.2 * cm

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height

        # Green banner
        c.setFillColor(GREEN)
        c.roundRect(0, 0, w, h, 4, fill=1, stroke=0)

        # Logos
        _safe_b64_img(self.slogo_uri, 6, 6, 40, 40, c)
        _safe_b64_img(self.dlogo_uri, w - 46, 6, 40, 40, c)

        cx = w / 2
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 10)
        republic = "THE UNITED REPUBLIC OF TANZANIA" if self.lang == 'en' else "JAMHURI YA MUUNGANO WA TANZANIA"
        c.drawCentredString(cx, h - 14, republic)
        c.setFont('Helvetica-Bold', 7.5)
        ministry = "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY" if self.lang == 'en' else "WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA"
        c.drawCentredString(cx, h - 24, ministry)
        c.setFont('Helvetica', 6.5)
        c.setFillColor(colors.HexColor("#E0E0E0"))
        c.drawCentredString(cx, h - 33, f"{self.stype} — EXAMINATION RESULTS")

        # Flag strip
        strip_y = -3
        for i, col in enumerate([TZ_GREEN, TZ_YELLOW, TZ_BLACK, TZ_BLUE]):
            c.setFillColor(col)
            c.rect(i * w / 4, strip_y, w / 4, 3, fill=1, stroke=0)

        # School name
        c.setFillColor(GOLD)
        c.setFont('Helvetica-Bold', 13)
        c.drawCentredString(cx, strip_y - 16, self.school_disp)
        c.setFillColor(SLATE)
        c.setFont('Helvetica', 6.5)
        c.drawCentredString(cx, strip_y - 26, _location_str(self.exam))

        # Gold line
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.5)
        c.line(0, strip_y - 32, w, strip_y - 32)


# ── Footer ───────────────────────────────────────────────────────────────────
def _footer(canvas, doc):
    canvas.saveState()
    try:
        w, _ = doc.pagesize
    except Exception:
        w = A4[0]
    canvas.setFont('Helvetica', 6.5)
    canvas.setFillColor(SLATE)
    canvas.drawString(doc.leftMargin, 0.7 * cm, get_full_school_name(doc._exam))
    canvas.drawCentredString(w / 2, 0.7 * cm, f"Page {canvas.getPageNumber()}")
    canvas.drawRightString(w - doc.rightMargin, 0.7 * cm, doc._gen_date)
    canvas.setStrokeColor(DARK_LINE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 1.05 * cm, w - doc.rightMargin, 1.05 * cm)
    canvas.restoreState()


# ══════════════════════════════════════════════════════════════════════════════
# BUILD PDF
# ══════════════════════════════════════════════════════════════════════════════
def generate_results_pdf_response(exam):
    st = _styles()
    school_disp = get_full_school_name(exam)
    lang = get_report_language(exam)
    etype = exam.get_exam_type_display().upper()
    rlabel = get_report_label(exam)
    gen_date = datetime.now().strftime('%d %B %Y')
    gen_date_short = datetime.now().strftime('%d/%m/%Y')

    payload = get_exam_export_payload(exam)
    subjects = payload['subjects']
    results = payload['processed_results']
    score_lookup = payload['score_lookup']
    N = len(results)
    n_subj = max(len(subjects), 1)

    slogo_uri = _load_logo_b64(exam.school.school_logo) if exam.school else ''
    dlogo_uri = _load_logo_b64(exam.school.district_logo) if exam.school else ''
    school_type = get_school_type_for_exam(exam)
    stype = "SECONDARY SCHOOL" if school_type == 'secondary' else "PRIMARY SCHOOL"

    # ── Compute stats ──
    if N:
        avg_total = sum(r.total_score for r in results) / N
        avg_average = sum(float(r.average_score) for r in results) / N
        avg_points = sum(r.points for r in results) / N
        div_counts = Counter(r.division for r in results)
        counted = len([s for s in (results[0].counted_subjects or '').split(',') if s.strip()]) if results else n_subj
    else:
        avg_total = avg_average = avg_points = 0
        div_counts = Counter()
        counted = n_subj

    # Sex breakdown
    sex_div = defaultdict(lambda: Counter())
    for r in results:
        g = (r.student.gender or 'M').upper()
        if g not in ('M', 'F'):
            g = 'M'
        sex_div[g][r.division] += 1

    def pct(n):
        return f"{n / N * 100:.1f}%" if N else "0%"

    # Subject stats
    subj_stats = []
    for subj in subjects:
        scores = [score_lookup[(r.student_id, subj.id)]
                  for r in results if (r.student_id, subj.id) in score_lookup]
        if scores:
            subj_stats.append({
                'name': subj.name,
                'avg': round(sum(scores) / len(scores), 1),
                'high': max(scores),
                'low': min(scores),
                'pass_pct': round(sum(1 for s in scores if s >= 40) / len(scores) * 100, 1),
            })

    # Subject GPA (NECTA style)
    subj_gpa = []
    for subj in subjects:
        scores = [score_lookup[(r.student_id, subj.id)]
                  for r in results if (r.student_id, subj.id) in score_lookup]
        if scores:
            # NECTA GPA: average of grade points
            gp_map = {'A': 1, 'B+': 2, 'B': 3, 'C+': 4, 'C': 5, 'D': 6, 'E': 7, 'S': 8, 'F': 9}
            gp_scores = []
            for sc in scores:
                g = _grade_for_score(sc, exam.form)
                gp_scores.append(gp_map.get(g, 9))
            avg_gp = sum(gp_scores) / len(gp_scores)
            # Determine competency level
            if avg_gp <= 1.5:
                level = "Grade A (Very Good)"
            elif avg_gp <= 2.5:
                level = "Grade B+ (Good)"
            elif avg_gp <= 3.5:
                level = "Grade B (Good)"
            elif avg_gp <= 4.5:
                level = "Grade C (Satisfactory)"
            elif avg_gp <= 5.5:
                level = "Grade D (Satisfactory)"
            elif avg_gp <= 6.5:
                level = "Grade E (Satisfactory)"
            elif avg_gp <= 7.5:
                level = "Grade S (Satisfactory)"
            else:
                level = "Grade F (Fail)"
            subj_gpa.append({
                'name': subj.name,
                'registered': N,
                'sat': len(scores),
                'pass_count': sum(1 for sc in scores if sc >= 40),
                'gpa': round(avg_gp, 4),
                'level': level,
            })

    # ══════════════════════════════════════════════════════════════════════
    # PAGE 1: SUMMARY (A4 Portrait)
    # ══════════════════════════════════════════════════════════════════════
    page_w, page_h = A4
    margin_lr = 1.8 * cm
    margin_top = 0.8 * cm
    margin_bot = 1.4 * cm
    content_w = page_w - 2 * margin_lr

    story = []
    story.append(NECTAHeader(exam, school_disp, slogo_uri, dlogo_uri, stype, lang))
    story.append(Spacer(1, 6))

    # Title — beautifully formatted
    story.append(_p(f"<b>{school_disp}</b>", st['title_lg']))
    story.append(_p(f"<b>{etype} {exam.year} — FORM {exam.form}</b>", st['title_md']))
    story.append(_p(exam.name, st['subtitle']))
    story.append(Spacer(1, 4))

    # ── DIVISION PERFORMANCE SUMMARY (NECTA style — by sex) ──
    story.append(_p("<b>DIVISION PERFORMANCE SUMMARY</b>", st['section']))
    div_hdrs = ["SEX", "I", "II", "III", "IV", "0"]
    div_data = [[_p(f"<b>{h}</b>", st['th']) for h in div_hdrs]]
    for sex_label in ('F', 'M', 'T'):
        if sex_label == 'T':
            row_counts = [div_counts.get(d, 0) for d in ('I', 'II', 'III', 'IV', '0')]
        else:
            row_counts = [sex_div[sex_label].get(d, 0) for d in ('I', 'II', 'III', 'IV', '0')]
        row = [_p(f"<b>{sex_label}</b>", st['td_bold'])]
        for dc in row_counts:
            row.append(_p(str(dc), st['td']))
        div_data.append(row)

    cw_div = [content_w * w for w in [0.12, 0.176, 0.176, 0.176, 0.176, 0.176]]
    div_table = Table(div_data, colWidths=cw_div)
    ds = _std_table_style(len(div_data))
    ds.append(('ALIGN', (1, 0), (-1, -1), 'CENTER'))
    div_table.setStyle(TableStyle(ds))
    story.append(div_table)
    story.append(Spacer(1, 6))

    # ── PERFORMANCE SUMMARY + GRADING KEY (side by side) ──
    # Left: Performance Summary
    perf_title = "PERFORMANCE SUMMARY" if lang == 'en' else "TAARIFA YA MAENDELEO"
    if lang == 'sw':
        perf_items = [("Wanafunzi", str(N)), ("Wastani Jumla", f"{avg_total:.1f}"),
                      ("GPA (Pointi)", f"{avg_points:.2f}"), ("Masomo", str(counted))]
    else:
        perf_items = [("Total Candidates", str(N)), ("Overall Average", f"{avg_total:.1f}"),
                      ("Centre GPA", f"{avg_points:.2f}"), ("Subjects", str(counted))]
    perf_data = [[_p(f"<b>{perf_title}</b>", st['th']), '']]
    for k, v in perf_items:
        perf_data.append([_p(k, st['td']), _p(f"<b>{v}</b>", st['td_bold'])])
    cw_perf = [content_w * 0.55, content_w * 0.45]
    perf_table = Table(perf_data, colWidths=cw_perf)
    perf_table.setStyle(TableStyle(_std_table_style(len(perf_data))))

    # Right: Grading Key
    _, grades = _grading_thresholds(exam.form)
    gk_title = "GRADING KEY" if lang == 'en' else "UFUNGUO WA DARAJA"
    gk_cells = [_p(f"<b>{g} ({rng})</b>", ParagraphStyle(
        f'gk_{g}', parent=st['td'], textColor=GRADE_FG.get(g, BLACK),
        fontName='Helvetica-Bold', fontSize=7.5, alignment=TA_CENTER,
    )) for g, rng in grades]
    gk_table = Table([gk_cells], colWidths=[content_w * 0.48 / len(grades)] * len(grades))
    gk_s = [
        ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    for i, (g, _) in enumerate(grades):
        gk_s.append(('BACKGROUND', (i, 0), (i, 0), GRADE_BG.get(g, WHITE)))
    gk_table.setStyle(TableStyle(gk_s))

    # Wrap grading key in a titled table
    gk_outer = Table(
        [[_p(f"<b>{gk_title}</b>", st['th']), '']],
        colWidths=[content_w * 0.48, 0],
    )
    gk_outer.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
    ]))

    side_data = [[perf_table, '', gk_outer]]
    side_table = Table(side_data, colWidths=[content_w * 0.50, content_w * 0.02, content_w * 0.48])
    side_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(side_table)
    story.append(Spacer(1, 4))
    # Grading key below
    story.append(gk_table)
    story.append(Spacer(1, 8))

    # ── SUBJECT STATISTICS ──
    if subj_stats:
        story.append(_p("<b>SUBJECT STATISTICS</b>", st['section']))
        sh = ["SUBJECT", "AVG", "HIGH", "LOW", "PASS%"]
        s_data = [[_p(f"<b>{h}</b>", st['th']) for h in sh]]
        for s in subj_stats:
            s_data.append([
                _p(s['name'], st['td']),
                _p(str(s['avg']), st['td']),
                _p(str(s['high']), st['td']),
                _p(str(s['low']), st['td']),
                _p(f"{s['pass_pct']}%", st['td']),
            ])
        cw_s = [content_w * 0.36] + [content_w * 0.16] * 4
        s_table = Table(s_data, colWidths=cw_s)
        s_table.setStyle(TableStyle(_std_table_style(len(s_data))))
        story.append(s_table)
        story.append(Spacer(1, 8))

    # ── TOP 5 ──
    if results:
        story.append(_p("<b>TOP 5 PERFORMERS</b>", st['section']))
        th = ["POS", "NAME", "TOTAL", "AVG", "PTS", "DIV"]
        t_data = [[_p(f"<b>{h}</b>", st['th']) for h in th]]
        for idx, r in enumerate(results[:5]):
            nm = _student_name(r)
            if len(nm) > 28:
                nm = nm[:26] + '..'
            t_data.append([
                _p(str(r.position), st['td']),
                _p(nm, ParagraphStyle('tn5', parent=st['td'], alignment=TA_LEFT)),
                _p(str(r.total_score), st['td']),
                _p(f"{r.average_score:.1f}", st['td']),
                _p(str(r.points), st['td']),
                _p(str(r.division), st['td']),
            ])
        cw_t5 = [content_w * w for w in [0.08, 0.38, 0.12, 0.12, 0.12, 0.18]]
        t_table = Table(t_data, colWidths=cw_t5)
        ts = _std_table_style(len(t_data))
        ts.append(('BACKGROUND', (0, 1), (-1, 1), GOLD))
        ts.append(('TEXTCOLOR', (0, 1), (-1, 1), colors.white))
        t_table.setStyle(TableStyle(ts))
        story.append(t_table)

    # ══════════════════════════════════════════════════════════════════════
    # RESULTS PAGES (A4 Landscape — NECTA format)
    # ══════════════════════════════════════════════════════════════════════
    story.append(NextPageTemplate('landscape'))
    story.append(PageBreak())

    land_w, land_h = landscape(A4)
    land_margin_lr = 1.2 * cm
    land_top = 0.8 * cm
    land_bot = 1.4 * cm
    land_content_w = land_w - 2 * land_margin_lr

    # Adaptive font size
    if n_subj <= 6:
        fs_cell = 7.5
        fs_hdr = 7.5
    elif n_subj <= 9:
        fs_cell = 6.5
        fs_hdr = 6.5
    else:
        fs_cell = 5.5
        fs_hdr = 5.5

    cell_st = ParagraphStyle('lsm', parent=st['td'], fontSize=fs_cell, leading=fs_cell + 2)
    cell_bold = ParagraphStyle('lsb', parent=st['td_bold'], fontSize=fs_cell, leading=fs_cell + 2)
    hdr_st = ParagraphStyle('lsh', parent=st['th'], fontSize=fs_hdr, leading=fs_hdr + 2)
    name_st = ParagraphStyle('lsn', parent=st['td_name'], fontSize=fs_cell, leading=fs_cell + 2)
    subj_st = ParagraphStyle('lss', parent=st['td'], fontSize=fs_cell - 0.5, leading=fs_cell + 1,
                             wordWrap='CJK')

    rows_per_page = 32 if n_subj <= 6 else 26 if n_subj <= 9 else 20
    chunks = [results[i:i + rows_per_page] for i in range(0, N, rows_per_page)]
    total_pages = len(chunks) or 1

    for pg_idx, chunk in enumerate(chunks, 1):
        # Title
        story.append(_p(f"<b>{school_disp} — {etype} {exam.year} — FORM {exam.form}</b>", st['title_md']))
        story.append(_p(f"{exam.name}  |  PAGE {pg_idx} of {total_pages}", st['subtitle']))

        # NECTA-style table: # | NAME | SEX | AGGT | DIV | DETAILED SUBJECTS
        r_hdr = ["#", "NAME", "SEX", "AGGT", "DIV", "DETAILED SUBJECTS"]
        data = [[_p(f"<b>{h}</b>", hdr_st) for h in r_hdr]]

        for r in chunk:
            nm = _student_name(r)
            max_nm = 22 if n_subj <= 6 else 18 if n_subj <= 9 else 14
            if len(nm) > max_nm:
                nm = nm[:max_nm - 2] + '..'

            # Build inline subjects string: CIV - 'B' HIST - 'C' ...
            subj_parts = []
            for sub in subjects:
                sc = score_lookup.get((r.student_id, sub.id))
                g = _grade_for_score(sc, exam.form) if sc is not None else 'X'
                # Abbreviate subject name
                abbr = sub.name.upper()[:4] if len(sub.name) > 4 else sub.name.upper()
                subj_parts.append(f"{abbr} - '{g}'")
            subj_text = '&nbsp;&nbsp;'.join(subj_parts)

            div_bg = DIV_BG.get(r.division, WHITE)
            div_fg = DIV_FG.get(r.division, BLACK)
            div_st = ParagraphStyle(f'dv2_{r.student_id}', parent=cell_st,
                                    backColor=div_bg, textColor=div_fg,
                                    fontName='Helvetica-Bold')

            data.append([
                _p(str(r.position), cell_st),
                _p(nm, name_st),
                _p(r.student.gender or 'M', cell_st),
                _p(str(r.points), cell_bold),
                _p(str(r.division), div_st),
                _p(subj_text, subj_st),
            ])

        # Column widths: #, NAME, SEX, AGGT, DIV, SUBJECTS (takes most space)
        cw_res = [land_content_w * w for w in [0.04, 0.14, 0.04, 0.05, 0.05, 0.68]]
        r_table = Table(data, colWidths=cw_res, repeatRows=1)
        rs = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('GRID', (0, 0), (-1, -1), 0.3, DARK_LINE),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (1, 0), (1, -1), 5),
            ('LEFTPADDING', (5, 0), (5, -1), 6),
        ]
        for i in range(1, len(data)):
            if i % 2 == 0:
                rs.append(('BACKGROUND', (0, i), (-1, i), CREAM))
        r_table.setStyle(TableStyle(rs))
        story.append(r_table)
        story.append(Spacer(1, 12))

        # Signature area (last page only)
        if pg_idx == total_pages:
            # Grading key (compact)
            gk_cells_pg = [
                _p(f"<b>{g} ({rng})</b>", ParagraphStyle(
                    f'gk3_{g}', parent=cell_st, textColor=GRADE_FG.get(g, BLACK),
                    fontName='Helvetica-Bold',
                ))
                for g, rng in grades
            ]
            gk_table_pg = Table([gk_cells_pg], colWidths=[land_content_w / len(grades)] * len(grades))
            gk_s = [
                ('GRID', (0, 0), (-1, -1), 0.3, LGRAY),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]
            for i, (g, _) in enumerate(grades):
                gk_s.append(('BACKGROUND', (i, 0), (i, 0), GRADE_BG.get(g, WHITE)))
            gk_table_pg.setStyle(TableStyle(gk_s))
            story.append(gk_table_pg)
            story.append(Spacer(1, 14))

            # ── EXAMINATION CENTRE OVERALL PERFORMANCE ──
            story.append(_p("<b>EXAMINATION CENTRE OVERALL PERFORMANCE</b>", st['section']))

            # Division breakdown table (like NECTA)
            div_perf_hdrs = ["", "REGIST", "ABSENT", "SAT", "CLEAN", "DIV I", "DIV II", "DIV III", "DIV IV", "DIV 0"]
            absent_count = sum(1 for r in results if r.total_score == 0)  # rough estimate
            dp_data = [[_p(f"<b>{h}</b>", ParagraphStyle('dph', parent=cell_st, fontSize=6, textColor=colors.white, fontName='Helvetica-Bold')) for h in div_perf_hdrs]]
            dp_row = [_p("<b>TOTAL</b>", ParagraphStyle('dpt', parent=cell_st, fontSize=6, fontName='Helvetica-Bold'))]
            dp_row += [
                _p(str(N), cell_st),
                _p(str(absent_count), cell_st),
                _p(str(N - absent_count), cell_st),
                _p(str(N - absent_count), cell_st),
                _p(str(div_counts.get('I', 0)), cell_st),
                _p(str(div_counts.get('II', 0)), cell_st),
                _p(str(div_counts.get('III', 0)), cell_st),
                _p(str(div_counts.get('IV', 0)), cell_st),
                _p(str(div_counts.get('0', 0)), cell_st),
            ]
            dp_data.append(dp_row)
            cw_dp = [land_content_w / len(div_perf_hdrs)] * len(div_perf_hdrs)
            dp_table = Table(dp_data, colWidths=cw_dp)
            dp_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), NAVY),
                ('GRID', (0, 0), (-1, -1), 0.3, LGRAY),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ]))
            story.append(dp_table)
            story.append(Spacer(1, 8))

            # ── SUBJECT PERFORMANCE SUMMARY (NECTA style) ──
            if subj_gpa:
                story.append(_p("<b>EXAMINATION CENTRE SUBJECTS PERFORMANCE</b>", st['section']))
                sp_hdrs = ["#", "SUBJECT", "REG", "SAT", "PASS", "GPA", "COMPETENCY LEVEL"]
                sp_data = [[_p(f"<b>{h}</b>", ParagraphStyle('sph', parent=cell_st, fontSize=6, textColor=colors.white, fontName='Helvetica-Bold')) for h in sp_hdrs]]
                for idx, sg in enumerate(subj_gpa, 1):
                    sp_data.append([
                        _p(str(idx), cell_st),
                        _p(sg['name'], ParagraphStyle('spn', parent=cell_st, fontSize=6, alignment=TA_LEFT)),
                        _p(str(sg['registered']), cell_st),
                        _p(str(sg['sat']), cell_st),
                        _p(str(sg['pass_count']), cell_st),
                        _p(f"{sg['gpa']:.4f}", cell_st),
                        _p(sg['level'], ParagraphStyle('spl', parent=cell_st, fontSize=6, alignment=TA_LEFT)),
                    ])
                cw_sp = [land_content_w * w for w in [0.04, 0.20, 0.06, 0.06, 0.06, 0.08, 0.50]]
                sp_table = Table(sp_data, colWidths=cw_sp)
                sp_table.setStyle(TableStyle(_std_table_style(len(sp_data))))
                story.append(sp_table)
                story.append(Spacer(1, 14))

            # ── Signature (with AUTO DATE) ──
            sig_left = [
                _p('<hr width="100%"/>', st['sig']),
                _p('<b>Signature &amp; Stamp</b>', st['sig']),
                _p('Academic Officer', st['sig']),
            ]
            sig_right = [
                _p('<hr width="100%"/>', st['sig']),
                _p('<b>Signature &amp; Stamp</b>', st['sig']),
                _p('Head of School', st['sig']),
            ]
            sig_data = [[sig_left, '', sig_right]]
            sig_table = Table(sig_data, colWidths=[land_content_w * 0.42, land_content_w * 0.16, land_content_w * 0.42])
            sig_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]))
            story.append(sig_table)
            story.append(Spacer(1, 6))
            story.append(_p(f'Date: {gen_date}', ParagraphStyle(
                'dt', parent=st['sig'], alignment=TA_LEFT,
            )))

        if pg_idx < total_pages:
            story.append(PageBreak())

    # ── Build with BaseDocTemplate ──
    buf = io.BytesIO()

    portrait_frame = Frame(
        margin_lr, margin_bot, content_w, page_h - margin_top - margin_bot,
        id='portrait',
    )
    landscape_frame = Frame(
        land_margin_lr, land_bot, land_content_w, land_h - land_top - land_bot,
        id='landscape',
    )

    portrait_tmpl = PageTemplate(
        id='portrait', frames=[portrait_frame], pagesize=A4,
        onPage=_footer,
    )
    landscape_tmpl = PageTemplate(
        id='landscape', frames=[landscape_frame],
        pagesize=landscape(A4),
        onPage=_footer,
    )

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        title=f"{school_disp} — {etype} {exam.year}",
        pageTemplates=[portrait_tmpl, landscape_tmpl],
    )
    doc._exam = exam
    doc._gen_date = f"Generated: {gen_date_short}"
    doc.build(story)

    buf.seek(0)
    resp = HttpResponse(buf, content_type='application/pdf')
    safe_name = exam.name.replace(" ", "_")
    resp['Content-Disposition'] = f'attachment; filename="{safe_name}_Results.pdf"'
    return resp
