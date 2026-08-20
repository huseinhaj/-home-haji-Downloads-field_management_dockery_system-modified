"""
Professional NECTA Academic Results PDF — Pure ReportLab.
International-standard layout. No overlapping, no text cutting.
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
    return {
        'page_title': ParagraphStyle(
            'page_title', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=11, alignment=TA_CENTER,
            textColor=NAVY, spaceBefore=2, spaceAfter=1,
        ),
        'page_sub': ParagraphStyle(
            'page_sub', parent=ss['Normal'],
            fontName='Helvetica', fontSize=7.5, alignment=TA_CENTER,
            textColor=SLATE, spaceAfter=6,
        ),
        'section': ParagraphStyle(
            'section', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=10, textColor=GREEN,
            spaceBefore=8, spaceAfter=4,
        ),
        # Table headers — used inside Paragraph cells
        'th': ParagraphStyle(
            'th', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=8, alignment=TA_CENTER,
            textColor=colors.white, leading=10,
        ),
        'th_sm': ParagraphStyle(
            'th_sm', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=7, alignment=TA_CENTER,
            textColor=colors.white, leading=9,
        ),
        # Table cells
        'td': ParagraphStyle(
            'td', parent=ss['Normal'],
            fontName='Helvetica', fontSize=8, alignment=TA_CENTER,
            leading=10,
        ),
        'td_sm': ParagraphStyle(
            'td_sm', parent=ss['Normal'],
            fontName='Helvetica', fontSize=7, alignment=TA_CENTER,
            leading=9,
        ),
        'td_name': ParagraphStyle(
            'td_name', parent=ss['Normal'],
            fontName='Helvetica', fontSize=8, alignment=TA_LEFT,
            leading=10,
        ),
        'td_name_sm': ParagraphStyle(
            'td_name_sm', parent=ss['Normal'],
            fontName='Helvetica', fontSize=7, alignment=TA_LEFT,
            leading=9,
        ),
        'td_bold': ParagraphStyle(
            'td_bold', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=8, alignment=TA_CENTER,
            leading=10,
        ),
        'td_bold_sm': ParagraphStyle(
            'td_bold_sm', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=7, alignment=TA_CENTER,
            leading=9,
        ),
        'sig': ParagraphStyle(
            'sig', parent=ss['Normal'],
            fontName='Helvetica', fontSize=8, alignment=TA_CENTER,
            textColor=SLATE, leading=11,
        ),
        'footer': ParagraphStyle(
            'footer', parent=ss['Normal'],
            fontName='Helvetica', fontSize=6.5, alignment=TA_CENTER,
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


def _safe_b64_img(data_uri, x, y, w, h, canvas):
    """Draw a base64 image on canvas."""
    if not data_uri or not data_uri.startswith('data:'):
        return
    try:
        import base64 as _b64
        b64_part = data_uri.split(',', 1)[1]
        img_data = _b64.b64decode(b64_part)
        img_buf = io.BytesIO(img_data)
        from reportlab.lib.utils import ImageReader
        img = ImageReader(img_buf)
        canvas.drawImage(img, x, y, width=w, height=h,
                         preserveAspectRatio=True, mask='auto')
    except Exception:
        pass


# ── Header Flowable ──────────────────────────────────────────────────────────
class NECTAHeader(Flowable):
    """Custom flowable that draws the green banner + logos + text on first page."""
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

        # Text
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

        # Tanzania flag strip
        strip_y = -3
        strip_h = 3
        for i, col in enumerate([TZ_GREEN, TZ_YELLOW, TZ_BLACK, TZ_BLUE]):
            c.setFillColor(col)
            c.rect(i * w / 4, strip_y, w / 4, strip_h, fill=1, stroke=0)

        # School name
        c.setFillColor(GOLD)
        c.setFont('Helvetica-Bold', 13)
        c.drawCentredString(cx, strip_y - 16, self.school_disp)

        # Location
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
    # Detect current page size (portrait or landscape)
    try:
        w, _ = doc.pagesize
    except Exception:
        w = A4[0]
    canvas.setFont('Helvetica', 6.5)
    canvas.setFillColor(SLATE)
    canvas.drawString(doc.leftMargin, 0.7 * cm,
                      get_full_school_name(doc._exam))
    canvas.drawCentredString(w / 2, 0.7 * cm,
                             f"Page {canvas.getPageNumber()}")
    canvas.drawRightString(w - doc.rightMargin, 0.7 * cm,
                           datetime.now().strftime('%d/%m/%Y at %H:%M'))
    canvas.setStrokeColor(DARK_LINE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 1.05 * cm, w - doc.rightMargin, 1.05 * cm)
    canvas.restoreState()


def _first_page_footer(canvas, doc):
    _footer(canvas, doc)


def _later_pages_footer(canvas, doc):
    _footer(canvas, doc)


# ══════════════════════════════════════════════════════════════════════════════
# BUILD PDF
# ══════════════════════════════════════════════════════════════════════════════
def generate_results_pdf_response(exam):
    st = _styles()
    school_disp = get_full_school_name(exam)
    lang = get_report_language(exam)
    etype = exam.get_exam_type_display().upper()
    rlabel = get_report_label(exam)

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

    # ── Stats ──
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

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 1: SUMMARY (A4 Portrait)
    # ════════════════════════════════════════════════════════════════════════
    page_w, page_h = A4
    margin_lr = 1.8 * cm
    margin_top = 0.8 * cm
    margin_bot = 1.4 * cm
    content_w = page_w - 2 * margin_lr

    story = []
    story.append(NECTAHeader(exam, school_disp, slogo_uri, dlogo_uri, stype, lang))
    story.append(Spacer(1, 4))

    # Title
    page_title = f"{etype} {exam.year} — FORM {exam.form}" if lang == 'en' else rlabel
    story.append(_p(page_title, st['page_title']))
    story.append(_p(exam.name, st['page_sub']))

    # ── Division Summary ──
    div_title = get_section_title(exam, 'division_summary')
    d_hdr = "DIVISION" if lang == 'en' else "DARAJA"
    d_cnt = "COUNT" if lang == 'en' else "IDADI"

    div_data = [
        [_p(f"<b>{div_title}</b>", st['th']), '', ''],
        [_p(f"<b>{d_hdr}</b>", st['th']),
         _p(f"<b>{d_cnt}</b>", st['th']),
         _p("<b>%</b>", st['th'])],
    ]
    div_row_bg = []
    for idx, d in enumerate(('I', 'II', 'III', 'IV', '0')):
        div_data.append([
            _p(f"<b>{_div_label(d, lang)}</b>", st['td']),
            _p(str(div_counts.get(d, 0)), st['td']),
            _p(pct(div_counts.get(d, 0)), st['td']),
        ])
        div_row_bg.append((idx + 2, DIV_BG.get(d, WHITE)))
    div_data.append([
        _p(f"<b>{'Total' if lang == 'en' else 'Jumla'}</b>", st['td']),
        _p(f"<b>{N}</b>", st['td_bold']),
        _p("<b>100%</b>", st['td_bold']),
    ])

    cw_div = [content_w * 0.45, content_w * 0.28, content_w * 0.27]
    div_table = Table(div_data, colWidths=cw_div)
    ds = [
        ('SPAN', (0, 0), (2, 0)),
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('BACKGROUND', (0, 1), (-1, 1), NAVY),
        ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, -1), (-1, -1), LGRAY),
    ]
    for ri, bg in div_row_bg:
        ds.append(('BACKGROUND', (0, ri), (-1, ri), bg))
    div_table.setStyle(TableStyle(ds))

    # ── Performance Summary ──
    perf_title = "PERFORMANCE SUMMARY" if lang == 'en' else "TAARIFA YA MAENDELEO"
    if lang == 'sw':
        perf_items = [("Wanafunzi", str(N)), ("Wastani Jumla", f"{avg_total:.1f}"),
                      ("Wastani Mean", f"{avg_average:.1f}"), ("GPA (Pointi)", f"{avg_points:.2f}"),
                      ("Masomo", str(counted))]
    else:
        perf_items = [("Total Students", str(N)), ("Overall Average", f"{avg_total:.1f}"),
                      ("Mean of Averages", f"{avg_average:.1f}"), ("Average Points (GPA)", f"{avg_points:.2f}"),
                      ("Subjects", str(counted))]

    perf_data = [[_p(f"<b>{perf_title}</b>", st['th']), '']]
    for k, v in perf_items:
        perf_data.append([_p(k, st['td']), _p(f"<b>{v}</b>", st['td_bold'])])

    cw_perf = [content_w * 0.55, content_w * 0.45]
    perf_table = Table(perf_data, colWidths=cw_perf)
    perf_table.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, -1), (-1, -1), LGRAY),
    ]))

    # Side-by-side
    side_table = Table(
        [[div_table, '', perf_table]],
        colWidths=[content_w * 0.48, content_w * 0.04, content_w * 0.48],
    )
    side_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(side_table)
    story.append(Spacer(1, 8))

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
        cw_s = [content_w * 0.36] + [content_w * 0.16] * 4
        s_table = Table(s_data, colWidths=cw_s)
        s_style = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]
        for i in range(1, len(s_data)):
            if i % 2 == 0:
                s_style.append(('BACKGROUND', (0, i), (-1, i), CREAM))
        s_table.setStyle(TableStyle(s_style))
        story.append(s_table)
        story.append(Spacer(1, 8))

    # ── Top 5 ──
    if results:
        story.append(_p(f"<b>{get_section_title(exam, 'top_students')}</b>", st['section']))
        th = ["POS", "NAME", "TOTAL", "AVG", "PTS", "DIV"] if lang == 'en' else ["NAFASI", "JINA", "JUMLA", "WASTANI", "POINTI", "DARAJA"]
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
        t_style = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 1), (-1, 1), GOLD),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ]
        t_table.setStyle(TableStyle(t_style))
        story.append(t_table)
        story.append(Spacer(1, 8))

    # ── Grading Key ──
    _, grades = _grading_thresholds(exam.form)
    gk_title = "GRADING KEY" if lang == 'en' else "UFUNGUO WA DARAJA"
    story.append(_p(f"<b>{gk_title}</b>", st['section']))
    gk_cells = [
        _p(f"<b>{g} ({rng})</b>", ParagraphStyle(
            f'gk_{g}', parent=st['td'], textColor=GRADE_FG.get(g, BLACK),
            fontName='Helvetica-Bold', fontSize=8,
        ))
        for g, rng in grades
    ]
    gk_table = Table([gk_cells], colWidths=[content_w / len(grades)] * len(grades))
    gk_style = [
        ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    for i, (g, _) in enumerate(grades):
        gk_style.append(('BACKGROUND', (i, 0), (i, 0), GRADE_BG.get(g, WHITE)))
    gk_table.setStyle(TableStyle(gk_style))
    story.append(gk_table)

    # ════════════════════════════════════════════════════════════════════════
    # RESULTS PAGES (A4 Landscape — more horizontal space)
    # ════════════════════════════════════════════════════════════════════════
    story.append(NextPageTemplate('landscape'))
    story.append(PageBreak())

    # Landscape margins
    land_w, land_h = landscape(A4)
    land_margin_lr = 1.2 * cm
    land_top = 0.8 * cm
    land_bot = 1.4 * cm
    land_content_w = land_w - 2 * land_margin_lr

    # Decide font size based on number of columns
    n_cols = n_subj + 8  # #, NAME, S, [subjects], TOTAL, AVG, PTS, GPA, DIV
    if n_cols <= 14:
        fs_cell = 8
        fs_hdr = 8
        fs_name = 8
        use_sm = False
    elif n_cols <= 18:
        fs_cell = 7
        fs_hdr = 7
        fs_name = 7
        use_sm = True
    else:
        fs_cell = 6
        fs_hdr = 6
        fs_name = 6
        use_sm = True

    cell_style = st['td_sm'] if use_sm else st['td']
    hdr_style = st['th_sm'] if use_sm else st['th']
    name_style = st['td_name_sm'] if use_sm else st['td_name']
    bold_style = st['td_bold_sm'] if use_sm else st['td_bold']

    rows_per_page = 30 if n_subj <= 5 else 24 if n_subj <= 8 else 16
    chunks = [results[i:i + rows_per_page] for i in range(0, N, rows_per_page)]
    total_pages = len(chunks) or 1

    for pg_idx, chunk in enumerate(chunks, 1):
        result_title = f"{school_disp} — {etype} {exam.year} — FORM {exam.form}"
        story.append(_p(result_title, st['page_title']))
        story.append(_p(f"{exam.name}  |  PAGE {pg_idx} of {total_pages}", st['page_sub']))

        # Build data
        r_hdr = ["#", "NAME", "S"]
        r_hdr += [s.name.upper()[:10] for s in subjects]
        r_hdr += ["TOTAL", "AVG", "PTS", "GPA", "DIV"]

        data = [[_p(f"<b>{h}</b>", hdr_style) for h in r_hdr]]

        for r in chunk:
            nm = _student_name(r)
            max_nm = 16 if n_subj >= 10 else 20 if n_subj >= 8 else 24
            if len(nm) > max_nm:
                nm = nm[:max_nm - 2] + '..'

            row = [
                _p(str(r.position), cell_style),
                _p(nm, name_style),
                _p(r.student.gender or 'M', cell_style),
            ]

            for sub in subjects:
                sc = score_lookup.get((r.student_id, sub.id))
                if sc is not None:
                    g = _grade_for_score(sc, exam.form)
                    bg = GRADE_BG.get(g, WHITE)
                    fg = GRADE_FG.get(g, BLACK)
                    sc_st = ParagraphStyle(
                        f'sc_{r.student_id}_{sub.id}', parent=cell_style,
                        backColor=bg, textColor=fg,
                        fontName='Helvetica-Bold' if g in ('A', 'F') else 'Helvetica',
                    )
                    row.append(_p(str(sc), sc_st))
                else:
                    row.append(_p('-', cell_style))

            c_counted = [s for s in (r.counted_subjects or '').split(',') if s.strip()]
            nc = len(c_counted) if c_counted else n_subj
            gpa = r.points / nc if nc else 0

            div_bg = DIV_BG.get(r.division, WHITE)
            div_fg = DIV_FG.get(r.division, BLACK)
            div_st = ParagraphStyle(
                f'dv_{r.student_id}', parent=cell_style,
                backColor=div_bg, textColor=div_fg,
                fontName='Helvetica-Bold',
            )

            row.extend([
                _p(str(r.total_score), bold_style),
                _p(f"{r.average_score:.1f}", cell_style),
                _p(str(r.points), cell_style),
                _p(f"{gpa:.2f}", cell_style),
                _p(str(r.division), div_st),
            ])
            data.append(row)

        # ── Column widths: proportional to available space ──
        # Fixed columns: #, NAME, S, TOTAL, AVG, PTS, GPA, DIV
        # Subject columns: share the remaining space equally
        fixed_total_frac = 0.06 + 0.18 + 0.03 + 0.06 + 0.05 + 0.05 + 0.05 + 0.07  # = 0.55
        subj_frac_each = (1.0 - fixed_total_frac) / max(n_subj, 1)

        col_fracs = (
            [0.06, 0.18, 0.03]  # #, NAME, S
            + [subj_frac_each] * n_subj
            + [0.06, 0.05, 0.05, 0.05, 0.07]  # TOTAL, AVG, PTS, GPA, DIV
        )
        # Normalize
        total_f = sum(col_fracs)
        col_widths = [f / total_f * land_content_w for f in col_fracs]

        r_table = Table(data, colWidths=col_widths, repeatRows=1)
        rs = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('GRID', (0, 0), (-1, -1), 0.3, DARK_LINE),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            # Extra left padding for NAME column
            ('LEFTPADDING', (1, 0), (1, -1), 4),
        ]
        for i in range(1, len(data)):
            if i % 2 == 0:
                rs.append(('BACKGROUND', (0, i), (-1, i), CREAM))
        r_table.setStyle(TableStyle(rs))
        story.append(r_table)
        story.append(Spacer(1, 8))

        # Grading key (compact)
        gk_cells_pg = [
            _p(f"<b>{g} ({rng})</b>", ParagraphStyle(
                f'gk2_{g}', parent=cell_style, textColor=GRADE_FG.get(g, BLACK),
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

        # Signature area
        sig_data = [[
            [_p('<hr width="100%"/>', st['sig']),
             _p('<b>Signature &amp; Stamp</b>', st['sig']),
             _p('Academic Officer', st['sig'])],
            '',
            [_p('<hr width="100%"/>', st['sig']),
             _p('<b>Signature &amp; Stamp</b>', st['sig']),
             _p('Head of School', st['sig'])],
        ]]
        sig_table = Table(sig_data, colWidths=[land_content_w * 0.42, land_content_w * 0.16, land_content_w * 0.42])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(sig_table)
        story.append(Spacer(1, 4))
        story.append(_p('Date: _________________________________', ParagraphStyle(
            'dt', parent=st['sig'], alignment=TA_LEFT,
        )))

        if pg_idx < total_pages:
            story.append(PageBreak())

    # ── Build with BaseDocTemplate (portrait summary + landscape results) ──
    buf = io.BytesIO()

    # Portrait frame (summary page)
    portrait_frame = Frame(
        margin_lr, margin_bot, content_w, page_h - margin_top - margin_bot,
        id='portrait',
    )
    # Landscape frame (results pages)
    land_w, land_h = landscape(A4)
    land_margin_lr = 1.2 * cm
    land_content_w = land_w - 2 * land_margin_lr
    landscape_frame = Frame(
        land_margin_lr, land_bot, land_content_w, land_h - land_top - land_bot,
        id='landscape',
    )

    # Page templates
    portrait_tmpl = PageTemplate(
        id='portrait', frames=[portrait_frame], pagesize=A4,
        onPage=_first_page_footer,
    )
    landscape_tmpl = PageTemplate(
        id='landscape', frames=[landscape_frame],
        pagesize=landscape(A4),
        onPage=_later_pages_footer,
    )

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        title=f"{school_disp} — {etype} {exam.year}",
        pageTemplates=[portrait_tmpl, landscape_tmpl],
    )
    doc._exam = exam
    doc.build(story)

    buf.seek(0)
    resp = HttpResponse(buf, content_type='application/pdf')
    safe_name = exam.name.replace(" ", "_")
    resp['Content-Disposition'] = f'attachment; filename="{safe_name}_Results.pdf"'
    return resp
