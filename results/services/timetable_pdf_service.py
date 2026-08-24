"""timetable_pdf_service.py — Generate a printable PDF of the class timetable.

The PDF includes the school header (name, district, logos), and a
per-day table showing every class's lessons across time slots.
"""
from __future__ import annotations

import io
import os
import base64
from datetime import datetime

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT


def _load_logo_b64(field, b64_field_value=''):
    """Load logo — first try base64 stored in DB, then fallback to ImageField."""
    if b64_field_value and b64_field_value.startswith('data:'):
        return b64_field_value
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
                    '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.svg': 'image/svg+xml'}
        mime = mime_map.get(ext, 'image/png')
        b64 = base64.b64encode(data).decode('ascii')
        return f'data:{mime};base64,{b64}'
    except Exception:
        return ''


def _logo_image(b64_uri, max_width=50, max_height=50):
    """Convert a base64 data URI to a ReportLab Image, or return None."""
    if not b64_uri:
        return None
    try:
        from reportlab.lib.utils import ImageReader
        import base64 as b64mod
        # Strip data URI prefix
        if ',' in b64_uri:
            b64_data = b64_uri.split(',', 1)[1]
        else:
            b64_data = b64_uri
        img_bytes = b64mod.b64decode(b64_data)
        img = ImageReader(io.BytesIO(img_bytes))
        # Scale to fit
        iw, ih = img.getSize()
        scale = min(max_width / iw, max_height / ih)
        return img, iw * scale, ih * scale
    except Exception:
        return None


# ── Color Palette ──
GREEN_DARK   = colors.HexColor('#1B5E20')
GREEN_MID    = colors.HexColor('#2E7D32')
GREEN_LIGHT  = colors.HexColor('#4CAF50')
GOLD         = colors.HexColor('#D9A441')
BLUE_DARK    = colors.HexColor('#1A237E')
BLUE_MID     = colors.HexColor('#1565C0')
GREY_BG      = colors.HexColor('#F5F7FA')
WHITE        = colors.white
DARK_TEXT     = colors.HexColor('#212121')
LIGHT_TEXT    = colors.HexColor('#FAFAFA')
AMBER_BG     = colors.HexColor('#FFF8E1')
BREAK_BG     = colors.HexColor('#ECEFF1')
ROW_ALT      = colors.HexColor('#F1F8E9')


def generate_timetable_pdf_response(school):
    """Generate a PDF of the school's class timetable.

    Returns an HttpResponse with the PDF content.
    """
    from ..models import ClassTimetableEntry, TimeSlot

    current_year = datetime.now().year

    # Load data
    slots = list(TimeSlot.objects.filter(school=school).order_by('day_of_week', 'order'))
    entries = ClassTimetableEntry.objects.filter(school=school).select_related('subject', 'teacher')
    entry_map = {(e.form, e.stream, e.time_slot_id): e for e in entries}

    # Get all classes
    class_keys = sorted({(e.form, e.stream) for e in entries})
    if not class_keys:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        styles = getSampleStyleSheet()
        doc.build([Paragraph("No timetable data available.", styles['Normal'])])
        buf.seek(0)
        response = HttpResponse(buf.read(), content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="timetable.pdf"'
        return response

    # Load school logos
    slogo_uri = _load_logo_b64(school.school_logo, getattr(school, 'school_logo_b64', ''))
    dlogo_uri = _load_logo_b64(school.district_logo, getattr(school, 'district_logo_b64', ''))

    # Build PDF — landscape A4
    buf = io.BytesIO()
    page_w, page_h = landscape(A4)
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
    )

    styles = getSampleStyleSheet()

    # ── Styles ──
    ministry_style = ParagraphStyle(
        'Ministry', parent=styles['Normal'], fontSize=9, spaceAfter=1,
        textColor=BLUE_DARK, alignment=TA_CENTER, fontName='Helvetica-Bold',
    )
    district_style = ParagraphStyle(
        'District', parent=styles['Normal'], fontSize=10, spaceAfter=1,
        textColor=BLUE_MID, alignment=TA_CENTER, fontName='Helvetica-Bold',
    )
    school_style = ParagraphStyle(
        'SchoolName', parent=styles['Normal'], fontSize=14, spaceAfter=1,
        textColor=GREEN_DARK, alignment=TA_CENTER, fontName='Helvetica-Bold',
    )
    title_style = ParagraphStyle(
        'TTitle', parent=styles['Title'], fontSize=16, spaceAfter=2,
        textColor=GOLD, alignment=TA_CENTER, fontName='Helvetica-Bold',
    )
    year_style = ParagraphStyle(
        'Year', parent=styles['Normal'], fontSize=12, spaceAfter=2,
        textColor=DARK_TEXT, alignment=TA_CENTER, fontName='Helvetica-Bold',
    )
    subtitle_style = ParagraphStyle(
        'TSub', parent=styles['Normal'], fontSize=9, spaceAfter=2,
        textColor=colors.HexColor('#555555'), alignment=TA_CENTER,
    )
    day_header_style = ParagraphStyle(
        'DayH', parent=styles['Normal'], fontSize=11, fontName='Helvetica-Bold',
        textColor=WHITE, backColor=GREEN_MID, spaceBefore=6, spaceAfter=2,
        leftIndent=0, borderPadding=(5, 5, 5, 5),
    )
    cell_style = ParagraphStyle(
        'TCell', parent=styles['Normal'], fontSize=7, leading=9,
        alignment=TA_CENTER,
    )
    cell_bold = ParagraphStyle(
        'TCellB', parent=cell_style, fontName='Helvetica-Bold',
        textColor=GREEN_DARK,
    )
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'], fontSize=7,
        textColor=colors.HexColor('#888888'), alignment=TA_CENTER,
        spaceBefore=4,
    )

    elements = []

    # ── Header Block ──
    # Logos
    slogo_img = _logo_image(slogo_uri, max_width=50, max_height=50)
    dlogo_img = _logo_image(dlogo_uri, max_width=50, max_height=50)

    logo_row_data = [[dlogo_img or '', '', slogo_img or '']]
    logo_row = Table(logo_row_data, colWidths=[3.5 * cm, page_w - 7 * cm, 3.5 * cm])
    logo_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(logo_row)
    elements.append(Spacer(1, 2 * mm))

    # Ministry line
    elements.append(Paragraph("MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY", ministry_style))

    # District line
    district_name = school.district.upper() if school.district else 'KYERWA DISTRICT COUNCIL'
    elements.append(Paragraph(f"{district_name}", district_style))

    # School name
    school_name = school.name.upper() if school.name else 'ISINGIRO SECONDARY SCHOOL'
    elements.append(Paragraph(f"{school_name}", school_style))

    elements.append(Spacer(1, 3 * mm))

    # Title bar — colored background
    title_bar_data = [[
        Paragraph(
            f"GENERAL SCHOOL TIME TABLE — {current_year}",
            ParagraphStyle('TitleBar', parent=styles['Normal'], fontSize=14,
                           fontName='Helvetica-Bold', textColor=WHITE, alignment=TA_CENTER)
        )
    ]]
    title_bar = Table(title_bar_data, colWidths=[page_w - 3 * cm])
    title_bar.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GREEN_DARK),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    elements.append(title_bar)
    elements.append(Spacer(1, 2 * mm))

    # Subtitle
    elements.append(Paragraph("Standing Weekly Schedule", subtitle_style))
    elements.append(Spacer(1, 3 * mm))

    # ── Build per-day tables ──
    for day_num, day_label in TimeSlot.DAY_CHOICES:
        day_slots = [s for s in slots if s.day_of_week == day_num]
        if not day_slots:
            continue

        # Day header bar
        day_bar_data = [[
            Paragraph(
                f"  {day_label.upper()}",
                ParagraphStyle('DH', parent=styles['Normal'], fontSize=11,
                               fontName='Helvetica-Bold', textColor=WHITE)
            )
        ]]
        day_bar = Table(day_bar_data, colWidths=[page_w - 3 * cm])
        day_bar.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), GREEN_MID),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('ROUNDEDCORNERS', [3, 3, 0, 0]),
        ]))
        elements.append(day_bar)

        # Build table: columns = [Class | time_slot_1 | time_slot_2 | ...]
        header_row = [Paragraph("<b>Class</b>", ParagraphStyle(
            'CH', parent=cell_style, fontName='Helvetica-Bold', textColor=WHITE, fontSize=8))]
        for slot in day_slots:
            header_row.append(Paragraph(
                f"<b>{slot.start_time.strftime('%H:%M')}<br/>{slot.end_time.strftime('%H:%M')}</b>",
                ParagraphStyle('CH2', parent=cell_style, fontName='Helvetica-Bold',
                               textColor=WHITE, fontSize=7)
            ))

        data = [header_row]

        for form, stream in class_keys:
            row_label = f"Form {form}{stream}" if stream else f"Form {form}"
            row = [Paragraph(f"<b>{row_label}</b>", cell_bold)]
            for slot in day_slots:
                entry = entry_map.get((form, stream, slot.id))
                if slot.is_teaching_slot:
                    if entry:
                        subj_name = entry.subject.name if entry.subject else '?'
                        teacher_name = ''
                        if entry.teacher:
                            teacher_name = entry.teacher.full_name or entry.teacher.email or ''
                        cell_content = Paragraph(
                            f"<b>{subj_name}</b><br/><font size=5 color='#666666'>{teacher_name}</font>",
                            cell_style,
                        )
                    else:
                        cell_content = Paragraph("—", cell_style)
                else:
                    label = slot.label or '—'
                    cell_content = Paragraph(
                        f"<b><i>{label}</i></b>",
                        ParagraphStyle('NonTeach', parent=cell_style,
                                       textColor=colors.HexColor('#546E7A'), fontSize=7),
                    )
                row.append(cell_content)
            data.append(row)

        # Column widths
        avail_width = page_w - 3 * cm
        class_col_width = 2.5 * cm
        remaining = avail_width - class_col_width
        slot_col_width = remaining / max(len(day_slots), 1)
        col_widths = [class_col_width] + [slot_col_width] * len(day_slots)

        t = Table(data, colWidths=col_widths, repeatRows=1)

        style_cmds = [
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), GREEN_DARK),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            # Class column
            ('BACKGROUND', (0, 1), (0, -1), AMBER_BG),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#BDBDBD')),
            ('BOX', (0, 0), (-1, -1), 1, GREEN_MID),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]

        # Alternate row backgrounds
        for i in range(1, len(data)):
            if i % 2 == 0:
                style_cmds.append(('BACKGROUND', (1, i), (-1, i), ROW_ALT))

        # Highlight non-teaching columns
        for col_idx, slot in enumerate(day_slots, start=1):
            if not slot.is_teaching_slot:
                style_cmds.append(('BACKGROUND', (col_idx, 0), (col_idx, 0), colors.HexColor('#78909C')))
                style_cmds.append(('BACKGROUND', (col_idx, 1), (col_idx, -1), BREAK_BG))

        t.setStyle(TableStyle(style_cmds))
        elements.append(t)
        elements.append(Spacer(1, 5 * mm))

    # ── Footer ──
    elements.append(Spacer(1, 10 * mm))

    # Divider line
    divider_data = [['']]
    divider = Table(divider_data, colWidths=[page_w - 3 * cm])
    divider.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 1, GREEN_MID),
    ]))
    elements.append(divider)
    elements.append(Spacer(1, 3 * mm))

    school_name_footer = school.name if school.name else 'Isingiro Secondary School'
    elements.append(Paragraph(
        f"<b>{school_name_footer}</b> — All Rights Reserved © {current_year}",
        footer_style
    ))
    elements.append(Paragraph(
        "Generated by School Results System",
        ParagraphStyle('Footer2', parent=footer_style, fontSize=6, textColor=colors.HexColor('#AAAAAA'))
    ))

    # Build
    doc.build(elements)
    buf.seek(0)

    response = HttpResponse(buf.read(), content_type='application/pdf')
    filename = f"Timetable_{school.name.replace(' ', '_')}_{current_year}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


def generate_timetable_pdf_inline_response(school):
    """Same as above but with Content-Disposition: inline for iframe embedding."""
    response = generate_timetable_pdf_response(school)
    current_year = datetime.now().year
    filename = f"Timetable_{school.name.replace(' ', '_')}_{current_year}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
