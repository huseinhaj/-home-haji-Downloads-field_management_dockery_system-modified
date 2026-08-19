"""
pdf_export_service.py — Professional NECTA-style Academic Results PDF

Uses ReportLab Platypus (flowable-based layout) for automatic spacing.
Logos loaded from School model ImageFields.
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
    Table, TableStyle, Paragraph, Spacer, PageBreak, KeepTogether,
)

from .export_data import get_exam_export_payload
from .report_helpers import (
    TZ_BLUE, TZ_DARK_GREY, TZ_GOLD, TZ_GREEN, TZ_LIGHT_GREY, TZ_WHITE,
    get_full_school_name, get_report_label, get_report_language,
    get_section_title, get_school_type_for_exam,
)

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN  = colors.HexColor(f"#{TZ_GREEN}")
GOLD   = colors.HexColor(f"#{TZ_GOLD}")
BLUE   = colors.HexColor(f"#{TZ_BLUE}")
GREY   = colors.HexColor(f"#{TZ_LIGHT_GREY}")
WHITE  = colors.white
BLACK  = colors.black
LRED   = colors.HexColor("#FADBD8")
LGREEN = colors.HexColor("#C6F4D6")
LYELLOW = colors.HexColor("#FFF9C4")
LORANGE = colors.HexColor("#FDEBD0")
LBLUE  = colors.HexColor("#D5F5E3")

FILL = {
    'A':  ("#C6F4D6", "#145A32"), 'B+': ("#D5F5E3", "#1E8449"),
    'B':  ("#D5F5E3", "#1E8449"), 'C+': ("#FFF9C4", "#7D6608"),
    'C':  ("#FFF9C4", "#7D6608"), 'D':  ("#FDEBD0", "#784212"),
    'E':  ("#F0B27A", "#9C640C"), 'S':  ("#F9E79F", "#B9770B"),
    'F':  ("#FADBD8", "#922B21"),
}
DIV_C = {
    'I':  ("#C6F4D6", "#145A32"), 'II': ("#D5F5E3", "#1E8449"),
    'III':("#FFF9C4", "#7D6608"), 'IV': ("#FDEBD0", "#784212"),
    '0':  ("#FADBD8", "#922B21"),
}


def _grade_thresh(form):
    if form == 2:
        return [75, 65, 45, 30], [('A','75-100'),('B','65-74'),('C','45-64'),('D','30-44'),('F','0-29')]
    if form in (5, 6):
        return [80, 70, 60, 50, 40, 35], [('A','80-100'),('B','70-79'),('C','60-69'),('D','50-59'),('E','40-49'),('S','35-39'),('F','0-34')]
    return [75, 65, 55, 45, 35, 25], [('A','75-100'),('B+','65-74'),('B','55-64'),('C+','45-54'),('C','35-44'),('D','25-34'),('F','0-24')]


def _sfill(score, form=4):
    if score is None or not isinstance(score, (int, float)):
        return None, None
    th, gr = _grade_thresh(form)
    for i, t in enumerate(th):
        if score >= t:
            return FILL.get(gr[i][0], (None, None))
    return FILL.get(gr[-1][0], (None, None))


def _s(score, form=4):
    if score is None or not isinstance(score, (int, float)):
        return ''
    th, gr = _grade_thresh(form)
    for i, t in enumerate(th):
        if score >= t:
            return gr[i][0]
    return gr[-1][0]


def _load_logo_from_field(field):
    if not field:
        return None
    try:
        field.open('rb')
        return ImageReader(field)
    except Exception:
        return None


def _ts(*cmds):
    return TableStyle(list(cmds))


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE DRAWING (header + border + footer)
# ═════════════════════════════════════════════════════════════════════════════

def _draw_page(canvas, doc, *, exam, lang, school_disp, school_logo, district_logo, page_num, total_pages):
    """Draw border + header + footer on every page."""
    W, H = A4
    LM, RM = 2.0*cm, 2.0*cm

    # ── Border ──
    bw, gm = 5, 12
    for clr, x, y, w, h in [
        (GREEN, gm, H-gm-bw, W-2*gm, bw),          # top
        (GOLD, W-gm-bw, gm, bw, H-2*gm),            # right
        (BLACK, gm, gm, W-2*gm, bw),                # bottom
        (BLUE, gm, gm, bw, H-2*gm),                 # left
    ]:
        canvas.setFillColor(clr)
        canvas.rect(x, y, w, h, fill=1, stroke=0)

    # ── Green banner ──
    bw_hdr = W - LM - RM
    bh = 3.0*cm
    by = H - gm - 5
    canvas.setFillColor(GREEN)
    canvas.rect(LM, by - bh, bw_hdr, bh, fill=1, stroke=0)

    cx = LM + bw_hdr / 2

    # Logos
    if school_logo:
        canvas.drawImage(school_logo, LM+3, by - bh + 3, width=1.7*cm, height=bh-6,
                         preserveAspectRatio=True, mask='auto')
    if district_logo:
        canvas.drawImage(district_logo, LM + bw_hdr - 3 - 1.7*cm, by - bh + 3,
                         width=1.7*cm, height=bh-6, preserveAspectRatio=True, mask='auto')

    # Country
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 11)
    c = "THE UNITED REPUBLIC OF TANZANIA" if lang == 'en' else "JAMHURI YA MUUNGANO WA TANZANIA"
    canvas.drawCentredString(cx, by - 14, c)

    canvas.setFont("Helvetica-Bold", 9)
    m = "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY" if lang == 'en' else "WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA"
    canvas.drawCentredString(cx, by - 26, m)

    canvas.setFont("Helvetica", 7)
    st = "SECONDARY SCHOOL" if get_school_type_for_exam(exam) == 'secondary' else "PRIMARY SCHOOL"
    canvas.drawCentredString(cx, by - 36, f"{st} — EXAMINATION RESULTS")

    # Flag bar
    bary = by - 41
    for i, clr in enumerate([GREEN, GOLD, BLACK, BLUE]):
        canvas.setFillColor(clr)
        canvas.rect(LM + i*bw_hdr/4, bary, bw_hdr/4, 3, fill=1, stroke=0)

    # School name
    canvas.setFillColor(colors.HexColor("#FCD116"))
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawCentredString(cx, by - 57, school_disp)

    # Location
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica", 7)
    loc = ''
    if exam.school and exam.school.district:
        loc = exam.school.district.upper()
    if exam.school and exam.school.region:
        loc += f" — {exam.school.region.upper()}" if loc else exam.school.region.upper()
    canvas.drawCentredString(cx, by - 68, loc or 'TANZANIA')

    # Gold line
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(2)
    canvas.line(LM, by - bh - 1, LM + bw_hdr, by - bh - 1)

    # ── Footer ──
    canvas.setStrokeColor(GREEN)
    canvas.setLineWidth(0.5)
    canvas.line(LM, 1.0*cm, W - RM, 1.0*cm)
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(colors.HexColor(f"#{TZ_DARK_GREY}"))
    canvas.drawString(LM, 0.6*cm, school_disp)
    canvas.drawCentredString(W/2, 0.6*cm, f"Page {page_num} of {total_pages}")
    ts = datetime.now().strftime('%d/%m/%Y %H:%M')
    canvas.drawRightString(W-RM, 0.6*cm, ts)


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN API
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

    # Logos from School model
    sch_logo = dis_logo = None
    if exam.school:
        sch_logo = _load_logo_from_field(exam.school.school_logo)
        dis_logo = _load_logo_from_field(exam.school.district_logo)

    # ── Stats ──
    if N:
        avg_total = sum(r.total_score for r in results) / N
        avg_avg = sum(float(r.average_score) for r in results) / N
        avg_pts = sum(r.points for r in results) / N
        div_counts = Counter(r.division for r in results)
        counted = len([s for s in (results[0].counted_subjects or '').split(',') if s.strip()]) if results else len(subjects)
    else:
        avg_total = avg_avg = avg_pts = 0
        div_counts = Counter()
        counted = len(subjects)

    # Per-subject stats
    ss = []
    for subj in subjects:
        sc = [score_lookup[(r.student_id, subj.id)] for r in results if (r.student_id, subj.id) in score_lookup]
        if sc:
            ss.append({'name': subj.name, 'avg': round(sum(sc)/len(sc),1),
                       'hi': max(sc), 'lo': min(sc),
                       'pass': round(sum(1 for s in sc if s>=40)/len(sc)*100,1)})

    def pct(n):
        return f"{n/N*100:.1f}%" if N else "0%"

    # ── Styles ──
    s = getSampleStyleSheet()
    T = ParagraphStyle('T', parent=s['Heading1'], fontSize=13, textColor=GREEN,
                       alignment=1, spaceAfter=3, spaceBefore=0, fontName='Helvetica-Bold')
    ST = ParagraphStyle('ST', parent=s['Normal'], fontSize=8, textColor=colors.HexColor(f"#{TZ_DARK_GREY}"),
                        alignment=1, spaceAfter=1)
    SH = ParagraphStyle('SH', parent=s['Heading2'], fontSize=10, textColor=GREEN,
                        fontName='Helvetica-Bold', spaceBefore=8, spaceAfter=4)

    story = []

    # ═══ PAGE 1: SUMMARY ═══
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f"{etype} {exam.year} — FORM {exam.form}" if lang=='en' else rlabel, T))
    story.append(Paragraph(exam.name, ST))
    story.append(Spacer(1, 0.3*cm))

    # ── Division + Stats side by side ──
    story.append(Paragraph(get_section_title(exam, 'division_summary'), SH))

    dl = {'I':'Division I','II':'Division II','III':'Division III','IV':'Division IV','0':'Fail (0)'}
    if lang == 'sw':
        dl = {'I':'Daraja I','II':'Daraja II','III':'Daraja III','IV':'Daraja IV','0':'Fail (0)'}

    dhdr = ["DIVISION","COUNT","%"] if lang=='en' else ["DARAJA","IDADI","ASILIMIA"]
    drows = [dhdr]
    for d in ('I','II','III','IV','0'):
        drows.append([dl[d], str(div_counts.get(d,0)), pct(div_counts.get(d,0))])
    drows.append(["Total" if lang=='en' else "Jumla", str(N), "100%"])

    dt = Table(drows, colWidths=[3.5*cm, 2*cm, 2*cm])
    dt_cmds = [
        ('BACKGROUND',(0,0),(-1,0),GREEN),('TEXTCOLOR',(0,0),(-1,0),WHITE),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8.5),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('INNERGRID',(0,0),(-1,-1),0.4,colors.HexColor("#ccc")),
        ('BOX',(0,0),(-1,-1),1.2,GREEN),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,GREY]),
        ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
    ]
    for i,d in enumerate(('I','II','III','IV','0'),1):
        bg,fg = DIV_C.get(d,("fff","000"))
        dt_cmds += [('BACKGROUND',(0,i),(0,i),colors.HexColor(bg)),
                    ('TEXTCOLOR',(0,i),(0,i),colors.HexColor(fg)),
                    ('FONTNAME',(0,i),(0,i),'Helvetica-Bold')]
    dt.setStyle(_ts(*dt_cmds))

    # Stats
    if lang == 'sw':
        st_rows = [["TAARIFA (NECTA)",""],["Wanafunzi",str(N)],
                   ["Wastani Jumla",f"{avg_total:.1f}"],["Wastani Mean",f"{avg_avg:.1f}"],
                   ["GPA (Wastani Pointi)",f"{avg_pts:.2f}"],["Masomo",str(counted)]]
    else:
        st_rows = [["PERFORMANCE (NECTA)",""],["Total Students",str(N)],
                   ["Overall Average",f"{avg_total:.1f}"],["Mean of Averages",f"{avg_avg:.1f}"],
                   ["Average Points (GPA)",f"{avg_pts:.2f}"],["Subjects Counted",str(counted)]]

    st = Table(st_rows, colWidths=[4.5*cm, 2.5*cm])
    st.setStyle(_ts(
        ('BACKGROUND',(0,0),(-1,0),GREEN),('TEXTCOLOR',(0,0),(-1,0),WHITE),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8.5),
        ('FONTNAME',(0,1),(-1,-1),'Helvetica'),
        ('ALIGN',(0,0),(-1,0),'CENTER'),('ALIGN',(0,1),(0,-1),'LEFT'),('ALIGN',(1,1),(-1,-1),'CENTER'),
        ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
        ('INNERGRID',(0,0),(-1,-1),0.4,colors.HexColor("#ccc")),
        ('BOX',(0,0),(-1,-1),1.2,GREEN),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,GREY]),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),8),
    ))

    wrapper = Table([[dt, '', st]], colWidths=[4*cm, 0.5*cm, 5*cm])
    wrapper.setStyle(_ts([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
                           ('RIGHTPADDING',(0,0),(-1,-1),0)]))
    story.append(wrapper)
    story.append(Spacer(1, 0.4*cm))

    # ── Subject Stats ──
    if ss:
        story.append(Paragraph(get_section_title(exam, 'subject_stats'), SH))
        sh = ["SUBJECT","AVG","HIGH","LOW","PASS%"] if lang=='en' else ["SOMO","WASTANI","JUU","CHINI","KUFAULU"]
        sd = [sh] + [[s['name'],str(s['avg']),str(s['hi']),str(s['lo']),f"{s['pass']}%"] for s in ss]
        stbl = Table(sd, colWidths=[4*cm,2*cm,1.8*cm,1.8*cm,1.8*cm])
        stbl.setStyle(_ts(
            ('BACKGROUND',(0,0),(-1,0),GREEN),('TEXTCOLOR',(0,0),(-1,0),WHITE),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('ALIGN',(0,1),(0,-1),'LEFT'),
            ('INNERGRID',(0,0),(-1,-1),0.4,colors.HexColor("#ccc")),
            ('BOX',(0,0),(-1,-1),1.2,GREEN),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,GREY]),
            ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
        ))
        story.append(stbl)
        story.append(Spacer(1, 0.3*cm))

    # ── Top 5 ──
    if results:
        story.append(Paragraph(get_section_title(exam, 'top_students'), SH))
        th = ["POS","NAME","TOTAL","AVG","PTS","DIV"] if lang=='en' else ["NAFASI","JINA","JUMLA","WASTANI","POINTI","DARAJA"]
        td = [th]
        for r in results[:5]:
            nm = ' '.join(p for p in [r.student.first_name, r.student.middle_name or '', r.student.last_name] if p)
            if len(nm) > 24: nm = nm[:22]+'..'
            td.append([str(r.position), nm, str(r.total_score),
                       f"{r.average_score:.1f}", str(r.points), r.division])
        ttbl = Table(td, colWidths=[1*cm,5*cm,1.5*cm,1.5*cm,1.2*cm,1.2*cm])
        ttbl.setStyle(_ts(
            ('BACKGROUND',(0,0),(-1,0),GREEN),('TEXTCOLOR',(0,0),(-1,0),WHITE),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('ALIGN',(1,1),(1,-1),'LEFT'),
            ('INNERGRID',(0,0),(-1,-1),0.4,colors.HexColor("#ccc")),
            ('BOX',(0,0),(-1,-1),1.2,GREEN),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,GREY]),
            ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
            ('BACKGROUND',(0,1),(0,1),GOLD),('TEXTCOLOR',(0,1),(0,1),WHITE),
            ('FONTNAME',(0,1),(0,1),'Helvetica-Bold'),
        ))
        story.append(ttbl)
        story.append(Spacer(1, 0.3*cm))

    # ── Grading Key ──
    _, gr = _grade_thresh(exam.form)
    gk = [[f"{g} ({rng})" for g,rng in gr]]
    gk_cols = [3*cm]*len(gr)
    gtbl = Table(gk, colWidths=gk_cols)
    gk_cmds = [('FONTNAME',(0,0),(-1,-1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),
                ('ALIGN',(0,0),(-1,-1),'CENTER'),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
                ('BOX',(0,0),(-1,-1),0.8,GREEN),('INNERGRID',(0,0),(-1,-1),0.4,colors.HexColor("#ccc"))]
    for i,(g,_) in enumerate(gr):
        gk_cmds.append(('BACKGROUND',(i,0),(i,0),colors.HexColor(FILL.get(g,("#C6F4D6","#145A32"))[0])))
    gtbl.setStyle(_ts(*gk_cmds))
    story.append(gtbl)

    # ═══ PAGE 2+: FULL RESULTS ═══
    story.append(PageBreak())

    n_subj = max(len(subjects), 1)
    fsz = 5.8 if n_subj>=11 else 6.2 if n_subj>=9 else 6.8 if n_subj>=7 else 7.5
    rpp = 28 if n_subj<=5 else 22 if n_subj<=8 else 16
    chunks = [results[i:i+rpp] for i in range(0, N, rpp)]
    tot_p = len(chunks) or 1

    for pn, grp in enumerate(chunks, 1):
        if pn > 1:
            story.append(PageBreak())

        story.append(Paragraph(f"{school_disp} — {etype} {exam.year} — FORM {exam.form}" if lang=='en'
                               else f"{school_disp} — {rlabel}", T))
        story.append(Paragraph(f"{exam.name}  |  PAGE {pn}/{tot_p}", ST))
        story.append(Spacer(1, 0.2*cm))

        # Column widths
        nw = 3.0*cm if n_subj<=7 else 2.5*cm
        rw = 4*cm
        avail = A4[0] - 4*cm - nw - rw
        cs = max(0.7*cm, min(avail/n_subj, 1.4*cm))
        cw = [0.8*cm, nw, 0.6*cm] + [cs]*n_subj + [0.9*cm, 0.8*cm, 0.8*cm, 0.9*cm, 0.9*cm]

        hdrs = (["#","NAME","S"] if lang=='sw' else ["#","NAME","S"])
        hdrs += [s.name.upper()[:9] for s in subjects]
        hdrs += (["JUML","AVG","PTS","GPA","DIV"] if lang=='sw' else ["TOTAL","AVG","PTS","GPA","DIV"])

        data = [hdrs]
        for r in grp:
            nm = ' '.join(p for p in [r.student.first_name, r.student.middle_name or '', r.student.last_name] if p)
            mx = 16 if n_subj>=10 else 20 if n_subj>=8 else 24
            if len(nm)>mx: nm=nm[:mx-2]+'..'
            row = [str(r.position), nm, r.student.gender or 'M']
            for subj in subjects:
                sc = score_lookup.get((r.student_id, subj.id))
                row.append(str(sc) if sc is not None else '-')
            c = [s for s in (r.counted_subjects or '').split(',') if s.strip()]
            nc = len(c) if c else n_subj
            gpa = r.points/nc if nc else 0
            row += [str(r.total_score), f"{r.average_score:.1f}", str(r.points), f"{gpa:.2f}", r.division]
            data.append(row)

        tbl = Table(data, colWidths=cw, repeatRows=1)
        style = [
            ('BACKGROUND',(0,0),(-1,0),GREEN),('TEXTCOLOR',(0,0),(-1,0),WHITE),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),fsz),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('ALIGN',(1,1),(1,-1),'LEFT'),
            ('INNERGRID',(0,0),(-1,-1),0.25,colors.HexColor("#ccc")),
            ('BOX',(0,0),(-1,-1),1.2,GREEN),
            ('TOPPADDING',(0,0),(-1,-1),1.5),('BOTTOMPADDING',(0,0),(-1,-1),1.5),
            ('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ]
        for i in range(1, len(data)):
            if i%2==0:
                style.append(('BACKGROUND',(0,i),(-1,i),GREY))
        # Score colours
        for i,r in enumerate(grp,1):
            for si,sub in enumerate(subjects):
                sc = score_lookup.get((r.student_id, sub.id))
                if sc is not None:
                    bg,fg = _sfill(sc, exam.form)
                    if bg: style.append(('BACKGROUND',(3+si,i),(3+si,i),colors.HexColor(bg)))
                    if fg: style.append(('TEXTCOLOR',(3+si,i),(3+si,i),colors.HexColor(fg)))
            # Division colour
            dc = len(hdrs)-1
            if r.division in DIV_C:
                bg,fg = DIV_C[r.division]
                style += [('BACKGROUND',(dc,i),(dc,i),colors.HexColor(bg)),
                          ('TEXTCOLOR',(dc,i),(dc,i),colors.HexColor(fg)),
                          ('FONTNAME',(dc,i),(dc,i),'Helvetica-Bold')]

        tbl.setStyle(_ts(*style))
        story.append(tbl)

        # Grade key at bottom
        story.append(Spacer(1, 0.2*cm))
        story.append(gtbl)

    # ── Signature ──
    story.append(Spacer(1, 1.2*cm))
    sig = Table([
        ["_"*30, "", "_"*30],
        ["Signature & Stamp", "", "Signature & Stamp"],
        ["Academic Officer", "", "Head of School"],
        ["", "", ""],
        ["Date: ________________________", "", ""],
    ], colWidths=[6*cm, 2*cm, 6*cm])
    sig.setStyle(_ts([
        ('FONTNAME',(0,0),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),7),
        ('TEXTCOLOR',(0,0),(-1,-1),colors.HexColor(f"#{TZ_DARK_GREY}")),
        ('ALIGN',(0,0),(0,-1),'LEFT'),('ALIGN',(2,0),(2,-1),'RIGHT'),
        ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
    ]))
    story.append(sig)

    # ── Build ──
    buf = BytesIO()
    _page = [0]

    def on_page(canvas, doc):
        _page[0] += 1
        _draw_page(canvas, doc, exam=exam, lang=lang, school_disp=school_disp,
                   school_logo=sch_logo, district_logo=dis_logo,
                   page_num=_page[0], total_pages=tot_p+1)

    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2.0*cm, leftMargin=2.0*cm,
                            topMargin=4.2*cm, bottomMargin=1.5*cm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='main')
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=on_page)])
    doc.build(story)
    buf.seek(0)

    resp = HttpResponse(buf, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{exam.name.replace(" ","_")}_Results.pdf"'
    return resp
