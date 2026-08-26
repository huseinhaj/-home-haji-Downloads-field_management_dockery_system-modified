#!/usr/bin/env python3
"""Generate POSHO YA KUJIKIMU PDF for Tamisemi format."""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import os


def generate_posho_pdf(output_path=None):
    """Generate the POSHO YA KUJIKIMU PDF document."""
    
    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), 'posho_ya_kujikimu_2026.pdf')
    
    # Page setup - landscape A4
    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        topMargin=1.5*cm,
        bottomMargin=1.5*cm,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'TitleCustom',
        parent=styles['Title'],
        fontSize=14,
        spaceAfter=4,
        textColor=colors.HexColor('#1a1a1a'),
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
    )
    
    subtitle_style = ParagraphStyle(
        'SubtitleCustom',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=2,
        textColor=colors.HexColor('#1a1a1a'),
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        leading=13,
    )
    
    header_style = ParagraphStyle(
        'HeaderCell',
        parent=styles['Normal'],
        fontSize=8,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        textColor=colors.white,
        leading=10,
    )
    
    cell_style = ParagraphStyle(
        'Cell',
        parent=styles['Normal'],
        fontSize=8,
        fontName='Helvetica',
        alignment=TA_CENTER,
        leading=10,
    )
    
    cell_left_style = ParagraphStyle(
        'CellLeft',
        parent=styles['Normal'],
        fontSize=8,
        fontName='Helvetica',
        alignment=TA_LEFT,
        leading=10,
    )
    
    # Colors
    HEADER_BG = colors.HexColor('#1F7A3D')  # Tanzania green
    HEADER_BG2 = colors.HexColor('#006B3F')  # Darker green
    LIGHT_GREEN = colors.HexColor('#E8F5E9')
    WHITE = colors.white
    
    elements = []
    
    # Title
    elements.append(Paragraph('OFISI YA WAZIRI MKUU TAMISEMI', title_style))
    elements.append(Spacer(1, 2*mm))
    
    # Subtitle
    subtitle_text = (
        'ORODHA MALIPO YA POSHO YA KUJIKIMU KWA WATUMISHI WALIOAJIRIWA '
        'KWENYE SEKTA YA ELIMU KATIKA MAMLAKA ZA SERIKALI ZA MITAA '
        'MWAKA 2026'
    )
    elements.append(Paragraph(subtitle_text, subtitle_style))
    elements.append(Spacer(1, 2*mm))
    
    # File number
    file_num_style = ParagraphStyle(
        'FileNum',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica-Bold',
        alignment=TA_LEFT,
        spaceAfter=4*mm,
    )
    elements.append(Paragraph('File No: 3901', file_num_style))
    
    # Column headers
    headers = [
        Paragraph('S/<br/>NO', header_style),
        Paragraph('JINA<br/>LA MTUMISHI', header_style),
        Paragraph('MKOA', header_style),
        Paragraph('WILAYA', header_style),
        Paragraph('KADA', header_style),
        Paragraph('SHULE<br/>ALIYOPO', header_style),
        Paragraph('KIASI<br/>ANACHODAI', header_style),
        Paragraph('ELIMU', header_style),
    ]
    
    # Data rows - first row filled, rest empty
    filled_row = [
        Paragraph('1', cell_style),
        Paragraph('HAJI HAMISI<br/>HUSENI', cell_left_style),
        Paragraph('KAGERA', cell_style),
        Paragraph('KYERWA DC', cell_style),
        Paragraph('ELIMU', cell_style),
        Paragraph('ISINGIRO<br/>SECONDARY<br/>SCHOOL', cell_left_style),
        Paragraph('715,000', cell_style),
        Paragraph('DIPLOMA', cell_style),
    ]
    
    data = [headers]
    data.append(filled_row)
    
    # Add 19 empty rows
    for i in range(2, 21):
        row = [
            Paragraph(str(i), cell_style),
            Paragraph('', cell_style),
            Paragraph('', cell_style),
            Paragraph('', cell_style),
            Paragraph('', cell_style),
            Paragraph('', cell_style),
            Paragraph('', cell_style),
            Paragraph('', cell_style),
        ]
        data.append(row)
    
    # GRAMAHA YA SKULI and JUMLA rows REMOVED per user request
    
    # Column widths
    col_widths = [
        1.2*cm,   # S/NO
        4.5*cm,   # JINA
        2.5*cm,   # MKOA
        2.5*cm,   # WILAYA
        2.0*cm,   # KADA
        4.0*cm,   # SHULE
        2.5*cm,   # KIASI
        2.0*cm,   # ELIMU
    ]
    
    # Create table
    table = Table(data, colWidths=col_widths, repeatRows=1)
    
    # Table style
    style_commands = [
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#999999')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#333333')),
        
        # Padding
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        
        # Alternating row colors
        ('BACKGROUND', (0, 1), (-1, 1), LIGHT_GREEN),  # First data row
    ]
    
    # Add alternating colors for empty rows
    for i in range(2, 21):
        if i % 2 == 0:
            style_commands.append(('BACKGROUND', (0, i), (-1, i), LIGHT_GREEN))
        else:
            style_commands.append(('BACKGROUND', (0, i), (-1, i), WHITE))
    
    # GRAMAHA and JUMLA rows REMOVED per user request
    
    table.setStyle(TableStyle(style_commands))
    
    elements.append(table)
    
    # Build PDF
    doc.build(elements)
    
    return output_path


if __name__ == '__main__':
    output = generate_posho_pdf()
    print(f'✅ PDF generated: {output}')
