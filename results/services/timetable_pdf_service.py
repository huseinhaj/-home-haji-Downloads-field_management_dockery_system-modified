"""timetable_pdf_service.py — Generate a printable PDF of the class timetable.

The PDF includes the school header (name, district, logos), and a
per-day table showing every class's lessons across time slots.
"""
from __future__ import annotations

import io
import os
import base64

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


def generate_timetable_pdf_response(school):
    """Generate a PDF of the school's class timetable.

    Returns an HttpResponse with the PDF content.
    """
    from ..models import ClassTimetableEntry, TimeSlot

    GREEN = colors.HexColor('#1F7A3D')
    GOLD = colors.HexColor('#D9A441')
    GREY_BG = colors.HexColor('#F2F4F7')
    WHITE = colors.white

    # Load data
    slots = list(TimeSlot.objects.filter(school=school).order_by('day_of_week', 'order'))
    entries = ClassTimetableEntry.objects.filter(school=school).select_related('subject', 'teacher')
    entry_map = {(e.form, e.stream, e.time_slot_id): e for e in entries}

    # Get all classes
    class_keys = sorted({(e.form, e.stream) for e in entries})
    if not class_keys:
        # Fallback: no timetable
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

    # Build PDF — landscape A4 for wide timetable tables
    buf = io.BytesIO()
    page_w, page_h = landscape(A4)
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TTitle', parent=styles['Title'], fontSize=16, spaceAfter=2,
        textColor=GREEN, alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        'TSub', parent=styles['Normal'], fontSize=10, spaceAfter=2,
        textColor=colors.HexColor('#333333'), alignment=TA_CENTER,
    )
    day_style = ParagraphStyle(
        'TDay', parent=styles['Normal'], fontSize=11, spaceBefore=8, spaceAfter=4,
        textColor=WHITE, fontName='Helvetica-Bold',
    )
    cell_style = ParagraphStyle(
        'TCell', parent=styles['Normal'], fontSize=7, leading=9,
        alignment=TA_CENTER,
    )
    cell_bold = ParagraphStyle(
        'TCellB', parent=cell_style, fontName='Helvetica-Bold',
        textColor=GREEN,
    )
    teacher_style = ParagraphStyle(
        'TTeacher', parent=cell_style, fontSize=6, leading=8,
        textColor=colors.HexColor('#666666'),
    )

    elements = []

    # ── Header ──
    # Logo row
    logo_data = []
    slogo_img = _logo_image(slogo_uri, max_width=45, max_height=45)
    dlogo_img = _logo_image(dlogo_uri, max_width=45, max_height=45)

    school_name = school.name.upper()
    district_name = school.district.upper() if school.district else ''

    header_text = f"<b>{school_name}</b>"
    if district_name:
        header_text += f"<br/><font size=8>{district_name}</font>"

    elements.append(Paragraph(header_text, subtitle_style))
    elements.append(Paragraph("CLASS TIMETABLE", title_style))
    elements.append(Paragraph("Standing Weekly Schedule", ParagraphStyle(
        'TSub2', parent=subtitle_style, fontSize=9, textColor=colors.HexColor('#666666'),
    )))
    elements.append(Spacer(1, 4 * mm))

    # ── Build per-day tables ──
    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    for day_num, day_label in TimeSlot.DAY_CHOICES:
        day_slots = [s for s in slots if s.day_of_week == day_num]
        if not day_slots:
            continue

        # Day header
        elements.append(Paragraph(f"  {day_label.upper()}", ParagraphStyle(
            'DayH', parent=styles['Normal'], fontSize=11, fontName='Helvetica-Bold',
            textColor=WHITE, backColor=GREEN, spaceBefore=6, spaceAfter=2,
            leftIndent=0, borderPadding=(4, 4, 4, 4),
        )))

        # Build table: columns = [Class | time_slot_1 | time_slot_2 | ...]
        # Header row: Class | 07:00-07:50 | 08:00-08:40 | ...
        header_row = ['Class']
        for slot in day_slots:
            header_row.append(Paragraph(
                f"<b>{slot.start_time.strftime('%H:%M')}<br/>{slot.end_time.strftime('%H:%M')}</b>",
                cell_style
            ))

        data = [header_row]

        # One row per class
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
                    # Non-teaching slot
                    label = slot.label or '—'
                    cell_content = Paragraph(
                        f"<i>{label}</i>",
                        ParagraphStyle('NonTeach', parent=cell_style, textColor=colors.HexColor('#888888')),
                    )
                row.append(cell_content)
            data.append(row)

        # Column widths: Class column ~2.5cm, rest distributed evenly
        avail_width = page_w - 3 * cm  # minus margins
        class_col_width = 2.5 * cm
        remaining = avail_width - class_col_width
        slot_col_width = remaining / max(len(day_slots), 1)
        col_widths = [class_col_width] + [slot_col_width] * len(day_slots)

        t = Table(data, colWidths=col_widths, repeatRows=1)

        # Style
        style_cmds = [
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), GREEN),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            # Class column
            ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#fdf6e3')),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]

        # Alternate row backgrounds
        for i in range(1, len(data)):
            if i % 2 == 0:
                style_cmds.append(('BACKGROUND', (0, i), (-1, i), GREY_BG))

        # Highlight non-teaching columns (break, lunch, etc.)
        for col_idx, slot in enumerate(day_slots, start=1):
            if not slot.is_teaching_slot:
                style_cmds.append(('BACKGROUND', (col_idx, 0), (col_idx, 0), colors.HexColor('#888888')))
                style_cmds.append(('BACKGROUND', (col_idx, 1), (col_idx, -1), colors.HexColor('#F0F0F0')))

        t.setStyle(TableStyle(style_cmds))
        elements.append(t)
        elements.append(Spacer(1, 4 * mm))

    # ── Footer ──
    elements.append(Spacer(1, 8 * mm))
    footer_style = ParagraphStyle(
        'TFooter', parent=styles['Normal'], fontSize=8,
        textColor=colors.HexColor('#999999'), alignment=TA_CENTER,
    )
    elements.append(Paragraph("Generated by School Results System", footer_style))

    # Build
    doc.build(elements)
    buf.seek(0)

    response = HttpResponse(buf.read(), content_type='application/pdf')
    filename = f"Timetable_{school.name.replace(' ', '_')}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


def generate_timetable_pdf_inline_response(school):
    """Same as above but with Content-Disposition: inline for iframe embedding."""
    response = generate_timetable_pdf_response(school)
    filename = f"Timetable_{school.name.replace(' ', '_')}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
