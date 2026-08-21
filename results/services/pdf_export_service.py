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
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Table, TableStyle, Paragraph, Spacer, PageBreak,
    Flowable,
)

from .export_data import get_exam_export_payload
from .report_helpers import (
    get_full_school_name, get_report_label, get_report_language,
    get_section_title, get_school_type_for_exam,
)

# ── Colours ──────────────────────────────────────────────────────────────────
NAVY      = colors.HexColor("#1A3C6E")
DARK_NAVY = colors.HexColor("#0F2744")
GREEN     = colors.HexColor("#1A7B3A")
GOLD      = colors.HexColor("#B8860B")
CREAM     = colors.HexColor("#FAF8F2")
SLATE     = colors.HexColor("#555555")
LGRAY     = colors.HexColor("#CCCCCC")
MGRAY     = colors.HexColor("#E8E8E8")
WHITE     = colors.white
BLACK     = colors.black
DARK_LINE = colors.HexColor("#999999")

TZ_GREEN  = colors.HexColor("#00A651")
TZ_YELLOW = colors.HexColor("#FCD116")
TZ_BLACK  = colors.black
TZ_BLUE   = colors.HexColor("#00A3DD")

GRADE_BG = {
    'A':  colors.HexColor("#C6EFCE"), 'B+': colors.HexColor("#D5F5E3"),
    'B':  colors.HexColor("#D5F5E3"), 'C+': colors.HexColor("#FEF9E7"),
    'C':  colors.HexColor("#FEF9E7"), 'D':  colors.HexColor("#FDEBD0"),
    'E':  colors.HexColor("#F5CBA7"), 'S':  colors.HexColor("#F9E79F"),
    'F':  colors.HexColor("#FADBD8"),
}
GRADE_FG = {
    'A':  colors.HexColor("#006100"), 'B+': colors.HexColor("#006100"),
    'B':  colors.HexColor("#006100"), 'C+': colors.HexColor("#9C6500"),
    'C':  colors.HexColor("#9C6500"), 'D':  colors.HexColor("#CC3300"),
    'E':  colors.HexColor("#CC3300"), 'S':  colors.HexColor("#9C6500"),
    'F':  colors.HexColor("#9C0006"),
}
DIV_BG = {
    'I':   colors.HexColor("#C6EFCE"), 'II':  colors.HexColor("#D5F5E3"),
    'III': colors.HexColor("#FEF9E7"), 'IV':  colors.HexColor("#FDEBD0"),
    '0':   colors.HexColor("#FADBD8"),
}
DIV_FG = {
    'I':   colors.HexColor("#006100"), 'II':  colors.HexColor("#006100"),
    'III': colors.HexColor("#9C6500"), 'IV':  colors.HexColor("#CC3300"),
    '0':   colors.HexColor("#9C0006"),
}

GRADE_COLORS = {
    'A':  ('#006100', '#C6EFCE'),
    'B+': ('#006100', '#D5F5E3'),
    'B':  ('#1E8449', '#D5F5E3'),
    'C+': ('#9C6500', '#FEF9E7'),
    'C':  ('#9C6500', '#FEF9E7'),
    'D':  ('#CC3300', '#FDEBD0'),
    'E':  ('#CC3300', '#F5CBA7'),
    'S':  ('#B9770B', '#F9E79F'),
    'F':  ('#9C0006', '#FADBD8'),
    'X':  ('#555555', '#E8E8E8'),
}

LEVEL_COLORS = {
    'Grade A': ('#006100', '#C6EFCE'),
    'Grade B+': ('#006100', '#D5F5E3'),
    'Grade B': ('#1E8449', '#D5F5E3'),
    'Grade C': ('#9C6500', '#FEF9E7'),
    'Grade D': ('#CC3300', '#FDEBD0'),
    'Grade E': ('#CC3300', '#F5CBA7'),
    'Grade S': ('#B9770B', '#F9E79F'),
    'Grade F': ('#9C0006', '#FADBD8'),
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


def _grade_point(grade):
    gp_map = {'A': 1, 'B+': 2, 'B': 3, 'C+': 4, 'C': 5, 'D': 6, 'E': 7, 'S': 8, 'F': 9}
    return gp_map.get(grade, 9)


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
        c.setFillColor(GREEN)
        c.roundRect(0, strip_top, w, h - strip_top, 3, fill=1, stroke=0)

        # ── PMO + Regional Admin text (on the green background) ──
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 9)
        c.drawCentredString(cx, banner_y + self.BANNER_H - 14, "PRIME MINISTER'S OFFICE")
        c.setFont('Helvetica-Bold', 7)
        c.drawCentredString(cx, banner_y + self.BANNER_H - 26, "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT")

        # ── 2. LOGOS ROW — School (left) + Coat of Arms (center) + District (right) ──
        logo_sz = 40
        # School logo — left
        if self.slogo_uri:
            _safe_b64_img(self.slogo_uri, 2, logos_y + 5, logo_sz, logo_sz, c)
        # Coat of Arms — center
        if self.coa_uri:
            _safe_b64_img(self.coa_uri, cx - logo_sz / 2, logos_y + 5, logo_sz, logo_sz, c)
        elif self.dlogo_uri:
            _safe_b64_img(self.dlogo_uri, cx - logo_sz / 2, logos_y + 5, logo_sz, logo_sz, c)
        # District logo — right
        if self.dlogo_uri:
            _safe_b64_img(self.dlogo_uri, w - logo_sz - 2, logos_y + 5, logo_sz, logo_sz, c)

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

        # ── 5. FORM X EXAM_TYPE EXAMINATION RESULTS ──
        y -= 15
        form_labels = {1: 'ONE', 2: 'TWO', 3: 'THREE', 4: 'FOUR', 5: 'FIVE', 6: 'SIX'}
        form_word = form_labels.get(self.form_num, str(self.form_num))
        result_line = f"FORM {form_word} {self.exam_title} EXAMINATION RESULTS"
        c.setFont('Helvetica-Bold', 11)
        c.drawCentredString(cx, y, result_line)

        # ── 6. MONTH-YEAR ──
        y -= 13
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
            self._saved_page_states.append(dict(self.__dict__))
            Canvas.showPage(self)

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
    counted = n_subj
    if N:
        avg_total = sum(r.total_score for r in results) / N
        avg_average = sum(float(r.average_score) for r in results) / N
        avg_points = sum(r.points for r in results) / N
        div_counts = Counter(r.division for r in results)
        counted = len([s for s in (results[0].counted_subjects or '').split(',') if s.strip()]) if results else n_subj
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

    # Subject GPA
    subj_gpa = []
    for subj in subjects:
        scores = [score_lookup[(r.student_id, subj.id)]
                  for r in results if (r.student_id, subj.id) in score_lookup]
        if scores:
            gp_scores = [_grade_point(_grade_for_score(sc, exam.form)) for sc in scores]
            avg_gp = sum(gp_scores) / len(gp_scores)
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
        ts.append(('BACKGROUND', (0, 1), (-1, 1), colors.HexColor("#DAA520")))
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
    subj_st = ParagraphStyle('lss', parent=st['td'], fontSize=7, leading=8.5,
                             wordWrap='CJK')

    r_hdr = ["CNO", "NAME", "SEX", "AGGT", "GPA", "DIV", "DETAILED SUBJECTS"]
    cw = [
        content_w * 0.05,  # CNO
        content_w * 0.14,  # NAME
        content_w * 0.04,  # SEX
        content_w * 0.05,  # AGGT
        content_w * 0.05,  # GPA
        content_w * 0.04,  # DIV
        content_w * 0.63,  # DETAILED SUBJECTS
    ]
    ROW_PAD = 6  # matches TOPPADDING(3)+BOTTOMPADDING(3) / LEFTPADDING(3)+RIGHTPADDING(3)

    def _row_cells_height(cells):
        """Real rendered height of a table row — each cell wrapped at its
        actual column width, same as ReportLab does when laying out the
        table. A fixed per-row guess doesn't hold: rows wrap to more lines
        as subject count or name length grows, so it must be measured."""
        h = 0
        for cell, col_w in zip(cells, cw):
            _, ch = cell.wrap(max(col_w - ROW_PAD, 1), 10000)
            h = max(h, ch)
        return h + ROW_PAD

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

        # Build COLOURED inline subjects
        subj_parts = []
        for sub in subjects:
            sc = score_lookup.get((r.student_id, sub.id))
            g = _grade_for_score(sc, exam.form) if sc is not None else 'X'
            abbr = sub.name.upper()[:4] if len(sub.name) > 4 else sub.name.upper()
            fg, bg = GRADE_COLORS.get(g, ('#555555', '#E8E8E8'))
            subj_parts.append(
                f"<font color='{fg}'><b>{abbr} - '{g}'</b></font>"
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
    header_overhead = 150 + 6  # 156pt
    footer_text = 20  # just footer text line
    available_h = page_h - margin_top - margin_bot - header_overhead - footer_text

    # Pack rows by their REAL measured height: fill each page up to
    # available_h, then make sure the final chunk also leaves room for the
    # tail block above it — if it doesn't fit, peel the overflow onto a new
    # final page instead of letting it silently spill past the frame.
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

    # If the final chunk doesn't leave room for the tail block, peel rows off
    # ITS END (not its start) onto a new final chunk — the remaining prefix
    # is a subset of a range that already fit the full budget, so it stays
    # full, and the peeled tail is packed as tightly as the smaller budget
    # allows, instead of splitting near the front and leaving both halves
    # sparse.
    c_start, c_end = chunks[-1]
    last_budget = available_h - tail_reserve
    total = sum(row_heights[c_start:c_end])
    if header_h + total > last_budget:
        k = c_end
        remaining = total
        while k > c_start and header_h + remaining > last_budget:
            k -= 1
            remaining -= row_heights[k]
        if k > c_start:
            chunks[-1] = (c_start, k)
            chunks.append((k, c_end))

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
        data = [_new_header_row()] + all_rows[c_start:c_end]

        r_table = Table(data, colWidths=cw)
        rs = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('GRID', (0, 0), (-1, -1), 0.3, DARK_LINE),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
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
