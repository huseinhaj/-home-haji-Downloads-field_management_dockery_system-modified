"""
Professional Academic Results PDF — Pure ReportLab.
All pages A4 Portrait. NECTA-style layout. Pages fully filled with results.
Each results page has its own Table (no ReportLab splitting issues).
"""
import io
import os
import base64
from collections import Counter, defaultdict
from datetime import datetime

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase.pdfmetrics import getAscent
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Table, TableStyle, Paragraph, Spacer, PageBreak,
    Flowable,
)

from ..models import ExamResult, ProcessedResult, Subject
from .export_data import get_exam_export_payload
from .report_helpers import (
    get_full_school_name, get_report_label, get_report_language,
    get_section_title, get_school_type_for_exam,
)

# ── Colours — modern flat palette (blue/emerald/amber) ────────────────────────
NAVY      = colors.HexColor("#1D4ED8")  # vivid modern blue (was muted navy)
DARK_NAVY = colors.HexColor("#1E3A8A")  # deep blue for contrast accents
GREEN     = colors.HexColor("#15803D")  # clean modern green (PMO banner)
GOLD      = colors.HexColor("#F59E0B")  # vivid amber (was dull goldenrod)
CREAM     = colors.HexColor("#F8FAFC")  # cool neutral row tint (was warm cream)
SLATE     = colors.HexColor("#475569")  # modern slate gray for muted text
LGRAY     = colors.HexColor("#CBD5E1")  # light slate — grid lines
MGRAY     = colors.HexColor("#F1F5F9")  # subtle slate surface tint
TINT      = colors.HexColor("#EFF6FF")  # light blue card behind the title block
WHITE     = colors.white
BLACK     = colors.black
DARK_LINE = colors.HexColor("#94A3B8")  # medium slate — page border/dividers

TZ_GREEN  = colors.HexColor("#00A651")
TZ_YELLOW = colors.HexColor("#FCD116")
TZ_BLACK  = colors.black
TZ_BLUE   = colors.HexColor("#00A3DD")

GRADE_BG = {
    'A':  colors.HexColor("#DCFCE7"),
    'B':  colors.HexColor("#D1FAE5"),
    'C':  colors.HexColor("#FEF3C7"),
    'D':  colors.HexColor("#FFEDD5"),
    'E':  colors.HexColor("#FFEDD5"), 'S':  colors.HexColor("#FEF3C7"),
    'F':  colors.HexColor("#FEE2E2"),
}
GRADE_FG = {
    'A':  colors.HexColor("#15803D"),
    'B':  colors.HexColor("#047857"),
    'C':  colors.HexColor("#B45309"),
    'D':  colors.HexColor("#C2410C"),
    'E':  colors.HexColor("#C2410C"), 'S':  colors.HexColor("#B45309"),
    'F':  colors.HexColor("#B91C1C"),
}
DIV_BG = {
    'I':   colors.HexColor("#DCFCE7"), 'II':  colors.HexColor("#CFFAFE"),
    'III': colors.HexColor("#FEF3C7"), 'IV':  colors.HexColor("#FFEDD5"),
    '0':   colors.HexColor("#FEE2E2"),
}
DIV_FG = {
    'I':   colors.HexColor("#15803D"), 'II':  colors.HexColor("#0E7490"),
    'III': colors.HexColor("#B45309"), 'IV':  colors.HexColor("#C2410C"),
    '0':   colors.HexColor("#B91C1C"),
}

GRADE_COLORS = {
    'A':  ('#15803D', '#DCFCE7'),
    'B':  ('#047857', '#D1FAE5'),
    'C':  ('#B45309', '#FEF3C7'),
    'D':  ('#C2410C', '#FFEDD5'),
    'E':  ('#C2410C', '#FFEDD5'),
    'S':  ('#B45309', '#FEF3C7'),
    'F':  ('#B91C1C', '#FEE2E2'),
    'X':  ('#475569', '#F1F5F9'),
}

LEVEL_COLORS = {
    'Grade A': ('#15803D', '#DCFCE7'),
    'Grade B': ('#047857', '#D1FAE5'),
    'Grade C': ('#B45309', '#FEF3C7'),
    'Grade D': ('#C2410C', '#FFEDD5'),
    'Grade E': ('#C2410C', '#FFEDD5'),
    'Grade S': ('#B45309', '#FEF3C7'),
    'Grade F': ('#B91C1C', '#FEE2E2'),
}


# ── Styles ───────────────────────────────────────────────────────────────────
def _styles():
    ss = getSampleStyleSheet()
    s = {}
    for name, fn, sz, al, clr, sb, sa in [
        ('title_lg',   'Helvetica-Bold', 14, TA_CENTER, NAVY,  0, 1),
        ('title_md',   'Helvetica-Bold', 11, TA_CENTER, NAVY,  0, 1),
        ('subtitle',   'Helvetica',       9, TA_CENTER, SLATE, 0, 4),
        ('section',    'Helvetica-Bold', 10, TA_LEFT,   NAVY,  8, 3),
        ('th',         'Helvetica-Bold',  8, TA_CENTER, WHITE, 0, 0),
        ('th_sm',      'Helvetica-Bold',  7, TA_CENTER, WHITE, 0, 0),
        ('td',         'Helvetica',       8, TA_CENTER, BLACK, 0, 0),
        ('td_sm',      'Helvetica',       7, TA_CENTER, BLACK, 0, 0),
        ('td_name',    'Helvetica',       8, TA_LEFT,   BLACK, 0, 0),
        ('td_bold',    'Helvetica-Bold',  8, TA_CENTER, BLACK, 0, 0),
        ('td_bold_sm', 'Helvetica-Bold',  7, TA_CENTER, BLACK, 0, 0),
        ('sig',        'Helvetica',       8, TA_CENTER, SLATE, 0, 0),
        ('footer',     'Helvetica',     6.5, TA_CENTER, SLATE, 0, 0),
    ]:
        s[name] = ParagraphStyle(name, parent=ss['Normal'], fontName=fn,
                                 fontSize=sz, alignment=al, textColor=clr,
                                 spaceBefore=sb, spaceAfter=sa, leading=sz + 3)
    return s


# ── Grading ──────────────────────────────────────────────────────────────────
def _grading_thresholds(form):
    """CSEE and FTNA share the same 5-band A/B/C/D/F scale — verified
    against real NECTA CSEE result slips, which never show B+/C+."""
    if form == 2:
        return [75, 65, 45, 30], [('A','75-100'),('B','65-74'),('C','45-64'),('D','30-44'),('F','0-29')]
    if form in (5, 6):
        return [80, 70, 60, 50, 40, 35], [('A','80-100'),('B','70-79'),('C','60-69'),('D','50-59'),('E','40-49'),('S','35-39'),('F','0-34')]
    return [75, 65, 45, 30], [('A','75-100'),('B','65-74'),('C','45-64'),('D','30-44'),('F','0-29')]


def _grade_for_score(score, form=4):
    if score is None or not isinstance(score, (int, float)):
        return None
    th, gr = _grading_thresholds(form)
    for i, t in enumerate(th):
        if score >= t:
            return gr[i][0]
    return gr[-1][0]


def _grade_point(grade, form=4):
    if form in (5, 6):
        gp_map = {'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'S': 6, 'F': 7}
    else:
        gp_map = {'A': 1, 'B': 2, 'C': 3, 'D': 4, 'F': 5}
    return gp_map.get(grade, max(gp_map.values()))


def _centre_counted_subjects(results, form):
    """How many subjects the division counts, for the centre GPA line.

    NECTA fixes this: best 7 for CSEE / FTNA (Form 1-4), best 3 (the
    combination) for ACSEE (Form 5-6). Use the real per-candidate count
    when the ProcessedResult rows carry it (widest across candidates — a
    full candidate has them all), else fall back to the NECTA standard.
    Never 0 — an empty first row used to zero out every GPA on the sheet.
    """
    necta_standard = 3 if form in (5, 6) else 7
    widest = max(
        (len([s for s in (r.counted_subjects or '').split(',') if s.strip()])
         for r in results),
        default=0,
    )
    return widest or necta_standard


# ── Helpers ──────────────────────────────────────────────────────────────────
def _load_logo_b64(field, b64_field_value=''):
    """Load logo — first try base64 stored in DB, then fallback to ImageField.
    If ImageField has data, auto-save it as base64 for next time.
    Returns '' if nothing found — never raises."""
    # Priority 1: base64 stored directly in DB (persists on Railway)
    if b64_field_value and b64_field_value.startswith('data:'):
        return b64_field_value
    # Priority 2: ImageField on disk — read AND save to DB for next time
    if not field:
        return ''
    try:
        storage = field.storage
        if not storage.exists(field.name):
            return ''
        field.open('rb')
        data = field.read()
        field.close()
        if not data:
            return ''
        ext = os.path.splitext(str(field.name))[1].lower()
        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg', '.gif': 'image/gif',
                    '.svg': 'image/svg+xml'}
        mime = mime_map.get(ext, 'image/png')
        b64 = base64.b64encode(data).decode('ascii')
        data_uri = f'data:{mime};base64,{b64}'
        # Auto-save to DB so next time it's instant
        try:
            if hasattr(field, 'instance') and field.instance:
                model = field.instance.__class__
                field_name = field.field.name
                b64_field = f'{field_name}_b64'
                if hasattr(field.instance, b64_field):
                    setattr(field.instance, b64_field, data_uri)
                    field.instance.save(update_fields=[b64_field])
        except Exception:
            pass  # best effort — don't break PDF generation
        return data_uri
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
    """Draw a base64 image on canvas. Silently skips on any error."""
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


def _std_table_style(n_rows, header_bg=None):
    hdr = header_bg or NAVY
    s = [
        ('BACKGROUND', (0, 0), (-1, 0), hdr),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]
    for i in range(1, n_rows):
        if i % 2 == 0:
            s.append(('BACKGROUND', (0, i), (-1, i), CREAM))
    return s


# ── Header Flowable ──────────────────────────────────────────────────────────
class NECTAHeader(Flowable):
    """Official header with green banner, logos, flag strip:
    PRIME MINISTER'S OFFICE
    REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT
    [School Logo] [Coat of Arms] [District Logo]
    Flag strip
    KYERWA DISTRICT COUNCIL
    FORM THREE MID-TERM EXAMINATION RESULTS
    SEPTEMBER-2026
    ISINGIRO SECONDARY SCHOOL
    """
    BANNER_H = 38
    LOGOS_H = 44
    BELOW_H = 68

    def __init__(self, exam, school_disp, slogo_uri, dlogo_uri, stype, lang, exam_title='', form_num=4, exam_month='', district='', coa_uri=''):
        Flowable.__init__(self)
        self.exam = exam
        self.school_disp = school_disp
        self.slogo_uri = slogo_uri
        self.dlogo_uri = dlogo_uri
        self.stype = stype
        self.lang = lang
        self.exam_title = exam_title
        self.form_num = form_num
        self.exam_month = exam_month
        self.district = district
        self.coa_uri = coa_uri
        self.width = A4[0] - 3.2 * cm
        self.height = self.BANNER_H + self.LOGOS_H + self.BELOW_H  # 145pt

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        cx = w / 2

        # ── 1. GREEN BACKGROUND — banner + logos row, full down to the flag strip ──
        banner_y = self.BELOW_H + self.LOGOS_H
        logos_y = self.BELOW_H
        strip_y = logos_y - 2
        strip_top = strip_y + 3

        # Light tint card behind the district/title/school-name block below
        # the flag strip, so that block reads as a distinct panel rather
        # than plain white page background.
        c.setFillColor(TINT)
        c.rect(0, 0, w, logos_y, fill=1, stroke=0)

        c.setFillColor(GREEN)
        c.roundRect(0, strip_top, w, h - strip_top, 3, fill=1, stroke=0)

        # ── PMO + Regional Admin text (on the green background) ──
        pmo_text = "PRIME MINISTER'S OFFICE"
        pmo_font, pmo_size = 'Helvetica-Bold', 9
        pmo_y = banner_y + self.BANNER_H - 14
        c.setFillColor(colors.white)
        c.setFont(pmo_font, pmo_size)
        c.drawCentredString(cx, pmo_y, pmo_text)
        c.setFont('Helvetica-Bold', 7)
        c.drawCentredString(cx, banner_y + self.BANNER_H - 26, "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT")

        # ── 2. LOGOS ROW — School (left) + Coat of Arms (center) + District (right) ──
        # Nudged up within the green band so the gap to the flag strip below
        # matches the gap to the PMO text above, instead of sitting low.
        # The Coat of Arms sits centered, directly under the PMO/Regional
        # Admin text, and is drawn a little larger than the side logos so
        # it reads as the primary emblem rather than a third equal logo.
        logo_sz = 40
        logo_y = logos_y + 12
        coa_sz = 46
        coa_y = logo_y - (coa_sz - logo_sz) / 2  # keep it vertically centred on the same midline

        # Decorative rays: from the top-inner corner of each side logo up
        # to the TOP of the PMO title's first/last letter — school logo's
        # top-right corner to the top of "P" (PRIME), district logo's
        # top-left corner to the top of "E" (OFFICE).
        pmo_w = c.stringWidth(pmo_text, pmo_font, pmo_size)
        pmo_left_x = cx - pmo_w / 2
        pmo_right_x = cx + pmo_w / 2
        pmo_top_y = pmo_y + getAscent(pmo_font) / 1000.0 * pmo_size
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.9)
        c.line(2 + logo_sz, logo_y + logo_sz, pmo_left_x, pmo_top_y)
        c.line(w - logo_sz - 2, logo_y + logo_sz, pmo_right_x, pmo_top_y)

        # White badge disc with a thin gold ring behind the LEFT and RIGHT
        # logos only, so they pop against the green instead of sitting
        # flat on it (the centre Coat of Arms stays plain — it's already
        # the larger, primary emblem).
        badge_r = logo_sz / 2 + 4
        for badge_cx in (2 + logo_sz / 2, w - logo_sz / 2 - 2):
            badge_cy = logo_y + logo_sz / 2
            c.setFillColor(colors.white)
            c.setStrokeColor(GOLD)
            c.setLineWidth(1.2)
            c.circle(badge_cx, badge_cy, badge_r, fill=1, stroke=1)

        # School logo — left
        if self.slogo_uri:
            _safe_b64_img(self.slogo_uri, 2, logo_y, logo_sz, logo_sz, c)
        # Coat of Arms — center, larger, as the primary emblem
        if self.coa_uri:
            _safe_b64_img(self.coa_uri, cx - coa_sz / 2, coa_y, coa_sz, coa_sz, c)
        elif self.dlogo_uri:
            _safe_b64_img(self.dlogo_uri, cx - coa_sz / 2, coa_y, coa_sz, coa_sz, c)
        # District logo — right
        if self.dlogo_uri:
            _safe_b64_img(self.dlogo_uri, w - logo_sz - 2, logo_y, logo_sz, logo_sz, c)

        # ── 3. FLAG STRIP ──
        for i, col in enumerate([TZ_GREEN, TZ_YELLOW, TZ_BLACK, TZ_BLUE]):
            c.setFillColor(col)
            c.rect(i * w / 4, strip_y, w / 4, 3, fill=1, stroke=0)

        # ── 4. DISTRICT COUNCIL ──
        y = strip_y - 14
        c.setFillColor(NAVY)
        c.setFont('Helvetica-Bold', 9)
        district_text = self.district.upper() + " DISTRICT COUNCIL" if self.district else "DISTRICT COUNCIL"
        c.drawCentredString(cx, y, district_text)

        # Thin gold divider separating the district identity from the
        # exam title below it.
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.8)
        c.line(cx - 60, y - 6, cx + 60, y - 6)

        # ── 5. FORM X EXAM_TYPE EXAMINATION RESULTS — navy badge for emphasis ──
        y -= 19
        form_labels = {1: 'ONE', 2: 'TWO', 3: 'THREE', 4: 'FOUR', 5: 'FIVE', 6: 'SIX'}
        form_word = form_labels.get(self.form_num, str(self.form_num))
        result_line = f"FORM {form_word} {self.exam_title} EXAMINATION RESULTS"
        c.setFont('Helvetica-Bold', 11)
        badge_w = c.stringWidth(result_line, 'Helvetica-Bold', 11) + 24
        c.setFillColor(NAVY)
        c.roundRect(cx - badge_w / 2, y - 4, badge_w, 16, 3, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.drawCentredString(cx, y, result_line)

        # ── 6. MONTH-YEAR ──
        y -= 17
        c.setFont('Helvetica-Bold', 8)
        c.setFillColor(SLATE)
        c.drawCentredString(cx, y, self.exam_month)

        # ── 7. SCHOOL NAME ──
        y -= 14
        c.setFillColor(NAVY)
        c.setFont('Helvetica-Bold', 12)
        c.drawCentredString(cx, y, self.school_disp)

        # ── Gold line at bottom ──
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.5)
        c.line(0, 0, w, 0)


# ── Footer (per-page, without page numbers) ─────────────────────────────────
def _footer(canvas, doc):
    canvas.saveState()
    try:
        w, h = doc.pagesize
    except Exception:
        w, h = A4

    # Page border — navy outer
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(1.0)
    canvas.rect(1.0 * cm, 0.8 * cm, w - 2.0 * cm, h - 1.6 * cm)

    # Inner decorative line — gold
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.3)
    canvas.rect(1.15 * cm, 0.95 * cm, w - 2.3 * cm, h - 1.9 * cm)

    # Footer text (without page numbers — added later by NumberedCanvas)
    canvas.setFont('Helvetica', 6)
    canvas.setFillColor(SLATE)
    canvas.drawString(doc.leftMargin, 0.55 * cm, get_full_school_name(doc._exam))
    canvas.drawRightString(w - doc.rightMargin, 0.55 * cm, f"Generated: {doc._gen_date_short}")
    canvas.setStrokeColor(DARK_LINE)
    canvas.setLineWidth(0.3)
    canvas.line(doc.leftMargin, 0.85 * cm, w - doc.rightMargin, 0.85 * cm)

    canvas.restoreState()


# ── NumberedCanvas — adds page numbers + signature as post-processing ─────
def _make_numbered_canvas(doc):
    """Builds a Canvas subclass bound to `doc` that draws page numbers
    ("Page X of Y") and the signature block on the last page, after all
    pages have been laid out (so the true total page count is known)."""
    from reportlab.pdfgen.canvas import Canvas

    class NumberedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            Canvas.__init__(self, *args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            # Capture this page's finished state and start a fresh one
            # WITHOUT emitting the page yet — _startPage() resets canvas
            # state for the next page but does not commit anything to the
            # PDF. The real Canvas.showPage() (which actually commits a
            # page) only runs once per page, inside save() below. Calling
            # the real showPage() here too — as an earlier version of this
            # code did — commits every page twice: once here, once more in
            # save(), silently doubling the entire document.
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_page_states)
            for i, state in enumerate(self._saved_page_states):
                self.__dict__.update(state)
                self._draw_page_number(i + 1, total)
                self._draw_signature(i + 1, total)
                Canvas.showPage(self)
            Canvas.save(self)

        def _draw_page_number(self, pg, total):
            try:
                w, h = doc.pagesize
            except Exception:
                w, h = A4
            self.saveState()
            self.setFont('Helvetica', 6)
            self.setFillColor(SLATE)
            self.drawCentredString(w / 2, 0.55 * cm, f"Page {pg} of {total}")
            self.restoreState()

        def _draw_signature(self, pg, total):
            if pg != total or total <= 1:
                return
            try:
                w, h = doc.pagesize
            except Exception:
                w, h = A4
            sig_y = 1.6 * cm
            sig_x_left = doc.leftMargin
            sig_x_right = w - doc.rightMargin
            content_w_val = getattr(doc, '_content_w', w - 3 * cm)
            sig_w = content_w_val * 0.42

            self.saveState()
            # Left signature
            self.setStrokeColor(DARK_LINE)
            self.setLineWidth(0.4)
            self.line(sig_x_left, sig_y + 14, sig_x_left + sig_w, sig_y + 14)
            self.setFont('Helvetica-Bold', 7.5)
            self.setFillColor(NAVY)
            self.drawCentredString(sig_x_left + sig_w / 2, sig_y + 6, 'Signature & Stamp')
            self.setFont('Helvetica', 7)
            self.setFillColor(SLATE)
            self.drawCentredString(sig_x_left + sig_w / 2, sig_y - 4, 'Academic Officer')
            # Right signature
            self.setStrokeColor(DARK_LINE)
            self.setLineWidth(0.4)
            self.line(sig_x_right - sig_w, sig_y + 14, sig_x_right, sig_y + 14)
            self.setFont('Helvetica-Bold', 7.5)
            self.setFillColor(NAVY)
            self.drawCentredString(sig_x_right - sig_w / 2, sig_y + 6, 'Signature & Stamp')
            self.setFont('Helvetica', 7)
            self.setFillColor(SLATE)
            self.drawCentredString(sig_x_right - sig_w / 2, sig_y - 4, 'Head of School')
            # Date
            self.setFont('Helvetica', 7)
            self.drawString(sig_x_left, sig_y - 16, f'Date: {datetime.now().strftime("%d %B %Y")}')
            self.restoreState()

    return NumberedCanvas


# ══════════════════════════════════════════════════════════════════════════════
# BUILD PDF
# ══════════════════════════════════════════════════════════════════════════════
def generate_results_pdf_response(exam):
    st = _styles()
    school_disp = get_full_school_name(exam)
    lang = get_report_language(exam)
    etype = exam.get_exam_type_display().upper()
    exam_title = exam.name.upper() if exam.name else etype
    gen_date_short = datetime.now().strftime('%d/%m/%Y')

    payload = get_exam_export_payload(exam)
    subjects = payload['subjects']
    results = payload['processed_results']
    score_lookup = payload['score_lookup']
    absent_lookup = payload['absent_lookup']
    student_subjects = payload['student_subjects']
    N = len(results)
    n_subj = max(len(subjects), 1)

    # Load logos — base64 from DB first, then ImageField fallback
    # After loading from ImageField, auto-save to base64 in DB for next time
    slogo_uri = ''
    dlogo_uri = ''
    if exam.school:
        slogo_uri = _load_logo_b64(
            exam.school.school_logo,
            getattr(exam.school, 'school_logo_b64', ''),
        )
        dlogo_uri = _load_logo_b64(
            exam.school.district_logo,
            getattr(exam.school, 'district_logo_b64', ''),
        )
        # If base64 is still empty but we got data from ImageField, save it
        if slogo_uri and not getattr(exam.school, 'school_logo_b64', ''):
            try:
                exam.school.school_logo_b64 = slogo_uri
                exam.school.save(update_fields=['school_logo_b64'])
            except Exception:
                pass
        if dlogo_uri and not getattr(exam.school, 'district_logo_b64', ''):
            try:
                exam.school.district_logo_b64 = dlogo_uri
                exam.school.save(update_fields=['district_logo_b64'])
            except Exception:
                pass
    school_type = get_school_type_for_exam(exam)
    stype = "SECONDARY SCHOOL" if school_type == 'secondary' else "PRIMARY SCHOOL"

    # ── Compute stats ──
    counted = _centre_counted_subjects(results, exam.form)
    if N:
        avg_total = sum(r.total_score for r in results) / N
        avg_average = sum(float(r.average_score) for r in results) / N
        avg_points = sum(r.points for r in results) / N
        div_counts = Counter(r.division for r in results)
        centre_gpa = avg_points / counted if counted else 0
    else:
        avg_total = avg_average = avg_points = centre_gpa = 0
        div_counts = Counter()

    # Sex breakdown
    sex_div = defaultdict(lambda: Counter())
    for r in results:
        g = (r.student.gender or 'M').upper()
        if g not in ('M', 'F'):
            g = 'M'
        sex_div[g][r.division] += 1

    # Subject stats
    subj_stats = []
    for subj in subjects:
        raw_scores = [score_lookup[(r.student_id, subj.id)]
                  for r in results if (r.student_id, subj.id) in score_lookup]
        scores = [s for s in raw_scores if s is not None]
        if scores:
            subj_stats.append({
                'name': subj.name,
                'avg': round(sum(scores) / len(scores), 1),
                'high': max(scores),
                'low': min(scores),
                'pass_pct': round(sum(1 for s in scores if s >= 40) / len(scores) * 100, 1),
            })

    # Subject GPA
    subj_gpa = []
    for subj in subjects:
        raw_scores = [score_lookup[(r.student_id, subj.id)]
                  for r in results if (r.student_id, subj.id) in score_lookup]
        scores = [s for s in raw_scores if s is not None]
        if scores:
            gp_scores = [_grade_point(_grade_for_score(sc, exam.form), exam.form) for sc in scores]
            avg_gp = sum(gp_scores) / len(gp_scores)
            if exam.form in (5, 6):
                if avg_gp <= 1.5:
                    level = "Grade A (Very Good)"
                elif avg_gp <= 2.5:
                    level = "Grade B (Good)"
                elif avg_gp <= 3.5:
                    level = "Grade C (Satisfactory)"
                elif avg_gp <= 4.5:
                    level = "Grade D (Satisfactory)"
                elif avg_gp <= 5.5:
                    level = "Grade E (Satisfactory)"
                elif avg_gp <= 6.5:
                    level = "Grade S (Satisfactory)"
                else:
                    level = "Grade F (Fail)"
            else:
                if avg_gp <= 1.5:
                    level = "Grade A (Very Good)"
                elif avg_gp <= 2.5:
                    level = "Grade B (Good)"
                elif avg_gp <= 3.5:
                    level = "Grade C (Satisfactory)"
                elif avg_gp <= 4.5:
                    level = "Grade D (Satisfactory)"
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
    # ALL PAGES: A4 Portrait
    # ══════════════════════════════════════════════════════════════════════
    page_w, page_h = A4
    margin_lr = 1.5 * cm
    margin_top = 0.5 * cm
    margin_bot = 1.2 * cm
    content_w = page_w - 2 * margin_lr

    story = []

    # ── Header params ──
    district = exam.school.district if exam.school and exam.school.district else ''
    # Get month from exam date or current date
    if exam.date:
        exam_month = exam.date.strftime('%B-%Y').upper()
    else:
        exam_month = datetime.now().strftime('%B-%Y').upper()

    # Coat of arms logo — 3rd logo stored on School model
    coa_uri = ''
    if exam.school:
        coa_uri = _load_logo_b64(
            getattr(exam.school, 'coat_of_arms', None),
            getattr(exam.school, 'coat_of_arms_b64', ''),
        )
        # Fallback: use district logo as coat of arms
        if not coa_uri:
            coa_uri = dlogo_uri

    # ── HEADER (official format) ──
    story.append(NECTAHeader(
        exam, school_disp, slogo_uri, dlogo_uri, stype, lang,
        exam_title=exam_title, form_num=exam.form,
        exam_month=exam_month, district=district,
        coa_uri=coa_uri,
    ))
    story.append(Spacer(1, 8))

    # ── DIVISION PERFORMANCE SUMMARY ──
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
    story.append(Spacer(1, 4))

    # ── PERFORMANCE SUMMARY + GRADING KEY (side by side) ──
    perf_title = "PERFORMANCE SUMMARY" if lang == 'en' else "TAARIFA YA MAENDELEO"
    if lang == 'sw':
        perf_items = [("Wanafunzi", str(N)), ("Wastani Jumla", f"{avg_total:.1f}"),
                      ("Centre GPA", f"{centre_gpa:.2f}"), ("Masomo", str(counted))]
    else:
        perf_items = [("Total Candidates", str(N)), ("Overall Average", f"{avg_total:.1f}"),
                      ("Centre GPA", f"{centre_gpa:.2f}"), ("Subjects Counted", str(counted))]
    perf_data = [[_p(f"<b>{perf_title}</b>", st['th']), '']]
    for k, v in perf_items:
        perf_data.append([_p(k, st['td']), _p(f"<b>{v}</b>", st['td_bold'])])
    cw_perf = [content_w * 0.55, content_w * 0.45]
    perf_table = Table(perf_data, colWidths=cw_perf)
    perf_table.setStyle(TableStyle(_std_table_style(len(perf_data))))

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
    story.append(Spacer(1, 3))
    story.append(gk_table)
    story.append(Spacer(1, 4))

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
        story.append(Spacer(1, 4))

    # ── TOP 5 ──
    if results:
        story.append(_p("<b>TOP 5 PERFORMERS</b>", st['section']))
        th5 = ["POS", "NAME", "TOTAL", "AVG", "GPA", "PTS", "DIV"]
        t_data = [[_p(f"<b>{h}</b>", st['th']) for h in th5]]
        for idx, r in enumerate(results[:5]):
            nm = _student_name(r)
            if len(nm) > 28:
                nm = nm[:26] + '..'
            stu_gpa = r.points / counted if counted else 0
            t_data.append([
                _p(str(r.position), st['td']),
                _p(nm, ParagraphStyle('tn5', parent=st['td'], alignment=TA_LEFT)),
                _p(str(r.total_score), st['td']),
                _p(f"{r.average_score:.1f}", st['td']),
                _p(f"{stu_gpa:.2f}", st['td_bold']),
                _p(str(r.points), st['td']),
                _p(str(r.division), st['td']),
            ])
        cw_t5 = [content_w * w for w in [0.06, 0.30, 0.10, 0.10, 0.10, 0.10, 0.14]]
        t_table = Table(t_data, colWidths=cw_t5)
        ts = _std_table_style(len(t_data))
        ts.append(('BACKGROUND', (0, 1), (-1, 1), GOLD))
        ts.append(('TEXTCOLOR', (0, 1), (-1, 1), WHITE))
        t_table.setStyle(TableStyle(ts))
        story.append(t_table)

    # ══════════════════════════════════════════════════════════════════════
    # RESULTS PAGES — each page gets its OWN table (no splitting issues)
    # CNO | NAME | SEX | AGGT | GPA | DIV | DETAILED SUBJECTS
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())

    cell_st = ParagraphStyle('lsm', parent=st['td'], fontSize=7.5, leading=9)
    cell_bold = ParagraphStyle('lsb', parent=st['td_bold'], fontSize=7.5, leading=9)
    hdr_st = ParagraphStyle('lsh', parent=st['th'], fontSize=7.5, leading=9)
    name_st = ParagraphStyle('lsn', parent=st['td_name'], fontSize=7.5, leading=9)
    subj_st = ParagraphStyle('lss', parent=st['td'], fontSize=6.5, leading=8,
                             wordWrap='CJK')

    r_hdr = ["CNO", "NAME", "SEX", "AGGT", "GPA", "DIV", "DETAILED SUBJECTS"]
    # NAME and DETAILED SUBJECTS are the columns most prone to wrapping onto
    # extra lines (driving up row height, and so page count) — give them as
    # much of the row as the narrow fixed columns can spare.
    cw = [
        content_w * 0.04,   # CNO
        content_w * 0.18,   # NAME
        content_w * 0.03,   # SEX
        content_w * 0.045,  # AGGT
        content_w * 0.045,  # GPA
        content_w * 0.035,  # DIV
        content_w * 0.625,  # DETAILED SUBJECTS
    ]
    PAD_V = 4  # TOPPADDING(2) + BOTTOMPADDING(2) — row height budget
    PAD_H = 6  # LEFTPADDING(3) + RIGHTPADDING(3) — row width budget

    def _row_cells_height(cells):
        """Real rendered height of a table row — each cell wrapped at its
        actual column width, same as ReportLab does when laying out the
        table. A fixed per-row guess doesn't hold: rows wrap to more lines
        as subject count or name length grows, so it must be measured."""
        h = 0
        for cell, col_w in zip(cells, cw):
            _, ch = cell.wrap(max(col_w - PAD_H, 1), 10000)
            h = max(h, ch)
        return h + PAD_V

    def _new_header_row():
        return [_p(f"<b>{h}</b>", hdr_st) for h in r_hdr]

    header_h = _row_cells_height(_new_header_row())

    # Build every result row ONCE, up front, so its real height can be
    # measured before deciding how many rows fit on each page.
    all_rows = []
    for r in results:
        cno = f"{r.position:03d}"
        nm = _student_name(r)
        stu_gpa = r.points / counted if counted else 0

        # Build COLOURED inline subjects — only for subjects this student
        # is enrolled in (has an ExamResult entry for).  Subjects the
        # student does NOT study are omitted entirely from their row.
        enrolled_ids = student_subjects.get(r.student_id, set())
        subj_parts = []
        for sub in subjects:
            if sub.id not in enrolled_ids:
                continue  # student does not study this subject — skip
            sc = score_lookup.get((r.student_id, sub.id))
            is_abs = (r.student_id, sub.id) in absent_lookup
            if is_abs or sc is None:
                g = 'X'
            else:
                g = _grade_for_score(sc, exam.form)
            abbr = (sub.code or '').strip().upper() or (
                sub.name.upper()[:4] if len(sub.name) > 4 else sub.name.upper()
            )
            fg, bg = GRADE_COLORS.get(g, ('#555555', '#E8E8E8'))
            subj_parts.append(
                f"<font color='{fg}'><b>{abbr}-{g}</b></font>"
            )
        subj_text = '&nbsp;'.join(subj_parts)

        div_bg = DIV_BG.get(r.division, WHITE)
        div_fg = DIV_FG.get(r.division, BLACK)
        dv_st = ParagraphStyle(f'dv4_{r.student_id}', parent=cell_st,
                               backColor=div_bg, textColor=div_fg,
                               fontName='Helvetica-Bold')

        all_rows.append([
            _p(cno, cell_st),
            _p(nm, name_st),
            _p(r.student.gender or 'M', cell_st),
            _p(str(r.points), cell_bold),
            _p(f"{stu_gpa:.2f}", cell_bold),
            _p(str(r.division), dv_st),
            _p(subj_text, subj_st),
        ])

    row_heights = [_row_cells_height(cells) for cells in all_rows]

    # ── Tail block (grading key + centre performance + subject performance) ──
    # Built once — it only ever lands on the true last page, right after the
    # last chunk of results, so its real height can be reserved up front.
    tail_flowables = []

    gk_cells_pg = [
        _p(f"<b>{g} ({rng})</b>", ParagraphStyle(
            f'gk3_{g}', parent=cell_st, textColor=GRADE_FG.get(g, BLACK),
            fontName='Helvetica-Bold',
        ))
        for g, rng in grades
    ]
    gk_table_pg = Table([gk_cells_pg], colWidths=[content_w / len(grades)] * len(grades))
    gk_s2 = [
        ('GRID', (0, 0), (-1, -1), 0.3, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    for i, (g, _) in enumerate(grades):
        gk_s2.append(('BACKGROUND', (i, 0), (i, 0), GRADE_BG.get(g, WHITE)))
    gk_table_pg.setStyle(TableStyle(gk_s2))
    tail_flowables.append(Spacer(1, 6))
    tail_flowables.append(gk_table_pg)
    tail_flowables.append(Spacer(1, 5))

    # Centre performance summary
    tail_flowables.append(_p("<b>EXAMINATION CENTRE OVERALL PERFORMANCE</b>", st['section']))
    div_perf_hdrs = ["", "REGIST", "ABSENT", "SAT", "CLEAN", "DIV I", "DIV II", "DIV III", "DIV IV", "DIV 0"]
    absent_count = sum(1 for r in results if r.total_score == 0)
    dp_data = [[_p(f"<b>{h}</b>", ParagraphStyle('dph', parent=cell_st, fontSize=6, textColor=WHITE, fontName='Helvetica-Bold')) for h in div_perf_hdrs]]
    dp_row = [_p("<b>TOTAL</b>", ParagraphStyle('dpt', parent=cell_st, fontSize=6, fontName='Helvetica-Bold'))]
    dp_row += [
        _p(str(N), cell_st), _p(str(absent_count), cell_st),
        _p(str(N - absent_count), cell_st), _p(str(N - absent_count), cell_st),
        _p(str(div_counts.get('I', 0)), cell_st), _p(str(div_counts.get('II', 0)), cell_st),
        _p(str(div_counts.get('III', 0)), cell_st), _p(str(div_counts.get('IV', 0)), cell_st),
        _p(str(div_counts.get('0', 0)), cell_st),
    ]
    dp_data.append(dp_row)
    cw_dp = [content_w / len(div_perf_hdrs)] * len(div_perf_hdrs)
    dp_table = Table(dp_data, colWidths=cw_dp)
    dp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.3, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    tail_flowables.append(dp_table)
    tail_flowables.append(Spacer(1, 4))

    # Subject performance
    if subj_gpa:
        tail_flowables.append(_p("<b>SUBJECT PERFORMANCE</b>", st['section']))
        sp_hdrs = ["#", "SUBJECT", "SAT", "PASS", "GPA", "LEVEL"]
        sp_data = [[_p(f"<b>{h}</b>", ParagraphStyle('sph', parent=cell_st, fontSize=6, textColor=WHITE, fontName='Helvetica-Bold')) for h in sp_hdrs]]
        for idx, sg in enumerate(subj_gpa, 1):
            level_key = sg['level'].split(' (')[0] if sg['level'] else ''
            fg, bg = LEVEL_COLORS.get(level_key, ('#555555', '#E8E8E8'))
            level_st = ParagraphStyle(f'lvl_{idx}', parent=cell_st, fontSize=6,
                                      textColor=colors.HexColor(fg), backColor=colors.HexColor(bg),
                                      fontName='Helvetica-Bold', alignment=TA_LEFT)
            sp_data.append([
                _p(str(idx), cell_st),
                _p(sg['name'], ParagraphStyle('spn', parent=cell_st, fontSize=6, alignment=TA_LEFT)),
                _p(str(sg['sat']), cell_st),
                _p(str(sg['pass_count']), cell_st),
                _p(f"{sg['gpa']:.4f}", cell_st),
                _p(sg['level'], level_st),
            ])
        cw_sp = [content_w * w for w in [0.04, 0.22, 0.08, 0.08, 0.12, 0.46]]
        sp_table = Table(sp_data, colWidths=cw_sp)
        sp_table.setStyle(TableStyle(_std_table_style(len(sp_data))))
        tail_flowables.append(sp_table)
        tail_flowables.append(Spacer(1, 6))

    # Signature is drawn in _footer canvas function on the last page
    # (left: Academic Officer, right: Head of School, with date)

    def _flowable_height(f):
        if isinstance(f, Spacer):
            return f.height
        return f.wrap(content_w, 10000)[1]

    tail_reserve = sum(_flowable_height(f) for f in tail_flowables)

    # Calculate how much vertical room a results table has on a page:
    # header (150pt) + spacer (6pt) = 156pt overhead
    # footer text only (20pt) — signature is on canvas, not in story
    # SAFETY_MARGIN absorbs small font-metric differences between the
    # environment this was tuned in and wherever it actually renders, so a
    # borderline page can never silently overflow onto a spurious extra one.
    header_overhead = 150 + 6  # 156pt
    footer_text = 20  # just footer text line
    SAFETY_MARGIN = 15
    available_h = page_h - margin_top - margin_bot - header_overhead - footer_text - SAFETY_MARGIN

    # Pack rows by their REAL measured height, filling EVERY page to full
    # capacity first — plain greedy, ignoring the tail block entirely — so
    # every results page, including what would be the last, holds as many
    # rows as actually fit. The tail block (grading key / centre performance
    # / subject performance) then either rides in whatever slack is left on
    # that final page, or — if it doesn't fit there — gets a page of its
    # own. Rows are never pulled off an already-packed page to make room
    # for it, so no results page ends up smaller than it needs to be.
    chunks = []
    idx = 0
    n_rows = len(all_rows)
    while idx < n_rows:
        cum = header_h
        j = idx
        while j < n_rows and (j == idx or cum + row_heights[j] <= available_h):
            cum += row_heights[j]
            j += 1
        chunks.append((idx, j))
        idx = j
    if not chunks:
        chunks = [(0, 0)]

    c_start, c_end = chunks[-1]
    last_page_used = header_h + sum(row_heights[c_start:c_end])
    if last_page_used + tail_reserve > available_h:
        chunks.append((n_rows, n_rows))  # tail doesn't fit here — give it its own page

    total_pages = len(chunks)

    for pg_idx, (c_start, c_end) in enumerate(chunks, 1):
        # ── Header on EVERY page (official format) ──
        story.append(NECTAHeader(
            exam, school_disp, slogo_uri, dlogo_uri, stype, lang,
            exam_title=exam_title, form_num=exam.form,
            exam_month=exam_month, district=district,
            coa_uri=coa_uri,
        ))
        story.append(Spacer(1, 6))

        # ── Build SEPARATE table for this chunk (no splitting!) ──
        # A chunk can be empty when the tail block didn't fit on the
        # previous page and got bumped to a page of its own — skip the
        # table entirely rather than render one with just a header row.
        if c_end > c_start:
            data = [_new_header_row()] + all_rows[c_start:c_end]

            r_table = Table(data, colWidths=cw)
            rs = [
                ('BACKGROUND', (0, 0), (-1, 0), NAVY),
                ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
                ('GRID', (0, 0), (-1, -1), 0.3, DARK_LINE),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ]
            for i in range(1, len(data)):
                if i % 2 == 0:
                    rs.append(('BACKGROUND', (0, i), (-1, i), CREAM))
            r_table.setStyle(TableStyle(rs))
            story.append(r_table)

        # ── Last page: grading key + centre performance + subject performance ──
        if pg_idx == total_pages:
            story.extend(tail_flowables)

        if pg_idx < total_pages:
            story.append(PageBreak())

    # ── Build ──
    buf = io.BytesIO()

    frame = Frame(margin_lr, margin_bot, content_w, page_h - margin_top - margin_bot, id='main')

    tmpl = PageTemplate(id='main', frames=[frame], pagesize=A4, onPage=_footer)

    # Single build — NumberedCanvas adds page numbers + signature at the end
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        title=f"{school_disp} \u2014 {etype} {exam.year}",
        pageTemplates=[tmpl],
    )
    doc._exam = exam
    doc._gen_date_short = gen_date_short
    doc._content_w = content_w

    # NumberedCanvas draws "Page X of Y" + signature after all pages are laid
    # out, once the true total page count is known — no second build needed.
    doc.build(story, canvasmaker=_make_numbered_canvas(doc))

    buf.seek(0)
    resp = HttpResponse(buf, content_type='application/pdf')
    safe_name = exam.name.replace(" ", "_")
    resp['Content-Disposition'] = f'attachment; filename="{safe_name}_Results.pdf"'
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# INDIVIDUAL STUDENT RESULT SLIP — the downloadable version of the public
# /shule/matokeo/<token>/ page, so a parent/student can take a copy home
# instead of only viewing it online.
# ══════════════════════════════════════════════════════════════════════════════
def _build_student_result_pdf_bytes(result, *, school_type=None, total_students=None, scores=None, subjects=None):
    """One-page NECTA-style result slip for a single ProcessedResult —
    same official header as the full class report, personalised below it
    with this student's own subjects, scores, and division/points/position.
    Returns a seeked-to-0 BytesIO — shared by the single-student download
    and the "all students, one file" bulk download, which merges one of
    these per student.

    school_type/total_students/scores/subjects are optional precomputed
    values — the bulk download passes them in (computed once for the whole
    exam) so this doesn't re-run the same exam-wide/cross-DB queries once
    per student; the single-student download leaves them None and this
    looks them up itself."""
    from reportlab.platypus import SimpleDocTemplate

    exam = result.exam
    student = result.student
    st = _styles()
    school_disp = get_full_school_name(exam)
    lang = get_report_language(exam)
    etype = exam.get_exam_type_display().upper()
    exam_title = exam.name.upper() if exam.name else etype
    gen_date_short = datetime.now().strftime('%d/%m/%Y')
    if school_type is None:
        school_type = get_school_type_for_exam(exam)
    stype = "SECONDARY SCHOOL" if school_type == 'secondary' else "PRIMARY SCHOOL"

    slogo_uri = dlogo_uri = coa_uri = ''
    if exam.school:
        slogo_uri = _load_logo_b64(exam.school.school_logo, getattr(exam.school, 'school_logo_b64', ''))
        dlogo_uri = _load_logo_b64(exam.school.district_logo, getattr(exam.school, 'district_logo_b64', ''))
        coa_uri = _load_logo_b64(getattr(exam.school, 'coat_of_arms', None), getattr(exam.school, 'coat_of_arms_b64', ''))
        if not coa_uri:
            coa_uri = dlogo_uri

    district = exam.school.district if exam.school and exam.school.district else ''
    exam_month = (exam.date.strftime('%B-%Y').upper() if exam.date else datetime.now().strftime('%B-%Y').upper())

    student_name = _student_name(result)
    if scores is None:
        scores = {
            er.subject_id: er.score
            for er in ExamResult.objects.filter(exam=exam, student=student).select_related('subject')
        }
    if subjects is None:
        subjects = list(Subject.objects.filter(examresult__exam=exam, examresult__student=student).distinct().order_by('name'))
    if total_students is None:
        total_students = ProcessedResult.objects.filter(exam=exam).count()
    division_label = dict(ProcessedResult.DIVISION_CHOICES).get(result.division, result.division)

    page_w, page_h = A4
    margin_lr = 1.6 * cm
    content_w = page_w - 2 * margin_lr

    story = [
        NECTAHeader(
            exam, school_disp, slogo_uri, dlogo_uri, stype, lang,
            exam_title=exam_title, form_num=exam.form,
            exam_month=exam_month, district=district, coa_uri=coa_uri,
        ),
        Spacer(1, 10),
        _p(f"<b>{student_name.upper()}</b>", st['title_md']),
        _p(f"{_location_str(exam)}", st['subtitle']),
        Spacer(1, 10),
    ]

    # ── Subjects table ──
    subj_hdrs = ["SOMO / SUBJECT", "ALAMA / SCORE", "DARAJA / GRADE"]
    subj_rows = [[_p(f"<b>{h}</b>", st['th']) for h in subj_hdrs]]
    for subj in subjects:
        score = scores.get(subj.id)
        if score is None:
            continue
        grade = _grade_for_score(score, exam.form)
        subj_rows.append([_p(subj.name, st['td_name']), _p(str(score), st['td']), _p(grade or '-', st['td_bold'])])
    subj_table = Table(subj_rows, colWidths=[content_w * 0.55, content_w * 0.22, content_w * 0.23])
    subj_table.setStyle(TableStyle(_std_table_style(len(subj_rows))))
    story.append(subj_table)
    story.append(Spacer(1, 14))

    # ── Summary box ──
    story.append(_p("<b>MUHTASARI / SUMMARY</b>", st['section']))
    summary_hdrs = ["JUMLA / TOTAL", "WASTANI / AVERAGE", "POINTS", "DIVISION", "NAFASI / POSITION"]
    summary_row = [
        str(result.total_score),
        str(result.average_score),
        str(result.points),
        division_label,
        f"{result.position} / {total_students}",
    ]
    summary_table = Table(
        [[_p(f"<b>{h}</b>", st['th_sm']) for h in summary_hdrs], [_p(v, st['td_bold']) for v in summary_row]],
        colWidths=[content_w / 5] * 5,
    )
    summary_table.setStyle(TableStyle(_std_table_style(2, header_bg=GREEN)))
    story.append(summary_table)
    story.append(Spacer(1, 16))
    story.append(_p(
        "Haya ni matokeo rasmi yaliyotolewa na mfumo wa shule. / "
        "These are official results generated by the school system.",
        st['sig'],
    ))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=0.6 * cm, bottomMargin=1.3 * cm, leftMargin=margin_lr, rightMargin=margin_lr,
        title=f"{school_disp} — {student_name} — {etype} {exam.year}",
    )
    doc._exam = exam
    doc._gen_date_short = gen_date_short
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)

    buf.seek(0)
    return buf


def generate_student_result_pdf_response(result):
    """Single-student download — see _build_student_result_pdf_bytes."""
    buf = _build_student_result_pdf_bytes(result)
    resp = HttpResponse(buf, content_type='application/pdf')
    safe_name = _student_name(result).replace(' ', '_')
    resp['Content-Disposition'] = f'attachment; filename="Matokeo_{safe_name}.pdf"'
    return resp


def generate_bulk_student_results_pdf_response(exam):
    """All students of this exam (i.e. this form — an Exam is already
    scoped to one form/year/type), each on their own page(s), merged into
    ONE downloadable PDF — same slip _build_student_result_pdf_bytes
    produces for a single student, just all of them together in position
    order. Mirrors the merge pattern curriculum/views.py's
    download_all_lesson_plans_pdf already uses for the same "many small
    PDFs -> one file" need."""
    import pypdfium2 as pdfium

    results = list(
        ProcessedResult.objects.filter(exam=exam)
        .select_related('student')
        .order_by('position')
    )
    if not results:
        resp = HttpResponse('Hakuna matokeo yaliyokamilika kwa mtihani huu bado.', status=404)
        return resp

    # Compute exam-wide values once instead of per-student inside the loop
    # below (school type does a cross-DB lookup; total_students was already
    # this same queryset's length).
    total_students = len(results)
    school_type = get_school_type_for_exam(exam)

    student_ids = [r.student_id for r in results]
    scores_by_student = {}
    subjects_by_student = {}
    for er in ExamResult.objects.filter(exam=exam, student_id__in=student_ids).select_related('subject'):
        scores_by_student.setdefault(er.student_id, {})[er.subject_id] = er.score
        subjects_by_student.setdefault(er.student_id, {})[er.subject_id] = er.subject
    for sid, subj_map in subjects_by_student.items():
        subjects_by_student[sid] = sorted(subj_map.values(), key=lambda s: s.name)

    merged = pdfium.PdfDocument.new()
    buffers = []
    for result in results:
        buf = _build_student_result_pdf_bytes(
            result,
            school_type=school_type,
            total_students=total_students,
            scores=scores_by_student.get(result.student_id, {}),
            subjects=subjects_by_student.get(result.student_id, []),
        )
        buffers.append(buf)
        src = pdfium.PdfDocument(buf)  # buffers stay alive until save()
        merged.import_pages(src)
        src.close()

    out = io.BytesIO()
    merged.save(out)
    merged.close()

    resp = HttpResponse(out.getvalue(), content_type='application/pdf')
    safe_name = exam.name.replace(' ', '_')
    resp['Content-Disposition'] = f'attachment; filename="Matokeo_Wote_Form{exam.form}_{safe_name}.pdf"'
    return resp
