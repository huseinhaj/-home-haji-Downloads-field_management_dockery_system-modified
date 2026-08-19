"""
pdf_export_service.py — Professional NECTA-style academic report PDF.

Uses ReportLab Platypus (flowable-based layout) for automatic spacing —
no more overlapping tables or text.

Page 1   SUMMARY — Division breakdown + Performance Summary + Subject Stats + Top 5
Page 2+  FULL RESULTS — NECTA-style colour-coded scores table with GPA
"""

from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Paragraph,
    PageBreak,
    KeepTogether,
)

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


# ── NECTA grading ────────────────────────────────────────────────────────────
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


def _load_logo(filename):
    """Load logo from static/results/logos/ directory."""
    candidates = [
        Path(settings.BASE_DIR) / 'results' / 'static' / 'results' / 'logos' / filename,
    ]
    if hasattr(settings, 'STATICFILES_DIRS') and settings.STATICFILES_DIRS:
        for d in settings.STATICFILES_DIRS:
            candidates.insert(0, Path(d) / 'results' / 'logos' / filename)
    for path in candidates:
        if path and path.exists():
            try:
                return ImageReader(str(path))
            except Exception:
                pass
    return None


def _get_location(exam):
    parts = []
    if exam.school and exam.school.district:
        parts.append(exam.school.district)
    if exam.school and exam.school.region:
        parts.append(exam.school.region)
    return ' — '.join(p.upper() for p in parts) if parts else "LOCATION UNKNOWN"


# ═════════════════════════════════════════════════════════════════════════════
#  CUSTOM DOC TEMPLATE — draws border + header/footer on every page
# ═════════════════════════════════════════════════════════════════════════════

class NECTADocTemplate(SimpleDocTemplate):
    """Custom doc that draws Tanzania flag border + official header on every page."""

    def __init__(self, *args, exam=None, lang='en', school_disp='', **kwargs):
        self._exam = exam
        self._lang = lang
        self._school_disp = school_disp
        self._school_logo = _load_logo('school_logo.png')
        self._district_logo = _load_logo('district_logo.png')
        self._page_count = 0
        super().__init__(*args, **kwargs)

    def afterPage(self):
        """Called after each page is drawn."""
        self._page_count += 1

    def handle_pageBegin(self, *args, **kwargs):
        try:
            super().handle_pageBegin(*args, **kwargs)
        except Exception:
            pass
        canvas = self.canv
        W, H = A4

        # ── Tanzania flag-colour border ──────────────────────────────
        bw = 5
        gm = 12
        canvas.setFillColor(TZ_GREEN_CLR)
        canvas.rect(gm, H - gm - bw, W - 2 * gm, bw, fill=1, stroke=0)
        canvas.setFillColor(TZ_YELLOW_CLR)
        canvas.rect(W - gm - bw, gm, bw, H - 2 * gm, fill=1, stroke=0)
        canvas.setFillColor(TZ_BLACK_CLR)
        canvas.rect(gm, gm, W - 2 * gm, bw, fill=1, stroke=0)
        canvas.setFillColor(TZ_BLUE_CLR)
        canvas.rect(gm, gm, bw, H - 2 * gm, fill=1, stroke=0)

        # ── Green banner ─────────────────────────────────────────────
        LM = 2.0 * cm
        RM = 2.0 * cm
        banner_w = W - LM - RM
        banner_h = 3.2 * cm
        banner_y = H - gm - bw - 6

        canvas.setFillColor(TZ_GREEN_CLR)
        canvas.rect(LM, banner_y - banner_h, banner_w, banner_h, fill=1, stroke=0)

        # Logos
        if self._school_logo:
            canvas.drawImage(self._school_logo, LM + 4, banner_y - banner_h + 4,
                           width=1.8*cm, height=1.8*cm,
                           preserveAspectRatio=True, mask='auto')
        if self._district_logo:
            canvas.drawImage(self._district_logo, LM + banner_w - 2.2*cm, banner_y - banner_h + 4,
                           width=1.8*cm, height=1.8*cm,
                           preserveAspectRatio=True, mask='auto')

        # Text
        text_cx = LM + banner_w / 2
        canvas.setFillColor(TZ_WHITE_CLR)
        canvas.setFont("Helvetica-Bold", 11)
        country = "THE UNITED REPUBLIC OF TANZANIA" if self._lang == 'en' \
            else "JAMHURI YA MUUNGANO WA TANZANIA"
        canvas.drawCentredString(text_cx, banner_y - 14, country)

        canvas.setFont("Helvetica-Bold", 9)
        ministry = "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY" if self._lang == 'en' \
            else "WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA"
        canvas.drawCentredString(text_cx, banner_y - 26, ministry)

        canvas.setFont("Helvetica", 7)
        stype = "SECONDARY SCHOOL" if get_school_type_for_exam(self._exam) == 'secondary' else "PRIMARY SCHOOL"
        canvas.drawCentredString(text_cx, banner_y - 36, f"{stype} — EXAMINATION RESULTS")

        # Flag colour bar
        bar_y = banner_y - 42
        bar_h = 3
        for i, clr in enumerate([FLAG_GREEN, FLAG_YELLOW, FLAG_BLACK, FLAG_BLUE]):
            canvas.setFillColor(clr)
            canvas.rect(LM + i * banner_w / 4, bar_y, banner_w / 4, bar_h, fill=1, stroke=0)

        # School name (gold)
        canvas.setFillColor(TZ_YELLOW_CLR)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawCentredString(text_cx, banner_y - 56, self._school_disp)

        # Location
        canvas.setFillColor(TZ_WHITE_CLR)
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(text_cx, banner_y - 68, _get_location(self._exam))

        # Gold accent line
        canvas.setStrokeColor(TZ_GOLD_CLR)
        canvas.setLineWidth(2)
        canvas.line(LM, banner_y - banner_h - 1, LM + banner_w, banner_y - banner_h - 1)

        # ── Page footer ──────────────────────────────────────────────
        canvas.setStrokeColor(TZ_GREEN_CLR)
        canvas.setLineWidth(0.5)
        canvas.line(LM, 1.1 * cm, W - RM, 1.1 * cm)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(TZ_DARK_GREY_CLR)
        ts = datetime.now().strftime('%d/%m/%Y %H:%M')
        canvas.drawString(LM, 0.7 * cm, self._school_disp)
        canvas.drawCentredString(W / 2, 0.7 * cm, f"Page {self._page_count + 1}")
        canvas.drawRightString(W - RM, 0.7 * cm, f"Generated: {ts}")


# ═════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═════════════════════════════════════════════════════════════════════════════

def generate_results_pdf_response(exam):
    """Professional NECTA-style academic report PDF using flowable layout."""
    payload = get_exam_export_payload(exam)
    subjects = payload['subjects']
    all_results = payload['processed_results']
    score_lookup = payload['score_lookup']

    total_students = len(all_results)
    lang = get_report_language(exam)
    school_disp = get_full_school_name(exam)
    etype_disp = exam.get_exam_type_display().upper()
    report_label = get_report_label(exam)

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

    # ── Styles ────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title2', parent=styles['Heading1'],
        fontSize=14, textColor=TZ_GREEN_CLR, alignment=1,
        spaceAfter=4, spaceBefore=0, fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('Sub', parent=styles['Normal'],
        fontSize=9, textColor=TZ_DARK_GREY_CLR, alignment=1,
        spaceAfter=2, spaceBefore=0)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'],
        fontSize=10, textColor=TZ_GREEN_CLR, fontName='Helvetica-Bold',
        spaceBefore=10, spaceAfter=4)
    normal_style = ParagraphStyle('Norm', parent=styles['Normal'],
        fontSize=8, textColor=TZ_DARK_GREY_CLR, alignment=1)

    # ── Build story (flowables) ──────────────────────────────────────
    story = []

    # Spacer after header banner
    story.append(Spacer(1, 0.3 * cm))

    # Exam title
    if lang == 'en':
        story.append(Paragraph(f"{etype_disp} {exam.year} — FORM {exam.form}", title_style))
    else:
        story.append(Paragraph(report_label, title_style))
    story.append(Paragraph(exam.name, subtitle_style))
    story.append(Spacer(1, 0.4 * cm))

    # ── Section: Division Summary ─────────────────────────────────────
    story.append(Paragraph(get_section_title(exam, 'division_summary'), section_style))

    # Division table + Stats table side by side
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

    dt = Table(div_rows, colWidths=[4.5*cm, 2.5*cm, 2.5*cm])
    dt_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
        ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ('BOX', (0, 0), (-1, -1), 1.2, TZ_GREEN_CLR),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [TZ_WHITE_CLR, TZ_LIGHT_GREY_CLR]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]
    for i, d in enumerate(('I', 'II', 'III', 'IV', '0'), 1):
        bg, fg = DIV_PALETTE.get(d, ('FFFFFF', '000000'))
        dt_cmds.extend([
            ('BACKGROUND', (0, i), (0, i), colors.HexColor(bg)),
            ('TEXTCOLOR',  (0, i), (0, i), colors.HexColor(fg)),
            ('FONTNAME', (0, i), (0, i), 'Helvetica-Bold'),
        ])
    dt.setStyle(_make_style(*dt_cmds))

    # Stats table (right side)
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
    st_tbl = Table(stats_all, colWidths=[5*cm, 3*cm])
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

    # Side-by-side table
    wrapper = Table([[dt, '', st_tbl]], colWidths=[5*cm, 0.5*cm, 5*cm])
    wrapper.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(wrapper)
    story.append(Spacer(1, 0.5 * cm))

    # ── Section: Subject Statistics ───────────────────────────────────
    if subj_stats:
        story.append(Paragraph(get_section_title(exam, 'subject_stats'), section_style))

        if lang == 'sw':
            sh = ["SOMO", "WASTANI", "JUU", "CHINI", "KUFAULU"]
        else:
            sh = ["SUBJECT", "AVERAGE", "HIGH", "LOW", "PASS %"]
        sd = [sh]
        for ss in subj_stats:
            sd.append([ss['name'], str(ss['avg']), str(ss['max']),
                       str(ss['min']), f"{ss['pass_pct']}%"])

        st = Table(sd, colWidths=[4*cm, 2.2*cm, 2*cm, 2*cm, 2*cm])
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
        story.append(st)
        story.append(Spacer(1, 0.4 * cm))

    # ── Section: Top 5 Students ──────────────────────────────────────
    if all_results:
        story.append(Paragraph(get_section_title(exam, 'top_students'), section_style))

        top5 = all_results[:5]
        if lang == 'sw':
            th = ["NAFASI", "JINA", "JUMLA", "WASTANI", "POINTI", "DARAJA"]
        else:
            th = ["POS.", "NAME", "TOTAL", "AVG", "PTS", "DIV."]
        td = [th]
        for r in top5:
            st = r.student
            nm = ' '.join(p for p in [st.first_name, st.middle_name or '', st.last_name] if p)
            if len(nm) > 26:
                nm = nm[:24] + ".."
            counted = [s for s in (r.counted_subjects or '').split(',') if s.strip()]
            n_c = len(counted) if counted else len(subjects)
            gpa = r.points / n_c if n_c > 0 else 0
            td.append([str(r.position), nm, str(r.total_score),
                       f"{r.average_score:.1f}", str(r.points), r.division])

        tt = Table(td, colWidths=[1.2*cm, 5.5*cm, 1.8*cm, 1.8*cm, 1.5*cm, 1.8*cm])
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
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            # Gold badge for position 1
            ('BACKGROUND', (0, 1), (0, 1), TZ_GOLD_CLR),
            ('TEXTCOLOR',  (0, 1), (0, 1), TZ_WHITE_CLR),
            ('FONTNAME',   (0, 1), (0, 1), 'Helvetica-Bold'),
        ))
        story.append(tt)
        story.append(Spacer(1, 0.4 * cm))

    # ── Grading Key ───────────────────────────────────────────────────
    _, grade_ranges = _grade_thresholds(exam.form)
    gk_data = [[f"{g} ({rng})" for g, rng in grade_ranges]]
    gk_cols = [3.0 * cm] * len(grade_ranges)
    gt = Table(gk_data, colWidths=gk_cols)
    gt_cmds = [
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.8, TZ_GREEN_CLR),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
    ]
    for i, (g, _) in enumerate(grade_ranges):
        bg = _FILL_BY_LETTER.get(g, ("#C6F4D6", "#145A32"))[0]
        gt_cmds.append(('BACKGROUND', (i, 0), (i, 0), colors.HexColor(bg)))
    gt.setStyle(_make_style(*gt_cmds))
    story.append(gt)
    story.append(Spacer(1, 0.3 * cm))

    # Disclaimer
    disc = "This is an official results report generated from the School Results Management System." if lang == 'en' \
        else "Hii ni ripoti rashi ya matokeo iliyotolewa kutoka Mfumo wa Usimamizi wa Matokeo wa Shule."
    story.append(Paragraph(disc, normal_style))

    # ═══════════════════════════════════════════════════════════════════
    #  PAGE 2+ — FULL RESULTS (NECTA-style table)
    # ═══════════════════════════════════════════════════════════════════
    story.append(PageBreak())

    n_subj = max(len(subjects), 1)
    full_title = get_section_title(exam, 'full_results')

    # Calculate if we need landscape
    if n_subj >= 9:
        page_w, page_h = landscape(A4)
    else:
        page_w, page_h = A4

    # Column widths — adaptive
    fixed_w = 3.5*cm  # POS + NAME + SEX
    right_w = 4.5*cm  # TOTAL + AVG + PTS + GPA + DIV
    avail_subj = page_w - 4*cm - fixed_w - right_w  # margins
    col_subj = max(0.7*cm, min(avail_subj / n_subj, 1.4*cm))
    subj_total = col_subj * n_subj

    col_pos   = 0.8*cm
    col_name  = 3.0*cm if n_subj >= 10 else 3.5*cm
    col_sex   = 0.7*cm
    col_total = 0.9*cm
    col_avg   = 0.9*cm
    col_pts   = 0.8*cm
    col_gpa   = 0.9*cm
    col_div   = 1.0*cm

    col_widths = [col_pos, col_name, col_sex] + [col_subj]*n_subj + \
                 [col_total, col_avg, col_pts, col_gpa, col_div]

    lang_cols = ["#", "JINA", "S"] if lang == 'sw' else ["#", "NAME", "S"]
    headers = (lang_cols
               + [s.name.upper()[:9] for s in subjects]
               + (["JUMLA", "WAST.", "PTS", "GPA", "DARAJA"] if lang == 'sw'
                  else ["TOTAL", "AVG", "PTS", "GPA", "DIV."]))

    # Title
    if lang == 'en':
        story.append(Paragraph(f"{school_disp} — {etype_disp} {exam.year} — FORM {exam.form}", title_style))
    else:
        story.append(Paragraph(f"{school_disp} — {report_label}", title_style))
    story.append(Paragraph(f"{exam.name}  |  {full_title}", subtitle_style))
    story.append(Spacer(1, 0.3 * cm))

    # Build results table in chunks (page breaks)
    fontsize = 5.5 if n_subj >= 11 else 6.0 if n_subj >= 9 else 6.5 if n_subj >= 7 else 7.0
    rpp = 25 if n_subj <= 5 else 20 if n_subj <= 8 else 15
    page_groups = [all_results[i:i + rpp] for i in range(0, len(all_results), rpp)]

    for pn, group in enumerate(page_groups, 1):
        if pn > 1:
            story.append(PageBreak())
            # Re-add title on continuation pages
            if lang == 'en':
                story.append(Paragraph(f"{school_disp} — {etype_disp} {exam.year} — FORM {exam.form}", title_style))
            else:
                story.append(Paragraph(f"{school_disp} — {report_label}", title_style))
            story.append(Paragraph(f"{exam.name}  |  {full_title} — PAGE {pn} / {len(page_groups)}", subtitle_style))
            story.append(Spacer(1, 0.3 * cm))

        data = [headers]
        for r in group:
            stu = r.student
            nm = ' '.join(p for p in [stu.first_name, stu.middle_name or '', stu.last_name] if p)
            max_name = 16 if n_subj >= 10 else 20 if n_subj >= 8 else 24
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

        tbl = Table(data, colWidths=col_widths, repeatRows=1)

        style = [
            ('BACKGROUND', (0, 0), (-1, 0), TZ_GREEN_CLR),
            ('TEXTCOLOR', (0, 0), (-1, 0), TZ_WHITE_CLR),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), fontsize),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ('BOX', (0, 0), (-1, -1), 1.2, TZ_GREEN_CLR),
            ('TOPPADDING', (0, 0), (-1, -1), 1.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
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
        story.append(tbl)

        # Grade legend after table
        story.append(Spacer(1, 0.2 * cm))
        story.append(gt)  # Reuse grading key

    # ── Signature area ────────────────────────────────────────────────
    story.append(Spacer(1, 1.5 * cm))
    sig_data = [
        ["", "", ""],
        ["_" * 30, "", "_" * 30],
        ["Signature & Stamp", "", "Signature & Stamp"],
        ["Academic Officer", "", "Head of School"],
        ["", "", ""],
        ["Date: ________________________", "", ""],
    ]
    sig_tbl = Table(sig_data, colWidths=[6*cm, 2*cm, 6*cm])
    sig_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TEXTCOLOR', (0, 0), (-1, -1), TZ_DARK_GREY_CLR),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(sig_tbl)

    # ── Build PDF ─────────────────────────────────────────────────────
    buf = BytesIO()

    doc = NECTADocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2.0 * cm,
        leftMargin=2.0 * cm,
        topMargin=4.5 * cm,  # Space for header banner
        bottomMargin=1.5 * cm,
        exam=exam,
        lang=lang,
        school_disp=school_disp,
    )

    # Use a simple frame for content
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id='normal'
    )
    template = PageTemplate(id='necta', frames=[frame], onPage=doc.handle_pageBegin)
    doc.addPageTemplates([template])

    doc.build(story)
    buf.seek(0)

    resp = HttpResponse(buf, content_type='application/pdf')
    safe_name = exam.name.replace(' ', '_')
    resp['Content-Disposition'] = f'attachment; filename="{safe_name}_Academic_Report.pdf"'
    return resp


def _make_style(*cmds):
    return TableStyle(list(cmds))
