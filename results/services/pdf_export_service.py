"""
Professional NECTA Academic Results PDF — xhtml2pdf-based.
Generates HTML → renders to PDF via xhtml2pdf for clean, professional output.
No overlapping, no text cutting, proper word-wrap, CSS-styled tables.
"""
import io
import os
import base64
from collections import Counter
from datetime import datetime

from django.http import HttpResponse
from django.utils.safestring import mark_safe
from xhtml2pdf import pisa

from .export_data import get_exam_export_payload
from .report_helpers import (
    get_full_school_name, get_report_label, get_report_language,
    get_section_title, get_school_type_for_exam,
)

# ── Colour constants ──
NAVY   = "#1B3A5C"
GREEN  = "#1A7B3A"
GOLD   = "#C4961A"
CREAM  = "#FAF7F0"
SLATE  = "#5A6B7A"
LGRAY  = "#E8EBF0"

GRADE_CSS = {
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
DIV_CSS = {
    'I':   ("#D4EFDF", "#1A6B3A"),
    'II':  ("#D5F5E3", "#1E8449"),
    'III': ("#FEF9E7", "#B7950B"),
    'IV':  ("#FDEBD0", "#BA4A00"),
    '0':   ("#FADBD8", "#922B21"),
}


def _grading_thresholds(form):
    if form == 2:
        return [75, 65, 45, 30], [('A','75-100'),('B','65-74'),('C','45-64'),('D','30-44'),('F','0-29')]
    if form in (5, 6):
        return [80, 70, 60, 50, 40, 35], [('A','80-100'),('B','70-79'),('C','60-69'),('D','50-59'),('E','40-49'),('S','35-39'),('F','0-34')]
    return [75, 65, 55, 45, 35, 25], [('A','75-100'),('B+','65-74'),('B','55-64'),('C+','45-54'),('C','35-44'),('D','25-34'),('F','0-24')]


def _score_color(score, form=4):
    if score is None or not isinstance(score, (int, float)):
        return None, None
    th, gr = _grading_thresholds(form)
    for i, t in enumerate(th):
        if score >= t:
            return GRADE_CSS.get(gr[i][0], (None, None))
    return GRADE_CSS.get(gr[-1][0], (None, None))


def _load_logo_b64(field):
    """Load an ImageField as a base64 data URI, or return empty string."""
    if not field:
        return ''
    try:
        field.open('rb')
        data = field.read()
        ext = os.path.splitext(str(field.name))[1].lower()
        mime = {'png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.gif': 'image/gif', '.svg': 'image/svg+xml'}.get(ext, 'image/png')
        b64 = base64.b64encode(data).decode('ascii')
        return f'data:{mime};base64,{b64}'
    except Exception:
        return ''


def _location_str(exam):
    parts = []
    if exam.school and exam.school.district:
        parts.append(exam.school.district.upper())
    if exam.school and exam.school.region:
        parts.append(exam.school.region.upper())
    return ' &mdash; '.join(parts) if parts else 'TANZANIA'


def _student_name(r):
    return ' '.join(p for p in [r.student.first_name, r.student.middle_name or '', r.student.last_name] if p)


def _grade_legend(form):
    _, grades = _grading_thresholds(form)
    cells = []
    for g, rng in grades:
        bg, fg = GRADE_CSS.get(g, ("#fff", "#000"))
        cells.append(f'<td style="background:{bg};color:{fg};font-weight:bold;text-align:center;padding:3px 6px;font-size:7pt;border:0.5px solid #ccc;">{g} ({rng})</td>')
    return '<table style="width:100%;border-collapse:collapse;margin-top:4px;"><tr>' + ''.join(cells) + '</tr></table>'


def _css():
    """Return the CSS styles for the PDF."""
    return f"""
    @page {{
        size: A4 portrait;
        margin: 3.6cm 1.8cm 1.4cm 1.8cm;
        @top-left {{ content: ""; }}
        @top-center {{ content: ""; }}
        @top-right {{ content: ""; }}
        @bottom-left {{
            content: "{school_disp_}";
            font-family: Helvetica, sans-serif;
            font-size: 6pt;
            color: {SLATE};
        }}
        @bottom-center {{
            content: "Page " counter(page) " of " counter(pages);
            font-family: Helvetica, sans-serif;
            font-size: 6pt;
            color: {SLATE};
        }}
        @bottom-right {{
            content: "{date_str_}";
            font-family: Helvetica, sans-serif;
            font-size: 6pt;
            color: {SLATE};
        }}
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        font-family: Helvetica, Arial, sans-serif;
        font-size: 8pt;
        color: #333;
        line-height: 1.3;
    }}

    /* Header banner */
    .header-banner {{
        background: {GREEN};
        border-radius: 4px;
        padding: 8px 12px 6px 12px;
        margin-bottom: 0;
        position: relative;
        min-height: 72px;
    }}
    .header-logos {{
        position: absolute;
        top: 4px;
    }}
    .header-logos.left {{ left: 4px; }}
    .header-logos.right {{ right: 4px; }}
    .header-logos img {{
        width: 52px;
        height: 52px;
        border-radius: 50%;
        object-fit: contain;
    }}
    .header-text {{
        text-align: center;
        color: white;
    }}
    .header-text .republic {{
        font-size: 10pt;
        font-weight: bold;
        letter-spacing: 0.5px;
    }}
    .header-text .ministry {{
        font-size: 7.5pt;
        font-weight: bold;
        margin-top: 2px;
    }}
    .header-text .exam-type {{
        font-size: 6.5pt;
        margin-top: 2px;
    }}

    /* Flag strip */
    .flag-strip {{
        height: 3px;
        margin: 0;
    }}
    .flag-strip td {{
        height: 3px;
        padding: 0;
    }}

    /* School name */
    .school-name {{
        text-align: center;
        font-size: 13pt;
        font-weight: bold;
        color: {GOLD};
        margin-top: 6px;
        margin-bottom: 2px;
    }}
    .school-location {{
        text-align: center;
        font-size: 6.5pt;
        color: #666;
        margin-bottom: 6px;
    }}

    /* Gold line */
    .gold-line {{
        border: none;
        border-top: 1.5px solid {GOLD};
        margin: 0 0 8px 0;
    }}

    /* Section titles */
    .section-title {{
        font-size: 9.5pt;
        font-weight: bold;
        color: {GREEN};
        border-bottom: 1px solid {GREEN};
        padding-bottom: 2px;
        margin-top: 10px;
        margin-bottom: 4px;
    }}

    /* Page title */
    .page-title {{
        font-size: 11pt;
        font-weight: bold;
        color: {NAVY};
        text-align: center;
        margin-bottom: 1px;
    }}
    .page-subtitle {{
        font-size: 7pt;
        color: {SLATE};
        text-align: center;
        margin-bottom: 6px;
    }}

    /* Tables */
    table.data {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 6px;
        font-size: 7.5pt;
    }}
    table.data th {{
        background: {NAVY};
        color: white;
        font-weight: bold;
        padding: 4px 3px;
        text-align: center;
        border: 0.5px solid #ccc;
        font-size: 7pt;
        white-space: nowrap;
    }}
    table.data td {{
        padding: 3px 3px;
        text-align: center;
        border: 0.5px solid {LGRAY};
        vertical-align: middle;
    }}
    table.data tr:nth-child(even) td {{
        background: {CREAM};
    }}
    table.data td.name-col {{
        text-align: left;
        font-weight: normal;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 120px;
    }}

    /* Summary tables */
    table.summary {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 6px;
    }}
    table.summary th {{
        background: {NAVY};
        color: white;
        font-weight: bold;
        padding: 4px 6px;
        text-align: center;
        border: 0.5px solid #ccc;
        font-size: 7.5pt;
    }}
    table.summary td {{
        padding: 3px 6px;
        border: 0.5px solid {LGRAY};
        font-size: 7.5pt;
    }}

    /* Side by side wrapper */
    .two-col {{
        width: 100%;
        border-collapse: collapse;
    }}
    .two-col > tr > td {{
        vertical-align: top;
        padding: 0;
        border: none;
    }}
    .two-col > tr > td.spacer {{
        width: 12px;
    }}

    /* Signature area */
    .signature {{
        margin-top: 20px;
    }}
    .signature table {{
        width: 100%;
        border-collapse: collapse;
    }}
    .signature td {{
        font-size: 7pt;
        color: {SLATE};
        padding: 2px 0;
        vertical-align: top;
    }}
    .sig-line {{
        border-bottom: 1px solid #999;
        height: 30px;
        margin-bottom: 2px;
    }}

    /* Score cell colouring */
    .sc-a  {{ background: #D4EFDF; color: #1A6B3A; font-weight: bold; }}
    .sc-bp {{ background: #D5F5E3; color: #1E8449; }}
    .sc-b  {{ background: #D5F5E3; color: #2D7D46; }}
    .sc-cp {{ background: #FEF9E7; color: #B7950B; }}
    .sc-c  {{ background: #FEF9E7; color: #9A7D0A; }}
    .sc-d  {{ background: #FDEBD0; color: #BA4A00; }}
    .sc-e  {{ background: #F5CBA7; color: #AF601A; }}
    .sc-s  {{ background: #F9E79F; color: #B9770B; }}
    .sc-f  {{ background: #FADBD8; color: #922B21; font-weight: bold; }}

    /* Division colours */
    .div-1  {{ background: #D4EFDF; color: #1A6B3A; font-weight: bold; }}
    .div-2  {{ background: #D5F5E3; color: #1E8449; font-weight: bold; }}
    .div-3  {{ background: #FEF9E7; color: #B7950B; font-weight: bold; }}
    .div-4  {{ background: #FDEBD0; color: #BA4A00; font-weight: bold; }}
    .div-0  {{ background: #FADBD8; color: #922B21; font-weight: bold; }}

    .gold-bg {{ background: {GOLD} !important; color: white !important; font-weight: bold; }}
    .total-row td {{ font-weight: bold; background: #E8EBF0 !important; }}

    /* Top 1 badge */
    .top1 {{ background: {GOLD} !important; color: white !important; font-weight: bold; }}
    """


# These will be set per-request for CSS @page margin content
school_disp_ = ""
date_str_ = ""


def _score_class(score, form=4):
    if score is None or not isinstance(score, (int, float)):
        return ''
    th, gr = _grading_thresholds(form)
    for i, t in enumerate(th):
        if score >= t:
            g = gr[i][0]
            return {
                'A': 'sc-a', 'B+': 'sc-bp', 'B': 'sc-b', 'C+': 'sc-cp',
                'C': 'sc-c', 'D': 'sc-d', 'E': 'sc-e', 'S': 'sc-s', 'F': 'sc-f',
            }.get(g, '')
    return 'sc-f'


def _div_class(div):
    return {
        'I': 'div-1', 'II': 'div-2', 'III': 'div-3', 'IV': 'div-4', '0': 'div-0',
    }.get(div, '')


def _generate_html(exam):
    payload = get_exam_export_payload(exam)
    subjects = payload['subjects']
    results = payload['processed_results']
    score_lookup = payload['score_lookup']
    N = len(results)
    lang = get_report_language(exam)
    school_disp = get_full_school_name(exam)
    etype = exam.get_exam_type_display().upper()
    rlabel = get_report_label(exam)

    # Logos
    slogo_uri = _load_logo_b64(exam.school.school_logo) if exam.school else ''
    dlogo_uri = _load_logo_b64(exam.school.district_logo) if exam.school else ''

    # Stats
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

    # ── Header HTML ──
    s_logo_html = f'<div class="header-logos left"><img src="{slogo_uri}" /></div>' if slogo_uri else ''
    d_logo_html = f'<div class="header-logos right"><img src="{dlogo_uri}" /></div>' if dlogo_uri else ''

    republic = "THE UNITED REPUBLIC OF TANZANIA" if lang == 'en' else "JAMHURI YA MUUNGANO WA TANZANIA"
    ministry = "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY" if lang == 'en' else "WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA"
    stype = "SECONDARY SCHOOL" if get_school_type_for_exam(exam) == 'secondary' else "PRIMARY SCHOOL"

    header_html = f"""
    <div class="header-banner">
        {s_logo_html}
        {d_logo_html}
        <div class="header-text">
            <div class="republic">{republic}</div>
            <div class="ministry">{ministry}</div>
            <div class="exam-type">{stype} &mdash; EXAMINATION RESULTS</div>
        </div>
    </div>
    <table class="flag-strip" style="width:100%;"><tr>
        <td style="width:25%;background:{GREEN};"></td>
        <td style="width:25%;background:{GOLD};"></td>
        <td style="width:25%;background:#000;"></td>
        <td style="width:25%;background:#00A3DD;"></td>
    </tr></table>
    <div class="school-name">{school_disp}</div>
    <div class="school-location">{_location_str(exam)}</div>
    <hr class="gold-line" />
    """

    # ── Page 1: SUMMARY ──
    page_title = f"{etype} {exam.year} &mdash; FORM {exam.form}" if lang == 'en' else rlabel
    page_sub = exam.name

    # Division table
    div_labels = {
        'I': ('Division I', 'Daraja I'), 'II': ('Division II', 'Daraja II'),
        'III': ('Division III', 'Daraja III'), 'IV': ('Division IV', 'Daraja IV'),
        '0': ('Fail (0)', 'Faili (0)'),
    }
    d_hdr = ["DIVISION", "COUNT", "%"] if lang == 'en' else ["DARAJA", "IDADI", "%"]
    d_rows = ""
    for d in ('I', 'II', 'III', 'IV', '0'):
        label = div_labels[d][0] if lang == 'en' else div_labels[d][1]
        dc = div_counts.get(d, 0)
        bg, fg = DIV_CSS.get(d, ("#fff", "#000"))
        d_rows += f'<tr><td style="background:{bg};color:{fg};font-weight:bold;text-align:left;">{label}</td><td>{dc}</td><td>{pct(dc)}</td></tr>'
    d_rows += f'<tr class="total-row"><td style="text-align:left;font-weight:bold;">{"Total" if lang == "en" else "Jumla"}</td><td>{N}</td><td>100%</td></tr>'

    div_html = f"""
    <table class="summary" style="width:100%;">
        <tr><th colspan="3">{get_section_title(exam, 'division_summary')}</th></tr>
        <tr>{"".join(f'<th>{h}</th>' for h in d_hdr)}</tr>
        {d_rows}
    </table>
    """

    # Performance summary
    if lang == 'sw':
        perf_rows = [
            ("Wanafunzi", str(N)),
            ("Wastani Jumla", f"{avg_total:.1f}"),
            ("Wastani Mean", f"{avg_average:.1f}"),
            ("GPA (Pointi)", f"{avg_points:.2f}"),
            ("Masomo", str(counted)),
        ]
    else:
        perf_rows = [
            ("Total Students", str(N)),
            ("Overall Average", f"{avg_total:.1f}"),
            ("Mean of Averages", f"{avg_average:.1f}"),
            ("Average Points (GPA)", f"{avg_points:.2f}"),
            ("Subjects", str(counted)),
        ]
    perf_title = "TAARIFA YA MAENDELEO" if lang == 'sw' else "PERFORMANCE SUMMARY"
    perf_html = f"""
    <table class="summary" style="width:100%;">
        <tr><th colspan="2">{perf_title}</th></tr>
        {''.join(f'<tr><td style="text-align:left;font-weight:normal;">{k}</td><td style="text-align:center;font-weight:bold;">{v}</td></tr>' for k, v in perf_rows)}
    </table>
    """

    # Two-column layout
    two_col_html = f"""
    <table class="two-col"><tr>
        <td style="width:48%;">{div_html}</td>
        <td class="spacer"></td>
        <td style="width:48%;">{perf_html}</td>
    </tr></table>
    """

    # Subject statistics
    subj_html = ""
    if subj_stats:
        s_hdr = ["SUBJECT", "AVG", "HIGH", "LOW", "PASS%"] if lang == 'en' else ["SOMO", "WASTANI", "JUU", "CHINI", "KUFAULU"]
        s_rows = ''.join(f'<tr><td style="text-align:left;">{s["name"]}</td><td>{s["avg"]}</td><td>{s["high"]}</td><td>{s["low"]}</td><td>{s["pass_pct"]}%</td></tr>' for s in subj_stats)
        subj_html = f"""
        <div class="section-title">{get_section_title(exam, 'subject_stats')}</div>
        <table class="data" style="width:100%;">
            <tr>{"".join(f'<th>{h}</th>' for h in s_hdr)}</tr>
            {s_rows}
        </table>
        """

    # Top 5
    top5_html = ""
    if results:
        t_hdr = ["POS", "NAME", "TOTAL", "AVG", "PTS", "DIV"] if lang == 'en' else ["NAFASI", "JINA", "JUMLA", "WASTANI", "POINTI", "DARAJA"]
        t_rows = ""
        for idx, r in enumerate(results[:5]):
            nm = _student_name(r)
            if len(nm) > 22:
                nm = nm[:20] + '..'
            css_class = 'top1' if idx == 0 else ''
            t_rows += f'<tr><td class="{css_class}">{r.position}</td><td class="name-col {css_class}">{nm}</td><td class="{css_class}">{r.total_score}</td><td class="{css_class}">{r.average_score:.1f}</td><td class="{css_class}">{r.points}</td><td class="{css_class}">{r.division}</td></tr>'
        top5_html = f"""
        <div class="section-title">{get_section_title(exam, 'top_students')}</div>
        <table class="data" style="width:100%;">
            <tr>{"".join(f'<th>{h}</th>' for h in t_hdr)}</tr>
            {t_rows}
        </table>
        """

    summary_page = f"""
    {header_html}
    <div class="page-title">{page_title}</div>
    <div class="page-subtitle">{page_sub}</div>

    {two_col_html}
    {subj_html}
    {top5_html}

    <div class="section-title">{"GRADING KEY" if lang == "en" else "UFUNGUO WA DARAJA"}</div>
    {_grade_legend(exam.form)}
    """

    # ── Page 2+: FULL RESULTS ──
    n_subj = max(len(subjects), 1)

    # Subject header cells
    subj_th = ''.join(f'<th style="font-size:6pt;min-width:28px;max-width:42px;">{s.name.upper()[:8]}</th>' for s in subjects)

    # Results pages
    rows_per_page = 30 if n_subj <= 5 else 22 if n_subj <= 8 else 14
    chunks = [results[i:i + rows_per_page] for i in range(0, N, rows_per_page)]
    total_pages = len(chunks) or 1
    result_pages = []

    for pg_idx, chunk in enumerate(chunks, 1):
        rows_html = ""
        for r in chunk:
            nm = _student_name(r)
            max_nm = 10 if n_subj >= 10 else 14 if n_subj >= 8 else 18
            if len(nm) > max_nm:
                nm = nm[:max_nm - 2] + '..'

            # Score cells
            score_cells = ""
            for sub in subjects:
                sc = score_lookup.get((r.student_id, sub.id))
                cls = _score_class(sc, exam.form) if sc is not None else ''
                val = str(sc) if sc is not None else '-'
                score_cells += f'<td class="{cls}">{val}</td>'

            # Stats
            c = [s for s in (r.counted_subjects or '').split(',') if s.strip()]
            nc = len(c) if c else n_subj
            gpa = r.points / nc if nc else 0
            div_cls = _div_class(r.division)

            rows_html += f"""
            <tr>
                <td>{r.position}</td>
                <td class="name-col">{nm}</td>
                <td>{r.student.gender or 'M'}</td>
                {score_cells}
                <td style="font-weight:bold;">{r.total_score}</td>
                <td>{r.average_score:.1f}</td>
                <td>{r.points}</td>
                <td>{gpa:.2f}</td>
                <td class="{div_cls}">{r.division}</td>
            </tr>"""

        r_hdr = ["#", "NAME", "S"] + [s.name.upper()[:8] for s in subjects]
        if lang == 'sw':
            r_hdr += ["JUMLA", "AVG", "PTS", "GPA", "DARAJA"]
        else:
            r_hdr += ["TOTAL", "AVG", "PTS", "GPA", "DIV"]

        result_page_html = f"""
        <div class="page-title">{school_disp} &mdash; {etype} {exam.year} &mdash; FORM {exam.form}</div>
        <div class="page-subtitle">{exam.name} &nbsp;|&nbsp; PAGE {pg_idx}/{total_pages}</div>

        <table class="data" style="width:100%;font-size:{6 if n_subj >= 9 else 7}pt;">
            <tr>
                <th style="width:18px;">#</th>
                <th style="min-width:60px;text-align:left;">NAME</th>
                <th style="width:16px;">S</th>
                {subj_th}
                <th style="min-width:30px;">TOTAL</th>
                <th style="min-width:28px;">AVG</th>
                <th style="min-width:24px;">PTS</th>
                <th style="min-width:24px;">GPA</th>
                <th style="min-width:28px;">DIV</th>
            </tr>
            {rows_html}
        </table>

        {_grade_legend(exam.form)}

        <div class="signature">
            <table><tr>
                <td style="width:45%;text-align:left;">
                    <div class="sig-line"></div>
                    <strong>Signature &amp; Stamp</strong><br/>
                    Academic Officer
                </td>
                <td style="width:10%;"></td>
                <td style="width:45%;text-align:right;">
                    <div class="sig-line"></div>
                    <strong>Signature &amp; Stamp</strong><br/>
                    Head of School
                </td>
            </tr></table>
            <div style="margin-top:8px;font-size:6.5pt;color:{SLATE};">Date: _________________________________</div>
        </div>
        """
        result_pages.append(result_page_html)

    # ── Combine all pages ──
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>{_css()}</style>
</head>
<body>
    {summary_page}
    {''.join(f'<div style="page-break-before:always;">{rp}</div>' for rp in result_pages)}
</body>
</html>"""

    return full_html


def generate_results_pdf_response(exam):
    """Generate a professional NECTA-style PDF report for the given exam."""
    global school_disp_, date_str_

    school_disp_ = get_full_school_name(exam)
    date_str_ = datetime.now().strftime('%d/%m/%Y')

    html = _generate_html(exam)

    buf = io.BytesIO()
    pisa_status = pisa.CreatePDF(
        io.BytesIO(html.encode('utf-8')),
        dest=buf,
        encoding='utf-8',
    )

    if pisa_status.err:
        # Fallback: return a simple error PDF
        return HttpResponse(
            b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 9 0 R>>endobj\n'
            b'9 0 obj<</Type/Pages/Kids[10 0 R]/Count 1>>endobj\n'
            b'10 0 obj<</Type/Page/MediaBox[0 0 595 842]/Parent 9 0 R'
            b'/Contents 11 0 R/Resources<</Font<</F1 2 0 R>>>>>>endobj\n'
            b'2 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n'
            b'11 0 obj<</Length 55>>stream\nBT /F1 14 Tf 200 700 Td '
            b'(PDF Generation Error) Tj ET\nendstream\nendobj\n'
            b'xref\n0 12\n0000000000 65535 f\n0000000009 00000 n\n'
            b'0000000200 00000 n\n0000000058 00000 n\n'
            b'0000000268 00000 n\n0000000340 00000 n\n'
            b'trailer<</Size 12/Root 1 0 R>>\nstartxref\n410\n%%EOF',
            content_type='application/pdf'
        )

    buf.seek(0)
    resp = HttpResponse(buf, content_type='application/pdf')
    safe_name = exam.name.replace(" ", "_")
    resp['Content-Disposition'] = f'attachment; filename="{safe_name}_Results.pdf"'
    return resp
