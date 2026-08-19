"""
Professional NECTA Academic Results PDF — Complete rewrite.
Clean layout, proper spacing, beautiful colors, no overlapping.
"""
from collections import Counter
from datetime import datetime
from io import BytesIO

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Frame, PageTemplate,
    Table, TableStyle, Paragraph, Spacer, PageBreak,
)

from .export_data import get_exam_export_payload
from .report_helpers import (
    TZ_BLUE, TZ_DARK_GREY, TZ_GOLD, TZ_GREEN, TZ_LIGHT_GREY,
    get_full_school_name, get_report_label, get_report_language,
    get_section_title, get_school_type_for_exam,
)

# ── Professional colour palette ─────────────────────────────────────────────
NAVY   = colors.HexColor("#1B3A5C")
GREEN  = colors.HexColor("#1A7B3A")
GOLD   = colors.HexColor("#C4961A")
CREAM  = colors.HexColor("#FAF7F0")
SLATE  = colors.HexColor("#5A6B7A")
WHITE  = colors.white
BLACK  = colors.black
LGRAY  = colors.HexColor("#E8EBF0")

GRADE_COLORS = {
    'A':  ("#D4EFDF", "#1A6B3A"),
    'B+': ("#D5F5E3", "#1E8449"),
    'B':  ("#D5F5E3", "#2D7D46"),
    'C+': ("#FEF9E7", "#B7950B"),
    'C':  ("#FEF9E7", "#9A7D0A"),
    'D':  ("#FDEBD0", "#BA4A00"),
    'E':  ("#F5CBA7", "#AF601A"),
    'S':  ("#F9E79F", "#B9770B"),
    'F':  ("#FADBD8", "#922B21"),
}
DIV_COLORS = {
    'I':   ("#D4EFDF", "#1A6B3A"),
    'II':  ("#D5F5E3", "#1E8449"),
    'III': ("#FEF9E7", "#B7950B"),
    'IV':  ("#FDEBD0", "#BA4A00"),
    '0':   ("#FADBD8", "#922B21"),
}


def _grading_thresholds(form):
    """Return (thresholds, grade_names) for the given form level."""
    if form == 2:
        return [75, 65, 45, 30], [('A','75-100'),('B','65-74'),('C','45-64'),('D','30-44'),('F','0-29')]
    if form in (5, 6):
        return [80, 70, 60, 50, 40, 35], [('A','80-100'),('B','70-79'),('C','60-69'),('D','50-59'),('E','40-49'),('S','35-39'),('F','0-34')]
    return [75, 65, 55, 45, 35, 25], [('A','75-100'),('B+','65-74'),('B','55-64'),('C+','45-54'),('C','35-44'),('D','25-34'),('F','0-24')]


def _score_fill(score, form=4):
    """Return (bg_hex, fg_hex) for a numeric score."""
    if score is None or not isinstance(score, (int, float)):
        return None, None
    thresholds, grades = _grading_thresholds(form)
    for i, t in enumerate(thresholds):
        if score >= t:
            return GRADE_COLORS.get(grades[i][0], (None, None))
    return GRADE_COLORS.get(grades[-1][0], (None, None))


def _load_image(field):
    """Load an ImageField into an ImageReader, or return None."""
    if not field:
        return None
    try:
        field.open('rb')
        return ImageReader(field)
    except Exception:
        return None


def _location_str(exam):
    parts = []
    if exam.school and exam.school.district:
        parts.append(exam.school.district.upper())
    if exam.school and exam.school.region:
        parts.append(exam.school.region.upper())
    return ' — '.join(parts) if parts else 'TANZANIA'


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE DECORATION (header + footer drawn on every page)
# ═════════════════════════════════════════════════════════════════════════════

def _decorate_page(cv, doc, *, exam, lang, school_disp, slogo, dlogo, page_num, total_pages):
    """Draw border + header banner + footer on each page."""
    W, H = A4
    LM, RM = 2.0 * cm, 2.0 * cm
    BW = W - LM - RM

    # ── Outer border ──
    cv.setStrokeColor(NAVY)
    cv.setLineWidth(1.5)
    cv.rect(12, 12, W - 24, H - 24, fill=0, stroke=1)

    # ── Header green banner ──
    banner_h = 2.4 * cm
    banner_top = H - 18

    cv.setFillColor(GREEN)
    cv.roundRect(LM, banner_top - banner_h, BW, banner_h, 4, fill=1, stroke=0)

    cx = LM + BW / 2

    # Logos (school left, district right)
    logo_h = banner_h - 6
    if slogo:
        cv.drawImage(slogo, LM + 3, banner_top - banner_h + 3,
                     width=logo_h, height=logo_h,
                     preserveAspectRatio=True, mask='auto')
    if dlogo:
        cv.drawImage(dlogo, LM + BW - 3 - logo_h, banner_top - banner_h + 3,
                     width=logo_h, height=logo_h,
                     preserveAspectRatio=True, mask='auto')

    # Header text
    cv.setFillColor(WHITE)
    cv.setFont("Helvetica-Bold", 10)
    title_text = "THE UNITED REPUBLIC OF TANZANIA" if lang == 'en' else "JAMHURI YA MUUNGANO WA TANZANIA"
    cv.drawCentredString(cx, banner_top - 12, title_text)

    cv.setFont("Helvetica-Bold", 8)
    ministry = "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY" if lang == 'en' else "WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA"
    cv.drawCentredString(cx, banner_top - 22, ministry)

    cv.setFont("Helvetica", 6.5)
    school_type = "SECONDARY SCHOOL" if get_school_type_for_exam(exam) == 'secondary' else "PRIMARY SCHOOL"
    cv.drawCentredString(cx, banner_top - 31, f"{school_type} — EXAMINATION RESULTS")

    # Tanzania flag colour strip
    strip_y = banner_top - 36
    strip_h = 3
    for i, clr in enumerate([GREEN, GOLD, BLACK, colors.HexColor("#00A3DD")]):
        cv.setFillColor(clr)
        cv.rect(LM + i * BW / 4, strip_y, BW / 4, strip_h, fill=1, stroke=0)

    # School name (gold)
    cv.setFillColor(GOLD)
    cv.setFont("Helvetica-Bold", 12)
    cv.drawCentredString(cx, banner_top - 50, school_disp)

    # Location
    cv.setFillColor(colors.HexColor("#E8F5E9"))
    cv.setFont("Helvetica", 6.5)
    cv.drawCentredString(cx, banner_top - 60, _location_str(exam))

    # Gold accent line below banner
    cv.setStrokeColor(GOLD)
    cv.setLineWidth(1.5)
    cv.line(LM, banner_top - banner_h - 1, LM + BW, banner_top - banner_h - 1)

    # ── Footer ──
    footer_y = 14
    cv.setStrokeColor(NAVY)
    cv.setLineWidth(0.5)
    cv.line(LM, footer_y + 10, W - RM, footer_y + 10)

    cv.setFont("Helvetica", 5.5)
    cv.setFillColor(SLATE)
    cv.drawString(LM, footer_y, school_disp[:40])
    cv.drawCentredString(W / 2, footer_y, f"Page {page_num} of {total_pages}")
    cv.drawRightString(W - RM, footer_y, datetime.now().strftime('%d/%m/%Y'))


# ═════════════════════════════════════════════════════════════════════════════
#  HELPER: build a clean TableStyle from a list of command tuples
# ═════════════════════════════════════════════════════════════════════════════

def _make_style(commands):
    """Safely build a TableStyle from a list of command tuples."""
    return TableStyle(commands)


# ═════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═════════════════════════════════════════════════════════════════════════════

def generate_results_pdf_response(exam):
    payload = get_exam_export_payload(exam)
    subjects = payload['subjects']
    results = payload['processed_results']
    score_lookup = payload['score_lookup']
    N = len(results)
    lang = get_report_language(exam)
    school_disp = get_full_school_name(exam)
    etype = exam.get_exam_type_display().upper()
    rlabel = get_report_label(exam)

    # ── Logos ──
    slogo = dlogo = None
    if exam.school:
        slogo = _load_image(exam.school.school_logo)
        dlogo = _load_image(exam.school.district_logo)

    # ── Aggregate stats ──
    if N:
        avg_total = sum(r.total_score for r in results) / N
        avg_average = sum(float(r.average_score) for r in results) / N
        avg_points = sum(r.points for r in results) / N
        div_counts = Counter(r.division for r in results)
        counted = len([s for s in (results[0].counted_subjects or '').split(',') if s.strip()]) if results else len(subjects)
    else:
        avg_total = avg_average = avg_points = 0
        div_counts = Counter()
        counted = len(subjects)

    def pct(n):
        return f"{n / N * 100:.1f}%" if N else "0%"

    # ── Per-subject stats ──
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

    # ── Paragraph styles ──
    ss = getSampleStyleSheet()
    TITLE_ST = ParagraphStyle('PTitle', parent=ss['Heading1'], fontSize=12, textColor=NAVY,
                              alignment=1, spaceAfter=2, spaceBefore=0, fontName='Helvetica-Bold')
    SUB_ST = ParagraphStyle('PSub', parent=ss['Normal'], fontSize=7.5, textColor=SLATE,
                            alignment=1, spaceAfter=1)
    SEC_ST = ParagraphStyle('PSec', parent=ss['Heading2'], fontSize=9, textColor=GREEN,
                            fontName='Helvetica-Bold', spaceBefore=6, spaceAfter=3)

    story = []

    # ═════════════════════════════════════════════════════════════════════════
    #  PAGE 1: SUMMARY
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(
        f"{etype} {exam.year} — FORM {exam.form}" if lang == 'en' else rlabel, TITLE_ST))
    story.append(Paragraph(exam.name, SUB_ST))
    story.append(Spacer(1, 0.25 * cm))

    # ── Division breakdown table ──
    story.append(Paragraph(get_section_title(exam, 'division_summary'), SEC_ST))

    div_labels = {
        'I': 'Division I', 'II': 'Division II', 'III': 'Division III',
        'IV': 'Division IV', '0': 'Fail (0)',
    }
    if lang == 'sw':
        div_labels = {
            'I': 'Daraja I', 'II': 'Daraja II', 'III': 'Daraja III',
            'IV': 'Daraja IV', '0': 'Faili (0)',
        }

    d_hdr = ["DIVISION", "COUNT", "%"] if lang == 'en' else ["DARAJA", "IDADI", "%"]
    d_data = [d_hdr]
    for d in ('I', 'II', 'III', 'IV', '0'):
        d_data.append([div_labels[d], str(div_counts.get(d, 0)), pct(div_counts.get(d, 0))])
    d_data.append(["Total" if lang == 'en' else "Jumla", str(N), "100%"])

    dt = Table(d_data, colWidths=[3.2 * cm, 1.8 * cm, 1.8 * cm])
    dt_style = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, LGRAY),
        ('BOX', (0, 0), (-1, -1), 1, NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, CREAM]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]
    for idx, d in enumerate(('I', 'II', 'III', 'IV', '0'), 1):
        bg, fg = DIV_COLORS.get(d, ("ffffff", "000000"))
        dt_style.append(('BACKGROUND', (0, idx), (0, idx), colors.HexColor(bg)))
        dt_style.append(('TEXTCOLOR', (0, idx), (0, idx), colors.HexColor(fg)))
        dt_style.append(('FONTNAME', (0, idx), (0, idx), 'Helvetica-Bold'))
    dt.setStyle(_make_style(dt_style))

    # ── Performance summary table ──
    if lang == 'sw':
        perf_data = [
            ["TAARIFA YA MAENDELEO", ""],
            ["Wanafunzi", str(N)],
            ["Wastani Jumla", f"{avg_total:.1f}"],
            ["Wastani Mean", f"{avg_average:.1f}"],
            ["GPA", f"{avg_points:.2f}"],
            ["Masomo", str(counted)],
        ]
    else:
        perf_data = [
            ["PERFORMANCE SUMMARY", ""],
            ["Total Students", str(N)],
            ["Overall Average", f"{avg_total:.1f}"],
            ["Mean of Averages", f"{avg_average:.1f}"],
            ["Average Points (GPA)", f"{avg_points:.2f}"],
            ["Subjects", str(counted)],
        ]

    pt = Table(perf_data, colWidths=[4.5 * cm, 2.5 * cm])
    pt.setStyle(_make_style([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, LGRAY),
        ('BOX', (0, 0), (-1, -1), 1, NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, CREAM]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))

    # Side by side: division table + perf summary
    wrapper = Table([[dt, '', pt]], colWidths=[4 * cm, 0.5 * cm, 5 * cm])
    wrapper.setStyle(_make_style([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(wrapper)
    story.append(Spacer(1, 0.35 * cm))

    # ── Subject Statistics ──
    if subj_stats:
        story.append(Paragraph(get_section_title(exam, 'subject_stats'), SEC_ST))
        s_hdr = ["SUBJECT", "AVG", "HIGH", "LOW", "PASS%"] if lang == 'en' else ["SOMO", "WASTANI", "JUU", "CHINI", "KUFAULU"]
        s_data = [s_hdr]
        for s in subj_stats:
            s_data.append([s['name'], str(s['avg']), str(s['high']), str(s['low']), f"{s['pass_pct']}%"])

        st = Table(s_data, colWidths=[4 * cm, 1.8 * cm, 1.5 * cm, 1.5 * cm, 1.7 * cm])
        st.setStyle(_make_style([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('INNERGRID', (0, 0), (-1, -1), 0.4, LGRAY),
            ('BOX', (0, 0), (-1, -1), 1, NAVY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, CREAM]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(st)
        story.append(Spacer(1, 0.3 * cm))

    # ── Top 5 Students ──
    if results:
        story.append(Paragraph(get_section_title(exam, 'top_students'), SEC_ST))
        t_hdr = ["POS", "NAME", "TOTAL", "AVG", "PTS", "DIV"] if lang == 'en' else ["NAFASI", "JINA", "JUMLA", "WASTANI", "POINTI", "DARAJA"]
        t_data = [t_hdr]
        for r in results[:5]:
            nm = ' '.join(p for p in [r.student.first_name, r.student.middle_name or '', r.student.last_name] if p)
            if len(nm) > 24:
                nm = nm[:22] + '..'
            t_data.append([str(r.position), nm, str(r.total_score),
                           f"{r.average_score:.1f}", str(r.points), r.division])

        top_t = Table(t_data, colWidths=[1 * cm, 5 * cm, 1.5 * cm, 1.5 * cm, 1.2 * cm, 1.2 * cm])
        top_t.setStyle(_make_style([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('INNERGRID', (0, 0), (-1, -1), 0.4, LGRAY),
            ('BOX', (0, 0), (-1, -1), 1, NAVY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, CREAM]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            # Highlight #1
            ('BACKGROUND', (0, 1), (0, 1), GOLD),
            ('TEXTCOLOR', (0, 1), (0, 1), WHITE),
            ('FONTNAME', (0, 1), (0, 1), 'Helvetica-Bold'),
        ]))
        story.append(top_t)
        story.append(Spacer(1, 0.2 * cm))

    # ── Grading Key ──
    _, grades = _grading_thresholds(exam.form)
    gk_data = [[f"{g} ({rng})" for g, rng in grades]]
    gk_t = Table(gk_data, colWidths=[max(2.2 * cm, 11 * cm / len(grades))] * len(grades))
    gk_cmds = [
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.8, NAVY),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, LGRAY),
    ]
    for i, (g, _) in enumerate(grades):
        bg, fg = GRADE_COLORS.get(g, ("ffffff", "000000"))
        gk_cmds.append(('BACKGROUND', (i, 0), (i, 0), colors.HexColor(bg)))
        gk_cmds.append(('TEXTCOLOR', (i, 0), (i, 0), colors.HexColor(fg)))
    gk_t.setStyle(_make_style(gk_cmds))
    story.append(gk_t)

    # ═════════════════════════════════════════════════════════════════════════
    #  PAGE 2+: FULL RESULTS TABLE
    # ═════════════════════════════════════════════════════════════════════════
    story.append(PageBreak())

    n_subj = max(len(subjects), 1)
    font_sz = 5.8 if n_subj >= 11 else 6.2 if n_subj >= 9 else 6.8 if n_subj >= 7 else 7.5
    rows_per_page = 30 if n_subj <= 5 else 24 if n_subj <= 8 else 16
    chunks = [results[i:i + rows_per_page] for i in range(0, N, rows_per_page)]
    total_result_pages = len(chunks) or 1

    for page_idx, chunk in enumerate(chunks, 1):
        if page_idx > 1:
            story.append(PageBreak())

        story.append(Paragraph(
            f"{school_disp} — {etype} {exam.year} — FORM {exam.form}" if lang == 'en'
            else f"{school_disp} — {rlabel}", TITLE_ST))
        story.append(Paragraph(f"{exam.name}  |  PAGE {page_idx}/{total_result_pages}", SUB_ST))
        story.append(Spacer(1, 0.15 * cm))

        # Column widths — adapt to number of subjects
        name_w = 2.5 * cm if n_subj <= 7 else 2.0 * cm
        avail = A4[0] - 4 * cm - name_w - 3.5 * cm  # usable width for subject columns
        subj_col_w = max(0.65 * cm, min(avail / n_subj, 1.2 * cm))
        col_widths = (
            [0.6 * cm, name_w, 0.45 * cm]                # #, NAME, S
            + [subj_col_w] * n_subj                        # subject scores
            + [0.75 * cm, 0.65 * cm, 0.65 * cm, 0.7 * cm, 0.75 * cm]  # TOTAL, AVG, PTS, GPA, DIV
        )

        # Headers
        result_hdrs = ["#", "NAME", "S"]
        result_hdrs += [s.name.upper()[:8] for s in subjects]
        if lang == 'sw':
            result_hdrs += ["JUMLA", "AVG", "PTS", "GPA", "DARAJA"]
        else:
            result_hdrs += ["TOTAL", "AVG", "PTS", "GPA", "DIV"]

        # Data rows
        table_data = [result_hdrs]
        for r in chunk:
            nm = ' '.join(p for p in [r.student.first_name, r.student.middle_name or '', r.student.last_name] if p)
            max_nm = 12 if n_subj >= 10 else 16 if n_subj >= 8 else 20
            if len(nm) > max_nm:
                nm = nm[:max_nm - 2] + '..'

            row = [str(r.position), nm, r.student.gender or 'M']
            for sub in subjects:
                sc = score_lookup.get((r.student_id, sub.id))
                row.append(str(sc) if sc is not None else '-')

            c = [s for s in (r.counted_subjects or '').split(',') if s.strip()]
            nc = len(c) if c else n_subj
            gpa = r.points / nc if nc else 0
            row += [str(r.total_score), f"{r.average_score:.1f}", str(r.points),
                    f"{gpa:.2f}", r.division]
            table_data.append(row)

        # Build table
        result_table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # Table style
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), font_sz),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, LGRAY),
            ('BOX', (0, 0), (-1, -1), 1, NAVY),
            ('TOPPADDING', (0, 0), (-1, -1), 1.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        # Alternating row backgrounds
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                style_cmds.append(('BACKGROUND', (0, i), (-1, i), CREAM))

        # Per-cell score colouring + division colour
        for row_idx, r in enumerate(chunk, 1):
            # Score colours
            for col_idx, sub in enumerate(subjects):
                sc = score_lookup.get((r.student_id, sub.id))
                if sc is not None:
                    bg, fg = _score_fill(sc, exam.form)
                    if bg:
                        style_cmds.append(('BACKGROUND', (3 + col_idx, row_idx), (3 + col_idx, row_idx), colors.HexColor(bg)))
                    if fg:
                        style_cmds.append(('TEXTCOLOR', (3 + col_idx, row_idx), (3 + col_idx, row_idx), colors.HexColor(fg)))

            # Division cell colour
            div_col = len(result_hdrs) - 1
            if r.division in DIV_COLORS:
                bg, fg = DIV_COLORS[r.division]
                style_cmds.append(('BACKGROUND', (div_col, row_idx), (div_col, row_idx), colors.HexColor(bg)))
                style_cmds.append(('TEXTCOLOR', (div_col, row_idx), (div_col, row_idx), colors.HexColor(fg)))
                style_cmds.append(('FONTNAME', (div_col, row_idx), (div_col, row_idx), 'Helvetica-Bold'))

        result_table.setStyle(_make_style(style_cmds))
        story.append(result_table)

        # Grade key below table
        story.append(Spacer(1, 0.1 * cm))
        story.append(gk_t)

    # ── Signature area ──
    story.append(Spacer(1, 0.8 * cm))
    sig_data = [
        ["_" * 28, "", "_" * 28],
        ["Signature & Stamp", "", "Signature & Stamp"],
        ["Academic Officer", "", "Head of School"],
        ["", "", ""],
        ["Date: ________________________", "", ""],
    ]
    sig_t = Table(sig_data, colWidths=[6 * cm, 2 * cm, 6 * cm])
    sig_t.setStyle(_make_style([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TEXTCOLOR', (0, 0), (-1, -1), SLATE),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(sig_t)

    # ═══ BUILD PDF ═══
    buf = BytesIO()
    page_counter = [0]

    def on_page(cv, doc):
        page_counter[0] += 1
        _decorate_page(cv, doc,
                       exam=exam, lang=lang, school_disp=school_disp,
                       slogo=slogo, dlogo=dlogo,
                       page_num=page_counter[0],
                       total_pages=total_result_pages + 1)

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=2.0 * cm, leftMargin=2.0 * cm,
        topMargin=3.8 * cm, bottomMargin=1.4 * cm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='main')
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=on_page)])
    doc.build(story)
    buf.seek(0)

    resp = HttpResponse(buf, content_type='application/pdf')
    safe_name = exam.name.replace(" ", "_")
    resp['Content-Disposition'] = f'attachment; filename="{safe_name}_Results.pdf"'
    return resp
