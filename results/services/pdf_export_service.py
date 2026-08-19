"""
Professional NECTA-style Academic Results PDF
Footer at bottom, header at top, clean spacing throughout.
"""
from collections import Counter
from datetime import datetime
from io import BytesIO

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
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

# ── Colours ──────────────────────────────────────────────────────────────────
GRN  = colors.HexColor(f"#{TZ_GREEN}")
GLD  = colors.HexColor(f"#{TZ_GOLD}")
BLU  = colors.HexColor(f"#{TZ_BLUE}")
GRY  = colors.HexColor(f"#{TZ_LIGHT_GREY}")
DRK  = colors.HexColor(f"#{TZ_DARK_GREY}")
WHT  = colors.white
BLK  = colors.black

FILL = {
    'A':  ("#C6F4D6","#145A32"), 'B+': ("#D5F5E3","#1E8449"),
    'B':  ("#D5F5E3","#1E8449"), 'C+': ("#FFF9C4","#7D6608"),
    'C':  ("#FFF9C4","#7D6608"), 'D':  ("#FDEBD0","#784212"),
    'E':  ("#F0B27A","#9C640C"), 'S':  ("#F9E79F","#B9770B"),
    'F':  ("#FADBD8","#922B21"),
}
DIV_C = {
    'I':  ("#C6F4D6","#145A32"), 'II': ("#D5F5E3","#1E8449"),
    'III':("#FFF9C4","#7D6608"), 'IV': ("#FDEBD0","#784212"),
    '0':  ("#FADBD8","#922B21"),
}

def _gt(form):
    if form == 2:
        return [75,65,45,30],[('A','75-100'),('B','65-74'),('C','45-64'),('D','30-44'),('F','0-29')]
    if form in (5,6):
        return [80,70,60,50,40,35],[('A','80-100'),('B','70-79'),('C','60-69'),('D','50-59'),('E','40-49'),('S','35-39'),('F','0-34')]
    return [75,65,55,45,35,25],[('A','75-100'),('B+','65-74'),('B','55-64'),('C+','45-54'),('C','35-44'),('D','25-34'),('F','0-24')]

def _sf(sc, form=4):
    if sc is None or not isinstance(sc,(int,float)): return None,None
    th,gr = _gt(form)
    for i,t in enumerate(th):
        if sc>=t: return FILL.get(gr[i][0],(None,None))
    return FILL.get(gr[-1][0],(None,None))

def _gr(sc, form=4):
    if sc is None or not isinstance(sc,(int,float)): return ''
    th,gr = _gt(form)
    for i,t in enumerate(th):
        if sc>=t: return gr[i][0]
    return gr[-1][0]

def _lf(field):
    if not field: return None
    try:
        field.open('rb')
        return ImageReader(field)
    except: return None

def _ts(*c): return TableStyle(list(c))


# ═════════════════════════════════════════════════════════════════════════════
#  HEADER + FOOTER (drawn by PageTemplate)
# ═════════════════════════════════════════════════════════════════════════════

def _draw_border(cv, W, H):
    """Tanzania flag border around the page."""
    bw, gm = 5, 12
    for clr, x, y, w, h in [
        (GRN, gm, H-gm-bw, W-2*gm, bw),
        (GLD, W-gm-bw, gm, bw, H-2*gm),
        (BLK, gm, gm, W-2*gm, bw),
        (BLU, gm, gm, bw, H-2*gm),
    ]:
        cv.setFillColor(clr)
        cv.rect(x, y, w, h, fill=1, stroke=0)

def _draw_header(cv, W, H, LM, RM, exam, lang, school_disp, slogo, dlogo):
    """Official header at the TOP of every page."""
    bw = W - LM - RM
    bh = 2.8*cm
    by = H - 17  # below border

    # Green banner
    cv.setFillColor(GRN)
    cv.rect(LM, by-bh, bw, bh, fill=1, stroke=0)

    cx = LM + bw/2

    # Logos
    if slogo:
        cv.drawImage(slogo, LM+3, by-bh+3, width=1.6*cm, height=bh-6,
                     preserveAspectRatio=True, mask='auto')
    if dlogo:
        cv.drawImage(dlogo, LM+bw-3-1.6*cm, by-bh+3, width=1.6*cm, height=bh-6,
                     preserveAspectRatio=True, mask='auto')

    # Text
    cv.setFillColor(WHT)
    cv.setFont("Helvetica-Bold", 11)
    cv.drawCentredString(cx, by-14,
        "THE UNITED REPUBLIC OF TANZANIA" if lang=='en' else "JAMHURI YA MUUNGANO WA TANZANIA")
    cv.setFont("Helvetica-Bold", 9)
    cv.drawCentredString(cx, by-26,
        "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY" if lang=='en' else "WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA")
    cv.setFont("Helvetica", 7)
    st = "SECONDARY SCHOOL" if get_school_type_for_exam(exam)=='secondary' else "PRIMARY SCHOOL"
    cv.drawCentredString(cx, by-36, f"{st} — EXAMINATION RESULTS")

    # Flag bar
    for i, clr in enumerate([GRN, GLD, BLK, BLU]):
        cv.setFillColor(clr)
        cv.rect(LM+i*bw/4, by-41, bw/4, 3, fill=1, stroke=0)

    # School name
    cv.setFillColor(colors.HexColor("#FCD116"))
    cv.setFont("Helvetica-Bold", 13)
    cv.drawCentredString(cx, by-55, school_disp)

    # Location
    cv.setFillColor(WHT)
    cv.setFont("Helvetica", 7)
    loc = ''
    if exam.school and exam.school.district: loc = exam.school.district.upper()
    if exam.school and exam.school.region: loc += f" — {exam.school.region.upper()}" if loc else exam.school.region.upper()
    cv.drawCentredString(cx, by-66, loc or 'TANZANIA')

    # Gold line
    cv.setStrokeColor(GLD)
    cv.setLineWidth(2)
    cv.line(LM, by-bh-1, LM+bw, by-bh-1)

    return by - bh - 6  # y after header

def _draw_footer(cv, W, LM, RM, school_disp, page_num, total_pages):
    """Footer at the VERY BOTTOM — below all content."""
    fy = 1.0*cm  # footer y position (above bottom border)
    cv.setStrokeColor(GRN)
    cv.setLineWidth(0.5)
    cv.line(LM, fy+8, W-RM, fy+8)
    cv.setFont("Helvetica", 6.5)
    cv.setFillColor(DRK)
    cv.drawString(LM, fy-2, school_disp)
    cv.drawCentredString(W/2, fy-2, f"Page {page_num} of {total_pages}")
    cv.drawRightString(W-RM, fy-2, datetime.now().strftime('%d/%m/%Y %H:%M'))


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN
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

    # Logos
    slogo = dlogo = None
    if exam.school:
        slogo = _lf(exam.school.school_logo)
        dlogo = _lf(exam.school.district_logo)

    # Stats
    if N:
        avg_t = sum(r.total_score for r in results)/N
        avg_a = sum(float(r.average_score) for r in results)/N
        avg_p = sum(r.points for r in results)/N
        dc = Counter(r.division for r in results)
        cnt = len([s for s in (results[0].counted_subjects or '').split(',') if s.strip()]) if results else len(subjects)
    else:
        avg_t=avg_a=avg_p=0; dc=Counter(); cnt=len(subjects)

    def pct(n): return f"{n/N*100:.1f}%" if N else "0%"

    # Subject stats
    ss = []
    for subj in subjects:
        sc = [score_lookup[(r.student_id,subj.id)] for r in results if (r.student_id,subj.id) in score_lookup]
        if sc:
            ss.append({'n':subj.name,'a':round(sum(sc)/len(sc),1),'h':max(sc),'l':min(sc),
                       'p':round(sum(1 for s in sc if s>=40)/len(sc)*100,1)})

    # Styles
    styles = getSampleStyleSheet()
    T  = ParagraphStyle('T',  parent=styles['Heading1'], fontSize=13, textColor=GRN,
                        alignment=1, spaceAfter=2, spaceBefore=0, fontName='Helvetica-Bold')
    ST = ParagraphStyle('ST', parent=styles['Normal'], fontSize=8, textColor=DRK,
                        alignment=1, spaceAfter=1, spaceBefore=0)
    SH = ParagraphStyle('SH', parent=styles['Heading2'], fontSize=10, textColor=GRN,
                        fontName='Helvetica-Bold', spaceBefore=6, spaceAfter=3)

    story = []

    # ═══ PAGE 1: SUMMARY ═══
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f"{etype} {exam.year} — FORM {exam.form}" if lang=='en' else rlabel, T))
    story.append(Paragraph(exam.name, ST))
    story.append(Spacer(1, 0.3*cm))

    # ── Division + Stats ──
    story.append(Paragraph(get_section_title(exam, 'division_summary'), SH))

    dl = {'I':'Division I','II':'Division II','III':'Division III','IV':'Division IV','0':'Fail (0)'}
    if lang=='sw': dl = {'I':'Daraja I','II':'Daraja II','III':'Daraja III','IV':'Daraja IV','0':'Fail (0)'}

    dh = ["DIVISION","COUNT","%"] if lang=='en' else ["DARAJA","IDADI","ASILIMIA"]
    dr = [dh] + [[dl[d], str(dc.get(d,0)), pct(dc.get(d,0))] for d in ('I','II','III','IV','0')]
    dr.append(["Total" if lang=='en' else "Jumla", str(N), "100%"])

    dt = Table(dr, colWidths=[3.5*cm,2*cm,2*cm])
    dcmds = [
        ('BACKGROUND',(0,0),(-1,0),GRN),('TEXTCOLOR',(0,0),(-1,0),WHT),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8.5),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('INNERGRID',(0,0),(-1,-1),0.4,colors.HexColor("#ccc")),
        ('BOX',(0,0),(-1,-1),1.2,GRN),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHT,GRY]),
        ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
    ]
    for i,d in enumerate(('I','II','III','IV','0'),1):
        bg,fg = DIV_C.get(d,("fff","000"))
        dcmds += [('BACKGROUND',(0,i),(0,i),colors.HexColor(bg)),
                  ('TEXTCOLOR',(0,i),(0,i),colors.HexColor(fg)),
                  ('FONTNAME',(0,i),(0,i),'Helvetica-Bold')]
    dt.setStyle(_ts(*dcmds))

    if lang=='sw':
        sr = [["TAARIFA (NECTA)",""],["Wanafunzi",str(N)],["Wastani Jumla",f"{avg_t:.1f}"],
              ["Wastani Mean",f"{avg_a:.1f}"],["GPA",f"{avg_p:.2f}"],["Masomo",str(cnt)]]
    else:
        sr = [["PERFORMANCE (NECTA)",""],["Total Students",str(N)],["Overall Average",f"{avg_t:.1f}"],
              ["Mean of Averages",f"{avg_a:.1f}"],["Average Points (GPA)",f"{avg_p:.2f}"],["Subjects",str(cnt)]]

    st = Table(sr, colWidths=[4.5*cm,2.5*cm])
    st.setStyle(_ts(
        ('BACKGROUND',(0,0),(-1,0),GRN),('TEXTCOLOR',(0,0),(-1,0),WHT),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8.5),
        ('FONTNAME',(0,1),(-1,-1),'Helvetica'),
        ('ALIGN',(0,0),(-1,0),'CENTER'),('ALIGN',(0,1),(0,-1),'LEFT'),('ALIGN',(1,1),(-1,-1),'CENTER'),
        ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
        ('INNERGRID',(0,0),(-1,-1),0.4,colors.HexColor("#ccc")),
        ('BOX',(0,0),(-1,-1),1.2,GRN),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHT,GRY]),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),8),
    ))

    w = Table([[dt,'',st]], colWidths=[4*cm,0.5*cm,5*cm])
    w.setStyle(_ts([('VALIGN',(0,0),(-1,-1),('TOP'))]))
    story.append(w)
    story.append(Spacer(1, 0.3*cm))

    # ── Subject Stats ──
    if ss:
        story.append(Paragraph(get_section_title(exam, 'subject_stats'), SH))
        sh = ["SUBJECT","AVG","HIGH","LOW","PASS%"] if lang=='en' else ["SOMO","WASTANI","JUU","CHINI","KUFAULU"]
        sd = [sh]+[[s['n'],str(s['a']),str(s['h']),str(s['l']),f"{s['p']}%"] for s in ss]
        stbl = Table(sd, colWidths=[4*cm,2*cm,1.8*cm,1.8*cm,1.8*cm])
        stbl.setStyle(_ts(
            ('BACKGROUND',(0,0),(-1,0),GRN),('TEXTCOLOR',(0,0),(-1,0),WHT),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('ALIGN',(0,1),(0,-1),'LEFT'),
            ('INNERGRID',(0,0),(-1,-1),0.4,colors.HexColor("#ccc")),
            ('BOX',(0,0),(-1,-1),1.2,GRN),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHT,GRY]),
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
            nm = ' '.join(p for p in [r.student.first_name,r.student.middle_name or '',r.student.last_name] if p)
            if len(nm)>24: nm=nm[:22]+'..'
            td.append([str(r.position),nm,str(r.total_score),f"{r.average_score:.1f}",str(r.points),r.division])
        tt = Table(td, colWidths=[1*cm,5*cm,1.5*cm,1.5*cm,1.2*cm,1.2*cm])
        tt.setStyle(_ts(
            ('BACKGROUND',(0,0),(-1,0),GRN),('TEXTCOLOR',(0,0),(-1,0),WHT),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('ALIGN',(1,1),(1,-1),'LEFT'),
            ('INNERGRID',(0,0),(-1,-1),0.4,colors.HexColor("#ccc")),
            ('BOX',(0,0),(-1,-1),1.2,GRN),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHT,GRY]),
            ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
            ('BACKGROUND',(0,1),(0,1),GLD),('TEXTCOLOR',(0,1),(0,1),WHT),
            ('FONTNAME',(0,1),(0,1),'Helvetica-Bold'),
        ))
        story.append(tt)
        story.append(Spacer(1, 0.2*cm))

    # ── Grading Key ──
    _,gr = _gt(exam.form)
    gk = [[f"{g} ({rng})" for g,rng in gr]]
    gtbl = Table(gk, colWidths=[3*cm]*len(gr))
    gk_c = [('FONTNAME',(0,0),(-1,-1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
            ('BOX',(0,0),(-1,-1),0.8,GRN),('INNERGRID',(0,0),(-1,-1),0.4,colors.HexColor("#ccc"))]
    for i,(g,_) in enumerate(gr):
        gk_c.append(('BACKGROUND',(i,0),(i,0),colors.HexColor(FILL.get(g,("#C6F4D6","#145A32"))[0])))
    gtbl.setStyle(_ts(*gk_c))
    story.append(gtbl)

    # ═══ PAGE 2+: FULL RESULTS ═══
    story.append(PageBreak())

    n_subj = max(len(subjects),1)
    fsz = 5.8 if n_subj>=11 else 6.2 if n_subj>=9 else 6.8 if n_subj>=7 else 7.5
    rpp = 28 if n_subj<=5 else 22 if n_subj<=8 else 16
    chunks = [results[i:i+rpp] for i in range(0,N,rpp)]
    tp = len(chunks) or 1

    for pn,grp in enumerate(chunks,1):
        if pn>1: story.append(PageBreak())

        story.append(Paragraph(f"{school_disp} — {etype} {exam.year} — FORM {exam.form}" if lang=='en'
                               else f"{school_disp} — {rlabel}", T))
        story.append(Paragraph(f"{exam.name}  |  PAGE {pn}/{tp}", ST))
        story.append(Spacer(1, 0.2*cm))

        nw = 3*cm if n_subj<=7 else 2.5*cm
        avail = A4[0]-4*cm-nw-4*cm
        cs = max(0.7*cm, min(avail/n_subj, 1.4*cm))
        cw = [0.8*cm, nw, 0.6*cm] + [cs]*n_subj + [0.9*cm, 0.8*cm, 0.8*cm, 0.9*cm, 0.9*cm]

        hdrs = (["#","NAME","S"] if lang=='sw' else ["#","NAME","S"])
        hdrs += [s.name.upper()[:9] for s in subjects]
        hdrs += (["JUML","AVG","PTS","GPA","DIV"] if lang=='sw' else ["TOTAL","AVG","PTS","GPA","DIV"])

        data = [hdrs]
        for r in grp:
            nm = ' '.join(p for p in [r.student.first_name,r.student.middle_name or '',r.student.last_name] if p)
            mx = 16 if n_subj>=10 else 20 if n_subj>=8 else 24
            if len(nm)>mx: nm=nm[:mx-2]+'..'
            row = [str(r.position),nm,r.student.gender or 'M']
            for sub in subjects:
                sc = score_lookup.get((r.student_id,sub.id))
                row.append(str(sc) if sc is not None else '-')
            c=[s for s in (r.counted_subjects or '').split(',') if s.strip()]
            nc=len(c) if c else n_subj
            gpa=r.points/nc if nc else 0
            row += [str(r.total_score),f"{r.average_score:.1f}",str(r.points),f"{gpa:.2f}",r.division]
            data.append(row)

        tbl = Table(data, colWidths=cw, repeatRows=1)
        style = [
            ('BACKGROUND',(0,0),(-1,0),GRN),('TEXTCOLOR',(0,0),(-1,0),WHT),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),fsz),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('ALIGN',(1,1),(1,-1),'LEFT'),
            ('INNERGRID',(0,0),(-1,-1),0.25,colors.HexColor("#ccc")),
            ('BOX',(0,0),(-1,-1),1.2,GRN),
            ('TOPPADDING',(0,0),(-1,-1),1.5),('BOTTOMPADDING',(0,0),(-1,-1),1.5),
            ('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ]
        for i in range(1,len(data)):
            if i%2==0: style.append(('BACKGROUND',(0,i),(-1,i),GRY))
        for i,r in enumerate(grp,1):
            for si,sub in enumerate(subjects):
                sc = score_lookup.get((r.student_id,sub.id))
                if sc is not None:
                    bg,fg = _sf(sc,exam.form)
                    if bg: style.append(('BACKGROUND',(3+si,i),(3+si,i),colors.HexColor(bg)))
                    if fg: style.append(('TEXTCOLOR',(3+si,i),(3+si,i),colors.HexColor(fg)))
            dc = len(hdrs)-1
            if r.division in DIV_C:
                bg,fg = DIV_C[r.division]
                style += [('BACKGROUND',(dc,i),(dc,i),colors.HexColor(bg)),
                          ('TEXTCOLOR',(dc,i),(dc,i),colors.HexColor(fg)),
                          ('FONTNAME',(dc,i),(dc,i),'Helvetica-Bold')]
        tbl.setStyle(_ts(*style))
        story.append(tbl)

        story.append(Spacer(1, 0.15*cm))
        story.append(gtbl)

    # ── Signature ──
    story.append(Spacer(1, 1*cm))
    sig = Table([
        ["_"*30, "", "_"*30],
        ["Signature & Stamp", "", "Signature & Stamp"],
        ["Academic Officer", "", "Head of School"],
        ["", "", ""],
        ["Date: ________________________", "", ""],
    ], colWidths=[6*cm,2*cm,6*cm])
    sig.setStyle(_ts([
        ('FONTNAME',(0,0),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),7),
        ('TEXTCOLOR',(0,0),(-1,-1),DRK),
        ('ALIGN',(0,0),(0,-1),'LEFT'),('ALIGN',(2,0),(2,-1),'RIGHT'),
        ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
    ]))
    story.append(sig)

    # ═══ BUILD ═══
    buf = BytesIO()
    _pn = [0]

    def on_page(cv, doc):
        _pn[0] += 1
        W,H = A4
        LM,RM = 2.0*cm, 2.0*cm
        _draw_border(cv, W, H)
        _draw_header(cv, W, H, LM, RM, exam, lang, school_disp, slogo, dlogo)
        _draw_footer(cv, W, LM, RM, school_disp, _pn[0], tp+1)

    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2.0*cm, leftMargin=2.0*cm,
                            topMargin=4.0*cm,   # space for header
                            bottomMargin=1.5*cm) # space for footer
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='main')
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=on_page)])
    doc.build(story)
    buf.seek(0)

    resp = HttpResponse(buf, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{exam.name.replace(" ","_")}_Results.pdf"'
    return resp
