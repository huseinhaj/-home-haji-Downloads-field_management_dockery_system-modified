"""
Huduma za Marking Scheme za Sahishi.

Mwalimu anascan/upload scheme (karatasi za majibu zenye bubbles za A–D —
na kwa masomo ya calculation: jibu fupi kwenye grid maalum ya mwisho).

Scheme inasomwa kwa OMR (bila AI):
  - CHOICE: bubbles → parsed_key {"1": "A", ...} → ScanAnswerKey auto
  - CALC:   bubbles za jibu fupi + picha zinabaki kama marejeleo

MUHIMU: scheme inatumia template ile ile ya karatasi (scan_pdf.py) —
mwalimu anachapisha karatasi tupu za template (bila QR ya mwanafunzi)
na anajaza majibu kwenye bubbles. QR ya scheme ina "s": 0.
"""
import io
import json
import logging

import cv2
import numpy as np

from .scan_qr import decode_qr

logger = logging.getLogger(__name__)

# Idadi ya maswali kwa ukurasa (sawa na template: 30 kwa ukurasa)
ROWS_PER_PAGE = 30

# Mwongozo wa kufafanua majibu ya CALC (jibu fupi):
# Grid ya CALC: bubbles 4 kwa kila swali = digits 0-9 kwa 2 bubbles?
# Kwa MVP: scheme ya CALC ina grid ile ile ya A-D; mwalimu anaweka
# "jibu fupi" kwa namba kwenye ukurasa wa mwisho — kwa sasa tunasoma
# A-D grid (kwa ajili ya choice section) na kurasa zinabaki kama marejeleo.
CALC_SHORT_ANSWER_NOTE = (
    'Kwa masomo ya calculation, scheme inabaki kama picha za marejeleo. '
    'Alama kamili zinapatikana kwenye review ya mwalimu.'
)


def pdf_to_images(pdf_bytes: bytes, scale: float = 2.0) -> list[bytes]:
    """Geuza PDF kuwa picha za PNG (ukurasa mmoja = picha moja)."""
    import pypdfium2 as pdfium

    out = []
    pdf = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
    try:
        for page in pdf:
            bitmap = page.render(scale=scale)  # scale 2 ≈ 144 dpi
            pil_image = bitmap.to_pil()
            buf = io.BytesIO()
            pil_image.save(buf, format='PNG')
            out.append(buf.getvalue())
    finally:
        pdf.close()
    return out


def parse_scheme_pages(images: list[bytes], expected_exam_id: int = None,
                       expected_subject_id: int = None) -> dict:
    """
    Soma kurasa za scheme (picha au PDF zilizogeuzwa picha).

    Inarudi:
    {
      "kind": "CHOICE" | "CALC",
      "parsed_key": {"1": "A", ...},
      "pages": [{"page_number": 1, "parsed": {...}, "image": bytes}, ...],
      "warnings": [...],
    }
    """
    warnings = []
    pages_out = []
    combined_key = {}

    for idx, data in enumerate(images, start=1):
        qr = decode_qr(data)
        answers = read_scheme_bubbles(data)

        # Ukurasa wa template una QR {"e": exam, "s": 0, "p": page, "sub": subject}
        page_number = qr['p'] if qr else idx
        is_scheme_page = bool(qr and qr.get('s') == 0)

        # Kama tunatarajia exam/subject maalum, thibitisha
        if qr and expected_exam_id and qr.get('e') not in (None, expected_exam_id):
            warnings.append(
                f'Ukurasa {idx}: QR inaonyesha mtihani tofauti (#{qr.get("e")}).'
            )
        if qr and expected_subject_id and qr.get('sub') not in (0, None, expected_subject_id):
            warnings.append(
                f'Ukurasa {idx}: QR inaonyesha somo tofauti (#{qr.get("sub")}).'
            )

        if not is_scheme_page:
            warnings.append(
                f'Ukurasa {idx}: hakuna QR ya scheme (s=0) — inaonekana ni karatasi ya mwanafunzi. '
                'Imepuuzwa kwenye key, ila picha imehifadhiwa.'
            )

        # Unganisha majibu yaliyosomwa
        filled = {q: a for q, a in answers.items() if a}
        for q, a in filled.items():
            combined_key.setdefault(q, a)  # ukurasa wa kwanza unashinda

        pages_out.append({
            'page_number': page_number,
            'parsed': filled,
            'image': data,
        })

    # Kind: kama kuna majibu → CHOICE; vinginevyo CALC (marejeleo tu)
    kind = 'CHOICE' if combined_key else 'CALC'
    if not combined_key:
        warnings.append(
            'Hakuna bubbles zilizojazwa zilizosomwa. Scheme imehifadhiwa kama '
            'marejeleo (CALC). Kwa masomo ya calculation hii ni kawaida.'
        )

    return {
        'kind': kind,
        'parsed_key': combined_key,
        'pages': pages_out,
        'warnings': warnings,
    }


def read_scheme_bubbles(image_bytes: bytes) -> dict:
    """Soma bubbles za scheme kwa OMR (grid ile ile ya template)."""
    from .scan_grader import read_answers_omr
    return read_answers_omr(image_bytes, rows=ROWS_PER_PAGE)


def sync_answer_key(scheme) -> int:
    """Andika parsed_key ya scheme kwenye ScanAnswerKey (CHOICE pekee)."""
    from results.scan_models import ScanAnswerKey

    if not scheme.is_choice:
        return 0

    key, _ = ScanAnswerKey.objects.get_or_create(
        exam=scheme.exam, subject=scheme.subject,
    )
    key.key = scheme.parsed_key
    key.save()
    return len(key.key)


def build_scheme_sheet_pdf(exam, subject, pages=1, n_questions=90) -> bytes:
    """
    Tengeneza PDF ya karatasi za SCHEME tupu (bubbles bila QR ya mwanafunzi).
    QR ya scheme ina s=0 (s=0 inamaanisha scheme).
    Kurasa 3 x maswali 30 = maswali 90.
    """
    from .scan_pdf import (
        BUBBLE_DY_MM, BUBBLE_DX_MM, BUBBLE_R_MM, BUBBLE_X0_MM, BUBBLE_Y0_MM,
        LETTERS,
    )
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    for page in range(1, pages + 1):
        q_start = (page - 1) * 30

        # Header
        c.setFont('Helvetica-Bold', 13)
        c.drawString(20 * mm, height - 18 * mm, 'MARKING SCHEME')
        c.setFont('Helvetica', 9)
        c.drawString(20 * mm, height - 24 * mm,
                     f'{exam.name} | Form {exam.form}'
                     f'{" " + exam.stream if exam.stream else ""} | {exam.year}')
        c.setFont('Helvetica-Bold', 10)
        c.drawString(20 * mm, height - 31 * mm, f'Somo: {subject.name}')

        # QR ya scheme (s=0)
        from .scan_qr import make_qr_png
        qr_bytes = make_qr_png(exam.pk, 0, page, subject.pk)
        c.drawImage(ImageReader(io.BytesIO(qr_bytes)),
                    width - 40 * mm, height - 42 * mm, 22 * mm, 22 * mm)

        # Maelekezo
        c.setFont('Helvetica-Oblique', 8)
        c.drawString(20 * mm, height - 53 * mm,
                     'Jaza jibu sahihi kwenye duara kwa pen ya blu. Ukurasa %d — maswali %d-%d'
                     % (page, q_start + 1, q_start + 30))

        # Bubbles
        for i in range(30):
            qnum = q_start + i + 1
            y = (BUBBLE_Y0_MM + i * BUBBLE_DY_MM) * mm
            y_from_top = height - y
            if y_from_top < 20 * mm:
                break
            c.setFont('Helvetica', 8)
            c.drawString(20 * mm, y_from_top, f'{qnum}.')
            for j, letter in enumerate(LETTERS):
                bx = (BUBBLE_X0_MM + j * BUBBLE_DX_MM) * mm
                c.setLineWidth(0.8)
                c.circle(bx, y_from_top + BUBBLE_R_MM, BUBBLE_R_MM * mm, stroke=1, fill=0)
                c.setFont('Helvetica', 6)
                c.drawString(bx - 1.2 * mm, y_from_top - 1.8 * mm, letter)

        c.showPage()

    c.save()
    return buf.getvalue()
