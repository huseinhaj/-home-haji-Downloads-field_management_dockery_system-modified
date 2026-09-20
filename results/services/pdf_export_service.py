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
from xml.sax.saxutils import escape as _xml_escape

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
    Flowable, Image,
)
import logging

from ..models import ExamResult, ProcessedResult, Subject, ResultVerificationToken
from .export_data import get_exam_export_payload, order_by_registration
from .report_helpers import (
    get_full_school_name, get_report_label, get_report_language,
    get_section_title, get_school_type_for_exam,
)

logger = logging.getLogger(__name__)


def _get_or_create_verification_token(result):
    """Token iliyo hai ya result hii — lazy create (historical slips pia).
    Token iliyorevoked haitumiki tena — QR mpya inaundwa."""
    vt = ResultVerificationToken.active_for(result)
    if vt is None:
        vt = ResultVerificationToken.objects.create(result=result)
    return vt


def _qr_data_uri(path, box_size=6):
    """QR code ya path → PNG bytes (kwa reportlab Image). None kwa hiccup."""
    try:
        import qrcode
        img = qrcode.make(path, box_size=box_size, border=2)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        logger.warning("QR generation failed for %s", path, exc_info=True)
        return None

# ── Colours — modern flat palette (blue/emerald/amber) ────────────────────────
NAVY      = colors.HexColor("#1D4ED8")  # vivid modern blue (was muted navy)
DARK_NAVY = colors.HexColor("#1E3A8A")  # deep blue for contrast accents
GREEN     = colors.HexColor("#15803D")  # clean modern green (PMO banner)
GOLD      = colors.HexColor("#F59E0B")  # vivid amber (was dull goldenrod)

# ── Authentic NECTA colours — verified against NECTA's own CSEE results HTML
# (onlinesys.necta.go.tz): BODY BGCOLOR="LIGHTBLUE", table BGCOLOR="LIGHTYELLOW",
# BODY TEXT="#000080" (navy), headings FONT COLOR="#800080" (purple).
NECTA_PAGE_BG   = colors.HexColor("#87CEEB")  # sky blue — whole-page background (deepened per user: "ikolee kweli")
NECTA_TABLE_BG  = colors.HexColor("#FFFFE0")  # "lightyellow" — table cell background
NECTA_TEXT_NAVY = colors.HexColor("#000080")  # navy body text
NECTA_HEADING   = colors.HexColor("#800080")  # purple section headings
NECTA_GRID      = colors.HexColor("#7A8BA8")  # slate-blue grid/frame lines
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

# Per-theme Division chip palettes — the DIV cell must POP against the row
# background each theme paints, so the pastel 'normal' chips don't work for
# the prestige/lavender/onyx sheets. royal: purple-tinted chips with aubergine
# ink (Division I gets a gold honour chip). acsee: cream chips on the onyx
# sheet with bronze ink (Division I gets the champagne honour chip).
DIV_BG_THEME = {
    'royal': {
        'I':   colors.HexColor("#E5C96B"), 'II':  colors.HexColor("#DCCBF2"),
        'III': colors.HexColor("#EADDF8"), 'IV':  colors.HexColor("#F2EBFA"),
        '0':   colors.HexColor("#F4EFFA"),
    },
    'acsee': {
        'I':   colors.HexColor("#D4B14A"), 'II':  colors.HexColor("#E5C96B"),
        'III': colors.HexColor("#F0E4BC"), 'IV':  colors.HexColor("#F6ECD0"),
        '0':   colors.HexColor("#FBF6E8"),
    },
}
DIV_FG_THEME = {
    'royal': {
        'I':   colors.HexColor("#3D2A08"), 'II':  colors.HexColor("#4A1D6E"),
        'III': colors.HexColor("#5B2E85"), 'IV':  colors.HexColor("#6B4FA0"),
        '0':   colors.HexColor("#7A5AAE"),
    },
    'acsee': {
        'I':   colors.HexColor("#2B2410"), 'II':  colors.HexColor("#4A3D10"),
        'III': colors.HexColor("#5A4713"), 'IV':  colors.HexColor("#6E5A1E"),
        '0':   colors.HexColor("#7E6B2A"),
    },
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

# Single flat text colour used for every subject-grade chip and the
# Division cell under the rank/necta styles, instead of GRADE_COLORS'/
# DIV_BG's/DIV_FG's per-grade rainbow (that pass/fail colour-coding is
# specific to this system's own 'normal' look) — matches each theme's own
# header colour so results read as part of that theme, not the default one.
# necta: BODY TEXT="#000080" — every cell prints navy, exactly like the sheet.
# royal: deep aubergine ink. acsee: charcoal on white panel, gold headings.
_UNIFORM_GRADE_TEXT_HEX = {
    'rank': '#000000', 'necta': '#000080',
    'royal': '#4A1D6E', 'acsee': '#2B2B2B',
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


# ── Output themes ───────────────────────────────────────────────────────────
# Same content and structure everywhere — only the palette / row styling
# changes. 'normal' keeps the exact colours the system has always used.
#   normal : the system's own blue/gold official look
#   rank   : the TEC "School GPA Ranks" sheet — peach headers, black text,
#            periwinkle accent rows
#   necta  : the NECTA CSEE results page — pale-lavender page, purple
#            headings, pale-blue table headers, white / pale-yellow bands
_THEMES = {
    'normal': {
        'header_bg':  NAVY,
        'header_fg':  WHITE,
        'band_bg':    CREAM,
        'accent_bg':  GOLD,
        'accent_fg':  WHITE,
        'section_fg': NAVY,
        'page_bg':    None,
    },
    'rank': {
        'header_bg':  colors.HexColor("#FCE4D6"),
        'header_fg':  BLACK,
        'band_bg':    colors.HexColor("#FDF3EE"),
        'accent_bg':  colors.HexColor("#8EA9DB"),
        'accent_fg':  BLACK,
        'section_fg': colors.HexColor("#375623"),
        'page_bg':    None,
    },
    'necta': {
        # Authentic NECTA CSEE look: light-yellow tables on a light-blue page,
        # navy text, purple headings (verified against NECTA's own results HTML).
        'header_bg':  NECTA_TABLE_BG,
        'header_fg':  NECTA_TEXT_NAVY,
        'band_bg':    NECTA_TABLE_BG,
        'accent_bg':  colors.HexColor("#FFF9B8"),  # slightly deeper yellow — TOP-5 highlight row
        'accent_fg':  NECTA_TEXT_NAVY,
        'section_fg': NECTA_HEADING,
        'page_bg':    NECTA_PAGE_BG,
    },
    'royal': {
        # Form Five — ROYAL AMETHYST: luminous lavender page, purple-silk
        # table headers, gold laurel framing. Regal and unmistakable.
        'header_bg':  colors.HexColor("#6B2FA0"),
        'header_fg':  WHITE,
        'band_bg':    colors.HexColor("#F4EFFA"),
        'accent_bg':  colors.HexColor("#E9DFF7"),
        'accent_fg':  colors.HexColor("#4A1D6E"),
        'section_fg': colors.HexColor("#6B2FA0"),
        'page_bg':    colors.HexColor("#EFE7F9"),
    },
    'acsee': {
        # Form Six — BLACK & GOLD PRESTIGE: onyx page, champagne-gold
        # framing, cream panels. The 'graduation gala' certificate look.
        'header_bg':  colors.HexColor("#1A1A1A"),
        'header_fg':  colors.HexColor("#E5C96B"),
        'band_bg':    colors.HexColor("#FBF6E8"),
        'accent_bg':  colors.HexColor("#F0E4BC"),
        'accent_fg':  colors.HexColor("#5A4713"),
        'section_fg': colors.HexColor("#8A6D1F"),
        'page_bg':    colors.HexColor("#141414"),
    },
}


def _resolve_theme(style):
    return _THEMES.get((style or 'normal').lower(), _THEMES['normal'])


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
def _grading_thresholds(form, primary=False):
    """CSEE and FTNA share the same 5-band A/B/C/D/F scale — verified
    against real NECTA CSEE result slips, which never show B+/C+.
    Primary (Darasa 1-7): A-E scale, E (si F) ndiyo kushindwa."""
    if primary:
        return [80, 65, 45, 30], [('A','80-100'),('B','65-79'),('C','45-64'),('D','30-44'),('E','0-29')]
    if form == 2:
        return [75, 65, 45, 30], [('A','75-100'),('B','65-74'),('C','45-64'),('D','30-44'),('F','0-29')]
    if form in (5, 6):
        return [80, 70, 60, 50, 40, 35], [('A','80-100'),('B','70-79'),('C','60-69'),('D','50-59'),('E','40-49'),('S','35-39'),('F','0-34')]
    return [75, 65, 45, 30], [('A','75-100'),('B','65-74'),('C','45-64'),('D','30-44'),('F','0-29')]


# Short Swahili "how did they do" label for a letter grade — used in the
# per-subject MAONI column and the MCHANGANUO legend on the full report
# card. Purely derived from the grade, no stored data.
GRADE_MEANING_SW = {
    'A': 'Vizuri sana', 'B': 'Vizuri', 'C': 'Wastani',
    'D': 'Dhaifu', 'E': 'Dhaifu', 'S': 'Hafifu', 'F': 'Mbaya sana',
}


def _grade_for_score(score, form=4, primary=False):
    if score is None or not isinstance(score, (int, float)):
        return None
    th, gr = _grading_thresholds(form, primary=primary)
    for i, t in enumerate(th):
        if score >= t:
            return gr[i][0]
    return gr[-1][0]


def _grade_point(grade, form=4, primary=False):
    if primary:
        gp_map = {'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5}
    elif form in (5, 6):
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


def _std_table_style(n_rows, header_bg=None, header_fg=None, band_bg=None, necta=False, prestige=False):
    hdr = header_bg or NAVY
    hfg = header_fg or WHITE
    band = band_bg or CREAM
    if prestige:
        # royal/acsee: white/cream panel cells, silk or onyx header, thin
        # coloured grid + gold (acsee) / purple (royal) outer box.
        line_c = NECTA_GRID if False else (colors.HexColor("#C9A227") if hfg == colors.HexColor("#E5C96B") else colors.HexColor("#6B2FA0"))
        s = [
            ('BACKGROUND', (0, 0), (-1, 0), hdr),
            ('TEXTCOLOR', (0, 0), (-1, 0), hfg),
            ('BACKGROUND', (0, 1), (-1, -1), band),
            ('GRID', (0, 0), (-1, -1), 0.4, line_c),
            ('BOX', (0, 0), (-1, -1), 1.0, line_c),
            ('BOX', (0, 0), (-1, -1), 2.0, hdr),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]
        return s
    if necta:
        # NECTA sheet: every table cell is light yellow and the outer frame
        # is a DOUBLE line (mistari miwili) — the "table border + spacing"
        # look of NECTA's printed sheet. Header row keeps the same yellow.
        s = [
            ('BACKGROUND', (0, 0), (-1, 0), hdr),
            ('TEXTCOLOR', (0, 0), (-1, 0), hfg),
            ('BACKGROUND', (0, 1), (-1, -1), band),
            ('GRID', (0, 0), (-1, -1), 0.4, NECTA_GRID),
            ('BOX', (0, 0), (-1, -1), 1.0, NECTA_GRID),
            ('BOX', (0, 0), (-1, -1), 2.2, NECTA_TEXT_NAVY),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]
        return s
    s = [
        ('BACKGROUND', (0, 0), (-1, 0), hdr),
        ('TEXTCOLOR', (0, 0), (-1, 0), hfg),
        ('GRID', (0, 0), (-1, -1), 0.5, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]
    for i in range(1, n_rows):
        if i % 2 == 0:
            s.append(('BACKGROUND', (0, i), (-1, i), band))
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

    def __init__(self, exam, school_disp, slogo_uri, dlogo_uri, stype, lang, exam_title='', form_num=4, exam_month='', district='', coa_uri='', card_color=None, heading_color=None, card_border_color=None):
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
        # Theme-aware palette: the tint card behind the district/title/school
        # block and the navy accents switch with the output theme (necta
        # paints them light-yellow / NECTA navy — verified against NECTA's
        # own CSEE results HTML).
        self.card_color = card_color or TINT
        self.heading_color = heading_color or NAVY
        self.card_border_color = card_border_color
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
        # than plain white page background (necta theme: light yellow with
        # a double-line border, so it reads as a sticker PASTED onto the
        # blue page rather than just a colour change).
        c.setFillColor(self.card_color)
        if self.card_color is not None:
            c.rect(0, 0, w, logos_y, fill=1, stroke=0)
            c.setStrokeColor(self.card_border_color or NECTA_TEXT_NAVY)
            c.setLineWidth(2.0)
            c.rect(0, 0, w, logos_y, fill=0, stroke=1)
            c.setLineWidth(0.6)
            c.rect(1.6, 1.6, w - 3.2, logos_y - 3.2, fill=0, stroke=1)
        else:
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
        c.setFillColor(self.heading_color)
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
        c.setFillColor(self.heading_color)
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
        c.setFillColor(self.heading_color)
        c.setFont('Helvetica-Bold', 12)
        c.drawCentredString(cx, y, self.school_disp)

        # ── Gold line at bottom ──
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.5)
        c.line(0, 0, w, 0)


# ── Footer (per-page, without page numbers) ─────────────────────────────────
# ── Themed page decorations (creative backgrounds per output style) ──────
def _draw_creative_background(canvas, w, h, style_key):
    """Per-style full-page backdrop painted behind everything.

    normal : full CHALKBOARD (chokaa) green-black page — white 'chalk'
             doodles (corner sketches, star sprinkles, chalk frame) around
             a clean white results panel, like a classroom board presenting
             the results.
    rank   : full DEEP GREEN page with white chalk-style frame and
             gold-lime celebratory accents (star burst corners, ribbon
             rule) around a bright white results panel.
    necta  : handled elsewhere (flat light-blue + double frame).
    """
    if style_key == 'normal':
        BOARD   = colors.HexColor("#2E4638")   # chalkboard green-black
        BOARD_D = colors.HexColor("#263B2F")   # board edge shading
        CHALK   = colors.HexColor("#F5F2E8")   # chalk white
        CHALK_S = colors.HexColor("#D8D4C4")   # chalk shadow
        WOOD    = colors.HexColor("#B98A4E")   # wooden board frame
        WOOD_D  = colors.HexColor("#9A6F3C")
        PANEL   = colors.white                 # clean results panel
        PANEL_E = colors.HexColor("#2E4638")   # panel edge

        # 1. Full chalkboard page.
        canvas.setFillColor(BOARD)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        canvas.setFillColor(BOARD_D)
        canvas.rect(0, 0, w, h * 0.02, fill=1, stroke=0)
        canvas.rect(0, h * 0.98, w, h * 0.02, fill=1, stroke=0)

        # 2. Wooden board frame around the page edge.
        canvas.setFillColor(WOOD)
        canvas.rect(0, h - 0.55 * cm, w, 0.55 * cm, fill=1, stroke=0)
        canvas.rect(0, 0, w, 0.55 * cm, fill=1, stroke=0)
        canvas.rect(0, 0, 0.55 * cm, h, fill=1, stroke=0)
        canvas.rect(w - 0.55 * cm, 0, 0.55 * cm, h, fill=1, stroke=0)
        canvas.setStrokeColor(WOOD_D)
        canvas.setLineWidth(0.7)
        canvas.rect(0.55 * cm, 0.55 * cm, w - 1.1 * cm, h - 1.1 * cm)

        # 3. Chalk dust doodles — chalk stars sprinkled on the visible
        #    board margin (drawn before the panel so the panel overlaps
        #    cleanly).
        canvas.setStrokeColor(CHALK)
        canvas.setLineWidth(0.8)
        seed = 7
        def _chalk_star(cx0, cy0, rr, alpha_w=0.8):
            canvas.setStrokeColor(CHALK)
            canvas.setLineWidth(alpha_w)
            for k in range(4):
                import math
                ang = math.pi / 4 + k * math.pi / 2
                x1 = cx0 + rr * math.cos(ang)
                y1 = cy0 + rr * math.sin(ang)
                x2 = cx0 - rr * math.cos(ang)
                y2 = cy0 - rr * math.sin(ang)
                canvas.line(x1, y1, x2, y2)
        # sprinkle along left/right board margins
        positions = []
        for i in range(14):
            seed = (seed * 37 + 11) % 97
            fx = seed / 97.0
            seed = (seed * 41 + 23) % 97
            fy = seed / 97.0
            positions.append((0.28 * cm + fx * (w - 0.56 * cm),
                              0.8 * cm + fy * (h - 1.6 * cm)))
        for (sx, sy) in positions:
            # keep stars only near page edges (outside the panel zone)
            if sx < w * 0.085 or sx > w * 0.915:
                _chalk_star(sx, sy, 0.09 * cm)
        # big chalk stars at the four corners of the board area
        for cx0, cy0 in ((1.05 * cm, h - 1.05 * cm), (w - 1.05 * cm, h - 1.05 * cm),
                         (1.05 * cm, 1.05 * cm), (w - 1.05 * cm, 1.05 * cm)):
            _chalk_star(cx0, cy0, 0.28 * cm, 1.2)
            _chalk_star(cx0, cy0, 0.16 * cm, 0.8)

        # 4. White results panel — the 'board writing zone', inner shadow
        #    for depth, then a hand-drawn feel double chalk border.
        px0, py0 = 1.05 * cm, 1.05 * cm
        pw, ph = w - 2.1 * cm, h - 2.1 * cm
        canvas.setFillColor(CHALK_S)
        canvas.rect(px0 - 0.07 * cm, py0 - 0.07 * cm, pw + 0.14 * cm, ph + 0.14 * cm, fill=1, stroke=0)
        canvas.setFillColor(PANEL)
        canvas.rect(px0, py0, pw, ph, fill=1, stroke=0)
        canvas.setStrokeColor(PANEL_E)
        canvas.setLineWidth(1.3)
        canvas.rect(px0 + 0.06 * cm, py0 + 0.06 * cm, pw - 0.12 * cm, ph - 0.12 * cm)
        canvas.setStrokeColor(CHALK_S)
        canvas.setLineWidth(0.5)
        canvas.rect(px0 + 0.16 * cm, py0 + 0.16 * cm, pw - 0.32 * cm, ph - 0.32 * cm)

        # 5. Chalk tray — small wooden ledge at the bottom edge of the board.
        canvas.setFillColor(WOOD_D)
        canvas.rect(0.55 * cm, 0.42 * cm, w - 1.1 * cm, 0.13 * cm, fill=1, stroke=0)

    elif style_key == 'royal':
        # ═ FORM FIVE — ROYAL AMETHYST ═══════════════════════════════
        # Luminous lavender page; silk purple header band with a gold
        # medallion sunburst centred above the frame; gold laurel
        # half-wreaths in the corners; lavender silk side rails.
        ROY_BG    = colors.HexColor("#EFE7F9")   # luminous lavender
        ROY_ROYAL = colors.HexColor("#6B2FA0")   # royal purple silk
        ROY_DEEP  = colors.HexColor("#4A1D6E")   # deep aubergine
        ROY_GOLD  = colors.HexColor("#C9A227")   # heraldic gold
        ROY_GOLD2 = colors.HexColor("#E5C96B")   # light gold
        PANEL     = colors.white

        canvas.setFillColor(ROY_BG)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)

        # Purple silk bands top & bottom (double-tone).
        canvas.setFillColor(ROY_ROYAL)
        canvas.rect(0, h - 1.35 * cm, w, 1.35 * cm, fill=1, stroke=0)
        canvas.setFillColor(ROY_DEEP)
        canvas.rect(0, h - 0.45 * cm, w, 0.45 * cm, fill=1, stroke=0)
        canvas.setFillColor(ROY_GOLD)
        canvas.rect(0, h - 1.42 * cm, w, 0.07 * cm, fill=1, stroke=0)
        canvas.setFillColor(ROY_ROYAL)
        canvas.rect(0, 0.9 * cm, w, 0.45 * cm, fill=1, stroke=0)
        canvas.setFillColor(ROY_DEEP)
        canvas.rect(0, 0, w, 0.9 * cm, fill=1, stroke=0)

        # Gold medallion sunburst top-centre — radiating regal rays.
        import math
        mcx, mcy, mr = w / 2, h - 1.35 * cm, 0.55 * cm
        for k in range(12):
            ang = math.pi * 2 * k / 12
            canvas.setStrokeColor(ROY_GOLD if k % 2 == 0 else ROY_GOLD2)
            canvas.setLineWidth(1.0)
            canvas.line(mcx + 0.18 * cm * math.cos(ang), mcy + 0.18 * cm * math.sin(ang),
                        mcx + mr * math.cos(ang), mcy + mr * math.sin(ang))
        canvas.setFillColor(ROY_GOLD)
        canvas.circle(mcx, mcy, 0.16 * cm, fill=1, stroke=0)
        canvas.setStrokeColor(ROY_GOLD2)
        canvas.setLineWidth(0.8)
        canvas.circle(mcx, mcy, 0.22 * cm, fill=0, stroke=1)

        # Laurel half-wreaths in all four corners — paired gold arcs with
        # leaf ticks, the classic 'academic honour' mark.
        def _laurel(cx0, cy0, flip):
            for rr in (0.85 * cm, 0.62 * cm):
                canvas.setStrokeColor(ROY_GOLD)
                canvas.setLineWidth(1.0)
                canvas.arc(cx0 - rr, cy0 - rr, cx0 + rr, cy0 + rr,
                           0 if flip else 90, 90)
                canvas.setStrokeColor(ROY_GOLD2)
                canvas.setLineWidth(0.55)
                canvas.arc(cx0 - rr * 0.8, cy0 - rr * 0.8,
                           cx0 + rr * 0.8, cy0 + rr * 0.8,
                           8 if flip else 98, 74)
        for cx0, cy0, flip in (
            (1.3 * cm, h - 2.2 * cm, True), (w - 1.3 * cm, h - 2.2 * cm, False),
            (1.3 * cm, 2.2 * cm, False), (w - 1.3 * cm, 2.2 * cm, True),
        ):
            _laurel(cx0, cy0, flip)

        # Silk side rails — purple double rules with gold tips.
        for x in (0.9 * cm, w - 0.9 * cm):
            canvas.setStrokeColor(ROY_ROYAL)
            canvas.setLineWidth(1.1)
            canvas.line(x, 1.4 * cm, x, h - 1.9 * cm)
            canvas.setLineWidth(0.4)
            canvas.line(x + 0.1 * cm, 1.4 * cm, x + 0.1 * cm, h - 1.9 * cm)
            canvas.setFillColor(ROY_GOLD)
            canvas.circle(x, h - 1.9 * cm, 0.07 * cm, fill=1, stroke=0)
            canvas.circle(x, 1.4 * cm, 0.07 * cm, fill=1, stroke=0)

        # White results panel with purple double frame + inner gold line.
        px0, py0 = 1.0 * cm, 1.0 * cm
        pw, ph = w - 2.0 * cm, h - 2.0 * cm
        canvas.setFillColor(PANEL)
        canvas.rect(px0, py0, pw, ph, fill=1, stroke=0)
        canvas.setStrokeColor(ROY_ROYAL)
        canvas.setLineWidth(1.6)
        canvas.rect(px0 + 0.07 * cm, py0 + 0.07 * cm, pw - 0.14 * cm, ph - 0.14 * cm)
        canvas.setStrokeColor(ROY_GOLD)
        canvas.setLineWidth(0.6)
        canvas.rect(px0 + 0.2 * cm, py0 + 0.2 * cm, pw - 0.4 * cm, ph - 0.4 * cm)

    elif style_key == 'acsee':
        # ═ FORM SIX — BLACK & GOLD PRESTIGE ═════════════════════════
        # Onyx page; champagne-gold double frame with corner fleurons; a
        # gold 'tassel' drop top-centre; cream results panel. The
        # graduation-gala certificate look.
        ONYX     = colors.HexColor("#141414")
        ONYX_2   = colors.HexColor("#1F1F1F")
        GOLD_L   = colors.HexColor("#D4B14A")   # champagne gold line
        GOLD_L2  = colors.HexColor("#E5C96B")
        CREAM_P  = colors.HexColor("#FBF6E8")   # warm cream panel
        PANEL_E  = colors.HexColor("#8A6D1F")   # gold-bronze panel edge

        canvas.setFillColor(ONYX)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        canvas.setFillColor(ONYX_2)
        canvas.rect(0, 0, w, h * 0.025, fill=1, stroke=0)
        canvas.rect(0, h * 0.975, w, h * 0.025, fill=1, stroke=0)

        # Champagne double frame — outer heavy, inner hairline.
        canvas.setStrokeColor(GOLD_L)
        canvas.setLineWidth(1.8)
        canvas.rect(0.8 * cm, 0.8 * cm, w - 1.6 * cm, h - 1.6 * cm)
        canvas.setStrokeColor(GOLD_L2)
        canvas.setLineWidth(0.5)
        canvas.rect(0.95 * cm, 0.95 * cm, w - 1.9 * cm, h - 1.9 * cm)

        # Corner fleurons — diamond clusters in the frame corners.
        import math
        def _fleuron(cx0, cy0):
            canvas.setFillColor(GOLD_L)
            for dx, dy, sz in ((0, 0, 0.11 * cm), (0.16 * cm, 0.16 * cm, 0.06 * cm),
                               (-0.16 * cm, 0.16 * cm, 0.06 * cm),
                               (0.16 * cm, -0.16 * cm, 0.06 * cm),
                               (-0.16 * cm, -0.16 * cm, 0.06 * cm)):
                canvas.saveState()
                canvas.translate(cx0 + dx, cy0 + dy)
                canvas.rotate(45)
                canvas.rect(-sz / 2, -sz / 2, sz, sz, fill=1, stroke=0)
                canvas.restoreState()
        for cx0, cy0 in ((0.8 * cm, h - 0.8 * cm), (w - 0.8 * cm, h - 0.8 * cm),
                         (0.8 * cm, 0.8 * cm), (w - 0.8 * cm, 0.8 * cm)):
            _fleuron(cx0, cy0)

        # Gold tassel drop — centred cord + tassel head at the top edge.
        tcx = w / 2
        canvas.setStrokeColor(GOLD_L)
        canvas.setLineWidth(1.0)
        canvas.line(tcx, h - 0.8 * cm, tcx, h - 1.5 * cm)
        canvas.setFillColor(GOLD_L2)
        canvas.circle(tcx, h - 1.55 * cm, 0.09 * cm, fill=1, stroke=0)
        canvas.setLineWidth(0.7)
        for k in (-1, 0, 1):
            canvas.line(tcx + k * 0.06 * cm, h - 1.62 * cm,
                        tcx + k * 0.09 * cm, h - 1.85 * cm)

        # Cream results panel with gold double border.
        px0, py0 = 1.05 * cm, 1.05 * cm
        pw, ph = w - 2.1 * cm, h - 2.1 * cm
        canvas.setFillColor(CREAM_P)
        canvas.rect(px0, py0, pw, ph, fill=1, stroke=0)
        canvas.setStrokeColor(PANEL_E)
        canvas.setLineWidth(1.5)
        canvas.rect(px0 + 0.07 * cm, py0 + 0.07 * cm, pw - 0.14 * cm, ph - 0.14 * cm)
        canvas.setStrokeColor(GOLD_L)
        canvas.setLineWidth(0.6)
        canvas.rect(px0 + 0.2 * cm, py0 + 0.2 * cm, pw - 0.4 * cm, ph - 0.4 * cm)
        GREEN_BG  = colors.HexColor("#1F7A3D")   # full deep school green
        GREEN_D   = colors.HexColor("#155C2C")   # darker edge shading
        LIME      = colors.HexColor("#C8E06B")   # celebratory gold-lime
        CREAM_W   = colors.HexColor("#F8FAF2")   # warm white panel
        PANEL_E   = colors.HexColor("#1F7A3D")

        # 1. Full green page with darker top/bottom shading strips.
        canvas.setFillColor(GREEN_BG)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        canvas.setFillColor(GREEN_D)
        canvas.rect(0, 0, w, h * 0.03, fill=1, stroke=0)
        canvas.rect(0, h * 0.97, w, h * 0.03, fill=1, stroke=0)

        # 2. Celebratory star-burst corners — radiating gold-lime rays.
        import math
        for cx0, cy0, base in (
            (0.9 * cm, h - 0.9 * cm, 0),
            (w - 0.9 * cm, h - 0.9 * cm, 45),
            (0.9 * cm, 0.9 * cm, 90),
            (w - 0.9 * cm, 0.9 * cm, 135),
        ):
            for k in range(5):
                ang = math.radians(base + k * 22.5)
                r1, r2 = 0.18 * cm, (0.62 if k % 2 == 0 else 0.44) * cm
                canvas.setStrokeColor(LIME)
                canvas.setLineWidth(1.1 if k % 2 == 0 else 0.7)
                canvas.line(cx0 + r1 * math.cos(ang), cy0 + r1 * math.sin(ang),
                            cx0 + r2 * math.cos(ang), cy0 + r2 * math.sin(ang))

        # 3. Lime ribbon rules across the top and bottom margins.
        canvas.setStrokeColor(LIME)
        canvas.setLineWidth(1.2)
        canvas.line(0.9 * cm, h - 1.5 * cm, w - 0.9 * cm, h - 1.5 * cm)
        canvas.setLineWidth(0.5)
        canvas.line(0.9 * cm, h - 1.58 * cm, w - 0.9 * cm, h - 1.58 * cm)
        canvas.setLineWidth(1.2)
        canvas.line(0.9 * cm, 1.5 * cm, w - 0.9 * cm, 1.5 * cm)
        canvas.setLineWidth(0.5)
        canvas.line(0.9 * cm, 1.42 * cm, w - 0.9 * cm, 1.42 * cm)

        # 4. White results panel with green double border + inner lime line.
        px0, py0 = 1.0 * cm, 1.0 * cm
        pw, ph = w - 2.0 * cm, h - 2.0 * cm
        canvas.setFillColor(CREAM_W)
        canvas.rect(px0, py0, pw, ph, fill=1, stroke=0)
        canvas.setStrokeColor(PANEL_E)
        canvas.setLineWidth(1.5)
        canvas.rect(px0 + 0.07 * cm, py0 + 0.07 * cm, pw - 0.14 * cm, ph - 0.14 * cm)
        canvas.setStrokeColor(LIME)
        canvas.setLineWidth(0.6)
        canvas.rect(px0 + 0.18 * cm, py0 + 0.18 * cm, pw - 0.36 * cm, ph - 0.36 * cm)


def _footer(canvas, doc):
    canvas.saveState()
    try:
        w, h = doc.pagesize
    except Exception:
        w, h = A4

    # Themed page background. necta: flat light blue (authentic NECTA
    # sheet). normal/rank: creative per-style backdrop (ivory certificate /
    # mint TEC look) painted behind everything, before the border/content.
    style_key_bg = getattr(doc, '_style_key', 'normal')
    page_bg = getattr(doc, '_page_bg', None)
    if page_bg is not None:
        canvas.setFillColor(page_bg)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)

    _draw_creative_background(canvas, w, h, style_key_bg)

    if getattr(doc, '_necta_frame', False):
        # NECTA sheet frame: a DOUBLE line (mistari miwili myembili) running
        # around the whole page — outer thin + inner thick, like the printed
        # NECTA results sheet's boxed edge. (normal/rank already got their
        # own content frames inside _draw_creative_background.)
        canvas.setStrokeColor(NECTA_TEXT_NAVY)
        canvas.setLineWidth(2.0)
        canvas.rect(1.0 * cm, 0.8 * cm, w - 2.0 * cm, h - 1.6 * cm)
        canvas.setLineWidth(0.6)
        canvas.rect(1.14 * cm, 0.94 * cm, w - 2.28 * cm, h - 1.88 * cm)

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
def generate_results_pdf_response(exam, style='normal'):
    st = _styles()
    style_key = (style or 'normal').lower()
    is_normal_style = style_key == 'normal'
    is_necta = style_key == 'necta'
    is_prestige = style_key in ('royal', 'acsee')
    theme = _resolve_theme(style)
    # Re-tint the shared paragraph styles for this theme. _styles() returns
    # fresh objects every call, so mutating them here is local to this PDF.
    st['th'].textColor = theme['header_fg']
    st['th_sm'].textColor = theme['header_fg']
    # necta: NECTA prints its own headings purple ("FONT COLOR=\"#800080\""
    # in their results HTML) — so here the section titles DO take the
    # theme's purple, unlike before.
    st['section'].textColor = theme['section_fg']
    if is_necta:
        # NECTA prints everything navy on the sheet (BODY TEXT="#000080").
        st['title_lg'].textColor = NECTA_TEXT_NAVY
        st['title_md'].textColor = NECTA_TEXT_NAVY
    if is_prestige:
        st['title_lg'].textColor = theme['section_fg']
        st['title_md'].textColor = theme['section_fg']
    _HB, _HF, _BB = theme['header_bg'], theme['header_fg'], theme['band_bg']
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
    # Namba za CNO/POS: 1..N kwa mpangilio wa ROSTER (si performance rank).
    # Rank halisi bado ipo kwenye r.position — inatumika kwenye TOP 5 tu.
    roster_numbers = payload.get('roster_numbers', {})
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
    is_primary = school_type == 'primary'

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
            gp_scores = [_grade_point(_grade_for_score(sc, exam.form, primary=is_primary), exam.form, primary=is_primary) for sc in scores]
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
        card_color=theme['band_bg'] if (is_necta or is_prestige) else None,
        heading_color=NECTA_TEXT_NAVY if is_necta else (theme['header_bg'] if is_prestige else None),
        card_border_color=colors.HexColor('#C9A227') if style_key == 'royal' else (colors.HexColor('#8A6D1F') if style_key == 'acsee' else None),
    ))
    story.append(Spacer(1, 8))

    # ── DIVISION PERFORMANCE SUMMARY ──
    # Msingi: badala ya madivisheni, onyesha ugawaji wa gredi za wastani
    # (Average Grade A-E) — PSLE haipo division.
    if is_primary:
        avg_grade_lookup = {
            r.student_id: _grade_for_score(float(r.average_score), exam.form, primary=True)
            for r in results
        }
        story.append(_p("<b>GAWA LA GREDI ZA WASTANI</b>", st['section']))
        div_hdrs = ["SEX", "A", "B", "C", "D", "E"]
        div_data = [[_p(f"<b>{h}</b>", st['th']) for h in div_hdrs]]
        for sex_label in ('F', 'M', 'T'):
            def _cnt(sex, grade):
                if sex == 'T':
                    return sum(1 for r in results if avg_grade_lookup.get(r.student_id) == grade)
                return sum(
                    1 for r in results
                    if (r.student.gender or 'M').upper() == sex
                    and avg_grade_lookup.get(r.student_id) == grade
                )
            row = [_p(f"<b>{sex_label}</b>", st['td_bold'])]
            for grade in ('A', 'B', 'C', 'D', 'E'):
                row.append(_p(str(_cnt(sex_label, grade)), st['td']))
            div_data.append(row)
    else:
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
    ds = _std_table_style(len(div_data), header_bg=_HB, header_fg=_HF, band_bg=_BB, necta=is_necta, prestige=is_prestige)
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
    perf_table.setStyle(TableStyle(_std_table_style(len(perf_data), header_bg=_HB, header_fg=_HF, band_bg=_BB, necta=is_necta, prestige=is_prestige)))

    _, grades = _grading_thresholds(exam.form, primary=is_primary)
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
        ('BACKGROUND', (0, 0), (-1, 0), _HB),
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
        s_table.setStyle(TableStyle(_std_table_style(len(s_data), header_bg=_HB, header_fg=_HF, band_bg=_BB, necta=is_necta, prestige=is_prestige)))
        story.append(s_table)
        story.append(Spacer(1, 4))

    # ── TOP 5 ──
    # results is in registration order (see get_exam_export_payload), NOT
    # ranked by score — sort a copy by position here so "Top 5" is always
    # the 5 actual best performers, regardless of the main table's order.
    if results:
        story.append(_p("<b>TOP 5 PERFORMERS</b>", st['section']))
        th5 = ["POS", "NAME", "TOTAL", "AVG", "GPA", "PTS", "DIV"]
        t_data = [[_p(f"<b>{h}</b>", st['th']) for h in th5]]
        top5 = sorted(results, key=lambda r: r.position)[:5]
        for idx, r in enumerate(top5):
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
        ts = _std_table_style(len(t_data), header_bg=_HB, header_fg=_HF, band_bg=_BB, necta=is_necta, prestige=is_prestige)
        ts.append(('BACKGROUND', (0, 1), (-1, 1), theme['accent_bg']))
        ts.append(('TEXTCOLOR', (0, 1), (-1, 1), theme['accent_fg']))
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

    r_hdr = (["CNO", "NAME", "SEX", "JUMLA", "WASTANI", "GREDI", "DETAILED SUBJECTS"]
             if is_primary else
             ["CNO", "NAME", "SEX", "AGGT", "GPA", "DIV", "DETAILED SUBJECTS"])
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
    necta_frames = []  # parallel to all_rows: per-row mini-table (necta) or None
    for r in results:
        # CNO = namba ya mwanafunzi kwenye ROSTER (1..N), si performance rank
        cno = f"{roster_numbers.get(r.student_id, r.position):03d}"
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
                g = _grade_for_score(sc, exam.form, primary=is_primary)
            abbr = (sub.code or '').strip().upper() or (
                sub.name.upper()[:4] if len(sub.name) > 4 else sub.name.upper()
            )
            if is_normal_style:
                fg = GRADE_COLORS.get(g, ('#555555', '#E8E8E8'))[0]
            else:
                # rank/necta mimic a specific reference sheet that doesn't
                # colour-code individual grades (no red for a fail, etc.)
                # — the pass/fail rainbow is the 'normal' system look only.
                fg = _UNIFORM_GRADE_TEXT_HEX.get(style_key, '#1F1F1F')
            subj_parts.append(
                f"<font color='{fg}'><b>{abbr}-{g}</b></font>"
            )
        subj_text = '&nbsp;'.join(subj_parts)

        if is_normal_style:
            div_bg = DIV_BG.get(r.division, WHITE)
            div_fg = DIV_FG.get(r.division, BLACK)
        elif style_key in DIV_BG_THEME:
            # royal/acsee: themed honour chips — Division I shines gold /
            # champagne, lower divisions step down through the theme's tint
            # ladder so every division reads clearly on the panel.
            div_bg = DIV_BG_THEME[style_key].get(r.division, theme['band_bg'])
            div_fg = DIV_FG_THEME[style_key].get(r.division, theme['section_fg'])
        else:
            div_bg = theme['band_bg']
            div_fg = theme['header_fg']
        dv_st = ParagraphStyle(f'dv4_{r.student_id}', parent=cell_st,
                               backColor=div_bg, textColor=div_fg,
                               fontName='Helvetica-Bold')

        if is_primary:
            avg_g = _grade_for_score(float(r.average_score), exam.form, primary=True)
            row_cells = [
                _p(cno, cell_st),
                _p(nm, name_st),
                _p(r.student.gender or 'M', cell_st),
                _p(str(r.total_score), cell_bold),
                _p(f"{float(r.average_score):.1f}", cell_bold),
                _p(avg_g or '-', dv_st),
                _p(subj_text, subj_st),
            ]
        else:
            row_cells = [
                _p(cno, cell_st),
                _p(nm, name_st),
                _p(r.student.gender or 'M', cell_st),
                _p(str(r.points), cell_bold),
                _p(f"{stu_gpa:.2f}", cell_bold),
                _p(str(r.division), dv_st),
                _p(subj_text, subj_st),
            ]
        if is_necta or is_prestige:
            # Framed per-student rows (NECTA double frame; prestige gets a
            # single elegant box in the theme's accent colour). Stored
            # parallel to all_rows and swapped in when the page tables are
            # assembled, so the real measured heights below already include
            # the frame.
            mini = Table([row_cells], colWidths=cw)
            if is_necta:
                mini_style = [
                    ('BOX', (0, 0), (-1, -1), 1.0, NECTA_GRID),
                    ('BOX', (0, 0), (-1, -1), 2.2, NECTA_TEXT_NAVY),
                ]
            elif style_key == 'royal':
                mini_style = [
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F4EFFA")),
                    ('BOX', (0, 0), (-1, -1), 1.1, colors.HexColor("#6B2FA0")),
                    ('LINEBELOW', (0, -1), (-1, -1), 0.5, colors.HexColor("#C9A227")),
                ]
            else:  # acsee
                mini_style = [
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#FBF6E8")),
                    ('BOX', (0, 0), (-1, -1), 1.1, colors.HexColor("#8A6D1F")),
                    ('LINEBELOW', (0, -1), (-1, -1), 0.5, colors.HexColor("#D4B14A")),
                ]
            mini_style += [
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ]
            mini.setStyle(TableStyle(mini_style))
            necta_frames.append(mini)
            all_rows.append(row_cells)
        else:
            necta_frames.append(None)
            all_rows.append(row_cells)

    row_heights = []
    for frame, cells in zip(necta_frames, all_rows):
        if frame is not None:
            # NECTA: the frame itself adds ~3pt of border + the outer
            # table's 2+2pt padding — measure the real mini-table height so
            # page packing doesn't underestimate and overflow a page.
            _, fh = frame.wrap(content_w, 10000)
            row_heights.append(fh + 4)
        else:
            row_heights.append(_row_cells_height(cells))

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
    if is_necta:
        gk_table_pg.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1.0, NECTA_GRID),
            ('BOX', (0, 0), (-1, -1), 2.2, NECTA_TEXT_NAVY),
        ]))
    tail_flowables.append(Spacer(1, 6))
    tail_flowables.append(gk_table_pg)
    tail_flowables.append(Spacer(1, 5))

    # Centre performance summary
    tail_flowables.append(_p("<b>EXAMINATION CENTRE OVERALL PERFORMANCE</b>", st['section']))
    # Centre overall performance — msingi inagredi za wastani (A-E),
    # sekondari madivisheni (I-0).
    if is_primary:
        div_perf_hdrs = ["", "REGIST", "ABSENT", "SAT", "CLEAN", "A", "B", "C", "D", "E"]
        absent_count = sum(1 for r in results if r.total_score == 0)
        dp_data = [[_p(f"<b>{h}</b>", ParagraphStyle('dph', parent=cell_st, fontSize=6, textColor=_HF, fontName='Helvetica-Bold')) for h in div_perf_hdrs]]
        dp_row = [_p("<b>TOTAL</b>", ParagraphStyle('dpt', parent=cell_st, fontSize=6, fontName='Helvetica-Bold'))]
        dp_row += [
            _p(str(N), cell_st), _p(str(absent_count), cell_st),
            _p(str(N - absent_count), cell_st), _p(str(N - absent_count), cell_st),
        ]
        for grade in ('A', 'B', 'C', 'D', 'E'):
            dp_row.append(_p(str(sum(1 for r in results if avg_grade_lookup.get(r.student_id) == grade)), cell_st))
        dp_data.append(dp_row)
    else:
        div_perf_hdrs = ["", "REGIST", "ABSENT", "SAT", "CLEAN", "DIV I", "DIV II", "DIV III", "DIV IV", "DIV 0"]
        absent_count = sum(1 for r in results if r.total_score == 0)
        dp_data = [[_p(f"<b>{h}</b>", ParagraphStyle('dph', parent=cell_st, fontSize=6, textColor=_HF, fontName='Helvetica-Bold')) for h in div_perf_hdrs]]
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
    dp_style = [
        ('BACKGROUND', (0, 0), (-1, 0), _HB),
        ('TEXTCOLOR', (0, 0), (-1, 0), _HF),
        ('GRID', (0, 0), (-1, -1), 0.3, LGRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]
    if is_necta:
        dp_style += [
            ('BACKGROUND', (0, 1), (-1, -1), _BB),
            ('BOX', (0, 0), (-1, -1), 1.0, NECTA_GRID),
            ('BOX', (0, 0), (-1, -1), 2.2, NECTA_TEXT_NAVY),
        ]
    dp_table.setStyle(TableStyle(dp_style))
    tail_flowables.append(dp_table)
    tail_flowables.append(Spacer(1, 4))

    # Subject performance
    if subj_gpa:
        tail_flowables.append(_p("<b>SUBJECT PERFORMANCE</b>", st['section']))
        sp_hdrs = ["#", "SUBJECT", "SAT", "PASS", "GPA", "LEVEL"]
        sp_data = [[_p(f"<b>{h}</b>", ParagraphStyle('sph', parent=cell_st, fontSize=6, textColor=_HF, fontName='Helvetica-Bold')) for h in sp_hdrs]]
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
        sp_table.setStyle(TableStyle(_std_table_style(len(sp_data), header_bg=_HB, header_fg=_HF, band_bg=_BB, necta=is_necta, prestige=is_prestige)))
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
    # (Under necta each row is a framed mini-table that renders a few points
    # taller than its bare cells, so a safety margin keeps ReportLab's own
    # wrapping from spilling a framed row onto its own page. 'normal' keeps
    # its original packing behaviour untouched — margin 0, exactly as before.)
    chunks = []
    idx = 0
    n_rows = len(all_rows)
    safety = SAFETY_MARGIN + 12 if (is_necta or is_prestige) else 0
    while idx < n_rows:
        cum = header_h
        j = idx
        while j < n_rows and (j == idx or cum + row_heights[j] <= available_h - safety):
            cum += row_heights[j]
            j += 1
        chunks.append((idx, j))
        idx = j
    if not chunks:
        chunks = [(0, 0)]

    c_start, c_end = chunks[-1]
    last_page_used = header_h + sum(row_heights[c_start:c_end])
    if last_page_used + tail_reserve > available_h - safety:
        chunks.append((n_rows, n_rows))  # tail doesn't fit here — give it its own page

    total_pages = len(chunks)

    for pg_idx, (c_start, c_end) in enumerate(chunks, 1):
        # ── Header on EVERY page (official format) ──
        story.append(NECTAHeader(
            exam, school_disp, slogo_uri, dlogo_uri, stype, lang,
            exam_title=exam_title, form_num=exam.form,
            exam_month=exam_month, district=district,
            coa_uri=coa_uri,
            card_color=theme['band_bg'] if (is_necta or is_prestige) else None,
            heading_color=NECTA_TEXT_NAVY if is_necta else (theme['header_bg'] if is_prestige else None),
            card_border_color=colors.HexColor('#C9A227') if style_key == 'royal' else (colors.HexColor('#8A6D1F') if style_key == 'acsee' else None),
        ))
        story.append(Spacer(1, 6))

        # ── Build SEPARATE table for this chunk (no splitting!) ──
        # A chunk can be empty when the tail block didn't fit on the
        # previous page and got bumped to a page of its own — skip the
        # table entirely rather than render one with just a header row.
        if c_end > c_start:
            if is_necta or is_prestige:
                # Framed-row themes: each candidate's row IS a mini-table
                # nested inside the page table and SPANned across all
                # columns. Each cell is a LIST of flowables (ReportLab's
                # format for nested content).
                data = [_new_header_row()] + [
                    [[f]] for f in necta_frames[c_start:c_end]
                ]
            else:
                data = [_new_header_row()] + all_rows[c_start:c_end]

            r_table = Table(data, colWidths=cw)
            rs = [
                ('BACKGROUND', (0, 0), (-1, 0), _HB),
                ('TEXTCOLOR', (0, 0), (-1, 0), _HF),
                ('GRID', (0, 0), (-1, -1), 0.3, DARK_LINE),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ]
            if is_necta or is_prestige:
                # Body rows are single SPANned cells holding the framed
                # mini-table: theme band behind them, zero side padding so
                # the mini-table's columns line up 1:1 with the header's,
                # and no inner grid (the mini-tables draw their own frames).
                # Double outer frame around the whole table.
                _outer = (NECTA_GRID, NECTA_TEXT_NAVY) if is_necta else (
                    (colors.HexColor("#C9A227"), colors.HexColor("#4A1D6E")) if style_key == 'royal'
                    else (colors.HexColor("#8A6D1F"), colors.HexColor("#1A1A1A"))
                )
                rs = [
                    ('BACKGROUND', (0, 0), (-1, 0), _HB),
                    ('TEXTCOLOR', (0, 0), (-1, 0), _HF),
                    ('GRID', (0, 0), (-1, 0), 0.3, DARK_LINE),
                    ('BACKGROUND', (0, 1), (-1, -1), _BB),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, 0), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
                    ('LEFTPADDING', (0, 0), (-1, 0), 3),
                    ('RIGHTPADDING', (0, 0), (-1, 0), 3),
                    ('TOPPADDING', (0, 1), (-1, -1), 2),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
                    ('LEFTPADDING', (0, 1), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 1), (-1, -1), 0),
                ]
                for i in range(1, len(data)):
                    rs.append(('SPAN', (0, i), (-1, i)))
                rs.append(('BOX', (0, 0), (-1, -1), 1.0, _outer[0]))
                rs.append(('BOX', (0, 0), (-1, -1), 2.2, _outer[1]))
            for i in range(1, len(data)):
                if i % 2 == 0 and not (is_necta or is_prestige):
                    rs.append(('BACKGROUND', (0, i), (-1, i), _BB))
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
    doc._page_bg = theme['page_bg']
    doc._style_key = style_key
    # necta: swap the navy+gold page border for the NECTA double-line frame
    doc._necta_frame = is_necta

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
def _build_student_result_pdf_bytes(result, *, school_type=None, total_students=None,
                                     scores=None, subjects=None, subject_ranks=None,
                                     style='normal'):
    """Full NECTA-style report card for a single ProcessedResult — same
    official header as the full class report, personalised below it with
    this student's own subjects/scores/grades (each with its own
    within-subject rank and an auto-derived comment), a conduct table, a
    grading-key legend, the class teacher's / headmaster's comments, term
    dates, and a parent sign-off block. Returns a seeked-to-0 BytesIO —
    shared by the single-student download and the "all students, one
    file" bulk download, which merges one of these per student.

    school_type/total_students/scores/subjects/subject_ranks are optional
    precomputed values — the bulk download passes them in (computed once
    for the whole exam) so this doesn't re-run the same exam-wide/cross-DB
    queries once per student; the single-student download leaves them
    None and this looks up what it can itself (subject_ranks is simply
    skipped — a single-slip download doesn't need to compute an entire
    exam's rankings for one student's NAFASI column)."""
    from reportlab.platypus import SimpleDocTemplate

    exam = result.exam
    student = result.student
    st = _styles()
    # ── Theme (normal | rank | necta | royal | acsee) — same treatment as
    #    the full class report in generate_results_pdf_response: palette/row
    #    styling only, content identical. ──
    style_key = (style or 'normal').lower()
    is_necta = style_key == 'necta'
    is_prestige = style_key in ('royal', 'acsee')
    theme = _resolve_theme(style)
    st['th'].textColor = theme['header_fg']
    st['th_sm'].textColor = theme['header_fg']
    st['section'].textColor = theme['section_fg']
    if is_necta:
        st['title_lg'].textColor = NECTA_TEXT_NAVY
        st['title_md'].textColor = NECTA_TEXT_NAVY
    if is_prestige:
        st['title_lg'].textColor = theme['section_fg']
        st['title_md'].textColor = theme['section_fg']
    _HB, _HF, _BB = theme['header_bg'], theme['header_fg'], theme['band_bg']
    school_disp = get_full_school_name(exam)
    lang = get_report_language(exam)
    etype = exam.get_exam_type_display().upper()
    exam_title = exam.name.upper() if exam.name else etype
    gen_date_short = datetime.now().strftime('%d/%m/%Y')
    if school_type is None:
        school_type = get_school_type_for_exam(exam)
    stype = "SECONDARY SCHOOL" if school_type == 'secondary' else "PRIMARY SCHOOL"
    is_primary = school_type == 'primary'

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
    division_label = (
        _grade_for_score(float(result.average_score), exam.form, primary=True)
        if is_primary
        else dict(ProcessedResult.DIVISION_CHOICES).get(result.division, result.division)
    )

    page_w, page_h = A4
    margin_lr = 1.6 * cm
    content_w = page_w - 2 * margin_lr

    story = [
        NECTAHeader(
            exam, school_disp, slogo_uri, dlogo_uri, stype, lang,
            exam_title=exam_title, form_num=exam.form,
            exam_month=exam_month, district=district, coa_uri=coa_uri,
            card_color=theme['band_bg'] if (is_necta or is_prestige) else None,
            heading_color=NECTA_TEXT_NAVY if is_necta else (theme['header_bg'] if is_prestige else None),
            card_border_color=colors.HexColor('#C9A227') if style_key == 'royal' else (colors.HexColor('#8A6D1F') if style_key == 'acsee' else None),
        ),
        Spacer(1, 10),
        _p(f"<b>JINA LA MWANAFUNZI:</b> {student_name.upper()}", st['title_md']),
        _p(
            f"<b>KIDATO:</b> {exam.FORM_LABELS.get(exam.form, f'Form {exam.form}')}"
            f"{' ' + exam.stream if exam.stream else ''} &nbsp;&nbsp;&nbsp; "
            f"<b>JINSI:</b> {student.gender or '-'} &nbsp;&nbsp;&nbsp; "
            f"<b>MWAKA:</b> {exam.year}",
            st['subtitle'],
        ),
        _p(f"{_location_str(exam)}", st['subtitle']),
        Spacer(1, 10),
    ]

    # ── Subjects table (NAFASI = rank within that subject, MAONI = a
    #    short comment auto-derived from the grade — no stored data for
    #    either) ──
    subj_hdrs = ["SOMO", "ALAMA", "DARAJA", "NAFASI", "MAONI"]
    subj_rows = [[_p(f"<b>{h}</b>", st['th_sm']) for h in subj_hdrs]]
    for subj in subjects:
        score = scores.get(subj.id)
        if score is None:
            continue
        grade = _grade_for_score(score, exam.form, primary=is_primary)
        rank = (subject_ranks or {}).get(subj.id, {}).get(student.id)
        subj_rows.append([
            _p(subj.name, st['td_name']),
            _p(str(score), st['td']),
            _p(grade or '-', st['td_bold']),
            _p(str(rank) if rank else '-', st['td']),
            _p(GRADE_MEANING_SW.get(grade, '-'), st['td_sm']),
        ])
    subj_table = Table(subj_rows, colWidths=[
        content_w * 0.32, content_w * 0.13, content_w * 0.13, content_w * 0.14, content_w * 0.28,
    ])
    subj_table.setStyle(TableStyle(_std_table_style(len(subj_rows), header_bg=_HB, header_fg=_HF, band_bg=_BB, necta=is_necta, prestige=is_prestige)))
    story.append(subj_table)
    story.append(Spacer(1, 14))

    # ── Summary box ──
    story.append(_p("<b>MUHTASARI</b>", st['section']))
    summary_hdrs = (["JUMLA", "WASTANI", "GREDI YA WASTANI", "NAFASI"]
                    if is_primary else
                    ["JUMLA", "WASTANI", "POINTS", "DIVISION", "NAFASI"])
    if is_primary:
        summary_row = [
            str(result.total_score),
            str(result.average_score),
            division_label,
            f"{result.position} / {total_students}",
        ]
    else:
        summary_row = [
            str(result.total_score),
            str(result.average_score),
            str(result.points),
            division_label,
            f"{result.position} / {total_students}",
        ]
    summary_table = Table(
        [[_p(f"<b>{h}</b>", st['th_sm']) for h in summary_hdrs], [_p(v, st['td_bold']) for v in summary_row]],
        colWidths=[content_w / len(summary_hdrs)] * len(summary_hdrs),
    )
    summary_table.setStyle(TableStyle(_std_table_style(
        2,
        header_bg=GREEN if style_key == 'normal' else _HB,
        header_fg=WHITE if style_key == 'normal' else _HF,
        band_bg=_BB,
        necta=is_necta, prestige=is_prestige,
    )))
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # ── TABIA NA MWENENDO (conduct) ──
    # Each category is its own grade, set by the exam's class_teacher —
    # deliberately NOT the same letter repeated across the row (a student
    # weak academically can still be strong on Michezo/Nidhamu/Usafi, and
    # parents flagged every student's row looking identical when it was).
    # Laid out as one compact row (like the grading key below) rather than
    # 6 stacked rows, which alone was pushing every slip onto a second,
    # near-empty page.
    story.append(_p("<b>TABIA NA MWENENDO</b>", st['section']))
    conduct_cats = [
        ('uaminifu', 'UAMINIFU'), ('kujitolea', 'KUJITOLEA'), ('kufanya_kazi', 'KUFANYA KAZI'),
        ('nidhamu', 'NIDHAMU'), ('usafi', 'USAFI'), ('michezo', 'MICHEZO'),
    ]
    conduct_grades = result.conduct_grades or {}
    conduct_table = Table(
        [[_p(f"<b>{label}</b>", st['th_sm']) for _key, label in conduct_cats],
         [_p(conduct_grades.get(key, '-'), st['td_bold']) for key, _label in conduct_cats]],
        colWidths=[content_w / len(conduct_cats)] * len(conduct_cats),
    )
    conduct_table.setStyle(TableStyle(_std_table_style(2, header_bg=_HB, header_fg=_HF, band_bg=_BB, necta=is_necta, prestige=is_prestige)))
    story.append(conduct_table)
    story.append(Spacer(1, 10))

    # ── MCHANGANUO (grading key) ──
    story.append(_p("<b>MCHANGANUO</b>", st['section']))
    _, grade_bands = _grading_thresholds(exam.form, primary=is_primary)
    mchanganuo_rows = [[_p(f"<b>{h}</b>", st['th_sm']) for h in ["ALAMA", "DARAJA", "MAANA"]]]
    for g, rng in grade_bands:
        mchanganuo_rows.append([_p(rng, st['td']), _p(g, st['td_bold']), _p(GRADE_MEANING_SW.get(g, '-'), st['td'])])
    mchanganuo_table = Table(mchanganuo_rows, colWidths=[content_w * 0.3, content_w * 0.2, content_w * 0.5])
    mchanganuo_table.setStyle(TableStyle(_std_table_style(len(mchanganuo_rows), header_bg=_HB, header_fg=_HF, band_bg=_BB, necta=is_necta, prestige=is_prestige)))
    story.append(mchanganuo_table)
    story.append(Spacer(1, 10))

    # ── Term dates + comments + parent sign-off ──
    # class_teacher_comment/headmaster_comment are free text set once for
    # the whole exam (see set_class_teacher / set_conduct_and_comments) —
    # escape before handing to Paragraph, which parses its text as a small
    # XML-like markup (an unescaped '<' or '&' would otherwise corrupt or
    # silently truncate the printed comment).
    def _fmt_term_date(d):
        return d.strftime('%d/%m/%Y') if d else '.......................'

    story.append(_p(
        f"<b>SHULE IMEFUNGWA TAREHE:</b> {_fmt_term_date(exam.term_closing_date)}"
        f"&nbsp;&nbsp;&nbsp;&nbsp;<b>SHULE ITAFUNGULIWA TAREHE:</b> {_fmt_term_date(exam.term_opening_date)}",
        st['td_name'],
    ))
    story.append(Spacer(1, 8))
    story.append(_p(
        f"<b>MAONI YA MWALIMU WA DARASA:</b> "
        f"{_xml_escape(exam.class_teacher_comment) if exam.class_teacher_comment else '.......................................................'}",
        st['td_name'],
    ))
    story.append(Spacer(1, 6))
    story.append(_p(
        f"<b>MAONI YA MKUU WA SHULE:</b> "
        f"{_xml_escape(exam.headmaster_comment) if exam.headmaster_comment else '.......................................................'}",
        st['td_name'],
    ))
    story.append(Spacer(1, 8))
    story.append(_p("<b>MAONI YA MZAZI/MLEZI:</b>", st['td_name']))
    story.append(Spacer(1, 10))
    story.append(_p(".................................................................................", st['td_name']))
    story.append(Spacer(1, 6))
    story.append(_p(
        "JINA LA MZAZI/MLEZI: ......................................... "
        "SIMU: ..................... SAHIHI: .....................",
        st['sig'],
    ))

    # ── QR ya uthibitisho (anti-forgery) ──
    # Kila slip ina token moja; QR inaelekeza /results/verify/<token>/ —
    # mzazi anascan bila account na anapata matokeo halisi kutoka DB.
    # Hakuna token → inaundwa wastaharabu (historical slips zinafaulu
    # bila migration ya data). PDF generation haipaswi kufeli kwenye
    # DB hiccup — QR ni optimization, siyo muhimu kwa slip yenyewe.
    try:
        vt = _get_or_create_verification_token(result)
        verify_path = f"/results/verify/{vt.token}/"
        qr_img = _qr_data_uri(verify_path)
        if qr_img:
            qr_table = Table(
                [[_p(
                    "<b>THIBITISHA MATOKEO</b><br/>Scan QR — angalia matokeo halisi online",
                    ParagraphStyle('qr', parent=st['sig'], fontSize=7, alignment=1),
                ), Image(io.BytesIO(qr_img), width=1.7 * cm, height=1.7 * cm)]],
                colWidths=[content_w - 2.2 * cm, 2.2 * cm],
            )
            qr_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                ('BOX', (0, 0), (-1, -1), 0.8, theme['header_bg']),
                ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(Spacer(1, 6))
            story.append(qr_table)
    except Exception:
        logger.warning("QR verification block failed for result %s", getattr(result, 'id', '?'), exc_info=True)

    story.append(Spacer(1, 6))
    story.append(_p("Haya ni matokeo rasmi yaliyotolewa na mfumo wa shule.", st['sig']))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=0.6 * cm, bottomMargin=1.3 * cm, leftMargin=margin_lr, rightMargin=margin_lr,
        title=f"{school_disp} — {student_name} — {etype} {exam.year}",
    )
    doc._exam = exam
    doc._gen_date_short = gen_date_short
    doc._page_bg = theme['page_bg']
    doc._style_key = style_key
    # necta: swap the navy+gold page border for the NECTA double-line frame
    doc._necta_frame = is_necta
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


def generate_bulk_student_results_pdf_response(exam, style='normal'):
    """All students of this exam (i.e. this form — an Exam is already
    scoped to one form/year/type), each on their own page(s), merged into
    ONE downloadable PDF — same slip _build_student_result_pdf_bytes
    produces for a single student, just all of them together in the same
    registration order (order_by_registration — see export_data.py) used
    for the roster list elsewhere in the system, not ranked by position.
    Mirrors the merge pattern curriculum/views.py's
    download_all_lesson_plans_pdf already uses for the same "many small
    PDFs -> one file" need."""
    import pypdfium2 as pdfium

    results = order_by_registration(
        exam,
        ProcessedResult.objects.filter(exam=exam)
        .select_related('student', 'exam', 'exam__school'),
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
    # {subject_id: [(score, student_id), ...]} — for the per-subject NAFASI
    # column; absent/no-score entries don't get ranked, same as
    # subject_pdf_service.py's existing single-subject ranking.
    scored_by_subject = defaultdict(list)
    for er in ExamResult.objects.filter(exam=exam, student_id__in=student_ids).select_related('subject'):
        scores_by_student.setdefault(er.student_id, {})[er.subject_id] = er.score
        subjects_by_student.setdefault(er.student_id, {})[er.subject_id] = er.subject
        if er.score is not None and not er.is_absent:
            scored_by_subject[er.subject_id].append((er.score, er.student_id))
    for sid, subj_map in subjects_by_student.items():
        subjects_by_student[sid] = sorted(subj_map.values(), key=lambda s: s.name)

    subject_ranks = {}  # {subject_id: {student_id: rank}}
    for subject_id, pairs in scored_by_subject.items():
        pairs.sort(key=lambda p: -p[0])
        subject_ranks[subject_id] = {sid: i + 1 for i, (_score, sid) in enumerate(pairs)}

    merged = pdfium.PdfDocument.new()
    buffers = []
    for result in results:
        buf = _build_student_result_pdf_bytes(
            result,
            school_type=school_type,
            total_students=total_students,
            scores=scores_by_student.get(result.student_id, {}),
            subjects=subjects_by_student.get(result.student_id, []),
            subject_ranks=subject_ranks,
            style=style,
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
