"""
Professional NECTA Academic Results PDF — Pure ReportLab.
Uses Paragraph in every table cell (no text cutting / word-wrap issues).
Flowable-based layout (no overlapping, no drawOn positioning).
"""
import io
import os
import base64
from collections import Counter
from datetime import datetime

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
    HRFlowable, KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

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
    return {
        'republic': ParagraphStyle(
            'republic', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=10, alignment=TA_CENTER,
            textColor=colors.white, spaceAfter=1,
        ),
        'ministry': ParagraphStyle(
            'ministry', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=7.5, alignment=TA_CENTER,
            textColor=colors.white, spaceAfter=1,
        ),
        'exam_type': ParagraphStyle(
            'exam_type', parent=ss['Normal'],
            fontName='Helvetica', fontSize=6.5, alignment=TA_CENTER,
            textColor=colors.HexColor("#E0E0E0"), spaceAfter=1,
        ),
        'school_name': ParagraphStyle(
            'school_name', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=13, alignment=TA_CENTER,
            textColor=GOLD, spaceBefore=6, spaceAfter=2,
        ),
        'school_loc': ParagraphStyle(
            'school_loc', parent=ss['Normal'],
            fontName='Helvetica', fontSize=6.5, alignment=TA_CENTER,
            textColor=SLATE, spaceAfter=4,
        ),
        'page_title': ParagraphStyle(
            'page_title', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=11, alignment=TA_CENTER,
            textColor=NAVY, spaceBefore=4, spaceAfter=1,
        ),
        'page_sub': ParagraphStyle(
            'page_sub', parent=ss['Normal'],
            fontName='Helvetica', fontSize=7, alignment=TA_CENTER,
            textColor=SLATE, spaceAfter=6,
        ),
        'section': ParagraphStyle(
            'section', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=9.5, textColor=GREEN,
            spaceBefore=8, spaceAfter=4,
        ),
        'th': ParagraphStyle(
            'th', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=7, alignment=TA_CENTER,
            textColor=colors.white,
        ),
        'th_sm': ParagraphStyle(
            'th_sm', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=6, alignment=TA_CENTER,
            textColor=colors.white,
        ),
        'td': ParagraphStyle(
            'td', parent=ss['Normal'],
            fontName='Helvetica', fontSize=7.5, alignment=TA_CENTER,
        ),
        'td_sm': ParagraphStyle(
            'td_sm', parent=ss['Normal'],
            fontName='Helvetica', fontSize=6.5, alignment=TA_CENTER,
        ),
        'td_name': ParagraphStyle(
            'td_name', parent=ss['Normal'],
            fontName='Helvetica', fontSize=7.5, alignment=TA_LEFT,
        ),
        'td_name_sm': ParagraphStyle(
            'td_name_sm', parent=ss['Normal'],
            fontName='Helvetica', fontSize=6.5, alignment=TA_LEFT,
        ),
        'td_bold': ParagraphStyle(
            'td_bold', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=7.5, alignment=TA_CENTER,
        ),
        'sig': ParagraphStyle(
            'sig', parent=ss['Normal'],
            fontName='Helvetica', fontSize=7, alignment=TA_CENTER,
            textColor=SLATE,
        ),
        'footer': ParagraphStyle(
            'footer', parent=ss['Normal'],
            fontName='Helvetica', fontSize=6, alignment=TA_CENTER,
            textColor=SLATE,
        ),
    }


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
    """Shortcut: create a Paragraph."""
    return Paragraph(str(text), style)


def _div_label(d, lang):
    labels = {
        'I':   ('Division I', 'Daraja I'),
        'II':  ('Division II', 'Daraja II'),
        'III': ('Division III', 'Daraja III'),
        'IV':  ('Division IV', 'Daraja IV'),
        '0':   ('Fail (0)', 'Faili (0)'),
    }
    pair = labels.get(d, (d, d))
    return pair[0] if lang == 'en' else pair[1]


# ── Header Flowable ──────────────────────────────────────────────────────────
class NECTAHeader:
    """Custom flowable that draws the green banner + logos + text on first page."""
    def __init__(self, exam, school_disp, slogo_uri, dlogo_uri, stype, lang):
        self.exam = exam
        self.school_disp = school_disp
        self.slogo_uri = slogo_uri
        self.dlogo_uri = dlogo_uri
        self.stype = stype
        self.lang = lang
        self.width = A4[0] - 3.6 * cm  # page width minus margins
        self.height = 3.2 * cm

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        exam = self.exam

        # Green banner background
        c.setFillColor(GREEN)
        c.roundRect(0, 0, w, h, 4, fill=1, stroke=0)

        # Logo left (school)
        if self.slogo_uri:
            try:
                import base64 as _b64
                data_uri = self.slogo_uri
                if data_uri.startswith('data:'):
                    b64_part = data_uri.split(',', 1)[1]
                    img_data = _b64.b64decode(b64_part)
                    img_buf = io.BytesIO(img_data)
                    from reportlab.lib.utils import ImageReader
                    img = ImageReader(img_buf)
                    c.drawImage(img, 6, 6, width=40, height=40, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        # Logo right (district)
        if self.dlogo_uri:
            try:
                import base64 as _b64
                data_uri = self.dlogo_uri
                if data_uri.startswith('data:'):
                    b64_part = data_uri.split(',', 1)[1]
                    img_data = _b64.b64decode(b64_part)
                    img_buf = io.BytesIO(img_data)
                    from reportlab.lib.utils import ImageReader
                    img = ImageReader(img_buf)
                    c.drawImage(img, w - 46, 6, width=40, height=40, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        # Text in center
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

        # Tanzania flag strip below banner
        strip_y = -3
        strip_h = 3
        colors_list = [TZ_GREEN, TZ_YELLOW, TZ_BLACK, TZ_BLUE]
        seg_w = w / 4
        for i, col in enumerate(colors_list):
            c.setFillColor(col)
            c.rect(i * seg_w, strip_y, seg_w, strip_h, fill=1, stroke=0)

        # School name below strip
        c.setFillColor(GOLD)
        c.setFont('Helvetica-Bold', 13)
        c.drawCentredString(cx, strip_y - 16, self.school_disp)

        # Location
        c.setFillColor(SLATE)
        c.setFont('Helvetica', 6.5)
        c.drawCentredString(cx, strip_y - 26, _location_str(exam))

        # Gold divider line
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.5)
        c.line(0, strip_y - 32, w, strip_y - 32)


# ── Footer ───────────────────────────────────────────────────────────────────
def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 6)
    canvas.setFillColor(SLATE)
    # School name left
    canvas.drawString(doc.leftMargin, 0.8 * cm, get_full_school_name(doc._exam))
    # Page number center
    canvas.drawCentredString(A4[0] / 2, 0.8 * cm, f"Page {canvas.getPageNumber()}")
    # Date right
    canvas.drawRightString(A4[0] - doc.rightMargin, 0.8 * cm, datetime.now().strftime('%d/%m/%Y at %H:%M'))
    # Black bottom border
    canvas.setStrokeColor(BLACK)
    canvas.setLineWidth(1)
    canvas.line(doc.leftMargin, 1.1 * cm, A4[0] - doc.rightMargin, 1.1 * cm)
    canvas.restoreState()


def _first_page_footer(canvas, doc):
    _footer(canvas, doc)


def _later_pages_footer(canvas, doc):
    _footer(canvas, doc)


# ── Build PDF ────────────────────────────────────────────────────────────────
def generate_results_pdf_response(exam):
    """Generate professional NECTA-style PDF."""
    st = _styles()
    school_disp = get_full_school_name(exam)
    lang = get_report_language(exam)
    etype = exam.get_exam_type_display().upper()
    rlabel = get_report_label(exam)

    # Load data
    payload = get_exam_export_payload(exam)
    subjects = payload['subjects']
    results = payload['processed_results']
    score_lookup = payload['score_lookup']
    N = len(results)
    n_subj = max(len(subjects), 1)

    # Logos
    slogo_uri = _load_logo_b64(exam.school.school_logo) if exam.school else ''
    dlogo_uri = _load_logo_b64(exam.school.district_logo) if exam.school else ''

    school_type = get_school_type_for_exam(exam)
    stype = "SECONDARY SCHOOL" if school_type == 'secondary' else "PRIMARY SCHOOL"

    # Stats
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

    # ── Page width ──
    page_w, page_h = A4
    margin_lr = 1.8 * cm
    margin_top = 0.8 * cm
    margin_bot = 1.4 * cm
    content_w = page_w - 2 * margin_lr

    story = []

    # ── Header ──
    header = NECTAHeader(exam, school_disp, slogo_uri, dlogo_uri, stype, lang)
    story.append(header)
    story.append(Spacer(1, 4))

    # ── Page title ──
    page_title = f"{etype} {exam.year} — FORM {exam.form}" if lang == 'en' else rlabel
    story.append(_p(page_title, st['page_title']))
    story.append(_p(exam.name, st['page_sub']))

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY PAGE
    # ══════════════════════════════════════════════════════════════════════════

    # ── Division Summary Table ──
    div_title = get_section_title(exam, 'division_summary')
    d_hdr_label = "DIVISION" if lang == 'en' else "DARAJA"
    d_count_label = "COUNT" if lang == 'en' else "IDADI"
    d_pct_label = "%"

    div_data = [
        [_p(f"<b>{div_title}</b>", st['th']), '', ''],
        [_p(d_hdr_label, st['th']), _p(d_count_label, st['th']), _p(d_pct_label, st['th'])],
    ]
    div_row_bg = []
    for idx, d in enumerate(('I', 'II', 'III', 'IV', '0')):
        row = [
            _p(f"<b>{_div_label(d, lang)}</b>", st['td']),
            _p(str(div_counts.get(d, 0)), st['td']),
            _p(pct(div_counts.get(d, 0)), st['td']),
        ]
        div_data.append(row)
        div_row_bg.append((idx + 2, DIV_BG.get(d, WHITE)))
    # Total row
    div_data.append([
        _p(f"<b>{'Total' if lang == 'en' else 'Jumla'}</b>", st['td']),
        _p(f"<b>{N}</b>", st['td_bold']),
        _p("<b>100%</b>", st['td_bold']),
    ])

    col_w_div = [content_w * 0.45, content_w * 0.28, content_w * 0.27]
    div_table = Table(div_data, colWidths=col_w_div)
    div_style = [
        ('SPAN', (0, 0), (2, 0)),  # title spans all cols
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('BACKGROUND', (0, 1), (-1, 1), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), LGRAY),
    ]
    for row_idx, bg in div_row_bg:
        div_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), bg))
    div_table.setStyle(TableStyle(div_style))

    # ── Performance Summary Table ──
    perf_title = "PERFORMANCE SUMMARY" if lang == 'en' else "TAARIFA YA MAENDELEO"
    if lang == 'sw':
        perf_items = [
            ("Wanafunzi", str(N)), ("Wastani Jumla", f"{avg_total:.1f}"),
            ("Wastani Mean", f"{avg_average:.1f}"), ("GPA (Pointi)", f"{avg_points:.2f}"),
            ("Masomo", str(counted)),
        ]
    else:
        perf_items = [
            ("Total Students", str(N)), ("Overall Average", f"{avg_total:.1f}"),
            ("Mean of Averages", f"{avg_average:.1f}"), ("Average Points (GPA)", f"{avg_points:.2f}"),
            ("Subjects", str(counted)),
        ]

    perf_data = [[_p(f"<b>{perf_title}</b>", st['th']), '']]
    for k, v in perf_items:
        perf_data.append([_p(k, st['td']), _p(f"<b>{v}</b>", st['td_bold'])])

    col_w_perf = [content_w * 0.55, content_w * 0.45]
    perf_table = Table(perf_data, colWidths=col_w_perf)
    perf_table.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, -1), (-1, -1), LGRAY),
    ]))

    # Side-by-side: div + perf
    side_data = [[div_table, '', perf_table]]
    side_table = Table(side_data, colWidths=[content_w * 0.48, content_w * 0.04, content_w * 0.48])
    side_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(side_table)
    story.append(Spacer(1, 6))

    # ── Subject Statistics ──
    if subj_stats:
        story.append(_p(f"<b>{get_section_title(exam, 'subject_stats')}</b>", st['section']))
        sh = ["SUBJECT", "AVG", "HIGH", "LOW", "PASS%"] if lang == 'en' else ["SOMO", "WASTANI", "JUU", "CHINI", "KUFAULU"]
        s_data = [[_p(f"<b>{h}</b>", st['th']) for h in sh]]
        for s in subj_stats:
            s_data.append([
                _p(s['name'], st['td']),
                _p(str(s['avg']), st['td']),
                _p(str(s['high']), st['td']),
                _p(str(s['low']), st['td']),
                _p(f"{s['pass_pct']}%", st['td']),
            ])
        col_w_subj = [content_w * 0.36] + [content_w * 0.16] * 4
        s_table = Table(s_data, colWidths=col_w_subj)
        s_style = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]
        for i in range(1, len(s_data)):
            if i % 2 == 0:
                s_style.append(('BACKGROUND', (0, i), (-1, i), CREAM))
        s_table.setStyle(TableStyle(s_style))
        story.append(s_table)
        story.append(Spacer(1, 6))

    # ── Top 5 ──
    if results:
        story.append(_p(f"<b>{get_section_title(exam, 'top_students')}</b>", st['section']))
        th = ["POS", "NAME", "TOTAL", "AVG", "PTS", "DIV"] if lang == 'en' else ["NAFASI", "JINA", "JUMLA", "WASTANI", "POINTI", "DARAJA"]
        t_data = [[_p(f"<b>{h}</b>", st['th']) for h in th]]
        for idx, r in enumerate(results[:5]):
            nm = _student_name(r)
            if len(nm) > 22:
                nm = nm[:20] + '..'
            bold = ' font-weight:bold;' if idx == 0 else ''
            name_style = ParagraphStyle('tn', parent=st['td'], alignment=TA_LEFT)
            t_data.append([
                _p(str(r.position), st['td']),
                _p(nm, name_style),
                _p(str(r.total_score), st['td']),
                _p(f"{r.average_score:.1f}", st['td']),
                _p(str(r.points), st['td']),
                _p(str(r.division), st['td']),
            ])
        col_w_top5 = [content_w * w for w in [0.08, 0.35, 0.13, 0.13, 0.13, 0.18]]
        t_table = Table(t_data, colWidths=col_w_top5)
        t_style = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 1), (-1, 1), GOLD),  # Top 1 gold
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ]
        t_table.setStyle(TableStyle(t_style))
        story.append(t_table)
        story.append(Spacer(1, 6))

    # ── Grading Key ──
    _, grades = _grading_thresholds(exam.form)
    gk_title = "GRADING KEY" if lang == 'en' else "UFUNGUO WA DARAJA"
    story.append(_p(f"<b>{gk_title}</b>", st['section']))
    gk_data = [[
        _p(f"<b>{g} ({rng})</b>", ParagraphStyle(
            'gk', parent=st['td'], textColor=GRADE_FG.get(g, BLACK),
            fontName='Helvetica-Bold', fontSize=7.5,
        ))
        for g, rng in grades
    ]]
    gk_w = content_w / len(grades) if grades else content_w
    gk_table = Table(gk_data, colWidths=[gk_w] * len(grades))
    gk_style = [
        ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]
    for i, (g, _) in enumerate(grades):
        gk_style.append(('BACKGROUND', (i, 0), (i, 0), GRADE_BG.get(g, WHITE)))
    gk_table.setStyle(TableStyle(gk_style))
    story.append(gk_table)

    # ══════════════════════════════════════════════════════════════════════════
    # FULL RESULTS PAGES
    # ══════════════════════════════════════════════════════════════════════════
    story.append(PageBreak())

    rows_per_page = 28 if n_subj <= 5 else 20 if n_subj <= 8 else 12
    chunks = [results[i:i + rows_per_page] for i in range(0, N, rows_per_page)]
    total_pages = len(chunks) or 1

    for pg_idx, chunk in enumerate(chunks, 1):
        # Page title
        result_title = f"{school_disp} — {etype} {exam.year} — FORM {exam.form}"
        story.append(_p(result_title, st['page_title']))
        story.append(_p(f"{exam.name} | PAGE {pg_idx}/{total_pages}", st['page_sub']))

        # Build header row
        r_hdr_labels = ["#", "NAME", "S"]
        r_hdr_labels += [s.name.upper()[:8] for s in subjects]
        r_hdr_labels += ["TOTAL", "AVG", "PTS", "GPA", "DIV"]

        data = [[_p(f"<b>{h}</b>", st['th_sm']) for h in r_hdr_labels]]

        for r in chunk:
            nm = _student_name(r)
            max_nm = 10 if n_subj >= 10 else 14 if n_subj >= 8 else 18
            if len(nm) > max_nm:
                nm = nm[:max_nm - 2] + '..'

            name_st = st['td_name_sm'] if n_subj >= 9 else st['td_name']
            cell_st = st['td_sm'] if n_subj >= 9 else st['td']

            row = [
                _p(str(r.position), cell_st),
                _p(nm, name_st),
                _p(r.student.gender or 'M', cell_st),
            ]

            for sub in subjects:
                sc = score_lookup.get((r.student_id, sub.id))
                if sc is not None:
                    g = _grade_for_score(sc, exam.form)
                    bg = GRADE_BG.get(g, WHITE)
                    fg = GRADE_FG.get(g, BLACK)
                    sc_style = ParagraphStyle(
                        'sc', parent=cell_st,
                        backColor=bg, textColor=fg,
                        fontName='Helvetica-Bold' if g in ('A', 'F') else 'Helvetica',
                    )
                    row.append(_p(str(sc), sc_style))
                else:
                    row.append(_p('-', cell_st))

            c_counted = [s for s in (r.counted_subjects or '').split(',') if s.strip()]
            nc = len(c_counted) if c_counted else n_subj
            gpa = r.points / nc if nc else 0

            div_bg = DIV_BG.get(r.division, WHITE)
            div_fg = DIV_FG.get(r.division, BLACK)
            div_st = ParagraphStyle(
                'dv', parent=cell_st, backColor=div_bg, textColor=div_fg,
                fontName='Helvetica-Bold',
            )

            row.extend([
                _p(str(r.total_score), st['td_bold']),
                _p(f"{r.average_score:.1f}", cell_st),
                _p(str(r.points), cell_st),
                _p(f"{gpa:.2f}", cell_st),
                _p(str(r.division), div_st),
            ])
            data.append(row)

        # Column widths
        fixed_cols = [0.05, 0.16, 0.03]  # #, NAME, S
        subj_total = 0.52
        subj_each = subj_total / max(n_subj, 1)
        tail_cols = [0.05, 0.04, 0.04, 0.04, 0.07]  # TOTAL, AVG, PTS, GPA, DIV
        all_cols = fixed_cols + [subj_each] * n_subj + tail_cols

        # Scale to fit content_w
        total_frac = sum(all_cols)
        all_cols = [f / total_frac * content_w for f in all_cols]

        r_table = Table(data, colWidths=all_cols, repeatRows=1)
        r_style = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.3, LGRAY),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('LEFTPADDING', (0, 0), (-1, -1), 1),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1),
        ]
        # Zebra rows
        for i in range(1, len(data)):
            if i % 2 == 0:
                r_style.append(('BACKGROUND', (0, i), (-1, i), CREAM))
        r_table.setStyle(TableStyle(r_style))
        story.append(r_table)
        story.append(Spacer(1, 8))

        # Grading key on each results page
        gk_data_pg = [[
            _p(f"<b>{g} ({rng})</b>", ParagraphStyle(
                'gk2', parent=st['td'], textColor=GRADE_FG.get(g, BLACK),
                fontName='Helvetica-Bold', fontSize=7,
            ))
            for g, rng in grades
        ]]
        gk_table_pg = Table(gk_data_pg, colWidths=[content_w / len(grades)] * len(grades))
        gk_s = [
            ('GRID', (0, 0), (-1, -1), 0.3, LGRAY),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]
        for i, (g, _) in enumerate(grades):
            gk_s.append(('BACKGROUND', (i, 0), (i, 0), GRADE_BG.get(g, WHITE)))
        gk_table_pg.setStyle(TableStyle(gk_s))
        story.append(gk_table_pg)
        story.append(Spacer(1, 10))

        # Signature area
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
        sig_table = Table(sig_data, colWidths=[content_w * 0.42, content_w * 0.16, content_w * 0.42])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(sig_table)
        story.append(_p('Date: _________________________________', ParagraphStyle(
            'dt', parent=st['sig'], alignment=TA_LEFT, spaceBefore=4,
        )))

        # Page break between result pages
        if pg_idx < total_pages:
            story.append(PageBreak())

    # ── Build PDF ──
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=margin_top,
        bottomMargin=margin_bot,
        leftMargin=margin_lr,
        rightMargin=margin_lr,
        title=f"{school_disp} — {etype} {exam.year}",
    )
    doc._exam = exam  # for footer access

    doc.build(story, onFirstPage=_first_page_footer, onLaterPages=_later_pages_footer)

    buf.seek(0)
    resp = HttpResponse(buf, content_type='application/pdf')
    safe_name = exam.name.replace(" ", "_")
    resp['Content-Disposition'] = f'attachment; filename="{safe_name}_Results.pdf"'
    return resp
